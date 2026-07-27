"""OpenRouter Free Models provider."""

import httpx
from loguru import logger


_OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider:
    def __init__(self, api_key: str, model: str = "google/gemini-2.0-flash-exp:free"):
        self._api_key = api_key
        self._model = model
        logger.info(f"OpenRouter initialized  model={model}")

    @property
    def name(self) -> str:
        return "OpenRouter"

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
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
                resp.raise_for_status()
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
                text = text.strip()
                if not text:
                    raise ValueError("OpenRouter returned empty response")
                logger.debug(f"OpenRouter response ({len(text)} chars)")
                return text
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter HTTP {e.response.status_code}: {e.response.text[:300]}")
            raise
        except Exception as e:
            logger.error(f"OpenRouter error: {e}")
            raise
