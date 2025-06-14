"""The R106 Router integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_URL
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .api import RouterAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button", "select", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up R106 Router from a config entry."""
    _LOGGER.info("Setting up R106 Router for %s", entry.title)
    
    hass.data.setdefault(DOMAIN, {})
    
    # Create API instance
    router_api = RouterAPI(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        router_url=entry.data[CONF_URL],
        proxy_url=entry.data.get("proxy"),
    )
    
    # Store API instance for platforms to access
    hass.data[DOMAIN][entry.entry_id] = router_api

    # Forward the setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading R106 Router for %s", entry.title)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_forward_entry_unloads(entry, PLATFORMS)

    # Remove API instance
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
