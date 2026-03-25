"""
Anthropic Claude LLM provider — stub (not yet implemented).

Implementation will use the Anthropic Python SDK with a standard API key.
Supports Claude 3.5 Sonnet and other models.

Config example:
    llm:
      providers:
        - service: anthropic
          enabled: true
          model: claude-sonnet-4-6
"""

from __future__ import annotations

SERVICE_KEY = "anthropic"
DISPLAY_NAME = "Anthropic Claude"


class AnthropicProvider:
    """
    Anthropic Claude LLM provider.

    Not yet implemented. Configure service: anthropic in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Anthropic Claude provider is not yet implemented. "
            "Use service: gemini in config.yaml for now."
        )

    def classify(self, ocr_text: str, known_names: list | None = None, dry_run: bool = False):
        raise NotImplementedError("Anthropic Claude provider is not yet implemented.")
