# `agent.py` 代码详解

本文对应 [agent.py](../../agents/shared-runtime/a2a_runtime/agent.py)，基于当前 995 行源码编写。这个文件实现**一个专业 Agent 的运行时**：接入大模型和 MCP 工具，建立 LangGraph ReAct 图，输出 A2A 事件，处理超时、预算及人工审批。Host Agent 如何分派任务不在这里。

## 一、一次请求的执行路线

```text
外部请求 (query, context_id)
  └─ RuntimeMCPAgent.stream()
      ├─ 审批决定 → _resume_approved()
      └─ 普通问题
          ├─ ensure_ready(): PostgreSQL checkpoint、MCP 工具、模型、ReAct 图
          ├─ LangGraph: model → ToolNode → model → ...
          ├─ AIMessage/ToolMessage/AIMessageChunk → RuntimeEvent
          └─ 正常结束或预算截断 → completed 事件
```

三个概念先分清：`AIMessage` 是模型一轮输出，可同时包含多个工具调用；`ToolMessage` 是某个工具调用的返回；`RuntimeEvent` 是本项目发往上层的流式事件。模型在中途输出的文字可能只是阶段草稿，不一定是最终结论。

## 二、导入与文件级函数（第 1–36 行）

- `ChatOpenAI` 调用 OpenAI 兼容模型；`create_react_agent` 和 `ToolNode` 负责 ReAct 循环；`RunnableLambda` 在模型输出后裁剪工具批次。
- 本地模块分别提供配置、PostgreSQL checkpoint、MCP 连接、审批数据类型、事件、工具适配和策略。
- `_handle_tool_error(exc)`：审批异常继续向上抛出，普通工具异常转成“工具执行失败：...”文本。后续用这个前缀识别失败。
- `_limit_tool_batch(message, limit)`：模型一次提出过多 `tool_calls` 时只保留前 `limit` 个。它限制一批的数量，并未关闭并行。

## 三、`RuntimeMCPAgent.__init__()`（第 39–127 行）

构造函数接收 Agent 配置、专业 prompt，可选注入 MCP client、模型、超时参数和 checkpoint URL。它向 prompt 追加通用规则：先取最小证据集、允许不同工具并行、不重复同参数调用、每批结果后检查是否足够、只读诊断默认最多两批、报告尽量简短。这些是**模型指令**；真正的硬限制由预算和工具策略执行。

| 参数/字段 | 默认或来源 | 用途 |
| --- | --- | --- |
| `checkpoint_database_url` | `AGENT_CHECKPOINT_DATABASE_URL` | 持久化 LangGraph 消息；缺失则初始化失败 |
| `run_timeout` | `AGENT_RUN_TIMEOUT` / 90 秒 | 总时间基数 |
| `summary_reserve_seconds` | 配置值或 `min(35, run_timeout × 0.2)` | 为兜底总结留时间 |
| `timeout_safety_margin_seconds` | 配置值或 `min(5, run_timeout × 0.05)` | 安全余量 |
| `investigation_timeout` | 上述三者相减 | 调查循环实际限时，必须大于 0 |
| `max_steps` | `AGENT_MAX_STEPS` / 30 | 图递归步数的下界 |
| `max_tool_calls` | `AGENT_MAX_TOOL_CALLS` / 40 | 工具调用总预算 |
| `max_output_tokens` | `AGENT_MAX_OUTPUT_TOKENS` / 4096 | 普通模型输出上限 |
| `summary_max_tokens` | `AGENT_SUMMARY_MAX_TOKENS` / 1024 | 强制总结输出上限 |
| `enable_thinking` | `AGENT_ENABLE_THINKING` / false | 兼容模型的 thinking 开关 |
| `tool_budget_warning_ratio` | `AGENT_TOOL_BUDGET_WARNING_RATIO` / 0.6 | 工具预算预警阈值 |

`_graph` 是已建好的 LangGraph；`_tool_adapter` 包装 MCP 工具；`_pending_by_context` 保存待审批动作；`_batch_results_by_context` 保存审批中断后同批工具的临时结果。后两者是**进程内状态**，图消息则保存在 PostgreSQL checkpoint。

## 四、`ensure_ready()`：建图（第 129–205 行）

1. 已初始化时直接返回。没有 checkpoint URL 就报错。
2. 打开 PostgreSQL checkpoint，然后通过 `mcp_client.list_tools()` 取工具定义；异常时记录 `_dependency_error` 并关闭已打开的 checkpoint。
3. 用 `MCPToolAdapter` 和 `ToolPolicy` 把 MCP 定义转换为 LangChain 工具，并设置权限、调用预算和预警比例。具体策略实现不在本文件。
4. 从 `load_llm_config("AGENT")` 取模型配置，默认创建 `ChatOpenAI`，启用 streaming、temperature=0，并传 `enable_thinking`。
5. `model.bind_tools(tools)` 让模型知道可用工具。
6. `model_for_session(_state, runtime)` 由图在模型节点调用：从 `runtime.context.session_id` 取会话 ID，绑到请求的 `metadata.session_id`；按剩余工具预算和 `AGENT_MAX_PARALLEL_TOOL_CALLS`（默认 4）限制本批调用。`_state` 在此未使用。
7. `create_react_agent(...)` 将模型工厂、`ToolNode`、prompt 和 checkpoint 组合成图。

工具批次裁剪发生在模型已生成调用之后、进入 ToolNode 之前；是否允许执行仍由工具适配器和策略决定。

## 五、状态检查和生命周期（第 207–325 行）

- `readiness()` 返回 `ready/degraded` 及 LLM、MCP、checkpoint、Kubernetes 状态。它主要依据配置与初始化状态，**不是**每次都实时查询集群。
- `probe_connections(timeout, target)` 主动检查模型或 MCP：模型做一个简短的 OK 请求；MCP 调用 `list_tools()`。`all` 模式使用 `asyncio.gather` 并行探测，返回耗时或错误。
- `warm_up()` 启动时尽力初始化；短超时失败返回 `False`，真实请求还会在 `stream()` 中尝试初始化。
- `shutdown()` 关闭 checkpoint 和 MCP 连接，重置就绪标记。

## 六、`stream()`：普通请求的核心流程（第 327–567 行）

### 入口和 checkpoint

先用 `_parse_approval(query)` 检查是否为 `{"type":"approval_decision", ...}`。若是，走审批恢复；否则调用 `ensure_ready()`。依赖不可用时发 `ERROR` 事件并结束。

`graph_config.configurable.thread_id = context_id`，让同一上下文使用同一条 checkpoint 线程。图递归上限取 `max(max_steps, max_tool_calls * 2 + 2)`，因为一个工具轮通常至少消耗模型节点和工具节点两个步骤。随后重置本次工具预算。

`seen_tool_calls`、`seen_tool_results` 用于事件去重。运行前先从 checkpoint 读取旧消息的调用 ID 和结果 ID，因此复用 `context_id` 时不会把历史活动重新发一遍。`current_tool_names/results` 只收集这次执行所见的工具证据，供预算截断时总结。

### 两种流模式

`_graph.astream(..., stream_mode=["values", "messages"], context={"session_id": context_id})` 同时读：

- `messages`：模型的 `AIMessageChunk`。只在已经有工具结果、节点是 `agent`、片段有文字且不是工具调用片段时，发 `RuntimeEventType.TEXT`。这些字可能仍是阶段草稿。
- `values`：图消息快照。新 `AIMessage.tool_calls` 变成 `TOOL_CALL` 事件（ID、名称、参数）；新 `ToolMessage` 变成 `TOOL_RESULT`（ID、结果）。已见 ID 跳过。预算拒绝的工具结果会标记 `skipped`。

### 中断、截断和完成

- `ApprovalRequired`：将 `pending_action` 放入 `_pending_by_context`，发审批事件，当前流结束。
- `TimeoutError` / `GraphRecursionError`：停止调查，提取已完成工具证据，先尝试 `_force_summary()`；失败再用 `_deterministic_partial_summary()`。最终 `status=partial`，说明限制。
- 正常结束：从 checkpoint 最后一条 `AIMessage.content` 取回答。若工具预算用尽且内容少于 200 字，先发 `TEXT_RESET` 撤回不完整草稿，再强制总结。框架的 “need more steps” 文本也改为部分总结。
- 如果有以“工具执行失败：”开头的工具结果，最终标为 `partial`；否则发 `completed`。

完成事件里的 `summary` 是主要正文；`findings/resources/evidence/recommendations` 在普通分支目前多为空列表，不能据此认为已经生成了独立的结构化分析。

## 七、预算后的总结函数（第 569–683 行）

`_force_summary(query, evidence)` 再调用模型，但提示禁止调用工具，只基于现有证据作答；受 `summary_reserve_seconds` 和 `summary_max_tokens` 限制，不进入原 ToolNode 循环。

`_deterministic_partial_summary(results, reason, tool_names)` 是模型总结失败时的 Python 兜底报告。它只解析少数结果形状：命名空间、名称暗示高权限的 RBAC 绑定、集群版本等。RBAC 名称**不能证明实际授权**，代码也要求进一步核对 `roleRef` / `subjects`。其他情况会截取最多四条工具结果，并明确证据不足。

`_current_run_evidence(results)` 为强制总结压缩证据：每条最多 2,000 字符，总计最多 12,000 字符。过长的工具返回不会完整进入兜底模型上下文。

## 八、人工审批链（第 685–992 行）

`_parse_approval()` 只识别 JSON 对象且 `type == "approval_decision"`。`_resume_approved()` 优先从内存中找待审批动作；没有时尝试从审批载荷重建，再校验 Agent ID、动作摘要、审批 ID。拒绝时不执行写操作，调用 `_close_pending_tool_call()` 给中断的图补结果。批准时再次校验摘要，再直接调用 MCP；执行失败发 `ERROR`。

为什么还需要 `_settle_interrupted_batch()`？模型的一条 `AIMessage` 可包含多个工具调用。`ToolNode` 遇到要求审批的动作会打断整批，同批其他调用可能没有 `ToolMessage`，此时图不能可靠继续。该方法会：

1. 用 `_pending_batch_calls()` 读取最近一批调用和已完成 ID。
2. 暂存已批准动作的结果。
3. 逐个处理剩余调用：策略判定需审批就继续发审批请求；允许的兄弟调用才直接执行。策略无法判断时 `_requires_approval()` 默认要求审批。
4. 全部结算后，`_inject_tool_messages()` 通过 `as_node="tools"` 把缺失的 `ToolMessage` 写回 checkpoint，然后发完成事件。

`_pending_batch_unresolved()` 查询最近未结算调用；`_inject_tool_message()` 注入单个结果，两者在当前文件内没有调用。`_close_pending_tool_call()` 在拒绝或执行失败时补上匹配调用的结果，避免悬空调用。

注意：审批恢复后的完成正文是同批 MCP 工具结果的拼接，并非再次让模型做自然语言验证总结。若业务要求变更后验证，需要检查后续编排是否安排了验证步骤。

## 九、`load_prompt()`（第 994–995 行）

按 UTF-8 读取 prompt 文件内容。专业 Agent 可以用它加载自己的系统提示，再传入 `RuntimeMCPAgent`。

## 十、建议的阅读顺序

1. 工具从哪里来：`ensure_ready()` → `MCPToolAdapter.build_tools()` → `model.bind_tools()`。
2. 为什么会并行、为什么被限制：`model_for_session()` → `_limit_tool_batch()` → `ToolNode`。
3. 页面阶段文字从哪里来：`stream()` 的 `messages` 模式与 `TEXT`，然后看后端运行事件映射。
4. 为什么最后是受限结论：`investigation_timeout` → `_force_summary()` → `_deterministic_partial_summary()`。
5. 写操作如何审批：`ApprovalRequired` → `_resume_approved()` → `_settle_interrupted_batch()`。

具体 Kubernetes API 请求在 `mcp_client.py`；工具授权在 `tool_policy.py` / `tool_adapter.py`；Host 分派在 `backend/host/` 与 `backend/orchestration/`。
