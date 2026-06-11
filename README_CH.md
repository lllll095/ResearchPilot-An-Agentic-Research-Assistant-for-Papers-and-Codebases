# ResearchPilot 中文说明

**ResearchPilot** 是一个类 Claude Code 的 Agent Harness 项目，面向论文研究、深度研究和带引用的论文问答。

它不是一个简单的 RAG demo，而是实现了一套小型但完整的 Agent Runtime，包括：

* 结构化 Agent Action
* 工具执行运行时
* 权限检查
* Trace 日志
* Todo / Hook 机制
* Evidence Store 证据管理
* 确定性论文研究 Workflow
* 外部 EngineeredRAG 后端集成
* Citation-aware Answer Writer
* 规则评价与 LLM Judge 评价

项目目标是构建一个实用型研究助手：它可以搜索和下载论文，将论文同步到外部 RAG 后端进行索引，检索证据，生成带引用的答案，并对答案质量进行评价。

---

## 1. 项目概览

ResearchPilot 支持三种主要使用方式。

### 1.1 Agent Mode：自由工具调用模式

Agent Mode 允许 LLM 自己决定调用哪个工具。

```bash
research-pilot run --policy llm "Use engineered_rag_search to find evidence about agentic RAG architecture, then use write_evidence_answer to answer with citations."
```

这种模式适合调试：

* LLM 工具调用能力
* Agent 多步规划能力
* ToolRuntime 是否正常工作
* Prompt 对工具选择的影响
* Todo / Hook 是否生效

不过在真实使用中，它不一定最稳定，因为 LLM 可能会选错工具、忘记保存报告，或者把完整引用答案压缩成弱总结。

---

### 1.2 Workflow Mode：确定性流程模式

Workflow Mode 使用固定流程编排高频研究任务。

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
research-pilot paper-collect "agentic RAG architecture" --max-papers 3
research-pilot paper-research "What is the architecture of agentic RAG?"
```

这种模式更稳定，适合正式使用和项目展示。

---

### 1.3 Ask Mode：自然语言入口

`ask` 命令会先理解用户意图，然后自动路由到对应 workflow。

```bash
research-pilot ask "What is the architecture of agentic RAG?"
research-pilot ask "Download 3 papers about agentic RAG architecture."
research-pilot ask "Write a report about the architecture of agentic RAG." --save-report
```

也就是说，用户不需要知道底层工具名，系统会自动判断应该执行论文问答、论文下载，还是完整论文研究流程。

---

## 2. 核心功能

### 2.1 Agent Harness

ResearchPilot 从零实现了一个轻量级 Agent Runtime。

核心组件包括：

* `AgentLoop`：控制多步 Agent 执行循环。
* `AgentAction`：表示 LLM 产生的结构化动作。
* `Observation`：表示工具执行结果。
* `ToolRuntime`：负责注册和执行工具。
* `PermissionChecker`：阻止危险文件操作和 shell 命令。
* `TraceStore`：保存每一步执行 trace。
* `ContextManager`：为 LLM policy 构造上下文。
* `TodoWrite`：维护运行时任务列表。
* `HookManager`：提供类似提醒和运行时控制的机制。

这一层是整个项目的底层框架，使项目不只是一个脚本，而是一个可扩展的 Agent Harness。

---

### 2.2 论文研究 Workflows

ResearchPilot 实现了几个确定性论文 workflow。

#### `paper-answer`

使用已经索引的本地论文库回答问题。

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
```

流程：

```text
用户问题
  ↓
engineered_rag_search
  ↓
结构化证据块
  ↓
write_evidence_answer
  ↓
带引用答案
```

---

#### `paper-collect`

按照主题搜索、下载论文，并重建外部 RAG 索引。

```bash
research-pilot paper-collect "agentic RAG architecture" --max-papers 3
```

流程：

```text
研究主题
  ↓
paper_search
  ↓
paper_download
  ↓
engineered_rag_index
```

---

#### `paper-research`

Local-first 综合研究流程。

它会先查本地 indexed papers；如果本地证据足够，就直接回答；如果证据不足，则下载新论文、重建索引、重新检索并写报告。

```bash
research-pilot paper-research "What is the architecture of agentic RAG?"
```

流程：

```text
用户问题
  ↓
检索本地 indexed papers
  ↓
判断证据是否足够
  ├── 足够 → write_evidence_answer → save_report
  └── 不足 → paper_download → engineered_rag_index → 重新检索 → write_evidence_answer → save_report
```

---

### 2.3 外部 EngineeredRAG 集成

ResearchPilot 集成了外部项目 `paper-rag-assistant` 作为论文 RAG 后端。

外部 EngineeredRAG 后端负责：

* paper-level retrieval
* dense retrieval
* BM25 retrieval
* cross-encoder reranking
* source-aware context formatting
* grounded answer generation

ResearchPilot 不重复实现所有检索细节，而是把外部 RAG 后端作为 retrieval backend，然后在自己这边负责：

* Agent Harness
* Tool Runtime
* Workflow 编排
* Evidence Store
* Citation-aware Answer Writer
* Evaluation Harness

这样项目结构更模块化，也更接近真实工程。

---

### 2.4 子进程 Worker 解决 Chroma 文件锁

在 Windows 上，如果一个 Python 进程已经打开 Chroma 向量库，然后又尝试重建同一个 Chroma index，可能出现：

```text
PermissionError: [WinError 32]
另一个程序正在使用此文件，进程无法访问
```

ResearchPilot 使用 subprocess worker 解决这个问题。

设计思路：

```text
ResearchPilot 主进程
  ↓
EngineeredRAG 子进程执行 search / answer / index
  ↓
子进程结束
  ↓
Chroma 文件句柄释放
```

这样可以避免同一进程中：

```text
search 打开 chroma_db
  ↓
index 尝试删除或重建 chroma_db
  ↓
Windows 文件锁错误
```

这个设计让 `paper-research` 这种 local-first workflow 更稳定。

---

### 2.5 Citation-aware Answer Writer

ResearchPilot 会把检索到的论文 chunk 保存为结构化证据块：

```text
[Source 1]
File:
Page:
Chunk ID:
Content:
```

然后 `write_evidence_answer` 会基于这些证据生成带引用的答案。

标准输出结构为：

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

这样比普通 summary 更可靠，因为它保留了来源、页码、chunk id 和证据内容。

---

### 2.6 Evaluation Harness

ResearchPilot 内置论文 workflow 评价命令。

规则评价会检查：

* workflow 是否成功
* 是否存在 tool error
* 是否包含 `## Answer`
* 是否包含 `## Sources Used`
* 是否包含 `## Limitations`
* 是否包含 citation marker
* 答案长度是否过短
* 是否成功保存报告

运行：

```bash
research-pilot eval-paper
```

LLM Judge 评价会进一步评分：

* groundedness：答案是否基于证据
* citation_quality：引用是否合理
* completeness：回答是否完整
* clarity：表达是否清晰
* hallucination_risk：幻觉风险
* overall_score：综合质量

运行：

```bash
research-pilot eval-paper --max-cases 1 --llm-judge
```

评价结果会保存在：

```text
workspace/eval_runs/
```

---

## 3. 系统架构

整体架构：

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

论文问答 workflow：

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

Local-first 论文研究 workflow：

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

## 4. 安装方式

### 4.1 创建 conda 环境

```bash
conda create -n research-pilot python=3.10
conda activate research-pilot
```

### 4.2 安装项目

在 ResearchPilot 项目根目录运行：

```bash
pip install -e .
```

`-e` 表示 editable install。之后你修改源码，命令行工具会直接使用最新代码。

### 4.3 安装依赖

根据使用功能安装：

```bash
pip install python-dotenv pydantic pydantic-settings typer rich openai
pip install tavily-python
pip install pypdf
pip install certifi
```

外部 `paper-rag-assistant` 项目还需要额外依赖，例如：

* Chroma
* sentence-transformers
* BM25
* reranker 相关依赖

---

## 5. 环境变量配置

在 ResearchPilot 项目根目录创建 `.env` 文件。

示例：

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

不要把 `.env` 上传到 GitHub。

确保 `.gitignore` 包含：

```gitignore
.env
workspace/
*.log
```

---

## 6. 常用命令

### 6.1 General Agent Run

Mock policy：

```bash
research-pilot run --policy mock "analyze this project"
```

LLM policy：

```bash
research-pilot run --policy llm "Inspect this project and save a short note."
```

这个模式适合调试 Agent 自主工具调用。

---

### 6.2 论文问答

基于 indexed papers 回答：

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
```

保存为报告：

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?" --save-report
```

---

### 6.3 搜索下载论文

搜索并下载论文：

```bash
research-pilot paper-collect "agentic RAG architecture" --max-papers 3
```

下载但不重建索引：

```bash
research-pilot paper-collect "agentic RAG architecture" --max-papers 3 --no-rebuild-index
```

---

### 6.4 Local-first 论文研究

完整 local-first workflow：

```bash
research-pilot paper-research "What is the architecture of agentic RAG?"
```

强制下载新论文：

```bash
research-pilot paper-research "What is the architecture of agentic RAG?" --force-download --max-papers 2
```

提高本地证据要求：

```bash
research-pilot paper-research "What is the architecture of agentic RAG?" --min-sources 5
```

不保存报告：

```bash
research-pilot paper-research "What is the architecture of agentic RAG?" --no-save-report
```

---

### 6.5 自然语言 ask

直接自然语言提问：

```bash
research-pilot ask "What is the architecture of agentic RAG?"
```

要求下载论文：

```bash
research-pilot ask "Download 3 papers about agentic RAG architecture."
```

要求写报告：

```bash
research-pilot ask "Write a report about the architecture of agentic RAG." --save-report
```

强制下载新论文并写报告：

```bash
research-pilot ask "What is the architecture of agentic RAG?" --force-download --save-report
```

---

### 6.6 评价

运行规则评价：

```bash
research-pilot eval-paper
```

只跑一个 case：

```bash
research-pilot eval-paper --max-cases 1
```

运行 LLM Judge 评价：

```bash
research-pilot eval-paper --max-cases 1 --llm-judge
```

结果保存在：

```text
workspace/eval_runs/
```

---

## 7. 项目结构

```text
ResearchPilot/
├── README.md
├── README_zh.md
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

## 8. 设计亮点

### 8.1 不是简单脚本，而是 Agent Runtime

ResearchPilot 将以下概念拆开：

```text
LLM policy
Tool runtime
State
Observation
Trace
Permission
Context
Evidence
```

这样项目更接近真实 Agent 系统，而不是一次性 demo 脚本。

---

### 8.2 用确定性 Workflow 提高稳定性

不是所有任务都应该交给 LLM 自由决定。

对于论文问答这种高频任务，ResearchPilot 使用固定 workflow：

```text
检索证据 → 写引用答案 → 保存报告
```

LLM 仍然负责语言理解和生成，但工具调用顺序由 workflow 保证。

这样可以减少：

* LLM 选错工具
* LLM 直接读 PDF 导致错误
* LLM 忘记保存报告
* LLM 把引用答案压缩成弱总结
* Chroma index 被锁住时仍尝试重建

---

### 8.3 外部 RAG 后端模块化

ResearchPilot 不重复造所有检索模块，而是集成成熟的外部 EngineeredRAG。

它自身重点放在：

* Agent 编排
* 证据管理
* workflow 控制
* citation-aware generation
* evaluation

这种设计更模块化，也方便未来替换成其他 RAG backend。

---

### 8.4 Evidence Store

所有重要工具输出都可以进入统一的 `EvidenceStore`。

Citation-aware Answer Writer 从 EvidenceStore 中读取结构化证据，生成带来源的回答。

---

### 8.5 LLM Judge Evaluation

ResearchPilot 支持规则评价和 LLM Judge 评价。

这让你可以持续观察：

* prompt 改动是否让答案变差
* workflow 改动是否影响稳定性
* citation 是否还可靠
* retrieval 是否支持最终回答

---

## 9. 示例输出

问题：

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
```

示例输出结构：

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

## 10. 评价示例

运行：

```bash
research-pilot eval-paper --max-cases 1 --llm-judge
```

示例 LLM Judge 输出：

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

## 11. 项目 Roadmap

后续可以继续扩展：

* Codebase Agent：支持代码仓库理解和代码问答。
* Streamlit / FastAPI Web UI。
* Evaluation Dashboard。
* 更强的 LLM intent router。
* 多阶段报告写作器。
* 更严格的 source verification。
* 支持多个外部 RAG backend。
* 支持长期 memory 和 long-running research tasks。

---

## 12. 开发常用命令

Git 提交：

```bash
git status
git add .
git commit -m "your commit message"
```

运行测试：

```bash
pytest
```

运行评价：

```bash
research-pilot eval-paper --llm-judge
```

查看生成文件：

```text
workspace/reports/
workspace/traces/
workspace/eval_runs/
workspace/documents/
```

注意不要误删外部 `paper-rag-assistant` 的 index，除非你准备重新构建。

---

## 13. 项目定位

ResearchPilot 是一个面向 Agent Engineering 学习和求职展示的项目。

它展示了：

* 如何从零实现 Agent Loop
* 如何设计 Tool 接口
* 如何管理 Agent 运行状态
* 如何结合 LLM 自主工具调用与确定性 workflow
* 如何接入外部 RAG 后端
* 如何生成 citation-aware research answer
* 如何设计 paper workflow evaluation harness

核心思想是：

> LLM 负责理解、推理和生成；确定性 workflow、结构化证据和 evaluation harness 负责稳定性、可追踪性和可评估性。
