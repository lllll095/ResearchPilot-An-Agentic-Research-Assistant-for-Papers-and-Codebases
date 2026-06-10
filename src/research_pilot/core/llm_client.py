from typing import Any

from research_pilot.config import settings


class OpenAICompatibleLLMClient:
    """A small wrapper around an OpenAI-compatible chat completion API.

    This class only does one thing:
    - send messages to the model
    - return the raw text output

    It does not know anything about tools or agent loops.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        model: str,
        temperature: float = 0.0,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is not installed. "
                "Please run: pip install -e \".[llm]\""
            ) from exc

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Please create a .env file and set OPENAI_API_KEY."
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = model
        self.temperature = temperature

    @classmethod
    def from_settings(cls) -> "OpenAICompatibleLLMClient":
        return cls(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            temperature=0.0,
        )

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Call the chat completion API and return the assistant text."""

        response: Any = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )

        content = response.choices[0].message.content
        return content or ""