# Workspace 消息 Agent 归属设计

## 目标

工作台中的每条 Agent 消息应明确显示真实来源，避免所有内容统一显示为“Agent”。子 Agent 的回复显示注册名称，Host 根任务的最终输出显示“Host Agent 总结”。

## 数据设计

在 Run 事件归一化阶段处理消息来源，并把结果保存在消息对象中：

- `agentId`：优先取消息事件的 `agent_id`，其次取对应任务的 `agentId`。
- `agentName`：使用 Agent 注册表把 `agentId` 映射为展示名称。
- 根任务且无子 Agent 来源的消息标记为 Host 输出，名称显示“Host Agent 总结”。
- 用户消息保持“你 / You”。
- 旧事件既没有来源字段、也无法从任务恢复时，兜底显示“Agent”。

来源信息属于消息状态，不由展示组件根据当前页面状态临时推测，因此事件实时流和 PostgreSQL 历史回放结果一致。

## 前端展示

`MessageTimeline` 直接读取消息上的 `agentName`：

- Auto 子任务：`K8s Security Agent`、`K8s Resource Orchestrator Agent` 等具体名称。
- Auto 根任务总结：`Host Agent 总结`。
- Direct 回复：目标 Agent 的具体名称。
- 兼容旧数据：`Agent`。

消息正文、工具活动和 Run Trace 的布局保持不变。

## 错误与兼容处理

- 未注册或已删除的 Agent 使用 `agentId` 作为名称。
- 缺少 `agent_id` 的旧消息尝试从 `taskId` 对应任务恢复。
- 完全无法判断来源时不错误标记为 Host，而是显示通用“Agent”；只有根任务输出明确标记为 Host。

## 测试

- reducer 测试覆盖事件自带 `agent_id`、从任务继承来源、Host 根消息和旧消息兜底。
- 消息展示测试覆盖具体 Agent 名称及“Host Agent 总结”。
- 运行完整前端测试与生产构建。
