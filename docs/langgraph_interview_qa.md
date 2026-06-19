````markdown
# LangGraph Interview Q&A

This document summarizes how to explain the relationship between ResearchPilot and LangGraph in interviews.

The key message is:

> ResearchPilot implements a lightweight graph-based multi-agent runtime by hand.  
> LangGraph is a mature production-oriented framework with similar core abstractions, such as state, nodes, edges, conditional routing, checkpointing, and durable execution.  
> The purpose of ResearchPilot is not to replace LangGraph, but to demonstrate a deep understanding of how agent workflows work internally.

---

## 1. What is LangGraph?

LangGraph is a framework for building stateful, graph-based agent workflows.

Its core idea is to represent an agent system as:

```text
shared state
  +
nodes
  +
edges
  +
conditional routing
````

A typical LangGraph workflow contains:

| Concept            | Meaning                                                              |
| ------------------ | -------------------------------------------------------------------- |
| `StateGraph`       | The graph definition and execution runtime.                          |
| `State`            | Shared state passed between nodes.                                   |
| `Node`             | A function that performs one step and returns partial state updates. |
| `Edge`             | A fixed transition from one node to another.                         |
| `Conditional Edge` | A transition determined by the current state.                        |
| `Checkpoint`       | Saved execution state for persistence and recovery.                  |

In simple terms:

```text
LangGraph lets us write complex agent workflows as explicit graphs.
```

---

## 2. How is ResearchPilot related to LangGraph?

ResearchPilot has a custom lightweight graph workflow runtime.

A typical ResearchPilot graph workflow is:

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
```

This is conceptually close to LangGraph.

| ResearchPilot                                      | LangGraph                       |
| -------------------------------------------------- | ------------------------------- |
| `GraphWorkflowRuntime`                             | `StateGraph`                    |
| `GraphState` / `Blackboard`                        | `State`                         |
| `prepare`, `planner`, `paper`, `reviewer`, `final` | Nodes                           |
| Fixed workflow transition                          | `add_edge`                      |
| Planner routing                                    | `add_conditional_edges`         |
| Reviewer retry / fallback                          | Conditional edge                |
| `visited_nodes` / trace report                     | Execution trace / observability |

So ResearchPilot and LangGraph share the same basic workflow idea:

```text
state + node + edge + conditional routing + trace
```

---

## 3. Why did I implement my own GraphWorkflowRuntime instead of directly using LangGraph?

A concise answer:

> I implemented a lightweight `GraphWorkflowRuntime` mainly for learning, control, and transparency. I wanted to understand how graph-based agent workflows work internally: how nodes are registered, how shared state is passed, how planner routing works, how reviewer fallback is triggered, and how execution traces are recorded.
>
> My goal was not to replace LangGraph. Instead, I wanted to build a minimal version of the same core ideas so that I could reason about the internals of agent orchestration. In a production system, I would consider migrating the workflow to LangGraph to take advantage of checkpointing, durable execution, streaming, and human-in-the-loop support.

Short version:

```text
I built my own runtime to understand the mechanism, not to compete with LangGraph.
```

---

## 4. What does ResearchPilot's graph runtime support?

ResearchPilot's custom graph runtime supports:

* graph nodes;
* fixed edges;
* conditional routing;
* shared graph state;
* planner-based branch selection;
* reviewer-based fallback;
* visited path recording;
* trace report generation;
* subagent orchestration.

A representative workflow is:

```text
prepare → planner → paper → reviewer → final
```

For example, if the user asks a paper-related question, the planner routes the request to the paper subagent. If the reviewer finds the answer insufficient, the system can trigger fallback behavior such as additional retrieval, paper download, indexing, or answer revision.

---

## 5. What are the strengths of LangGraph compared with my custom runtime?

LangGraph is more mature and production-oriented.

Its strengths include:

* standardized graph abstraction;
* mature execution engine;
* checkpointing;
* durable execution;
* streaming;
* persistence;
* human-in-the-loop support;
* ecosystem integration with LangChain tools and agents.

Compared with LangGraph, ResearchPilot's custom runtime is:

```text
lighter,
more transparent,
more educational,
more project-specific,
but less production-ready.
```

A good interview answer:

> ResearchPilot's runtime is intentionally lightweight. It is enough to demonstrate planner routing, subagent execution, reviewer feedback, fallback, and trace logging. But LangGraph is more suitable for production-grade systems because it provides stronger runtime guarantees, checkpointing, persistence, streaming, and human-in-the-loop mechanisms.

---

## 6. Could ResearchPilot be migrated to LangGraph?

Yes.

A possible migration plan is:

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

2. Convert existing ResearchPilot nodes into LangGraph node functions.

```python
def planner_node(state: ResearchPilotState) -> dict:
    route = planner.plan(state["user_request"])
    return {
        "route": route,
        "visited_nodes": state.get("visited_nodes", []) + ["planner"],
    }
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

4. Put existing subagents inside LangGraph nodes.

```python
def paper_node(state: ResearchPilotState) -> dict:
    result = paper_subagent.run(state["user_request"])
    return {
        "draft_answer": result.answer,
        "evidence": result.evidence,
        "metadata": result.metadata,
    }
```

5. Use conditional edges for reviewer fallback.

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

The key point:

```text
ResearchPilot's architecture is already graph-shaped, so migration to LangGraph is natural.
```

---

## 7. What did I learn by implementing the runtime myself?

The most important learning points are:

1. Agent workflows need explicit state management.
2. Planner routing should be observable and debuggable.
3. Tool execution results should be written back into shared state.
4. Reviewer feedback should be represented as routing decisions.
5. Trace logging is essential for debugging complex agent systems.
6. A graph-based design is easier to debug than a fully free-form agent loop.
7. Production frameworks such as LangGraph formalize these same ideas at a larger scale.

A concise interview answer:

> By implementing the runtime myself, I learned that agent orchestration is not only about prompting an LLM. The difficult part is state management, tool execution, routing, fallback, and observability. This helped me better understand why frameworks like LangGraph are designed around stateful graphs instead of simple sequential chains.

---

## 8. How is this different from a simple LangChain Agent?

A simple LangChain-style agent often follows a loop like:

```text
LLM decides action
  ↓
tool execution
  ↓
observation
  ↓
LLM decides next action
```

This is flexible, but it can be hard to control and debug.

ResearchPilot's graph workflow is more structured:

```text
prepare
  ↓
planner
  ↓
specialized subagent
  ↓
reviewer
  ↓
final
```

The difference is:

| Free-form agent loop                | Graph workflow                     |
| ----------------------------------- | ---------------------------------- |
| Flexible but less predictable       | More structured and controllable   |
| Tool choices are often model-driven | Routing can be explicit            |
| Harder to debug long traces         | Easier to inspect visited nodes    |
| Good for open-ended tasks           | Good for production-like workflows |

A good answer:

> I see free-form agent loops and graph workflows as complementary. Free-form loops are flexible, but graph workflows are easier to control, evaluate, and debug. ResearchPilot uses graph workflow as the default path because code QA and paper research are structured tasks that benefit from explicit routing and review.

---

## 9. How would I explain the project in 2 minutes?

A polished answer:

> ResearchPilot is a graph-based multi-agent research assistant. It supports codebase QA, paper research, and general question answering.
>
> The core workflow is organized as a graph: `prepare → planner → code/paper/general → reviewer → final`. The planner decides which subagent should handle the request, and the reviewer checks whether the generated answer is sufficient. If the answer is insufficient, the workflow can trigger fallback behavior such as additional retrieval or paper indexing.
>
> I implemented a lightweight `GraphWorkflowRuntime` myself, with node registration, conditional routing, shared state, visited path recording, and trace reporting. This design is conceptually similar to LangGraph's `StateGraph`.
>
> I also wrote a LangGraph demo that maps ResearchPilot's workflow into LangGraph nodes and conditional edges, and another wrapper demo that calls the real ResearchPilot paper workflow from inside a LangGraph node. This helped me understand both the internals of custom agent orchestration and how to integrate with mainstream frameworks.

---

## 10. How would I answer "Why not just use LangGraph?"

A strong answer:

> For a production system, I would seriously consider using LangGraph. It provides mature support for checkpointing, durable execution, streaming, persistence, and human-in-the-loop workflows.
>
> In this project, I intentionally implemented a lightweight graph runtime myself because I wanted to understand the underlying mechanics of graph-based agent orchestration. I wanted full visibility into how state is updated, how conditional routing works, how subagents communicate, and how trace reports are generated.
>
> After building this myself, I can better appreciate what LangGraph provides, and I can migrate the current workflow to LangGraph if the system needs stronger production-level orchestration.

---

## 11. How would I answer "What is the biggest difference between your runtime and LangGraph?"

A concise answer:

> My runtime is lightweight and project-specific. It focuses on planner routing, subagent execution, reviewer feedback, fallback, and trace logging.
>
> LangGraph is a general-purpose production framework. It provides more robust runtime features such as checkpointing, persistence, streaming, and human-in-the-loop.
>
> So the difference is not the basic abstraction. Both use state, nodes, and edges. The difference is maturity, ecosystem, and production readiness.

---

## 12. How would I answer "What would you improve next?"

A good answer:

> I would improve ResearchPilot in three directions.
>
> First, I would add stronger persistence and checkpointing, so that long-running paper research workflows can be resumed after interruption.
>
> Second, I would add streaming output for better user experience, especially for long answers and paper reports.
>
> Third, I would introduce more systematic evaluation for agent routing, retrieval quality, reviewer decisions, and final answer groundedness.
>
> If I were building a production version, I would consider migrating the graph runtime to LangGraph while keeping the existing subagents and paper workflow logic.

---

## 13. Key takeaway

The key takeaway is:

```text
ResearchPilot demonstrates hands-on understanding of graph-based agent orchestration.
```

It is not just a wrapper around an existing framework.

It manually implements:

```text
AgentLoop
ToolRuntime
GraphWorkflowRuntime
shared state
conditional routing
subagent orchestration
reviewer feedback
fallback
trace report
FastAPI service
Docker deployment
```

LangGraph provides a more mature framework for many of these ideas.

So the best way to position the project is:

> ResearchPilot is a custom lightweight graph-based multi-agent research assistant, inspired by modern agent workflow systems such as LangGraph. It demonstrates that I understand both the engineering mechanics and the framework-level abstractions behind agentic RAG systems.

```
```
