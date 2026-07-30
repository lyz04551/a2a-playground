# A2A Kubernetes 多智能体工程化 MVP 设计

## 1. 目标

在保留现有单智能体聊天能力的基础上，将 A2A Playground 建设成可扩展、
可演示的 Kubernetes 多智能体工程化 MVP。

本阶段实现：

- 一套共享 Python Agent Runtime；
- 三个基于 `a2a-sdk`、可独立启动的 Kubernetes Agent；
- 确定性的 MCP 工具权限隔离与写操作审批；
- 由大模型驱动的 Host Agent 动态编排；
- 稳定的 Agent 路由和远程 A2A 上下文延续；
- 基于 SQLite 的对话、任务、执行轨迹、审批、产物和事件持久化；
- Docker Compose 一键启动；
- 融合对话、执行轨迹和审批操作的前端。

多租户、企业认证、分布式任务队列、高可用和 PostgreSQL 不属于本阶段范围。

## 2. 设计原则

1. 每个面向用户的子智能体都保持为独立 A2A Agent。
2. Agent 之间统一使用 `a2a-sdk` 通信。
3. Host 不直接调用 Kubernetes MCP，只能通过 A2A 委派任务。
4. Host LLM 控制用户对话节奏，动态决定追问、委派和总结，不使用固定的
   Ops → Orchestrator → Ops 工作流。
5. 权限和审批属于确定性安全边界，提示词不能授予权限或绕过审批。
6. 单智能体聊天与多智能体协作复用相同的 A2A 网关和持久化基础设施。
7. 在可行范围内兼容已有 API。

## 3. 系统架构

### 3.1 服务组成

- `frontend`：React + Ant Design Playground。
- `backend`：管理 API、Host Agent、A2A 网关、SQLite、审批和事件流。
- `k8s-ops`：只读 Kubernetes 运维诊断 Agent。
- `k8s-orchestrator`：需要审批的 Kubernetes 变更 Agent。
- `k8s-security`：只读 Kubernetes 安全评估 Agent。

三个 Kubernetes Agent 分别拥有自己的：

- 稳定 Agent ID；
- Agent Card；
- 服务 URL 和端口；
- A2A Executor；
- 工具权限策略；
- 健康状态和任务生命周期。

| Agent | 稳定 ID | 端口 | 权限 |
|---|---|---:|---|
| K8s Orchestrator | `k8s-orchestrator` | 8051 | 写操作需要审批 |
| K8s Ops | `k8s-ops` | 8052 | 只读 |
| K8s Security | `k8s-security` | 8053 | 只读 |

Host Runtime 当前运行在 Backend 进程内。未来可以使用相同能力将 Host
进一步封装为独立 A2A 服务，但这不是当前 MVP 的运行前提。

### 3.2 共享 Agent Runtime

`agents/shared-runtime/a2a_runtime` 是可安装的本地 Python 包，包含：

- MCP SSE 连接与重连；
- MCP JSON Schema 到 LangChain Tool 的转换；
- 工具 allow、deny 和 approval-required 策略；
- 可复用的 LangGraph MCP Agent；
- A2A Executor、流式状态和 Artifact 适配；
- Agent YAML 配置和结构化结果模型；
- Pending Action 创建、摘要签名和审批后续执行。

共享 Runtime 是基础设施包，不是独立 A2A 服务。三个 Agent 分别安装它，
并通过自己的 Agent Card 和 Executor 对外提供能力。

### 3.3 协议边界

单智能体聊天：

```text
Playground → Backend A2A Client → 用户指定的 A2A Agent
```

多智能体协作：

```text
Playground → Backend / Host
Host → a2a-sdk → 选中的子 A2A Agent
子 Agent → MCP → Kubernetes
```

Backend 的 REST/SSE 只用于浏览器适配和管理，不替代 Agent 之间的 A2A 协议。

## 4. Agent 职责

### 4.1 K8s Ops Agent

Ops Agent 负责观察和诊断，包括：

- Pod、Deployment、DaemonSet 和 Node 状态；
- 日志、事件和资源使用情况；
- Rollout 状态；
- 拓扑、存储和工作负载关系；
- 故障根因和建议操作。

Ops 不能执行 apply、patch、delete、restart、scale、exec、文件变更、
Node 变更、Helm 变更或集群注册。

输出可以包含结构化 `diagnosis` Artifact：摘要、严重级别、证据、可能根因、
建议操作和是否需要变更。

### 4.2 K8s Orchestrator Agent

Orchestrator 负责规划 Kubernetes 变更，并在审批后执行：

- 应用 YAML；
- Patch 资源；
- 扩缩容；
- 重启工作负载；
- Rollout 暂停、恢复和回滚；
- 更新镜像；
- 添加 Label 和 Annotation；
- 允许范围内的 Helm 安装。

所有写工具都属于 `approval_required`。Agent 可以在审批前生成方案、Manifest
和差异，但不能调用 MCP 写工具。

以下高风险能力在 MVP 中全局禁止：

- 集群注册；
- 任意 Pod Exec；
- 文件上传和删除；
- 强制删除；
- Node Drain；
- Helm Uninstall。

Orchestrator 可以输出 `change_plan`、`pending_action` 和
`execution_result` Artifact。

### 4.3 K8s Security Agent

Security Agent 使用只读工具检查：

- Workload Security Context；
- RBAC、ServiceAccount 和权限关系；
- 镜像标签和镜像风险；
- CPU、内存约束；
- NetworkPolicy 覆盖；
- 特权容器和其他高风险配置。

Security 不读取 Secret 明文，工具结果中的疑似凭据会被脱敏。它只输出
安全发现、证据和修复建议，不直接执行修复。

## 5. Host Agent 与动态编排

Host 是由 LLM 驱动的 LangGraph ReAct 风格 Agent。它可以动态决定：

- 是否需要向用户补充询问；
- 是否需要查看可用 Agent；
- 创建新的远程 A2A Task；
- 延续已有远程 Task；
- 查询远程 Task 或 Artifact；
- 请求用户审批；
- 委派验证；
- 汇总最终结果。

Host 可使用的是 A2A 操作，而不是 Kubernetes 工具：

- `list_remote_agents`
- `delegate_task`
- `continue_task`
- `get_remote_task`
- `cancel_remote_task`

路由使用稳定 `agent_id`，不依赖可能重复或变化的显示名称。候选 Agent
会先根据技能、健康状态、风险等级和内容模式过滤，再交给 LLM 选择。

对于每个多智能体会话，SQLite 保存：

```text
(run_id, agent_id) → remote context_id + latest task_id
```

后续的“继续”“执行刚才方案”“再验证一次”等请求会复用远程 A2A Context。

`orchestration_run` 只是持久化执行轨迹的外壳，负责记录 Host 决策、子任务、
Artifact、审批和状态，不向 Host 强加固定工作流。

## 6. 工具权限和审批闭环

工具策略运行在共享 Runtime 内，因此即使用户直接与 Orchestrator 聊天，
也不能绕过审批。

写操作处理流程：

1. LLM 提议调用写工具。
2. Runtime 暂停执行，不调用 MCP。
3. Runtime 规范化工具名称和参数。
4. 创建包含风险信息和摘要签名的 `pending_action`。
5. A2A Task 进入 `input_required`。
6. Backend 持久化审批，并通过 SSE 推送到前端。
7. 用户批准或拒绝。
8. 批准后复用相同 A2A `task_id` 和 `context_id`。
9. Runtime 只执行与已批准摘要完全匹配的调用。
10. 参数发生变化时，必须创建新的审批。

只读工具自动执行。拒绝后控制权回到 Host，由 Host 解释替代方案或继续追问。

## 7. 稳定路由与上下文延续

Agent Registry 使用稳定 ID：

- `k8s-ops`
- `k8s-orchestrator`
- `k8s-security`

Agent 显示名称只用于 UI，不作为路由主键。因此即使两个远程 Agent 名称相同，
也不会造成路由漂移。

`A2AGateway` 统一负责：

- Agent Card 获取；
- A2A 消息发送和流式响应；
- Task 和 Context ID 提取；
- 远程状态与 Artifact 规范化；
- 上下文复用；
- 超时和错误映射。

## 8. 持久化

SQLite 是系统事实来源，主要数据包括：

- Agents；
- Conversations；
- Messages；
- Orchestration Runs；
- Run Steps；
- Remote Task Bindings；
- Approvals；
- Artifacts；
- Events；
- Migration Records。

写入使用事务和外键，事件按追加方式保存。Backend 启动时自动初始化数据库。

首次启动时，旧的 `backend/data/*.json` 会被导入一次。Migration Record
防止重复导入，原 JSON 文件保留为备份，不会被修改。

## 9. API 与流式事件

原有 Agent、Conversation、Message 和 Event API 保持可用。

新增的核心管理接口：

- `POST /api/runs/list`
- `POST /api/runs/get`
- `POST /api/approvals/list`
- `POST /api/approvals/decide`

多智能体请求会创建或恢复 Orchestration Run，并通过 SSE 输出规范化事件：

- `run_status`
- `agent_routing`
- `task_status`
- `tool_call`
- `tool_result`
- `artifact`
- `approval_required`
- `text`
- `error`
- `done`

事件按适用范围携带 `run_id`、`task_id`、`agent_id` 和 `conversation_id`。

## 10. 前端设计

前端保留四个主入口：

- Agents；
- Chat；
- Events；
- Multi-Agent。

Multi-Agent 使用统一浅色应用框架，不创建第二套品牌导航。页面内部采用：

```text
多智能体会话列表 | Host 对话区 | 实时执行轨迹
```

主要能力：

- 展示 Host 与具体子 Agent 身份；
- 实时显示路由和工具调用；
- 展开查看工具参数和结果；
- 展示结构化 Artifact；
- 展示写操作、目标、参数和风险；
- 在审批卡片中批准或拒绝；
- 页面刷新后恢复会话和审批状态。

较窄屏幕下，右侧执行轨迹变为抽屉；移动端优先展示对话区。

## 11. 异常处理

- MCP 连接失败时，A2A Task 进入失败状态并返回可理解的错误。
- 子 Agent 超时时，不假设远程操作一定未执行；重试前先查询 Task 状态。
- 只有只读或已知幂等操作允许自动重试。
- Agent Card 刷新失败时保留最后一次有效注册信息。
- SSE 断开不会自动取消持久化 Run，前端可以重新加载事件。
- 审批决定保持幂等。
- 不支持取消时明确返回状态，不能伪装取消成功。
- 工具结果在持久化和重新交给 LLM 前执行长度限制与敏感信息脱敏。

## 12. 启动与部署

### 12.1 本地开发

本地开发使用五个进程：

- 三个独立 Python A2A Agent；
- 一个 Python Backend / Host；
- 一个 Vite Frontend。

具体命令见根目录 [guide.md](../../../guide.md)。

### 12.2 Docker Compose

Docker Compose 启动：

- frontend；
- backend；
- k8s-ops；
- k8s-orchestrator；
- k8s-security。

Agent Card 的公开 URL 通过环境变量配置，不使用 `0.0.0.0`。SQLite 使用
持久化 Volume。Backend 等待三个 Agent 健康检查通过后自动注册。

## 13. 测试范围

Backend 和 Runtime 测试覆盖：

- 工具 allow、deny 和 approval-required 分类；
- 参数摘要匹配；
- JSON 到 SQLite 的一次性迁移；
- 稳定 ID 路由和重名 Agent；
- 远程 Context 复用；
- A2A 状态和 Artifact 规范化；
- 审批决定幂等；
- Run 和 Event 持久化；
- 使用 Fake A2A Client 验证 Host Tool。

Agent Contract 测试验证三个 Agent Card，以及只读、需要审批和禁止请求。

前端测试覆盖事件 Reducer、执行轨迹、审批和 Artifact 的基础行为，并执行
生产构建与浏览器视觉验收。

## 14. 验收标准

1. Ops、Orchestrator 和 Security 是三个独立的 `a2a-sdk` 服务。
2. 三个 Agent 都能通过 Agent Card 被发现，并支持单独聊天。
3. Host 只通过 `a2a-sdk` 委派任务，并使用稳定 Agent ID 路由。
4. Host 再次委派给同一 Agent 时复用 A2A Context。
5. Ops 和 Security 无法调用写工具。
6. Orchestrator 在精确审批前无法执行写操作。
7. 审批决定、Task ID 和 Context ID 形成完整闭环。
8. SQLite 持久化 Run、子任务、审批、Artifact、消息和事件。
9. 旧 JSON 数据只导入一次，且不修改源文件。
10. Multi-Agent 页面显示实时路由、工具调用、Artifact 和审批。
11. Docker Compose 定义并健康检查完整 MVP。
12. 自动化测试和前端生产构建通过。
