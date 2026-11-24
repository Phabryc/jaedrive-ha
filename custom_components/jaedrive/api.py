"""Client del cloud JaeDrive: link guidato, stato e stream SSE (sola lettura)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json
from typing import Any

import aiohttp

from .const import STREAM_READ_TIMEOUT


class JaeDriveError(Exception):
    """Errore generico (rete, risposta inattesa)."""


class JaeDriveAuthError(JaeDriveError):
    """Token non valido o revocato (401): serve un nuovo collegamento."""


class JaeDriveSubscriptionExpired(JaeDriveError):
    """Abbonamento cloud non attivo (402): il token resta valido."""

    def __init__(self, subscription: dict[str, Any]) -> None:
        super().__init__("subscription expired")
        self.subscription = subscription


async def link_start(session: aiohttp.ClientSession, base_url: str, instance_name: str) -> dict[str, Any]:
    """Apre una richiesta di collegamento; restituisce deviceCode e link per l'utente."""
    try:
        async with session.post(
            f"{base_url}/api/ha/link/start",
            json={"instanceName": instance_name},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                raise JaeDriveError(f"link start: HTTP {resp.status}")
            return await resp.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise JaeDriveError(str(err)) from err


async def link_poll(session: aiohttp.ClientSession, base_url: str, device_code: str) -> dict[str, Any]:
    """Una richiesta di polling: status = pending | approved | denied | expired | consumed | invalid."""
    try:
        async with session.post(
            f"{base_url}/api/ha/link/poll",
            json={"deviceCode": device_code},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status == 404:
                return {"status": "invalid"}
            if resp.status == 429:
                return {"status": "pending"}
            if resp.status != 200:
                raise JaeDriveError(f"link poll: HTTP {resp.status}")
            return await resp.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise JaeDriveError(str(err)) from err


class JaeDriveApi:
    """Chiamate autenticate col token jdh_."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, token: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}

    async def get_state(self) -> dict[str, Any]:
        """Stato completo di tutte le auto."""
        return await self._get_json("/api/ha/v1/state")

    async def get_subscription(self) -> dict[str, Any]:
        """Stato dell'abbonamento: risponde anche ad abbonamento scaduto."""
        return await self._get_json("/api/ha/v1/subscription")

    async def _get_json(self, path: str) -> dict[str, Any]:
        try:
            async with self._session.get(
                f"{self._base_url}{path}",
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 401:
                    raise JaeDriveAuthError("token rejected")
                if resp.status == 402:
                    body = await resp.json(content_type=None)
                    raise JaeDriveSubscriptionExpired(body.get("subscription") or {})
                if resp.status != 200:
                    raise JaeDriveError(f"{path}: HTTP {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise JaeDriveError(str(err)) from err

    async def events(self) -> AsyncIterator[tuple[str, Any]]:
        """Legge lo stream SSE e restituisce (evento, dati) finché la connessione regge.

        Parser minimo: righe `event:` e `data:`, riga vuota = fine evento, `:` = commento
        (il keepalive del server). Un silenzio più lungo di STREAM_READ_TIMEOUT chiude.
        """
        try:
            async with self._session.get(
                f"{self._base_url}/api/ha/v1/events",
                headers={**self._headers, "Accept": "text/event-stream"},
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=STREAM_READ_TIMEOUT),
            ) as resp:
                if resp.status == 401:
                    raise JaeDriveAuthError("token rejected")
                if resp.status != 200:
                    raise JaeDriveError(f"events: HTTP {resp.status}")
                event = "message"
                data_lines: list[str] = []
                async for raw in resp.content:
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if not line:
                        if data_lines:
                            try:
                                payload = json.loads("\n".join(data_lines))
                            except ValueError:
                                payload = None
                            yield event, payload
                        event, data_lines = "message", []
                        continue
                    if line.startswith(":"):
                        continue
                    field, _, value = line.partition(":")
                    value = value.removeprefix(" ")
                    if field == "event":
                        event = value
                    elif field == "data":
                        data_lines.append(value)
        except (aiohttp.ClientError, TimeoutError, asyncio.IncompleteReadError) as err:
            raise JaeDriveError(str(err)) from err
