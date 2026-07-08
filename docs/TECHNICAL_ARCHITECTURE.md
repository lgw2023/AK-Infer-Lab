# 技术架构：AK 状态分层推理实验栈

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

## 2. 热层、温层、冷层

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

Prefill 更偏 compute-bound。主要记录：prompt tokens、chunked prefill 配置、AI Core task、HBM peak、KV write bytes、prefix reuse、full prefill latency、first token latency。

### 4.2 Decode

Decode 更偏 memory/state-bound。主要记录：per-token latency、KV read、expert dispatch、hot expert hit、H2D/D2H、scheduler queue、prefix hit、MTP accept、tail latency。

### 4.3 KV/Prefix 分层路径

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

### 4.4 Expert 分层路径

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
