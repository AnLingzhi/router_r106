"""Config flow for R106 Router."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_URL
from homeassistant.core import callback

from .const import DOMAIN
from .api import RouterAPI

_LOGGER = logging.getLogger(__name__)

class R106ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for R106 Router."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                router_api = RouterAPI(
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    router_url=user_input[CONF_URL],
                    proxy_url=user_input.get("proxy"),
                )
                # Test the connection
                login_success = await self.hass.async_add_executor_job(router_api.login)

                if login_success:
                    await self.async_set_unique_id(user_input[CONF_URL])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title="R106 Router", data=user_input)
                else:
                    errors["base"] = "cannot_connect"

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_URL, default="http://192.168.1.1"): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional("proxy"): str,
            }),
            errors=errors,
        )