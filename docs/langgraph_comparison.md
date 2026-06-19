````markdown
# LangGraph and ResearchPilot Graph Workflow Comparison

This note explains how the graph-based multi-agent workflow in ResearchPilot maps to LangGraph's `StateGraph` abstraction.

The goal is not to replace ResearchPilot's custom `GraphWorkflowRuntime` with LangGraph immediately. Instead, this note clarifies the conceptual mapping between the two systems and summarizes how to explain the difference in interviews.

---

## 1. ResearchPilot graph workflow

ResearchPilot uses a graph-based multi-agent workflow for routing user requests to different subagents.

A typical workflow is:

```text
prepare
  ↓
planner
  ↓
code / paper / general
  ↓
reviewer
  ↓
final
````

The main nodes are:

| Node       | Responsibility                                                          |
| ---------- | ----------------------------------------------------------------------- |
| `prepare`  | Normalize and prepare the user request.                                 |
| `planner`  | Decide whether the request should go to code, paper, or general branch. |
| `code`     | Run codebase QA workflow or code-related subagent.                      |
| `paper`    | Run paper research workflow or paper-related subagent.                  |
| `general`  | Answer general questions.                                               |
| `reviewer` | Review whether the draft answer is sufficient.                          |
| `final`    | Produce the final user-facing answer.                                   |

The workflow also records `visited_nodes`, which makes the actual execution path observable.

Example:

```text
prepare → planner → paper → reviewer → final
```

This makes it possible to debug planner routing, fallback behavior, and evidence insufficiency.

---

## 2. LangGraph core abstraction

LangGraph represents an agent workflow as a stateful graph.

The main concepts are:

| LangGraph concept  | Meaning                                                           |
| ------------------ | ----------------------------------------------------------------- |
| `StateGraph`       | The graph definition that manages nodes, edges, and shared state. |
| `State`            | The shared data object passed between nodes.                      |
| `Node`             | A function that reads state and returns partial state updates.    |
| `Edge`             | A fixed transition from one node to another.                      |
| `Conditional Edge` | A dynamic transition determined by the current state.             |
| `START` / `END`    | Special graph entry and exit points.                              |

A typical node has this conceptual form:

```python
def node(state: State) -> dict:
    # read current state
    # do some work
    # return partial state update
    return {"some_key": some_value}
```

The graph is compiled and then invoked:

```python
app = graph.compile()
result = app.invoke(initial_state)
```

---

## 3. Conceptual mapping

ResearchPilot and LangGraph share very similar workflow concepts.

| ResearchPilot                                      | LangGraph                       | Explanation                                    |
| -------------------------------------------------- | ------------------------------- | ---------------------------------------------- |
| `GraphWorkflowRuntime`                             | `StateGraph`                    | Both manage graph execution.                   |
| `GraphState` / `Blackboard`                        | `State`                         | Shared state passed across nodes.              |
| `prepare`, `planner`, `paper`, `reviewer`, `final` | Nodes                           | Each node performs one step and updates state. |
| Fixed transition                                   | `add_edge`                      | Always move from one node to another.          |
| Planner routing                                    | `add_conditional_edges`         | Choose branch based on state.                  |
| Reviewer retry / fallback                          | `add_conditional_edges`         | Decide whether to finish or retry/fallback.    |
| `visited_nodes`                                    | Execution path / trace metadata | Records actual graph path.                     |

For example, the ResearchPilot planner branch:

```text
planner
  ├── code
  ├── paper
  └── general
```

can be represented in LangGraph as:

```python
graph.add_conditional_edges(
    "planner",
    route_after_planner,
    {
        "code": "code",
        "paper": "paper",
        "general": "general",
    },
)
```

The reviewer branch:

```text
reviewer
  ├── final
  └── fallback
```

can also be represented as a conditional edge.

---

## 4. Why ResearchPilot implements its own GraphWorkflowRuntime

ResearchPilot implements a lightweight graph workflow runtime mainly for learning, control, and project-specific customization.

The custom runtime makes the following mechanisms explicit:

* how nodes are registered;
* how conditional routing works;
* how shared graph state is updated;
* how subagents communicate through the blackboard;
* how visited nodes are recorded;
* how fallback and retry loops are implemented;
* how trace reports are generated.

This is useful for understanding the internal mechanics of agent workflow systems instead of treating a framework as a black box.

---

## 5. Why LangGraph is still useful

LangGraph is more mature and production-oriented.

Compared with the custom ResearchPilot runtime, LangGraph provides a more standardized framework for:

* stateful graph execution;
* conditional routing;
* streaming;
* persistence and checkpointing;
* durable execution;
* human-in-the-loop workflows;
* integration with the LangChain ecosystem.

Therefore, the custom ResearchPilot runtime is not intended to replace LangGraph in production. It is better understood as a lightweight educational and project-specific implementation of graph-based agent orchestration.

A production version of ResearchPilot could migrate its workflow to LangGraph while keeping the existing subagent and tool abstractions.

---

## 6. How ResearchPilot could be migrated to LangGraph

A possible migration plan:

1. Define a LangGraph state schema.

```python
class ResearchPilotState(TypedDict, total=False):
    user_request: str
    route: str
    draft_answer: str
    final_answer: str
    evidence: list[dict]
    metadata: dict
    visited_nodes: list[str]
```

2. Convert existing graph nodes into LangGraph node functions.

```python
def planner_node(state: ResearchPilotState) -> dict:
    ...
    return {"route": route, "visited_nodes": updated_path}
```

3. Use conditional edges for planner routing.

```python
graph.add_conditional_edges(
    "planner",
    route_after_planner,
    {
        "code": "code",
        "paper": "paper",
        "general": "general",
    },
)
```

4. Use conditional edges for reviewer decision and fallback.

```python
graph.add_conditional_edges(
    "reviewer",
    route_after_reviewer,
    {
        "final": "final",
        "paper": "paper",
        "general": "general",
    },
)
```

5. Reuse existing subagents inside LangGraph nodes.

For example:

```python
def paper_node(state: ResearchPilotState) -> dict:
    result = paper_subagent.run(state["user_request"])
    return {
        "draft_answer": result.answer,
        "evidence": result.evidence,
    }
```

This migration would preserve the core ResearchPilot logic while using LangGraph's mature execution engine.

---

## 7. Interview explanation

A concise interview explanation:

> I implemented a lightweight `GraphWorkflowRuntime` in ResearchPilot to better understand how graph-based agent workflows work internally. Its design is conceptually close to LangGraph: both use nodes, edges, conditional routing, and shared state. In ResearchPilot, the workflow goes through `prepare`, `planner`, `code/paper/general`, `reviewer`, and `final` nodes. The planner uses conditional routing to decide which subagent should handle the request, and the reviewer can trigger fallback or finalization.
>
> The main difference is that my implementation is lightweight and project-specific, while LangGraph is a mature production-oriented framework with checkpointing, durable execution, streaming, and human-in-the-loop support. I built my own runtime mainly for learning and fine-grained control, but the architecture can be migrated to LangGraph if production-level orchestration is needed.

---

## 8. Key takeaway

ResearchPilot demonstrates that I understand the core mechanics behind graph-based agent orchestration.

The project is not only a wrapper around an existing framework. It implements the key ideas manually:

```text
state + node + edge + conditional routing + subagent execution + trace
```

LangGraph provides a more mature version of the same general idea.

Therefore, ResearchPilot can be described as:

```text
a custom lightweight graph-based multi-agent runtime inspired by modern agent workflow systems such as LangGraph
```

```
```
