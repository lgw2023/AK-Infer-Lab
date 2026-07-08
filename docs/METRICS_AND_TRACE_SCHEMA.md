# Metrics and Trace Schema

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
