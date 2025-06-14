import logging
import requests
import json
import hmac
import hashlib
import time
from datetime import timedelta, datetime
import voluptuous as vol

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_URL
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import Throttle

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)

# Service constants
SERVICE_SET_SIM_SLOT = "set_sim_slot"
ATTR_SLOT_ID = "slot_id"

SERVICE_SET_SIM_SLOT_SCHEMA = vol.Schema({
    vol.Required(ATTR_SLOT_ID): vol.All(cv.string, vol.In(["1", "2"])),
})

# Service constants for charge control
SERVICE_SET_CHARGE_STATE = "set_charge_state"
ATTR_CHARGE_STATE = "charge_state"

SERVICE_SET_CHARGE_STATE_SCHEMA = vol.Schema({
    vol.Required(ATTR_CHARGE_STATE): cv.boolean,
})

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up the sensor platform."""
    _LOGGER.info("router_r106: Starting async_setup_entry for sensors.")
    
    config = entry.data
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    router_url = config[CONF_URL]
    proxy_url = config.get("proxy", "")

    router_api = RouterAPI(username, password, router_url, proxy_url)

    _LOGGER.debug("router_r106: Attempting initial router login in async_setup_entry...")
    initial_login_success = await hass.async_add_executor_job(router_api.login)

    if not initial_login_success:
        _LOGGER.warning(
            "router_r106: Initial router login failed during setup. "
            "Integration will load, and sensors will attempt to connect on their first update."
        )
    else:
        _LOGGER.info("router_r106: Initial router login successful during setup.")

    device_info = {
        "identifiers": {(DOMAIN, entry.unique_id)},
        "name": entry.title,
        "manufacturer": "R106",
    }

    control_entity = RouterControlEntity(router_api, entry, device_info)

    entities_to_add = [
        RouterBatterySensor(router_api, entry, device_info),
        RouterBatteryTempSensor(router_api, entry, device_info),
        RouterNetworkSensor(router_api, entry, device_info),
        RouterExtraSensor(router_api, entry, device_info),
        RouterSimSlotSensor(router_api, entry, device_info),
        control_entity,
    ]
    
    async_add_entities(entities_to_add, True)
    _LOGGER.info("router_r106: Entities added successfully.")

    # Register services
    async def async_handle_set_sim_slot(call):
        """Handle the service call to set_sim_slot."""
        slot_id = call.data.get(ATTR_SLOT_ID)
        _LOGGER.debug(f"router_r106: async_handle_set_sim_slot called with slot_id: {slot_id}")
        await control_entity.async_set_sim_slot(slot_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SIM_SLOT,
        async_handle_set_sim_slot,
        schema=SERVICE_SET_SIM_SLOT_SCHEMA,
    )
    _LOGGER.info(f"router_r106: Service {DOMAIN}.{SERVICE_SET_SIM_SLOT} registration complete.")

    async def async_handle_set_charge_state(call):
        """Handle the service call to set_charge_state."""
        charge_state = call.data.get(ATTR_CHARGE_STATE)
        _LOGGER.debug(f"router_r106: async_handle_set_charge_state called with charge_state: {charge_state}")
        await control_entity.async_set_charge_state(charge_state)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CHARGE_STATE,
        async_handle_set_charge_state,
        schema=SERVICE_SET_CHARGE_STATE_SCHEMA,
    )
    _LOGGER.info(f"router_r106: Service {DOMAIN}.{SERVICE_SET_CHARGE_STATE} registration complete.")

    async def handle_reboot(call):
        """Handle the reboot service call."""
        _LOGGER.info("router_r106: Reboot service called")
        await hass.async_add_executor_job(control_entity.reboot_router)

    hass.services.async_register(DOMAIN, "reboot", handle_reboot)
    _LOGGER.info("router_r106: Reboot service registered.")

    return True

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

class RouterEntity(SensorEntity):
    """Base class for router entities."""
    _attr_has_entity_name = True

    def __init__(self, router_api: RouterAPI, entry: ConfigEntry, device_info: dict):
        """Initialize the entity."""
        self._router_api = router_api
        self._attr_device_info = device_info
        self._entry = entry

class RouterBatterySensor(RouterEntity):
    """电池百分比传感器"""
    _attr_name = "Battery Level"
    _attr_unit_of_measurement = "%"
    _attr_device_class = "battery"
    _attr_state_class = "measurement"

    def __init__(self, router_api, entry, device_info):
        """Initialize the sensor."""
        super().__init__(router_api, entry, device_info)
        self._attr_unique_id = f"{self._entry.unique_id}_battery_level"
        self._state = None

    @property
    def state(self):
        try:
            return float(self._state) if self._state is not None else None
        except (ValueError, TypeError):
            _LOGGER.warning(f"router_r106: Could not convert state '{self._state}' to float for {self.name}")
            return None

    @Throttle(SCAN_INTERVAL)
    def update(self):
        _LOGGER.debug(f"router_r106: Updating {self.name}")
        status = self._router_api.get_status()
        self._state = status.get("device_battery_level_percent")
        _LOGGER.debug(f"router_r106: {self.name} new state: {self._state}")

class RouterBatteryTempSensor(RouterEntity):
    """电池温度传感器"""
    _attr_name = "Battery Temperature"
    _attr_unit_of_measurement = "°C"
    _attr_device_class = "temperature"
    _attr_state_class = "measurement"

    def __init__(self, router_api, entry, device_info):
        """Initialize the sensor."""
        super().__init__(router_api, entry, device_info)
        self._attr_unique_id = f"{self._entry.unique_id}_battery_temp"
        self._state = None

    @property
    def state(self):
        try:
            return float(self._state) if self._state is not None else None
        except (ValueError, TypeError):
            _LOGGER.warning(f"router_r106: Could not convert state '{self._state}' to float for {self.name}")
            return None

    @Throttle(SCAN_INTERVAL)
    def update(self):
        _LOGGER.debug(f"router_r106: Updating {self.name}")
        status = self._router_api.get_status()
        self._state = status.get("device_battery_temperature")
        _LOGGER.debug(f"router_r106: {self.name} new state: {self._state}")

class RouterNetworkSensor(RouterEntity):
    """网络信号强度传感器"""
    _attr_name = "Network Signal Level"
    _attr_unit_of_measurement = "dB"
    _attr_device_class = "signal_strength"
    _attr_state_class = "measurement"

    def __init__(self, router_api, entry, device_info):
        """Initialize the sensor."""
        super().__init__(router_api, entry, device_info)
        self._attr_unique_id = f"{self._entry.unique_id}_signal_level"
        self._state = None

    @property
    def state(self):
        return self._state

    @Throttle(SCAN_INTERVAL)
    def update(self):
        _LOGGER.debug(f"router_r106: Updating {self.name}")
        status = self._router_api.get_status()
        self._state = status.get("mnet_sig_level")
        _LOGGER.debug(f"router_r106: {self.name} new state: {self._state}")

class RouterExtraSensor(RouterEntity):
    """额外信息传感器"""
    _attr_name = "Info"

    def __init__(self, router_api, entry, device_info):
        """Initialize the sensor."""
        super().__init__(router_api, entry, device_info)
        self._attr_unique_id = f"{self._entry.unique_id}_info"
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
        _LOGGER.debug(f"router_r106: Updating {self.name}")
        status = self._router_api.get_status()
        self._state = status.get("mnet_sysmode", "Unknown")
        self._attributes = {
            "roaming_status": status.get("mnet_roam_status"),
            "operator": status.get("mnet_operator_name"),
            "internet_mode": status.get("rt_internet_mode"),
            "dial_status": status.get("dialup_dial_status"),
            "wifi_status": status.get("wifi_work_status"),
            "unread_sms": status.get("sms_unread_count"),
            "firmware_status": status.get("fota_curr_istatus")
        }
        _LOGGER.debug(f"router_r106: {self.name} new state: {self._state}, attributes: {self._attributes}")

class RouterSimSlotSensor(RouterEntity):
    """SIM卡槽状态传感器"""
    _attr_name = "SIM Slot"
    _attr_icon = "mdi:sim"

    def __init__(self, router_api, entry, device_info):
        """Initialize the sensor."""
        super().__init__(router_api, entry, device_info)
        self._attr_unique_id = f"{self._entry.unique_id}_sim_slot"
        self._state = None
        _LOGGER.debug("router_r106: RouterSimSlotSensor initialized.")

    @property
    def state(self):
        return self._state

    @Throttle(SCAN_INTERVAL)
    def update(self):
        _LOGGER.debug(f"router_r106: Updating {self.name}")
        slot_status = self._router_api.get_mnet_sim_slot()
        self._state = slot_status
        _LOGGER.debug(f"router_r106: {self.name} new state: {self._state}")


class RouterControlEntity(RouterEntity):
    """路由器控制实体，用于处理重启等控制命令"""
    _attr_name = "Control"

    def __init__(self, router_api, entry, device_info):
        """Initialize the control entity."""
        super().__init__(router_api, entry, device_info)
        self._attr_unique_id = f"{self._entry.unique_id}_control"
        _LOGGER.debug("router_r106: RouterControlEntity initialized.")

    def reboot_router(self):
        """调用 RouterAPI 的 reboot_router 方法"""
        self._router_api.reboot_router()
        _LOGGER.info("router_r106: Reboot command sent to router.")

    async def async_set_sim_slot(self, slot_id: str):
        """Service call to set the SIM slot."""
        _LOGGER.info(f"router_r106: Service async_set_sim_slot called with slot_id: {slot_id}")
        success = await self.hass.async_add_executor_job(self._router_api.set_mnet_sim_slot, slot_id)
        if success:
            _LOGGER.info(f"router_r106: SIM slot set command to {slot_id} was successful.")
        else:
            _LOGGER.error(f"router_r106: SIM slot set command to {slot_id} failed.")

    async def async_set_charge_state(self, charge_state: bool):
        """Service call to set the charge state."""
        _LOGGER.info(f"router_r106: Service async_set_charge_state called with charge_state: {charge_state}")
        success = await self.hass.async_add_executor_job(self._router_api.set_charge_state, charge_state)
        if success:
            _LOGGER.info(f"router_r106: Charge state set command to {charge_state} was successful.")
        else:
            _LOGGER.error(f"router_r106: Charge state set command to {charge_state} failed.")

    @property
    def state(self):
        """返回实体的状态，这里可以返回一个通用的状态，例如 'Idle' 或 'Ready'"""
        return "Ready"
