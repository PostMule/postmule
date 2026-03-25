"""
OpenAI LLM provider — stub (not yet implemented).

Implementation will use the OpenAI Python SDK with a standard API key.
Supports GPT-4o and other chat completion models.

Config example:
    llm:
      providers:
        - service: openai
          enabled: true
          model: gpt-4o
"""

from __future__ import annotations

SERVICE_KEY = "openai"
DISPLAY_NAME = "OpenAI"


class OpenAIProvider:
    """
    OpenAI (GPT-4o, etc.) LLM provider.

    Not yet implemented. Configure service: openai in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "OpenAI provider is not yet implemented. "
            "Use service: gemini in config.yaml for now."
        )

    def classify(self, ocr_text: str, known_names: list | None = None, dry_run: bool = False):
        raise NotImplementedError("OpenAI provider is not yet implemented.")
