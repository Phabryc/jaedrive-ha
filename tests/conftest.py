"""Common fixtures: a car as the cloud sends it and a fake client."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import copy
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jaedrive.const import CONF_ACCOUNT_ID, CONF_BASE_URL, CONF_SCOPES, CONF_TOKEN, DOMAIN

ACCOUNT_ID = "acc-1"
VEHICLE_ID = "veh-1"

SUBSCRIPTION = {"active": True, "status": "PREMIUM", "tier": "STANDARD", "expiresAt": "2026-12-24T21:11:02.858Z", "reason": None}

# Same shape as the real GET /api/ha/v1/state response.
VEHICLE: dict[str, Any] = {
    "id": VEHICLE_ID,
    "name": "Jaecoo test",
    "brand": "JAECOO",
    "model": "7",
    "powertrain": "SHS_H",
    "vin": None,
    "odometerKm": 12345,
    "serviceDueKm": None,
    "serviceDueDate": "2027-03-01",
    "evKmTotal": None,
    "hevKmTotal": None,
    "batteryPct": 61.2,
    "fuelPct": 40,
    "evRangeKm": None,
    "fuelRangeKm": 420,
    "statusAt": "2026-11-24T21:11:02.866Z",
    "vehicleDataAt": None,
    "lastSeenAt": None,
    "park": {"lat": 45.46, "lon": 9.19, "address": "Piazza Duomo, Milano", "accuracyM": 8, "at": "2026-11-24T21:11:02.866Z"},
    "lastTrip": {
        "id": "trip-1",
        "startedAt": "2026-11-24T20:11:02.869Z",
        "endedAt": "2026-11-24T20:41:02.869Z",
        "from": "Home",
        "to": "Office",
        "km": 23.4,
        "liters": 1.2,
        "kmPerLiter": 19.5,
        "kwh": None,
        "durationSec": 1800,
        "movingSec": 1500,
        "avgSpeedKmh": 56.2,
        "kmEv": None,
        "kmHev": None,
        "kwhPer100Km": None,
        "socStart": None,
        "socEnd": None,
        "powerKwMax": None,
        "regenKwMax": None,
        "regenKwh": None,
        "flowPct": {"ev": 42.0, "series": 30.0, "parallel": 20.0, "charge": 8.0},
    },
    "tripA": {
        "id": "man-a", "label": "Trip A", "startedAt": "2026-11-01T08:00:00.000Z",
        "km": 812.4, "liters": 41.3, "kmPerLiter": 19.7, "kwh": None, "kmEv": None, "kmHev": None,
    },
    "tripB": None,
    "stats30d": {"km": 23.4, "tripCount": 1, "kmPerLiter": 19.5, "avgKwhPer100Km": None, "flowPct": None},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def vehicle() -> dict[str, Any]:
    return copy.deepcopy(VEHICLE)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="JaeDrive",
        unique_id=ACCOUNT_ID,
        data={
            CONF_BASE_URL: "https://jaedrive.test",
            CONF_TOKEN: "jdh_test",
            CONF_ACCOUNT_ID: ACCOUNT_ID,
            CONF_SCOPES: ["vehicles:read", "location:read"],
        },
    )


class FakeStream:
    """SSE event queue: tests put (event, data) in it and the coordinator reads them."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    def push(self, event: str, data: Any) -> None:
        self.queue.put_nowait((event, data))

    async def events(self) -> AsyncIterator[tuple[str, Any]]:
        while True:
            yield await self.queue.get()


@pytest.fixture
def stream() -> FakeStream:
    return FakeStream()


@pytest.fixture
def mock_api(vehicle, stream):
    """Fake JaeDriveApi: /state returns the test car, the stream is the FakeStream queue."""
    with patch("custom_components.jaedrive.JaeDriveApi", autospec=True) as cls:
        api = cls.return_value
        api.get_state.return_value = {"subscription": dict(SUBSCRIPTION), "vehicles": [vehicle]}
        api.events.side_effect = stream.events
        yield api
