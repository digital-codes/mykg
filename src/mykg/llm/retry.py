from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable, TypeVar

from mykg import config as _cfg
from mykg.llm.adapter import LLMAdapter
from mykg.logging import get

if TYPE_CHECKING:
    from mykg.llm.error_gate import ErrorGate

log = get("mykg.llm.retry")

E = TypeVar("E", bound=BaseException)


def llm_complete_with_retry(
    adapter: LLMAdapter,
    system: str,
    user: str,
    context_label: str = "",
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> str:
    """Call adapter.complete(), retrying up to LLM_RETRY_MAX_RETRIES times on empty response.

    Returns the first non-empty (non-whitespace) response. If all attempts return empty,
    returns "" so callers can handle it as they would a failed parse (existing behaviour).

    max_tokens: per-call override forwarded to the adapter; None means use adapter default.
    timeout: per-call override in seconds forwarded to the adapter; None means use adapter default.
    """
    max_retries = _cfg.LLM_RETRY_MAX_RETRIES
    label = f" [{context_label}]" if context_label else ""
    for retry in range(max_retries + 1):
        raw = adapter.complete(
            system,
            user,
            context_label=context_label,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if raw.strip():
            return raw
        if retry < max_retries:
            log.warning("empty response%s — retrying (retry %d/%d)", label, retry + 1, max_retries)
        else:
            log.warning(
                "empty response%s — all %d retr%s exhausted",
                label,
                max_retries,
                "y" if max_retries == 1 else "ies",
            )
    return ""


def retry_on_rate_limit(
    fn: Callable[[], E],
    exc_type: type[E],
    provider: str,
    retry_max: int,
    base_delay: float,
    error_gate: ErrorGate | None = None,
) -> object:
    """Call fn(), retrying on rate-limit errors with exponential backoff.

    Args:
        fn: Zero-argument callable that performs the LLM call and returns its result.
        exc_type: The rate-limit exception class to catch (e.g. anthropic.RateLimitError).
        provider: Human-readable provider name used in log messages (e.g. "Anthropic").
        retry_max: Maximum number of retries (not counting the initial attempt).
        base_delay: Base sleep duration in seconds; doubles each attempt.
        error_gate: Optional shared gate; notified after all retries are exhausted.

    Returns:
        The return value of fn() on success.

    Raises:
        exc_type: After all retries are exhausted.
    """
    last_exc: BaseException | None = None
    for attempt in range(retry_max + 1):
        try:
            return fn()
        except exc_type as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt < retry_max:
                delay = base_delay * (2**attempt)
                log.warning(
                    "%s 429 rate-limit (attempt %d/%d) — retrying in %.1fs",
                    provider,
                    attempt + 1,
                    retry_max,
                    delay,
                )
                time.sleep(delay)
    if error_gate is not None:
        error_gate.record_error(last_exc)  # type: ignore[arg-type]
    raise last_exc  # type: ignore[misc]
