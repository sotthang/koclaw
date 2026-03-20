import openai

from koclaw.providers.openai import OpenAIProvider

DEFAULT_MODEL = "gpt-4o"


class AzureOpenAIProvider(OpenAIProvider):
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        api_version: str = "2025-03-01-preview",
        model: str = DEFAULT_MODEL,
    ):
        self._client = openai.AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        self._model = model
