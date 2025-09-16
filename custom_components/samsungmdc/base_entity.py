from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MDCUpdateCoordinator


class SamsungMDCBaseEntity(CoordinatorEntity[MDCUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MDCUpdateCoordinator,
        *,
        name: str | None = None,
        model: str | None = None,
        unique_id: str,
        device_unique_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_name = name
        if model:
            self._attr_device_model = model
        self._attr_unique_id = unique_id
        self._device_unique_id = device_unique_id

    @property
    def device_info(self):
        data = self.coordinator.data or {}
        model = data.get("model")
        sw = data.get("sw_version")
        return {
            "identifiers": {(DOMAIN, self._device_unique_id)},
            "manufacturer": "Samsung",
            "model": self._attr_device_model or model or "MDC",
            "sw_version": sw,
            "name": self.name,
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Entity is available if coordinator has data or is in a power transition
        return super().available and (
            self.coordinator.data is not None or self.coordinator.in_power_transition
        )
