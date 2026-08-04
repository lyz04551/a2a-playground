┌─────────────────────────────────────────────────────────┐
│  第1层：用户/客户端层                                      │
│  HTTP/OpenAI API / CLI / Python SDK / gRPC / WebSocket   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP请求 / API调用
┌──────────────────────▼──────────────────────────────────┐
│  第2层：服务入口层 (Entrypoints)                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ InputProcessor(分词+多模态) → Detokenizer → OutputProcessor │
│  │ ToolParserManager(工具调用) / ReasoningParser(CoT)│   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │ EngineCoreRequest (msgspec序列化)
┌──────────────────────▼──────────────────────────────────┐
│  第3层：V1引擎层 (Engine)                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Frontend进程:  AsyncLLM → EngineCoreClient(IPC)  │   │
│  │ Core子进程:    EngineCore → Scheduler → Executor │   │
│  │                KVCacheManager → BlockPool         │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │ SchedulerOutput (调度决策)
┌──────────────────────▼──────────────────────────────────┐
│  第4层：执行器+Worker层                                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Executor(UniProc/Multiproc/Ray/ExternalLauncher) │   │
│  │ Worker(GPU/CPU/XPU) → ModelRunner(GPU/CPU)       │   │
│  │ GPUModelRunner._prepare_inputs() → forward()     │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │ model.forward()
┌──────────────────────▼──────────────────────────────────┐
│  第5层：模型执行层 (Model Executor)                       │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Models: 296种(LLaMA/Mixtral/DeepSeek/Qwen/...)   │   │
│  │ Layers: Attention/FusedMoE/Quantization/RoPE/Lin │   │
│  │ Weight Loader: AutoWeightsLoader/WeightsMapper   │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │ CUDA ops / torch.ops.vllm.*
┌──────────────────────▼──────────────────────────────────┐
│  第6层：内核+分布式层                                     │
│  ┌──────────────────┐  ┌───────────────────────────┐   │
│  │ C++/CUDA Kernels │  │ Distributed               │   │
│  │ PagedAttention   │  │ parallel_state(5维并行)    │   │
│  │ QuantKernels     │  │ kv_transfer(11种Connector)│   │
│  │ MoE/Sampler/...  │  │ device_communicators(NCCL)│   │
│  └──────────────────┘  └───────────────────────────┘   │
└─────────────────────────────────────────────────────────┘

         ←──── 横切关注点 ────→
┌─────────────────────────────────────────────────────────┐
│  VllmConfig(22子配置) | Platforms(6平台) | Compilation   │
│  Tokenizers | ToolParsers(40种) | LoRA | MultiModal     │
│  IR(ir.ops注册) | Tracing | Profiler | Plugins          │
└─────────────────────────────────────────────────────────┘
