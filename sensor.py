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
from homeassistant.helpers import selector # Added selector import
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__) # Ensure _LOGGER is defined for all subsequent uses

SCAN_INTERVAL = timedelta(minutes=1)
DOMAIN = "router_r106" # Integration domain

CONF_PROXY = "proxy" # Locally define CONF_PROXY
CONF_ROUTER_URL = CONF_URL # Reusing CONF_URL from const for router URL
# DEFAULT_PROXY = "http://172.17.13.165:7890" # No longer a hardcoded default in code logic
DEFAULT_ROUTER_URL = "http://192.168.1.1"

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
            # Assuming success if HTTP 2xx and no error code in JSON if present
            # The provided curl does not show a JSON response for this action.
            # If it did, we'd check:
            # json_response = response.json()
            # if json_response.get("retcode") == 0:
            #    _LOGGER.info(f"router_r106: Successfully set SIM slot to {slot_id}.")
            #    return True
            # else:
            #    _LOGGER.error(f"router_r106: Failed to set SIM slot, API error: {json_response}")
            #    return False
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
        
        # 从 self._router_url 解析主机名，并使用新的端口和路径
        from urllib.parse import urlparse
        parsed_router_url = urlparse(self._router_url)
        # 假设 self._router_url 是类似 "http://192.168.1.1" 或 "http://your.router.domain"
        # 新的 URL 将是 "http://<hostname_from_self._router_url>:8080/api/set/charge/state"
        # 如果 self._router_url 包含端口，需要移除它，然后添加新的端口。
        # urlparse(self._router_url).hostname 会给出纯主机名。
        
        scheme = parsed_router_url.scheme
        hostname = parsed_router_url.hostname
        # 如果原始URL中包含端口，urlparse().netloc 会是 "hostname:port"
        # 我们只需要 hostname 部分来构建新的 URL
        
        url = f"{scheme}://{hostname}:8080/api/set/charge/state"
        
        _LOGGER.debug(f"router_r106: Constructed charge API URL: {url}")

        headers = {
            'Accept': '*/*',
            'Accept-Language': 'zh,zh-CN;q=0.9',
            'Content-Type': 'application/json',
            'DNT': '1', # 根据 curl 命令
            'Proxy-Connection': 'keep-alive', # 根据 curl 命令
        }
        # 如果需要 session cookies，需要确保它们已设置或在此处传递
        # 对于这个特定的API，它可能不需要之前登录的cookies，因为它是一个不同的域和端口
        
        data = {"CHARGE_STATE": charge_state}
        _LOGGER.debug(f"router_r106: Setting charge state to {charge_state} at {url}")
        
        # 使用一个新的 requests session 或全局的 requests，因为代理和认证可能不同
        # 这里我们暂时不使用 self._session，除非确认需要共享 cookies 或代理设置
        try:
            # response = requests.post(url, headers=headers, json=data, timeout=10, verify=False) # verify=False for --insecure
            # 为了与现有代码风格保持一致，并且如果这个API也需要通过代理，我们还是用 self._session
            # 但要注意，这个API的URL是 http://route.tesla.alz:8080，与路由器的 self._router_url 不同
            # 如果这个API不需要代理，或者需要不同的代理，那么应该使用独立的 requests.post
            # 假设这个API也可能需要通过配置的代理 (虽然curl命令中没有体现)
            # 如果确定不需要代理，或者代理会干扰，应该用 requests.post(...)
            
            # 修正：由于URL和潜在的认证机制不同，使用独立的requests调用更安全
            # 并且，用户提供的 curl 有 --insecure，意味着 SSL 验证应被禁用 (如果URL是HTTPS)
            # 当前URL是HTTP，所以 verify=False 不是严格必需的，但加上无害。
            
            # 重新评估：如果这个API是路由器本身提供的另一个端点，只是端口不同，
            # 那么使用 self._session 可能是合适的，特别是如果它依赖于登录会话。
            # 但 "route.tesla.alz" 看起来不像一个标准路由器地址。
            # 假设它是一个独立的API，不需要共享session的cookies或特定代理。
            
            # 使用 requests.post 直接调用，不依赖 self._session，因为目标主机和端口不同
            # 并且用户提供的 curl 中没有认证信息，暗示可能不需要登录 session
            # 如果代理适用于所有出站请求，则需要考虑。但这里我们先直接请求。
            
            # 最终决定：为了简单起见，并遵循用户提供的 curl，我们将直接使用 requests.post
            # 不使用 self._session，因为目标服务不同。
            # 如果需要代理，用户必须确保其系统级代理或Python环境配置正确，
            # 或者我们在配置中为此特定API提供单独的代理设置。
            # 目前，我们不从 self._session.proxies 应用代理。
            # 更正：根据用户反馈，需要使用 self._session 以便应用代理和可能的共享 cookies

            if not self._login_status: # 检查登录状态，如果这个API也需要登录的话
                _LOGGER.debug("router_r106: Not logged in, attempting login before set_charge_state.")
                if not self.login():
                    _LOGGER.error("router_r106: Login failed before set_charge_state. Command not sent.")
                    return False
            
            _LOGGER.info(f"router_r106: Sending request to {url} via self._session with data: {data} and headers: {headers}")
            # 使用 self._session.post 并传入 verify=False
            response = self._session.post(url, headers=headers, json=data, timeout=10, verify=False) # verify=False for --insecure

            _LOGGER.debug(f"router_r106: set_charge_state response status: {response.status_code}")
            response.raise_for_status() # 检查HTTP错误
            _LOGGER.info(f"router_r106: Command to set charge state to {charge_state} sent successfully.")
            return True
        except requests.RequestException as e:
            _LOGGER.error(f"router_r106: Failed to set charge state with RequestException: {e}")
            return False
        except Exception as e_gen:
            _LOGGER.exception(f"router_r106: Unexpected error during set_charge_state: {e_gen}")
            return False

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

class RouterSimSlotSensor(SensorEntity):
    """SIM卡槽状态传感器"""
    _attr_name = "Router SIM Slot"
    _attr_icon = "mdi:sim"

    def __init__(self, router_api):
        self._router_api = router_api
        self._state = None
        _LOGGER.debug("router_r106: RouterSimSlotSensor initialized.")

    @property
    def state(self):
        if self._state is None:
            return None
        # Consider returning just the number "1" or "2" for easier automation,
        # or a more descriptive "Slot 1" / "Slot 2" for UI.
        # For now, returning the raw value.
        return self._state
        # If you want "Slot X":
        # return f"Slot {self._state}"


    @Throttle(SCAN_INTERVAL)
    def update(self):
        _LOGGER.debug(f"router_r106: Updating {self.name if hasattr(self, 'name') else 'RouterSimSlotSensor'}")
        slot_status = self._router_api.get_mnet_sim_slot()
        self._state = slot_status
        _LOGGER.debug(f"router_r106: {self.name if hasattr(self, 'name') else 'RouterSimSlotSensor'} new state: {self._state}")


class RouterControlEntity(SensorEntity): # 继承 SensorEntity 是为了方便添加到 entities 列表中，实际上它不一定是一个传感器
    """路由器控制实体，用于处理重启等控制命令"""
    _attr_name = "Router Control"  # 可以自定义实体名称，例如 "Router Reboot Control"

    def __init__(self, router_api):
        """初始化控制实体"""
        self._router_api = router_api
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
            # Optionally, force update the SIM slot sensor
            # This assumes the sensor is registered with an entity_id like 'sensor.router_sim_slot'
            # This part is a bit more advanced and might require access to the entity registry
            # or a direct reference to the sensor entity if passed around.
            # For now, we rely on its own update interval.
        else:
            _LOGGER.error(f"router_r106: SIM slot set command to {slot_id} failed.")

    async def async_set_charge_state(self, charge_state: bool):
        """Service call to set the charge state."""
        _LOGGER.info(f"router_r106: Service async_set_charge_state called with charge_state: {charge_state}")
        # 注意：这里的 set_charge_state 是一个同步方法，在 executor 中运行
        success = await self.hass.async_add_executor_job(self._router_api.set_charge_state, charge_state)
        if success:
            _LOGGER.info(f"router_r106: Charge state set command to {charge_state} was successful.")
        else:
            _LOGGER.error(f"router_r106: Charge state set command to {charge_state} failed.")

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
        
        _LOGGER.debug("router_r106: Attempting initial router login in setup_platform...")
        initial_login_success = router_api.login() # Store login result

        if not initial_login_success:
            _LOGGER.warning(
                "router_r106: Initial router login failed during setup. "
                "Integration will load, and sensors will attempt to connect on their first update."
            )
        else:
            _LOGGER.info("router_r106: Initial router login successful during setup.")

        # Regardless of initial login, proceed to create entities.
        # The entities' update methods will handle login status and data fetching.
        _LOGGER.debug("router_r106: Proceeding to create entities.")
        
        control_entity = RouterControlEntity(router_api)

        entities_to_add = [
            RouterBatterySensor(router_api),
            RouterBatteryTempSensor(router_api),
            RouterNetworkSensor(router_api),
            RouterExtraSensor(router_api),
            RouterSimSlotSensor(router_api), # Add new SIM slot sensor
            control_entity,
        ]
        _LOGGER.debug(f"router_r106: Prepared {len(entities_to_add)} entities to add.")
        
        add_entities(entities_to_add, True) # The 'True' here is for update_before_add
        _LOGGER.info("router_r106: Entities added successfully.")

        # Register services
        async def async_handle_set_sim_slot(call):
            """Handle the service call to set_sim_slot."""
            slot_id = call.data.get(ATTR_SLOT_ID)
            _LOGGER.debug(f"router_r106: async_handle_set_sim_slot called with slot_id: {slot_id}")
            await control_entity.async_set_sim_slot(slot_id)

        # Schedule the service registration in the event loop
        hass.loop.call_soon_threadsafe(
            hass.services.async_register,
            DOMAIN,
            SERVICE_SET_SIM_SLOT,
            async_handle_set_sim_slot,
            SERVICE_SET_SIM_SLOT_SCHEMA, # Pass schema directly
        )
        _LOGGER.info(f"router_r106: Service {DOMAIN}.{SERVICE_SET_SIM_SLOT} registration scheduled.")

        # Register set_charge_state service
        async def async_handle_set_charge_state(call):
            """Handle the service call to set_charge_state."""
            charge_state = call.data.get(ATTR_CHARGE_STATE)
            _LOGGER.debug(f"router_r106: async_handle_set_charge_state called with charge_state: {charge_state}")
            # Assuming control_entity is the correct entity to handle this.
            # If charge control is independent or managed differently, adjust target.
            await control_entity.async_set_charge_state(charge_state)

        hass.loop.call_soon_threadsafe(
            hass.services.async_register,
            DOMAIN,
            SERVICE_SET_CHARGE_STATE,
            async_handle_set_charge_state,
            SERVICE_SET_CHARGE_STATE_SCHEMA,
        )
        _LOGGER.info(f"router_r106: Service {DOMAIN}.{SERVICE_SET_CHARGE_STATE} registration scheduled.")
        
        _LOGGER.info("router_r106: Setup complete.")
        return True # Explicitly return True for successful setup
    except Exception as e:
        _LOGGER.exception(f"router_r106: Exception during setup_platform: {e}")
        return False # Explicitly return False on other exceptions