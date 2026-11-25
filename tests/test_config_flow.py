"""Guided link: link shown, approval on the website, entry created."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.jaedrive.const import CONF_ACCOUNT_ID, CONF_TOKEN, DOMAIN

from .conftest import ACCOUNT_ID

START = {
    "deviceCode": "d" * 43,
    "userCode": "ABCD2345",
    "verificationUri": "https://jaedrive.com/link",
    "verificationUriComplete": "https://jaedrive.com/link?code=ABCD2345",
    "interval": 0,
    "expiresIn": 600,
}


@pytest.fixture(autouse=True)
def fast_poll():
    with patch("custom_components.jaedrive.config_flow.MIN_POLL_INTERVAL", 0):
        yield


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.jaedrive.async_setup_entry", return_value=True):
        yield


async def _run_flow(hass: HomeAssistant, poll_results: list[dict], entry=None):
    with (
        patch("custom_components.jaedrive.config_flow.link_start", return_value=START),
        patch("custom_components.jaedrive.config_flow.link_poll", side_effect=poll_results),
    ):
        if entry is None:
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        else:
            result = await entry.start_reauth_flow(hass)
            assert result["type"] is FlowResultType.FORM
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["description_placeholders"]["url"] == START["verificationUriComplete"]
        await hass.async_block_till_done()
        return await hass.config_entries.flow.async_configure(result["flow_id"])


async def test_link_approved(hass: HomeAssistant) -> None:
    result = await _run_flow(
        hass,
        [{"status": "pending"}, {"status": "approved", "token": "jdh_abc", "scopes": ["vehicles:read"], "accountId": ACCOUNT_ID}],
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TOKEN] == "jdh_abc"
    assert result["data"][CONF_ACCOUNT_ID] == ACCOUNT_ID
    assert result["result"].unique_id == ACCOUNT_ID


async def test_link_denied(hass: HomeAssistant) -> None:
    result = await _run_flow(hass, [{"status": "denied"}])
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "denied"


async def test_already_configured(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await _run_flow(hass, [{"status": "approved", "token": "jdh_new", "accountId": ACCOUNT_ID}])
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_token(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await _run_flow(hass, [{"status": "approved", "token": "jdh_new", "accountId": ACCOUNT_ID}], entry=config_entry)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_TOKEN] == "jdh_new"


async def test_reauth_wrong_account(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await _run_flow(hass, [{"status": "approved", "token": "jdh_x", "accountId": "other"}], entry=config_entry)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
