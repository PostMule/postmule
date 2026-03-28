"""
Ollama LLM provider — uses the Ollama REST API (no API key required).

Ollama runs large language models locally. No data leaves the machine.

Config example:
    llm:
      providers:
        - service: ollama
          enabled: true
          model: llama3.2
          host: http://localhost:11434
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from postmule.providers.llm.base import ClassificationResult

log = logging.getLogger("postmule.llm.ollama")

SERVICE_KEY = "ollama"
DISPLAY_NAME = "Ollama (local)"

OLLAMA_DEFAULT_HOST = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.2"
_DEFAULT_TIMEOUT = 120  # seconds — local inference can be slow

_CLASSIFY_PROMPT = """\
You are a mail classification assistant. Given the OCR text of a physical mail item,
classify it and extract key data.

Respond with ONLY a valid JSON object — no markdown, no explanation. Use this exact schema:
{
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
}

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


class OllamaProvider:
    """
    Ollama local LLM provider.

    Uses the Ollama REST API at http://localhost:11434 (or configured host).
    No API key required — all inference runs on the local machine.

    Args:
        host:         Ollama server URL (default: http://localhost:11434).
        safety_agent: APISafetyAgent to check/record usage before each call.
        model:        Model name (default: llama3.2).
        timeout:      HTTP timeout in seconds (default: 120).
    """

    def __init__(
        self,
        host: str = OLLAMA_DEFAULT_HOST,
        safety_agent=None,
        model: str = _DEFAULT_MODEL,
        timeout: int = _DEFAULT_TIMEOUT,
        # api_key is accepted but ignored — Ollama needs no auth
        api_key: str | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.safety_agent = safety_agent
        self.model_name = model
        self.timeout = timeout

    def health_check(self):
        """
        Return a HealthResult.

        Checks:
        1. Ollama server is reachable at the configured host.
        2. The configured model is available (pulled).
        """
        from postmule.providers import HealthResult
        try:
            import requests  # type: ignore[import]
        except ImportError:
            return HealthResult(ok=False, status="error", message="requests is not installed")

        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
            tags = resp.json()
        except Exception as exc:
            return HealthResult(
                ok=False,
                status="error",
                message=f"Ollama server not reachable at {self.host}: {exc}",
            )

        models = [m.get("name", "") for m in tags.get("models", [])]
        # Ollama model names may include a tag (e.g., "llama3.2:latest")
        model_base = self.model_name.split(":")[0]
        available = any(m.split(":")[0] == model_base for m in models)

        if not available:
            pulled = ", ".join(m.split(":")[0] for m in models) or "none"
            return HealthResult(
                ok=False,
                status="warn",
                message=(
                    f"Model '{self.model_name}' not found on Ollama server. "
                    f"Available: {pulled}. Run: ollama pull {self.model_name}"
                ),
            )

        return HealthResult(
            ok=True,
            status="ok",
            message=f"Ollama connected — model '{self.model_name}' available",
        )

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

        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError(
                "requests is not installed.\n"
                "Run: pip install requests"
            )

        names_str = ", ".join(known_names) if known_names else "unknown"
        prompt = _CLASSIFY_PROMPT.format(
            known_names=names_str,
            ocr_text=ocr_text[:100_000],
        )

        # Rough token estimate for safety agent
        estimated_tokens = len(prompt) // 4 + 200

        if self.safety_agent:
            self.safety_agent.check_and_record(tokens=estimated_tokens)

        log.debug(f"Sending classification request to Ollama ({self.model_name})")

        try:
            resp = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["message"]["content"]
            # Ollama doesn't report token counts in /api/chat by default
            tokens_used = data.get("eval_count", estimated_tokens) + data.get("prompt_eval_count", 0)
        except Exception as exc:
            log.error(f"Ollama API call failed: {exc}")
            raise RuntimeError(
                f"Ollama classification failed: {exc}\n"
                f"Ensure Ollama is running at {self.host} and model '{self.model_name}' is pulled."
            ) from exc

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
