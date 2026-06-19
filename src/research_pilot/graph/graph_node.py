# src/research_pilot/graph/graph_node.py

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from research_pilot.graph.graph_state import GraphState


class GraphNodeResult(BaseModel):
    """Result returned by one graph node."""

    success: bool = True

    # If next_node is set, GraphWorkflowRunner will route to it.
    # If it is None, the runner uses default or conditional edges.
    next_node: str | None = None

    # If is_final=True, graph execution stops.
    is_final: bool = False
    final_answer: str = ""

    # Updates are merged into GraphState.metadata by default.
    updates: dict[str, Any] = Field(default_factory=dict)

    # Extra metadata for tracing/debugging.
    metadata: dict[str, Any] = Field(default_factory=dict)

    error: str | None = None
    output_preview: str = ""


class BaseGraphNode(ABC):
    """Base class for all graph workflow nodes."""

    name: str = "base_node"
    description: str = "Base graph node."

    @abstractmethod
    def run(self, state: GraphState) -> GraphNodeResult:
        """Run this node against the shared graph state."""



class ParallelGroupNode(BaseGraphNode):
    "Run multiple sub-nodes and merge results. Can be upgraded to true parallelism."

    def __init__(self, name: str, sub_nodes: list[BaseGraphNode], description: str = ""):
        self.name = name
        self.sub_nodes = sub_nodes
        self.description = description or "Parallel group: " + name

    def run(self, state: GraphState) -> GraphNodeResult:
        merged = GraphNodeResult(success=True)
        merged.updates["parallel_node_results"] = {}

        for node in self.sub_nodes:
            result = node.run(state)

            if not result.success:
                merged.success = False
                merged.error = node.name + ": " + (result.error or "unknown error")

            merged.updates.update(result.updates)
            merged.updates["parallel_node_results"][node.name] = {
                "success": result.success,
                "output_preview": result.output_preview[:500],
                "error": result.error,
            }

            merged.metadata[node.name] = result.output_preview[:300]

            if result.final_answer:
                merged.final_answer = (merged.final_answer + chr(10)*2 + result.final_answer).strip()



        merged.output_preview = (
            "Parallel group ran " + str(len(self.sub_nodes)) + " nodes. "
            + "Success: " + str(merged.success)
        )
        return merged


class FunctionGraphNode(BaseGraphNode):
    """Wrap a normal Python function as a graph node."""

    def __init__(
        self,
        name: str,
        fn: Callable[[GraphState], GraphNodeResult],
        description: str = "",
    ):
        self.name = name
        self.fn = fn
        self.description = description or f"Function graph node: {name}"

    def run(self, state: GraphState) -> GraphNodeResult:
        return self.fn(state)