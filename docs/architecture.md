# ResearchPilot 架构说明

本文档用于说明 ResearchPilot 的系统架构。ResearchPilot 是一个类 Claude Code 的 Agent Harness 项目，主要面向论文研究、论文问答、文献下载、基于证据的回答生成和答案质量评价。

项目的核心思想是：

> LLM 负责理解、推理和生成；确定性 workflow、结构化工具、Evidence Store、Trace 和 Evaluation 负责稳定性、可追踪性和可评估性。

---

## 1. 总体架构

ResearchPilot 可以分成三层：

```text
用户入口层
  ↓
Agent / Workflow 编排层
  ↓
工具 / 证据 / 外部后端层
```

整体架构如下：

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
  ├── Evidence answer tool
  └── Evaluation tools
  ↓
Evidence Store
  ↓
Citation-aware Answer Writer
  ↓
Final Answer / Report / Trace / Evaluation
```

ResearchPilot 同时支持两类执行方式：

```text
1. Agent Mode
   由 LLM 自主决定下一步调用哪个工具。

2. Workflow Mode
   对稳定高频任务使用确定性流程编排。
```

---

## 2. 两种执行模式

### 2.1 Agent Mode：自由工具调用模式

Agent Mode 使用 LLM Policy 根据当前上下文生成下一个结构化动作。

示例命令：

```bash
research-pilot run --policy llm "Inspect this project and save a short note."
```

执行流程：

```text
User goal
  ↓
AgentLoop
  ↓
ContextManager 构造上下文
  ↓
LLMAgentPolicy 生成 AgentAction
  ↓
ToolRuntime 执行工具
  ↓
返回 Observation
  ↓
更新 AgentState 和 Trace
  ↓
重复直到 final_answer
```

Agent Mode 适合调试：

```text
工具调用能力
Prompt 设计
Agent 多步执行逻辑
Trace 是否正确保存
Todo / Hook 是否生效
开放式任务探索
```

但是对于稳定任务，完全依赖 LLM 自主选择工具会有风险。例如：

```text
LLM 可能选错工具
LLM 可能忘记保存报告
LLM 可能直接 read_file 读取 PDF
LLM 可能把 citation-aware answer 压缩成弱总结
LLM 可能在不合适的时机重建 Chroma index
```

所以项目引入了 Workflow Mode。

---

### 2.2 Workflow Mode：确定性流程模式

Workflow Mode 用代码固定高价值任务的执行路径。

示例命令：

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
```

执行流程：

```text
Question
  ↓
PaperWorkflowRunner
  ↓
engineered_rag_search
  ↓
write_evidence_answer
  ↓
optional save_report
  ↓
final_answer
```

Workflow Mode 的特点是：

```text
工具顺序由代码控制
LLM 负责语言理解和生成
系统整体更稳定
输出更可复现
更适合真实使用和项目展示
```

---

## 3. Core Runtime 核心模块

核心代码位于：

```text
src/research_pilot/core/
```

---

### 3.1 AgentAction

文件：

```text
src/research_pilot/core/action.py
```

`AgentAction` 表示 Agent 的结构化动作。

主要有两类：

```text
tool_call
final_answer
```

一个工具调用动作类似：

```python
AgentAction(
    action_type="tool_call",
    tool_name="read_file",
    tool_input={"path": "README.md"},
    thought_summary="Read the README to understand the project."
)
```

一个最终回答动作类似：

```python
AgentAction(
    action_type="final_answer",
    final_answer="Here is the result...",
    thought_summary="The task is complete."
)
```

这个设计的意义是：

> LLM 不直接执行任意代码，而是输出结构化动作；真正的执行由 ToolRuntime 控制。

---

### 3.2 Observation

文件：

```text
src/research_pilot/core/observation.py
```

`Observation` 是工具执行后的标准返回格式。

包含：

```python
success: bool
content: str
metadata: dict
error: str | None
```

成功示例：

```python
Observation(
    success=True,
    content="Retrieved evidence chunks...",
    metadata={"num_docs": 6, "sources": [...]}
)
```

失败示例：

```python
Observation(
    success=False,
    content="Missing input: query",
    error="MissingQuery"
)
```

统一 Observation 的好处是：所有工具都能用同一种方式进入 AgentState、TraceStore 和 EvidenceStore。

---

### 3.3 AgentState 和 AgentStep

文件：

```text
src/research_pilot/core/state.py
```

`AgentState` 保存一次运行的完整状态，包括：

```text
用户目标
执行步骤
notes
todo list
evidence store
final answer
```

每一步由 `AgentStep` 表示：

```python
step_id: int
action: AgentAction
observation: Observation | None
```

这样可以完整重建一次 Agent 运行过程。

---

### 3.4 Tool 接口

文件：

```text
src/research_pilot/core/tool.py
```

所有工具都遵循统一接口：

```python
class BaseTool:
    name: str
    description: str

    def spec(self) -> ToolSpec:
        ...

    def run(self, tool_input: dict, state=None) -> Observation:
        ...
```

这样不同类型的工具都能被 ToolRuntime 统一管理，例如：

```text
文件读取工具
shell 工具
web search 工具
paper download 工具
external RAG 工具
answer writer 工具
report 工具
evaluation 工具
```

---

### 3.5 ToolRuntime

文件：

```text
src/research_pilot/core/tool_runtime.py
```

`ToolRuntime` 负责：

```text
注册工具
根据 tool_name 查找工具
做权限检查
执行工具
返回 Observation
```

执行流程：

```text
AgentAction
  ↓
ToolRuntime.execute()
  ↓
PermissionChecker
  ↓
tool.run()
  ↓
Observation
```

它把“LLM 决策”和“工具执行”分离开来。LLM 负责决定想做什么，但工具是否允许执行、如何执行，由 Runtime 控制。

---

### 3.6 PermissionChecker

文件：

```text
src/research_pilot/core/permission.py
```

`PermissionChecker` 用来阻止危险操作，例如：

```text
读取敏感文件
写入不允许的位置
执行危险 shell 命令
```

因为 LLM 生成的动作不能完全信任，所以工具执行前需要有安全检查。

这也是 ResearchPilot 更像 Agent Harness，而不是普通脚本的重要原因。

---

### 3.7 ContextManager

文件：

```text
src/research_pilot/core/context_manager.py
```

`ContextManager` 负责把当前状态转换成 LLM 可读上下文。

可能包含：

```text
用户目标
可用工具列表
历史 steps
工具 observations
todo list
hook reminder
evidence summary
```

也就是说，它负责把运行时状态注入 prompt。

---

### 3.8 TraceStore

文件：

```text
src/research_pilot/core/trace.py
```

`TraceStore` 保存每一步执行记录，包括：

```text
step id
action
observation
final state
```

Trace 的作用：

```text
调试工具调用
分析 LLM 决策
定位 workflow 失败原因
展示 Agent 执行透明性
作为 evaluation 的辅助信息
```

默认输出位置：

```text
workspace/traces/
```

---

### 3.9 Todo 和 Hooks

相关文件：

```text
src/research_pilot/core/todo.py
src/research_pilot/core/hooks.py
src/research_pilot/tools/todo_tool.py
```

Todo 系统用于维护运行时任务状态：

```text
pending
in_progress
completed
cancelled
```

Hook 系统用于运行时提醒。例如，如果 Agent 有未完成的 todo，但已经多步没有更新 todo，Hook 可以注入 reminder 到上下文中。

这个设计参考了 Claude Code 一类 coding agent 的实践：长任务中使用 todo 可以帮助 Agent 不跑偏。

---

## 4. AgentLoop

文件：

```text
src/research_pilot/core/agent_loop.py
```

AgentLoop 是 Agent Mode 的核心控制循环。

简化流程：

```text
初始化 AgentState
  ↓
for step in max_steps:
    构造上下文
    调用 policy 得到 AgentAction
    如果是 final_answer，则结束
    否则通过 ToolRuntime 执行工具
    保存 AgentStep
    更新 TraceStore
    运行 Hooks
  ↓
返回最终 AgentState
```

核心设计是职责分离：

```text
LLM Policy
    负责决定下一步动作

ToolRuntime
    负责安全执行动作

AgentState
    负责保存运行状态

TraceStore
    负责记录执行过程

Hooks
    负责运行时控制
```

---

## 5. LLM Policy

文件：

```text
src/research_pilot/agents/llm_agent.py
```

`LLMAgentPolicy` 负责把上下文转换成结构化 JSON action。

模型需要输出：

```json
{
  "action_type": "tool_call",
  "tool_name": "list_files",
  "tool_input": {"path": "."},
  "thought_summary": "Inspect the project structure."
}
```

或者：

```json
{
  "action_type": "final_answer",
  "final_answer": "Here is the result...",
  "thought_summary": "The task is complete."
}
```

为了让 LLM 输出更稳定，Policy 中包含一些兼容逻辑：

```text
从 markdown code fence 中提取 JSON
把 tool 归一化成 tool_call
把 arguments / input 归一化成 tool_input
检查 tool_name 是否存在
对 write_evidence_answer 做 passthrough，避免最终答案被二次压缩
```

---

## 6. Evidence Store

文件：

```text
src/research_pilot/core/evidence.py
```

`EvidenceStore` 是 ResearchPilot 的关键设计之一。

它统一保存工具产生的证据，例如：

```text
web search 结果
note
report
paper chunk
RAG retrieval 结果
generated answer
```

每个 EvidenceItem 包含：

```python
evidence_type
source
content
metadata
```

对于论文 RAG，metadata 中可以保存结构化 evidence blocks：

```python
{
    "source_id": 1,
    "file": "01_2510.25518v1.pdf",
    "page": 2,
    "chunk_id": 236,
    "content": "..."
}
```

这样 Answer Writer 可以基于结构化证据生成带引用的回答，而不是泛泛总结。

---

## 7. 论文研究架构

论文研究是目前项目最完整的功能线。

它组合了：

```text
paper_search
paper_download
engineered_rag_index
engineered_rag_search
write_evidence_answer
save_report
eval-paper
```

---

### 7.1 Paper Collection

命令：

```bash
research-pilot paper-collect "agentic RAG architecture" --max-papers 3
```

流程：

```text
topic
  ↓
paper_search
  ↓
paper_download
  ↓
engineered_rag_index
  ↓
collection note
```

`paper_download` 支持去重机制，会维护下载索引，避免重复下载同一篇 arXiv 论文。

---

### 7.2 Paper Answer

命令：

```bash
research-pilot paper-answer "What is the architecture of agentic RAG?"
```

流程：

```text
question
  ↓
engineered_rag_search
  ↓
structured evidence blocks
  ↓
write_evidence_answer
  ↓
final answer
```

这是最稳定的论文问答 workflow。

---

### 7.3 Local-first Paper Research

命令：

```bash
research-pilot paper-research "What is the architecture of agentic RAG?"
```

流程：

```text
question
  ↓
检索本地 indexed papers
  ↓
证据是否足够？
      ├── 足够
      │     ↓
      │   write_evidence_answer
      │     ↓
      │   save_report
      │
      └── 不足
            ↓
          paper_download
            ↓
          engineered_rag_index
            ↓
          再次检索
            ↓
          write_evidence_answer
            ↓
          save_report
```

这个 workflow 的核心是 local-first：

```text
优先使用已有本地论文库
证据不足时再补充下载新论文
始终基于检索证据写答案
```

---

## 8. 外部 EngineeredRAG 集成

相关文件：

```text
src/research_pilot/tools/engineered_rag_tool.py
src/research_pilot/workers/engineered_rag_worker.py
```

ResearchPilot 集成外部项目：

```text
paper-rag-assistant
```

外部 EngineeredRAG 后端负责更复杂的检索逻辑：

```text
paper-level retrieval
dense vector retrieval
BM25 retrieval
hybrid retrieval
cross-encoder reranking
source-aware context formatting
```

ResearchPilot 将其包装成工具：

```text
engineered_rag_index
engineered_rag_search
engineered_rag_answer
```

这样的好处是：

```text
外部 RAG 后端专注检索质量
ResearchPilot 专注 Agent 编排、证据管理、workflow 和 evaluation
```

---

## 9. 为什么使用子进程 Worker？

在 Windows 上，Chroma 有时会锁住数据库文件。问题流程是：

```text
同一个 Python 进程：
    search Chroma
      ↓
    rebuild Chroma index
      ↓
    WinError 32 文件锁错误
```

ResearchPilot 的解决方案是：将 EngineeredRAG 的 index/search/answer 全部放到子进程中执行。

流程：

```text
主进程
  ↓
子进程执行 search
  ↓
子进程退出，释放 Chroma 文件句柄
  ↓
子进程执行 index
  ↓
子进程退出，释放 Chroma 文件句柄
```

这比下面这些临时方案更稳定：

```text
gc.collect()
time.sleep()
cache_clear()
```

因为子进程退出时，操作系统会可靠释放文件句柄。

---

## 10. Citation-aware Answer Writer

相关文件：

```text
src/research_pilot/agents/evidence_answer_writer_agent.py
src/research_pilot/tools/evidence_answer_tool.py
```

Answer Writer 接收：

```text
用户问题
结构化 evidence blocks
source id
file name
page number
chunk id
retrieved content
```

然后输出固定结构：

```markdown
## Answer

...

## Architecture Breakdown

...

## Explanation

...

## Sources Used

...

## Limitations

...
```

设计目标是：

```text
减少无依据回答
保留引用
保留文件名 / 页码 / chunk id
如果证据不足，要明确说明 limitation
```

---

## 11. Intent Router

文件：

```text
src/research_pilot/workflows/intent_router.py
```

`ask` 命令使用轻量级 Intent Router。

示例：

```bash
research-pilot ask "Download 3 papers about agentic RAG architecture."
```

路由逻辑：

```text
下载论文请求
  → paper_collect

论文相关问题
  → paper_answer

写报告请求
  → paper_research

其他开放任务
  → general agent mode
```

这个设计让用户可以自然语言提问，同时底层仍然走稳定 workflow。

---

## 12. Evaluation 架构

相关文件：

```text
src/research_pilot/evaluation/paper_eval.py
src/research_pilot/evaluation/llm_judge.py
eval/paper_eval_cases.jsonl
```

ResearchPilot 支持两层评价。

---

### 12.1 规则评价

命令：

```bash
research-pilot eval-paper
```

检查项：

```text
workflow 是否成功
是否没有 tool error
是否包含 ## Answer
是否包含 ## Sources Used
是否包含 ## Limitations
是否包含 citation marker
答案长度是否足够
需要保存报告时是否成功保存
```

这适合 regression test。

---

### 12.2 LLM Judge 评价

命令：

```bash
research-pilot eval-paper --llm-judge
```

LLM Judge 会评分：

```text
groundedness
citation_quality
completeness
clarity
hallucination_risk
overall_score
```

Judge 输入包括：

```text
原始问题
最终答案
检索证据
```

输出结构化 JSON，例如：

```json
{
  "groundedness": 4,
  "citation_quality": 4,
  "completeness": 4,
  "clarity": 5,
  "hallucination_risk": 4,
  "overall_score": 4.2,
  "verdict": "PASS",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "suggestions": ["..."]
}
```

---

## 13. 为什么不完全依赖 LLM 自由调用工具？

完全自由的 tool-calling agent 灵活，但不稳定。

可能出现：

```text
跳过检索直接回答
调用错误工具
直接读取 PDF 导致报错
忘记保存 report
回答没有 citation
把答案写成 summary 而不是 answer
在 Chroma 被锁时尝试重建 index
```

因此 ResearchPilot 使用混合策略：

```text
开放式任务
  → Agent Mode

稳定高频任务
  → Deterministic Workflow Mode
```

这也是项目的核心工程设计之一。

---

## 14. 和普通 RAG Demo 的区别

普通 RAG demo 通常是：

```text
加载文档
检索 chunk
生成答案
```

ResearchPilot 在此基础上增加了：

```text
Agent Harness
Tool Runtime
Permission Control
Trace Logging
Todo / Hooks
Evidence Store
Paper Workflows
Intent Router
Subprocess Worker
Citation-aware Writer
Evaluation Harness
```

所以这个项目的重点不仅是 retrieval，而是构建一个可追踪、可评估、可扩展的研究 Agent 系统。

---

## 15. 主要设计取舍

### 15.1 灵活性 vs 稳定性

Agent Mode 灵活，但不可预测。

Workflow Mode 稳定，但自由度较低。

ResearchPilot 保留两者。

---

### 15.2 复用外部 RAG vs 重写所有模块

ResearchPilot 复用 `paper-rag-assistant` 作为外部检索后端。

这样可以避免重复实现复杂检索逻辑，把精力集中在 Agent 编排和评价上。

---

### 15.3 规则评价 vs LLM Judge

规则评价稳定、便宜、可复现。

LLM Judge 评价更丰富，但依赖模型。

ResearchPilot 两者都支持。

---

### 15.4 进程内集成 vs 子进程隔离

进程内集成简单。

子进程隔离更适合解决 Chroma 文件锁问题。

ResearchPilot 对 EngineeredRAG 使用子进程 worker。

---

## 16. 当前局限

当前项目仍有一些局限：

```text
Intent Router 还是规则型，比较简单
答案质量依赖检索质量
LLM Judge 分数依赖所用模型
citation correctness 目前主要是结构性检查，还不是严格语义验证
项目重点目前是 paper research，还没有深入 codebase editing
没有 Web UI
长篇多章节报告写作还可以继续增强
```

---

## 17. 后续扩展方向

可以继续扩展：

```text
Codebase Agent：支持代码仓库理解和代码问答
多章节 Report Writer：支持 section-level citation
Streamlit / FastAPI Web UI
Evaluation Dashboard
更严格的 citation verification
多 RAG backend 支持
长期 memory
long-running research task
LLM-based intent router
```

---

## 18. 总结

ResearchPilot 不是一个单纯 RAG 脚本，而是一个 Agent Engineering 项目。

它结合了：

```text
Agent Runtime
Tool Execution
Permission Control
Evidence Management
Deterministic Workflows
External RAG Backend
Citation-aware Generation
Evaluation Harness
```

最重要的设计思想是：

> 让 LLM 负责理解、推理和生成；让结构化工具、确定性 workflow、Evidence Store、Trace 和 Evaluation 保证系统稳定、可追踪、可评估。
