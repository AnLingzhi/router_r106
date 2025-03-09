import logging
import requests
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

DEFAULT_TESTURL = "baidu.com"
SCAN_INTERVAL = timedelta(minutes=1)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional('testurl', default=DEFAULT_TESTURL): cv.string,
})


class RouterAPI:
    """路由器 API 交互类，管理登录和数据获取。"""

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._session = requests.Session()
        self.logged_in = False

    def hex_hmac_md5(self, key, data):
        """HMAC-MD5 加密"""
        return hmac.new(key.encode(), data.encode(), hashlib.md5).hexdigest()

    def login(self):
        """登录路由器"""
        url = "http://192.168.1.1/goform/login"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": "http://192.168.1.1/common/login.html"
        }
        username_hmac = self.hex_hmac_md5("0123456789", self._username)
        password_hmac = self.hex_hmac_md5("0123456789", self._password)
        data = {"username": username_hmac, "password": password_hmac}

        try:
            response = self._session.post(url, headers=headers, json=data)
            response.raise_for_status()
            self._session.cookies = response.cookies
            self.logged_in = True
            _LOGGER.info("Router login successful")
        except requests.exceptions.RequestException as e:
            _LOGGER.error("Router login failed: %s", e)
            self.logged_in = False

    def get_status(self):
        """获取路由器状态信息"""
        if not self.logged_in:
            self.login()
        if not self.logged_in:  # 再次检查是否登录成功
            return None

        url = "http://192.168.1.1/action/get_mgdb_params"
        data = {
            "keys": [
                "device_uptime",
                "device_battery_level_percent",
                "device_battery_temperature",
                "mnet_sysmode",
                "mnet_sig_level",
                "mnet_roam_status",
                "mnet_operator_name",
                "rt_internet_mode",
                "rt_eth_conn_info",
                "dialup_dial_status",
                "wifi_work_status",
                "sms_unread_count",
                "fota_curr_istatus"
            ]
        }

        try:
            response = self._session.post(url, json=data)
            response.raise_for_status()
            return response.json().get("data", {})
        except requests.exceptions.RequestException as e:
            _LOGGER.error("Failed to fetch router status: %s", e)
            return None


class RouterBatterySensor(SensorEntity):
    """电池百分比传感器"""

    def __init__(self, router_api):
        self._router_api = router_api
        self._attr_name = "Router Battery Level"
        self._attr_unit_of_measurement = "%"
        self._attr_unique_id = "router_battery_level"
        self._state = None

    @property
    def state(self):
        return self._state

    @Throttle(SCAN_INTERVAL)
    def update(self):
        status = self._router_api.get_status()
        if status:
            self._state = status.get("device_battery_level_percent")


class RouterBatteryTempSensor(SensorEntity):
    """电池温度传感器"""

    def __init__(self, router_api):
        self._router_api = router_api
        self._attr_name = "Router Battery Temperature"
        self._attr_unit_of_measurement = "°C"
        self._attr_unique_id = "router_battery_temp"
        self._state = None

    @property
    def state(self):
        return self._state

    @Throttle(SCAN_INTERVAL)
    def update(self):
        status = self._router_api.get_status()
        if status:
            self._state = status.get("device_battery_temperature")


class RouterNetworkModeSensor(SensorEntity):
    """网络模式传感器"""

    def __init__(self, router_api):
        self._router_api = router_api
        self._attr_name = "Router Network Mode"
        self._attr_unique_id = "router_network_mode"
        self._state = None

    @property
    def state(self):
        return self._state

    @Throttle(SCAN_INTERVAL)
    def update(self):
        status = self._router_api.get_status()
        if status:
            self._state = status.get("mnet_sysmode")


class RouterExtraAttributesSensor(SensorEntity):
    """存储额外信息的传感器"""

    def __init__(self, router_api):
        self._router_api = router_api
        self._attr_name = "Router Extra Attributes"
        self._attr_unique_id = "router_extra_attributes"
        self._attributes = {}

    @property
    def state(self):
        return self._attributes.get("device_uptime", "Unknown")  # 显示设备运行时间

    @property
    def extra_state_attributes(self):
        return self._attributes

    @Throttle(SCAN_INTERVAL)
    def update(self):
        status = self._router_api.get_status()
        if status:
            self._attributes = status


class NetworkProber(SensorEntity):
    """网络连通性探测传感器"""

    def __init__(self, testurl):
        self.testurl = testurl
        self._attr_name = "Network Connectivity"
        self._attr_unique_id = "network_prober"
        self._state = 0
        self._last_probe_time = None
        self._last_probe_duration = None
        self._last_probe_error = None

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return {
            "last_probe_time": self._last_probe_time,
            "last_probe_duration": self._last_probe_duration,
            "last_probe_error": self._last_probe_error,
        }

    @Throttle(SCAN_INTERVAL)
    def update(self):
        start_time = time.time()
        self._last_probe_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            url = f"https://{self.testurl}"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            self._state = 1
            self._last_probe_error = None
        except requests.exceptions.RequestException as e:
            self._state = 0
            self._last_probe_error = str(e)

        self._last_probe_duration = round(time.time() - start_time, 2)


def setup_platform(hass, config, add_entities, discovery_info=None):
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    testurl = config.get('testurl')

    router_api = RouterAPI(username, password)

    sensors = [
        RouterBatterySensor(router_api),
        RouterBatteryTempSensor(router_api),
        RouterNetworkModeSensor(router_api),
        RouterExtraAttributesSensor(router_api),  # 额外属性传感器
        NetworkProber(testurl),
    ]

    add_entities(sensors, True)