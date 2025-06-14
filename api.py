import logging
import requests
import json
import hmac
import hashlib
import time

_LOGGER = logging.getLogger(__name__)

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

    def get_mnet_sim_slot(self):
        """获取当前活动的 SIM 卡槽"""
        _LOGGER.debug("router_r106: get_mnet_sim_slot called.")
        if not self._login_status:
            _LOGGER.debug("router_r106: Not logged in, attempting login before get_mnet_sim_slot.")
            if not self.login():
                _LOGGER.warning("router_r106: Login failed before get_mnet_sim_slot. Returning None.")
                return None
        
        url = f"{self._router_url}/action/get_mgdb_params"
        keys = [
            "esim_profile_default", "mnet_sim_slot", "esim_profile_1", "esim_profile_2",
            "esim_profile_3", "esim_profile_4", "esim_profile_5", "esim_profile_6",
            "esim_profile_7", "esim_profile_8"
        ]
        data = {"keys": keys}
        _LOGGER.debug(f"router_r106: Getting mnet_sim_slot from {url} with keys: {keys}")
        try:
            response = self._session.post(url, json=data, timeout=5)
            _LOGGER.debug(f"router_r106: get_mnet_sim_slot response status: {response.status_code}")
            response.raise_for_status()
            json_response = response.json()
            _LOGGER.debug(f"router_r106: get_mnet_sim_slot JSON response: {json_response}")
            
            if json_response.get("retcode") == 0 and "data" in json_response:
                return json_response["data"].get("mnet_sim_slot")
            else:
                _LOGGER.error(f"router_r106: get_mnet_sim_slot failed, retcode or data missing: {json_response}")
                return None
        except requests.RequestException as e:
            _LOGGER.error("router_r106: Failed to fetch mnet_sim_slot with RequestException: %s", e)
            return None
        except Exception as e_gen:
            _LOGGER.exception(f"router_r106: Unexpected error during get_mnet_sim_slot: {e_gen}")
            return None

    def set_mnet_sim_slot(self, slot_id: str):
        """设置活动的 SIM 卡槽"""
        _LOGGER.debug(f"router_r106: set_mnet_sim_slot called with slot_id: {slot_id}")
        if not self._login_status:
            _LOGGER.debug("router_r106: Not logged in, attempting login before set_mnet_sim_slot.")
            if not self.login():
                _LOGGER.error("router_r106: Login failed before set_mnet_sim_slot. Command not sent.")
                return False
        
        url = f"{self._router_url}/action/mnet_set_sim_slot"
        data = {"mnet_sim_slot": slot_id}
        _LOGGER.debug(f"router_r106: Setting SIM slot to {slot_id} at {url}")
        try:
            response = self._session.post(url, json=data, timeout=10) # Longer timeout for action
            _LOGGER.debug(f"router_r106: set_mnet_sim_slot response status: {response.status_code}")
            response.raise_for_status()
            _LOGGER.info(f"router_r106: Command to set SIM slot to {slot_id} sent successfully (HTTP {response.status_code}).")
            return True
        except requests.RequestException as e:
            _LOGGER.error("router_r106: Failed to set SIM slot with RequestException: %s", e)
            return False
        except Exception as e_gen:
            _LOGGER.exception(f"router_r106: Unexpected error during set_mnet_sim_slot: {e_gen}")
            return False

    def set_charge_state(self, charge_state: bool):
        """设置充电状态"""
        _LOGGER.debug(f"router_r106: set_charge_state called with charge_state: {charge_state}")
        
        from urllib.parse import urlparse
        parsed_router_url = urlparse(self._router_url)
        
        scheme = parsed_router_url.scheme
        hostname = parsed_router_url.hostname
        
        url = f"{scheme}://{hostname}:8080/api/set/charge/state"
        
        _LOGGER.debug(f"router_r106: Constructed charge API URL: {url}")

        headers = {
            'Accept': '*/*',
            'Accept-Language': 'zh,zh-CN;q=0.9',
            'Content-Type': 'application/json',
            'DNT': '1',
            'Proxy-Connection': 'keep-alive',
        }
        
        data = {"CHARGE_STATE": charge_state}
        _LOGGER.debug(f"router_r106: Setting charge state to {charge_state} at {url}")
        
        try:
            if not self._login_status:
                _LOGGER.debug("router_r106: Not logged in, attempting login before set_charge_state.")
                if not self.login():
                    _LOGGER.error("router_r106: Login failed before set_charge_state. Command not sent.")
                    return False
            
            _LOGGER.info(f"router_r106: Sending request to {url} via self._session with data: {data} and headers: {headers}")
            response = self._session.post(url, headers=headers, json=data, timeout=10, verify=False)

            _LOGGER.debug(f"router_r106: set_charge_state response status: {response.status_code}")
            response.raise_for_status()
            _LOGGER.info(f"router_r106: Command to set charge state to {charge_state} sent successfully.")
            return True
        except requests.RequestException as e:
            _LOGGER.error(f"router_r106: Failed to set charge state with RequestException: {e}")
            return False
        except Exception as e_gen:
            _LOGGER.exception(f"router_r106: Unexpected error during set_charge_state: {e_gen}")
            return False