# src/research_pilot/graph/graph_runner.py

from collections.abc import Callable
from typing import Any

from rich.console import Console

from research_pilot.graph.graph_node import BaseGraphNode, GraphNodeResult
from research_pilot.graph.graph_state import GraphState, GraphStepRecord


ConditionalRouter = Callable[[GraphState, GraphNodeResult], str | None]


class GraphWorkflowRunner:
    """A lightweight LangGraph-style graph workflow runner.

    Features:
    - node-based execution
    - default edges
    - conditional edges
    - shared GraphState
    - bounded loops through max_steps
    - visited node tracing
    """

    END = "__end__"

    def __init__(
        self,
        start_node: str,
        max_steps: int = 20,
        console: Console | None = None,
        stop_on_node_error: bool = True,
    ):
        self.start_node = start_node
        self.max_steps = max_steps
        self.console = console or Console()
        self.stop_on_node_error = stop_on_node_error

        self.nodes: dict[str, BaseGraphNode] = {}
        self.default_edges: dict[str, str] = {}
        self.conditional_edges: dict[str, ConditionalRouter] = {}

    def add_parallel_group(
        self, name: str, sub_nodes: list, description: str = "",
    ) -> None:
        "Add a node that runs sub-nodes and merges results."
        from research_pilot.graph.graph_node import ParallelGroupNode
        node = ParallelGroupNode(name=name, sub_nodes=sub_nodes,
                             description=description or "Parallel: " + name)
        self.nodes[node.name] = node

    def add_node(self, node) -> None:
        "Register a graph node."
        if not node.name:
            raise ValueError("Graph node name cannot be empty.")
        self.nodes[node.name] = node

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add a default edge from one node to another."""

        self.default_edges[from_node] = to_node

    def add_conditional_edge(
        self,
        from_node: str,
        router: ConditionalRouter,
    ) -> None:
        """Add a conditional router for one node."""

        self.conditional_edges[from_node] = router

    def run(
        self,
        user_request: str,
        initial_metadata: dict[str, Any] | None = None,
    ) -> GraphState:
        """Run the graph from the start node."""

        state = GraphState(
            user_request=user_request,
            current_node=self.start_node,
            max_steps=self.max_steps,
            metadata=initial_metadata or {},
        )

        return self.run_state(state)

    def run_state(self, state: GraphState) -> GraphState:
        """Run the graph using an existing GraphState."""

        if not state.current_node:
            state.current_node = self.start_node

        while not state.is_final and state.step_count < state.max_steps:
            node_name = state.current_node

            if node_name == self.END or node_name is None:
                state.is_final = True
                break

            node = self.nodes.get(node_name)

            if node is None:
                error = f"Graph node not found: {node_name}"
                state.add_error(error)
                state.set_final_answer(error)
                break

            result = self._run_node_safely(node=node, state=state)

            self._apply_updates(state=state, result=result)

            next_node = self._choose_next_node(
                node_name=node_name,
                state=state,
                result=result,
            )

            record = GraphStepRecord(
                step_id=state.step_count + 1,
                node_name=node_name,
                success=result.success,
                next_node=next_node,
                is_final=result.is_final,
                error=result.error,
                output_preview=result.output_preview[:1000],
                metadata=result.metadata,
            )
            state.add_step_record(record)

            if result.error:
                state.add_error(result.error)

            if result.final_answer:
                state.final_answer = result.final_answer

            if result.is_final or next_node == self.END or next_node is None:
                state.is_final = True
                break

            if not result.success and self.stop_on_node_error:
                state.is_final = True
                if not state.final_answer:
                    state.final_answer = result.error or "Graph stopped on node error."
                break

            state.current_node = next_node

        if not state.is_final and state.step_count >= state.max_steps:
            state.is_final = True
            state.add_error(
                f"Graph reached max_steps={state.max_steps} before final node."
            )
            if not state.final_answer:
                state.final_answer = (
                    f"Graph stopped because it reached max_steps={state.max_steps}."
                )

        return state

    def _run_node_safely(
        self,
        node: BaseGraphNode,
        state: GraphState,
    ) -> GraphNodeResult:
        try:
            return node.run(state)

        except Exception as exc:
            return GraphNodeResult(
                success=False,
                is_final=self.stop_on_node_error,
                error=f"{type(exc).__name__}: {exc}",
                output_preview=f"Node {node.name} failed.",
            )

    def _choose_next_node(
        self,
        node_name: str,
        state: GraphState,
        result: GraphNodeResult,
    ) -> str | None:
        """Choose the next node by priority.

        Priority:
        1. final result
        2. explicit result.next_node
        3. conditional router
        4. default edge
        5. stop
        """

        if result.is_final:
            return self.END

        if result.next_node:
            return result.next_node

        router = self.conditional_edges.get(node_name)
        if router is not None:
            routed = router(state, result)
            if routed is not None:
                return routed

        if node_name in self.default_edges:
            return self.default_edges[node_name]

        return None


    def render_mermaid(self, graph_state=None):
        """Generate a Mermaid flowchart diagram of this graph structure."""
        lines = ["flowchart TD"]
        visited = set()
        if graph_state is not None:
            visited = set(getattr(graph_state, "visited_nodes", []))
        for name, node in self.nodes.items():
            br = name.replace("_", " ")
            style = " visited" if name in visited else ""
            safe_desc = node.description.replace("\"", "'")
            lines.append(f"    {name}[\"{br}\"]{style}")
        for from_node, to_node in self.default_edges.items():
            lines.append(f"    {from_node} --> {to_node}")
        for from_node in self.conditional_edges:
            lines.append(f"    {from_node} -.-> |route| ROUTER")
        if visited:
            for name in visited:
                if name in self.nodes:
                    lines.append(f"    style {name} stroke:#00a,stroke-width:2px")
        return "\n".join(lines)


    def render_mermaid(self, graph_state=None):
        """Generate a Mermaid flowchart diagram of this graph structure."""
        lines = ["flowchart TD"]
        visited = set()
        if graph_state is not None:
            visited = set(getattr(graph_state, "visited_nodes", []))
        for name, node in self.nodes.items():
            br = name.replace("_", " ")
            style = " visited" if name in visited else ""
            lines.append(f"    {name}[\"{br}\"]{style}")
        for from_node, to_node in self.default_edges.items():
            lines.append(f"    {from_node} --> {to_node}")
        for from_node in self.conditional_edges:
            lines.append(f"    {from_node} -.-> |route| ROUTER")
        if visited:
            for name in visited:
                if name in self.nodes:
                    lines.append(f"    style {name} stroke:#00a,stroke-width:2px")
        return "\n".join(lines)

    @staticmethod
    def _apply_updates(
        state: GraphState,
        result: GraphNodeResult,
    ) -> None:
        """Apply node updates to graph state.

        Existing GraphState fields are updated directly.
        Other keys are stored under state.metadata.
        """

        for key, value in result.updates.items():
            if hasattr(state, key):
                setattr(state, key, value)
            else:
                state.metadata[key] = value