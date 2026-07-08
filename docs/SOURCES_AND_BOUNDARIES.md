# Sources and Boundaries

本文档记录 AK-Infer-Lab DeepSeek-V4-Flash 专项的事实来源、项目内证据和边界。外部事实最后校验时间：2026-07-08。

## 1. 外部事实来源

| 来源 | 用途 | 当前采用的事实 |
| --- | --- | --- |
| [DeepSeek-V4-Flash Hugging Face model card](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash) | 模型规格 | 284B total parameters、13B activated parameters、1M context、FP4+FP8 Mixed；MoE expert parameters 使用 FP4，多数其他参数使用 FP8。 |
| [vLLM-Ascend DeepSeek-V4-Flash tutorial v0.18.0](https://docs.vllm.ai/projects/ascend/en/v0.18.0/tutorials/models/DeepSeek-V4-Flash.html) | Ascend 官方部署基线 | `DeepSeek-V4-Flash-w8a8-mtp`，1 台 Atlas 800 A2 64GB×8 或 Atlas 800 A3 128GB×8；部署命令包含 TP、EP、`--quantization ascend`、prefix cache、chunked prefill、MTP speculative config 等要素。 |
| [vLLM-Ascend KV Cache CPU Offload guide](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html) | DRAM warm tier 候选 | inactive KV blocks 从 NPU memory offload 到 CPU memory；基于 `OffloadingConnector` 和 `NPUOffloadingSpec`；D2H/H2D 使用独立 NPU streams。 |
| [vLLM-Ascend UCM Store guide](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html) | external KV / prefix cache 候选 | UCM 面向 prefix cache 的外部 KV storage layer，采用 HBM → DRAM → SSD/NFS/3FS hierarchy，并支持 vLLM/vLLM-Ascend 与 CANN/Atlas A2/A3 平台。 |
| [vLLM-Ascend KV Cache Pool guide](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_pool.html) | Mooncake/KV pool 候选 | AscendStoreConnector / MooncakeBackend、embedded client、SSD offload、SSD quota、per-rank buffer 和 eviction policy 等部署约束。 |
| [Mooncake documentation](https://kvcache-ai.github.io/Mooncake/) | KV store 生态参考 | Mooncake 是面向 LLM inference 的分布式 KV cache/storage 体系，可作为 vLLM-Ascend KV pool、PD 和 storage-backed cache 的机制参考。 |

## 2. 项目内部来源

- 硬件规格材料：n+1 分级内存与 n+2 HMM/PIM 路线。
- 小算力系统论证关键问题：显存放不下、CPU/NPU 交互、KV Cache、Agent Swarm、Prefix Cache 收益等问题。
- 一体机汇报：Mini / 塔式工作站场景、84GB Bailu、DDR5、SSD、UB、NPU-SSD 直通等设计目标。
- Deep Research 第三轮可核验报告：vLLM-Ascend、UCM、KV Pool、MoE expert、KV state、simulator 和 P0/P1/P2/P3 路线。
- 代表工作硬件拓扑映射：NEO、Tutti、Mooncake、Bidaw、SolidAttention、KTransformers、LMCache、ProfInfer、LLMServingSim2.0 等工作如何映射到硬件链路。
- Ascend 服务器环境汇总：当前 Atlas 800T A2 / 8×910B1 / 64GB HBM / CANN 9.0.0 / vLLM-Ascend 环境边界。

## 3. 不确定性与边界

- DeepSeek-V4-Flash 的非官方量化版本很多，但本项目八卡基准只以官方 Ascend W8A8-MTP 路线为 reference。
- vLLM-Ascend `main` 文档和 stable `v0.18.0` 文档可能存在差异；正式服务器任务必须在 handoff 中固定版本、镜像、commit 或文档 URL。
- 官方教程列出 Atlas 800 A2/A3；本项目服务器是 Atlas 800T A2，必须用服务器 smoke 证明实际兼容性。
- 单卡/双卡极限实验不等同于官方模型可部署。
- KV CPU Offload、UCM、Mooncake、LMCache 的思想可以迁移，但具体收益必须由本机 trace 证明。
- KTransformers 等 x86/AMX/CUDA 工作不能直接外推到 Kunpeng/Ascend；只能作为机制参考。
- SSD cold tier 的账面容量不等于 decode 热路径可用；必须证明 I/O 粒度、异步和预取能隐藏。
- P/D 分离不是默认正收益；小算力单机优先做逻辑队列和状态对象，不先做完整物理拆分。
- 任何性能数字必须明确来自 smoke、controlled benchmark、profile readout、request-device aggregate 还是 simulator；不同证明力不能混用。
