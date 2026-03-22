"""
API Safety Agent — tracks usage, enforces hard limits, warns at thresholds.

Persists daily usage counters to a JSON file so limits survive process restarts.
Call check_and_record() before every API call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

log = logging.getLogger("postmule.api_safety")


class APILimitError(Exception):
    """Raised when a hard API limit would be exceeded."""


@dataclass
class ProviderLimits:
    daily_request_limit: int = 1400
    daily_token_limit: int = 900_000
    warn_at_percent: float = 0.80


@dataclass
class DayUsage:
    date: str = ""
    requests: int = 0
    tokens: int = 0
    estimated_cost_usd: float = 0.0


class APISafetyAgent:
    """
    Tracks daily API usage for a named provider and enforces limits.

    Usage:
        agent = APISafetyAgent("gemini", limits, state_file)
        agent.check_and_record(tokens=1200)  # raises if limit exceeded
    """

    def __init__(
        self,
        provider: str,
        limits: ProviderLimits,
        state_file: Path,
        monthly_budget_usd: float = 0.0,
    ) -> None:
        self.provider = provider
        self.limits = limits
        self.state_file = state_file
        self.monthly_budget_usd = monthly_budget_usd
        self._usage = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_and_record(
        self,
        tokens: int = 0,
        cost_usd: float = 0.0,
        dry_run: bool = False,
    ) -> None:
        """
        Check whether making an API call with *tokens* tokens would exceed limits.
        If safe, record the usage. If over limit, raise APILimitError.

        Args:
            tokens:   Estimated tokens for this call.
            cost_usd: Estimated cost for this call.
            dry_run:  If True, check limits but don't persist usage.

        Raises:
            APILimitError: If a hard limit would be exceeded.
        """
        self._maybe_reset_for_new_day()
        usage = self._usage

        new_requests = usage.requests + 1
        new_tokens = usage.tokens + tokens
        new_cost = usage.estimated_cost_usd + cost_usd

        # Hard limits
        if new_requests > self.limits.daily_request_limit:
            raise APILimitError(
                f"{self.provider} daily request limit reached "
                f"({self.limits.daily_request_limit} req/day).\n"
                "PostMule will resume processing tomorrow.\n"
                "To increase this limit, edit api_safety in config.yaml."
            )

        if new_tokens > self.limits.daily_token_limit:
            raise APILimitError(
                f"{self.provider} daily token limit reached "
                f"({self.limits.daily_token_limit:,} tokens/day).\n"
                "PostMule will resume processing tomorrow."
            )

        if self.monthly_budget_usd > 0 and new_cost > self.monthly_budget_usd:
            raise APILimitError(
                f"Monthly cost budget exceeded "
                f"(${self.monthly_budget_usd:.2f}/month limit).\n"
                "Adjust monthly_cost_budget_usd in config.yaml."
            )

        # Warnings
        req_pct = new_requests / self.limits.daily_request_limit
        tok_pct = new_tokens / self.limits.daily_token_limit if self.limits.daily_token_limit else 0

        if req_pct >= self.limits.warn_at_percent:
            log.warning(
                f"{self.provider}: {req_pct:.0%} of daily request limit used "
                f"({new_requests}/{self.limits.daily_request_limit})"
            )
        if tok_pct >= self.limits.warn_at_percent:
            log.warning(
                f"{self.provider}: {tok_pct:.0%} of daily token limit used "
                f"({new_tokens:,}/{self.limits.daily_token_limit:,})"
            )

        if not dry_run:
            usage.requests = new_requests
            usage.tokens = new_tokens
            usage.estimated_cost_usd = new_cost
            self._save()

    def summary(self) -> dict[str, Any]:
        """Return current day's usage as a dict (for inclusion in daily email)."""
        self._maybe_reset_for_new_day()
        u = self._usage
        return {
            "provider": self.provider,
            "date": u.date,
            "requests": u.requests,
            "request_limit": self.limits.daily_request_limit,
            "tokens": u.tokens,
            "token_limit": self.limits.daily_token_limit,
            "estimated_cost_usd": round(u.estimated_cost_usd, 4),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> DayUsage:
        if not self.state_file.exists():
            return DayUsage(date=date.today().isoformat())
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            return DayUsage(**raw)
        except Exception:
            return DayUsage(date=date.today().isoformat())

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "date": self._usage.date,
            "requests": self._usage.requests,
            "tokens": self._usage.tokens,
            "estimated_cost_usd": self._usage.estimated_cost_usd,
        }
        self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _maybe_reset_for_new_day(self) -> None:
        today = date.today().isoformat()
        if self._usage.date != today:
            log.debug(f"{self.provider}: new day — resetting usage counters")
            self._usage = DayUsage(date=today)
            self._save()


def build_safety_agent(config, provider_name: str, state_dir: Path) -> APISafetyAgent:
    """Convenience factory: build agent from config dict for any LLM provider."""
    safety_cfg = config.get("api_safety") or {}
    limits = ProviderLimits(
        daily_request_limit=safety_cfg.get("daily_request_limit", 1400),
        daily_token_limit=safety_cfg.get("daily_token_limit", 900_000),
        warn_at_percent=safety_cfg.get("warn_at_percent", 80) / 100,
    )
    monthly_budget = safety_cfg.get("monthly_cost_budget_usd", 0.0)
    return APISafetyAgent(
        provider=provider_name,
        limits=limits,
        state_file=state_dir / f"api_usage_{provider_name}.json",
        monthly_budget_usd=float(monthly_budget),
    )
