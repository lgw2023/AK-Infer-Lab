# Sources and Boundaries

本文档记录 AK-Infer-Lab DeepSeek-V4-Flash 专项的事实来源、项目内证据和边界。DeepSeek 模型与 vLLM-Ascend v0.18.0 部署事实于 2026-07-08 校验，并在 P5 首轮中形成不兼容的历史证据；2026-07-10 服务器已构建 `vLLM 0.20.2 / vLLM-Ascend 0.20.2rc1 / CANN 9.0.0 / PyTorch 2.10.0 / torch-npu 2.10.0 / triton-ascend 3.2.1` 隔离栈，并以 Qwen2.5-3B-Instruct 完成纯注意力端到端 smoke。该结果证明通用 Ascend/vLLM 链路，不证明 DeepSeek DSA/MTP/TP8/EP/W8A8 路径。

术语与字段命名优先级为：`AK 协同/` 内的官方文档 / 框架资料 / benchmark 输出字段 > 本地系统论文中的通用表达 > 项目内中文解释。项目内可使用“状态底座”或“热/温/冷层”帮助阅读，但首次出现时必须对齐 External KV Cache / state-object management 以及 HBM / DRAM / SSD-NVMe tier 等可检索术语，并注明来源类型和适用边界。若 `AK 协同/` 内找不到对应来源，只能标记为“项目内解释”或“待来源对齐”，不能包装成领域标准名词。

## 0.1 术语来源映射

`AK 协同/references/bibliography_inference_sim.md` 是术语来源路由索引；以下路径均相对于 `AK 协同/`。

| 标准术语 | 来源类型 | 本地来源锚点 | 适用边界 |
| --- | --- | --- | --- |
| TTFT / ITL；Prefill/Decode disaggregation | 官方框架文档快照 | `references/web/vLLM-disaggregated-prefill.html` | 证明 vLLM 使用这些阶段和指标名称；本项目 host-client 计算口径仍以采集脚本为准，不等于 device event |
| TPOT / E2EL / throughput | benchmark / 框架指标命名与本项目输出字段 | `Deep Research 反向回顾报告 第三轮可核验版 小算力大模型推理落地与推理仿真系统构建.md`、MindIE/vLLM 资料快照 | 证明字段属于推理服务指标体系；P1.29/P1.31 的具体公式和数值只适用于当前 vLLM streaming client |
| H2D / D2H | 官方框架 release-note 与数据路径用语 | `references/web/vLLM-Ascend-release-notes-v0.18.html`、`references/web/vLLM-Ascend-KV-CPU-offload-live.html` | 只定义 Host↔Device 方向和相关路径，不定义本机 PCIe/UB 理论峰值，也不代表 NPU-NPU 通信 |
| KV Cache CPU Offload / UCM Store | vLLM-Ascend 官方文档快照 | `references/web/vLLM-Ascend-KV-CPU-offload-live.html`、`references/web/vLLM-Ascend-UCM-deployment-live.html` | 证明 inactive KV block 下沉、CPU↔NPU restore 与分层 store 机制存在；不证明本机净收益 |
| External KV Cache / tiered KV cache offloading | 框架文档与系统论文 | `references/web/LMCache-docs.html`、`references/papers/LMCache__arxiv-2510.09665.pdf`、`references/papers/Mooncake__arxiv-2407.00079.pdf` | 用于外部化、复用和多级存储机制；不是当前项目已完成的 object bytes / hit-miss 闭环 |
| Expert Parallelism Load Balancer (EPLB) / expert hotness / expert map | vLLM-Ascend 官方文档与 release-note 快照 | `references/web/vLLM-Ascend-docs.html`、`references/web/vLLM-Ascend-release-notes-live.html` | 证明 Ascend runtime 有专家热度、复制和放置入口；EPLB 不等于 Expert Offload / Expert Cache，也不证明当前服务器 0.18.0 已暴露最新配置 |
| MoE Expert Offload / Expert Cache | 系统论文 | `references/papers/KTransformers.pdf`、`references/papers/fMoE-FineMoE__arxiv-2502.05370.pdf`、`references/papers/DALI__arxiv-2602.03495.pdf`、`references/papers/FluxMoE__arxiv-2604.02715v2.pdf` | 作为 expert placement/offload/cache 机制参考；x86/CUDA 结果不能直接外推到 Kunpeng/Ascend |
| MindIE Prefix Cache / KV Cache 池化 / 冗余专家部署 | MindIE 官方产品索引与 2.3 live official 页面 | `references/web/MindIE-docs.html`；具体特性页待本地快照对齐 | 只登记 MindIE 候选能力；当前服务器 `mindie_version=unknown` 且 package inventory 为 missing，不得写成可执行路径或本机收益 |
| HCCL collective；all-reduce / all-gather / reduce-scatter / all-to-all | vLLM-Ascend 官方资料与 collective benchmark 论文 | `references/web/vLLM-Ascend-release-notes-main.html`、`references/web/vLLM-Ascend-KV-pool-live.html`、`references/papers/CCL-Bench__arxiv-2605.06544.pdf` | 证明 HCCL 和 collective 模式属于相关系统/benchmark 认知体系；当前没有本机八卡 sweep |
| algbw / busbw | 待选 collective benchmark 的输出字段 | 当前 `AK 协同/` 无独立权威定义页；执行实验时必须随工具版本和原始字段一并登记 | 仅作计划字段，不得写成 HCCL 官方字段或本机已测“卡间带宽” |

## 1. 外部事实来源

| 来源 | 用途 | 当前采用的事实 |
| --- | --- | --- |
| [DeepSeek-V4-Flash Hugging Face model card](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash) | 模型规格 | 284B total parameters、13B activated parameters、1M context、FP4+FP8 Mixed；MoE expert parameters 使用 FP4，多数其他参数使用 FP8。 |
| [vLLM-Ascend DeepSeek-V4-Flash tutorial v0.18.0](https://docs.vllm.ai/projects/ascend/en/v0.18.0/tutorials/models/DeepSeek-V4-Flash.html) | Ascend 官方部署基线 | `DeepSeek-V4-Flash-w8a8-mtp`，1 台 Atlas 800 A2 64GB×8 或 Atlas 800 A3 128GB×8；部署命令包含 TP、EP、`--quantization ascend`、prefix cache、chunked prefill、MTP speculative config 等要素。 |
| [vLLM tag v0.20.2](https://github.com/vllm-project/vllm/tree/v0.20.2) | 目标开发基线 | 官方 tag commit `bc150f50299199599673614f80d12a196f377655`；已取回到本地滚动 `vllm/` shallow checkout。 |
| [vLLM-Ascend tag v0.20.2rc1](https://github.com/vllm-project/vllm-ascend/tree/v0.20.2rc1) | Ascend 目标开发基线 | 官方 tag commit `367b8e62da799870a7476ce34f5f7658589a8aad`；已取回到本地滚动 `vllm-ascend/` shallow checkout，服务器已验证同版本隔离环境的 Qwen 纯注意力链路，但 DeepSeek-V4 八卡路径仍待 P5。 |
| [vLLM-Ascend KV Cache CPU Offload guide](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html) | DRAM warm tier 候选 | inactive KV blocks 从 NPU memory offload 到 CPU memory；基于 `OffloadingConnector` 和 `NPUOffloadingSpec`；D2H/H2D 使用独立 NPU streams。 |
| [vLLM-Ascend UCM Store guide](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html) | external KV / prefix cache 候选 | UCM 面向 prefix cache 的外部 KV storage layer，采用 HBM → DRAM → SSD/NFS/3FS hierarchy，并支持 vLLM/vLLM-Ascend 与 CANN/Atlas A2/A3 平台。 |
| [vLLM-Ascend KV Cache Pool guide](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_pool.html) | Mooncake/KV pool 候选 | AscendStoreConnector / MooncakeBackend、embedded client、SSD offload、SSD quota、per-rank buffer 和 eviction policy 等部署约束。 |
| [vLLM-Ascend EPLB guide](https://docs.vllm.ai/projects/ascend/en/latest/user_guide/feature_guide/eplb_swift_balancer.html) | expert hotness / placement 候选 | 最新文档包含 recording、static map、redundant expert 和 placement 配置；执行前必须在服务器目标 0.20.2rc1 运行时做 capability probe，且不能解释为 expert offload。 |
| [MindIE 2.3 Prefix Cache](https://www.hiascend.com/document/detail/zh/mindie/230/mindiellm/llmdev/mindie_llm0302.html) | MindIE 对照候选 | 官方页面记录跨 session prefix reuse 与支持/组合约束；当前服务器尚无 MindIE 可用性证据。 |
| [MindIE 2.3 KV Cache 池化](https://www.hiascend.com/document/detail/zh/mindie/230/mindiellm/llmdev/mindie_llm0538.html) | MindIE DRAM pool 对照候选 | 官方页面说明当前该版本仅支持 DRAM 池化；不证明本项目 server/model 组合可运行。 |
| [MindIE 2.3 冗余专家部署表](https://www.hiascend.com/document/detail/zh/mindie/230/mindiellm/llmdev/mindie_llm0431.html) | expert hotness / static placement 对照候选 | 官方页面记录热点采集和冗余专家部署表生成；不等于动态 warm/cold expert offload。 |
| [Mooncake documentation](https://kvcache-ai.github.io/Mooncake/) | KV store 生态参考 | Mooncake 是面向 LLM inference 的分布式 KV cache/storage 体系，可作为 vLLM-Ascend KV pool、PD 和 storage-backed cache 的机制参考。 |

## 2. 项目内部来源

- `AK 协同/` 硬件规格材料：n+1 分级内存与 n+2 HMM/PIM 路线。
- 小算力系统论证关键问题：显存放不下、CPU/NPU 交互、KV Cache、Agent Swarm、Prefix Cache 收益等问题。
- 一体机汇报：Mini / 塔式工作站场景、84GB Bailu、DDR5、SSD、UB、NPU-SSD 直通等设计目标。
- Deep Research 第三轮可核验报告：vLLM-Ascend、UCM、KV Pool、MoE expert、KV state、simulator 和 P0/P1/P2/P3 路线。
- 代表工作硬件拓扑映射：NEO、Tutti、Mooncake、Bidaw、SolidAttention、KTransformers、LMCache、ProfInfer、LLMServingSim2.0 等工作如何映射到硬件链路。
- Ascend 服务器环境汇总：当前 Atlas 800T A2 / 8×910B1 / 64GB HBM / CANN 9.0.0 / vLLM-Ascend 环境边界。

这些项目材料可以组织证据和提出实验假设，但其中的中文概括不自动成为领域标准术语。页面引用时应回到上表的论文、官方文档、框架或 benchmark 来源锚点。

## 2.1 本地待测模型对象

| 对象 | 本地路径 | 当前状态 | 用途 | 边界 |
| --- | --- | --- | --- | --- |
| `DeepSeek-V4-Flash-w8a8-mtp` | `/Volumes/Elements/DeepSeek-V4-Flash-w8a8-mtp` | 本地已下载；服务器盘点 70 连续分片 / `300,013,759,966 B ≈ 279.41 GiB` | P6 单机八卡 baseline 首选对象；优先匹配 vLLM-Ascend `--quantization ascend` reference | 服务器分片事实不等于 runtime load；静态权重超过四卡约 256GiB HBM，本轮四卡不启动 |
| `deepseek-ai/DeepSeek-V4-Flash` | `/Volumes/Elements/DeepSeek-V4-Flash` | 本地 metadata 已观测；服务器盘点 46 连续分片 / `159,617,149,040 B ≈ 148.66 GiB` | 官方来源、版本对照，以及当前 NPU 4-7 FP8/FP4 格式兼容性探针 | checkpoint config 的 `fp8` + expert `fp4` 不等同于 Ascend ModelSlim 格式；四卡实跑前不得写成 runtime ready |

用户会自行把模型目录拷贝到 Ascend 服务器。本仓库只登记对象、来源、实验用途和边界，不复制模型 payload，不推断服务器路径。

## 3. 不确定性与边界

- DeepSeek-V4-Flash 的来源和量化形态必须分开登记：P6 八卡基准首选 ModelScope `DeepSeek-V4-Flash-w8a8-mtp`；`deepseek-ai/DeepSeek-V4-Flash` 当前只承担四卡 FP8/FP4 格式/运行时诊断，不因体积较小而升级为 canonical runtime object。
- vLLM/vLLM-Ascend `main` 只用于跟踪最新代码；当前一方开发起点分别是 `v0.20.2@bc150f5` 和 `v0.20.2rc1@367b8e6`。正式服务器任务必须在 handoff 中固定版本、镜像、commit 或文档 URL，不能照抄 `main` 参数。
- 官方教程列出 Atlas 800 A2/A3；本项目服务器是 Atlas 800T A2，必须用服务器 smoke 证明实际兼容性。
- 单卡/双卡极限实验不等同于官方模型可部署。
- KV CPU Offload、UCM、Mooncake、LMCache 的思想可以迁移，但具体收益必须由本机 trace 证明。
- KTransformers 等 x86/AMX/CUDA 工作不能直接外推到 Kunpeng/Ascend；只能作为机制参考。
- SSD cold tier 的账面容量不等于 decode 热路径可用；必须证明 I/O 粒度、异步和预取能隐藏。
- P/D 分离不是默认正收益；小算力单机优先做逻辑队列和状态对象，不先做完整物理拆分。
- 任何性能数字必须明确来自 smoke、controlled benchmark、profile readout、request-device aggregate 还是 simulator；不同证明力不能混用。
- H2D/D2H 表示 Host↔Device copy，不表示 NPU-NPU interconnect。当前项目尚无单机八卡 pairwise P2P 或 HCCL all-reduce / all-gather / reduce-scatter / all-to-all 的 algbw / busbw 实测结论。
- `non_blocking=True` 后立即 synchronize 的数据只能解释为同步完成计时下的 API 参数对比，不是 host async issue 或 copy-compute overlap 证据。
- `ITL` 在 P1.29/P1.31 中是 host streaming inter-chunk median per request；`TPOT` 是 `(response_end - first_token) / (generated_tokens - 1)`。两者都不是 runtime native decode event。
- NumPy `source.sum()` / `np.copyto()` 数据是 Python/NumPy 软件路径的 observed CPU memory path ceiling，不是 server DRAM hardware peak。
