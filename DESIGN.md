# A2A Playground 设计说明

本项目是一个面向 Kubernetes 场景的 A2A 多智能体工程化 MVP。

完整设计见：

[A2A Kubernetes 多智能体工程化 MVP 设计](docs/superpowers/specs/2026-07-28-a2a-k8s-engineering-mvp-design.md)

## 核心设计

- 每个 Kubernetes 智能体都是基于 `a2a-sdk==0.3.25` 的独立 A2A 服务。
- Host Agent 使用大模型控制对话节奏、追问、路由和最终总结。
- Host 只能通过 A2A 协议调用子智能体，不直接调用 Kubernetes MCP。
- 所有写操作必须经过用户审批；未归属工具默认拒绝。
- Backend 与本地 Kubernetes Agent 解耦，在零 Agent 时也能独立启动，并支持运行时注册外部 A2A Server。
- A2A `task_id` 和 `context_id` 会被保存并复用，以支持上下文延续。
- SQLite 持久化对话、任务、执行轨迹、审批、产物和事件。
- 单智能体聊天与多智能体协作同时保留。

## 系统组成

| 服务 | 端口 | 职责 |
|---|---:|---|
| Frontend | 5173 | Agent 管理、单智能体聊天、多智能体协作和执行轨迹 |
| Backend / Host | 8050 | API、Host Agent、A2A 网关、审批和 SQLite |
| K8s 资源编排 Agent | 8051 | 通过 MCP 创建和管理 Kubernetes 资源，写操作需要审批 |
| K8s Ops | 8052 | 日志、事件、资源状态和故障诊断 |
| K8s Security | 8053 | 工作负载、RBAC、镜像和网络安全检查 |
| K8s Infrastructure | 8054 | 节点维护、默认类和集群注册管理 |
| K8s Helm | 8055 | Helm release 生命周期管理 |
| K8s Incident Responder | 8056 | 基于证据链的 Kubernetes 故障诊断 |
| K8s Capacity Planner | 8057 | CPU、内存、IP、Pod 密度和 HPA 容量规划 |
| K8s GPU Specialist | 8058 | GPU/大模型工作负载生成、部署和诊断 |

## 调用关系

单智能体聊天：

```text
用户 → Playground → Backend A2A Client → 指定的 A2A Agent
```

多智能体协作：

```text
用户 → Playground → Host Agent
                       ↓
                 A2A Gateway
                       ↓
            任意已注册 A2A Agent
                       ↓
          Kubernetes MCP 或外部能力
```

Host Agent 负责选择子智能体，但工具权限由子智能体内部的共享 Runtime
确定性执行。大模型提示词不能绕过工具策略或审批。

Compose 提供八个本地 Agent 作为可选开发环境，但 Backend 不依赖它们的
启动顺序或健康状态。外部 A2A Server 只需提供标准 Agent Card 即可注册。

## 前端设计

应用使用统一的浅色视觉体系。全局左侧导航只出现一次，Multi-Agent 页面内部
使用以下三栏结构：

```text
多智能体会话列表 | Host 对话区 | 实时执行轨迹与审批
```

较窄屏幕下，执行轨迹收进抽屉；移动端隐藏会话列表，优先保证对话体验。

## 本地运行

纯本地 Python 和前端启动命令见：

[本地启动指南](guide.md)
