from research_pilot.core.observation import Observation
from research_pilot.core.tool import BaseTool, ToolSpec


class MockWebSearchTool(BaseTool):
    """A mock web search tool for Phase 3A.

    Later this can be replaced by Tavily, DuckDuckGo, SerpAPI, or another provider.
    """

    name = "web_search"
    description = "Search web resources for a query. Phase 3A uses mock results."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "query": "Search query string.",
                "max_results": "Optional number of results. Default is 3.",
            },
        )

    def run(self, tool_input: dict, state=None) -> Observation:
        query = tool_input.get("query", "")
        max_results = int(tool_input.get("max_results", 3))

        if not query:
            return Observation(
                success=False,
                content="Missing input: query",
                error="MissingQuery",
            )

        mock_results = [
            {
                "title": f"Overview of {query}",
                "url": "https://example.com/overview",
                "snippet": (
                    f"{query} is commonly discussed in relation to planning, "
                    "tool use, retrieval, evaluation, and iterative refinement."
                ),
            },
            {
                "title": f"Architectures related to {query}",
                "url": "https://example.com/architecture",
                "snippet": (
                    "A typical agentic architecture includes a planner, executor, "
                    "tool runtime, memory, reflection, and report generation."
                ),
            },
            {
                "title": f"Challenges of {query}",
                "url": "https://example.com/challenges",
                "snippet": (
                    "Common challenges include hallucination control, source grounding, "
                    "tool reliability, context management, and evaluation."
                ),
            },
        ][:max_results]

        lines = [f"Mock web search results for query: {query}", ""]

        for idx, result in enumerate(mock_results, start=1):
            lines.append(f"{idx}. {result['title']}")
            lines.append(f"   URL: {result['url']}")
            lines.append(f"   Snippet: {result['snippet']}")
            lines.append("")

        return Observation(
            success=True,
            content="\n".join(lines),
            metadata={
                "query": query,
                "num_results": len(mock_results),
                "backend": "mock",
                "results": mock_results,
            },
        )