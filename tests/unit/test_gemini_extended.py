"""Extended tests for postmule.providers.llm.gemini (coverage of _parse_response, edge cases)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from postmule.providers.llm.gemini import ClassificationResult, GeminiProvider, _safe_float


class TestSafeFloat:
    def test_converts_float(self):
        assert _safe_float(3.14) == 3.14

    def test_converts_int(self):
        assert _safe_float(10) == 10.0

    def test_converts_string(self):
        assert _safe_float("42.5") == 42.5

    def test_returns_none_for_none(self):
        assert _safe_float(None) is None

    def test_returns_none_for_invalid_string(self):
        assert _safe_float("abc") is None

    def test_returns_none_for_dict(self):
        assert _safe_float({}) is None


class TestGeminiProviderDryRun:
    def test_dry_run_returns_needs_review(self):
        provider = GeminiProvider(api_key="test-key")
        result = provider.classify("some text", dry_run=True)
        assert result.category == "NeedsReview"
        assert result.confidence == 0.0
        assert "dry-run" in result.summary

    def test_dry_run_does_not_call_api(self):
        provider = GeminiProvider(api_key="test-key")
        with patch.object(provider, "_get_client") as mock_client:
            provider.classify("text", dry_run=True)
            mock_client.assert_not_called()


class TestGeminiParseResponse:
    def setup_method(self):
        self.provider = GeminiProvider(api_key="test")

    def test_valid_json_parsed(self):
        raw = json.dumps({
            "category": "Bill",
            "confidence": 0.95,
            "sender": "ATT",
            "recipients": ["Alice"],
            "amount_due": 94.0,
            "due_date": "2025-04-05",
            "account_number": "1234",
            "summary": "Monthly bill",
        })
        result = self.provider._parse_response(raw, tokens_used=100)
        assert result.category == "Bill"
        assert result.confidence == 0.95
        assert result.sender == "ATT"
        assert result.amount_due == 94.0

    def test_markdown_code_fence_stripped(self):
        raw = "```json\n{\"category\":\"Notice\",\"confidence\":0.9,\"sender\":\"IRS\",\"recipients\":[],\"amount_due\":null,\"due_date\":null,\"account_number\":null,\"summary\":\"tax doc\"}\n```"
        result = self.provider._parse_response(raw, tokens_used=50)
        assert result.category == "Notice"

    def test_invalid_json_falls_back_to_needs_review(self):
        result = self.provider._parse_response("this is not json", tokens_used=50)
        assert result.category == "NeedsReview"
        assert result.confidence == 0.0

    def test_invalid_category_becomes_needs_review(self):
        raw = json.dumps({"category": "UNKNOWN", "confidence": 0.9, "sender": None,
                           "recipients": [], "amount_due": None, "due_date": None,
                           "account_number": None, "summary": ""})
        result = self.provider._parse_response(raw, tokens_used=50)
        assert result.category == "NeedsReview"

    def test_confidence_clamped_to_1(self):
        raw = json.dumps({"category": "Bill", "confidence": 5.0, "sender": None,
                           "recipients": [], "amount_due": None, "due_date": None,
                           "account_number": None, "summary": ""})
        result = self.provider._parse_response(raw, tokens_used=50)
        assert result.confidence == 1.0

    def test_confidence_clamped_to_0(self):
        raw = json.dumps({"category": "Bill", "confidence": -1.0, "sender": None,
                           "recipients": [], "amount_due": None, "due_date": None,
                           "account_number": None, "summary": ""})
        result = self.provider._parse_response(raw, tokens_used=50)
        assert result.confidence == 0.0

    def test_missing_fields_use_defaults(self):
        raw = json.dumps({"category": "Junk"})
        result = self.provider._parse_response(raw, tokens_used=10)
        assert result.category == "Junk"
        assert result.recipients == []
        assert result.amount_due is None


class TestGeminiClassifyWithMockedClient:
    def test_calls_safety_agent_before_api(self):
        safety = MagicMock()
        provider = GeminiProvider(api_key="key", safety_agent=safety)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "category": "Bill", "confidence": 0.9, "sender": "X",
            "recipients": [], "amount_due": 10.0, "due_date": None,
            "account_number": None, "summary": "test",
        })
        mock_response.usage_metadata.total_token_count = 100
        mock_client.generate_content.return_value = mock_response
        provider._client = mock_client

        provider.classify("some text")
        safety.check_and_record.assert_called_once()

    def test_api_error_raises_runtime_error(self):
        provider = GeminiProvider(api_key="key")
        mock_client = MagicMock()
        mock_client.generate_content.side_effect = Exception("API down")
        provider._client = mock_client

        with pytest.raises(RuntimeError, match="Gemini classification failed"):
            provider.classify("some text")

    def test_known_names_included_in_prompt(self):
        provider = GeminiProvider(api_key="key")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "category": "Bill", "confidence": 0.9, "sender": None,
            "recipients": [], "amount_due": None, "due_date": None,
            "account_number": None, "summary": "",
        })
        mock_response.usage_metadata.total_token_count = 50
        mock_client.generate_content.return_value = mock_response
        provider._client = mock_client

        provider.classify("text", known_names=["Alice", "Bob"])
        call_args = mock_client.generate_content.call_args[0][0]
        assert "Alice" in call_args
        assert "Bob" in call_args
