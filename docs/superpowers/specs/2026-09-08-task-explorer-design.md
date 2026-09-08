# Task Explorer 页面设计

## 目标

新增 `/tasks` 页面，用统一视图展示历史 Run 中 Host Agent、子 Agent、MCP 工具、审批和结果的完整流转。页面同时支持 Auto 与 Direct：Auto 展示 Host 多轮编排，Direct 从用户指定的 Agent 开始，不虚构 Host 节点。

## 页面结构

页面采用三段式布局：

1. 顶部摘要显示 Run ID、模式、状态、开始时间、耗时、任务数、Agent 数、工具调用数和审批数。
2. 左侧 Run 浏览器显示历史 Run，支持按 Auto/Direct、运行状态、Agent 和关键词筛选；选择 Run 后更新主体内容。
3. 主体显示纵向任务流，右侧详情抽屉按需展示节点完整内容。

窄屏时左侧 Run 浏览器进入抽屉，任务流保持主视图；节点详情继续使用抽屉。

## 任务关系模型

页面只消费现有 Run、Task 和 Run Event，不引入第二套任务状态。

Auto 模式按以下层级展示：

```text
Host Root Task
  -> Host Round N / Decision
    -> Agent Task
      -> MCP Tool Call / Result
      -> Human Checkpoint
    -> Evaluation
  -> Host Summary
```

Direct 模式按以下层级展示：

```text
Selected Agent Root Task
  -> MCP Tool Call / Result
  -> Human Checkpoint
  -> Agent Result
```

任务关系优先使用 `parent_task_id`、Round 事件和 Task ID；远程 A2A Task ID 作为关联信息展示，不用于替代本地稳定 ID。

## 组件边界

- `TasksPage`：加载 Run、Agent 和选中 Run 的详情，管理筛选与选择状态。
- `TaskRunList`：历史 Run 搜索、过滤与状态摘要。
- `TaskFlow`：把标准化 Run State 渲染成 Auto 或 Direct 纵向关系流。
- `TaskFlowNode`：显示 Host、Agent、工具、审批、评估和结果节点的紧凑摘要。
- `TaskNodeDrawer`：显示节点输入、输出、完成标准、工具参数、工具结果、审批、错误和原始事件。
- `taskExplorer` 纯函数模块：从现有 Run Event 构造页面视图模型、统计数据和筛选结果。

现有 `runEvents` reducer 继续作为事件语义来源。Task Explorer 不复制审批状态机或 Host 编排逻辑。

## 数据流

1. 页面加载现有 Runs 与 Agent 注册信息。
2. 选择 Run 后并行读取 Run 详情和 Run Events。
3. 使用现有事件 reducer 重放事件，得到任务、轮次、消息、工具和审批状态。
4. `taskExplorer` 将标准化状态转换为只读页面模型。
5. 点击节点只更新本地选中状态，不重新请求数据。

首版为只读诊断页面，不在 Task Explorer 内执行审批、取消或重试，避免产生第二个操作入口。相关操作仍在 Workspace 完成。

## 内容与滚动

- 所有布局列使用 `minmax(0, 1fr)` 和 `min-width: 0`，防止 YAML、JSON 和错误文本撑宽页面。
- 节点仅显示短摘要，长内容放入详情抽屉。
- YAML、JSON、日志和原始事件使用 `pre-wrap`、`overflow-wrap: anywhere`、受控最大高度和内部纵向滚动。
- 内层滚动使用可传递的 overscroll 行为，滚动到边界后继续滚动页面外层。
- 审批参数和结果明确区分，不显示内部控制制品。

## 状态与异常

- Run 或事件加载失败时保留 Run 列表，并在主体提供可重试错误状态。
- 缺失 Agent 注册信息时显示稳定 Agent ID。
- 旧事件缺少 Round 或远程 Task ID 时降级为按 Task 父子关系和事件顺序展示。
- 正在运行的 Run 可定时刷新或复用现有事件追赶接口；首版采用轻量轮询，不创建第二条执行流。
- Direct 根任务必须显示目标 Agent，不显示 Host Agent。

## 导航

在主导航新增“Tasks / 任务”入口，路由为 `/tasks`。Workspace 的 Run Trace 提供“查看完整任务”链接，并携带 `run` 查询参数直接定位当前 Run。

## 测试与验收

- 纯函数测试覆盖 Auto 多轮、并行子任务、Direct 根任务、工具、连续审批、失败与旧事件降级。
- 组件测试覆盖筛选、Run 切换、节点展开和 Direct 不出现 Host。
- CSS 回归测试覆盖窄屏、长 YAML/JSON、内部滚动与宽度约束。
- 运行完整前端测试和 production build。

验收标准：

1. Auto Run 可以按轮次追踪 Host 到每个子 Agent、工具、审批、评估和最终总结。
2. Direct Run 只显示目标 Agent 链路。
3. 任一节点可查看完整输入输出和对应原始事件。
4. 长内容不撑破页面，纵向能够滚到底部。
5. 页面不改变后端、A2A、MCP 或审批语义。
