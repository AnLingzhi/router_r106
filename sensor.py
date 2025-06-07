import logging
import requests
import json
import hmac
import hashlib
import time
from datetime import timedelta, datetime
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_URL # Removed CONF_PROXY
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__) # Ensure _LOGGER is defined for all subsequent uses

SCAN_INTERVAL = timedelta(minutes=1)

CONF_PROXY = "proxy" # Locally define CONF_PROXY
CONF_ROUTER_URL = CONF_URL # Reusing CONF_URL from const for router URL
# DEFAULT_PROXY = "http://172.17.13.165:7890" # No longer a hardcoded default in code logic
DEFAULT_ROUTER_URL = "http://192.168.1.1"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_PROXY, default=""): cv.string, # Default to empty string, meaning no proxy if not set
    vol.Optional(CONF_ROUTER_URL, default=DEFAULT_ROUTER_URL): cv.string,
})

class RouterAPI:
    """路由器 API 处理登录和数据获取"""
    def __init__(self, username, password, router_url, proxy_url=None):
        self._username = username
        self._password = password
        self._router_url = router_url
        self._session = requests.Session()
        if proxy_url:
            self._session.proxies = {"http": proxy_url, "https": proxy_url}
        self._login_status = False
	
    def hex_hmac_md5(self, key, data):
        return hmac.new(key.encode(), data.encode(), hashlib.md5).hexdigest()

    def login(self):
        """登录路由器"""
        url = f"{self._router_url}/goform/login"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        username_hmac = self.hex_hmac_md5("0123456789", self._username)
        password_hmac = self.hex_hmac_md5("0123456789", self._password)
        data = {"username": username_hmac, "password": password_hmac}
        
        _LOGGER.debug(f"router_r106: Attempting login to {url}")
        try:
            response = self._session.post(url, headers=headers, json=data, timeout=5)
            _LOGGER.debug(f"router_r106: Login response status: {response.status_code}")
            response.raise_for_status() # This will raise for 4xx/5xx errors
            self._session.cookies = response.cookies
            self._login_status = True
            _LOGGER.debug("router_r106: Login successful, cookies set.")
            return True
        except requests.RequestException as e:
            _LOGGER.error("router_r106: Router login failed with RequestException: %s", e)
            self._login_status = False
            return False
        except Exception as e_gen:
            _LOGGER.exception(f"router_r106: Unexpected error during login: {e_gen}")
            self._login_status = False
            return False

    def reboot_router(self):
        url = f"{self._router_url}/action/reboot"
        try:
            response = self._session.post(url)
            response.raise_for_status()
            _LOGGER.info("Router rebooted successfully")
        except requests.exceptions.RequestException as e:
            _LOGGER.error("Error rebooting router: %s", e)

    def get_status(self):
        """获取路由器状态"""
        _LOGGER.debug("router_r106: get_status called.")
        if not self._login_status:
            _LOGGER.debug("router_r106: Not logged in, attempting login before get_status.")
            if not self.login():
                _LOGGER.warning("router_r106: Login failed before get_status. Returning empty status.")
                return {}
        
        url = f"{self._router_url}/action/get_mgdb_params"
        data = {
            "keys": [
                "device_battery_level_percent", "device_battery_temperature",
                "mnet_sysmode", "mnet_sig_level", "mnet_roam_status",
                "mnet_operator_name", "rt_internet_mode", "dialup_dial_status",
                "wifi_work_status", "sms_unread_count", "fota_curr_istatus"
            ]
        }
        _LOGGER.debug(f"router_r106: Getting status from {url}")
        try:
            response = self._session.post(url, json=data, timeout=5)
            _LOGGER.debug(f"router_r106: Get_status response status: {response.status_code}")
            response.raise_for_status()
            json_response = response.json()
            _LOGGER.debug(f"router_r106: Get_status JSON response: {json_response}")
            return json_response.get("data", {})
        except requests.RequestException as e:
            _LOGGER.error("router_r106: Failed to fetch router status with RequestException: %s", e)
            self._login_status = False
            return {}
        except Exception as e_gen:
            _LOGGER.exception(f"router_r106: Unexpected error during get_status: {e_gen}")
            self._login_status = False
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
        try:
            return float(self._state) if self._state is not None else None
        except (ValueError, TypeError):
            _LOGGER.warning(f"router_r106: Could not convert state '{self._state}' to float for {self.name if hasattr(self, 'name') else 'RouterBatterySensor'}")
            return None

    @Throttle(SCAN_INTERVAL)
    def update(self):
        _LOGGER.debug(f"router_r106: Updating {self.name if hasattr(self, 'name') else 'RouterBatterySensor'}")
        status = self._router_api.get_status()
        self._state = status.get("device_battery_level_percent")
        _LOGGER.debug(f"router_r106: {self.name if hasattr(self, 'name') else 'RouterBatterySensor'} new state: {self._state}")

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
        try:
            return float(self._state) if self._state is not None else None
        except (ValueError, TypeError):
            _LOGGER.warning(f"router_r106: Could not convert state '{self._state}' to float for {self.name if hasattr(self, 'name') else 'RouterBatteryTempSensor'}")
            return None

    @Throttle(SCAN_INTERVAL)
    def update(self):
        _LOGGER.debug(f"router_r106: Updating {self.name if hasattr(self, 'name') else 'RouterBatteryTempSensor'}")
        status = self._router_api.get_status()
        self._state = status.get("device_battery_temperature")
        _LOGGER.debug(f"router_r106: {self.name if hasattr(self, 'name') else 'RouterBatteryTempSensor'} new state: {self._state}")

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
        # Assuming mnet_sig_level might be a string or number, no float conversion needed unless specified
        return self._state

    @Throttle(SCAN_INTERVAL)
    def update(self):
        _LOGGER.debug(f"router_r106: Updating {self.name if hasattr(self, 'name') else 'RouterNetworkSensor'}")
        status = self._router_api.get_status()
        self._state = status.get("mnet_sig_level")
        _LOGGER.debug(f"router_r106: {self.name if hasattr(self, 'name') else 'RouterNetworkSensor'} new state: {self._state}")

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
        _LOGGER.debug(f"router_r106: Updating {self.name if hasattr(self, 'name') else 'RouterExtraSensor'}")
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
        _LOGGER.debug(f"router_r106: {self.name if hasattr(self, 'name') else 'RouterExtraSensor'} new state: {self._state}, attributes: {self._attributes}")


class RouterControlEntity(SensorEntity): # 继承 SensorEntity 是为了方便添加到 entities 列表中，实际上它不一定是一个传感器
    """路由器控制实体，用于处理重启等控制命令"""
    _attr_name = "Router Control"  # 可以自定义实体名称，例如 "Router Reboot Control"

    def __init__(self, router_api):
        """初始化控制实体"""
        self._router_api = router_api

    def reboot_router(self):
        """调用 RouterAPI 的 reboot_router 方法"""
        self._router_api.reboot_router()
        # 可以添加一些日志或状态更新，例如：
        _LOGGER.info("Reboot command sent to router.")
        # 如果需要，可以更新实体的状态来反映操作结果 (例如，设置一个 last_reboot_time 属性)

    @property
    def state(self):
        """返回实体的状态，这里可以返回一个通用的状态，例如 'Idle' 或 'Ready'"""
        return "Ready" # 或者根据实际情况返回更有意义的状态



def setup_platform(hass, config, add_entities, discovery_info=None):
    _LOGGER.info("router_r106: Starting setup_platform.")
    try:
        username = config[CONF_USERNAME]
        password = config[CONF_PASSWORD]
        proxy_url = config.get(CONF_PROXY)
        router_url = config[CONF_ROUTER_URL]
        
        _LOGGER.debug(f"router_r106: Config - Username={username}, Router URL={router_url}, Proxy URL='{proxy_url}'")

        router_api = RouterAPI(username, password, router_url, proxy_url)
        
        _LOGGER.debug("router_r106: Attempting router login in setup_platform...")
        if not router_api.login():
            _LOGGER.error("router_r106: Router login failed during setup. Sensors will not be created.")
            return False # Explicitly return False on login failure

        _LOGGER.debug("router_r106: Router login successful in setup_platform. Creating entities.")
        
        control_entity = RouterControlEntity(router_api)

        entities_to_add = [
            RouterBatterySensor(router_api),
            RouterBatteryTempSensor(router_api),
            RouterNetworkSensor(router_api),
            RouterExtraSensor(router_api),
            control_entity,
        ]
        _LOGGER.debug(f"router_r106: Prepared {len(entities_to_add)} entities to add.")
        
        add_entities(entities_to_add, True) # The 'True' here is for update_before_add
        _LOGGER.info("router_r106: Entities added successfully. Setup complete.")
        return True # Explicitly return True for successful setup
    except Exception as e:
        _LOGGER.exception(f"router_r106: Exception during setup_platform: {e}")
        return False # Explicitly return False on other exceptions