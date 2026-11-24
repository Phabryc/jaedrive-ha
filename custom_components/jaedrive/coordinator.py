"""Coordinator: stato iniziale via /state, poi aggiornamenti push dallo stream SSE."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import JaeDriveApi, JaeDriveAuthError, JaeDriveError, JaeDriveSubscriptionExpired
from .const import (
    DOMAIN,
    FALLBACK_INTERVAL,
    ISSUE_SUBSCRIPTION,
    PLANS_URL,
    SIGNAL_TRIP_ENDED,
    STREAM_BACKOFF_MAX,
    STREAM_BACKOFF_MIN,
)

_LOGGER = logging.getLogger(__name__)

type JaeDriveConfigEntry = ConfigEntry[JaeDriveCoordinator]


class JaeDriveCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Dati: {"subscription": {...}, "vehicles": {id: auto}}.

    Ad abbonamento scaduto le auto restano quelle dell'ultimo stato noto (le entità vanno in
    "non disponibile", non spariscono) e si aggiorna solo l'abbonamento.
    """

    config_entry: JaeDriveConfigEntry

    def __init__(self, hass: HomeAssistant, entry: JaeDriveConfigEntry, api: JaeDriveApi) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=FALLBACK_INTERVAL)
        self.api = api
        self._stream_task: asyncio.Task | None = None

    @property
    def subscription_active(self) -> bool:
        return bool(self.data and self.data.get("subscription", {}).get("active"))

    def _merge(self, subscription: dict[str, Any] | None = None, vehicles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        data = dict(self.data or {"subscription": {}, "vehicles": {}})
        if subscription is not None:
            data["subscription"] = subscription
        if vehicles is not None:
            data["vehicles"] = {v["id"]: v for v in vehicles}
        return data

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.api.get_state()
        except JaeDriveAuthError as err:
            raise ConfigEntryAuthFailed from err
        except JaeDriveSubscriptionExpired as err:
            data = self._merge(subscription=err.subscription)
        except JaeDriveError as err:
            raise UpdateFailed(str(err)) from err
        else:
            data = self._merge(subscription=state.get("subscription", {}), vehicles=state.get("vehicles", []))
        self._sync_issue(data["subscription"])
        return data

    def _sync_issue(self, subscription: dict[str, Any]) -> None:
        """Repair "abbonamento scaduto" finché il cloud non torna attivo."""
        if subscription.get("active"):
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_SUBSCRIPTION)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            ISSUE_SUBSCRIPTION,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_SUBSCRIPTION,
            learn_more_url=PLANS_URL,
        )

    # --- stream SSE ---------------------------------------------------------------------

    def start_stream(self) -> None:
        self._stream_task = self.config_entry.async_create_background_task(
            self.hass, self._stream_loop(), f"{DOMAIN}_stream"
        )

    async def _stream_loop(self) -> None:
        backoff = STREAM_BACKOFF_MIN
        while True:
            try:
                async for event, payload in self.api.events():
                    backoff = STREAM_BACKOFF_MIN
                    if self._handle_event(event, payload):
                        return
            except JaeDriveAuthError:
                self.config_entry.async_start_reauth(self.hass)
                return
            except JaeDriveError as err:
                _LOGGER.debug("Stream JaeDrive interrotto: %s", err)
            delay = backoff + random.uniform(0, backoff / 2)
            backoff = min(backoff * 2, STREAM_BACKOFF_MAX)
            await asyncio.sleep(delay)

    def _handle_event(self, event: str, payload: Any) -> bool:
        """Applica un evento; True = fermare lo stream (token revocato)."""
        if event == "revoked":
            self.config_entry.async_start_reauth(self.hass)
            return True
        if not isinstance(payload, dict):
            return False
        if event == "subscription":
            data = self._merge(subscription=payload)
            self._sync_issue(payload)
        elif event == "state":
            data = self._merge(subscription=payload.get("subscription"), vehicles=payload.get("vehicles", []))
        elif event == "vehicle" and isinstance(payload.get("vehicle"), dict):
            data = self._merge()
            vehicle = payload["vehicle"]
            data["vehicles"] = {**data["vehicles"], vehicle["id"]: vehicle}
        elif event == "vehicle_removed":
            data = self._merge()
            data["vehicles"] = {k: v for k, v in data["vehicles"].items() if k != payload.get("vehicleId")}
        elif event == "trip_ended":
            async_dispatcher_send(
                self.hass,
                SIGNAL_TRIP_ENDED.format(self.config_entry.entry_id),
                payload.get("vehicleId"),
                payload.get("trip") or {},
            )
            return False
        else:
            return False
        self.async_set_updated_data(data)
        return False
