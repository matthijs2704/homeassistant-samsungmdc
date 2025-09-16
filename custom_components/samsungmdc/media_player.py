"""Media Player class for Samsung MDC display."""

import asyncio
import logging

from samsung_mdc import MDC
from samsung_mdc.commands import INPUT_SOURCE, MUTE, POWER
from samsung_mdc.exceptions import (
    MDCTimeoutError,
    MDCResponseError,
    NAKError,
)

from homeassistant import config_entries
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerDeviceClass,
)
from homeassistant.components.media_player.const import (
    MediaPlayerEntityFeature,
)
from homeassistant.const import (
    CONF_IP_ADDRESS,
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

# Connection retry settings
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 2
POWER_ON_WAIT_TIME = 15

SUPPORT_MDC = (
    MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.VOLUME_STEP
)

# Map the input sources of the MDC protocol to names for Home Assistant
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

    mdc = MDC(config[CONF_IP_ADDRESS])
    media_player = SamsungMDCDisplay(mdc, name, serial, model_type, display_id)

    async_add_entities([media_player], update_before_add=True)


class SamsungMDCDisplay(MediaPlayerEntity):
    """Samsung MDC screen represented as a media_player."""

    _attr_device_class = MediaPlayerDeviceClass.TV
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

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    async def async_update_sw_version(self):
        """Retrieve the software version of the display."""
        # Only update the SW version if the display is turned on, otherwise it will NAK
        if self._power:
            try:
                self._sw_version = await self.mdc.software_version(self.display_id)
            except NAKError:
                # Display in a state where it can not report the SW version (possibly powering on)
                pass
            except (
                ConnectionResetError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                OSError,
                MDCTimeoutError
            ) as e:
                _LOGGER.debug("Connection error getting SW version: %s", str(e))
                # Don't mark as unavailable for SW version errors, it's not critical
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
        except ValueError:
            # Some unknown value is passed to the MDC library, ignore
            # Possibly switching sources which gives undefined POWER and SOURCE state
            return
        except MDCResponseError:
            _LOGGER.warning("MDC response parsing error. Resetting connection.")
            await self.mdc.close()
            return
        except NAKError:
            _LOGGER.error("Received NAK from display for status command")
            self._available = False
            await self.mdc.close()
            return
        except (
            MDCTimeoutError,
            ConnectionAbortedError,
            ConnectionRefusedError,
            ConnectionResetError,
            OSError
        ) as e:
            error_type = type(e).__name__
            await self._handle_connection_error(f"Connection error during status update: {error_type}: {str(e)}")
            return

        # We have received status data, so that must mean we are online!
        self._available = True

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

    async def _handle_connection_error(self, error_msg: str):
        """Handle connection errors by marking device unavailable and closing connection."""
        _LOGGER.error("%s", error_msg)
        self._available = False
        try:
            await self.mdc.close()
        except Exception as e:
            _LOGGER.debug("Error closing MDC connection: %s", e)

    async def _execute_with_retry(self, command_func, *args, **kwargs):
        """Execute an MDC command with retry logic for connection errors."""
        last_exception = None

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                return await command_func(*args, **kwargs)
            except (
                ConnectionResetError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                OSError,
                MDCTimeoutError
            ) as e:
                last_exception = e
                error_type = type(e).__name__
                _LOGGER.warning(
                    "Connection error (%s) on attempt %d/%d: %s",
                    error_type, attempt + 1, MAX_RETRY_ATTEMPTS, str(e)
                )

                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    # Close connection and wait before retry
                    try:
                        await self.mdc.close()
                    except Exception:
                        pass
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                else:
                    # Final attempt failed
                    await self._handle_connection_error(
                        f"Failed to execute command after {MAX_RETRY_ATTEMPTS} attempts. Last error: {error_type}: {str(e)}"
                    )
                    raise
            except (NAKError, MDCResponseError, ValueError) as e:
                # These are protocol-level errors that shouldn't be retried
                raise

        # This should never be reached, but just in case
        if last_exception:
            raise last_exception

    async def async_execute_power(self, power):
        """Change the display power state."""
        power_state = POWER.POWER_STATE.ON if power else POWER.POWER_STATE.OFF

        for i in range(MAX_RETRY_ATTEMPTS):
            try:
                await self.mdc.power(self.display_id, [power_state])
                # Power command ACK'd, so successful!
                return
            except NAKError:
                # For power commands, need to retry sending the command 3 times
                # every 2 seconds until ACK'd, otherwise failure
                _LOGGER.info("MDC power command has not been ACK'd after try %d/%d", i + 1, MAX_RETRY_ATTEMPTS)
                if i < MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except MDCResponseError:
                # Samsung displays are weird when powering on and might raise an non-issue exception in the parser,
                # Let's assume the display is now turning on and will not respond (correctly) for the following 15 seconds.
                return
            except (
                ConnectionResetError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                OSError,
                MDCTimeoutError
            ) as e:
                error_type = type(e).__name__
                _LOGGER.warning("Connection error during power command attempt %d/%d: %s: %s",
                              i + 1, MAX_RETRY_ATTEMPTS, error_type, str(e))
                if i < MAX_RETRY_ATTEMPTS - 1:
                    try:
                        await self.mdc.close()
                    except Exception:
                        pass
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                else:
                    await self._handle_connection_error(f"Power command failed after {MAX_RETRY_ATTEMPTS} attempts")
                    return

        # If the power command is not ACK'd after 3 tries, it should be considered a failure.
        # We'll set the display offline and retry with a fresh connection next time.
        _LOGGER.error("MDC power command has not been ACK'd after %d tries!", MAX_RETRY_ATTEMPTS)
        self._available = False
        try:
            await self.mdc.close()
        except Exception:
            pass

    async def async_turn_on(self, **kwargs):
        """Turn the display on."""
        if not self._power:
            self._is_awaiting_power_on = True
            self._power = True
            await self.async_execute_power(True)
            await self.mdc.close()  # Force reconnect on next command
            await asyncio.sleep(POWER_ON_WAIT_TIME)  # Wait 15 seconds to boot, as described by Samsung
            self._is_awaiting_power_on = False

    async def async_turn_off(self, **kwargs):
        """Turn the display off."""
        return await self.async_execute_power(False)

    async def async_mute_volume(self, mute):
        """Set the mute state of the display."""
        try:
            return await self._execute_with_retry(
                self.mdc.mute,
                self.display_id,
                [MUTE.MUTE_STATE.ON if mute else MUTE.MUTE_STATE.OFF],
            )
        except Exception as e:
            _LOGGER.error("Failed to set mute state: %s", str(e))
            raise

    async def async_set_volume_level(self, volume):
        """Set the volume level of the display."""
        vol_pct = round(volume * 100)
        try:
            return await self._execute_with_retry(
                self.mdc.volume,
                self.display_id,
                [vol_pct]
            )
        except Exception as e:
            _LOGGER.error("Failed to set volume level: %s", str(e))
            raise

    async def async_select_source(self, source):
        """Set the input source of the display."""
        try:
            position = self.source_list.index(source)
            return await self._execute_with_retry(
                self.mdc.input_source,
                self.display_id,
                [list(SOURCE_MAP.keys())[position]]
            )
        except ValueError as e:
            _LOGGER.error("Invalid source '%s': %s", source, str(e))
            raise
        except Exception as e:
            _LOGGER.error("Failed to select source: %s", str(e))
            raise
