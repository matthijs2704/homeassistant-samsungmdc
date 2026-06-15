"""Media Player class for Samsung MDC display."""

import asyncio
import logging
import time

from samsung_mdc import MDC
from samsung_mdc.commands import INPUT_SOURCE, MUTE, POWER
from samsung_mdc.exceptions import (
    MDCTimeoutError,
    MDCResponseError,
    NAKError,
)

from homeassistant import config_entries
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerDeviceClass,
)
from homeassistant.components.media_player.const import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_NAME,
    CONF_TYPE,
    CONF_MODEL,
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

from .base_entity import SamsungMDCBaseEntity
from .coordinator import MDCUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Connection retry settings (per Samsung MDC documentation)
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 2  # Samsung spec: retry every 2 seconds
POWER_ON_SOCKET_RECONNECT_TIME = (
    10  # Samsung spec: must re-connect socket after 10 sec for power on
)
POWER_ON_CHECK_INTERVAL = 3  # Check every 3 seconds after socket reconnect
MAX_POWER_ON_CHECKS = 10  # Try for up to 30 more seconds (10 * 3)

# Map the input sources of the MDC protocol to names for Home Assistant
ENUM_TO_NAME = {
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
NAME_TO_ENUM = {v: k for k, v in ENUM_TO_NAME.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Samsung MDC media player from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The configuration entry for this integration.
        async_add_entities: Callback to add entities to Home Assistant.
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: MDCUpdateCoordinator = data["coordinator"]
    device_unique_id = data["unique_base"]
    device_model = entry.data.get(CONF_MODEL, "Unknown")

    unique_id = f"{device_unique_id}-media_player"

    async_add_entities(
        [
            SamsungMDCMediaPlayer(
                coordinator,
                name=None,
                model=device_model,
                unique_id=unique_id,
                device_unique_id=device_unique_id,
            )
        ],
        True,
    )


class SamsungMDCMediaPlayer(SamsungMDCBaseEntity, MediaPlayerEntity):
    """Samsung MDC screen represented as a media_player."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_icon = "mdi:television"
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.VOLUME_STEP
    )

    # ----- State mapping from coordinator cache -----
    @property
    def state(self):
        """Return the current power state of the display.

        Returns
        -------
        MediaPlayerState
            MediaPlayerState.ON if powered on, MediaPlayerState.OFF if powered off, or None if unavailable.
        """
        data = self.coordinator.data or {}
        if not data:
            return None

        return (
            MediaPlayerState.ON
            if self.coordinator.effective_power_state
            else MediaPlayerState.OFF
        )

    @property
    def is_volume_muted(self) -> bool | None:
        """Return True if the display volume is muted, False if not, or None if unavailable."""
        data = self.coordinator.data or {}
        return data.get("muted")

    @property
    def volume_level(self) -> float | None:
        """Return the current volume level as a float between 0.0 and 1.0, or None if unavailable."""
        data = self.coordinator.data or {}
        vol = data.get("volume")
        if vol is None:
            return None
        # Normalize to 0.0-1.0 (adapt to your device’s range)
        return max(0.0, min(1.0, vol / 100.0))

    @property
    def source_list(self):
        """Return the list of available input sources for the display."""
        return list(ENUM_TO_NAME.values())

    @property
    def source(self):
        """Return the current input source of the display."""
        data = self.coordinator.data or {}
        src_enum = data.get("input")
        return ENUM_TO_NAME.get(src_enum, SOURCE_NONE)

    # ----- Commands delegate to coordinator (which handles retries) -----
    async def async_turn_on(self) -> None:
        """Turn on the Samsung MDC display."""
        await self.coordinator.async_power_on()

    async def async_turn_off(self) -> None:
        """Turn off the Samsung MDC display."""
        await self.coordinator.async_power_off()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the display volume level.

        Args:
            volume: The desired volume level as a float between 0.0 and 1.0.
        """
        # Convert 0.0-1.0 back to device scale
        val = round(volume * 100)
        await self.coordinator.async_execute("volume", args=[val])

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the display volume.

        Args:
            mute: True to mute, False to unmute.
        """
        await self.coordinator.async_execute("mute", args=[mute])

    async def async_select_source(self, source: str) -> None:
        """Select the input source for the display.

        Args:
            source: The name of the input source to select.

        """
        await self.coordinator.async_execute(
            "input_source", args=[NAME_TO_ENUM[source]]
        )
