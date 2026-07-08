根据 2026-07-02 的项目《融合方案》和 2026-07-06 的服务器环境材料，你们现在最应该采用的是 **“MindIE 做稳定基线 + vLLM-Ascend 做可改造研究原型 + UCM/Mooncake/LMCache 做 KV/Prefix 状态层 + 自研 ExpertObject/Trace/Simulator 层”**。项目材料里已经把这条路线收敛为双轨：MindIE 用来测官方高性能基线，vLLM-Ascend 用来改 KV connector、UCM/external KV、metrics hooks、expert trace、copy/stall trace；KV/Prefix 外部状态参考 UCM/Mooncake/LMCache，MoE 专家分层参考 KTransformers/FineMoE/DALI/FluxMoE/MoE-APEX，SSD cold tier 只参考 Tutti/SolidAttention/Bidaw，不放进 P0 热路径。

你们当前机器条件也比较适合这条路线：服务器是 Ubuntu 22.04/aarch64、Kunpeng-920、8×Ascend 910B1、每卡 64GB HBM、约 1.5TiB 主存、多个 7TB 级 NVMe，项目已确认 CANN 9.0.0、`msprof`、`fio`、`numactl` 可用；但 eBPF/bpftrace 权限受阻，所以 ProfInfer 式 eBPF 观测不能直接作为 P0 前提，需要先用 CANN/msprof + 自研 trace 兜住。

## 1. 先用这些作为 P0 工程底座

| 组件                      | 类型                          | 当前可用性                         | 你们应该怎么用                                               |
| ------------------------- | ----------------------------- | ---------------------------------- | ------------------------------------------------------------ |
| **vLLM-Ascend**           | 开源框架 / Ascend 后端插件    | 优先级最高                         | 作为主研究原型；改 KV offload、UCM、KV Pool、trace hooks、expert trace。vLLM-Ascend 官方说明它是 vLLM 社区维护的 Ascend NPU 插件；Quickstart 要求 Linux、Python 3.10–3.12、Atlas A2 类硬件、CANN 9.0.0、torch-npu 2.10.0，与你们现有 CANN 9.0.0 环境基本吻合。([GitHub](https://github.com/vllm-project/vllm-ascend?utm_source=chatgpt.com)) |
| **MindIE / MindIE Turbo** | 官方 Ascend 推理栈 / 加速插件 | 做基线，不建议 P0 深改             | 用来跑官方高性能 baseline，测 W8A8、TP/EP/DP/CP、TTFT、TPOT、显存占用。MindIE 官方定位是 Ascend 高性能推理引擎，MindIE Turbo 是 LLM 推理引擎加速插件库，有模块化插件接口。([昇腾社区](https://www.hiascend.com/en/developer/inference?utm_source=chatgpt.com)) |
| **vLLM mainline**         | 开源推理框架                  | 作为上游参考                       | 用于理解 PagedAttention、continuous batching、prefix cache、P/D disaggregation 的标准接口。vLLM 本身是高吞吐、内存高效的 LLM inference/serving 框架，PagedAttention 论文说明它把 KV cache 管理做成近似虚拟内存/分页结构。([GitHub](https://github.com/vllm-project/vllm?utm_source=chatgpt.com)) |
| **SGLang / HiCache**      | 开源 serving 框架 + 分层 KV   | 作为对照/备选，不是 Ascend P0 主线 | 适合学习 hierarchical KV cache、RadixAttention、Mooncake backend 集成。SGLang HiCache 明确是 GPU memory、host memory、external storage 的三层 KV caching 系统，但 Ascend 首发工程仍建议放在 vLLM-Ascend。([GitHub](https://github.com/sgl-project/sglang/blob/main/docs/advanced_features/hicache_best_practices.md?utm_source=chatgpt.com)) |

**工程判断：**P0 不要从自研推理引擎开始。先把 `vLLM-Ascend + KV CPU Offload + UCM + trace` 跑起来，再决定要不要把某些机制挖出来自研。

## 2. KV / Prefix / Context 分层：最直接可用的开源组件

### 2.1 vLLM-Ascend KV Cache CPU Offload

这是你们现在最值得马上动手的功能。官方文档写得很清楚：它把 inactive KV cache blocks 从 NPU memory offload 到 CPU memory；CPU 中命中后可以异步 H2D 拉回 NPU，减少重算；实现基于 vLLM `OffloadingConnector`，Ascend 特化实现是 `NPUOffloadingSpec`，并用独立 NPU streams 做 D2H/H2D。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html))

关键能力：

```text
NPU HBM active KV
  ↓ D2H async
CPU DRAM KV block pool
  ↓ H2D async on prefix hit / restore
NPU HBM
```

官方配置里已经有你们需要的几个 P0 控制点：`num_cpu_blocks`、`block_size`、`NPUOffloadingSpec`、`vllm_ascend.kv_offload.npu`，并且 CPU block pool 使用 LRU；还支持 KV cache events，用于 monitoring/debug。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_cache_cpu_offload.html))

**你们要做的不是重写它，而是包一层实验采集：**

```text
num_cpu_blocks
block_size
pinned / non-pinned CPU pool
D2H bytes
H2D bytes
D2H/H2D latency
copy overlap
KV hit/miss
TTFT/TPOT/P95/P99
host OOM
```

### 2.2 UCM Store

UCM 是第二个 P0/P1 组件。它明确提供 external KV-cache storage layer，目标是 prefix caching；架构是三层：

```text
HBM / device memory
  → DRAM local cache
  → Storage backend: SSD / NFS / 3FS
```

官方文档直接写明 UCM 打破 HBM/DRAM 容量限制，提供持久 KV cache，并支持 prefix cache、training-free sparse attention、PD disaggregation 等能力。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html))

更重要的是，UCM 文档明确列出 **CANN / Atlas A2 / Atlas A3** 为支持平台，支持框架包括 vLLM、vLLM-Ascend、SGLang。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html))

**你们用 UCM 的正确方式：**

```text
P0: DRAM local cache only
P1: DRAM + local SSD / NFS mock
P2: 共享 storage backend / 3FS / Mooncake
```

不要一上来把 SSD 放进逐 token decode 热路径。UCM 是 prefix/KV 状态层，不是“单 token 冷 KV 随机回取加速器”。

### 2.3 Mooncake

Mooncake 是 KVCache-centric disaggregated serving 的代表系统，也是 vLLM-Ascend KV Pool 的可用 backend。Mooncake 官方说明它分离 prefill/decode，并利用 CPU、DRAM、SSD 资源构建 disaggregated KV cache pool；Mooncake Transfer Engine 和 Mooncake Store 已开源。([KVCACHE AI](https://kvcache-ai.github.io/Mooncake/?utm_source=chatgpt.com))

vLLM-Ascend KV Pool 文档直接给了 Mooncake backend 部署指南，要求 `vLLM main branch`、`vLLM-Ascend main branch`、`mooncake >= 0.3.9`，并给出 `MooncakeConnectorV1 + AscendStoreConnector` 的配置。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_pool.html))

**你们的用法：**

| 阶段 | 用法                                                         |
| ---- | ------------------------------------------------------------ |
| P0   | 不开 Mooncake，只做 KV CPU Offload/UCM DRAM                  |
| P1   | 单机/双实例 KV Pool，验证 producer/consumer、KV hit、load failure |
| P2   | PD/KV Pool + SSD offload，测 Mooncake control overhead、HCCL/HCCS/UB、Fabric Mem、host memory budget |
| P3   | 作为 NPU-native storage/direct path 的对照组                 |

### 2.4 LMCache

LMCache 是另一个必须看的开源组件。官方 GitHub 说明它是 LLM inference 的 KV cache management layer，把 KV cache 从临时状态变成可持久化、可跨 serving engine 复用、可监控、可变换的对象；它支持 CPU RAM、local disk/SSD、Redis/Valkey、Mooncake、S3-compatible object storage 等 backend。([GitHub](https://github.com/lmcache/lmcache?utm_source=chatgpt.com))

vLLM 官方也有 LMCache examples，用于 KV cache offloading、disaggregated prefilling、KV cache sharing。([vLLM](https://docs.vllm.ai/en/latest/examples/disaggregated/lmcache/?utm_source=chatgpt.com))

**你们不一定要直接把 LMCache 跑在 Ascend 上，但要抄它的对象接口思想：**

```text
KVObject:
  object_id
  model_id
  layer_id
  block_id
  token_range
  dtype
  bytes
  tier: HBM / DRAM / SSD / remote
  state: resident / loading / evicted / invalid
  last_access_ts
  hit_count
  restore_cost
  recompute_cost
```

这正好对齐你们方案里要做的 `kv_object / prefix_object / expert_object / weight_shard_object / tier_manager`。项目方案已经建议按这个结构建仓库。

## 3. MoE 专家热温冷分层：能借鉴，但 Ascend 上要自研适配

这里要区分 **“可直接运行的代码仓”** 和 **“可迁移机制”**。

| 方向                                   | 代表代码/论文                         | 当前状态                                                   | 对 A+K 的用法                                                |
| -------------------------------------- | ------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------ |
| **KTransformers**                      | `kvcache-ai/ktransformers`，SOSP 2025 | 有开源代码和文档；面向 CPU-GPU heterogeneous MoE           | 强烈建议读代码和机制，但不能直接当 Kunpeng+Ascend 实现。它依赖 AMX/AVX/NUMA/CUDA Graph/FlashInfer 等 x86+CUDA 栈；迁移到 Kunpeng 必须先做 SVE/SME/OMP microbench。([GitHub](https://github.com/kvcache-ai/ktransformers?utm_source=chatgpt.com)) |
| **SGLang + KTransformers integration** | SGLang 官方博客/issue                 | 对 GPU TP + CPU/GPU hybrid expert parallelism 有工程化趋势 | 学它的 runtime 集成边界：GPU/NPU 保 hot path，CPU 承接 expert compute/offload。但 Ascend P0 不建议直接走 SGLang。([LMSYS Org](https://www.lmsys.org/blog/2025-10-22-KTransformers/?utm_source=chatgpt.com)) |
| **FineMoE**                            | `IntelliSys-Lab/FineMoE-EuroSys26`    | 有 GitHub repo；EuroSys 2026/ACM                           | 用来做 expert map、semantic hint、expert prefetch/cache/offload 策略原型。([GitHub](https://github.com/IntelliSys-Lab/FineMoE-EuroSys26?utm_source=chatgpt.com)) |
| **DALI**                               | arXiv 2026                            | 论文机制强，代码仓未稳定确认                               | 适合做 workload-aware assignment、residual-based prefetch、workload-aware cache replacement 的算法参考。([arXiv](https://arxiv.org/abs/2602.03495?utm_source=chatgpt.com)) |
| **FluxMoE**                            | arXiv 2026                            | 论文写明实现 atop vLLM，但是否完整开源需复核               | 适合借鉴 expert paging，把 expert weights 从常驻模型参数变成 transient streamed resource。([arXiv](https://arxiv.org/html/2604.02715v2?utm_source=chatgpt.com)) |
| **MoE-Lightning**                      | ASPLOS 2025                           | 论文成熟，偏 batch/offline                                 | 借鉴 CPU-GPU-I/O pipeline、paged weights、Hierarchical Roofline Model；不适合作为交互式 Agent P0。([ACM Digital Library](https://dl.acm.org/doi/10.1145/3669940.3707267?utm_source=chatgpt.com)) |
| **Fiddler**                            | `efeslab/fiddler`                     | PoC，local MoE CPU-GPU orchestration                       | 可做小规模读代码，不应作为生产底座。([GitHub](https://github.com/efeslab/fiddler?utm_source=chatgpt.com)) |
| **vLLM MoE offload RFC/PR**            | vLLM issues                           | 仍是 RFC/PR 形态                                           | 值得跟踪，因为它和 vLLM-Ascend 未来接口更可能对齐。当前只能作为接口设计参考。([GitHub](https://github.com/vllm-project/vllm/issues/38256?utm_source=chatgpt.com)) |

项目内部材料也强调了边界：KTransformers 不是“把 MoE 权重放 CPU”这么简单，而是 shared/hot experts 在 GPU/NPU、routed experts 在 CPU，并结合 AMX/AVX/NUMA/异步调度/Expert Deferral；迁移到 Kunpeng 必须重测 SVE/SME。

**建议你们 P1 先做 ExpertTrace，不要先做 ExpertOffload：**

```text
ExpertTrace:
  request_id
  layer_id
  token_id
  topk_expert_ids
  expert_scores
  expert_tier: HBM / DRAM / SSD / missing
  expert_hit
  expert_load_bytes
  expert_load_latency
  prefetch_lead_time
  wrong_prefetch_bytes
  stall_ms
```

然后再做三个 policy：

```text
V0: static hot experts pinned in HBM
V1: sliding-window top-k expert prefetch
V2: session/prompt/layer-aware hotness predictor
```

## 4. SSD cold tier：有好论文，但不应作为 P0 热路径

| 工作               | 类型                                           | 结论                                                         | 你们怎么用                                                   |
| ------------------ | ---------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **Tutti**          | arXiv 2026，vLLM-integrated SSD-backed KV 思路 | 它解决 SSD-backed KV 的 tiny random I/O、CPU-centric control path、GPU/NPU stall 问题；核心是 GPU-centric HBM-SSD KV object I/O 和 GPU io_uring。([arXiv](https://arxiv.org/abs/2605.03375?utm_source=chatgpt.com)) | 作为 P3 目标：未来 NPU-native SSD/direct path。当前 Ascend 不要默认有同等能力。 |
| **Bidaw**          | FAST 2026                                      | host memory + SSD two-tier KV，compute-storage bidirectional awareness；按 KV 所在层和大小调度，避免慢 KV 请求阻塞。([USENIX](https://www.usenix.org/conference/fast26/presentation/hu-shipeng?utm_source=chatgpt.com)) | 用它设计你们的 DRAM/SSD KV 队列：ready queue / preparing queue / KV-size-aware ordering。 |
| **SolidAttention** | FAST 2026                                      | SSD 存完整 KV，GPU/HBM 只装 sparse attention 选中的关键 KV blocks；128k context 下可提升速度并大幅减少 KV footprint。([USENIX](https://www.usenix.org/system/files/fast26-zheng.pdf?utm_source=chatgpt.com)) | 只适合作为长上下文/稀疏 attention 研究项。DeepSeek/GLM 的 attention 结构兼容性要单独验证。 |

项目材料里的判断非常关键：SSD cold tier 可以放 cold KV、cold experts、checkpoint、trace，但不能在 P0 进入逐 token 热路径；P0 应先把 active KV 留 HBM、inactive KV 异步下沉 DRAM、prefix/reusable context 放 DRAM 或 UCM external KV。

## 5. CPU/NPU 协同计算：这些论文能指导边界

| 工作          | 已发表状态  | 机制                                                         | 对 A+K 的意义                                                |
| ------------- | ----------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **NEO**       | MLSys 2025  | 把部分 decode attention compute 和 KV cache state offload 到本机 CPU，用 asymmetric GPU-CPU pipelining 和 load-aware scheduling 提升 batch/throughput。([arXiv](https://arxiv.org/abs/2411.01142?utm_source=chatgpt.com)) | 适合指导 “Kunpeng 只吃可重叠的 decode/KV 子路径”。不要把它理解为 CPU 主算。 |
| **FlexInfer** | MLSys 2025  | 在 CPU-only、GPU offload、CPU-GPU static partition/SplitGen 之间按阶段和硬件 profile 选策略。([ACM Digital Library](https://dl.acm.org/doi/10.1145/3721146.3721961?utm_source=chatgpt.com)) | 适合做你们的 `policy_selector`：prefill/decode/KV restore/expert miss 分别估算，不静态写死。 |
| **llm.npu**   | ASPLOS 2025 | prompt/tensor/block 三层拆分，NPU 处理规则大矩阵，CPU/GPU 处理 outlier、动态路径、fallback。([ACM Digital Library](https://dl.acm.org/doi/10.1145/3669940.3707239?utm_source=chatgpt.com)) | 方法论可迁移：Ascend NPU 主算，Kunpeng 做 outlier、控制、小算子、fallback；但手机 NPU 结果不能直接外推到 Atlas A2。 |
| **DistServe** | OSDI 2024   | 将 prefill 和 decode 分离，解决两阶段干扰，并按 TTFT/TPOT 优化 goodput。([USENIX](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin?utm_source=chatgpt.com)) | 单机 A2 不建议先做物理 P/D 分离；先做逻辑队列分离、stream 隔离和 KV transfer 计量。 |

内部精读也给了重要纠偏：NEO 应理解为“部分 decode attention + KV 留 CPU 侧，并通过 asymmetric pipeline 与 GPU/NPU 主路径重叠”；FlexInfer 是阶段级 policy selector；KTransformers 是 shared experts/GPU + routed experts/CPU + AMX/AVX/NUMA/CUDA Graph/Expert Deferral，不是普通 expert offload。

## 6. 可观测、仿真和 trace：必须并行建设

你们现在最容易犯的错误是先优化再测瓶颈。项目材料已经把 P0 定为 “workload/profiler/simulator host + KV CPU Offload + UCM/prefix cache”，P1 才是 Mooncake KV Pool / PD 与 MoE expert hotness，P2 才是 SSD-backed KV/state cold tier，P3 才是 NPU-native SSD/direct path。

| 工具/论文                     | 类型                    | 用途                                                         | 现状                                                         |
| ----------------------------- | ----------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **CANN msprof / msnpureport** | Ascend 官方工具         | P0 必用；采 NPU kernel、stream、H2D/D2H、CANN 侧性能         | 你们服务器上已经可用。                                       |
| **ProfInfer**                 | arXiv 2026              | eBPF 细粒度 LLM profiler，可采 forward、graph、operator、thread、hardware counters | 你们当前 bpftrace/eBPF 权限受阻，所以先借鉴 schema，不直接依赖它落地。([arXiv](https://arxiv.org/pdf/2601.20755?utm_source=chatgpt.com)) |
| **LLMServingSim2.0**          | 开源 repo + arXiv       | 异构加速器、CPU/CXL/PIM、MoE routing、P/D、TP/PP/EP/DP 的系统级仿真 | 可以作为 simulator 参考，但 Ascend/Kunpeng 需要补自己的硬件 profile。([GitHub](https://github.com/casys-kaist/LLMServingSim?utm_source=chatgpt.com)) |
| **ServeGen**                  | NSDI 2026 + GitHub      | 真实 LLM serving workload generator，按 client 分解生成负载  | 用来生成压测 trace 的外部参考；需要补本地 Coding Agent/办公 Agent trace。([USENIX](https://www.usenix.org/conference/nsdi26/presentation/xiang-servegen?utm_source=chatgpt.com)) |
| **BurstGPT**                  | 数据集 repo + 论文      | 真实 Azure OpenAI 负载 trace，适合 replay/burstiness 研究    | 可作为仿真输入模板，但不是本地 Agent 专属 trace。([GitHub](https://github.com/HPMLL/BurstGPT?utm_source=chatgpt.com)) |
| **MLCommons Chakra**          | 开源 trace schema/tools | 标准化 AI execution trace，适合 simulator 接口               | 可作为长远 trace schema 对齐参考。([GitHub](https://github.com/mlcommons/chakra/blob/main/USER_GUIDE.md?utm_source=chatgpt.com)) |

项目文档建议的实验字段已经足够接近可执行：记录 `request_id/session_id/model_name`、prompt/output tokens、prefill/decode 时间、TTFT/TPOT/P95/P99、NPU memory/HBM、CPU/DRAM、SSD bytes/queue depth、D2H/H2D、KV hit/miss、prefix hit/miss、expert ids、expert hit/miss、expert load latency、stall reason。

## 7. 推荐你们的第一版代码仓结构

直接按项目材料里的 `ak-infer-lab` 拆。这个结构已经覆盖 baseline、microbench、trace、state runtime、MoE offload、simulator，不需要先搞一个大而全的 serving engine。

```text
ak-infer-lab/
  microbench/
    npu_gemm_shapes/
    cpu_sve_shapes/
    d2h_h2d_copy/
    hccs_hccl_bw/
    ddr_bandwidth/
    nvme_io/
    duma_latency/

  serving_baseline/
    mindie/
    vllm_ascend/
    sglang_optional/

  trace/
    schema/
    collector/
    chrome_trace_export/
    dashboard/

  state_runtime/
    kv_object/
    prefix_object/
    expert_object/
    weight_shard_object/
    tier_manager/

  moe_offload/
    expert_trace/
    hotness_predictor/
    prefetch_scheduler/
    placement_policy/

  simulator/
    cost_model/
    replay/
    what_if/
    hardware_sensitivity/
```

每个实验都要输出 experiment card。内部材料已经给了字段模板，包括 model/framework/npu_count/quant/context_len/TP/EP/DP/CP、KV policy、prefix policy、expert policy、CPU policy、SSD policy、TTFT、TPOT、HBM max、DRAM traffic、SSD bytes、D2H/H2D bytes、expert hit、prefix hit、quality delta、stall top-3。

## 8. 开工顺序：不要平均用力

### 第 0 层：基础环境与 microbench

先验证：

```text
CANN / torch-npu / vLLM-Ascend version matrix
npu-smi / msprof / msnpureport
H2D / D2H bandwidth and overlap
DDR bandwidth and NUMA locality
NVMe seq/random I/O and P99
HCCS/HCCL bandwidth
NPU GEMM shapes
CPU SVE/OMP small matmul shapes
```

原因：你们要做的是状态分层和 offload，收益边界由 **搬运成本、同步成本、CPU kernel 能力、SSD P99** 决定，不是由论文倍率决定。

### 第 1 层：MindIE + vLLM-Ascend baseline

用 Qwen/DeepSeek 小中模型先跑通：

```text
Qwen 7B / 14B / 32B
DeepSeek-R1-Distill-Qwen 7B / 14B / 32B
Qwen 72B / Qwen MoE 或其他中型 MoE
```

内部方案也建议先分三档：A 档基线模型打通 CANN/vLLM-Ascend/profile，B 档中型/中大模型验证 KV/Prefix/MoE trace，C 档 GLM5.2/DeepSeek 大 MoE 只做低比特、专家分层、KV/Prefix 分层和 SSD cold tier 的边界实验。

### 第 2 层：KV CPU Offload + UCM

按变量矩阵跑：

```text
offload on/off
num_cpu_blocks
block_size
gpu_memory_utilization
max_model_len
prefix reuse ratio
session interval
batch/concurrency
```

目标不是“平均吞吐提升”，而是回答：

```text
HBM 释放了多少？
H2D/D2H stall 是否进热路径？
prefix miss/hit 的 TTFT 差多少？
CPU DRAM pool 是否稳定？
LRU 是否造成 thrash？
```

### 第 3 层：ExpertTrace + hot expert cache V0

先记录，不先优化：

```text
top-k experts per layer
expert frequency
reuse distance
layer-wise hotness
session-wise hotness
expert miss penalty
load bytes
load latency
```

再实现最简单的：

```text
shared expert + non-expert 主干常驻 HBM
top-N hot routed experts 常驻 HBM
warm experts 在 DRAM
cold experts 在 SSD / checkpoint
```

### 第 4 层：Simulator

把 microbench 和 trace 喂进 simulator：

```text
what if HBM = 64GB / 84GB / 128GB / 200GB?
what if DDR bandwidth +50%?
what if SSD P99 doubles?
what if H2D latency increases?
what if expert hit rate 70/80/90/95%?
what if prefix hit 50/70/90%?
```

这就是你们后续反推硬件规格的主证据。项目材料也明确要求 12 周内形成 A+K serving simulator，回答 HBM、DRAM、SSD P99、CPU 核数、TP/EP/DP/CP 配比变化对 TTFT/TPOT/P95/P99 的影响。

## 9. 最小可执行清单

按“今天就能开工”的优先级排：

| 优先级 | 代码/框架/论文                                              | 动作                                                         |
| ------ | ----------------------------------------------------------- | ------------------------------------------------------------ |
| 1      | `vllm-project/vllm-ascend`                                  | 拉起 Qwen 小模型 baseline；打开 KV Cache CPU Offload；接 KV events。 |
| 2      | UCM Store                                                   | 做 DRAM local cache + prefix cache；暂不依赖共享 storage。   |
| 3      | `kvcache-ai/Mooncake`                                       | P1 做 KV Pool backend；先不要进 P0。                         |
| 4      | `lmcache/lmcache`                                           | 抄 KVObject API、backend 抽象和 observability 思路。         |
| 5      | `kvcache-ai/ktransformers`                                  | 读 MoE hybrid expert placement；不要直接移植 AMX kernel。    |
| 6      | `IntelliSys-Lab/FineMoE-EuroSys26`                          | 做 ExpertMap / semantic hint / expert prefetch 的参考实现。  |
| 7      | DALI / FluxMoE / MoE-Lightning                              | 把 workload-aware assignment、expert paging、HRM model 写进 simulator。 |
| 8      | Tutti / Bidaw / SolidAttention                              | 作为 SSD cold tier 设计参考；不要 P0 上热路径。              |
| 9      | NEO / FlexInfer / llm.npu                                   | 做 CPU/NPU 阶段级协同 policy selector 的论文依据。           |
| 10     | ProfInfer / LLMServingSim2.0 / ServeGen / BurstGPT / Chakra | 做 trace、profiling、simulator 和 workload generation 的证据层。 |

## 10. 一句话落地建议

**第一版工程不要叫 “DeepSeek/GLM 单卡部署系统”，应叫 “AK-Infer-Lab：Ascend NPU 热计算 + Kunpeng/DRAM/SSD 状态分层实验栈”。**

P0 只承诺：

```text
MindIE/vLLM-Ascend baseline
KV CPU Offload
UCM prefix/KV object
request-level trace
microbench
ExpertTrace
simple hot expert cache
first simulator
```

P1 再承诺：

```text
Mooncake KV Pool
expert hotness predictor
warm expert DRAM tier
prefix reuse / restore-vs-recompute
miss penalty curves
```

P2/P3 才谈：

```text
SSD-backed KV / expert cold tier
NPU-SSD direct path
adaptive precision cold expert
physical P/D disaggregation
unified state-object runtime
```

这条路线和你们项目材料中的最终表述一致：基于 Atlas 800T A2 的 64GB/NPU 近端显存约束，构建 MindIE + vLLM-Ascend 双轨底座，通过 KV/Prefix DRAM warm tier、UCM/external KV、MoE expert hotness trace、专家冷热分层、SSD cold tier 和 trace-driven simulator，验证 Qwen/DeepSeek/GLM 类模型在 A+K 架构上的容量、性能和失效边界。