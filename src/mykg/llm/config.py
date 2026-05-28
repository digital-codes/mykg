from __future__ import annotations

import os
from typing import TYPE_CHECKING

import mykg.config as _cfg
from mykg.llm.adapter import LLMAdapter

if TYPE_CHECKING:
    from mykg.llm.error_gate import ErrorGate


def load_adapter(_raw: dict | None = None, error_gate: ErrorGate | None = None) -> LLMAdapter:
    """Build an LLM adapter from mykg_config.yaml.

    mykg_config.yaml is loaded by mykg.config at import time via auto-discovery.
    _raw is an escape hatch for tests that need to supply a custom config dict.
    """
    cfg = _raw if _raw is not None else _cfg.RAW
    provider = cfg.get("provider", "")
    if not provider:
        raise ValueError('mykg_config.yaml must set "provider"')

    # llm: is a flat block for the active provider (inside the active profile).
    section = cfg.get("llm", {})

    if provider == "ollama":
        from mykg.llm.ollama_adapter import OllamaAdapter

        return OllamaAdapter(
            model=section["model"],
            base_url=section["base_url"],
            timeout=section["timeout"],
            stream=section["stream"],
            max_tokens=section["max_output_tokens"],
            retry_429_max=section.get("retry_429_max", _cfg.LLM_RETRY_429_MAX),
            retry_429_base_delay=section.get("retry_429_base_delay", _cfg.LLM_RETRY_429_BASE_DELAY),
            error_gate=error_gate,
        )

    if provider == "anthropic":
        from mykg.llm.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(
            model=section["model"],
            max_tokens=section["max_output_tokens"],
            timeout=section["timeout"],
            base_url=section.get("base_url") or os.environ.get("ANTHROPIC_BASE_URL") or None,
            api_key=(
                section.get("api_key")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_API_KEY")
            ),
            retry_429_max=section.get("retry_429_max", _cfg.LLM_RETRY_429_MAX),
            retry_429_base_delay=section.get("retry_429_base_delay", _cfg.LLM_RETRY_429_BASE_DELAY),
            error_gate=error_gate,
        )

    if provider == "openrouter":
        from mykg.llm.openrouter_adapter import OpenRouterAdapter

        return OpenRouterAdapter(
            model=section["model"],
            max_tokens=section["max_output_tokens"],
            timeout=section["timeout"],
            api_key=(
                section.get("api_key")
                or os.environ.get("OPENROUTER_AUTH_TOKEN")
                or os.environ.get("OPENROUTER_API_KEY")
            ),
            base_url=section.get("base_url") or None,
            retry_429_max=section.get("retry_429_max", _cfg.LLM_RETRY_429_MAX),
            retry_429_base_delay=section.get("retry_429_base_delay", _cfg.LLM_RETRY_429_BASE_DELAY),
            error_gate=error_gate,
        )

    if provider == "openai":
        from mykg.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(
            model=section["model"],
            max_tokens=section["max_output_tokens"],
            timeout=section["timeout"],
            api_key=section.get("api_key") or os.environ.get("OPENAI_API_KEY"),
            base_url=section.get("base_url") or None,
            retry_429_max=section.get("retry_429_max", _cfg.LLM_RETRY_429_MAX),
            retry_429_base_delay=section.get("retry_429_base_delay", _cfg.LLM_RETRY_429_BASE_DELAY),
            error_gate=error_gate,
        )

    if provider == "claude-cli":
        from mykg.llm.claude_cli_adapter import ClaudeCLIAdapter

        return ClaudeCLIAdapter(
            max_tokens=section["max_output_tokens"],
            timeout=section["timeout"],
            model=section.get("model", "auto"),
            effort=section.get("effort", "auto"),
            error_gate=error_gate,
        )

    raise ValueError(f"Unknown provider in mykg_config.yaml: {provider!r}")
