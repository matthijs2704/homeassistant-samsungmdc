"""Config flow for Samsung MDC."""

import ipaddress
from typing import Tuple
import logging

from samsung_mdc import MDC
from samsung_mdc.exceptions import MDCTimeoutError

import voluptuous as vol
from voluptuous.schema_builder import message
from voluptuous.error import Invalid

from homeassistant import config_entries, exceptions
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_NAME,
    CONF_TYPE,
    CONF_UNIQUE_ID,
    CONF_MODEL,
)

from .const import (
    CONF_DISPLAY_ID,
    DEFAULT_DISPLAY_ID,
    DEFAULT_NAME,
    DOMAIN,
    RESULT_CANNOT_CONNECT,
    RESULT_INV_DSPID,
    RESULT_INV_IP,
)
from .mdc_api import MdcApi

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): str,
        vol.Optional(CONF_DISPLAY_ID, default=DEFAULT_DISPLAY_ID): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Optional(CONF_NAME): str,
    }
)


def is_valid_ip(host: str):
    """Return True if IP address is valid."""
    try:
        if ipaddress.ip_address(host).version == (4 or 6):
            return True
    except ValueError:
        # Could be a hostname
        return len(host) > 0 and not host.isspace()


class SamsungMDCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Samsung MDC display entities."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(self, user_input):
        """Present form for user input for entering connection details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_IP_ADDRESS]
            display_id = user_input[CONF_DISPLAY_ID]
            name = user_input.get(CONF_NAME, f"Samsung MDC ({host} #{display_id})")

            # Validate input
            if not is_valid_ip(host):
                errors["base"] = RESULT_INV_IP
            elif not (0 <= display_id <= 255):
                errors["base"] = RESULT_INV_DSPID
            else:
                # Test connection
                api = MdcApi(host, display_id)
                try:
                    await api.async_connect()

                    model = await api.async_command(fn="model_name")
                    if not model or model == "Unknown":
                        errors["base"] = RESULT_CANNOT_CONNECT
                        await api.async_close()
                        return self.async_show_form(
                            step_id="user",
                            data_schema=SCHEMA,
                            errors=errors,
                        )

                    # Create unique ID based on host and display ID
                    unique_id = f"{host}_{display_id}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_IP_ADDRESS: host,
                            CONF_DISPLAY_ID: display_id,
                            CONF_NAME: name,
                            CONF_MODEL: model,
                            CONF_TYPE: "MDC",
                            CONF_UNIQUE_ID: unique_id,
                        },
                    )
                except Exception as ex:
                    _LOGGER.error("Cannot connect to Samsung MDC display: %s", ex)
                    errors["base"] = RESULT_CANNOT_CONNECT
                    raise
                finally:
                    await api.async_close()

        return self.async_show_form(
            step_id="user",
            data_schema=SCHEMA,
            errors=errors,
        )
