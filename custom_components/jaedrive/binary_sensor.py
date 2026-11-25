"""Cloud subscription not active: a problem to report (also for automations)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import JaeDriveConfigEntry, JaeDriveCoordinator
from .entity import JaeDriveAccountEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JaeDriveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([JaeDriveSubscriptionProblem(entry.runtime_data)])


class JaeDriveSubscriptionProblem(JaeDriveAccountEntity, BinarySensorEntity):
    _platform_domain = "binary_sensor"
    _attr_translation_key = "subscription_problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: JaeDriveCoordinator) -> None:
        super().__init__(coordinator, "subscription_problem")

    @property
    def is_on(self) -> bool:
        return not self.subscription.get("active", False)

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {"reason": self.subscription.get("reason"), "tier": self.subscription.get("tier")}
