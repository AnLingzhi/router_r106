"""Select platform for R106 Router."""
import logging
from datetime import timedelta

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import Throttle

from .const import DOMAIN
from .api import RouterAPI

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    router_api: RouterAPI = hass.data[DOMAIN][entry.entry_id]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id)},
        name=entry.title,
        manufacturer="R106",
    )

    async_add_entities([SimSlotSelect(router_api, entry, device_info)], True)


class SimSlotSelect(SelectEntity):
    """A SIM slot selector for the R106 router."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:sim"
    _attr_options = ["1", "2"]

    def __init__(
        self,
        router_api: RouterAPI,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the select entity."""
        self._router_api = router_api
        self._attr_unique_id = f"{entry.unique_id}_sim_slot_selector"
        self._attr_device_info = device_info
        self._attr_name = "SIM Slot"
        self._attr_current_option = None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.info(f"R106 Router: Setting SIM slot to {option}")
        success = await self.hass.async_add_executor_job(
            self._router_api.set_mnet_sim_slot, option
        )
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()
        else:
            _LOGGER.error(f"R106 Router: Failed to set SIM slot to {option}")

    @Throttle(SCAN_INTERVAL)
    def update(self) -> None:
        """Fetch new state data for the select entity."""
        _LOGGER.debug("R106 Router: Updating SIM slot selection")
        self._attr_current_option = self._router_api.get_mnet_sim_slot()
        _LOGGER.debug(f"R106 Router: Current SIM slot is {self._attr_current_option}")