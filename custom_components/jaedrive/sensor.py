"""JaeDrive sensors: odometer, service, battery, ranges, last trip, Trip A/B, last 30 days."""

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
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import JaeDriveConfigEntry, JaeDriveCoordinator
from .entity import JaeDriveAccountEntity, JaeDriveVehicleEntity, track_vehicles

PARALLEL_UPDATES = 0

# Consumption as in the app and on the website, from the units of the JaeDrive profile
# (coordinator.units). Miles use the imperial gallon, as the app does.
KM_TO_MI = 0.621371
L_PER_IMPERIAL_GALLON = 4.54609
FUEL_UNITS = {
    ("km", "ratio"): "km/L",
    ("km", "l100"): "L/100 km",
    ("mi", "ratio"): "mpg",
    ("mi", "l100"): "gal/100 mi",
}
ELECTRIC_UNITS = {"km": "kWh/100 km", "mi": "kWh/100 mi"}
# Distances and speeds keep km and km/h as native unit; the profile picks the display unit.
DISPLAY_UNITS = {
    SensorDeviceClass.DISTANCE: {"km": UnitOfLength.KILOMETERS, "mi": UnitOfLength.MILES},
    SensorDeviceClass.SPEED: {"km": UnitOfSpeed.KILOMETERS_PER_HOUR, "mi": UnitOfSpeed.MILES_PER_HOUR},
}
APPLIED_DISTANCE_UNIT = "applied_distance_unit"


def fuel_consumption(km_per_liter: Any, units: dict[str, str]) -> float | None:
    """The cloud gives km/l; convert it to the unit of the profile."""
    if not isinstance(km_per_liter, (int, float)) or km_per_liter <= 0:
        return None
    miles = units["distance"] == "mi"
    if units["consumption"] == "l100":
        per_100_km = 100 / km_per_liter
        return round(per_100_km / (KM_TO_MI * L_PER_IMPERIAL_GALLON) if miles else per_100_km, 2)
    return round(km_per_liter * KM_TO_MI * L_PER_IMPERIAL_GALLON if miles else km_per_liter, 2)


def electric_consumption(kwh_per_100_km: Any, units: dict[str, str]) -> float | None:
    """The cloud gives kWh/100 km; with miles it becomes kWh/100 mi."""
    if not isinstance(kwh_per_100_km, (int, float)):
        return None
    return round(kwh_per_100_km / KM_TO_MI if units["distance"] == "mi" else kwh_per_100_km, 2)


def _ts(value: Any) -> datetime | None:
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def _date(value: Any) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else None


def _trip(v: dict[str, Any], key: str) -> Any:
    return (v.get("lastTrip") or {}).get(key)


def _stats(v: dict[str, Any], key: str) -> Any:
    return (v.get("stats30d") or {}).get(key)


def _slot(v: dict[str, Any], slot: str, key: str) -> Any:
    return (v.get(f"trip{slot.upper()}") or {}).get(key)


def _plugin(v: dict[str, Any]) -> bool:
    return (v.get("powertrain") or "").startswith(("SHS_P", "BEV"))


def _hybrid(v: dict[str, Any]) -> bool:
    return (v.get("powertrain") or "").startswith(("SHS", "BEV"))


def _always(v: dict[str, Any]) -> bool:
    return True


def _minutes(seconds: Any) -> int | None:
    return round(seconds / 60) if isinstance(seconds, (int, float)) and seconds > 0 else None


def _park(v: dict[str, Any], key: str) -> Any:
    return (v.get("park") or {}).get(key)


@dataclass(frozen=True, kw_only=True)
class JaeDriveSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    # Created only if there is a value at startup (or when the car appears): a car that does not
    # expose the value does not get an entity that is "unknown" forever.
    exists_fn: Callable[[dict[str, Any]], bool] | None = None
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    # "fuel" (value_fn gives km/l) or "electric" (kWh/100 km): value and unit follow the profile.
    consumption: str | None = None


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
        # Only with the location permission (the "park" key exists) and a saved parking spot.
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
        consumption="fuel",
        suggested_display_precision=1,
        value_fn=lambda v: _trip(v, "kmPerLiter"),
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
        consumption="fuel",
        suggested_display_precision=1,
        value_fn=lambda v: _stats(v, "kmPerLiter"),
        exists_fn=lambda v: True,
        attrs_fn=lambda v: {"km_per_liter": _stats(v, "kmPerLiter")},
    ),
    JaeDriveSensorDescription(
        key="electric_consumption_30d",
        translation_key="electric_consumption_30d",
        consumption="electric",
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


def _d(key: str, value_fn: Callable[[dict[str, Any]], Any], exists_fn=_always, **kw: Any) -> JaeDriveSensorDescription:
    return JaeDriveSensorDescription(key=key, translation_key=key, value_fn=value_fn, exists_fn=exists_fn, **kw)


KM = {"device_class": SensorDeviceClass.DISTANCE, "native_unit_of_measurement": UnitOfLength.KILOMETERS, "suggested_display_precision": 1}
LITERS = {"device_class": SensorDeviceClass.VOLUME, "native_unit_of_measurement": UnitOfVolume.LITERS, "suggested_display_precision": 2}
KWH = {"device_class": SensorDeviceClass.ENERGY, "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR, "suggested_display_precision": 2}
KW = {"device_class": SensorDeviceClass.POWER, "native_unit_of_measurement": UnitOfPower.KILO_WATT, "suggested_display_precision": 0}
SOC = {"device_class": SensorDeviceClass.BATTERY, "native_unit_of_measurement": PERCENTAGE, "suggested_display_precision": 0}

# Last trip: the same data as the trip detail cards on the website (not the charts).
LAST_TRIP_SENSORS: tuple[JaeDriveSensorDescription, ...] = (
    _d("last_trip_start", lambda v: _trip(v, "from")),
    _d("last_trip_end", lambda v: _trip(v, "to")),
    _d("last_trip_ended_at", lambda v: _ts(_trip(v, "endedAt")), device_class=SensorDeviceClass.TIMESTAMP),
    _d(
        "last_trip_duration",
        lambda v: _minutes(_trip(v, "durationSec")),
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    _d(
        "last_trip_avg_speed",
        lambda v: _trip(v, "avgSpeedKmh"),
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=0,
    ),
    _d("last_trip_fuel_used", lambda v: _trip(v, "liters"), **LITERS),
    _d(
        "last_trip_ev_share",
        lambda v: (_trip(v, "flowPct") or {}).get("ev"),
        _hybrid,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
    ),
    _d("last_trip_ev_distance", lambda v: _trip(v, "kmEv"), _plugin, **KM),
    _d("last_trip_hev_distance", lambda v: _trip(v, "kmHev"), _plugin, **KM),
    _d("last_trip_energy", lambda v: _trip(v, "kwh"), _plugin, **KWH),
    _d(
        "last_trip_electric_consumption",
        lambda v: _trip(v, "kwhPer100Km"),
        _plugin,
        consumption="electric",
        suggested_display_precision=1,
    ),
    _d("last_trip_battery_start", lambda v: _trip(v, "socStart"), _plugin, **SOC),
    _d("last_trip_battery_end", lambda v: _trip(v, "socEnd"), _plugin, **SOC),
    _d("last_trip_power_max", lambda v: _trip(v, "powerKwMax"), _plugin, **KW),
    _d("last_trip_regen_max", lambda v: _trip(v, "regenKwMax"), _plugin, **KW),
    _d("last_trip_regen_energy", lambda v: _trip(v, "regenKwh"), _plugin, **KWH),
)


def _slot_sensors(slot: str) -> tuple[JaeDriveSensorDescription, ...]:
    """Running Trip A/B (the manual counter not reset yet). Always present, as in the app."""
    return (
        _d(f"trip_{slot}_distance", lambda v: _slot(v, slot, "km"), attrs_fn=lambda v: {"label": _slot(v, slot, "label")}, **KM),
        _d(f"trip_{slot}_fuel_used", lambda v: _slot(v, slot, "liters"), **LITERS),
        _d(
            f"trip_{slot}_consumption",
            lambda v: _slot(v, slot, "kmPerLiter"),
            consumption="fuel",
            suggested_display_precision=1,
            attrs_fn=lambda v: {"km_per_liter": _slot(v, slot, "kmPerLiter")},
        ),
        _d(f"trip_{slot}_since", lambda v: _ts(_slot(v, slot, "startedAt")), device_class=SensorDeviceClass.TIMESTAMP),
        _d(f"trip_{slot}_ev_distance", lambda v: _slot(v, slot, "kmEv"), _plugin, **KM),
        _d(f"trip_{slot}_energy", lambda v: _slot(v, slot, "kwh"), _plugin, **KWH),
    )


ALL_VEHICLE_SENSORS = VEHICLE_SENSORS + LAST_TRIP_SENSORS + _slot_sensors("a") + _slot_sensors("b")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JaeDriveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data

    def build(vehicle_id: str, vehicle: dict[str, Any]) -> list[JaeDriveVehicleSensor]:
        return [
            JaeDriveVehicleSensor(coordinator, vehicle_id, d)
            for d in ALL_VEHICLE_SENSORS
            if (d.exists_fn(vehicle) if d.exists_fn else d.value_fn(vehicle) is not None)
        ]

    entry.async_on_unload(track_vehicles(coordinator, async_add_entities, build))
    async_add_entities([JaeDriveSubscriptionExpirySensor(coordinator)])

    @callback
    def apply_distance_unit() -> None:
        """Distance unit of the JaeDrive profile -> display unit of distances and speeds.

        Written in the entity registry, as when the unit is picked in the entity settings, and
        only when the profile changes it: a unit picked by hand in HA stays until then. The first
        time km is just recorded, so an imperial HA keeps its miles until the profile says so.
        """
        unit = coordinator.units["distance"]
        applied = entry.data.get(APPLIED_DISTANCE_UNIT)
        if unit == applied:
            return
        if applied is not None or unit != "km":
            registry = er.async_get(hass)
            for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
                units = DISPLAY_UNITS.get(reg.original_device_class)
                if reg.domain != "sensor" or units is None:
                    continue
                options = dict(reg.options.get("sensor", {}))
                if options.get("unit_of_measurement") == units[unit]:
                    continue
                options["unit_of_measurement"] = units[unit]
                registry.async_update_entity_options(reg.entity_id, "sensor", options)
        hass.config_entries.async_update_entry(entry, data={**entry.data, APPLIED_DISTANCE_UNIT: unit})

    apply_distance_unit()
    entry.async_on_unload(coordinator.async_add_listener(apply_distance_unit))


class JaeDriveVehicleSensor(JaeDriveVehicleEntity, SensorEntity):
    _platform_domain = "sensor"
    entity_description: JaeDriveSensorDescription

    def __init__(self, coordinator: JaeDriveCoordinator, vehicle_id: str, description: JaeDriveSensorDescription) -> None:
        super().__init__(coordinator, vehicle_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        value = self.entity_description.value_fn(self.vehicle)
        kind = self.entity_description.consumption
        if kind == "fuel":
            return fuel_consumption(value, self.coordinator.units)
        if kind == "electric":
            return electric_consumption(value, self.coordinator.units)
        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        units = self.coordinator.units
        kind = self.entity_description.consumption
        if kind == "fuel":
            return FUEL_UNITS[(units["distance"], units["consumption"])]
        if kind == "electric":
            return ELECTRIC_UNITS[units["distance"]]
        return self.entity_description.native_unit_of_measurement

    @property
    def suggested_unit_of_measurement(self) -> str | None:
        """New entities (a new car) start with the distance unit of the profile."""
        units = DISPLAY_UNITS.get(self.entity_description.device_class)
        if units is not None:
            return units[self.coordinator.units["distance"]]
        return self.entity_description.suggested_unit_of_measurement

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
