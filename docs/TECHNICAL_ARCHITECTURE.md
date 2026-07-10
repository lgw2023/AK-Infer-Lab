# 技术架构：KV/Prefix/Expert Memory Tiering 推理实验栈

术语来源：Memory tiering / External KV Cache 对齐 `AK 协同/references/web/LMCache-docs.html`、Mooncake/LMCache 系统论文与 vLLM-Ascend UCM 文档；KV Cache CPU Offload 对齐 vLLM-Ascend 官方 guide；MoE Expert Offload / Expert Cache 对齐 KTransformers、FineMoE、DALI、FluxMoE 等论文；Prefill/Decode disaggregation 对齐 vLLM 官方文档与 DistServe/Splitwise 论文。这里的“热层 / 温层 / 冷层”和“状态对象”是项目内解释，不是新的外部技术名词；架构映射也不代表相关机制已经在 Atlas 800T A2 上验证为正收益。

本页描述长期技术架构；当前 P8 的 runtime adapter、StateObject metadata 边界、垂直切片和证据门见 `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`。P8 不要求一次性实现本页所有真实迁移路径。

## 1. 架构视图

```text
Request / Workload
  → vLLM-Ascend / MindIE Runtime
    → Ascend NPU Hot Path
      → HBM: active weights, hot experts, active KV, workspace
    ↔ Kunpeng CPU + DRAM Warm Tier
      → inactive KV, reusable prefix, warm experts, metadata, staging buffers
    ↔ NVMe SSD Cold Tier
      → cold KV, cold experts, checkpoints, trace, raw profiler artifacts
    → Trace / Profiler / Simulator
      → request-device join, bottleneck attribution, what-if hardware scan
```

## 2. HBM / DRAM / SSD-NVMe Memory Tiers（项目内：热层 / 温层 / 冷层）

| 层 | 硬件 | 状态对象 | 目标 | 约束 |
| --- | --- | --- | --- | --- |
| Hot | Ascend NPU HBM | hot weights, hot experts, active KV, activation, workspace | 保障 decode 热路径连续执行 | 64GB per NPU，不是统一 512GB |
| Warm | Kunpeng DRAM/DUMA | inactive KV, reusable prefix, warm experts, pinned staging, metadata | 扩展容量并支持低成本回温 | DDR 带宽、NUMA、H2D/D2H、同步开销 |
| Cold | NVMe SSD | cold KV, cold expert, checkpoint, raw trace | 大容量持久化与离线分析 | 不能随机小块进入逐 token 热路径 |
| Control | CPU runtime | scheduler, cache manager, policy, ledger | 决策和可观测 | 控制面开销不能吞掉收益 |

## 3. 状态对象模型

所有可迁移对象都应纳入统一 ledger：

```yaml
object_id: string
object_type: kv_block | prefix_chunk | expert_weight | weight_shard | activation | workspace | trace_artifact
model_id: string
layer_id: int | null
rank_id: int | null
request_id: string | null
session_id: string | null
bytes: int
dtype: string
tier: hbm | dram | ssd | remote | absent
state: resident | loading | evicting | evicted | recompute_only | invalid
hotness_score: float
last_access_ts_ns: int
next_use_hint: string | null
load_cost_ms: float | null
evict_cost_ms: float | null
recompute_cost_ms: float | null
quality_risk: none | low | medium | high
```

## 4. 运行时数据流

### 4.1 Prefill

Prefill 在论文和推理系统中常作为 compute-sensitive 阶段分析，但本项目不预设当前 workload 已经 compute-bound。主要记录：prompt tokens、chunked prefill 配置、AI Core task、HBM peak、KV write bytes、prefix reuse、full prefill latency、first token latency。

### 4.2 Decode

Decode 在论文和推理系统中常作为 memory/state-sensitive 阶段分析，但本项目不预设当前 workload 已经 memory-bound。主要记录：per-token latency、KV read、expert dispatch、hot expert hit、H2D/D2H、scheduler queue、prefix hit、MTP accept、tail latency。

### 4.3 KV Cache CPU Offload / External KV Cache 路径

```text
NPU HBM active KV
  ├─ keep: 当前请求和短期复用热块
  ├─ offload: inactive KV → CPU block pool
  └─ restore: prefix miss on HBM but hit in CPU/DRAM → async H2D
```

UCM/Mooncake 进一步扩展为：

```text
HBM → DRAM local cache → SSD/NFS/3FS storage backend
```

### 4.4 MoE Expert Offload / Expert Cache 路径

```text
Router top-k
  → check HBM hot expert cache
    → hit: execute on NPU
    → miss: check DRAM warm expert tier
      → async prefetch / stage to HBM
      → if late: record stall or fallback
    → cold expert: SSD restore only if prefetch window sufficient
```

## 5. 控制面策略

### KV policy

- Active KV stays in HBM.
- Inactive KV can move to CPU DRAM.
- SSD KV is cold tier only unless object I/O and prefetch are proven.
- Restore-vs-recompute decision must be measured.

### Prefix policy

- Exact prefix cache first.
- Repeated-prefix workload first.
- Cross-position reuse only after baseline exact cache is measurable.

### Expert policy

- Trace before tiering.
- Static hotset before predictor.
- Predictor before SSD cold tier.
- Low-precision cold expert only after quality regression.

### CPU/NPU policy

- CPU always does metadata, scheduling and analysis.
- CPU may do prefetch planning and I/O aggregation.
- CPU may do partial compute only when overlap and microbench prove net benefit.

## 6. 软件组件映射

| 组件 | 作用 | 当前优先级 |
| --- | --- | --- |
| MindIE | 官方性能基线 | A |
| vLLM-Ascend | 可改造研究原型 | A |
| KV Cache CPU Offload | DRAM warm tier | A |
| UCM | external KV / prefix object layer | A- |
| Mooncake KV Pool | distributed/persistent KV backend | B |
| LMCache | API 与对象模型参考 | B |
| KTransformers/FineMoE/DALI/FluxMoE | MoE expert tiering 机制参考 | B |
| Tutti/Bidaw/SolidAttention | SSD cold tier 边界参考 | C |
| Profiler + Simulator | 硬件规格反推 | A |

## 7. 当前证据状态

| 机制 / 指标 | 状态 | 当前可声明 | 当前不可声明 |
| --- | --- | --- | --- |
| H2D / D2H copy | YES | 当前 benchmark 路径下的同步端到端 observed copy ceiling | PCIe/UB 理论峰值、NPU-NPU 通信或 copy-compute overlap |
| Two-stream copy concurrency | PARTIAL | 已有早期双 stream copy smoke | 不是 host async issue 或 copy-compute overlap 证据 |
| NPU-NPU interconnect / HCCL collective | NO | 待做 pairwise P2P 和 HCCL sweep | 不得用 H2D/D2H 替代 algbw / busbw |
| KV Cache CPU Offload / External KV Cache | PARTIAL | 已有 copy ceiling、phase memory 和 KV usage proxy | 不能声称 offload 净收益、object bytes 或 hit/miss 闭环 |
| Bottleneck attribution | NO | 待 request-token-operator-stall 证据闭合 | 不得声称 compute/memory/queue/scheduler-bound |
