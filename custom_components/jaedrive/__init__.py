"""Integrazione JaeDrive: i dati delle auto dal cloud JaeDrive, in sola lettura."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JaeDriveApi
from .const import CONF_BASE_URL, CONF_TOKEN, DEFAULT_BASE_URL
from .coordinator import JaeDriveConfigEntry, JaeDriveCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.EVENT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: JaeDriveConfigEntry) -> bool:
    api = JaeDriveApi(
        async_get_clientsession(hass),
        entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        entry.data[CONF_TOKEN],
    )
    coordinator = JaeDriveCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start_stream()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JaeDriveConfigEntry) -> bool:
    # Il task dello stream è legato alla voce (async_create_background_task) e si chiude da sé.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
