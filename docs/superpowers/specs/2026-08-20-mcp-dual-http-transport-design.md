# MCP 双 HTTP 传输支持设计

## 目标

让三个 Kubernetes Agent 通过共享 runtime 同时支持以下 MCP 远程传输：

- `streamable_http`：当前 MCP Streamable HTTP transport。
- `sse`：兼容旧 MCP HTTP+SSE transport。

传输方式由部署者显式配置，不进行运行时协议探测或自动回退。

## 配置

新增环境变量 `MCP_TRANSPORT`，允许值为 `streamable_http` 和 `sse`。默认值为 `sse`，以保持现有部署行为不变。

Streamable HTTP 示例：

```env
MCP_TRANSPORT=streamable_http
K8S_MCP_URL=http://mcp-server:9096/mcp
```

旧 HTTP+SSE 示例：

```env
MCP_TRANSPORT=sse
K8S_MCP_URL=http://mcp-server:9096/sse
```

配置加载阶段必须验证 `MCP_TRANSPORT`。其他值应产生包含变量名和允许值的明确错误，不能静默回退。

## 架构和数据流

`AgentRuntimeConfig` 负责读取并验证 transport。`RuntimeMCPAgent` 将配置值传给共享的 `K8sMCPClient`。客户端在建立连接时只根据该值选择一个 transport：

- `streamable_http` 使用 MCP Python SDK 的 `streamablehttp_client`。
- `sse` 继续使用现有的 `sse_client`。

两种 transport 建立连接后都转换为现有 `ClientSession` 边界，因此工具发现、工具调用、超时、重连、审批和 A2A 行为保持不变。三个 Agent 不包含各自的 transport 分支。

## 错误处理

- 无效 transport 在配置加载时失败。
- 连接和初始化错误继续记录为 MCP dependency error，并让 Agent readiness 显示 `degraded`。
- 工具调用超时和 `httpx.TransportError` 继续沿用现有断开、重连和单次重试行为；重连仍使用配置中指定的同一种 transport。
- 不因连接失败切换 transport，避免掩盖 URL 或服务端配置错误。

## 兼容性和文档

- 未设置 `MCP_TRANSPORT` 时继续使用 `sse`。
- 保留 `MCP_SSE_READ_TIMEOUT`，因为 Streamable HTTP 响应也可能使用 SSE 流；此次不重命名该变量，避免额外迁移成本。
- 更新 Compose、各 Agent 的 `.env.example`、README 和运行指南，展示两种合法组合。
- Frontend SSE、Backend run SSE 以及 Host 与 Agent 之间的 A2A transport 均不在本次改动范围内。

## 测试

按测试驱动方式覆盖：

1. 配置默认得到 `sse`。
2. 两个合法 transport 均可加载，无效值被拒绝。
3. `sse` 选择旧 `sse_client`，并按现有二元返回值建立 `ClientSession`。
4. `streamable_http` 选择 `streamablehttp_client`，正确处理其三元返回值并建立 `ClientSession`。
5. 两种 transport 下既有工具发现、调用、超时和重连测试继续通过。
6. 运行 shared runtime 测试集，确认三个 Agent 的公共行为没有回归。

## 非目标

- 不实现 `auto` 探测或自动回退。
- 不支持 stdio transport。
- 不修改 MCP Server。
- 不改变 A2A 或前端事件流协议。
