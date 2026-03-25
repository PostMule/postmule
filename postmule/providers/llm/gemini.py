"""
Gemini LLM provider — wraps google-generativeai for PostMule classification.

Responsibilities:
  - Send classification prompts to Gemini 1.5 Flash
  - Return structured JSON responses
  - Report token usage back to the API safety agent
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from postmule.providers.llm.base import ClassificationResult

log = logging.getLogger("postmule.llm.gemini")

_MODEL = "gemini-1.5-flash"

# Prompt template for mail classification
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


class GeminiProvider:
    """
    Gemini 1.5 Flash LLM provider.

    Args:
        api_key:      Gemini API key from credentials.
        safety_agent: APISafetyAgent to check/record usage before each call.
        model:        Model name (default: gemini-1.5-flash).
    """

    def __init__(self, api_key: str, safety_agent=None, model: str = _MODEL) -> None:
        self.api_key = api_key
        self.safety_agent = safety_agent
        self.model_name = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import google.generativeai as genai  # type: ignore[import]
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.model_name)
            except ImportError:
                raise RuntimeError(
                    "google-generativeai is not installed.\n"
                    "Run: pip install google-generativeai"
                )
        return self._client

    def classify(
        self,
        ocr_text: str,
        known_names: list[str] | None = None,
        dry_run: bool = False,
    ) -> ClassificationResult:
        """
        Classify a mail item from its OCR text.

        Args:
            ocr_text:    Full OCR text of the mail item.
            known_names: List of known household entity names for context.
            dry_run:     If True, return a placeholder result without calling API.

        Returns:
            ClassificationResult with category, confidence, extracted data.
        """
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
            ocr_text=ocr_text[:100_000],  # cap well below Gemini 1M token limit
        )

        # Estimate tokens (rough: 1 token per 4 chars)
        estimated_tokens = len(prompt) // 4 + 200

        if self.safety_agent:
            self.safety_agent.check_and_record(tokens=estimated_tokens)

        log.debug(f"Sending classification request (~{estimated_tokens} tokens estimated)")
        client = self._get_client()

        try:
            response = client.generate_content(prompt)
            raw = response.text
            tokens_used = getattr(response.usage_metadata, "total_token_count", estimated_tokens)
        except Exception as exc:
            log.error(f"Gemini API call failed: {exc}")
            raise RuntimeError(
                f"Gemini classification failed: {exc}\n"
                "Check your API key and network connection."
            ) from exc

        # Correct the token count if actual usage exceeded the pre-call estimate
        if self.safety_agent and tokens_used > estimated_tokens:
            self.safety_agent.record_additional_tokens(tokens_used - estimated_tokens)

        return self._parse_response(raw, tokens_used)

    def _parse_response(self, raw: str, tokens_used: int) -> ClassificationResult:
        """Parse the JSON response from Gemini."""
        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning(f"Gemini returned non-JSON response, falling back to NeedsReview. Raw: {raw[:200]}")
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

        confidence = float(data.get("confidence", 0.0))
        # Cap confidence at 1.0, treat invalid as 0
        confidence = max(0.0, min(1.0, confidence))

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
