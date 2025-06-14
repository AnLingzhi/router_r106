"""Switch platform for R106 Router."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .api import RouterAPI

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    router_api: RouterAPI = hass.data[DOMAIN][entry.entry_id]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id)},
        name=entry.title,
        manufacturer="R106",
    )

    async_add_entities([ChargeSwitch(router_api, entry, device_info)], True)


class ChargeSwitch(SwitchEntity):
    """A charge control switch for the R106 router."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:battery-charging"
    # We cannot read the charge state, so we use optimistic mode.
    _attr_assumed_state = True

    def __init__(
        self,
        router_api: RouterAPI,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the switch entity."""
        self._router_api = router_api
        self._attr_unique_id = f"{entry.unique_id}_charge_control"
        self._attr_device_info = device_info
        self._attr_name = "Charge Control"
        self._attr_is_on = False  # Default to off

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        _LOGGER.info("R106 Router: Enabling charging via switch.")
        success = await self.hass.async_add_executor_job(
            self._router_api.set_charge_state, True
        )
        if success:
            self._attr_is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("R106 Router: Failed to enable charging.")

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        _LOGGER.info("R106 Router: Disabling charging via switch.")
        success = await self.hass.async_add_executor_job(
            self._router_api.set_charge_state, False
        )
        if success:
            self._attr_is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("R106 Router: Failed to disable charging.")