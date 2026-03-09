from koclaw.providers.openai import OpenAIProvider

DEFAULT_MODEL = "llama3"
DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(OpenAIProvider):
    """Ollama는 OpenAI 호환 API를 제공하므로 OpenAIProvider를 재사용"""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
    ):
        super().__init__(
            api_key="ollama",
            model=model,
            base_url=base_url,
        )
