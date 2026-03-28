"""
Anthropic Claude LLM provider — wraps the anthropic Python SDK.

Config example:
    llm:
      providers:
        - service: anthropic
          enabled: true
          model: claude-haiku-4-5-20251001
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from postmule.providers.llm.base import ClassificationResult

log = logging.getLogger("postmule.llm.anthropic")

SERVICE_KEY = "anthropic"
DISPLAY_NAME = "Anthropic Claude"

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_DEFAULT_MAX_TOKENS = 1024

_CLASSIFY_PROMPT = """\
You are a mail classification assistant. Given the OCR text of a physical mail item,
classify it and extract key data.

Respond with ONLY a valid JSON object — no markdown, no explanation. Use this exact schema:
{{
  "category": "<Bill|Notice|ForwardToMe|Personal|Junk|NeedsReview>",
  "confidence": <0.0-1.0>,
  "sender": "<company or person name, or null>",
  "recipients": ["<name1>", "<name2>"],
  "amount_due": <float or null>,
  "due_date": "<YYYY-MM-DD or null>",
  "account_number": "<last 4 digits only, or null>",
  "summary": "<one sentence description>",
  "statement_date": "<YYYY-MM-DD or null — the billing cycle/statement date, if different from due_date>",
  "ach_descriptor": "<ACH/bank descriptor string as it would appear on a bank statement, or null>"
}}

Category definitions:
- Bill: invoice, statement with amount due, payment demand
- Notice: informational letter, EOB, tax document, statement (no payment due)
- ForwardToMe: physical item of value (credit card, debit card, check, gift card,
  ticket, passport, key, anything unusual that must be physically forwarded)
- Personal: greeting card, personal letter
- Junk: marketing, advertisement, solicitation
- NeedsReview: unclear or insufficient text to classify confidently

Known recipient names: {known_names}

Mail OCR text:
---
{ocr_text}
---
"""


class AnthropicProvider:
    """
    Anthropic Claude LLM provider.

    Args:
        api_key:      Anthropic API key from credentials.
        safety_agent: APISafetyAgent to check/record usage before each call.
        model:        Model name (default: claude-haiku-4-5-20251001).
        max_tokens:   Max output tokens (default: 1024).
    """

    def __init__(
        self,
        api_key: str,
        safety_agent=None,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self.api_key = api_key
        self.safety_agent = safety_agent
        self.model_name = model
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic  # type: ignore[import]
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise RuntimeError(
                    "anthropic is not installed.\n"
                    "Run: pip install anthropic"
                )
        return self._client

    def health_check(self):
        """Return a HealthResult indicating whether the Anthropic API key is valid."""
        from postmule.providers import HealthResult
        try:
            import anthropic  # type: ignore[import]
            client = anthropic.Anthropic(api_key=self.api_key)
            client.models.list(limit=1)
            return HealthResult(ok=True, status="ok", message=f"Anthropic connected ({self.model_name})")
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    def classify(
        self,
        ocr_text: str,
        known_names: list[str] | None = None,
        dry_run: bool = False,
    ) -> ClassificationResult:
        if dry_run:
            return ClassificationResult(
                category="NeedsReview",
                confidence=0.0,
                sender=None,
                recipients=[],
                amount_due=None,
                due_date=None,
                account_number=None,
                summary="[dry-run — no API call made]",
                statement_date=None,
                ach_descriptor=None,
            )

        names_str = ", ".join(known_names) if known_names else "unknown"
        prompt = _CLASSIFY_PROMPT.format(
            known_names=names_str,
            ocr_text=ocr_text[:100_000],
        )

        estimated_tokens = len(prompt) // 4 + 200

        if self.safety_agent:
            self.safety_agent.check_and_record(tokens=estimated_tokens)

        log.debug(f"Sending classification request (~{estimated_tokens} tokens estimated)")
        client = self._get_client()

        try:
            message = client.messages.create(
                model=self.model_name,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text
            tokens_used = message.usage.input_tokens + message.usage.output_tokens
        except Exception as exc:
            log.error(f"Anthropic API call failed: {exc}")
            raise RuntimeError(
                f"Anthropic classification failed: {exc}\n"
                "Check your API key and network connection."
            ) from exc

        if self.safety_agent and tokens_used > estimated_tokens:
            self.safety_agent.record_additional_tokens(tokens_used - estimated_tokens)

        return _parse_response(raw, tokens_used)


def _parse_response(raw: str, tokens_used: int) -> ClassificationResult:
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning(f"Non-JSON response, falling back to NeedsReview. Raw: {raw[:200]}")
        return ClassificationResult(
            category="NeedsReview",
            confidence=0.0,
            sender=None,
            recipients=[],
            amount_due=None,
            due_date=None,
            account_number=None,
            summary="Could not parse LLM response",
            statement_date=None,
            ach_descriptor=None,
            tokens_used=tokens_used,
            raw_response=raw,
        )

    valid_categories = {"Bill", "Notice", "ForwardToMe", "Personal", "Junk", "NeedsReview"}
    category = data.get("category", "NeedsReview")
    if category not in valid_categories:
        category = "NeedsReview"

    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))

    return ClassificationResult(
        category=category,
        confidence=confidence,
        sender=data.get("sender"),
        recipients=data.get("recipients") or [],
        amount_due=_safe_float(data.get("amount_due")),
        due_date=data.get("due_date"),
        account_number=data.get("account_number"),
        summary=data.get("summary", ""),
        statement_date=data.get("statement_date"),
        ach_descriptor=data.get("ach_descriptor"),
        tokens_used=tokens_used,
        raw_response=raw,
    )


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
