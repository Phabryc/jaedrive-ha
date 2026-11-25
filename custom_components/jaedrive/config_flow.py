"""Guided link: HA shows a link, the user authorizes on the website, the token arrives by itself."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
import time
from typing import Any

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JaeDriveError, link_poll, link_start
from .const import CONF_ACCOUNT_ID, CONF_BASE_URL, CONF_SCOPES, CONF_TOKEN, DEFAULT_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Minimum pause between two polls, whatever the server says (tests set it to zero).
MIN_POLL_INTERVAL = 2


class JaeDriveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Device flow (same scheme as the car pairing): no token to copy."""

    VERSION = 1

    def __init__(self) -> None:
        self._link: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None
        self._result: dict[str, Any] | None = None
        self._failure: str | None = None
        self._base_url = DEFAULT_BASE_URL

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_link()

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._base_url = entry_data.get(CONF_BASE_URL, DEFAULT_BASE_URL)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_link()

    async def async_step_link(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._link is None:
            try:
                self._link = await link_start(
                    async_get_clientsession(self.hass), self._base_url, self.hass.config.location_name
                )
            except JaeDriveError:
                _LOGGER.exception("JaeDrive: cannot start the link")
                return self.async_abort(reason="cannot_connect")
        if self._task is None:
            self._task = self.hass.async_create_task(self._wait_for_approval())
        if not self._task.done():
            return self.async_show_progress(
                step_id="link",
                progress_action="wait_for_approval",
                progress_task=self._task,
                description_placeholders={
                    "url": self._link["verificationUriComplete"],
                    "code": self._link["userCode"],
                },
            )
        return self.async_show_progress_done(next_step_id="finish" if self._result else "failed")

    async def _wait_for_approval(self) -> None:
        assert self._link is not None
        session = async_get_clientsession(self.hass)
        deadline = time.monotonic() + float(self._link.get("expiresIn", 600))
        interval = max(MIN_POLL_INTERVAL, int(self._link.get("interval", 3)))
        while time.monotonic() < deadline:
            await asyncio.sleep(interval)
            try:
                res = await link_poll(session, self._base_url, self._link["deviceCode"])
            except JaeDriveError:
                continue  # network briefly down: retry until it expires
            status = res.get("status")
            if status == "approved" and res.get("token"):
                self._result = res
                return
            if status in ("denied", "expired", "consumed", "invalid"):
                self._failure = "denied" if status == "denied" else "expired"
                return
        self._failure = "expired"

    async def async_step_failed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason=self._failure or "expired")

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._result is not None
        account_id = str(self._result.get("accountId") or "")
        data = {
            CONF_BASE_URL: self._base_url,
            CONF_TOKEN: self._result["token"],
            CONF_ACCOUNT_ID: account_id,
            CONF_SCOPES: self._result.get("scopes", []),
        }
        await self.async_set_unique_id(account_id or None)
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="JaeDrive", data=data)
