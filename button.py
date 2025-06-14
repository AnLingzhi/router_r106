"""Button platform for R106 Router."""
import logging

from homeassistant.components.button import ButtonEntity
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
    """Set up the button platform."""
    router_api: RouterAPI = hass.data[DOMAIN][entry.entry_id]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id)},
        name=entry.title,
        manufacturer="R106",
    )

    async_add_entities([RebootButton(router_api, entry, device_info)], True)


class RebootButton(ButtonEntity):
    """A reboot button for the R106 router."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:restart"

    def __init__(
        self,
        router_api: RouterAPI,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the reboot button."""
        self._router_api = router_api
        self._attr_unique_id = f"{entry.unique_id}_reboot"
        self._attr_device_info = device_info
        self._attr_name = "Reboot"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("R106 Router reboot initiated by button press.")
        await self.hass.async_add_executor_job(self._router_api.reboot_router)