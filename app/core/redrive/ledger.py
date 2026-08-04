"""
DB-backed per-provider usage ledger — mirrors peripateticware's
mt_fallback.py UsageLedger (budget-aware fallback across MT providers),
persisted in Postgres instead of a JSON file since Phase 1 already put this
system there.

Default limits are placeholders. Real free-tier/contracted allowances depend
on the operator's own account and provider, not something this system can
know in advance — override via the PROVIDER_USAGE_LIMITS env var, JSON:
  {"deepl": {"scope": "lifetime", "limit": 500000}, "google": {"scope": "month", "limit": 500000}}
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

from app.core.database import get_db

_DEFAULT_LIMITS: Dict[str, Dict[str, Any]] = {
    "deepl": {"scope": "lifetime", "limit": 500_000},
    "google": {"scope": "month", "limit": 500_000},
    "anthropic": {"scope": "month", "limit": 10_000_000},
    "mock": {"scope": "month", "limit": 10_000_000},
}
_FALLBACK_LIMIT: Dict[str, Any] = {"scope": "month", "limit": 10_000_000}


def _load_limits() -> Dict[str, Dict[str, Any]]:
    raw = os.getenv("PROVIDER_USAGE_LIMITS")
    if not raw:
        return _DEFAULT_LIMITS
    try:
        overrides = json.loads(raw)
        return {**_DEFAULT_LIMITS, **overrides}
    except json.JSONDecodeError:
        return _DEFAULT_LIMITS


def _period_for(scope: str) -> str:
    return "lifetime" if scope == "lifetime" else datetime.utcnow().strftime("%Y-%m")


class UsageLedger:
    def __init__(self):
        self._limits = _load_limits()

    def _config(self, provider: str) -> Dict[str, Any]:
        return self._limits.get(provider, _FALLBACK_LIMIT)

    async def status(self, provider: str) -> Dict[str, Any]:
        cfg = self._config(provider)
        period = _period_for(cfg["scope"])
        db = get_db()
        return await db.get_or_create_ledger_row(provider, period, cfg["scope"], cfg["limit"])

    async def can_spend(self, provider: str, chars: int) -> bool:
        row = await self.status(provider)
        return row["used_chars"] + chars <= row["limit_chars"]

    async def record(self, provider: str, chars: int) -> None:
        cfg = self._config(provider)
        period = _period_for(cfg["scope"])
        db = get_db()
        await db.get_or_create_ledger_row(provider, period, cfg["scope"], cfg["limit"])
        await db.record_usage(provider, period, chars)
