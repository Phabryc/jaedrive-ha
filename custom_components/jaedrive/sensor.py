"""Sensori JaeDrive: odometro, tagliando, batteria, autonomie, ultimo viaggio, ultimi 30 giorni."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import JaeDriveConfigEntry, JaeDriveCoordinator
from .entity import JaeDriveAccountEntity, JaeDriveVehicleEntity, track_vehicles

PARALLEL_UPDATES = 0

CONSUMPTION_L = "L/100 km"
CONSUMPTION_KWH = "kWh/100 km"


def _ts(value: Any) -> datetime | None:
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def _date(value: Any) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else None


def _l100(km_per_liter: Any) -> float | None:
    """Il cloud dà il consumo in km/l; in HA lo mostriamo in L/100 km."""
    if not isinstance(km_per_liter, (int, float)) or km_per_liter <= 0:
        return None
    return round(100 / km_per_liter, 2)


def _trip(v: dict[str, Any], key: str) -> Any:
    return (v.get("lastTrip") or {}).get(key)


def _stats(v: dict[str, Any], key: str) -> Any:
    return (v.get("stats30d") or {}).get(key)


def _park(v: dict[str, Any], key: str) -> Any:
    return (v.get("park") or {}).get(key)


@dataclass(frozen=True, kw_only=True)
class JaeDriveSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    # Creata solo se all'avvio (o alla comparsa dell'auto) c'è un valore: un'auto che non
    # espone il dato non si ritrova un'entità "sconosciuta" per sempre.
    exists_fn: Callable[[dict[str, Any]], bool] | None = None
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _trip_attrs(v: dict[str, Any]) -> dict[str, Any]:
    t = v.get("lastTrip") or {}
    flow = t.get("flowPct") or {}
    return {
        "from": t.get("from"),
        "to": t.get("to"),
        "started_at": t.get("startedAt"),
        "ended_at": t.get("endedAt"),
        "duration_min": round(t["durationSec"] / 60) if t.get("durationSec") else None,
        "liters": t.get("liters"),
        "kwh": t.get("kwh"),
        "ev_percent": round(flow["ev"], 1) if "ev" in flow else None,
    }


VEHICLE_SENSORS: tuple[JaeDriveSensorDescription, ...] = (
    JaeDriveSensorDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda v: v.get("odometerKm"),
        suggested_display_precision=0,
        exists_fn=lambda v: True,
    ),
    JaeDriveSensorDescription(
        key="service_due_distance",
        translation_key="service_due_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda v: v.get("serviceDueKm"),
        suggested_display_precision=0,
    ),
    JaeDriveSensorDescription(
        key="service_due_date",
        translation_key="service_due_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda v: _date(v.get("serviceDueDate")),
        exists_fn=lambda v: True,
    ),
    JaeDriveSensorDescription(
        key="ev_distance_total",
        translation_key="ev_distance_total",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda v: v.get("evKmTotal"),
        suggested_display_precision=0,
    ),
    JaeDriveSensorDescription(
        key="hev_distance_total",
        translation_key="hev_distance_total",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda v: v.get("hevKmTotal"),
        suggested_display_precision=0,
    ),
    JaeDriveSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.get("batteryPct"),
        suggested_display_precision=0,
        exists_fn=lambda v: True,
    ),
    JaeDriveSensorDescription(
        key="fuel_level",
        translation_key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.get("fuelPct"),
        suggested_display_precision=0,
        exists_fn=lambda v: not (v.get("powertrain") or "").startswith("BEV"),
    ),
    JaeDriveSensorDescription(
        key="ev_range",
        translation_key="ev_range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.get("evRangeKm"),
        suggested_display_precision=0,
    ),
    JaeDriveSensorDescription(
        key="fuel_range",
        translation_key="fuel_range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda v: v.get("fuelRangeKm"),
        suggested_display_precision=0,
        exists_fn=lambda v: not (v.get("powertrain") or "").startswith("BEV"),
    ),
    JaeDriveSensorDescription(
        key="parked_at",
        translation_key="parked_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda v: _ts(_park(v, "at")),
        # Solo con il permesso alla posizione (la chiave "park" esiste) e un parcheggio salvato.
        exists_fn=lambda v: "park" in v,
        attrs_fn=lambda v: {"address": _park(v, "address")},
    ),
    JaeDriveSensorDescription(
        key="last_trip_distance",
        translation_key="last_trip_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda v: _trip(v, "km"),
        exists_fn=lambda v: True,
        attrs_fn=_trip_attrs,
        suggested_display_precision=1,
    ),
    JaeDriveSensorDescription(
        key="last_trip_consumption",
        translation_key="last_trip_consumption",
        native_unit_of_measurement=CONSUMPTION_L,
        suggested_display_precision=1,
        value_fn=lambda v: _l100(_trip(v, "kmPerLiter")),
        exists_fn=lambda v: True,
        attrs_fn=lambda v: {"km_per_liter": _trip(v, "kmPerLiter")},
    ),
    JaeDriveSensorDescription(
        key="distance_30d",
        translation_key="distance_30d",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda v: _stats(v, "km") or 0,
        exists_fn=lambda v: True,
        attrs_fn=lambda v: {"trips": _stats(v, "tripCount") or 0},
        suggested_display_precision=0,
    ),
    JaeDriveSensorDescription(
        key="consumption_30d",
        translation_key="consumption_30d",
        native_unit_of_measurement=CONSUMPTION_L,
        suggested_display_precision=1,
        value_fn=lambda v: _l100(_stats(v, "kmPerLiter")),
        exists_fn=lambda v: True,
        attrs_fn=lambda v: {"km_per_liter": _stats(v, "kmPerLiter")},
    ),
    JaeDriveSensorDescription(
        key="electric_consumption_30d",
        translation_key="electric_consumption_30d",
        native_unit_of_measurement=CONSUMPTION_KWH,
        suggested_display_precision=1,
        value_fn=lambda v: _stats(v, "avgKwhPer100Km"),
        exists_fn=lambda v: (v.get("powertrain") or "").startswith(("SHS_P", "BEV")),
    ),
    JaeDriveSensorDescription(
        key="ev_share_30d",
        translation_key="ev_share_30d",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda v: ((v.get("stats30d") or {}).get("flowPct") or {}).get("ev"),
        exists_fn=lambda v: (v.get("powertrain") or "").startswith(("SHS", "BEV")),
    ),
    JaeDriveSensorDescription(
        key="status_updated",
        translation_key="status_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: _ts(v.get("statusAt")),
        exists_fn=lambda v: True,
    ),
    JaeDriveSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: _ts(v.get("lastSeenAt") or v.get("vehicleDataAt")),
        exists_fn=lambda v: True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JaeDriveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data

    def build(vehicle_id: str, vehicle: dict[str, Any]) -> list[JaeDriveVehicleSensor]:
        return [
            JaeDriveVehicleSensor(coordinator, vehicle_id, d)
            for d in VEHICLE_SENSORS
            if (d.exists_fn(vehicle) if d.exists_fn else d.value_fn(vehicle) is not None)
        ]

    entry.async_on_unload(track_vehicles(coordinator, async_add_entities, build))
    async_add_entities([JaeDriveSubscriptionExpirySensor(coordinator)])


class JaeDriveVehicleSensor(JaeDriveVehicleEntity, SensorEntity):
    _platform_domain = "sensor"
    entity_description: JaeDriveSensorDescription

    def __init__(self, coordinator: JaeDriveCoordinator, vehicle_id: str, description: JaeDriveSensorDescription) -> None:
        super().__init__(coordinator, vehicle_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.vehicle)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.vehicle) if fn else None


class JaeDriveSubscriptionExpirySensor(JaeDriveAccountEntity, SensorEntity):
    _platform_domain = "sensor"
    _attr_translation_key = "subscription_expires"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: JaeDriveCoordinator) -> None:
        super().__init__(coordinator, "subscription_expires")

    @property
    def native_value(self) -> datetime | None:
        return _ts(self.subscription.get("expiresAt"))
