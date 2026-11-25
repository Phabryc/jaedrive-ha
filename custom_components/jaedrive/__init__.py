"""JaeDrive integration: car data from the JaeDrive cloud, read only."""

from __future__ import annotations

from pathlib import Path

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import JaeDriveApi
from .const import CONF_BASE_URL, CONF_TOKEN, DEFAULT_BASE_URL, DOMAIN, FRONTEND_URL
from .coordinator import JaeDriveConfigEntry, JaeDriveCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.EVENT,
    Platform.SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the cards and the dashboard strategy, and load them in every browser."""
    await _async_register_frontend(hass)
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    # Without http or frontend (tests, minimal setups) the entities still work.
    if hass.http is None or "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    version = (await async_get_integration(hass, DOMAIN)).version
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(Path(__file__).parent / "frontend"), cache_headers=False)]
    )
    # The version in the query makes browsers fetch the new file after an update.
    add_extra_js_url(hass, f"{FRONTEND_URL}/jaedrive.js?v={version}")


async def async_setup_entry(hass: HomeAssistant, entry: JaeDriveConfigEntry) -> bool:
    api = JaeDriveApi(
        async_get_clientsession(hass),
        entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        entry.data[CONF_TOKEN],
    )
    coordinator = JaeDriveCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _migrate_entity_ids(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start_stream()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JaeDriveConfigEntry) -> bool:
    # The stream task belongs to the entry (async_create_background_task) and stops by itself.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _migrate_entity_ids(hass: HomeAssistant, entry: JaeDriveConfigEntry) -> None:
    """0.1.0 put the car name in the entity_id (`sensor.jaedrive_<car>_odometer`).

    Since 0.1.1 it is `sensor.jaedrive_odometer` (HA adds `_2` for a second car), so the ready-made
    dashboard works as is. Only ids still in the old form are renamed, and only when the new one is
    free: an id the user changed by hand is left alone.
    """
    registry = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        vehicle_id, _, key = ent.unique_id.partition("_")
        if not key or vehicle_id == entry.unique_id:
            continue
        domain, object_id = ent.entity_id.split(".", 1)
        if not (object_id.startswith("jaedrive_") and object_id.endswith(f"_{key}")):
            continue
        if object_id == f"jaedrive_{key}":
            continue
        new_id = f"{domain}.jaedrive_{key}"
        if registry.async_is_registered(new_id):
            continue
        registry.async_update_entity(ent.entity_id, new_entity_id=new_id)
