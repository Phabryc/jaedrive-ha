"""Trip ended event, for automations like "I have arrived"."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SIGNAL_TRIP_ENDED
from .coordinator import JaeDriveConfigEntry
from .entity import JaeDriveVehicleEntity, track_vehicles

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JaeDriveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data

    def build(vehicle_id: str, vehicle: dict[str, Any]) -> list[JaeDriveTripEvent]:
        return [JaeDriveTripEvent(coordinator, vehicle_id, "trip")]

    entry.async_on_unload(track_vehicles(coordinator, async_add_entities, build))


class JaeDriveTripEvent(JaeDriveVehicleEntity, EventEntity):
    _platform_domain = "event"
    _attr_translation_key = "trip"
    _attr_event_types = ["trip_ended"]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_TRIP_ENDED.format(self.coordinator.config_entry.entry_id),
                self._on_trip_ended,
            )
        )

    @callback
    def _on_trip_ended(self, vehicle_id: str, trip: dict[str, Any]) -> None:
        if vehicle_id != self.vehicle_id:
            return
        self._trigger_event(
            "trip_ended",
            {
                "km": trip.get("km"),
                "from": trip.get("from"),
                "to": trip.get("to"),
                "started_at": trip.get("startedAt"),
                "ended_at": trip.get("endedAt"),
                "km_per_liter": trip.get("kmPerLiter"),
            },
        )
        self.async_write_ha_state()
