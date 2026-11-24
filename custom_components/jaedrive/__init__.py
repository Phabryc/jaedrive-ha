"""Integrazione JaeDrive: i dati delle auto dal cloud JaeDrive, in sola lettura."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
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
    _migrate_entity_ids(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start_stream()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JaeDriveConfigEntry) -> bool:
    # Il task dello stream è legato alla voce (async_create_background_task) e si chiude da sé.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _migrate_entity_ids(hass: HomeAssistant, entry: JaeDriveConfigEntry) -> None:
    """0.1.0 metteva il nome dell'auto nell'entity_id (`sensor.jaedrive_<auto>_odometer`).

    Dalla 0.1.1 è `sensor.jaedrive_odometer` (la seconda auto prende `_2` da HA), così la plancia
    pronta si incolla senza modifiche. Rinomina solo gli id rimasti nella forma vecchia e solo se
    quello nuovo è libero: un id cambiato a mano dall'utente non si tocca.
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
