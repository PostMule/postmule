"""Unit tests for postmule.core.api_safety."""

import json
from pathlib import Path

import pytest

from postmule.core.api_safety import APISafetyAgent, APILimitError, ProviderLimits


@pytest.fixture
def limits():
    return ProviderLimits(daily_request_limit=10, daily_token_limit=1000, warn_at_percent=0.80)


@pytest.fixture
def agent(tmp_path, limits):
    return APISafetyAgent("gemini", limits, tmp_path / "usage.json")


class TestAPISafetyAgent:
    def test_records_usage(self, agent, tmp_path):
        agent.check_and_record(tokens=100)
        assert agent._usage.requests == 1
        assert agent._usage.tokens == 100

    def test_raises_on_request_limit(self, agent):
        for _ in range(10):
            agent.check_and_record(tokens=1)
        with pytest.raises(APILimitError, match="request limit"):
            agent.check_and_record(tokens=1)

    def test_raises_on_token_limit(self, agent):
        agent.check_and_record(tokens=999)
        with pytest.raises(APILimitError, match="token limit"):
            agent.check_and_record(tokens=2)

    def test_dry_run_does_not_persist(self, agent):
        agent.check_and_record(tokens=100, dry_run=True)
        assert agent._usage.requests == 0

    def test_persists_to_file(self, agent, tmp_path):
        agent.check_and_record(tokens=200)
        data = json.loads((tmp_path / "usage.json").read_text())
        assert data["requests"] == 1
        assert data["tokens"] == 200

    def test_resets_on_new_day(self, agent):
        agent.check_and_record(tokens=100)
        assert agent._usage.requests == 1
        # Simulate a new day
        agent._usage.date = "2000-01-01"
        agent._maybe_reset_for_new_day()
        assert agent._usage.requests == 0

    def test_monthly_budget_limit(self, tmp_path, limits):
        agent = APISafetyAgent("gemini", limits, tmp_path / "usage.json", monthly_budget_usd=0.01)
        with pytest.raises(APILimitError, match="budget"):
            agent.check_and_record(tokens=1, cost_usd=0.02)

    def test_summary(self, agent):
        agent.check_and_record(tokens=500)
        summary = agent.summary()
        assert summary["provider"] == "gemini"
        assert summary["requests"] == 1
        assert summary["tokens"] == 500
