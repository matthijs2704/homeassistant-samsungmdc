"""Config flow for Samsung MDC."""
import ipaddress

from samsung_mdc import MDC
import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_TYPE, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_flow

from .const import CONF_DISPLAY_ID, DEFAULT_DISPLAY_ID, DEFAULT_NAME, DOMAIN


async def _async_has_devices(hass: HomeAssistant) -> bool:
    """Return if there are devices that can be discovered."""
    # TODO Check if there are any devices that can be discovered in the network.
    # devices = await hass.async_add_executor_job(my_pypi_dependency.discover)
    # return len(devices) > 0
    return False


config_entry_flow.register_discovery_flow(DOMAIN, "Samsung MDC", _async_has_devices)


@callback
def samsung_mdc_entries(hass: HomeAssistant):
    """Return the hosts already configured."""
    return {
        entry.data[CONF_HOST] for entry in hass.config_entries.async_entries(DOMAIN)
    }


def host_valid(host: str):
    """Return True if hostname or IP address is valid."""
    try:
        if ipaddress.ip_address(host).version == (4 or 6):
            return True
    except ValueError:
        return False


def is_valid(info):
    """Check if the entered information is valid connection info."""
    is_host_valid = host_valid(info[CONF_HOST])

    if not is_host_valid:
        raise InvalidHost

    if not 0 <= info[CONF_DISPLAY_ID] <= 0xFF:
        raise InvalidDisplayID

    return True


async def test_connection(info: dict):
    """Test the connection to a display and receive its serial."""
    async with MDC(info[CONF_HOST], verbose=True) as mdc:
        (serial_number,) = await mdc.serial_number(info[CONF_DISPLAY_ID])
        (model,) = await mdc.model_name(info[CONF_DISPLAY_ID])
        return (serial_number, model)


class SamsungMDCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Samsung MDC display entities."""

    def _host_in_configuration_exists(self, host) -> bool:
        """Return True if host exists in configuration."""
        if host in samsung_mdc_entries(self.hass):
            return True
        return False

    async def async_step_user(self, user_input):
        """Present form for user input for entering connection details."""
        if user_input is not None:
            valid = is_valid(user_input)
            if valid:
                (serial, model_type) = await test_connection(user_input)

                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_DISPLAY_ID: user_input[CONF_DISPLAY_ID],
                    }
                )

                return self.async_create_entry(
                    title=user_input["name"],
                    data={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_DISPLAY_ID: user_input[CONF_DISPLAY_ID],
                        CONF_UNIQUE_ID: serial,
                        CONF_TYPE: model_type,
                    },
                )
            pass

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_DISPLAY_ID, default=DEFAULT_DISPLAY_ID): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema)


class InvalidDisplayID(exceptions.HomeAssistantError):
    """Error to indicate an invalid display ID is entered."""


class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""
