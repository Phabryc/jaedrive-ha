"""Setup, entities and updates from the stream."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from custom_components.jaedrive.api import JaeDriveAuthError
from custom_components.jaedrive.const import DOMAIN, ISSUE_SUBSCRIPTION

from .conftest import SUBSCRIPTION, VEHICLE_ID


async def _setup(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities_created(hass: HomeAssistant, config_entry, mock_api) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.jaedrive_odometer").state == "12345"
    assert hass.states.get("sensor.jaedrive_battery").state == "61.2"
    assert hass.states.get("sensor.jaedrive_fuel_range").state == "420"
    # 19.5 km/l = 5.13 L/100 km
    consumption = hass.states.get("sensor.jaedrive_last_trip_consumption")
    assert float(consumption.state) == 5.13
    assert consumption.attributes["km_per_liter"] == 19.5
    tracker = hass.states.get("device_tracker.jaedrive_park")
    assert tracker.attributes["latitude"] == 45.46
    assert tracker.attributes["address"] == "Piazza Duomo, Milano"
    assert hass.states.get("binary_sensor.jaedrive_subscription_problem").state == "off"
    # A value this car does not have: no entity.
    assert hass.states.get("sensor.jaedrive_ev_range") is None


async def test_stream_updates(hass: HomeAssistant, config_entry, mock_api, stream, vehicle) -> None:
    await _setup(hass, config_entry)

    vehicle["odometerKm"] = 12400
    vehicle["lastTrip"] = {**vehicle["lastTrip"], "id": "trip-2", "km": 55.0}
    stream.push("vehicle", {"vehicle": vehicle})
    stream.push("trip_ended", {"vehicleId": VEHICLE_ID, "trip": vehicle["lastTrip"]})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.jaedrive_odometer").state == "12400"
    event = hass.states.get("event.jaedrive_trip")
    assert event.attributes["event_type"] == "trip_ended"
    assert event.attributes["km"] == 55.0


async def test_subscription_expired(hass: HomeAssistant, config_entry, mock_api, stream) -> None:
    await _setup(hass, config_entry)

    stream.push("subscription", {**SUBSCRIPTION, "active": False, "reason": "expired"})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.jaedrive_odometer").state == STATE_UNAVAILABLE
    assert hass.states.get("binary_sensor.jaedrive_subscription_problem").state == "on"
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_SUBSCRIPTION) is not None

    stream.push("subscription", SUBSCRIPTION)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.jaedrive_odometer").state == "12345"
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_SUBSCRIPTION) is None


async def test_revoked_starts_reauth(hass: HomeAssistant, config_entry, mock_api, stream) -> None:
    await _setup(hass, config_entry)
    stream.push("revoked", {})
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_auth_error_on_setup(hass: HomeAssistant, config_entry, mock_api) -> None:
    mock_api.get_state.side_effect = JaeDriveAuthError("nope")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_entity_ids_do_not_depend_on_language(hass: HomeAssistant, config_entry, mock_api) -> None:
    # In Italian HA would derive "sensor.jaecoo_test_contachilometri": the YAML dashboard would break.
    hass.config.language = "it"
    await _setup(hass, config_entry)
    assert hass.states.get("sensor.jaedrive_odometer").state == "12345"
    assert hass.states.get("sensor.jaedrive_odometer").attributes["friendly_name"] == "Jaecoo test Contachilometri"
    assert hass.states.get("sensor.jaedrive_subscription_expires") is not None


async def test_second_vehicle_gets_suffix(hass: HomeAssistant, config_entry, mock_api, vehicle) -> None:
    other = {**vehicle, "id": "veh-2", "name": "Omoda test", "odometerKm": 500}
    mock_api.get_state.return_value = {"subscription": dict(SUBSCRIPTION), "vehicles": [vehicle, other]}
    await _setup(hass, config_entry)
    assert hass.states.get("sensor.jaedrive_odometer").state == "12345"
    assert hass.states.get("sensor.jaedrive_odometer_2").state == "500"


async def test_migrates_entity_ids_from_0_1_0(hass: HomeAssistant, config_entry, mock_api) -> None:
    # 0.1.0 put the car name in the id: they are renamed at startup, ids changed by hand are not.
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{VEHICLE_ID}_odometer", config_entry=config_entry,
        suggested_object_id="jaedrive_jaecoo_test_odometer",
    )
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{VEHICLE_ID}_battery", config_entry=config_entry,
        suggested_object_id="batteria_auto",
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{VEHICLE_ID}_odometer") == "sensor.jaedrive_odometer"
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{VEHICLE_ID}_battery") == "sensor.batteria_auto"
    assert hass.states.get("sensor.jaedrive_odometer").state == "12345"


async def test_last_trip_details_and_manual_trips(hass: HomeAssistant, config_entry, mock_api) -> None:
    await _setup(hass, config_entry)
    assert hass.states.get("sensor.jaedrive_last_trip_start").state == "Home"
    assert hass.states.get("sensor.jaedrive_last_trip_end").state == "Office"
    assert hass.states.get("sensor.jaedrive_last_trip_duration").state == "30"
    assert float(hass.states.get("sensor.jaedrive_last_trip_avg_speed").state) == 56.2
    assert float(hass.states.get("sensor.jaedrive_last_trip_ev_share").state) == 42.0
    # Full hybrid: no plug-in sensors.
    assert hass.states.get("sensor.jaedrive_last_trip_energy") is None
    trip_a = hass.states.get("sensor.jaedrive_trip_a_distance")
    assert float(trip_a.state) == 812.4
    assert trip_a.attributes["label"] == "Trip A"
    assert float(hass.states.get("sensor.jaedrive_trip_a_consumption").state) == 5.08
    # Trip B reset or never started: it exists but has no value.
    assert hass.states.get("sensor.jaedrive_trip_b_distance").state == "unknown"
