import logging
import requests
import json
import hmac
import hashlib
import time
from datetime import timedelta, datetime
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)
ROUTER_URL = "http://192.168.1.1"

CONF_TESTURL = "testurl"
DEFAULT_TESTURL = "baidu.com"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_TESTURL, default=DEFAULT_TESTURL): cv.string,
})

class RouterAPI:
    """路由器 API 处理登录和数据获取"""
    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._session = requests.Session()

    def hex_hmac_md5(self, key, data):
        return hmac.new(key.encode(), data.encode(), hashlib.md5).hexdigest()

    def login(self):
        """登录路由器"""
        url = f"{ROUTER_URL}/goform/login"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        username_hmac = self.hex_hmac_md5("0123456789", self._username)
        password_hmac = self.hex_hmac_md5("0123456789", self._password)
        data = {"username": username_hmac, "password": password_hmac}
        
        try:
            response = self._session.post(url, headers=headers, json=data, timeout=5)
            response.raise_for_status()
            self._session.cookies = response.cookies
            return True
        except requests.RequestException as e:
            _LOGGER.error("Router login failed: %s", e)
            return False

    def get_status(self):
        """获取路由器状态"""
        url = f"{ROUTER_URL}/action/get_mgdb_params"
        data = {
            "keys": [
                "device_battery_level_percent", "device_battery_temperature",
                "mnet_sysmode", "mnet_sig_level", "mnet_roam_status", 
                "mnet_operator_name", "rt_internet_mode", "dialup_dial_status",
                "wifi_work_status", "sms_unread_count", "fota_curr_istatus"
            ]
        }

        try:
            response = self._session.post(url, json=data, timeout=5)
            response.raise_for_status()
            return response.json().get("data", {})
        except requests.RequestException as e:
            _LOGGER.error("Failed to fetch router status: %s", e)
            return {}

class RouterBatterySensor(SensorEntity):
    """电池百分比传感器"""
    _attr_name = "Router Battery Level"
    _attr_unit_of_measurement = "%"
    _attr_device_class = "battery"
    _attr_state_class = "measurement"

    def __init__(self, router_api):
        self._router_api = router_api
        self._state = None

    @property
    def state(self):
        return float(self._state) if self._state is not None else None

    @Throttle(SCAN_INTERVAL)
    def update(self):
        status = self._router_api.get_status()
        self._state = status.get("device_battery_level_percent")

class RouterBatteryTempSensor(SensorEntity):
    """电池温度传感器"""
    _attr_name = "Router Battery Temperature"
    _attr_unit_of_measurement = "°C"
    _attr_device_class = "temperature"
    _attr_state_class = "measurement"

    def __init__(self, router_api):
        self._router_api = router_api
        self._state = None

    @property
    def state(self):
        return float(self._state) if self._state is not None else None

    @Throttle(SCAN_INTERVAL)
    def update(self):
        status = self._router_api.get_status()
        self._state = status.get("device_battery_temperature")

class RouterNetworkSensor(SensorEntity):
    """网络信号强度传感器"""
    _attr_name = "Router Network Signal Level"
    _attr_unit_of_measurement = "dB"
    _attr_device_class = "signal_strength"
    _attr_state_class = "measurement"

    def __init__(self, router_api):
        self._router_api = router_api
        self._state = None

    @property
    def state(self):
        return float(self._state) if self._state is not None else None

    @Throttle(SCAN_INTERVAL)
    def update(self):
        status = self._router_api.get_status()
        self._state = status.get("mnet_sig_level")

class RouterExtraSensor(SensorEntity):
    """额外信息传感器"""
    _attr_name = "Router Extra Info"

    def __init__(self, router_api):
        self._router_api = router_api
        self._state = None
        self._attributes = {}

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @Throttle(SCAN_INTERVAL)
    def update(self):
        status = self._router_api.get_status()
        self._state = status.get("mnet_sysmode", "Unknown")  # 例如 5G/4G
        self._attributes = {
            "roaming_status": status.get("mnet_roam_status"),
            "operator": status.get("mnet_operator_name"),
            "internet_mode": status.get("rt_internet_mode"),
            "dial_status": status.get("dialup_dial_status"),
            "wifi_status": status.get("wifi_work_status"),
            "unread_sms": status.get("sms_unread_count"),
            "firmware_status": status.get("fota_curr_istatus")
        }

class NetworkProberSensor(SensorEntity):
    """网络探测传感器"""
    _attr_name = "Internet Connectivity"
    _attr_unit_of_measurement = "ms"
    _attr_device_class = "connectivity"
    _attr_state_class = "measurement"

    def __init__(self, test_url):
        self._test_url = test_url if test_url.startswith("http") else f"https://{test_url}"
        self._state = None
        self._last_probe_error = None

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return {"last_probe_error": self._last_probe_error}

    @Throttle(SCAN_INTERVAL)
    def update(self):
        start_time = time.time()
        try:
            response = requests.get(self._test_url, timeout=5)
            response.raise_for_status()
            self._state = round((time.time() - start_time) * 1000, 2)  # 毫秒
            self._last_probe_error = None
        except requests.RequestException as e:
            self._state = None
            self._last_probe_error = str(e)

def setup_platform(hass, config, add_entities, discovery_info=None):
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    test_url = config[CONF_TESTURL]
    
    router_api = RouterAPI(username, password)
    
    if not router_api.login():
        _LOGGER.error("Router login failed, sensors will not be created")
        return

    add_entities([
        RouterBatterySensor(router_api),
        RouterBatteryTempSensor(router_api),
        RouterNetworkSensor(router_api),
        RouterExtraSensor(router_api),
        NetworkProberSensor(test_url)
    ], True)