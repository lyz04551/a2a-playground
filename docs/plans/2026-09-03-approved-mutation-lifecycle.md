# 审批写操作生命周期实施计划

> **执行要求：** 按 TDD 顺序逐项实施，每个生产代码改动前必须先看到对应测试失败。

**目标：** 让原始请求“可以创建一个nginx pod么 然后检查一下有没有什么问题”稳定完成预检、一次审批写入、验证和最终收口，不再出现审批按钮长时间 loading、孤立 Working 工具、虚假成功或跨轮重复创建。

**架构：** 在 Runtime 层串行化共享 MCP session；在 API 层将 Auto 审批接受与后台执行拆开；在 RunService 中只用真实 continuation 结果恢复 Host；在 Host ReAct 状态中对跨轮等价失败任务应用统一预算。现有审批参数与 MCP 工具协议保持不变。

**技术栈：** Python 3.12、asyncio、FastAPI、SQLAlchemy/PostgreSQL、LangGraph、pytest、React、Node test、Vite。

---

### 任务一：保证 MCP session 并发安全

**文件：**

- 修改：`tests/runtime/test_mcp_client.py`
- 修改：`agents/shared-runtime/a2a_runtime/mcp_client.py`

**步骤：**

1. 新增并发 fake session 测试，同时发起多个 `call_tool`，断言 session 内最大并发数为 1。
2. 运行该测试并确认因当前并发复用而失败。
3. 新增超时/异常后 session 失效测试，断言下一次调用重新建连。
4. 运行测试并确认失败原因准确。
5. 用 client 操作锁串行化 session 生命周期，并在 session 级异常后安全断开。
6. 运行 `pytest -q tests/runtime/test_mcp_client.py`，确认通过。

### 任务二：拆分 Auto 审批接受与实际执行

**文件：**

- 修改：`tests/backend/test_approval_service.py`
- 修改：`tests/backend/test_runs_api.py`
- 修改：`backend/approvals/service.py`
- 修改：`backend/api/runs.py`

**步骤：**

1. 新增测试：第一个 Auto 审批请求只取得执行所有权，接口不等待阻塞中的 gateway。
2. 新增测试：重复请求不再次 delegate，也不触发第二次 Host resume。
3. 运行目标测试并确认当前同步实现失败。
4. 将 `ApprovalService` 拆为原子接受与执行已取得所有权的 continuation；Direct 模式保留同步兼容行为。
5. 在 runs API 中跟踪 Auto 审批后台执行任务，执行结束后仅调用一次 `resume_after_approval`。
6. 运行审批 service/API 测试并确认通过。

### 任务三：严格校验执行结果并闭合事件

**文件：**

- 修改：`tests/backend/test_run_service.py`
- 修改：`backend/orchestration/service.py`

**步骤：**

1. 新增测试：`executing`、duplicate、空成功文本和 Agent stream failure 均不能进入验证。
2. 新增测试：重复终态回调不会产生第二个 `approval.decided` 或 `tool.completed`。
3. 运行目标测试并确认当前逻辑失败。
4. 收紧 continuation 成功判定，并让事件闭合具备幂等性。
5. 运行 RunService 测试并确认通过。

### 任务四：阻止跨轮等价失败任务循环

**文件：**

- 修改：`tests/backend/test_host_orchestration_engine.py`
- 修改：`backend/host/orchestration/models.py`
- 修改：`backend/host/orchestration/validation.py`
- 修改：`backend/host/orchestration/engine.py`

**步骤：**

1. 构造连续返回不同任务 ID、但 objective/input/Agent 等价的 ReAct decision 测试。
2. 断言引擎在统一预算耗尽后终止，而不是继续到最大轮数。
3. 运行测试并确认当前实现会继续创建任务。
4. 在 HostRunState 中持久化语义失败次数，并在 decision 校验后、执行前应用跨轮预算。
5. 运行 Host engine 与 plan validation 测试并确认通过。

### 任务五：前端审批反馈与端到端验收

**文件：**

- 修改：`frontend/src/pages/WorkspacePage.jsx`
- 修改或新增：`frontend/src/components/workspaceState.test.js`
- 新增或修改：`tests/backend/test_approved_mutation_workflow.py`

**步骤：**

1. 新增前端测试，断言审批接受响应后本地状态进入 executing/已接受，按钮结束 loading，终态由事件流覆盖。
2. 新增后端验收测试，固定原始中文请求并模拟预检、审批、一次 apply、验证与最终回答。
3. 断言 apply 仅调用一次、验证晚于 tool completion、无孤立工具调用、无等价重复任务、运行只有一个终态。
4. 运行测试并确认失败。
5. 实现最小前端状态调整和必要的验收 fixture。
6. 运行前后端目标测试并确认通过。

### 任务六：真实回归、全量验证与提交

**步骤：**

1. 启动本 worktree 对应的后端与三个 Agent，避免混用主项目旧进程。
2. 使用唯一 Pod 名称执行原始中文请求，批准一次写操作。
3. 验证事件顺序、按钮状态、Pod 存在及 Ready、最终回答和无重复轮次。
4. 删除测试 Pod，并确认清理成功。
5. 运行后端全量测试、Runtime 测试、前端全量测试和 `npm run build`。
6. 运行 `git diff --check`，检查工作区只包含本任务文件。
7. 提交实现并汇报根因、改动文件、真实链路时序、测试结果和 commit。
