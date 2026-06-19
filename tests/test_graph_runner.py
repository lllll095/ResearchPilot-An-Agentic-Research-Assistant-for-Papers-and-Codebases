"""Tests for GraphWorkflowRunner."""

from pathlib import Path

import pytest

from research_pilot.graph.graph_node import BaseGraphNode, GraphNodeResult, FunctionGraphNode
from research_pilot.graph.graph_runner import GraphWorkflowRunner
from research_pilot.graph.graph_state import GraphState


# ---------------------------------------------------------------------------
# Helper nodes
# ---------------------------------------------------------------------------

class SimpleNode(BaseGraphNode):
    """Node that returns a basic result."""
    def __init__(self, name: str, is_final: bool = False, next_node: str | None = None):
        self.name = name
        self.is_final = is_final
        self.next_node = next_node

    def run(self, state: GraphState) -> GraphNodeResult:
        return GraphNodeResult(
            success=True,
            is_final=self.is_final,
            next_node=self.next_node,
            output_preview=f"{self.name} executed",
        )


class ConditionalNode(BaseGraphNode):
    """Node that sets metadata for conditional routing."""
    def __init__(self, name: str, route_to: str):
        self.name = name
        self.route_to = route_to

    def run(self, state: GraphState) -> GraphNodeResult:
        return GraphNodeResult(
            success=True,
            updates={"route_to": self.route_to},
            output_preview=f"{self.name} -> {self.route_to}",
        )


class FailingNode(BaseGraphNode):
    """Node that always fails."""
    def __init__(self, name: str):
        self.name = name

    def run(self, state: GraphState) -> GraphNodeResult:
        return GraphNodeResult(
            success=False,
            is_final=True,
            error=f"{self.name} failed",
            output_preview="error",
        )


class ExplodingNode(BaseGraphNode):
    """Node that raises an exception."""
    def __init__(self, name: str):
        self.name = name

    def run(self, state: GraphState) -> GraphNodeResult:
        raise RuntimeError(f"{self.name} exploded")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGraphWorkflowRunnerBasic:
    """Basic graph workflow tests."""

    def test_start_to_end(self):
        """Simple path: start -> A -> B -> END."""
        graph = GraphWorkflowRunner(start_node="A", max_steps=10)

        graph.add_node(SimpleNode("A"))
        graph.add_node(SimpleNode("B", is_final=True))
        graph.add_edge("A", "B")

        state = graph.run("test request")

        assert state.is_final is True
        assert state.visited_nodes == ["A", "B"]
        assert state.step_count == 2

    def test_single_final_node(self):
        """Single node that is final."""
        graph = GraphWorkflowRunner(start_node="A", max_steps=10)

        graph.add_node(SimpleNode("A", is_final=True))

        state = graph.run("test")

        assert state.is_final is True
        assert state.visited_nodes == ["A"]

    def test_max_steps_termination(self):
        """Graph stops when max_steps is reached."""
        graph = GraphWorkflowRunner(start_node="A", max_steps=3)

        graph.add_node(SimpleNode("A"))
        graph.add_node(SimpleNode("B"))
        graph.add_node(SimpleNode("C"))
        graph.add_edge("A", "B")
        graph.add_edge("B", "C")

        state = graph.run("test")

        assert state.step_count == 3

    def test_missing_node(self):
        """Graph handles missing node gracefully."""
        graph = GraphWorkflowRunner(start_node="A", max_steps=10)

        graph.add_node(SimpleNode("A"))
        graph.add_edge("A", "MISSING")

        state = graph.run("test")

        assert state.is_final is True
        assert "not found" in state.final_answer.lower() or "not found" in " ".join(state.errors)

    def test_node_error_termination(self):
        """Graph stops on node error when stop_on_node_error=True."""
        graph = GraphWorkflowRunner(
            start_node="A",
            max_steps=10,
            stop_on_node_error=True,
        )

        graph.add_node(FailingNode("A"))

        state = graph.run("test")

        assert state.is_final is True
        assert "failed" in state.final_answer or any("failed" in e for e in state.errors)

    def test_node_exception(self):
        """Graph handles node exceptions."""
        graph = GraphWorkflowRunner(
            start_node="A",
            max_steps=10,
            stop_on_node_error=True,
        )

        graph.add_node(ExplodingNode("A"))

        state = graph.run("test")

        assert state.is_final is True
        assert "exploded" in state.final_answer or any("exploded" in e for e in state.errors)

    def test_result_next_node_wins(self):
        """result.next_node takes priority over default edge."""
        graph = GraphWorkflowRunner(start_node="A", max_steps=10)

        graph.add_node(SimpleNode("A", next_node="C"))
        graph.add_node(SimpleNode("C", is_final=True))
        graph.add_edge("A", "B")

        state = graph.run("test")

        assert state.visited_nodes == ["A", "C"]


class TestGraphConditionalEdges:
    """Conditional edge tests."""

    def test_conditional_route_to_code(self):
        """Conditional edge routes based on metadata."""
        graph = GraphWorkflowRunner(start_node="planner", max_steps=10)

        def router(state: GraphState, result: GraphNodeResult) -> str | None:
            return state.metadata.get("route_to")

        graph.add_node(ConditionalNode("planner", route_to="code"))
        graph.add_node(SimpleNode("code", is_final=True))
        graph.add_conditional_edge("planner", router)

        state = graph.run("test")

        assert state.visited_nodes == ["planner", "code"]

    def test_conditional_route_to_fallback(self):
        """Conditional edge routes to default when router returns None."""
        graph = GraphWorkflowRunner(start_node="planner", max_steps=10)

        def router(state: GraphState, result: GraphNodeResult) -> str | None:
            return None

        graph.add_node(ConditionalNode("planner", route_to="code"))
        graph.add_node(SimpleNode("fallback", is_final=True))
        graph.add_edge("planner", "fallback")
        graph.add_conditional_edge("planner", router)

        state = graph.run("test")

        assert state.visited_nodes == ["planner", "fallback"]

    def test_conditional_chain(self):
        """Multi-step conditional chain."""
        graph = GraphWorkflowRunner(start_node="start", max_steps=10)

        def router(state: GraphState, result: GraphNodeResult) -> str | None:
            return state.metadata.get("route_to")

        graph.add_node(ConditionalNode("start", route_to="middle"))
        graph.add_node(ConditionalNode("middle", route_to="end"))
        graph.add_node(SimpleNode("end", is_final=True))
        graph.add_conditional_edge("start", router)
        graph.add_conditional_edge("middle", router)

        state = graph.run("test")

        assert state.visited_nodes == ["start", "middle", "end"]


class TestGraphWorkflowRunnerAPI:
    """Graph API tests."""

    def test_add_node_empty_name(self):
        graph = GraphWorkflowRunner(start_node="start", max_steps=10)
        with pytest.raises(ValueError, match="cannot be empty"):
            graph.add_node(SimpleNode(""))

    def test_run_state_from_existing_state(self):
        graph = GraphWorkflowRunner(start_node="A", max_steps=10)
        graph.add_node(SimpleNode("A", is_final=True))

        state = GraphState(user_request="test")
        result = graph.run_state(state)

        assert result.is_final is True

    def test_mermaid_generation(self):
        """render_mermaid produces valid Mermaid output."""
        graph = GraphWorkflowRunner(start_node="A", max_steps=10)
        graph.add_node(SimpleNode("A"))
        graph.add_node(SimpleNode("B", is_final=True))
        graph.add_edge("A", "B")

        mermaid = graph.render_mermaid()

        assert "flowchart TD" in mermaid
        assert "A --> B" in mermaid or "A-->B" in mermaid

    def test_mermaid_with_conditional(self):
        """render_mermaid includes conditional edges."""
        graph = GraphWorkflowRunner(start_node="planner", max_steps=10)

        def router(state, result):
            return "code" if state.metadata.get("route_to") == "code" else None

        graph.add_node(ConditionalNode("planner", route_to="code"))
        graph.add_node(SimpleNode("code", is_final=True))
        graph.add_conditional_edge("planner", router)

        mermaid = graph.render_mermaid()

        assert "flowchart TD" in mermaid
        assert "planner" in mermaid
        assert "code" in mermaid

    def test_node_description_default(self):
        """FunctionGraphNode gets a default description."""
        def my_fn(state):
            return GraphNodeResult(success=True, is_final=True)

        node = FunctionGraphNode("test", my_fn)
        assert "test" in node.description


class TestGraphNodeResult:
    """GraphNodeResult field tests."""

    def test_defaults(self):
        result = GraphNodeResult()
        assert result.success is True
        assert result.is_final is False
        assert result.next_node is None
        assert result.error is None
        assert result.final_answer == ""

class TestRetryPolicy:
    """Tests for RetryPolicy dataclass."""

    def test_default_values(self):
        from research_pilot.graph.policy import RetryPolicy
        rp = RetryPolicy()
        assert rp.max_retries == 1
        assert rp.fallback_to_writer is True
        assert rp.retry_on_failures is True
        assert rp.allowed_retry_agents == ("code", "paper")

    def test_custom_values(self):
        from research_pilot.graph.policy import RetryPolicy
        rp = RetryPolicy(max_retries=3, fallback_to_writer=False, allowed_retry_agents=("paper",))
        assert rp.max_retries == 3
        assert rp.fallback_to_writer is False
        assert rp.allowed_retry_agents == ("paper",)

    def test_zero_retries(self):
        from research_pilot.graph.policy import RetryPolicy
        rp = RetryPolicy(max_retries=0)
        assert rp.max_retries == 0

    def test_immutable_tuple(self):
        from research_pilot.graph.policy import RetryPolicy
        rp = RetryPolicy()
        assert isinstance(rp.allowed_retry_agents, tuple)

class TestParallelGroupNode:
    "Tests for ParallelGroupNode."

    def test_runs_multiple_nodes(self):
        from research_pilot.graph.graph_node import ParallelGroupNode
        from research_pilot.graph.graph_node import BaseGraphNode, GraphNodeResult
        from research_pilot.graph.graph_state import GraphState
        node_a = SimpleNode('a', is_final=False)
        node_b = SimpleNode('b', next_node='end')
        group = ParallelGroupNode('group', [node_a, node_b])
        state = GraphState(user_request='test')
        result = group.run(state)
        assert result.success is True
        assert 'a' in result.metadata
        assert 'b' in result.metadata

    def test_merges_updates(self):
        from research_pilot.graph.graph_node import ParallelGroupNode
        from research_pilot.graph.graph_node import BaseGraphNode
        from research_pilot.graph.graph_node import GraphNodeResult
        from research_pilot.graph.graph_state import GraphState
        class UpdNode(BaseGraphNode):
            def __init__(self, name, key, value):
                self.name = name
                self.key = key
                self.value = value
            def run(self, state):
                return GraphNodeResult(success=True, updates={self.key: self.value})
        group = ParallelGroupNode('group', [
            UpdNode('x', 'k1', 'v1'),
            UpdNode('y', 'k2', 'v2'),
        ])
        state = GraphState(user_request='test')
        result = group.run(state)
        assert result.updates.get('k1') == 'v1'
        assert result.updates.get('k2') == 'v2'

    def test_merges_final_answers(self):
        from research_pilot.graph.graph_node import ParallelGroupNode
        from research_pilot.graph.graph_node import BaseGraphNode
        from research_pilot.graph.graph_node import GraphNodeResult
        from research_pilot.graph.graph_state import GraphState
        class AnsNode(BaseGraphNode):
            def __init__(self, name, answer):
                self.name = name
                self.answer = answer
            def run(self, state):
                return GraphNodeResult(success=True, final_answer=self.answer)
        group = ParallelGroupNode('group', [
            AnsNode('code', 'Code done.'),
            AnsNode('paper', 'Paper done.'),
        ])
        state = GraphState(user_request='test')
        result = group.run(state)
        assert 'Code done' in result.final_answer
        assert 'Paper done' in result.final_answer

    def test_parallel_results_in_updates(self):
        from research_pilot.graph.graph_node import ParallelGroupNode
        from research_pilot.graph.graph_node import BaseGraphNode, GraphNodeResult
        from research_pilot.graph.graph_state import GraphState
        class _S2(BaseGraphNode):
            def __init__(self, name):
                self.name = name
            def run(self, state):
                return GraphNodeResult(success=True, output_preview=self.name)
        group = ParallelGroupNode('group', [SimpleNode('a'), SimpleNode('b')])
        state = GraphState(user_request='test')
        result = group.run(state)
        nr = result.updates.get('parallel_node_results', {})
        assert 'a' in nr
        assert 'b' in nr
        assert nr['a']['success'] is True
        assert nr['b']['success'] is True
