# 从 DeepSeek-V4-Flash 推理实验反推下一代硬件规格

## 1. 反推目标

项目最终要回答的不是“某个软件开关是否提升 tokens/s”，而是下一代小算力系统应优先补哪类短板：近端容量、近端带宽、CPU/NPU 互联、主存带宽、SSD I/O、NPU-SSD 直通、CPU 核数、PIM/HMM、计数器还是运行时接口。

## 2. 硬件参数与推理症状

| 症状 | 可能瓶颈 | 需要证据 | 硬件含义 |
| --- | --- | --- | --- |
| 模型无法加载 | HBM 容量 / 权重分片 / expert 总量 | weight memory, rank HBM, loader trace | 增加近端容量或支持更强分层加载 |
| TPOT 高且 AI Core 不满 | HBM bandwidth / KV / expert miss / scheduler | AI Core util, HBM, KV/expert events | 增加近端带宽或热集驻留能力 |
| TTFT 高 | prefill compute / prefix miss / chunked prefill | prefill tasks, prefix hit, prompt length | 优化 prefill 并行、prefix cache 和 Index/attention 路径 |
| tail latency 抖动 | H2D/D2H、SSD、expert miss、runtime queue | P95/P99, transfer, storage, queue | 降低跨层恢复尾延迟 |
| prefix on/off 差异不稳定 | workload 复用不足或 cache 管理不足 | prefix_id, reuse_distance, server stats | 需要更好的 external KV / position-aware reuse |
| KV offload 反而变慢 | NPU-CPU link 或 restore 不可重叠 | D2H/H2D, overlap, restore latency | 需要更高互联或更好的异步 copy engine |
| expert tiering 无收益 | expert 热度不可预测或 miss 在关键路径 | topk trace, hit/miss, miss penalty | 需要更大 hot expert cache 或更低 latency warm tier |
| SSD cold tier 不可用 | tiny random I/O / CPU bounce / queue tail | io_size, queue depth, P99 | 需要 object I/O、direct path 或更大 DRAM warm tier |

证据阶梯：
- Smoke：只能说明路径可运行或不可运行。
- Controlled benchmark：可以比较单变量方向性影响。
- Profile + request-device aggregate：可以提出候选瓶颈。
- Microbench + simulator what-if：可以做硬件参数敏感性判断。
- 只有以上证据能闭合时，才能形成下一代硬件规格诉求。

## 3. 硬件敏感性实验

### 3.1 HBM 容量

模拟 64GB、84GB、128GB、200GB、400GB per NPU。输出：可常驻 hot expert 数量、KV headroom、max_model_len、max_num_seqs、fragmentation risk。

### 3.2 HBM 带宽

对 decode 热路径做 bandwidth stress。输出：TPOT 对 HBM bandwidth 的斜率，以及 hot KV/hot expert 访问量。

### 3.3 CPU-DRAM 带宽

对 KV CPU Offload 和 warm expert tier 建模。输出：offload block restore 是否被 DRAM 带宽限制；warm expert 是否可以在 prefetch window 内回温。

### 3.4 NPU-CPU 互联

扫 H2D/D2H bandwidth 和 latency。输出：restore bytes/token、copy stream overlap、barrier stall、有效重叠比例。

### 3.5 SSD I/O

区分 sequential large I/O、random small I/O、object I/O。输出：SSD cold tier 是否只能离线，还是可作为 prefetch tier。

### 3.6 CPU 核数与向量能力

记录 metadata manager、I/O aggregation、prefix hash、expert prediction、fallback compute。输出：CPU 在控制面与少量计算路径上的饱和点。

## 4. 下一代硬件诉求模板

```yaml
hardware_ask_id:
trigger_experiment:
observed_bottleneck:
affected_metric:
  - ttft
  - tpot
  - p95
  - hbm_peak
  - expert_miss
  - kv_restore
current_value:
required_value:
modeling_basis:
software_assumption:
risk_if_not_fixed:
priority: P0 | P1 | P2 | P3
```

## 5. 预期硬件诉求方向

1. **更大近端容量**：让 hot weights、hot experts、active KV 和 workspace 不互相挤压。
2. **更强主存与近端互联**：让 DRAM warm tier 真正可回温，而不是只做冷备份。
3. **NPU-SSD direct/object I/O**：面向 P3，避免 CPU-centric tiny I/O 与 bounce copy。
4. **更强状态可观测计数器**：暴露 KV、expert、copy、stream、HCCL/HCCS、HBM、SSD 的统一时间域事件。
5. **HMM/PIM 类容量与近存计算**：面向更长上下文和更稳定低 TPOT，把 KV、activation 或专家访问变成近存高带宽问题。
6. **运行时可编排的内存语义**：统一 state object、pin/move/evict/compress/recompute 接口，避免软件只能被动 swap。
