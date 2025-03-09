import logging
import requests
import json
import hmac
import hashlib
from datetime import timedelta, datetime
import voluptuous as vol
import time

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.entity import Entity
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

# "device_uptime" : "300",
# "device_battery_level" : "3",
# "device_battery_level_percent" : "59",
# "device_battery_charge_status" : "charging"
# "device_battery_temperature" : "42",
# "mnet_sim_status" : "ready",
# "mnet_sysmode" : "nr5g",
# "mnet_sig_level" : "great",
# "mnet_roam_status" : "off",
# "mnet_operator_name" : "中国移动",
# "rt_internet_mode" : "mobile_data",
# "rt_eth_conn_info" : "",
# "dialup_dial_status" : "connected",
# "wifi_work_status" : "open",
# "sms_unread_count" : "0",
# "fota_curr_istatus" : "no new version",


# 获取路由器状态信息
class RouterR106(Entity):
    def __init__(self, username, password):
        self._name = "R106 Status Sensor"
        self._username = username
        self._password = password
        self._session = requests.Session()
        self.device_uptime = None
        self.device_battery_level = None
        self.device_battery_level_percent = None
        self.device_battery_charge_status = None
        self.device_battery_temperature = None
        self.mnet_sim_status = None
        self.mnet_sysmode = None
        self.mnet_sig_level = None
        self.mnet_roam_status = None
        self.mnet_operator_name = None
        self.rt_internet_mode = None
        self.rt_eth_conn_info = None
        self.dialup_dial_status = None
        self.wifi_work_status = None
        self.sms_unread_count = None
        self.fota_curr_istatus = None
        self._unique_id = f"r106_status_{username}"  # 生成唯一标识符

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return float(self.device_battery_level_percent)

    @property
    def unit_of_measurement(self):
        return "%"

    @property
    def extra_state_attributes(self):
        return {
            'device_uptime': self.device_uptime,
            'device_battery_level': self.device_battery_level,
            'device_battery_level_percent': self.device_battery_level_percent,
            'device_battery_charge_status': self.device_battery_charge_status,
            'device_battery_temperature': self.device_battery_temperature,
            'mnet_sim_status': self.mnet_sim_status,
            'mnet_sysmode': self.mnet_sysmode,
            'mnet_sig_level': self.mnet_sig_level,
            'mnet_roam_status': self.mnet_roam_status,
            'mnet_operator_name': self.mnet_operator_name,
            'rt_internet_mode': self.rt_internet_mode,
            'rt_eth_conn_info': self.rt_eth_conn_info,
            'dialup_dial_status': self.dialup_dial_status,
            'wifi_work_status': self.wifi_work_status,
            'sms_unread_count': self.sms_unread_count,
            'fota_curr_istatus': self.fota_curr_istatus
        }

    def hex_hmac_md5(self, key, data):
        hmac_md5 = hmac.new(key.encode(), data.encode(), hashlib.md5)
        return hmac_md5.hexdigest()

    def login(self):
        url = "http://192.168.1.1/goform/login"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": "http://192.168.1.1/common/login.html"
        }
        username_hmac = self.hex_hmac_md5("0123456789", self._username)
        password_hmac = self.hex_hmac_md5("0123456789", self._password)
        data = {
            "username": username_hmac,
            "password": password_hmac
        }
        response = self._session.post(url, headers=headers, json=data)
        response.raise_for_status()
        self._session.cookies = response.cookies
    
    def check_battery_status(self):
        url = "http://192.168.1.1/action/get_mgdb_params"
        data = {
            "keys": [
                "device_uptime",
                "device_battery_level",
                "device_battery_level_percent",
                "device_battery_charge_status",
                "device_battery_temperature",
                "mnet_sim_status",
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
        
        response = self._session.post(url, json=data)
        response.raise_for_status()
        result = response.json()
        self.device_uptime = result["data"].get("device_uptime")
        self.device_battery_level = result["data"].get("device_battery_level")
        self.device_battery_level_percent = result["data"].get("device_battery_level_percent")
        self.device_battery_charge_status = result["data"].get("device_battery_charge_status")
        self.device_battery_temperature = result["data"].get("device_battery_temperature")
        self.mnet_sim_status = result["data"].get("mnet_sim_status")
        self.mnet_sysmode = result["data"].get("mnet_sysmode")
        self.mnet_sig_level = result["data"].get("mnet_sig_level")
        self.mnet_roam_status = result["data"].get("mnet_roam_status")
        self.mnet_operator_name = result["data"].get("mnet_operator_name")
        self.rt_internet_mode = result["data"].get("rt_internet_mode")
        self.rt_eth_conn_info = result["data"].get("rt_eth_conn_info")
        self.dialup_dial_status = result["data"].get("dialup_dial_status")
        self.wifi_work_status = result["data"].get("wifi_work_status")
        self.sms_unread_count = result["data"].get("sms_unread_count")
        self.fota_curr_istatus = result["data"].get("fota_curr_istatus")
        _LOGGER.info("Battery level: %s, Battery level percent: %s, Charge status: %s, Temperature: %s", self.device_battery_level, self.device_battery_level_percent, self.device_battery_charge_status, self.device_battery_temperature)
        _LOGGER.info("SIM status: %s, System mode: %s, Signal level: %s, Roaming status: %s, Operator name: %s, Internet mode: %s, Ethernet connection info: %s, Dialup dial status: %s, WiFi work status: %s, Unread SMS count: %s, Firmware update status: %s", self.mnet_sim_status, self.mnet_sysmode, self.mnet_sig_level, self.mnet_roam_status, self.mnet_operator_name, self.rt_internet_mode, self.rt_eth_conn_info, self.dialup_dial_status, self.wifi_work_status, self.sms_unread_count, self.fota_curr_istatus)

    def reboot_router(self):
        url = "http://192.168.1.1/action/reboot"
        try:
            response = self._session.post(url)
            response.raise_for_status()
            _LOGGER.info("Router rebooted successfully")
        except requests.exceptions.RequestException as e:
            _LOGGER.error("Error rebooting router: %s", e)

    @Throttle(SCAN_INTERVAL)
    def update(self):
        self.login()  # 每次更新时都进行登录
        self.check_battery_status()

class NetworkProber(Entity):
    def __init__(self, testurl):
        self._name = "R106 Network Prober"
        self.testurl = testurl
        self._session = requests.Session()
        self._status = None
        self._last_probe_time = None
        self._last_probe_duration = None
        self._last_probe_result = 0
        self._last_probe_error = None
        self._last_successful_probe_time = None
        self._last_failed_probe_time = None
        self._unique_id = f"r106_network_{testurl}"  # 生成唯一标识符

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name
    
    @property
    def state(self):
        return self._last_probe_result
    
    @property
    def extra_state_attributes(self):
        return {
            "last_probe_time": self._last_probe_time,
            "last_probe_result": self._last_probe_result,
            "last_probe_duration": self._last_probe_duration,
            "last_probe_error": self._last_probe_error,
            "last_successful_probe_time": self._last_successful_probe_time,
            "last_failed_probe_time": self._last_failed_probe_time,
        }

    def probe(self):
        start_time = time.time()
        self._last_probe_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            # 添加https头
            url = f"https://{self.testurl}"
            response = self._session.get(url, timeout=5)
            response.raise_for_status()
            self._last_probe_result = 1
            self._last_probe_error = None
            self._last_successful_probe_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except requests.exceptions.RequestException as e:
            self._last_probe_result = 0
            self._last_probe_error = str(e)
            self._last_failed_probe_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _LOGGER.error("Error probing network: %s", e)
        self._last_probe_duration = time.time() - start_time
        return self._last_probe_result   
    
    @Throttle(SCAN_INTERVAL)
    def update(self):
        self.probe()
def setup_platform(hass, config, add_entities, discovery_info=None):
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    router = RouterR106(username, password)
    
    testurl = config.get('testurl')
    networkprober = NetworkProber(testurl)
    
    add_entities([router, networkprober], True)
