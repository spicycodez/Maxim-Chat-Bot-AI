"""OpenRouter Free Models provider."""

import time
import httpx
from loguru import logger


_OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"

# Module-level rate limit cache — shared across all provider instances
# because 429 is account-wide (free-models-per-day), not per-model.
_rate_limit_reset: float = 0.0   # epoch seconds when rate limit resets
_rate_limit_logged: bool = False  # avoid spamming the same warning


def is_rate_limited() -> bool:
    """Check if we're currently rate-limited account-wide."""
    global _rate_limit_reset, _rate_limit_logged
    if _rate_limit_reset > time.time():
        return True
    if _rate_limit_reset > 0:
        # Reset time passed, clear it
        _rate_limit_reset = 0.0
        _rate_limit_logged = False
        logger.info("OpenRouter rate limit period expired, resuming requests")
    return False


class OpenRouterProvider:
    def __init__(self, api_key: str, model: str = "nvidia/nemotron-3-super-120b-a12b:free"):
        self._api_key = api_key
        self._model = model
        logger.info(f"OpenRouter initialized  model={model}")

    @property
    def name(self) -> str:
        return "OpenRouter"

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        global _rate_limit_reset, _rate_limit_logged

        # Short-circuit if account is rate-limited
        if is_rate_limited():
            remaining = _rate_limit_reset - time.time()
            if not _rate_limit_logged:
                logger.warning(f"OpenRouter rate limited, skipping ({remaining:.0f}s remaining)")
                _rate_limit_logged = True
            raise RateLimitedError(f"Account rate-limited, resets in {remaining:.0f}s")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    _OPENROUTER_BASE,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/persona-ai-assistant",
                        "X-Title": "Persona AI Assistant",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 2048,
                    },
                )

                # Handle 429 — account-wide rate limit
                if resp.status_code == 429:
                    reset_header = resp.headers.get("X-RateLimit-Reset", "")
                    if reset_header:
                        try:
                            _rate_limit_reset = float(reset_header) / 1000.0  # ms -> seconds
                        except (ValueError, TypeError):
                            # Default: 24 hours from now
                            _rate_limit_reset = time.time() + 86400
                    else:
                        _rate_limit_reset = time.time() + 3600  # default 1h
                    _rate_limit_logged = False
                    remaining_h = (_rate_limit_reset - time.time()) / 3600
                    logger.error(f"OpenRouter HTTP 429: free-models-per-day rate limit hit. Resets in {remaining_h:.1f}h")
                    raise RateLimitedError(f"Rate limited, resets in {remaining_h:.1f}h")

                resp.raise_for_status()
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                text = text.strip()
                if not text:
                    raise ValueError("OpenRouter returned empty response")
                logger.debug(f"OpenRouter response ({len(text)} chars) via {self._model}")
                return text
        except RateLimitedError:
            raise  # re-raise as-is, don't wrap
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter HTTP {e.response.status_code} for {self._model}: {e.response.text[:300]}")
            raise
        except Exception as e:
            logger.error(f"OpenRouter error for {self._model}: {e}")
            raise


class RateLimitedError(Exception):
    """Raised when the OpenRouter account hits the free-models-per-day limit."""
    pass
