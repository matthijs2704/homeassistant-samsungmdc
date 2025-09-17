"""The Samsung MDC integration."""

from __future__ import annotations

import logging
import contextlib

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, PLATFORMS, CONF_IP_ADDRESS, CONF_DISPLAY_ID
from .mdc_api import MdcApi
from .coordinator import MDCUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Samsung MDC from a config entry."""
    host = entry.data[CONF_IP_ADDRESS]
    display_id = entry.data.get(CONF_DISPLAY_ID, 1)
    name = entry.data.get("name", f"Samsung MDC ({host}#{display_id})")
    model = entry.data.get("model")

    api = MdcApi(host, display_id)

    try:
        await api.async_connect()
    except Exception as err:
        with contextlib.suppress(Exception):
            await api.async_close()
        raise ConfigEntryNotReady(
            f"Cannot connect to Samsung MDC display: {err}"
        ) from err

    coordinator = MDCUpdateCoordinator(hass, api, name=name)
    await coordinator.async_config_entry_first_refresh()
    sw_version = (coordinator.data or {}).get("sw_version")

    # Register top-level device once
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{host}-{display_id}")},
        manufacturer="Samsung",
        name=name,
        model=model or "Unknown",
        sw_version=sw_version or "Unknown",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "device_id": device.id,
        "device_info": {
            "identifiers": {(DOMAIN, f"{host}-{display_id}")},
            "manufacturer": "Samsung",
            "name": name,
            "model": model or "Unknown",
            "sw_version": sw_version or "Unknown",
        },
        "unique_base": f"{host}-{display_id}",
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
