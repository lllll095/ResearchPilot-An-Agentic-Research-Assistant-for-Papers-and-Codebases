"""
LangGraph wrapper demo for ResearchPilot's real paper workflow.

This demo shows how to call the existing PaperWorkflowRunner from inside
a LangGraph node.

It is intentionally small:

prepare -> paper_research -> reviewer -> final

Unlike langgraph_researchpilot_demo.py, this file calls the real
ResearchPilot paper workflow instead of using simulated string responses.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from research_pilot.cli import build_paper_workflow_runner


ReviewDecision = Literal["final", "fallback"]


class RealPaperState(TypedDict, total=False):
    """Shared state for the LangGraph paper workflow demo."""

    question: str
    normalized_question: str
    answer: str
    final_answer: str
    metadata: dict[str, Any]
    approved: bool
    visited_nodes: list[str]


def add_visit(state: RealPaperState, node_name: str) -> list[str]:
    """Append one node name to the visited path."""

    return state.get("visited_nodes", []) + [node_name]


@lru_cache(maxsize=1)
def get_paper_runner():
    """Build and cache the real ResearchPilot PaperWorkflowRunner."""

    return build_paper_workflow_runner(verbose=False)


def prepare_node(state: RealPaperState) -> RealPaperState:
    """Normalize the paper research question."""

    question = state.get("question", "")
    normalized_question = question.strip()

    return {
        "normalized_question": normalized_question,
        "visited_nodes": add_visit(state, "prepare"),
    }


def paper_research_node(state: RealPaperState) -> RealPaperState:
    """Call the real ResearchPilot paper workflow."""

    question = state.get("normalized_question", "")

    runner = get_paper_runner()

    result = runner.paper_research(
        question=question,
        max_papers=3,
        min_sources=3,
        force_download=False,
        save_report=False,
    )

    return {
        "answer": result.final_answer or "",
        "metadata": result.metadata or {},
        "visited_nodes": add_visit(state, "paper_research"),
    }


def reviewer_node(state: RealPaperState) -> RealPaperState:
    """A lightweight reviewer for the demo.

    In the real ResearchPilot graph workflow, the reviewer can be LLM-based.
    Here we only check whether the paper workflow returned a non-empty answer.
    """

    answer = state.get("answer", "")
    approved = len(answer.strip()) > 0

    return {
        "approved": approved,
        "visited_nodes": add_visit(state, "reviewer"),
    }


def fallback_node(state: RealPaperState) -> RealPaperState:
    """Fallback response when the workflow does not produce an answer."""

    question = state.get("normalized_question", "")

    fallback_answer = (
        "The LangGraph wrapper successfully ran, but the paper workflow "
        "did not return a sufficient answer. "
        f"Original question: {question}"
    )

    return {
        "answer": fallback_answer,
        "metadata": {
            **state.get("metadata", {}),
            "fallback": True,
        },
        "visited_nodes": add_visit(state, "fallback"),
    }


def final_node(state: RealPaperState) -> RealPaperState:
    """Produce final answer with lightweight demo metadata."""

    answer = state.get("answer", "")
    visited_nodes = add_visit(state, "final")

    final_answer = (
        f"{answer}\n\n"
        f"[LangGraph wrapper demo]\n"
        f"visited_nodes = {' -> '.join(visited_nodes)}"
    )

    return {
        "final_answer": final_answer,
        "visited_nodes": visited_nodes,
    }


def route_after_reviewer(state: RealPaperState) -> ReviewDecision:
    """Choose whether to finish or go to fallback."""

    if state.get("approved", False):
        return "final"

    return "fallback"


def build_graph():
    """Build and compile the LangGraph wrapper workflow."""

    graph = StateGraph(RealPaperState)

    graph.add_node("prepare", prepare_node)
    graph.add_node("paper_research", paper_research_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("final", final_node)

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "paper_research")
    graph.add_edge("paper_research", "reviewer")

    graph.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "final": "final",
            "fallback": "fallback",
        },
    )

    graph.add_edge("fallback", "final")
    graph.add_edge("final", END)

    return graph.compile()


def run_demo(question: str) -> None:
    """Run one demo question."""

    app = build_graph()

    result = app.invoke(
        {
            "question": question,
            "visited_nodes": [],
        }
    )

    print("=" * 80)
    print(f"Question: {question}")
    print(f"Visited nodes: {' -> '.join(result.get('visited_nodes', []))}")
    print()
    print(result.get("final_answer", ""))


if __name__ == "__main__":
    run_demo("基于已有论文证据，agentic RAG 的架构是什么？")