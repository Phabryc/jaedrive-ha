"""Dove è parcheggiata l'auto (solo se l'utente ha concesso la posizione)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import JaeDriveConfigEntry
from .entity import JaeDriveVehicleEntity, track_vehicles

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JaeDriveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data

    def build(vehicle_id: str, vehicle: dict[str, Any]) -> list[JaeDriveParkTracker]:
        # La chiave "park" c'è solo con lo scope location:read.
        return [JaeDriveParkTracker(coordinator, vehicle_id, "park")] if "park" in vehicle else []

    entry.async_on_unload(track_vehicles(coordinator, async_add_entities, build))


class JaeDriveParkTracker(JaeDriveVehicleEntity, TrackerEntity):
    _platform_domain = "device_tracker"
    _attr_translation_key = "park"
    _attr_source_type = SourceType.GPS

    @property
    def _park(self) -> dict[str, Any]:
        return self.vehicle.get("park") or {}

    @property
    def latitude(self) -> float | None:
        return self._park.get("lat")

    @property
    def longitude(self) -> float | None:
        return self._park.get("lon")

    @property
    def location_accuracy(self) -> float:
        return float(self._park.get("accuracyM") or 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"address": self._park.get("address"), "parked_at": self._park.get("at")}
