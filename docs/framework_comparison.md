````markdown
# Agent / RAG 主流框架对比总结

本文整理 ResearchPilot 与主流 Agent / RAG 框架或平台的关系，包括 LangChain、LangGraph、LlamaIndex、Dify、Coze 和 MCP。

这份文档的目的不是说明 ResearchPilot 比这些框架更强，而是讲清楚：

1. 每个框架主要解决什么问题；
2. ResearchPilot 中哪些模块和它们对应；
3. 为什么 ResearchPilot 选择手写部分核心机制；
4. 未来如何和这些主流框架集成。

---

## 1. 总体生态图

当前 Agent / RAG 生态可以大致分成四层：

```text
应用平台层：
  Dify / Coze

代码框架层：
  LangChain / LangGraph / LlamaIndex

协议层：
  MCP

自研项目层：
  ResearchPilot
````

它们解决的问题不同。

| 层级    | 代表工具                           | 主要作用                                                                           |
| ----- | ------------------------------ | ------------------------------------------------------------------------------ |
| 应用平台层 | Dify、Coze                      | 用低代码方式快速搭建、发布 AI 应用，通常包含工作流、知识库、插件和 UI。                                        |
| 代码框架层 | LangChain、LangGraph、LlamaIndex | 用代码构建 LLM 应用、Agent 工作流和 RAG 系统。                                                |
| 协议层   | MCP                            | 标准化 AI 应用和外部工具、资源、Prompt 的连接方式。                                                |
| 自研项目层 | ResearchPilot                  | 手写实现 AgentLoop、ToolRuntime、图工作流、RAG workflow、Trace、Evaluation、API 和 Docker 部署。 |

ResearchPilot 的核心定位是：

```text
ResearchPilot 不是低代码平台；
ResearchPilot 也不只是某个框架的简单封装；
ResearchPilot 是一个自研 Agent / RAG 工程项目，用来展示我对 Agentic RAG 内部机制的理解和实现能力。
```

---

## 2. LangChain

### 2.1 LangChain 是什么？

LangChain 是一个用于构建 LLM 应用和 Agent 应用的代码框架。

它提供很多常见抽象，例如：

* model interface；
* tool；
* agent；
* retriever；
* document loader；
* vector store integration；
* structured output；
* 各种第三方集成。

简单来说，LangChain 适合快速把大模型、工具、检索器和外部 API 组合成一个 LLM 应用。

### 2.2 LangChain 和 ResearchPilot 的对应关系

| LangChain 概念      | ResearchPilot 中的对应模块                        |
| ----------------- | ------------------------------------------- |
| Tool              | `BaseTool` / `ToolRuntime`                  |
| Agent             | `AgentLoop`                                 |
| Retriever         | Paper RAG 里的检索工具                            |
| Runnable / Chain  | deterministic workflow runner               |
| Tool calling loop | Agent action → tool execution → observation |
| Integrations      | 自定义工具与外部 API                                |

### 2.3 主要区别

LangChain 提供了很多现成抽象，适合快速开发。

ResearchPilot 则是手写实现了一套核心机制：

```text
AgentLoop
ToolRuntime
AgentAction
Observation
TraceStore
WorkflowRunner
GraphWorkflowRuntime
```

所以 ResearchPilot 更适合描述成：

```text
一个手写实现 tool-using LLM agent 核心机制的工程项目。
```

而不是一个简单的 LangChain 应用。

### 2.4 面试说法

可以这样说：

> LangChain 很适合快速搭建 LLM 应用，它提供了 Tool、Retriever、Agent 和各种 integration。ResearchPilot 里我没有直接套 LangChain Agent，而是自己实现了 AgentLoop 和 ToolRuntime，目的是把 tool calling、observation、state update、trace logging 这些底层机制拆开理解。
>
> 如果未来需要更多第三方生态集成，我可以把 ResearchPilot 的工具适配成 LangChain Tool。但这个项目的价值在于我手写了核心 Agent runtime，而不是只调用一个现成框架。

---

## 3. LangGraph

### 3.1 LangGraph 是什么？

LangGraph 是一个用于构建 stateful、graph-based agent workflow 的编排框架。

它的核心概念包括：

* shared state；
* node；
* edge；
* conditional edge；
* checkpoint；
* durable execution；
* streaming；
* human-in-the-loop。

它适合表达复杂、多步骤、需要状态管理和分支控制的 Agent 工作流。

### 3.2 LangGraph 和 ResearchPilot 的对应关系

| LangGraph 概念     | ResearchPilot 中的对应模块                                          |
| ---------------- | ------------------------------------------------------------- |
| `StateGraph`     | `GraphWorkflowRuntime`                                        |
| Shared state     | `GraphState` / Blackboard                                     |
| Node             | prepare / planner / code / paper / general / reviewer / final |
| Edge             | 固定流程跳转                                                        |
| Conditional edge | planner routing / reviewer fallback                           |
| Checkpoint       | 未来可以扩展的 session / trace persistence                           |
| Execution trace  | `visited_nodes` / trace report                                |

ResearchPilot 中典型的图工作流是：

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

这个结构天然可以映射到 LangGraph。

### 3.3 主要区别

ResearchPilot 的图运行时是轻量级、项目定制的。

LangGraph 是成熟的、生产级的编排框架。

| ResearchPilot GraphWorkflowRuntime | LangGraph                           |
| ---------------------------------- | ----------------------------------- |
| 轻量级自研 runtime                      | 成熟的图编排框架                            |
| 适合学习和控制细节                          | 适合生产级复杂 workflow                    |
| 支持 visited path 和 trace            | 支持 checkpoint、persistence、streaming |
| 节点和流程为项目定制                         | 通用 graph runtime                    |
| 更容易看清内部机制                          | 生态和功能更完整                            |

### 3.4 面试说法

可以这样说：

> 我的 GraphWorkflowRuntime 和 LangGraph 在抽象上比较接近，都是用 shared state、node、edge 和 conditional routing 来组织 Agent workflow。在 ResearchPilot 里，planner 会把问题路由到 code、paper 或 general 子智能体，reviewer 可以决定是否 final 或触发 fallback。
>
> 我自己实现这层主要是为了理解 graph-based agent orchestration 的内部机制。如果做生产级系统，需要 checkpoint、durable execution、streaming 或 human-in-the-loop，LangGraph 会是很自然的迁移方向。

---

## 4. LlamaIndex

### 4.1 LlamaIndex 是什么？

LlamaIndex 更偏向 RAG 和知识库应用。

它主要围绕“如何让 LLM 使用私有数据或领域数据”来提供抽象，例如：

* Document；
* Node；
* Index；
* Retriever；
* QueryEngine；
* ResponseSynthesizer；
* Agent over data。

它很适合快速构建知识库问答、文档问答、企业数据问答等应用。

### 4.2 LlamaIndex 和 Paper RAG Assistant 的对应关系

| LlamaIndex 概念      | Paper RAG Assistant 中的对应模块                          |
| ------------------ | --------------------------------------------------- |
| Document           | 解析后的 PDF paper                                      |
| Node               | 文本 chunk                                            |
| Index              | Chroma vector index / paper catalog index           |
| Retriever          | dense retriever / BM25 retriever / hybrid retriever |
| QueryEngine        | retrieval + rerank + answer pipeline                |
| Response synthesis | source-grounded answer generation                   |

### 4.3 主要区别

LlamaIndex 提供成熟的 RAG 抽象。

Paper RAG Assistant 则是手写实现了一套面向学术论文的 RAG pipeline：

```text
PDF parsing
  ↓
chunking
  ↓
paper-level catalog retrieval
  ↓
chunk-level dense retrieval
  ↓
BM25 keyword retrieval
  ↓
hybrid retrieval
  ↓
cross-encoder reranking
  ↓
source-grounded answer generation
  ↓
evaluation
```

Paper RAG Assistant 的价值是：把底层检索链路和评估链路显式做出来，而不是只调用高层 query engine。

### 4.4 面试说法

可以这样说：

> LlamaIndex 很适合构建基于私有数据的 RAG 应用，它提供了 Document、Node、Index、Retriever、QueryEngine 等成熟抽象。
>
> 我的 Paper RAG Assistant 和它目标接近，但我更强调手写实现学术论文 RAG 的完整链路，包括 paper-level retrieval、chunk-level dense retrieval、BM25、hybrid retrieval、cross-encoder reranking、query routing 和 evaluation。这样能展示我对 RAG 内部机制的理解，而不是只会调一个高层接口。

---

## 5. Dify

### 5.1 Dify 是什么？

Dify 是一个 LLM 应用开发平台，偏低代码 / 平台化。

它通常提供：

* workflow；
* knowledge base；
* model configuration；
* tool；
* app publishing；
* observability。

Dify 适合快速搭建和发布 AI 应用，比如知识库问答、客服机器人、企业内部助手等。

### 5.2 Dify 和 ResearchPilot 的对应关系

| Dify 概念        | ResearchPilot 中的对应模块                          |
| -------------- | --------------------------------------------- |
| Workflow       | deterministic workflow / graph workflow       |
| Knowledge base | Paper RAG Assistant index                     |
| Tool           | ToolRuntime tool                              |
| App            | FastAPI service / CLI application             |
| Observability  | Trace report / metadata / visited nodes       |
| RAG pipeline   | PaperWorkflowRunner / paper research workflow |

### 5.3 主要区别

Dify 是产品平台导向。

ResearchPilot 是代码实现导向。

| Dify                         | ResearchPilot     |
| ---------------------------- | ----------------- |
| 低代码 / 平台化                    | code-first / 自研实现 |
| 适合快速搭应用                      | 适合展示内部机制理解        |
| 自带 UI 和应用管理                  | 需要自己写 API / UI    |
| 内置 workflow 和 knowledge base | 手写 workflow 和 RAG |
| 更适合快速产品交付                    | 更适合展示工程深度         |

### 5.4 面试说法

可以这样说：

> Dify 适合快速搭建 LLM 应用，它提供 workflow、knowledge base 和 UI 管理能力。如果目标是快速交付一个应用，Dify 是很好的选择。
>
> ResearchPilot 不同，它是我手写实现的工程项目，包括 AgentLoop、ToolRuntime、图工作流、PaperWorkflowRunner、trace report、FastAPI 服务和 Docker 部署。它更适合展示我对 Agentic RAG 内部机制的理解，而不是只做平台配置。

---

## 6. Coze

### 6.1 Coze 是什么？

Coze 是一个 AI Agent 应用平台，也偏低代码 / 平台化。

它通常提供：

* Agent 构建；
* workflow；
* plugin；
* knowledge base；
* 多渠道发布；
* 可视化配置。

它适合快速创建和发布 Agent 应用。

### 6.2 Coze 和 ResearchPilot 的对应关系

| Coze 概念              | ResearchPilot 中的对应模块                    |
| -------------------- | --------------------------------------- |
| Agent                | ResearchPilot multi-agent workflow      |
| Workflow             | GraphWorkflowRuntime / WorkflowRunner   |
| Plugin               | ToolRuntime tool                        |
| Knowledge base       | Paper RAG Assistant / local paper index |
| Published app        | FastAPI / future frontend               |
| Visual orchestration | code-level graph orchestration          |

### 6.3 主要区别

Coze 更像是 Agent 产品搭建平台。

ResearchPilot 更像是自研 Agent 系统工程项目。

一句话区分：

```text
Coze 适合快速搭 Agent 应用；
ResearchPilot 适合展示我理解 Agent 应用内部是怎么运行的。
```

### 6.4 面试说法

可以这样说：

> Coze 提供了比较方便的 Agent 应用搭建能力，包括 workflow、plugin 和 knowledge base，适合快速原型和发布。
>
> ResearchPilot 是 code-first 的自研实现，我自己实现了 routing、tool execution、RAG workflow、reviewer feedback、trace、API service 和 Docker deployment。所以我会把 Coze 看作应用平台，把 ResearchPilot 看作我对 Agent 系统底层机制的工程实现。

---

## 7. MCP

### 7.1 MCP 是什么？

MCP 全称是 Model Context Protocol。

它是一个用于连接 AI 应用和外部系统的协议。

MCP 标准化了 AI 应用如何使用：

* tools；
* resources；
* prompts。

简单理解：

```text
Tool Calling 解决的是：模型如何调用工具。
MCP 解决的是：外部工具、资源、Prompt 如何用标准方式暴露给 AI 应用。
```

### 7.2 MCP 和 ResearchPilot 的对应关系

| MCP 概念      | ResearchPilot 中的对应模块                      |
| ----------- | ----------------------------------------- |
| MCP server  | 外部工具提供方                                   |
| MCP client  | 未来可以添加的 ResearchPilot MCP adapter         |
| Tool        | ToolRuntime tool                          |
| Resource    | file / database / paper source / API data |
| Prompt      | reusable task template                    |
| Tool schema | tool input schema                         |

### 7.3 MCP 和 ToolRuntime 的区别

ResearchPilot 的 ToolRuntime 是内部工具系统。

MCP 是外部标准协议。

| ResearchPilot ToolRuntime | MCP                    |
| ------------------------- | ---------------------- |
| 自定义工具注册表                  | 标准化协议                  |
| 工具定义在项目内部                 | 工具由外部 MCP server 暴露    |
| 直接 Python 执行              | client-server 交互       |
| 项目定制 schema               | 标准化 schema 和 discovery |
| 本地控制更强                    | 生态集成更好                 |

### 7.4 ResearchPilot 未来如何支持 MCP？

可以设计一个 MCP adapter：

```text
ResearchPilot
  ↓
MCPToolAdapter
  ↓
MCP client
  ↓
external MCP servers
  ↓
tools / resources / prompts
```

这个 adapter 负责：

1. 从 MCP server 发现工具；
2. 把 MCP tool schema 转成 ResearchPilot tool schema；
3. 注册到 ToolRuntime；
4. 当 Agent 选择该工具时，通过 MCP client 调用外部 MCP server；
5. 把 MCP 返回结果转成 ResearchPilot observation。

### 7.5 面试说法

可以这样说：

> 我理解 MCP 是 Agent 工具体系的标准化协议。传统 tool calling 通常是每个项目自己定义工具 schema 和调用方式，而 MCP 把 tools、resources、prompts 这些能力通过 client-server 协议标准化。
>
> ResearchPilot 目前的 ToolRuntime 是自定义内部工具执行系统。未来可以加一个 MCP adapter，把 MCP server 暴露的工具发现并注册到 ToolRuntime 中，这样 ResearchPilot 就可以接入更标准化的外部工具生态。

---

## 8. 总结对比表

| 系统            | 核心定位                         | 最适合做什么                                   | 和 ResearchPilot 的关系                     |
| ------------- | ---------------------------- | ---------------------------------------- | --------------------------------------- |
| LangChain     | LLM 应用和 Agent 组件框架           | tools、agents、retrievers、integrations     | 类似 AgentLoop / ToolRuntime / retrievers |
| LangGraph     | stateful graph orchestration | 多步骤 Agent workflow、routing、checkpoint    | 类似 GraphWorkflowRuntime                 |
| LlamaIndex    | 数据和 RAG 框架                   | 文档问答、知识库、retrieval over data             | 类似 Paper RAG Assistant                  |
| Dify          | LLM 应用平台                     | 低代码 workflow、知识库、应用发布                    | 平台化 workflow/RAG app building           |
| Coze          | Agent 应用平台                   | 可视化 Agent、workflow、plugin、knowledge base | 平台化 Agent app building                  |
| MCP           | 工具/资源/Prompt 接入协议            | 标准化外部系统集成                                | ToolRuntime 的未来扩展方向                     |
| ResearchPilot | 自研 Agent/RAG 工程项目            | 展示内部机制理解和工程实现能力                          | Portfolio project                       |

---

## 9. ResearchPilot 应该怎么定位？

最好的定位是：

```text
ResearchPilot 是一个自研的轻量级图工作流驱动多智能体研究助手。
它手写实现了 Agentic RAG 系统中的核心机制：
AgentLoop、ToolRuntime、GraphWorkflowRuntime、PaperWorkflowRunner、Trace Report、Evaluation、FastAPI 和 Docker。
```

不要把它说成：

```text
LangGraph 的替代品；
Dify 的替代品；
LlamaIndex 的替代品；
低代码平台。
```

而应该说成：

```text
一个 code-first 的工程项目，用来展示我理解这些系统内部是怎么工作的。
```

---

## 10. 面试一分钟回答

如果面试官问：

> 你的项目和 LangChain、LangGraph、LlamaIndex、Dify、Coze、MCP 这些东西是什么关系？

可以这样回答：

> 我把这些工具理解成不同层次的东西。LangChain 更像 LLM 应用组件框架，提供 tools、agents、retrievers 和各种 integrations；LangGraph 重点是 stateful graph-based agent orchestration；LlamaIndex 更偏数据和 RAG，适合做知识库问答；Dify 和 Coze 更偏低代码应用平台；MCP 则是连接外部 tools、resources 和 prompts 的标准协议。
>
> ResearchPilot 是我的 code-first 自研 Agentic RAG 项目。我自己实现了 AgentLoop、ToolRuntime、GraphWorkflowRuntime、PaperWorkflowRunner、trace report、evaluation、FastAPI 服务和 Docker 部署。它的目的不是替代这些框架，而是展示我理解这些系统背后的核心机制，并且能从底层把一个可控的 Agent/RAG 系统搭起来。
>
> 未来如果要做生产级版本，可以把图编排迁移到 LangGraph，把工具系统适配 LangChain Tool 或 MCP，把 RAG 部分参考 LlamaIndex 的抽象，把 API 服务接到 Dify/Coze 这类平台中。

---

## 11. 核心结论

ResearchPilot 给我的价值是：

```text
从底层理解 Agent/RAG 系统。
```

通过这个项目，我能讲清楚：

```text
tool calling 怎么工作；
workflow routing 怎么工作；
RAG retrieval 怎么实现；
reviewer feedback 怎么触发 fallback；
trace report 怎么帮助 debug；
Agent 系统怎么暴露成 API 服务；
服务怎么用 Docker 容器化；
未来怎么接入主流框架和协议。
```

```
```
