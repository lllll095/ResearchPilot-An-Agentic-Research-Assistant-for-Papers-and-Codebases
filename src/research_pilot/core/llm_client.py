import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from research_pilot.config import settings


class OpenAICompatibleLLMClient:
    """A minimal OpenAI-compatible LLM client with explicit retry support.

    Why this wrapper exists:
    - Agent loops call the LLM many times.
    - Any single transient connection error can break the whole run.
    - We want retry behavior to be visible and controllable.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        max_retries: int = 3,
        temperature: float = 0.2,
    ):
        self.model = model
        self.max_retries = max_retries
        self.temperature = temperature

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,  # Disable SDK retry; we handle retry explicitly below.
        )

    @classmethod
    def from_settings(cls) -> "OpenAICompatibleLLMClient":
        return cls(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            timeout=60.0,
            max_retries=3,
            temperature=0.2,
        )

    def complete(self, messages: list[dict[str, Any]]) -> str:
        """Call chat completions and return text content.

        Retries transient API/network failures with exponential backoff.
        """

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                )

                content = response.choices[0].message.content

                if content is None or not content.strip():
                    raise RuntimeError("LLM returned empty content.")

                return content

            except (APIConnectionError, APITimeoutError, RateLimitError) as exc:
                last_error = exc
                sleep_seconds = self._backoff_seconds(attempt)

                print(
                    f"[LLM retry] attempt {attempt}/{self.max_retries} failed: "
                    f"{type(exc).__name__}: {exc}. "
                    f"Retrying in {sleep_seconds}s..."
                )

                time.sleep(sleep_seconds)

        raise RuntimeError(
            f"LLM call failed after {self.max_retries} attempts. "
            f"Last error: {repr(last_error)}"
        )


    def stream(self, messages: list[dict[str, Any]]):
        """Stream chat completion response token by token.

        Yields content tokens as they arrive from the LLM API.
        This is useful for real-time display in UI or CLI.

        Yields:
            str: Content tokens from the LLM response.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                stream=True,
                stream_options={"include_usage": False},
            )

            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

        except Exception as exc:
            yield f"[Stream error: {type(exc).__name__}: {exc}]"

    @staticmethod
    def _backoff_seconds(attempt: int) -> int:
        """Exponential backoff with a small upper bound."""

        return min(2**attempt, 8)