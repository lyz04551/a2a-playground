# Kubernetes 八 Agent 能力扩展设计

## 目标

在保持 `Host -> A2A Agent -> Kubernetes MCP` 调用边界的前提下，将当前三个 Agent 扩展为五个基础能力 Agent 和三个首批场景 Agent，使 `http://10.2.0.57:9096/mcp` 当前暴露的 66 个工具全部至少归属于一个 Agent。

Backend 与这些 Kubernetes Agent 保持解耦：Backend 在零 Agent、部分 Agent 或全部本地 Agent 离线时都能独立启动和提供 API，并能在运行期间接入任意符合 A2A 协议的外部 Server。

本阶段优先功能覆盖，同时保留以下最低保护：未明确配置的工具默认拒绝，所有集群变更必须经过现有审批流程。

## 系统结构

```text
Host
 ├─ 基础能力 Agent
 │   ├─ K8s Ops                    :8052
 │   ├─ K8s Security               :8053
 │   ├─ K8s Orchestrator           :8051
 │   ├─ K8s Infrastructure         :8054
 │   └─ K8s Helm                   :8055
 │
 └─ 典型场景 Agent
     ├─ K8s Incident Responder     :8056
     ├─ K8s Capacity Planner       :8057
     └─ K8s GPU Specialist         :8058
```

所有 Agent 都是独立 A2A 服务并直接连接 MCP Server。Agent 之间不互相调用，Host 负责路由、并行调度、依赖上下文传递和最终综合。

Backend 只依赖标准 A2A Agent Card 和 A2A 调用协议，不识别或导入任何具体 Kubernetes Agent 实现。外部 Agent 不要求使用本项目的 MCP、Runtime、LLM 或部署方式。

暂缓实现 Release Manager、Network Troubleshooter 和 Storage Troubleshooter。

## 基础能力 Agent

### K8s Ops

负责通用集群检查、日志、Events、Pod 关联关系、资源使用和 Pod 深度调试。

只读能力：

- `list_k8s_*`
- `get_k8s_*`
- `get_pod_*`
- `describe_k8s_*`
- `list_files_in_k8s_pod`
- `list_pod_all_files`

审批能力：

- `run_command_in_k8s_pod`
- `upload_file_to_k8s_pod`
- `delete_pod_file`
- `delete_k8s_pod`

Skills：

- `cluster.inspect`，Tags 为 `kubernetes, operations, inspection, events, logs`。
- `pod.debug`，Tags 为 `kubernetes, pod, debugging, exec, files`。

Prompt 要求确认 cluster、namespace 和目标资源，按最小证据集调用工具。运行时环境变量中的疑似 Token、密码和密钥不得原样输出。

### K8s Security

负责 RBAC、ServiceAccount、NetworkPolicy、workload securityContext、镜像和环境配置的只读审计。

允许能力：

- `list_k8s_clusters`
- `list_k8s_namespace`
- `list_k8s_node`
- `list_k8s_pod`
- `list_k8s_resource`
- `list_k8s_event`
- `list_k8s_pod_event`
- `list_k8s_deploy_event`
- `get_k8s_resource`
- `get_pod_linked_env_from_yaml`
- `describe_k8s_resource`
- `describe_k8s_pod`

Skill 为 `cluster.security_assess`，Tags 为 `kubernetes, security, rbac, network-policy, workload, image`。

### K8s Orchestrator

负责通用资源变更、Deployment 生命周期和 YAML 模板。

只读能力：

- `list_k8s_*`
- `get_k8s_*`
- `get_pod_*`
- `describe_k8s_*`
- `get_large_model_yaml_example`
- `get_metax_gpu_pod_yaml`
- `get_mthreads_gpu_pod_yaml`

审批能力：

- `annotate_k8s_resource`
- `apply_k8s_yaml`
- `delete_k8s_pod`
- `delete_k8s_resource`
- `delete_k8s_yaml`
- `label_k8s_resource`
- `patch_k8s_resource`
- `pause_k8s_deployment_rollout`
- `restart_k8s_daemonset`
- `restart_k8s_deployment`
- `restore_k8s_deployment`
- `resume_k8s_deployment_rollout`
- `scale_k8s_deployment`
- `stop_k8s_deployment`
- `undo_k8s_deployment_rollout`
- `update_k8s_deployment_image_tag`

Skills：

- `resource.manage`，Tags 为 `kubernetes, yaml, apply, patch, delete`。
- `workload.orchestrate`，Tags 为 `kubernetes, deployment, rollout, scale, rollback`。

移除 Server 当前不存在的 `helm_search_repo`。

### K8s Infrastructure

负责节点维护、StorageClass、IngressClass 和集群注册。

只读能力：

- `list_k8s_clusters`
- `list_k8s_node`
- `list_k8s_resource`
- `get_k8s_node_ip_usage`
- `get_k8s_node_resource_usage`
- `get_k8s_pod_count_running_on_node`
- `get_k8s_storageclass_pv_count`
- `get_k8s_storageclass_pvc_count`
- `get_k8s_top_node`
- `describe_k8s_resource`

审批能力：

- `cordon_k8s_node`
- `drain_k8s_node`
- `taint_k8s_node`
- `uncordon_k8s_node`
- `untaint_k8s_node`
- `set_default_k8s_ingressclass`
- `set_k8s_default_storageclass`
- `register_k8s_cluster`
- `unregister_k8s_cluster`

Skills：

- `node.maintain`，Tags 为 `kubernetes, node, cordon, drain, taint`。
- `storage.configure`，Tags 为 `kubernetes, storageclass, ingressclass`。
- `cluster.registry`，Tags 为 `kubernetes, cluster, registration, kubeconfig`。

### K8s Helm

负责 Helm release 生命周期。

只读能力：

- `helm_list_releases`
- `list_k8s_namespace`
- `list_k8s_resource`
- `get_k8s_resource`

审批能力：

- `helm_install_chart`
- `helm_uninstall_release`

Skill 为 `helm.release_manage`，Tags 为 `kubernetes, helm, chart, release, install, uninstall`。

## 典型场景 Agent

### K8s Incident Responder

负责从故障症状定位根因，首阶段只读。

工具范围：

- 集群、namespace、Pod 和资源查询。
- Pod、Deployment 和通用 Events。
- Pod 日志和资源使用。
- Service、Endpoints 和 Ingress 关联。
- PV 和 PVC 关联。
- Deployment rollout 状态。

固定工作流：

```text
确认目标 -> 获取状态 -> 获取 Events -> 按需读取日志
-> 检查资源压力 -> 检查网络依赖 -> 检查存储依赖
-> 输出根因、证据、置信度和建议
```

Skill 为 `incident.respond`，Tags 为 `kubernetes, incident, crashloop, pending, unavailable, diagnosis`。

### K8s Capacity Planner

负责 Node/Pod CPU、内存、IP、Pod 数量、requests/limits 和 HPA 分析，首阶段只读。

工具范围：

- 集群、namespace、Node 和 Pod 列表。
- Node/Pod top。
- Node 资源、IP 和 Pod 数量。
- Pod 资源使用。
- Deployment HPA。
- 通用资源列表和详情。

输出必须区分当前快照与历史趋势，并包含热点、容量风险、资源浪费、HPA 覆盖和扩容建议。

Skill 为 `cluster.capacity_plan`，Tags 为 `kubernetes, capacity, cpu, memory, hpa, scheduling`。

### K8s GPU Specialist

负责 vLLM、Metax 和 MThreads GPU 工作负载生成、部署与诊断。

只读能力：

- 三种 GPU/大模型 YAML 模板。
- 集群、namespace、Node、Pod 和通用资源查询。
- Pod describe、Events、日志和资源使用。

审批能力：

- `apply_k8s_yaml`
- `patch_k8s_resource`
- `delete_k8s_resource`
- `restart_k8s_deployment`
- `scale_k8s_deployment`

固定工作流：

```text
确认 GPU 类型、模型、镜像和资源需求 -> 获取模板
-> 检查节点和调度条件 -> 生成完整 YAML -> 请求审批
-> 部署 -> 检查 Pod、Service 和日志
```

Skill 为 `gpu.workload_manage`，Tags 为 `kubernetes, gpu, vllm, metax, mthreads, inference`。

## 路由优先级

数字越小越优先：

| Agent | Priority |
| --- | ---: |
| Incident Responder | 10 |
| Capacity Planner | 12 |
| GPU Specialist | 15 |
| Ops | 20 |
| Security | 30 |
| Infrastructure | 35 |
| Helm | 38 |
| Orchestrator | 40 |

场景明确时优先使用场景 Agent；通用查询和通用变更分别回退到基础 Agent。

## ToolPolicy 调整

当前 `DEFAULT_GLOBAL_DENY` 使 drain、集群注册、Helm 卸载和 Pod exec/file 工具无法归属于任何 Agent。本阶段移除这些工具的永久全局禁止，改为由 Agent 的 `approval_required` 精确开放。

策略顺序保持：Agent deny、Agent approval、Agent allow、默认拒绝。所有写操作至少需要审批，不允许直接 allow。

## 部署和注册

- 新增五套 Agent 目录，每套包含 `main.py`、`agent.yaml`、`prompt.md`、`Dockerfile`、`requirements.txt` 和 `.env.example`。
- 新端口使用 8054 至 8058。
- Compose 新增五个可选 Agent 服务，但 Backend 不对任何具体 Agent 配置 `depends_on`。
- Backend 在没有 Agent 的情况下独立启动并保持健康。
- `BOOTSTRAP_AGENTS` 是可选的本地开发便利配置，可以包含八个本地 Agent，也可以为空；它不是 Backend 的运行依赖。
- Bootstrap 地址不可达时只产生离线状态或诊断记录，不能阻止 Backend 启动。
- 运行期间可以通过标准注册 API 或前端添加任意外部 A2A Server，无需重启 Backend。
- Agent 注册信息、能力和健康状态来自远端 Agent Card，不在 Backend 代码中写死。
- Host 只按 Registry 中当前可用且能力匹配的 Agent 制定委派计划；无可用能力时返回直接说明或澄清，不得崩溃。
- 所有 Agent 默认使用 `K8S_MCP_URL=http://10.2.0.57:9096/mcp` 与 `MCP_TRANSPORT=streamable_http`。

## 错误处理

- 缺少 cluster、namespace 或资源标识时追问，不猜测。
- MCP 不可用时 readiness 为 `degraded`，请求到来时重新初始化。
- 工具超时后断开；传输错误只重连并重试一次。
- 工具预算耗尽后基于已有证据总结。
- 审批绑定 Agent、工具名和完整参数；恢复后只执行原参数。
- 场景 Agent 输出已验证、未验证、证据、结论和建议。

## 测试

### 工具覆盖

维护 MCP 66 工具的固定契约清单，验证每个工具至少在一个 Agent 中为 allow 或 approval，且配置中不存在 Server 未提供的精确工具名。

### 策略测试

- 覆盖八个 Agent 的代表性 allow、approval 和 deny。
- 验证写工具不能直接 allow。
- 验证未配置工具默认拒绝。

### Agent Card 与路由

- 验证八个稳定 ID、端口、Skills、Tags、优先级和风险等级。
- 验证 Incident、Capacity、GPU、Helm、节点维护和通用变更的路由提示与能力资料互不冲突。
- 验证外部非 Kubernetes A2A Agent 能通过 Agent Card 进入 Registry 并参与能力路由。

### 部署与回归

- Compose 能正常展开并包含八个本地 Agent，但 Backend 不依赖这些服务的启动顺序或健康状态。
- 零 Agent 时 Backend 正常启动和响应 API。
- 所有 Bootstrap 地址离线时 Backend 仍正常启动。
- 只启动部分 Agent 时 Host 只使用可用能力。
- 动态注册或移除外部 A2A Server 不要求重启 Backend。
- 所有 Agent 使用 Streamable HTTP 配置。
- Runtime 和 Backend 测试通过。
- Frontend 测试与生产构建通过。
- Python 编译和 diff 格式检查通过。

## MCP Server 后续改进

MCP Server 源码不在当前工作区，本阶段不直接修改远端服务。后续独立实施：

- 为 42 个缺少 required 的工具修正输入 Schema。
- 将只读工具错误的 `destructiveHint=True` 修正为 false。
- 增加 YAML dry-run、资源 diff、namespace 健康摘要、Pod 综合诊断、RBAC 扫描、workload 安全扫描、NetworkPolicy 覆盖分析和 Deployment 发布摘要。

## 非目标

- 本阶段不实现 Release Manager、Network Troubleshooter 和 Storage Troubleshooter。
- 不允许 Agent 互相调用。
- 不让 Host 直接调用 MCP。
- 不修改远端 MCP Server。
