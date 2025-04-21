# __init__.py
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import async_get_platforms

DOMAIN = "router_r106"

async def async_setup(hass: HomeAssistant, config: dict):
    async def handle_reboot(call):
        entity_id = call.data.get('entity_id')
        
        # 如果指定了entity_id，只重启指定的路由器
        if entity_id:
            for platform in async_get_platforms(hass, DOMAIN):
                for entity_obj in platform.entities.values():
                    if entity_obj.entity_id == entity_id and hasattr(entity_obj, 'reboot_router'):
                        await hass.async_add_executor_job(entity_obj.reboot_router)
                        return
        # 如果没有指定entity_id，重启所有路由器
        else:
            for platform in async_get_platforms(hass, DOMAIN):
                for entity_obj in platform.entities.values():
                    if hasattr(entity_obj, 'reboot_router'):
                        await hass.async_add_executor_job(entity_obj.reboot_router)

    hass.services.async_register(DOMAIN, "reboot", handle_reboot)

    return True
