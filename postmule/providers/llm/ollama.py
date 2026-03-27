"""
Ollama LLM provider — stub (not yet implemented).

Ollama runs large language models locally (no API key required).
Implementation will use the Ollama REST API at http://localhost:11434.

Config example:
    llm:
      providers:
        - service: ollama
          enabled: true
          model: llama3.2
          host: http://localhost:11434
"""

from __future__ import annotations

SERVICE_KEY = "ollama"
DISPLAY_NAME = "Ollama (local)"

OLLAMA_DEFAULT_HOST = "http://localhost:11434"


class OllamaProvider:
    """
    Ollama local LLM provider.

    Not yet implemented. Configure service: ollama in config.yaml
    once this provider is available. Requires Ollama running locally.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Ollama provider is not yet implemented. "
            "Use service: gemini in config.yaml for now. "
            f"When implemented, requires Ollama running at {OLLAMA_DEFAULT_HOST}."
        )

    def classify(self, ocr_text: str, known_names: list | None = None, dry_run: bool = False):
        raise NotImplementedError("Ollama provider is not yet implemented.")

    def health_check(self):
        raise NotImplementedError("Ollama provider is not yet implemented.")
