from __future__ import annotations

import logging

from openai import AzureOpenAI, OpenAI

from app.config import Settings, settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around Azure OpenAI / OpenAI chat completions."""

    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or settings
        if not self.config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for chat completions.")

        api_type = self.config.openai_api_type.lower()
        if api_type == "azure":
            if not self.config.openai_api_base:
                raise ValueError("OPENAI_API_BASE is required for Azure chat.")
            if not self.config.chat_model:
                raise ValueError("OPENAI_DEPLOYMENT_NAME is required for Azure chat.")
            self._client: AzureOpenAI | OpenAI = AzureOpenAI(
                api_key=self.config.openai_api_key,
                api_version=self.config.openai_api_version,
                azure_endpoint=self.config.openai_api_base,
            )
        else:
            self._client = OpenAI(
                api_key=self.config.openai_api_key,
                base_url=self.config.openai_api_base or None,
            )
        self._model = self.config.chat_model
        logger.info("LLM client ready (type=%s, model=%s)", api_type, self._model)

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        logger.debug("Calling chat completion model=%s", self._model)
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=self.config.rag_temperature,
            max_tokens=self.config.rag_max_output_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content if response.choices else None
        if not content or not content.strip():
            raise RuntimeError("LLM returned an empty response.")
        return content.strip()
