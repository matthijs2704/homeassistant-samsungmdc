"""Number entities for Samsung MDC display."""

import logging

from homeassistant import config_entries
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_entity import SamsungMDCBaseEntity
from .const import DOMAIN
from .coordinator import MDCUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Samsung MDC number entities from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The configuration entry for this integration.
        async_add_entities: Callback to add entities to Home Assistant.
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: MDCUpdateCoordinator = data["coordinator"]
    device_unique_id = data["unique_base"]
    device_model = entry.data.get("model", "Unknown")

    entities = []

    # Brightness control
    unique_id = f"{device_unique_id}-brightness"
    entities.append(
        SamsungMDCBrightness(
            coordinator,
            name="Brightness",
            model=device_model,
            unique_id=unique_id,
            device_unique_id=device_unique_id,
        )
    )

    async_add_entities(entities, True)


class SamsungMDCBrightness(SamsungMDCBaseEntity, NumberEntity):
    """Samsung MDC brightness control."""

    _attr_icon = "mdi:brightness-6"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        """Return the current brightness level."""
        data = self.coordinator.data or {}
        brightness = data.get("brightness")
        if brightness is None:
            return None
        return float(brightness)

    async def async_set_native_value(self, value: float) -> None:
        """Set the brightness level.

        Args:
            value: The desired brightness level (0-100).
        """
        val = round(value)
        await self.coordinator.async_execute("manual_lamp", args=[val])
