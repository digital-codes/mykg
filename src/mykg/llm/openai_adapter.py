from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import openai

from mykg.llm.adapter import LLMAdapter
from mykg.llm.retry import retry_on_rate_limit
from mykg.logging import record_llm_call

if TYPE_CHECKING:
    from mykg.llm.error_gate import ErrorGate


class OpenAIAdapter(LLMAdapter):
    def __init__(
        self,
        model: str,
        max_tokens: int,
        timeout: int,
        api_key: str | None = None,
        base_url: str | None = None,
        retry_429_max: int = 5,
        retry_429_base_delay: float = 2.0,
        error_gate: ErrorGate | None = None,
    ):
        self._model = model
        self._max_tokens = max_tokens
        self._retry_429_max = retry_429_max
        self._retry_429_base_delay = retry_429_base_delay
        self._error_gate = error_gate

        if api_key is None:
            api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is required — set OPENAI_API_KEY in your environment "
                "or supply api_key in mykg_config.yaml"
            )

        self._timeout = timeout
        self._base_url = base_url
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def endpoint_label(self) -> str:
        url = self._base_url or "https://api.openai.com"
        return f"openai / {self._model} @ {url}"

    def complete(
        self,
        system: str,
        user: str,
        context_label: str = "",
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> str:
        effective_max_tokens = max_tokens if max_tokens is not None else self._max_tokens
        effective_timeout = timeout if timeout is not None else self._timeout

        def _call() -> str:
            t0 = time.monotonic()
            resp = self._client.chat.completions.create(
                model=self._model,
                max_tokens=effective_max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout=effective_timeout,
            )
            usage = resp.usage
            raw = resp.choices[0].message.content or "" if resp.choices else ""
            record_llm_call(
                provider="openai",
                model=self._model,
                context_label=context_label,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                duration_s=time.monotonic() - t0,
                system_prompt=system,
                user_prompt=user,
                raw_response=raw,
            )
            return self.strip_code_fences(raw)

        return retry_on_rate_limit(  # type: ignore[return-value]
            _call,
            openai.RateLimitError,
            "OpenAI",
            self._retry_429_max,
            self._retry_429_base_delay,
            error_gate=self._error_gate,
        )
