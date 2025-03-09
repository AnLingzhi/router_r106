# __init__.py
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import async_get_platforms

DOMAIN = "router_r106"

async def async_setup(hass: HomeAssistant, config: dict):
    async def handle_reboot(call):
        for platform in async_get_platforms(hass, DOMAIN):
            for entity in platform.entities.values():
                if hasattr(entity, 'reboot_router'):
                    await hass.async_add_executor_job(entity.reboot_router)

    hass.services.async_register(DOMAIN, "reboot", handle_reboot)

    return True
