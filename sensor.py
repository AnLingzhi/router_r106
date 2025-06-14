import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import Throttle
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    UnitOfTemperature,
)

from .const import DOMAIN
from .api import RouterAPI

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    router_api: RouterAPI = hass.data[DOMAIN][entry.entry_id]

    device_info = {
        "identifiers": {(DOMAIN, entry.unique_id)},
        "name": entry.title,
        "manufacturer": "R106",
    }

    entities_to_add = [
        RouterBatterySensor(router_api, entry, device_info),
        RouterBatteryTempSensor(router_api, entry, device_info),
        RouterNetworkSensor(router_api, entry, device_info),
        RouterExtraSensor(router_api, entry, device_info),
        RouterSimSlotSensor(router_api, entry, device_info),
    ]
    
    async_add_entities(entities_to_add, True)

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
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT

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
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

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
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT

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


