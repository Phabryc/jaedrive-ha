"""Common bases: one device per car, plus an "account" device for the subscription."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JaeDriveCoordinator

BRANDS = {"JAECOO": "Jaecoo", "OMODA": "Omoda", "CHERY": "Chery"}


def vehicle_device_info(vehicle: dict[str, Any]) -> DeviceInfo:
    brand = BRANDS.get(vehicle.get("brand") or "", vehicle.get("brand"))
    model = " ".join(x for x in (vehicle.get("model"), vehicle.get("powertrain")) if x) or None
    return DeviceInfo(
        identifiers={(DOMAIN, vehicle["id"])},
        name=vehicle.get("name") or "JaeDrive",
        manufacturer=brand,
        model=model,
        serial_number=vehicle.get("vin"),
        configuration_url="https://jaedrive.com/dashboard",
    )


class JaeDriveVehicleEntity(CoordinatorEntity[JaeDriveCoordinator]):
    """Entity of a car. HA builds the name: "<car> <entity name>".

    The entity_id instead is fixed: `<platform>.jaedrive_<key>`, with the key in English.
    HA would derive it from the translated name (in Italian `sensor.<car>_contachilometri`), and
    the YAML dashboard (dashboards/) could not work in every language. HA uses it only at the
    first registration; after that the registry one stays (even if the user renames it).
    """

    _attr_has_entity_name = True
    # Platform domain, for the entity_id: every subclass sets it.
    _platform_domain: str = ""

    def __init__(self, coordinator: JaeDriveCoordinator, vehicle_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.vehicle_id = vehicle_id
        self._attr_unique_id = f"{vehicle_id}_{key}"
        self._attr_device_info = vehicle_device_info(self.vehicle)
        if self._platform_domain:
            # Without the car name: the YAML dashboard works as is. For a second car HA takes it
            # as a suggestion and adds `_2` by itself.
            self.entity_id = f"{self._platform_domain}.jaedrive_{key}"

    @property
    def vehicle(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("vehicles", {}).get(self.vehicle_id, {})

    @property
    def available(self) -> bool:
        # Subscription expired or car removed from the cloud: "unavailable", nothing is deleted.
        return super().available and self.coordinator.subscription_active and bool(self.vehicle)


class JaeDriveAccountEntity(CoordinatorEntity[JaeDriveCoordinator]):
    """Account entities (subscription): they stay available even when the subscription expired."""

    _attr_has_entity_name = True

    _platform_domain: str = ""

    def __init__(self, coordinator: JaeDriveCoordinator, key: str) -> None:
        super().__init__(coordinator)
        if self._platform_domain:
            self.entity_id = f"{self._platform_domain}.jaedrive_{key}"
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"account_{entry.unique_id or entry.entry_id}")},
            name="JaeDrive",
            manufacturer="JaeDrive",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://jaedrive.com/settings",
        )

    @property
    def subscription(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("subscription", {})


def track_vehicles(
    coordinator: JaeDriveCoordinator,
    add_entities: Callable[[Iterable[Entity]], None],
    build: Callable[[str, dict[str, Any]], list[Entity]],
) -> Callable[[], None]:
    """Create the entities of the current cars and of the ones that appear later (new pairing)."""
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        vehicles = (coordinator.data or {}).get("vehicles", {})
        new = [vid for vid in vehicles if vid not in known]
        entities: list[Entity] = []
        for vid in new:
            known.add(vid)
            entities.extend(build(vid, vehicles[vid]))
        if entities:
            add_entities(entities)

    _add_new()
    return coordinator.async_add_listener(_add_new)
