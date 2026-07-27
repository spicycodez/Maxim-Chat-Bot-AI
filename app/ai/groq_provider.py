"""Groq Free API provider."""

import httpx
from loguru import logger


_GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self._api_key = api_key
        self._model = model
        logger.info(f"Groq initialized  model={model}")

    @property
    def name(self) -> str:
        return "Groq"

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    _GROQ_BASE,
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
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                logger.debug(f"Groq response ({len(text)} chars)")
                return text
        except httpx.HTTPStatusError as e:
            logger.error(f"Groq HTTP {e.response.status_code}: {e.response.text[:300]}")
            raise
        except Exception as e:
            logger.error(f"Groq error: {e}")
            raise
