"""Media Player class for Samsung MDC display."""

import asyncio
import logging

from samsung_mdc import MDC
from samsung_mdc.commands import INPUT_SOURCE, MUTE, POWER
from samsung_mdc.exceptions import (
    MDCError,
    MDCReadTimeoutError,
    MDCResponseError,
    NAKError,
)

from homeassistant import config_entries
from homeassistant.components.media_player import DEVICE_CLASS_TV, MediaPlayerEntity
from homeassistant.components.media_player.const import (
    SUPPORT_SELECT_SOURCE,
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_TYPE,
    CONF_UNIQUE_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DISPLAY_ID,
    DOMAIN,
    SOURCE_AV,
    SOURCE_AV2,
    SOURCE_BNC,
    SOURCE_COMPONENT,
    SOURCE_DISPLAY_PORT_1,
    SOURCE_DISPLAY_PORT_2,
    SOURCE_DISPLAY_PORT_3,
    SOURCE_DVI,
    SOURCE_DVI_VIDEO,
    SOURCE_HD_BASE_T,
    SOURCE_HDMI1,
    SOURCE_HDMI1_PC,
    SOURCE_HDMI2,
    SOURCE_HDMI2_PC,
    SOURCE_HDMI3,
    SOURCE_HDMI3_PC,
    SOURCE_HDMI4,
    SOURCE_HDMI4_PC,
    SOURCE_INTERNAL_USB,
    SOURCE_IWB,
    SOURCE_MAGIC_INFO,
    SOURCE_MEDIA_MAGIC_INFO_S,
    SOURCE_NONE,
    SOURCE_PC,
    SOURCE_PLUG_IN_MODE,
    SOURCE_RF_TV,
    SOURCE_S_VIDEO,
    SOURCE_SCART1,
    SOURCE_TV_DTV,
    SOURCE_URL_LAUNCHER,
    SOURCE_WIDI_SCREEN_MIRRORING,
)

_LOGGER = logging.getLogger(__name__)

SUPPORT_MDC = (
    SUPPORT_SELECT_SOURCE
    | SUPPORT_VOLUME_SET
    | SUPPORT_VOLUME_MUTE
    | SUPPORT_TURN_OFF
    | SUPPORT_TURN_ON
    | SUPPORT_VOLUME_STEP
)

SOURCE_MAP = {
    INPUT_SOURCE.INPUT_SOURCE_STATE.NONE: SOURCE_NONE,
    INPUT_SOURCE.INPUT_SOURCE_STATE.S_VIDEO: SOURCE_S_VIDEO,
    INPUT_SOURCE.INPUT_SOURCE_STATE.COMPONENT: SOURCE_COMPONENT,
    INPUT_SOURCE.INPUT_SOURCE_STATE.AV: SOURCE_AV,
    INPUT_SOURCE.INPUT_SOURCE_STATE.AV2: SOURCE_AV2,
    INPUT_SOURCE.INPUT_SOURCE_STATE.SCART1: SOURCE_SCART1,
    INPUT_SOURCE.INPUT_SOURCE_STATE.DVI: SOURCE_DVI,
    INPUT_SOURCE.INPUT_SOURCE_STATE.PC: SOURCE_PC,
    INPUT_SOURCE.INPUT_SOURCE_STATE.BNC: SOURCE_BNC,
    INPUT_SOURCE.INPUT_SOURCE_STATE.DVI_VIDEO: SOURCE_DVI_VIDEO,
    INPUT_SOURCE.INPUT_SOURCE_STATE.MAGIC_INFO: SOURCE_MAGIC_INFO,
    INPUT_SOURCE.INPUT_SOURCE_STATE.HDMI1: SOURCE_HDMI1,
    INPUT_SOURCE.INPUT_SOURCE_STATE.HDMI1_PC: SOURCE_HDMI1_PC,
    INPUT_SOURCE.INPUT_SOURCE_STATE.HDMI2: SOURCE_HDMI2,
    INPUT_SOURCE.INPUT_SOURCE_STATE.HDMI2_PC: SOURCE_HDMI2_PC,
    INPUT_SOURCE.INPUT_SOURCE_STATE.DISPLAY_PORT_1: SOURCE_DISPLAY_PORT_1,
    INPUT_SOURCE.INPUT_SOURCE_STATE.DISPLAY_PORT_2: SOURCE_DISPLAY_PORT_2,
    INPUT_SOURCE.INPUT_SOURCE_STATE.DISPLAY_PORT_3: SOURCE_DISPLAY_PORT_3,
    INPUT_SOURCE.INPUT_SOURCE_STATE.RF_TV: SOURCE_RF_TV,
    INPUT_SOURCE.INPUT_SOURCE_STATE.HDMI3: SOURCE_HDMI3,
    INPUT_SOURCE.INPUT_SOURCE_STATE.HDMI3_PC: SOURCE_HDMI3_PC,
    INPUT_SOURCE.INPUT_SOURCE_STATE.HDMI4: SOURCE_HDMI4,
    INPUT_SOURCE.INPUT_SOURCE_STATE.HDMI4_PC: SOURCE_HDMI4_PC,
    INPUT_SOURCE.INPUT_SOURCE_STATE.TV_DTV: SOURCE_TV_DTV,
    INPUT_SOURCE.INPUT_SOURCE_STATE.PLUG_IN_MODE: SOURCE_PLUG_IN_MODE,
    INPUT_SOURCE.INPUT_SOURCE_STATE.HD_BASE_T: SOURCE_HD_BASE_T,
    INPUT_SOURCE.INPUT_SOURCE_STATE.MEDIA_MAGIC_INFO_S: SOURCE_MEDIA_MAGIC_INFO_S,
    INPUT_SOURCE.INPUT_SOURCE_STATE.WIDI_SCREEN_MIRRORING: SOURCE_WIDI_SCREEN_MIRRORING,
    INPUT_SOURCE.INPUT_SOURCE_STATE.INTERNAL_USB: SOURCE_INTERNAL_USB,
    INPUT_SOURCE.INPUT_SOURCE_STATE.URL_LAUNCHER: SOURCE_URL_LAUNCHER,
    INPUT_SOURCE.INPUT_SOURCE_STATE.IWB: SOURCE_IWB,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Set up media player from a config entry created in the integrations UI."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    name = config[CONF_NAME]
    serial = config[CONF_UNIQUE_ID]
    model_type = config[CONF_TYPE]
    display_id = config[CONF_DISPLAY_ID]

    mdc = MDC(config[CONF_HOST])
    media_player = SamsungMDCDisplay(mdc, name, serial, model_type, display_id)

    async_add_entities([media_player], update_before_add=True)


class SamsungMDCDisplay(MediaPlayerEntity):
    """Samsung MDC screen represented as a media_player."""

    _attr_device_class = DEVICE_CLASS_TV
    _attr_icon = "mdi:television"

    def __init__(
        self, mdc: MDC, conf_name: str, serial: str, model_type: str, display_id: int
    ) -> None:
        """Initialize a new instance of SamsungMDCDisplay class."""
        super().__init__()
        self.conf_name = conf_name
        self.mdc = mdc
        self.serial = serial
        self.model_type = model_type
        self.display_id = display_id

        self._is_awaiting_power_on = False
        self._power = False
        self._volume = None
        self._muted = False
        self._input_source = None
        self._available = True
        self._sw_version = None

    @property
    def device_info(self):
        """Return device properties for MDC display."""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.conf_name,
            "manufacturer": "Samsung",
            "model": self.model_type,
            "sw_version": self._sw_version,
        }

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the display."""
        return self.serial

    @property
    def name(self):
        """Name of the entity."""
        return self.conf_name

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        if self._volume is None:
            return None
        return self._volume / 100.0

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._muted

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_MDC

    @property
    def is_on(self):
        """If the display is currently on or off."""
        return self._power

    @property
    def source_list(self):
        """List of the available input sources."""
        return list(SOURCE_MAP.values())

    @property
    def source(self):
        """Return the name of the active input source."""
        if self._input_source is None:
            return None
        return SOURCE_MAP[self._input_source]

    @property
    def state(self):
        """Return the state of the display."""
        if not self.available:
            return STATE_UNAVAILABLE

        if self._power:
            return STATE_ON
        else:
            return STATE_OFF

    @property
    def assumed_state(self) -> bool:
        """If the state is currently assumed or not."""
        if self._is_awaiting_power_on:
            return True
        return False

    async def async_update_sw_version(self):
        """Retrieve the software version of the display."""
        # Only update the SW version if the display is turned on, otherwise it will NAK
        if self._power:
            try:
                self._sw_version = await self.mdc.software_version(self.display_id)
            except NAKError:
                # Display in a state where it can not report the SW version (possibly powering on)
                pass

    async def async_update(self):
        """Update the state of the MDC display."""
        if self._is_awaiting_power_on:
            # Display is still turning on
            # Samsung describes a 15 second wait before reconnecting...
            return

        try:
            status = await self.mdc.status(self.display_id)
            await self.async_update_sw_version()
        except MDCReadTimeoutError:
            # Timeout occurred, close connection
            self.available = False
            await self.mdc.close()
            return
        except MDCResponseError as exc:
            # Some unknown value is passed to the MDC library, ignore
            # Possibly switching sources which gives undefined POWER and SOURCE state
            _LOGGER.error("Unknown status received from display", exc_info=exc)
            await self.mdc.close()
            return
        except MDCError:
            self._available = False
            _LOGGER.exception("Error retrieving status info from display")
            await self.mdc.close()
            return

        (power_state, volume_level, mute_state, input_state, _, _, _) = status

        if power_state == POWER.POWER_STATE.ON:
            self._power = True
        elif power_state == POWER.POWER_STATE.OFF:
            self._power = False
        elif power_state == POWER.POWER_STATE.REBOOT:
            self._power = False

        self._volume = volume_level

        if mute_state == MUTE.MUTE_STATE.ON:
            self._muted = True
        else:
            self._muted = False

        self._input_source = input_state

        # Update additional information
        await self.async_update_sw_version()

    async def async_execute_power(self, power):
        """Change the display power state."""
        for _ in range(3):
            try:
                await self.mdc.power(
                    self.display_id,
                    [POWER.POWER_STATE.ON if power else POWER.POWER_STATE.OFF],
                )
                # Power command ACK'd, so successful!
                return
            except NAKError:
                # For power commands, need to retry sending the command 3 times
                # every 2 seconds until ACK'd, otherwise failure
                await asyncio.sleep(2)
                continue
            except MDCResponseError:
                # Samsung displays are weird when powering on and might raise an non-issue exception in the parser,
                # Let's assume the display is now turning on and will not respond (correctly) for the following 15 seconds.
                continue
        raise MDCPowerNAKError("Power not ACK'd after 3 tries!")

    async def async_turn_on(self, **kwargs):
        """Turn the display on."""
        if not self._power:
            self._is_awaiting_power_on = True
            self._power = True
            await self.async_execute_power(True)
            await self.mdc.close()  # Force reconnect on next command
            await asyncio.sleep(15)  # Wait 15 seconds to boot, as described by Samsung
            self._is_awaiting_power_on = False

    async def async_turn_off(self, **kwargs):
        """Turn the display off."""
        return await self.async_execute_power(False)

    async def async_mute_volume(self, mute):
        """Set the mute state of the display."""
        return await self.mdc.mute(
            self.display_id,
            [MUTE.MUTE_STATE.ON if mute else MUTE.MUTE_STATE.OFF],
        )

    async def async_set_volume_level(self, volume):
        """Set the volume level of the display."""
        vol_pct = round(volume * 100)
        return await self.mdc.volume(self.display_id, [vol_pct])

    async def async_select_source(self, source):
        """Set the input source of the display."""

        position = self.source_list.index(source)
        return await self.mdc.input_source(
            self.display_id, [list(SOURCE_MAP.keys())[position]]
        )


class MDCPowerNAKError(Exception):
    """Display power command has failed exception."""

    pass
