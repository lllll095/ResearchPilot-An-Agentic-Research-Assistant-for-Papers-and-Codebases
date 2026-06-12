# ResearchPilot

**ResearchPilot** is a Claude Code-like Agent Harness for paper research, deep research, and citation-aware question answering.

It is not only a RAG demo. The project implements a small but complete agent runtime:

* structured agent actions
* tool execution runtime
* permission checking
* trace logging
* todo / hook mechanism
* evidence store
* deterministic paper workflows
* external EngineeredRAG integration
* citation-aware answer writer
* rule-based and LLM-judge evaluation

The goal is to build a practical research assistant that can search and download papers, index them into an external RAG backend, retrieve evidence, generate grounded answers with citations, and evaluate answer quality.

---

## 1. Project Overview

ResearchPilot supports two usage modes.

### 1.1 Agent Mode

Agent mode lets an LLM decide which tool to call.

```bash
research-pilot run --policy llm "Use engineered_rag_search to find evidence about agentic RAG architecture, then use write_evidence_answer to answer with citations."
```

This mode is useful for debugging tool calling, agent planning, and open-ended experiments.

### 1.2 Workflow Mode

Workflow mode uses deterministic orchestration for high-value research tasks.

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
research-pilot paper-collect "agentic RAG architecture" --max-papers 3
research-pilot paper-research "What is the architecture of agentic RAG?"
```

This mode is more stable and suitable for real use.

### 1.3 Natural Language Ask Mode

The `ask` command routes a natural language request to the appropriate workflow.

```bash
research-pilot ask "What is the architecture of agentic RAG?"
research-pilot ask "Download 3 papers about agentic RAG architecture."
research-pilot ask "Write a report about the architecture of agentic RAG." --save-report
```

---

## 2. Key Features

### Agent Harness

ResearchPilot implements a lightweight agent runtime from scratch.

Core components include:

* `AgentLoop`: controls the multi-step reasoning and tool-use loop.
* `AgentAction`: represents structured LLM actions.
* `Observation`: represents tool execution results.
* `ToolRuntime`: registers and executes tools.
* `PermissionChecker`: blocks unsafe file and shell operations.
* `TraceStore`: saves step-level execution traces.
* `ContextManager`: builds context for the LLM policy.
* `TodoWrite`: maintains runtime task state.
* `HookManager`: provides reminder-style runtime control.

### Paper Research Workflows

ResearchPilot provides deterministic workflows for common paper tasks:

* `paper-answer`: answer using already indexed papers.
* `paper-collect`: search, download, and index papers.
* `paper-research`: local-first research workflow. It first searches the local indexed library; if evidence is insufficient, it can download new papers, rebuild the index, retrieve again, and write a report.

### External EngineeredRAG Integration

ResearchPilot integrates an existing external paper RAG backend, `paper-rag-assistant`.

The external backend provides:

* paper-level retrieval
* dense retrieval
* BM25 retrieval
* cross-encoder reranking
* source-aware context formatting
* grounded answer generation

ResearchPilot uses it as a retrieval backend while keeping its own agent harness, workflows, evidence store, and evaluation system.

### Subprocess Worker for Chroma Stability

On Windows, Chroma can lock database files when a process searches the vector store and then tries to rebuild the index.

ResearchPilot solves this by running EngineeredRAG operations in subprocess workers:

```text
ResearchPilot main process
    ↓
EngineeredRAG subprocess: search / answer / index
    ↓
subprocess exits
    ↓
Chroma file handles are released
```

This avoids `WinError 32` file-lock errors during local-first workflows.

### Citation-aware Answer Writer

ResearchPilot stores retrieved chunks as structured evidence blocks:

```text
[Source 1]
File:
Page:
Chunk ID:
Content:
```

Then the answer writer generates answers with:

* direct answer
* architecture breakdown
* explanation
* sources used
* limitations

Example output structure:

```markdown
## Answer

...

## Architecture Breakdown

- Query Reformulator Agent ... [Source 1]
- Retriever Agent ... [Source 2]
- Evidence Assessment Module ... [Source 3]

## Explanation

...

## Sources Used

- [Source 1] file name, page, chunk id: what it supports.

## Limitations

...
```

### Evaluation Harness

ResearchPilot includes evaluation commands for paper workflows.

Rule-based evaluation checks:

* workflow success
* tool errors
* answer section
* sources section
* limitations section
* citation markers
* answer length
* report saving

LLM-judge evaluation additionally scores:

* groundedness
* citation quality
* completeness
* clarity
* hallucination risk
* overall score

Run evaluation:

```bash
research-pilot eval-paper
research-pilot eval-paper --max-cases 1 --llm-judge
```

Evaluation results are saved to:

```text
workspace/eval_runs/
```

---

## 3. System Architecture

High-level architecture:

```text
User
  ↓
CLI
  ↓
Intent Router / Agent Loop / Workflow Runner
  ↓
Tool Runtime
  ↓
Tools
  ├── File tools
  ├── Note tool
  ├── Report tool
  ├── Web search tool
  ├── Paper search/download tools
  ├── EngineeredRAG tools
  └── Evidence answer tool
  ↓
Evidence Store
  ↓
Citation-aware Answer Writer
  ↓
Final Answer / Report / Trace / Evaluation
```

Paper QA workflow:

```text
Question
  ↓
engineered_rag_search
  ↓
structured evidence blocks
  ↓
write_evidence_answer
  ↓
citation-aware answer
  ↓
optional save_report
```

Local-first paper research workflow:

```text
Question
  ↓
Search local indexed papers
  ↓
Evidence sufficient?
  ├── yes → write_evidence_answer → save_report
  └── no  → paper_download → engineered_rag_index → search again → write_evidence_answer → save_report
```

---

## 4. Installation

### 4.1 Create environment

Using conda:

```bash
conda create -n research-pilot python=3.10
conda activate research-pilot
```

### 4.2 Install project

From the project root:

```bash
pip install -e .
```

### 4.3 Install optional dependencies

Depending on which tools you use, install:

```bash
pip install python-dotenv pydantic pydantic-settings typer rich openai
pip install tavily-python
pip install pypdf
pip install certifi
```

The external `paper-rag-assistant` project may require additional dependencies such as Chroma, sentence-transformers, BM25, and reranker-related packages.

---

## 5. Environment Variables

Create a `.env` file in the ResearchPilot project root.

Example:

```env
OPENAI_API_KEY=your_openai_compatible_key
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_MODEL=your-model-name

TAVILY_API_KEY=your_tavily_key
WEB_SEARCH_BACKEND=tavily

PAPER_RAG_ASSISTANT_ROOT=C:\Users\your_name\Desktop\Working\paper-rag-assistant

DASHSCOPE_API_KEY=your_dashscope_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus

MAX_PAPER_DOWNLOADS=3
```

Do not commit `.env` to GitHub.

Make sure `.gitignore` contains:

```gitignore
.env
workspace/
*.log
```

---

## 6. Main Commands

### 6.1 General Agent Run

```bash
research-pilot run --policy mock "analyze this project"
```

```bash
research-pilot run --policy llm "Inspect this project and save a short note."
```

Agent mode is useful for testing LLM tool-use behavior.

---

### 6.2 Paper Answer

Answer a question using indexed papers:

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
```

Save the answer as a report:

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?" --save-report
```

---

### 6.3 Paper Collection

Search and download papers:

```bash
research-pilot paper-collect "agentic RAG architecture" --max-papers 3
```

Download papers without rebuilding the index:

```bash
research-pilot paper-collect "agentic RAG architecture" --max-papers 3 --no-rebuild-index
```

---

### 6.4 Local-first Paper Research

Run the full local-first workflow:

```bash
research-pilot paper-research "What is the architecture of agentic RAG?"
```

Force downloading new papers before answering:

```bash
research-pilot paper-research "What is the architecture of agentic RAG?" --force-download --max-papers 2
```

Require more local sources before skipping download:

```bash
research-pilot paper-research "What is the architecture of agentic RAG?" --min-sources 5
```

Disable report saving:

```bash
research-pilot paper-research "What is the architecture of agentic RAG?" --no-save-report
```

---

### 6.5 Natural Language Ask

Ask a broad natural language question:

```bash
research-pilot ask "What is the architecture of agentic RAG?"
```

Ask it to download papers:

```bash
research-pilot ask "Download 3 papers about agentic RAG architecture."
```

Ask it to write a report:

```bash
research-pilot ask "Write a report about the architecture of agentic RAG." --save-report
```

Force new paper collection:

```bash
research-pilot ask "What is the architecture of agentic RAG?" --force-download --save-report
```

---

### 6.6 Evaluation

Run rule-based evaluation:

```bash
research-pilot eval-paper
```

Run one evaluation case:

```bash
research-pilot eval-paper --max-cases 1
```

Run LLM judge evaluation:

```bash
research-pilot eval-paper --max-cases 1 --llm-judge
```

The evaluation outputs are saved under:

```text
workspace/eval_runs/
```

---

## 7. Project Structure

```text
ResearchPilot/
├── README.md
├── pyproject.toml
├── .env.example
├── eval/
│   └── paper_eval_cases.jsonl
├── docs/
│   ├── architecture.md
│   ├── demo_script.md
│   └── interview_guide.md
├── src/
│   └── research_pilot/
│       ├── agents/
│       │   ├── llm_agent.py
│       │   ├── mock_agent.py
│       │   ├── research_planner_agent.py
│       │   ├── task_summarizer_agent.py
│       │   └── evidence_answer_writer_agent.py
│       ├── core/
│       │   ├── action.py
│       │   ├── agent_loop.py
│       │   ├── context_manager.py
│       │   ├── evidence.py
│       │   ├── hooks.py
│       │   ├── llm_client.py
│       │   ├── observation.py
│       │   ├── permission.py
│       │   ├── state.py
│       │   ├── todo.py
│       │   ├── tool.py
│       │   ├── tool_runtime.py
│       │   └── trace.py
│       ├── evaluation/
│       │   ├── paper_eval.py
│       │   └── llm_judge.py
│       ├── tools/
│       │   ├── file_tools.py
│       │   ├── note_tool.py
│       │   ├── report_tool.py
│       │   ├── shell_tool.py
│       │   ├── todo_tool.py
│       │   ├── web_search_tool.py
│       │   ├── paper_tools.py
│       │   ├── engineered_rag_tool.py
│       │   ├── summarize_tool.py
│       │   └── evidence_answer_tool.py
│       ├── workflows/
│       │   ├── intent_router.py
│       │   └── paper_workflows.py
│       ├── workers/
│       │   └── engineered_rag_worker.py
│       ├── cli.py
│       └── config.py
├── tests/
└── workspace/
    ├── documents/
    ├── reports/
    ├── notes/
    ├── traces/
    └── eval_runs/
```

---

## 8. Design Highlights

### 8.1 Agent Runtime Instead of Simple Script

ResearchPilot separates:

```text
LLM policy
tool runtime
state
observation
trace
permission
context
```

This makes the project closer to a real agent runtime instead of a one-off script.

### 8.2 Deterministic Workflows for Stability

Not every task should be fully delegated to the LLM.

For stable high-frequency tasks such as paper QA, ResearchPilot uses deterministic workflows:

```text
retrieve evidence → write grounded answer → save report
```

The LLM is still used for language understanding and answer generation, but the tool order is controlled by the workflow.

This reduces errors such as:

* selecting the wrong tool
* reading PDF files directly as text
* forgetting to save a report
* compressing citation-aware answers into weak summaries
* rebuilding a Chroma index while it is locked

### 8.3 External RAG as Backend

ResearchPilot does not reimplement every retrieval technique.

Instead, it integrates an external EngineeredRAG backend and focuses on:

* agent orchestration
* evidence management
* workflow control
* evaluation
* user-facing commands

This makes the system modular.

### 8.4 Evidence Store

Every important tool output can be written into a central `EvidenceStore`.

The answer writer reads structured evidence from this store and produces citation-aware responses.

### 8.5 LLM Judge Evaluation

ResearchPilot supports both rule-based and LLM-based evaluation.

This makes it easier to track whether changes to prompts, workflows, or retrieval logic improve or degrade answer quality.

---

## 9. Example Output

Example question:

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
```

Example answer structure:

```markdown
## Answer

Agentic RAG extends standard Retrieval-Augmented Generation by introducing specialized agents for query reformulation, retrieval, evidence assessment, iterative refinement, and final synthesis [Source 1], [Source 2].

## Architecture Breakdown

- Query Reformulator Agent: refines the user's question into retrieval-optimized queries [Source 2].
- Retriever Agent: retrieves relevant evidence chunks from the indexed paper collection [Source 2].
- Structured Evidence Assessment Module: checks whether the retrieved evidence is sufficient and identifies information gaps [Source 6].
- Adaptive Query Refinement Agent: generates new sub-queries when evidence is insufficient [Source 6].
- Context Re-ranking: improves relevance using cross-encoder reranking [Source 3].

## Explanation

...

## Sources Used

- [Source 1] file name, page, chunk id: what it supports.
- [Source 2] file name, page, chunk id: what it supports.

## Limitations

The retrieved evidence may not contain complete architectural diagrams or implementation-level details.
```

---

## 10. Evaluation Example

Run:

```bash
research-pilot eval-paper --max-cases 1 --llm-judge
```

Example LLM judge result:

```json
{
  "groundedness": 4,
  "citation_quality": 4,
  "completeness": 4,
  "clarity": 5,
  "hallucination_risk": 4,
  "overall_score": 4.2,
  "verdict": "PASS",
  "strengths": [
    "The answer is clearly structured.",
    "Most key claims are supported by source citations."
  ],
  "weaknesses": [
    "Some implementation details are still missing."
  ],
  "suggestions": [
    "Retrieve additional chunks containing architectural diagrams or method details."
  ]
}
```

---

## 11. Roadmap

Planned extensions:

* Codebase Agent for repository understanding.
* Streamlit or FastAPI web UI.
* Evaluation dashboard.
* Better LLM-based intent routing.
* Multi-step report writer with section-level citations.
* More robust source verification.
* Support for multiple external RAG backends.
* Memory and long-running research tasks.

---

## 12. Development Notes

Useful commands:

```bash
git status
git add .
git commit -m "your commit message"
```

Run tests:

```bash
pytest
```

Run evaluation:

```bash
research-pilot eval-paper --llm-judge
```

Clean generated workspace files manually if needed:

```text
workspace/reports/
workspace/traces/
workspace/eval_runs/
workspace/documents/
```

Do not delete the external `paper-rag-assistant` index unless you plan to rebuild it.

---

## 13. Project Positioning

ResearchPilot is designed as a learning and portfolio project for agent engineering.

It demonstrates:

* how to implement an agent loop from scratch
* how to design tool interfaces
* how to manage runtime state
* how to combine autonomous tool use with deterministic workflows
* how to integrate an external RAG backend
* how to build citation-aware research answers
* how to evaluate workflow quality

The core idea is:

> Use LLMs for reasoning and generation, but use deterministic workflows, structured evidence, and evaluation harnesses to make the system stable and inspectable.

## Current Project Status

ResearchPilot currently supports two major capabilities:

### 1. Paper Research Agent

The paper research workflow supports:

* Searching and downloading papers.
* Building or updating a local paper index.
* Querying indexed papers through the external EngineeredRAG backend.
* Generating citation-aware answers from retrieved evidence.
* Saving reports.
* Evaluating paper answers through rule-based checks and optional LLM judge.

Main commands:

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
research-pilot paper-collect "agentic RAG architecture" --max-papers 3
research-pilot paper-research "Write a report about agentic RAG architecture."
research-pilot eval-paper
research-pilot eval-paper --llm-judge
```

### 2. Codebase Understanding Agent

The codebase workflow supports:

* Mapping the project source tree.
* Searching code files.
* Reading code files with line numbers.
* Generating grounded codebase explanations.
* Routing codebase questions from the general `ask` command.
* Evaluating code answers through rule-based checks.

Main commands:

```bash
research-pilot code-answer "Explain how AgentLoop works in this project."
research-pilot ask "AgentLoop 是怎么实现的？"
research-pilot eval-code
```

### Design Philosophy

ResearchPilot follows a hybrid agent design:

```text
LLM reasoning + structured tools + deterministic workflows + evidence store + trace + evaluation
```

The goal is not only to make the agent answer questions, but also to make its behavior traceable, inspectable, and evaluable.
