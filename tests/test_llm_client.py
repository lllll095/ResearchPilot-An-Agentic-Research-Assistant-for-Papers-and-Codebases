"""Tests for LLM client streaming."""

from research_pilot.core.llm_client import OpenAICompatibleLLMClient


class TestLLMClientStreaming:
    """Tests for the stream() method on OpenAICompatibleLLMClient."""

    def test_stream_method_exists(self):
        """stream() should be a generator function."""
        client = OpenAICompatibleLLMClient(
            api_key="test_key",
            base_url="http://test.local",
            model="test-model",
        )
        assert hasattr(client, "stream")

    def test_stream_is_generator(self):
        """Calling stream() should return a generator."""
        client = OpenAICompatibleLLMClient(
            api_key="test_key",
            base_url="http://test.local",
            model="test-model",
        )
        result = client.stream([{"role": "user", "content": "hi"}])
        from typing import Generator
        assert isinstance(result, Generator)

    def test_complete_still_works(self):
        """Adding stream() should not break complete()."""
        client = OpenAICompatibleLLMClient(
            api_key="test_key",
            base_url="http://test.local",
            model="test-model",
        )
        assert hasattr(client, "complete")
