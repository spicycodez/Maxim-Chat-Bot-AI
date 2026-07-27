"""Google Gemini Free API provider."""

import google.generativeai as genai
from loguru import logger


class GeminiProvider:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._model_name = model
        genai.configure(api_key=api_key)
        self._client = genai.GenerativeModel(model_name=model)
        logger.info(f"Gemini initialized  model={model}")

    @property
    def name(self) -> str:
        return "Gemini"

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        try:
            if system_prompt:
                model_with_sys = genai.GenerativeModel(
                    model_name=self._model_name,
                    system_instruction=system_prompt,
                )
                resp = await model_with_sys.generate_content_async(prompt)
            else:
                resp = await self._client.generate_content_async(prompt)

            text = resp.text.strip()
            logger.debug(f"Gemini response ({len(text)} chars)")
            return text
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            raise
