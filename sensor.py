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
ROUTER_R106_URL = "http://192.168.1.1"
ROUTER_JDC_URL = "http://192.168.68.1"

CONF_R106_URL = "r106_url"
CONF_JDC_URL = "jdc_url"

CONF_TESTURL = "testurl"
DEFAULT_TESTURL = "mi.com"

CONF_JDC_PASSWORD = "jdc_password"
CONF_R106_PASSWORD = "r106_password"
CONF_R106_USERNAME = "r106_username"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_TESTURL, default=DEFAULT_TESTURL): cv.string,
    vol.Optional(CONF_JDC_PASSWORD): cv.string,
    vol.Optional(CONF_R106_PASSWORD): cv.string,
    vol.Optional(CONF_R106_USERNAME): cv.string,
    vol.Optional(CONF_R106_URL, default=ROUTER_R106_URL): cv.string,
    vol.Optional(CONF_JDC_URL, default=ROUTER_JDC_URL): cv.string
})

class RouterR106API:
    """路由器 API 处理登录和数据获取"""
    def __init__(self, username, password, url=ROUTER_R106_URL):
        self._username = username
        self._password = password
        self._url = url
        self._session = requests.Session()
        self._login_status = False
	
    def hex_hmac_md5(self, key, data):
        return hmac.new(key.encode(), data.encode(), hashlib.md5).hexdigest()

    def login(self):
        """登录路由器"""
        url = f"{self._url}/goform/login"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        username_hmac = self.hex_hmac_md5("0123456789", self._username)
        password_hmac = self.hex_hmac_md5("0123456789", self._password)
        data = {"username": username_hmac, "password": password_hmac}
        
        try:
            response = self._session.post(url, headers=headers, json=data, timeout=5)
            response.raise_for_status()
            self._session.cookies = response.cookies
            self._login_status = True
            return True
        except requests.RequestException as e:
            _LOGGER.error("Router login failed: %s", e)
            self._login_status = False
            return False

    def reboot_router(self):
        url = f"{self._url}/action/reboot"
        try:
            response = self._session.post(url)
            response.raise_for_status()
            _LOGGER.info("Router rebooted successfully")
        except requests.exceptions.RequestException as e:
            _LOGGER.error("Error rebooting router: %s", e)

    def get_status(self):
        """获取路由器状态"""
        if not self._login_status:
            if not self.login():
                return {}
        url = f"{self._url}/action/get_mgdb_params"
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
            self._login_status = False
            return {}

class RouterJDCAPI:
    """路由器 API 处理登录和数据获取"""
    def __init__(self, password, url=ROUTER_JDC_URL):
        self._username = "root"
        self._password = password
        self._url = url
        self._session = requests.Session()
        self._login_status = False
        self._token = None
	
    def login(self):
        """登录路由器"""
        url = f"{self._url}/jdcapi"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        # JSON-RPC 2.0 格式请求
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [
                "00000000000000000000000000000000",
                "session",
                "login",
                {
                    "username": self._username,
                    "password": self._password,
                    "timeout": 600
                }
            ]
        }
        
        try:
            response = self._session.post(url, headers=headers, json=data, timeout=5)
            response.raise_for_status()
            response_data = response.json()
            
            # 检查响应中是否包含 token
            if ("result" in response_data and 
                isinstance(response_data["result"], list) and 
                len(response_data["result"]) > 1 and 
                isinstance(response_data["result"][1], dict) and 
                "ubus_rpc_session" in response_data["result"][1]):
                
                self._token = response_data["result"][1]["ubus_rpc_session"]
                self._login_status = True
                _LOGGER.info("JDC Router login successful, token received")
                return True
            else:
                _LOGGER.error("JDC Router login failed: Invalid response format")
                self._login_status = False
                return False
                
        except requests.RequestException as e:
            _LOGGER.error("JDC Router login failed: %s", e)
            self._login_status = False
            return False

    def reboot_router(self):
        """重启路由器"""
        if not self._login_status or not self._token:
            if not self.login():
                _LOGGER.error("Cannot reboot router: Not logged in")
                return False
                
        url = f"{self._url}/jdcapi"
        headers = {
            "Content-Type": "application/json", 
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self._url,
            "Referer": f"{self._url}/PC/main.html"
        }
        
        # JSON-RPC 2.0 格式请求，使用登录获取的 token
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [
                self._token,
                "jdcapi.static",
                "reboot",
                {}
            ]
        }
        
        try:
            response = self._session.post(url, headers=headers, json=data, timeout=5)
            response.raise_for_status()
            _LOGGER.info("JDC Router reboot command sent successfully")
            return True
        except requests.exceptions.RequestException as e:
            _LOGGER.error("Error rebooting JDC router: %s", e)
            return False

    def get_status(self):
        """获取路由器在线设备数"""
        if not self._login_status or not self._token:
            if not self.login():
                return {}
                
        url = f"{self._url}/jdcapi"
        headers = {
            "Content-Type": "application/json", 
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self._url,
            "Referer": f"{self._url}/PC/routerStatus/routerStatus.html"
        }
        
        # JSON-RPC 2.0 格式请求，使用登录获取的 token
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [
                self._token,
                "jdcapi.static",
                "web_get_online_device_count",
                {}
            ]
        }

        try:
            response = self._session.post(url, headers=headers, json=data, timeout=5)
            response.raise_for_status()
            response_data = response.json()
            
            # 检查响应中是否包含设备数量
            if ("result" in response_data and 
                isinstance(response_data["result"], list) and 
                len(response_data["result"]) > 1 and 
                isinstance(response_data["result"][1], dict)):
                
                result = response_data["result"][1]
                return {"online_device_count": result.get("count", 0)}
            else:
                _LOGGER.error("Failed to parse router status: Invalid response format")
                return {}
                
        except requests.RequestException as e:
            _LOGGER.error("Failed to fetch router status: %s", e)
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
        return self._state

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
    _attr_name = "Router Network Prober"
    _attr_unit_of_measurement = "ms"
    _attr_device_class = "connectivity"
    _attr_state_class = "measurement"

    def __init__(self, test_url):
        self._test_url = test_url if test_url.startswith("http") else f"http://{test_url}"
        self._connected = 0
        self._dalay = -1
        self._last_probe_error = None
        self._attributes = {}

    @property
    def state(self):
        return self._dalay

    @property
    def extra_state_attributes(self):
        return self._attributes

    @Throttle(SCAN_INTERVAL)
    def update(self):
        print(self._test_url)
        try:
            start_time = time.time()
            response = requests.get(self._test_url, timeout=5)
            response.raise_for_status()
            self._dalay = round((time.time() - start_time) * 1000, 2)  # 毫秒
            self._last_probe_error = None
            self._connected = 1
        except requests.RequestException as e:
            self._connected = 0
            self._dalay = -1
            self._last_probe_error = str(e)
        self._attributes = {
            "connected": self._connected,
            "last_error": self._last_probe_error,
            "last_probe": datetime.now().isoformat(),
            "test_url": self._test_url
        }

class RouterR106ControlEntity(SensorEntity): # 继承 SensorEntity 是为了方便添加到 entities 列表中，实际上它不一定是一个传感器
    """路由器控制实体，用于处理重启等控制命令"""
    _attr_name = "Router R106 Control"  # 可以自定义实体名称，例如 "Router Reboot Control"

    def __init__(self, router_api):
        """初始化控制实体"""
        self._router_api = router_api

    def reboot_router(self):
        """调用 RouterR106API 的 reboot_router 方法"""
        self._router_api.reboot_router()
        _LOGGER.info("Reboot command sent to R106 router.")

    @property
    def state(self):
        """返回实体的状态，这里可以返回一个通用的状态，例如 'Idle' 或 'Ready'"""
        return "Ready" # 或者根据实际情况返回更有意义的状态

class RouterJDCControlEntity(SensorEntity):
    """JDC路由器控制实体，用于处理重启等控制命令"""
    _attr_name = "JDC Router Control"  # 自定义实体名称

    def __init__(self, router_api):
        """初始化控制实体"""
        self._router_api = router_api

    def reboot_router(self):
        """调用 RouterJDCAPI 的 reboot_router 方法"""
        self._router_api.reboot_router()
        _LOGGER.info("Reboot command sent to JDC router.")

    @property
    def state(self):
        """返回实体的状态"""
        return "Ready"

class RouterJDCDeviceCountSensor(SensorEntity):
    """JDC路由器在线设备数传感器"""
    _attr_name = "JDC Router Online Devices"
    _attr_unit_of_measurement = "devices"
    _attr_icon = "mdi:devices"
    _attr_state_class = "measurement"

    def __init__(self, router_api):
        self._router_api = router_api
        self._state = None

    @property
    def state(self):
        return self._state

    @Throttle(SCAN_INTERVAL)
    def update(self):
        status = self._router_api.get_status()
        self._state = status.get("online_device_count")

def setup_platform(hass, config, add_entities, discovery_info=None):
    username_r106 = config.get(CONF_R106_USERNAME)
    password_r106 = config.get(CONF_R106_PASSWORD)
    url_r106 = config.get(CONF_R106_URL)
    
    password_jdc = config.get(CONF_JDC_PASSWORD)
    url_jdc = config.get(CONF_JDC_URL)

    test_url = config.get(CONF_TESTURL, DEFAULT_TESTURL)
    
    entities = []
    
    # 设置R106路由器
    if username_r106 and password_r106:
        router_r106_api = RouterR106API(username_r106, password_r106, url_r106)
        
        if router_r106_api.login():
            # 创建 RouterR106ControlEntity 实例，并传递 router_r106_api
            r106_control_entity = RouterR106ControlEntity(router_r106_api)
            
            entities.extend([
                RouterBatterySensor(router_r106_api),
                RouterBatteryTempSensor(router_r106_api),
                RouterNetworkSensor(router_r106_api),
                RouterExtraSensor(router_r106_api),
                r106_control_entity,
            ])
        else:
            _LOGGER.error("R106 Router login failed, sensors will not be created")
    
    # 设置JDC路由器
    if password_jdc:
        router_jdc_api = RouterJDCAPI(password_jdc, url_jdc)
        
        if router_jdc_api.login():
            # 创建 RouterJDCControlEntity 实例
            jdc_control_entity = RouterJDCControlEntity(router_jdc_api)
            
            entities.extend([
                RouterJDCDeviceCountSensor(router_jdc_api),
                jdc_control_entity,
            ])
        else:
            _LOGGER.error("JDC Router login failed, sensors will not be created")
    
    # 添加网络探测传感器
    entities.append(NetworkProberSensor(test_url))
    
    add_entities(entities, True)