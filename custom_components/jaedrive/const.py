"""JaeDrive integration constants."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "jaedrive"

DEFAULT_BASE_URL: Final = "https://jaedrive.com"
CONF_BASE_URL: Final = "base_url"
CONF_TOKEN: Final = "token"
CONF_ACCOUNT_ID: Final = "account_id"
CONF_SCOPES: Final = "scopes"

SCOPE_LOCATION: Final = "location:read"

# The SSE stream carries the updates; polling is only a fallback.
FALLBACK_INTERVAL: Final = timedelta(hours=1)
STREAM_BACKOFF_MIN: Final = 5
STREAM_BACKOFF_MAX: Final = 300
# No data (not even the ": ping" every 30 s) for this long = dead connection.
STREAM_READ_TIMEOUT: Final = 150

PLANS_URL: Final = "https://jaedrive.com/plans"
ISSUE_SUBSCRIPTION: Final = "subscription_expired"
SIGNAL_TRIP_ENDED: Final = "jaedrive_trip_ended_{}"

# Where the cards and the dashboard strategy (frontend/) are served.
FRONTEND_URL: Final = "/jaedrive_static"
