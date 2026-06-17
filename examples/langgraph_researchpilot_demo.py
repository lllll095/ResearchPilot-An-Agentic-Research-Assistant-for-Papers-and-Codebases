"""
A minimal LangGraph demo that mirrors the ResearchPilot graph workflow.

This demo does NOT call real LLMs, tools, or RAG components.
It only shows how ResearchPilot's graph-style workflow can be expressed
with LangGraph's StateGraph abstraction.

Workflow:

prepare -> planner -> code / paper / general -> reviewer -> final
"""

from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


Route = Literal["code", "paper", "general"]
ReviewDecision = Literal["final", "general"]


class DemoState(TypedDict, total=False):
    """Shared state passed between graph nodes."""

    user_request: str
    normalized_request: str
    route: Route
    draft_answer: str
    final_answer: str
    approved: bool
    visited_nodes: list[str]


def add_visit(state: DemoState, node_name: str) -> list[str]:
    """Append one node name to the visited path."""

    return state.get("visited_nodes", []) + [node_name]


def prepare_node(state: DemoState) -> DemoState:
    """Prepare the user request before planning."""

    user_request = state.get("user_request", "")
    normalized_request = user_request.strip()

    return {
        "normalized_request": normalized_request,
        "visited_nodes": add_visit(state, "prepare"),
    }


def planner_node(state: DemoState) -> DemoState:
    """Route the request to code, paper, or general branch."""

    query = state.get("normalized_request", "").lower()

    code_keywords = [
        "code",
        "代码",
        "函数",
        "class",
        "agentloop",
        "toolruntime",
        "graphworkflowruntime",
    ]

    paper_keywords = [
        "paper",
        "论文",
        "rag",
        "retrieval",
        "adadetectgpt",
        "detectgpt",
        "搜索",
        "检索",
    ]

    if any(keyword in query for keyword in code_keywords):
        route: Route = "code"
    elif any(keyword in query for keyword in paper_keywords):
        route = "paper"
    else:
        route = "general"

    return {
        "route": route,
        "visited_nodes": add_visit(state, "planner"),
    }


def code_node(state: DemoState) -> DemoState:
    """Simulate the code subagent."""

    question = state.get("normalized_request", "")

    draft_answer = (
        "This is a simulated CodeSubAgent answer. "
        f"It would inspect the codebase and answer the code question: {question}"
    )

    return {
        "draft_answer": draft_answer,
        "visited_nodes": add_visit(state, "code"),
    }


def paper_node(state: DemoState) -> DemoState:
    """Simulate the paper subagent."""

    question = state.get("normalized_request", "")

    draft_answer = (
        "This is a simulated PaperSubAgent answer. "
        f"It would run adaptive paper research, retrieve evidence, and answer: {question}"
    )

    return {
        "draft_answer": draft_answer,
        "visited_nodes": add_visit(state, "paper"),
    }


def general_node(state: DemoState) -> DemoState:
    """Simulate the general subagent."""

    question = state.get("normalized_request", "")

    draft_answer = (
        "This is a simulated GeneralSubAgent answer. "
        f"It would answer the general question directly: {question}"
    )

    return {
        "draft_answer": draft_answer,
        "visited_nodes": add_visit(state, "general"),
    }


def reviewer_node(state: DemoState) -> DemoState:
    """Review whether the draft answer is good enough."""

    draft_answer = state.get("draft_answer", "")

    # A toy review rule:
    # In the real ResearchPilot project, this would be an LLM-based reviewer.
    approved = len(draft_answer.strip()) >= 20

    return {
        "approved": approved,
        "visited_nodes": add_visit(state, "reviewer"),
    }


def final_node(state: DemoState) -> DemoState:
    """Produce final answer."""

    draft_answer = state.get("draft_answer", "")
    visited_nodes = add_visit(state, "final")

    final_answer = (
        f"{draft_answer}\n\n"
        f"[Demo metadata] visited_nodes = {' -> '.join(visited_nodes)}"
    )

    return {
        "final_answer": final_answer,
        "visited_nodes": visited_nodes,
    }


def route_after_planner(state: DemoState) -> Route:
    """Choose the branch after planner."""

    return state.get("route", "general")


def route_after_reviewer(state: DemoState) -> ReviewDecision:
    """Choose whether to finish or fallback to general branch."""

    if state.get("approved", False):
        return "final"

    return "general"


def build_graph():
    """Build and compile the LangGraph workflow."""

    graph = StateGraph(DemoState)

    graph.add_node("prepare", prepare_node)
    graph.add_node("planner", planner_node)
    graph.add_node("code", code_node)
    graph.add_node("paper", paper_node)
    graph.add_node("general", general_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("final", final_node)

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "planner")

    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "code": "code",
            "paper": "paper",
            "general": "general",
        },
    )

    graph.add_edge("code", "reviewer")
    graph.add_edge("paper", "reviewer")
    graph.add_edge("general", "reviewer")

    graph.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "final": "final",
            "general": "general",
        },
    )

    graph.add_edge("final", END)

    return graph.compile()


def run_demo(question: str) -> None:
    """Run one demo query and print the result."""

    app = build_graph()

    result = app.invoke(
        {
            "user_request": question,
            "visited_nodes": [],
        }
    )

    print("=" * 80)
    print(f"Question: {question}")
    print(f"Route: {result.get('route')}")
    print(f"Visited nodes: {' -> '.join(result.get('visited_nodes', []))}")
    print()
    print(result.get("final_answer", ""))


if __name__ == "__main__":
    demo_questions = [
        "AgentLoop 是怎么实现的？",
        "搜索一下并告诉我 AdaDetectGPT 是啥",
        "RAG 和 Agent 的区别是什么？",
    ]

    for demo_question in demo_questions:
        run_demo(demo_question)
