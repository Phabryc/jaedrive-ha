"""Costanti dell'integrazione JaeDrive."""

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

# Lo stream SSE porta gli aggiornamenti; il polling resta solo come riserva.
FALLBACK_INTERVAL: Final = timedelta(hours=1)
STREAM_BACKOFF_MIN: Final = 5
STREAM_BACKOFF_MAX: Final = 300
# Nessun dato (nemmeno il ": ping" ogni 60 s) per questo tempo = connessione morta.
STREAM_READ_TIMEOUT: Final = 150

PLANS_URL: Final = "https://jaedrive.com/plans"
ISSUE_SUBSCRIPTION: Final = "subscription_expired"
SIGNAL_TRIP_ENDED: Final = "jaedrive_trip_ended_{}"
