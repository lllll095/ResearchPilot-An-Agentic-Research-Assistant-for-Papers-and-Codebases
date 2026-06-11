# ResearchPilot 面试讲解稿

本文档用于面试或项目答辩时讲解 ResearchPilot。它不是命令手册，而是帮助你把项目讲清楚。

---

## 1. 项目一句话介绍

ResearchPilot 是一个类 Claude Code 的 Agent Harness，用于论文研究、论文下载、基于本地论文库的 RAG 问答、带引用答案生成和答案质量评价。

更完整的说法是：

> ResearchPilot 是一个面向论文研究场景的 Agent Engineering 项目。它从零实现了 Agent Loop、Tool Runtime、Permission、Trace、Todo/Hook 和 Evidence Store，同时集成外部 EngineeredRAG 后端，提供确定性论文 workflow 和评价系统。

---

## 2. 为什么做这个项目？

可以这样回答：

> 我之前做过 RAG 和 Agent 的一些 demo，但这些 demo 往往只是把 LLM 和工具串起来，稳定性和可评估性不足。所以我想做一个更接近真实 Agent Harness 的项目，把 LLM tool use、workflow 编排、证据管理、外部 RAG 后端和 evaluation 结合起来。

核心动机：

```text
从 demo 变成可用系统
从单次问答变成 workflow
从普通 RAG 变成 Agent Harness
从能跑变成可追踪、可评估
```

---

## 3. 这个项目解决什么问题？

ResearchPilot 主要解决论文研究中的几个问题：

```text
1. 如何自动搜索和下载相关论文？
2. 如何把论文接入已有 RAG 后端？
3. 如何基于本地论文库检索证据？
4. 如何生成带引用的回答？
5. 如何把回答保存为报告？
6. 如何评价答案是否可靠？
7. 如何让 Agent 工具调用过程可追踪？
```

它不是只关注最终回答，而是关注完整研究流程。

---

## 4. 总体架构怎么讲？

可以分三层讲：

```text
第一层：Agent Runtime
    AgentLoop、AgentAction、Observation、ToolRuntime、Permission、Trace

第二层：Research Workflow
    paper-answer、paper-collect、paper-research、ask

第三层：RAG 和 Evaluation
    EngineeredRAG 后端、EvidenceStore、Citation-aware Writer、eval-paper、LLM Judge
```

一句话总结：

> 底层是 Agent Harness，中间是确定性 workflow，上层是论文研究能力和评价能力。

---

## 5. Agent Loop 怎么实现？

可以这样讲：

> AgentLoop 是一个多步循环。每一步先由 ContextManager 构造上下文，再由 LLM Policy 输出结构化 AgentAction。如果 action 是 tool_call，就交给 ToolRuntime 执行，并把 Observation 写入 AgentState 和 TraceStore；如果 action 是 final_answer，就结束。

流程：

```text
User Goal
  ↓
ContextManager
  ↓
LLM Policy
  ↓
AgentAction
  ↓
ToolRuntime
  ↓
Observation
  ↓
AgentState / TraceStore
  ↓
Next Step
```

强调点：

```text
LLM 只输出结构化 action
工具执行由 ToolRuntime 控制
每一步都有 Observation
Trace 可以完整复盘
```

---

## 6. ToolRuntime 的意义是什么？

可以这样回答：

> ToolRuntime 是 LLM 和真实工具之间的执行层。LLM 不能直接执行任意代码，它只能提出结构化动作。ToolRuntime 会根据 tool_name 找到对应工具，做权限检查，然后执行工具并返回 Observation。

它解决了三个问题：

```text
1. 工具统一注册和调用
2. 工具输出统一成 Observation
3. 工具执行前可以做 Permission Check
```

这让系统更安全、更可扩展。

---

## 7. 为什么要做 PermissionChecker？

回答：

> 因为 LLM 生成的工具调用不能完全信任。比如它可能尝试读取敏感文件，或者执行危险 shell 命令。所以我加了 PermissionChecker，在 ToolRuntime 执行前做限制。

可以补充：

> 这也是 Agent Harness 和普通脚本的区别之一。普通脚本只考虑功能，Agent Harness 还要考虑安全边界和执行控制。

---

## 8. Todo 和 Hooks 有什么用？

可以这样讲：

> TodoWrite 和 HookManager 是为了支持长任务运行。Todo 记录任务状态，Hook 可以在 Agent 偏离计划时加入 reminder。这个思路参考了 Claude Code 这类 coding agent。

例子：

```text
如果 Agent 有未完成 todo
但连续几步没有更新 todo
Hook 会把提醒注入下一轮 context
```

意义：

```text
让长任务更可控
减少 Agent 跑偏
方便 trace 中观察任务进度
```

---

## 9. 为什么不完全依赖 LLM 自主调用工具？

这是面试里很重要的问题。

可以这样回答：

> 我一开始也让 LLM 自己决定调用 engineered_rag_search、write_evidence_answer、save_report 等工具。但实际测试发现，LLM 有时会选错工具、忘记保存报告、直接 read_file 读取 PDF，或者把 citation-aware answer 压缩成普通总结。所以我保留了 run 模式用于开放任务，同时对论文问答这种高频任务设计了 deterministic workflow。

核心观点：

```text
开放任务 → Agent Mode
稳定任务 → Workflow Mode
```

一句话：

> 不是所有任务都应该交给 LLM 自由发挥，高价值流程应该由 workflow 保证稳定性。

---

## 10. Workflow 有哪些？

目前主要有三个 paper workflow。

### 10.1 paper-answer

用途：

```text
基于已有 indexed papers 回答问题
```

流程：

```text
question
  ↓
engineered_rag_search
  ↓
write_evidence_answer
  ↓
final answer
```

### 10.2 paper-collect

用途：

```text
按照主题搜索、下载论文并重建索引
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
```

### 10.3 paper-research

用途：

```text
完整 local-first 论文研究流程
```

流程：

```text
先查本地论文库
证据够 → 直接回答
证据不够 → 下载新论文 → 重建索引 → 再检索 → 回答 → 保存报告
```

---

## 11. ask 命令的作用是什么？

回答：

> ask 是自然语言入口。用户不需要知道具体工具或 workflow 名称，只需要直接提问。IntentRouter 会判断这个请求是论文问答、论文下载、还是写报告，然后路由到对应 workflow。

例子：

```bash
research-pilot ask "What is the architecture of agentic RAG?"
```

路由到：

```text
paper-answer
```

```bash
research-pilot ask "Download 3 papers about agentic RAG architecture."
```

路由到：

```text
paper-collect
```

```bash
research-pilot ask "Write a report about the architecture of agentic RAG." --save-report
```

路由到：

```text
paper-research
```

---

## 12. 为什么接入外部 EngineeredRAG？

回答：

> 我之前已经有一个效果更好的 paper-rag-assistant 项目，里面实现了 paper-level retrieval、dense/BM25 hybrid retrieval、cross-encoder reranking 和 source-aware context formatting。所以 ResearchPilot 没有重复实现这些检索模块，而是把它作为外部 RAG backend 接入。

这样做的好处：

```text
复用已有强检索能力
ResearchPilot 专注 Agent Harness 和 workflow
系统模块化，未来可以替换其他 RAG backend
```

可以补充：

> 这也是工程中常见思路，不是所有模块都要重写，关键是设计好边界和接口。

---

## 13. EngineeredRAG 是怎么接入的？

ResearchPilot 把外部后端包装成三个工具：

```text
engineered_rag_index
engineered_rag_search
engineered_rag_answer
```

其中最常用的是：

```text
engineered_rag_search
```

它会返回结构化 evidence blocks，包括：

```text
source id
file name
page
chunk id
content
reranker score
```

这些 evidence blocks 会进入 EvidenceStore，然后由 Citation-aware Answer Writer 使用。

---

## 14. 为什么需要 subprocess worker？

可以这样回答：

> 在 Windows 上，Chroma 可能会持有数据库文件句柄。如果同一个 Python 进程先 search 向量库，然后又 rebuild index，就可能出现 WinError 32 文件锁错误。为了解决这个问题，我把 EngineeredRAG 的 search、answer 和 index 都放到独立子进程里执行。子进程执行完退出后，操作系统会释放 Chroma 文件句柄。

问题流程：

```text
同一进程：
search Chroma → rebuild Chroma → WinError 32
```

解决后：

```text
主进程 → search 子进程 → 子进程退出
主进程 → index 子进程 → 子进程退出
```

这比简单使用 `gc.collect()` 或 `time.sleep()` 更可靠。

---

## 15. EvidenceStore 的作用是什么？

回答：

> EvidenceStore 是系统的统一证据层。工具产生的重要信息都会存入 EvidenceStore，例如 web search 结果、论文检索结果、note、report 等。Citation-aware Answer Writer 会从 EvidenceStore 读取结构化 evidence blocks，然后生成带引用的回答。

意义：

```text
证据和答案生成解耦
支持多工具证据融合
方便后续评价 groundedness
可以在 trace 中复盘证据来源
```

---

## 16. Citation-aware Answer Writer 怎么工作？

回答：

> 它接收用户问题和结构化证据块，把每个 chunk 格式化成 [Source X]，保留 file、page、chunk id 和 content，然后要求 LLM 只基于这些证据回答，并输出 Answer、Architecture Breakdown、Explanation、Sources Used 和 Limitations。

标准输出结构：

```markdown
## Answer

## Architecture Breakdown

## Explanation

## Sources Used

## Limitations
```

这样比普通 RAG answer 更清晰，因为它要求每个关键结论都能对应到 source。

---

## 17. Evaluation 怎么做？

ResearchPilot 有两层评价。

### 17.1 Rule-based Evaluation

检查：

```text
workflow 是否成功
是否有 tool error
是否有 ## Answer
是否有 ## Sources Used
是否有 ## Limitations
是否有 citation marker
答案长度是否足够
是否保存报告
```

命令：

```bash
research-pilot eval-paper
```

### 17.2 LLM Judge Evaluation

LLM Judge 会评价：

```text
groundedness
citation_quality
completeness
clarity
hallucination_risk
overall_score
```

命令：

```bash
research-pilot eval-paper --llm-judge
```

可以这样讲：

> 规则评价适合做 regression test，LLM Judge 适合做答案质量评价。二者结合可以让项目从“能跑”变成“可评估”。

---

## 18. 这个项目和普通 RAG Demo 有什么区别？

普通 RAG demo 通常是：

```text
加载文档 → 检索 chunk → 生成答案
```

ResearchPilot 多了：

```text
Agent Loop
Tool Runtime
Permission Control
Trace Logging
Todo / Hooks
Evidence Store
Deterministic Workflows
Intent Router
External RAG Backend
Subprocess Worker
Citation-aware Answer Writer
Evaluation Harness
```

可以总结为：

> 普通 RAG demo 关注一次问答效果；ResearchPilot 更关注构建一个稳定、可追踪、可评估的研究 Agent 系统。

---

## 19. 项目亮点怎么总结？

可以讲 5 个亮点：

```text
1. 从零实现轻量 Agent Harness，而不是只调 LangGraph。
2. 同时支持 LLM 自由工具调用和确定性 workflow。
3. 集成外部 EngineeredRAG，复用强检索能力。
4. 使用 EvidenceStore 和 Citation-aware Writer 生成带来源答案。
5. 加入 rule-based 和 LLM Judge evaluation，支持质量评估。
```

---

## 20. 当前局限怎么讲？

可以坦诚说：

```text
1. Intent Router 目前是规则型，未来可以换成 LLM classifier。
2. Citation correctness 目前主要是格式和 evidence-level 检查，后续可以做更严格的 source verification。
3. LLM Judge 分数依赖模型，不是绝对客观。
4. 当前重点是 paper research，还没有深入做 codebase editing。
5. 目前没有 Web UI，主要是 CLI 工具。
```

这种回答会显得你对项目边界很清楚。

---

## 21. 后续如何扩展？

可以说：

```text
1. 做 Codebase Agent，让它支持代码仓库理解和代码问答。
2. 做多章节 Report Writer，支持 section-level citation。
3. 做 Streamlit / FastAPI Web UI。
4. 做 Evaluation Dashboard。
5. 支持多 RAG backend。
6. 做更严格的 citation verification。
```

---

## 22. 面试 1 分钟版本

可以这样讲：

> ResearchPilot 是我做的一个论文研究 Agent Harness。它底层实现了 AgentLoop、ToolRuntime、Permission、Trace、Todo/Hook 和 EvidenceStore；上层提供 paper-answer、paper-collect、paper-research 和 ask 等 workflow。项目接入了我之前做的外部 EngineeredRAG 后端，用于论文检索和 reranking，然后通过 citation-aware answer writer 生成带 source 的回答。为了提高稳定性，我没有完全依赖 LLM 自主调用工具，而是对高频任务设计了 deterministic workflow。同时我还加入了 rule-based evaluation 和 LLM Judge，用来评价答案是否 grounded、引用是否合理、完整性如何。这个项目的重点不是单次 RAG 问答，而是把 Agent 工具调用、工作流编排、证据管理和评价结合成一个可追踪、可评估的研究助手。

---

## 23. 面试 3 分钟版本

可以这样讲：

> ResearchPilot 是一个面向论文研究场景的 Agent Engineering 项目。最开始我做过一些 RAG 和 Agent demo，但我发现单纯让 LLM 自由调用工具不够稳定，所以这个项目的目标是做一个更完整的 Agent Harness。
>
> 底层我实现了 AgentLoop、AgentAction、Observation、ToolRuntime、PermissionChecker、TraceStore、ContextManager 和 Todo/Hook。LLM 不直接执行工具，而是输出结构化 action，ToolRuntime 再进行权限检查和工具执行，每一步都会记录 observation 和 trace。
>
> 在论文研究部分，我设计了三个确定性 workflow：paper-answer 用本地 indexed papers 回答问题；paper-collect 负责搜索、下载论文并重建索引；paper-research 是 local-first 流程，先查本地库，证据不足再下载新论文、重建索引、重新检索并写报告。
>
> 检索后端方面，我复用了之前做的 paper-rag-assistant，它有 paper-level retrieval、dense/BM25 hybrid retrieval 和 cross-encoder reranking。ResearchPilot 把它包装成 EngineeredRAG tools，并通过 subprocess worker 执行，解决了 Windows 上 Chroma 文件锁的问题。
>
> 为了让答案更可靠，我加入了 EvidenceStore，把检索到的 chunk 保存为结构化 evidence blocks，包括 source id、file、page、chunk id 和 content。Citation-aware Answer Writer 会基于这些证据生成 Answer、Architecture Breakdown、Explanation、Sources Used 和 Limitations。
>
> 最后，我还做了 evaluation harness。规则评价检查 workflow 是否成功、是否有 tool error、是否包含 citation 和 Sources Used；LLM Judge 进一步评价 groundedness、citation quality、completeness、clarity 和 hallucination risk。
>
> 所以这个项目和普通 RAG demo 的区别是，它不仅做检索问答，还实现了 Agent Runtime、确定性 workflow、证据管理和评价系统，更接近一个可追踪、可评估的研究 Agent。

---

## 24. 简历写法参考

可以写成英文：

```text
ResearchPilot: Agentic Paper Research Assistant
- Built a Claude Code-like agent harness with structured actions, tool runtime, permission checks, trace logging, todo hooks, and evidence management.
- Integrated an external EngineeredRAG backend with hybrid retrieval, reranking, and source-aware context formatting for paper QA.
- Designed deterministic paper workflows for paper collection, local-first retrieval, citation-aware answering, and report generation.
- Implemented subprocess-based EngineeredRAG workers to avoid Chroma file-lock issues on Windows.
- Added rule-based and LLM-as-judge evaluation for groundedness, citation quality, completeness, and hallucination risk.
```

中文版：

```text
ResearchPilot：面向论文研究的 Agentic Research Assistant
- 从零实现类 Claude Code 的 Agent Harness，包括结构化 action、ToolRuntime、权限检查、Trace、Todo/Hook 和 EvidenceStore。
- 集成外部 EngineeredRAG 后端，支持 hybrid retrieval、reranking 和 source-aware context formatting。
- 设计 paper-answer、paper-collect、paper-research 等确定性 workflow，实现本地优先的论文问答和报告生成。
- 使用 subprocess worker 解决 Windows 下 Chroma 文件锁导致的索引重建问题。
- 实现规则评价和 LLM Judge，用于评估答案 groundedness、citation quality、completeness 和 hallucination risk。
```

---

## 25. 最终总结

面试时要反复强调一句话：

> 这个项目不是单纯 RAG demo，而是一个把 Agent Runtime、Tool Calling、Workflow、Evidence Store、External RAG 和 Evaluation 结合起来的 Agent Engineering 项目。

这句话是整个项目的定位。
