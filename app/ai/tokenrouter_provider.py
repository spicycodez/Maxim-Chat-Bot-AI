"""TokenRouter provider — OpenAI-compatible API at api.tokenrouter.com/v1."""

import httpx
from loguru import logger


_TOKENROUTER_BASE = "https://api.tokenrouter.com/v1/chat/completions"


class TokenRouterProvider:
    """OpenAI-compatible provider for tokenrouter.com."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self._api_key = api_key
        self._model = model
        logger.info(f"TokenRouter initialized  model={model}")

    @property
    def name(self) -> str:
        return "TokenRouter"

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    _TOKENROUTER_BASE,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 2048,
                    },
                )

                # Handle 429 — rate limit (per-provider, not account-wide like OpenRouter)
                if resp.status_code == 429:
                    logger.warning(f"TokenRouter HTTP 429 rate limit for {self._model}")
                    resp.raise_for_status()

                resp.raise_for_status()
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                text = text.strip()
                if not text:
                    raise ValueError("TokenRouter returned empty response")
                logger.debug(f"TokenRouter response ({len(text)} chars) via {self._model}")
                return text
        except httpx.HTTPStatusError as e:
            logger.error(f"TokenRouter HTTP {e.response.status_code} for {self._model}: {e.response.text[:300]}")
            raise
        except Exception as e:
            logger.error(f"TokenRouter error for {self._model}: {e}")
            raise
