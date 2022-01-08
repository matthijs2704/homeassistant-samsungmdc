"""Config flow for Samsung MDC."""
import ipaddress
from typing import Tuple

from samsung_mdc import MDC
from samsung_mdc.exceptions import MDCTimeoutError

import voluptuous as vol
from voluptuous.schema_builder import message
from voluptuous.error import Invalid

from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME, CONF_TYPE, CONF_UNIQUE_ID

from .const import CONF_DISPLAY_ID, DEFAULT_DISPLAY_ID, DEFAULT_NAME, DOMAIN, RESULT_CANNOT_CONNECT, RESULT_INV_DSPID, RESULT_INV_IP

async def test_connection(host: str, display_id: int) -> Tuple[str, str]:
    """Test the connection to a display and receive its serial."""
    async with MDC(host, verbose=False) as mdc:
        (serial_number,) = await mdc.serial_number(display_id)
        (model,) = await mdc.model_name(display_id)
        return (serial_number, model)

def is_valid_ip(ip: str):
    """Return True if IP address is valid."""
    try:
        if ipaddress.ip_address(ip).version == (4 or 6):
            return True
    except ValueError:
        return False

class SamsungMDCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Samsung MDC display entities."""

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(self, user_input):
        """Present form for user input for entering connection details."""
        self._errors = {}
        if user_input is not None:
            data_valid = True
            if not is_valid_ip(user_input[CONF_IP_ADDRESS]):
                self._errors["base"] = RESULT_INV_IP
                data_valid = False

            if not 0 <= user_input[CONF_DISPLAY_ID] <= 0xFF:
                self._errors["base"] = RESULT_INV_DSPID
                data_valid = False

            if data_valid:
                display_ip = user_input[CONF_IP_ADDRESS]
                display_id = user_input[CONF_DISPLAY_ID]
                try:
                    (serial, model_type) = await test_connection(display_ip, display_id)
                    await self.async_set_unique_id(serial)
                    self._abort_if_unique_id_configured(
                        updates={
                            CONF_IP_ADDRESS: display_ip,
                            CONF_DISPLAY_ID: display_id,
                        }
                    )

                    return self.async_create_entry(
                        title=user_input["name"],
                        data={
                            CONF_NAME: user_input[CONF_NAME],
                            CONF_IP_ADDRESS: display_ip,
                            CONF_DISPLAY_ID: display_id,
                            CONF_UNIQUE_ID: serial,
                            CONF_TYPE: model_type,
                        },
                    )
                except (MDCTimeoutError, ConnectionRefusedError, OSError) as exc:
                    self._errors["base"] = RESULT_CANNOT_CONNECT                

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_IP_ADDRESS): str,
                vol.Optional(CONF_DISPLAY_ID, default=DEFAULT_DISPLAY_ID): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=self._errors)