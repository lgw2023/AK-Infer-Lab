# Metrics and Trace Schema

## 0. 术语、来源与当前采集口径

| 标准术语 | 来源类型 / `AK 协同/` 锚点 | 当前项目口径 | 不可替代为 |
| --- | --- | --- | --- |
| TTFT / Time To First Token | 官方框架文档：`references/web/vLLM-disaggregated-prefill.html` | host client 收到 first non-empty streaming chunk 的耗时 | NPU 首个 kernel 或纯 prefill device time |
| TPOT / Time Per Output Token | benchmark / 框架指标：第三轮可核验报告与 MindIE/vLLM 资料 | `(response_end - first_token) / (generated_tokens - 1)` | 单个 decode kernel latency |
| ITL / Inter-Token or Inter-Chunk Latency | 官方框架文档：`references/web/vLLM-disaggregated-prefill.html` | P1.29/P1.31 中为 host streaming inter-chunk median per request | runtime native decode event 或算子执行间隔 |
| E2EL / client wall time | benchmark / 框架指标：第三轮可核验报告与 MindIE/vLLM 资料 | 客户端从 request start 到 response end 的端到端耗时 | 纯设备执行时间 |
| H2D / D2H | 官方框架 release-note/guide：vLLM-Ascend release notes 与 KV CPU Offload guide | Host to Device / Device to Host copy | NPU-NPU interconnect 或 HCCL collective 带宽 |
| HBM used/free | 设备监控与项目 artifact 字段 | whole-device NPU HBM occupancy | per-request KV object bytes 或 HBM traffic |
| KV cache usage | vLLM server stats 输出字段 | vLLM server stats 中的 KV cache usage proxy | KV 真实字节数 |
| all-reduce / all-gather / reduce-scatter / all-to-all | 官方框架资料 + CCL-Bench：vLLM-Ascend release notes、`CCL-Bench__arxiv-2605.06544.pdf` | 待测 HCCL collective 通信模式 | 泛化的“多卡通信速度” |
| algbw / busbw | 待选 collective benchmark 的原始输出字段；当前资料库无独立权威定义页 | 计划随工具版本、collective、world size、payload 一并登记 | HCCL 官方字段或未标口径的“卡间带宽” |

完整来源路径和机制类术语映射见 `docs/SOURCES_AND_BOUNDARIES.md`。来源锚点证明术语或机制在领域认知体系中存在，不提升当前实验的证据等级。

写入网站、README 或阶段报告时，每个性能数字都必须附带 `Scope` 和 `Not Claim`。当前 P0-P4 仅能提供特定路径的 observed facts，不支持 compute-bound、memory-bound、queue-bound、scheduler-bound、AI Core / AIV / MTE bottleneck 归因。

## 1. 指标分组

### Request-level

```yaml
request_id:
session_id:
model_id:
prompt_id:
arrival_ts_ns:
start_ts_ns:
first_token_ts_ns:
end_ts_ns:
prompt_tokens:
generated_tokens:
status:
error_type:
ttft_ms:
tpot_ms_mean:
tpot_ms_p95:
itl_ms_list_digest:
```

### Runtime queue

```yaml
event_type: queue_event
request_id:
stage: prefill | decode | restore | sampling
queue_name:
ts_ns:
running_reqs:
waiting_reqs:
batch_size:
max_num_seqs:
max_num_batched_tokens:
policy_decision:
stall_reason:
```

### NPU / HBM

```yaml
event_type: device_metric
rank_id:
ts_ns:
hbm_used_gb:
hbm_peak_gb:
kv_cache_usage_pct:
ai_core_utilization:
aiv_utilization:
top_op_type:
top_op_duration_ns:
stream_id:
task_id:
```

### Transfer

```yaml
event_type: transfer_event
request_id:
rank_id:
direction: h2d | d2h | p2p | disk_to_host | host_to_disk | disk_to_device
object_id:
bytes:
start_ts_ns:
end_ts_ns:
latency_ms:
stream_id:
overlap_with_compute: true | false | unknown
```

### KV / Prefix object

```yaml
event_type: state_object_event
object_type: kv_block | prefix_chunk | context_chunk
object_id:
request_id:
session_id:
layer_id:
block_id:
tokens:
bytes:
tier_before:
tier_after:
action: create | lookup | hit | miss | offload | restore | evict | recompute
start_ts_ns:
end_ts_ns:
latency_ms:
reason:
```

### Expert object

```yaml
event_type: expert_event
request_id:
session_id:
rank_id:
layer_id:
token_index:
router_topk:
expert_scores_digest:
expert_id:
expert_tier:
action: route | hit | miss | prefetch | load | evict | execute | fallback
bytes:
load_latency_ms:
execute_latency_ms:
prefetch_lead_time_ms:
wrong_prefetch_bytes:
stall_ms:
```

### SSD / storage

```yaml
event_type: storage_event
device_path:
object_id:
operation: read | write | delete | stat
bytes:
io_size:
queue_depth:
start_ts_ns:
end_ts_ns:
latency_ms:
p95_latency_ms_window:
eviction_policy:
quota_bytes:
```

## 2. Join Keys

所有 trace 必须至少支持以下 join：

| Join | 字段 |
| --- | --- |
| request ↔ runtime queue | request_id |
| request ↔ device task | time window + request_id when possible |
| request ↔ transfer | request_id + object_id |
| request ↔ KV object | request_id + object_id |
| request ↔ expert | request_id + layer_id + token_index |
| device task ↔ msprof | timebase + startNs/endNs |
| workload ↔ request | prompt_id + session_id |

## 3. Experiment card

```yaml
experiment_id:
date:
git_commit:
operator:
server:
model:
model_variant:
model_source:
local_source_path:
server_model_path:
model_role: official_baseline | source_checkpoint_readiness | conversion_candidate | boundary_probe
runtime_source:
runtime:
scenario: p6_eight_card_baseline | p7_single_dual_extreme | p8_kv_prefix_tiering | p8_expert_tiering | p9_hardware_sensitivity
parallelism:
features:
workload:
metrics:
boundaries:
is_smoke:
is_benchmark:
is_controlled_ab:
is_degraded_smoke:
control_variables:
changed_variable:
known_confounds:
artifacts:
  workload_manifest:
  request_trace:
  server_log:
  msprof_dir:
  device_aggregate:
  summary:
acceptance:
  request_success:
  fixed_generated_tokens:
  profiler_collected:
  request_device_join:
  benchmark_claim_allowed:
```

## 4. 判读规则

- Smoke 只能证明路径可运行。
- Server stats 只能作为 runtime 自带指标，不能单独作为命中率验收。
- msprof collected 只能证明 profiler 可采集，不能自动说明瓶颈。
- on/off A/B 必须固定请求、输出长度、并发计划和环境变量。
- 如果 generated tokens 不一致，不得做性能对比。
- 如果 request window 与 device timebase 未对齐，不得做 request-device 归因。
- 如果 SSD I/O size 不可见，不得声称 SSD cold tier 可用。
- 如果 expert miss penalty 不可见，不得声称专家分层收益。
- `size=1G, pinned=1, non_blocking=0` 的 H2D/D2H `24.313915 / 26.480714 GB/s` 只是当前 benchmark 路径下的同步端到端 observed copy ceiling；不是 PCIe/UB 理论峰值、NPU-NPU 带宽或 copy-compute overlap 证据。
- `non_blocking=True` 后立即 synchronize 的 sweep 不保留 host async issue 或 copy-compute overlap 证明力。
- NumPy read/copy `5.332057 / 2.963189 GB/s` 只是 Python/NumPy 路径下的 observed CPU memory path ceiling；不是 server DRAM hardware peak。
- 当前没有 Atlas 800T A2 单机八卡 NPU-NPU interconnect 实测；H2D/D2H 不得代替 pairwise P2P 或 HCCL collective 数据。
