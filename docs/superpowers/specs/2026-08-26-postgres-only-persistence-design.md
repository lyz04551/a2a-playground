# Postgres 单数据库技术栈持久化设计

## 目标

将后端的 SQLite 持久化和所有 Agent 的 LangGraph 内存 checkpointer 替换为基于 Postgres 的持久化。Docker Compose 将成为标准的本地运行方式。新的部署从空的 Postgres 数据库开始，不迁移现有 SQLite 和旧版 JSON 数据。

本次改造必须保持现有后端 API、Direct 对话、Auto 编排、审批流程、事件流和前端展示行为不变。

## 范围

包含：

- 将后端业务数据迁移到 Postgres。
- 删除 SQLite 运行时支持、SQLite 配置、SQLite 专用 SQL 和旧版 JSON 到 SQLite 的导入器。
- 在 Docker Compose 中增加具有本地持久卷和健康检查的 Postgres 服务。
- 所有使用共享运行时的 Agent 改用 Postgres LangGraph checkpointer。
- 在复用相同 LangGraph `thread_id` 时，使 Agent 对话状态能够跨 Agent 进程重启恢复。
- 增加 Repository、API、Compose 和浏览器自动化回归测试。
- 补充启动、配置、重置和测试命令文档。

不包含：

- 迁移已有的 `playground-local.db` 或旧版 JSON 数据。
- 将 LangGraph checkpoint 内部表暴露为后端业务 API。
- 重新设计前端交互体验。
- 在本次改造中将现有自定义审批协议替换为 LangGraph `interrupt`。

## 架构

一个 Postgres 容器承载两个逻辑数据库：

- `playground`：后端负责管理的业务表。
- `langgraph`：由 LangGraph 管理的 checkpoint 表。

后端只访问 `playground`，Agent 只访问 `langgraph`。在条件允许时，两者使用不同的连接地址和账号权限。后端代码不得查询或修改 LangGraph 内部表。

继续保持以下稳定标识链路：

```text
conversation_id -> A2A context_id -> LangGraph thread_id
```

每个 Agent 继续使用包含 Agent 标识的 context ID，避免参与同一个 Auto 会话的多个 Agent 意外共享 Graph 状态。

## 后端持久化

将 Repository 重命名为与数据库实现无关的 `DatabaseRepository`，但运行时只支持 Postgres。通过必需的 `DATABASE_URL` 环境变量创建 SQLAlchemy Engine。如果缺少该变量、URL 协议不受支持或数据库不可访问，后端应输出明确错误并启动失败。

复用现有 SQLAlchemy Core 表定义和 Repository 公共方法，避免修改 API 和编排层调用方。SQLite 专用实现按以下方式替换：

- Agent upsert 改用 PostgreSQL `INSERT ... ON CONFLICT`。
- 删除 SQLite PRAGMA、WAL、busy timeout、数据库文件路径和目录创建逻辑。
- 消息数量和更新时间不再依赖 SQLite JSON 函数；改为在事务中锁定会话行，读取 JSON、合并修改并写回。这样可以保持 JSON 数据和普通列一致，同时避免在 Repository 中散布 Postgres 专用 JSON 表达式。
- 使用兼容 PostgreSQL 的索引和约束。
- 使用 Alembic 管理表结构创建和升级，不再在应用运行时检查表并手写 `ALTER TABLE`。

应用开始提供服务前，应运行明确的迁移命令或迁移入口。数据库结构迁移失败时，后端不得进入就绪状态。

## Agent checkpoint

共享 Agent 运行时使用 `AsyncPostgresSaver`，因为 Graph 当前通过异步流执行。Docker Compose 运行时必须配置 `AGENT_CHECKPOINT_DATABASE_URL`。

checkpointer 在 Agent 初始化时打开一次，在编译后的 Graph 整个生命周期内保持可用，并在 Agent 关闭时释放。所需表结构通过部署或启动阶段的迁移步骤创建，并保证在多个 Agent 启动前安全完成。

Graph 状态读取使用异步接口，包括 `aget_state`，避免异步流路径调用同步 checkpointer 方法。

Postgres 不可用时，Agent 就绪状态应显示为 degraded，并且不得静默回退到内存模式，防止系统表面上支持持久化，实际仍只在进程内保存状态。

现有 `_pending_by_context` 审批缓存不属于 checkpoint 范围，后端审批记录仍是权威数据。除非当前 A2A 恢复协议能够根据后端持久化记录重建待审批动作，否则本次改造不承诺 Agent 重启后仍能继续原审批。测试必须明确覆盖这一行为；如果还需改造协议，应在测试结论中说明。

## Docker Compose 和配置

Docker Compose 增加一个带命名持久卷和健康检查的 Postgres 服务。后端和 Agent 服务必须依赖健康状态正常的 Postgres 服务。

需要配置以下连接地址：

```text
DATABASE_URL=postgresql+psycopg://...@postgres:5432/playground
AGENT_CHECKPOINT_DATABASE_URL=postgresql://...@postgres:5432/langgraph
```

账号密码通过环境变量和开发环境示例默认值提供，不得提交生产密码。删除 Postgres 命名卷会清空本地后端数据和 checkpoint 数据，文档必须明确说明这是破坏性操作。

## 故障与一致性行为

- 后端数据库故障：启动或就绪检查失败，不得使用内存替代方案继续提供请求。
- Agent checkpoint 故障：Agent 就绪状态变为 degraded，请求返回依赖错误，同时保留稳定的 context ID。
- 事务失败：整个 Repository 写操作回滚。
- 重复事件或审批写入：继续通过 Postgres 唯一约束及幂等 Repository 行为进行限制。
- 并发消息写入：更新会话 JSON 中的消息数量和更新时间前锁定对应会话行。
- 数据库重置：系统从空数据开始，并通过正常的 bootstrap 或注册流程注册三个配置的 Agent。

## 验证策略

### Repository 和 API 测试

测试使用可清理的临时 Postgres 数据库，覆盖：

- 从空数据库执行结构迁移；
- Agent 注册和 upsert；
- 会话、消息、事件、Run、编排任务、远程绑定、审批和产物操作；
- 分页、排序、约束、级联行为和事务回滚；
- 后端重启后仍能读取已写入的数据；
- 缺少 `DATABASE_URL` 或数据库不可访问时给出明确的启动错误。

### Agent checkpoint 测试

- 两个运行时实例使用相同 `thread_id` 和 Postgres 数据库时，可以读取相同的历史 Graph 状态。
- 带不同 Agent 标识的 thread ID 相互隔离。
- Agent 重启后保留多轮对话上下文。
- 异步状态读取和关闭过程完成且不产生资源警告。
- checkpoint Postgres 缺失或不可访问时显示 degraded，不回退到内存模式。

### Compose 冒烟测试

- Compose 配置包含 Postgres、健康检查、持久卷、两个数据库连接地址及正确的依赖顺序。
- 从空数据卷启动时，完整系统最终达到健康状态。
- 重启后端和 Agent 容器不会删除已有会话或 checkpoint。

### 浏览器回归测试

使用真实浏览器访问 Compose 启动的系统：

1. 确认三个 Agent 已注册并在页面可见。
2. 分别为三个 Agent 打开 Direct 会话，发送确定性的只读请求，并等待回复完成。
3. 确认用户消息、Agent 消息、状态标识和工具活动都能正常显示，页面没有运行错误。
4. 创建一个协调三个 Agent 的 Auto 会话，确认 Host 决策、Agent 任务卡片、事件活动和最终输出都能正常显示。
5. 刷新页面，确认会话历史仍然可见。
6. 重启后端和 Agent 服务，重新打开相同会话，确认后端历史仍然存在，并且 Agent 能在后续消息中保留之前的 LangGraph 上下文。

依赖 LLM 或 Kubernetes MCP 服务的测试必须使用明确配置的测试依赖。Repository 和前端展示测试不得依赖对不受控生产集群的写操作。

## 实施顺序

1. 增加 Postgres 依赖、数据库结构迁移和临时测试数据库支持。
2. 改造后端 Repository，并通过 Postgres 集成测试。
3. 增加 Compose Postgres 配置，验证后端数据能够跨重启持久化。
4. 将共享 Agent 运行时改为 `AsyncPostgresSaver`，验证 checkpoint 恢复。
5. 执行 API、运行时、Compose 和浏览器回归测试。
6. 只有在 Postgres 路径验证通过后，才删除 SQLite 代码、SQLite 测试、旧数据库路径配置和旧版数据迁移启动逻辑。

## 验收标准

- Docker Compose 只在 Postgres 健康后启动依赖服务。
- 后端和 Agent 的生产代码不再使用 SQLite 或 `MemorySaver`。
- 全新部署能够创建所需数据库结构，并注册预期的三个 Agent。
- Direct 和 Auto 会话能够完成，且前端展示正常。
- 后端历史和 LangGraph 对话状态能够跨对应的进程或容器重启恢复。
- 现有非数据库相关回归测试保持通过。
- 不从已有 SQLite 或 JSON 文件导入任何数据。
