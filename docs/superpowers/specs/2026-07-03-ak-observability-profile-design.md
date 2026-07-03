# A+K Observability Profile Spec

## 0. 目标与非目标

本 spec 定义 Atlas 800T A2 A+K 推理实验环境的服务器可观测能力体检格式。

服务器体检不是性能测试，而是对 Atlas 800T A2 当前软硬件环境的可观测能力盘点：逐字段判断是否可采、采集来源、权限依赖、采集代价、证据 artifact、fallback 路径，以及能否通过 join key 和时间戳对齐归因到请求、算子、搬运或状态对象。

目标：

- 建立全量观测字段目录，覆盖 request/runtime、operator、NPU/HBM、CPU/DRAM、transfer/overlap、SSD/I/O、state object、KV/Prefix、MoE expert、power/stability 和 microbench。
- 为每个字段定义统一元信息，明确字段类型、单位、采样方式、采集工具、权限、开销、join key、time base、验证方式和验收规则。
- 对服务器实际可测性给出结构化结论：`measurable`、`partial`、`blocked`、`unknown`、`not_applicable`。
- 输出机器可读结果，使后续 P3/P4/P5 实验卡直接引用字段状态和 P0 硬验收字段。
- 单独判断 join key readiness 和 time alignment，避免“采到很多数据但无法归因”。

非目标：

- 不输出模型性能优劣结论。
- 不承诺 SSD cold tier、MoE expert hot cache、KV offload 或 CPU fallback 的收益。
- 不实现 profiler hook、runtime hook 或采集脚本。
- 不把 `blocked` 和 `unknown` 字段从设计中删除；它们必须进入缺口闭环。

## 1. 设计原则

1. 全量字段先盘点，再决定 P0 硬验收范围。
2. 字段定义与服务器可测性分离；字段存在不代表当前服务器已经能采。
3. 人读摘要不维护第二套事实，只引用机器可读结果。
4. 每个可用于瓶颈归因的字段必须声明 `join_key` 和 `time_base`。
5. `state_object_profile` 是父层，KV、Prefix、Expert、Weight、Activation、Workspace 都继承统一对象字段。
6. `operator_timeline_profile` 只描述算子发生了什么，`npu_hbm_profile` 只描述 NPU/HBM 资源状态。
7. `ssd_io_profile` 进入 P0 能力体检，但 SSD cold tier 性能优化不进入 P0 硬验收。
8. 多次服务器体检必须可比较；run manifest 要记录硬件拓扑、软件栈和 probe 脚本版本。

## 2. Profile 分层

第一版全量 profile 包括：

| Profile | 角色 | 第一版字段组 |
| --- | --- | --- |
| `server_observability_profile` | 服务器、软件栈、权限和工具能力盘点 | OS、kernel、CANN、driver、firmware、torch-npu、MindIE/vLLM-Ascend、容器、NPU 可见性、perf/eBPF/fio/CANN profiler 权限 |
| `request_runtime_profile` | 请求生命周期 | arrival、enqueue/dequeue、queue_wait、admission、batch_id、batch size、prefill/decode/sampling/cleanup、JCT |
| `scheduler_policy_profile` | 调度与决策 | policy_name、why_this_device、why_prefetch、why_evict、why_recompute、cache allocation/free、pin/unpin、TTL、backpressure、reject reason |
| `operator_timeline_profile` | 算子发生了什么 | layer_id、op_name、kernel_name、CANN op、shape、dtype、tiling、launch overhead、kernel duration、stream id、graph compile/cache、dynamic shape fallback |
| `npu_hbm_profile` | NPU/HBM 资源状态 | AI Core/AIV/Cube util、busy/idle、HBM allocated/reserved/free/peak、fragmentation、workspace peak、KV pool、expert cache、HBM read/write BW、HBM stall |
| `cpu_dram_profile` | CPU/DRAM 控制面与温层 | thread name、core id、NUMA node、user/sys/iowait、context switch、runqueue、scheduler/tokenizer/sampler/cache lookup、DRAM BW、pinned memory、page fault、host OOM |
| `transfer_overlap_profile` | 搬运与重叠 | direction、bytes、latency、effective GB/s、setup cost、copy submit/complete、copy stream、compute stream、compute_overlap_us、copy_exposed_us、overlap_ratio、sync barrier、event wait |
| `ssd_io_profile` | SSD/I/O 能力体检 | seq/random read/write BW、IOPS、QD、p50/p95/p99/p999、I/O size histogram、direct I/O/page cache、mmap、readahead、submit path、temperature、throttling |
| `state_object_profile` | 状态对象父层 | object_type、object_id、owner_request、layer_id、bytes、tier、lifecycle_event、load_cost、evict_cost、recompute_cost、hotness、next_use、consistency_scope |
| `kv_prefix_profile` | KV/Prefix 子层 | kv_object_id、tokens_range、block_size、block_table、fragmentation、hit tier、miss reason、prefix_hash、matched_tokens、position_shift、reuse_distance、restore vs recompute |
| `moe_expert_profile` | MoE Expert 子层 | router logits/scores、top_k ids/probs、entropy、expert_frequency、hotness、reuse_distance、resident/prefetched/evicted、hit/miss、miss_tier、load_latency、prefetch lead time、accuracy |
| `power_stability_profile` | 能耗和稳定性 | NPU/CPU/DRAM/SSD/system power、energy/token、temperature、frequency、DVFS、thermal throttling、OOM、CANN error、SSD timeout、1h/6h/24h p95/p99 drift |
| `microbench_profile` | 硬件基线 | NPU op-by-shape、CPU kernel-by-shape、DDR BW、SSD IOPS、H2D/D2H latency/BW、pageable/pinned、sync/async、copy overlap、不同 size/chunk/QD 矩阵 |

## 3. 字段元信息 Schema

每个观测字段必须按同一套元信息描述：

```yaml
field:
  name:
  profile:
  meaning:
  layer:
  field_type: inventory | counter | event | metric | trace | derived_metric
  unit:
  required_for_p0: true | false
  sampling_mode: one_shot | per_request | per_token | per_layer | periodic | microbench
  measurement_source:
  expected_tool:
  permission_need:
  collection_overhead: low | medium | high
  expected_artifact:
  join_key:
    - trace_id
    - request_id
    - session_id
    - phase
    - layer_id
    - stream_id
    - object_id
  time_base:
  availability:
    status: measurable | partial | blocked | unknown | not_applicable
    confidence: high | medium | low
    evidence_probe:
    evidence_artifact:
    blocked_reason:
      category:
      detail:
    partial_reason:
    last_checked_at:
  validation_method:
  acceptance_rule:
  fallback:
  notes:
```

`blocked_reason.category` 枚举：

```yaml
permission
tool_missing
framework_hook_missing
container_isolation
timestamp_unaligned
join_key_missing
hardware_not_exposed
workload_not_available
unknown
```

`join_key` 规则：

- 用于瓶颈归因的字段必须能通过 `trace_id`、`request_id`、`phase`、`layer_id`、`stream_id`、`object_id` 或同等字段对齐。
- 没有 join key 的字段只能进入 inventory、独立 microbench 或全局趋势分析，不能直接用于解释某个 token、某个 layer 或某次 KV restore 为什么慢。
- `time_base` 必须声明来源，例如 `host_monotonic_ns`、`host_wall_clock`、`cann_device_timeline`、`fio_timestamp`、`probe_tool_timestamp`。

## 4. 服务器体检 Run 目录结构

每次服务器体检输出一个独立 run 目录：

```text
工作记录与进度笔记本/observability_profiles/
  YYYY-MM-DD_<profile_run_id>_observability_run/
    manifest.yaml
    server_observability_profile.md
    field_availability.yaml
    join_key_readiness.yaml
    p0_acceptance_fields.yaml
    probe_results/
      npu_smi_probe.md
      cann_profiler_probe.md
      perf_probe.md
      ebpf_probe.md
      fio_probe.md
      numa_probe.md
      container_permission_probe.md
```

目录命名中的日期使用体检开始日期，后接清理后的 `profile_run_id`。这样同一天多次体检也会落到不同目录。

## 5. `manifest.yaml` Schema

`manifest.yaml` 记录这次体检的全局身份、硬件、软件和版本信息：

```yaml
profile_run_id: obs_2026_0703_atlas800t_a2_001
schema_version: 0.1.0
server_id: atlas800t-a2-node-001
timestamp_start:
timestamp_end:
operator:
git_commit:
host_name:
container_id:
container_image:
inside_container:
container_privileged:
cann_version:
driver_version:
npu_count:
hbm_per_npu_gb:
field_catalog_version:
hardware_topology_hash:
software_stack_hash:
probe_script_version:
notes:
```

Hash 含义：

- `hardware_topology_hash`：由 NPU 数量、PCIe/UB/HCCS 拓扑、NUMA、NVMe 列表生成，用来判断硬件拓扑是否变化。
- `software_stack_hash`：由 CANN、driver、torch-npu、MindIE、vLLM-Ascend、Python、容器镜像生成，用来判断软件栈是否变化。
- `probe_script_version`：体检脚本或探针目录版本，用来区分字段状态变化来自环境变化还是 probe 逻辑变化。

## 6. `field_availability.yaml` Schema

`field_availability.yaml` 是字段可测性主表。每个字段一条记录：

```yaml
fields:
  - name: queue_wait_us
    profile: request_runtime_profile
    meaning: time between request enqueue and dequeue
    layer: runtime
    field_type: metric
    unit: us
    required_for_p0: true
    sampling_mode: per_request
    measurement_source: runtime request log
    expected_tool: vLLM/MindIE request hook or wrapper log
    permission_need: app_log_access
    collection_overhead: low
    expected_artifact: runtime_queue_trace.jsonl
    join_key: [trace_id, request_id, phase]
    time_base: host_monotonic_ns
    availability:
      status: unknown
      confidence: low
      evidence_probe:
      evidence_artifact:
      blocked_reason:
        category:
        detail:
      partial_reason:
      last_checked_at:
    validation_method: compare enqueue/dequeue timestamps on synthetic single request
    acceptance_rule: measurable if non-null for >=95% requests and monotonic timestamps are valid
    fallback: wrapper-level enqueue/dequeue log
    notes:
```

Availability status rules:

- `measurable`：字段可采，证据 artifact 存在，验收规则满足。
- `partial`：字段可部分采集，但存在粒度不足、时间戳不齐、join key 不全、容器内外差异或工具只暴露近似值。
- `blocked`：当前环境应当可以追求该字段，但被权限、工具、hook、容器隔离、时间戳、join key 或硬件暴露问题阻塞。
- `unknown`：尚未验证，不能作为硬验收字段。
- `not_applicable`：当前硬件或实验形态不适用，例如无远端 RDMA 时的 remote transfer 字段。

## 7. `probe_results` Schema

每个 probe 文件记录一个工具或权限探针的运行上下文、证据和阻塞原因：

```yaml
tool: cann_profiler
available: true
permission_status: ok | limited | blocked
command:
exit_code:
start_time:
end_time:
runtime_ms:
run_as_user:
inside_container:
container_privileged:
output_excerpt:
artifact_path:
maps_to_fields:
  - operator_timeline_profile.kernel_duration_us
  - npu_hbm_profile.hbm_read_gbps
blocked_reason:
  category:
  detail:
```

Probe 文件可以使用 Markdown 包裹 YAML front matter 或 YAML code block。必须保留足够证据说明判定来源，但不需要保存完整长日志。

## 8. `join_key_readiness.yaml` Schema

`join_key_readiness.yaml` 判断不同 profile 的数据能否对齐到同一次请求、同一阶段、同一层、同一 stream 或同一状态对象。

```yaml
join_key_readiness:
  - profile_pair: state_object_profile + transfer_overlap_profile
    required_keys: [trace_id, object_id, lifecycle_event, stream_id]
    status: measurable | partial | blocked | unknown | not_applicable
    missing_keys: [object_id, stream_id]
    time_alignment:
      status: measurable | partial | blocked | unknown
      time_bases:
        - host_monotonic_ns
        - cann_device_timeline
      alignment_method: offset_calibration | wrapper_event_marker | unavailable
      max_expected_skew_us:
      consequence: cannot prove object restore/load caused exposed copy time
    consequence: cannot attribute KV restore or expert load to copy overlap loss
    fix: add object event hook, copy stream tagging, and wrapper event marker
```

Time alignment rules:

- `offset_calibration`：通过启动前后事件标记估计不同时间基偏移。
- `wrapper_event_marker`：在 host log、runtime log、profiler timeline 中插入同一事件标记。
- `unavailable`：没有可用对齐方法，不能用于精确归因。

即使 join key 完整，如果 time alignment 为 `blocked` 或 `unknown`，也不能声称某个 KV restore、expert load、SSD restore 或 H2D/D2H copy 直接导致了某个 TPOT spike。

## 9. `p0_acceptance_fields.yaml` Schema

`p0_acceptance_fields.yaml` 单独列出第一轮可以进入硬验收的字段。它只引用 `measurable` 和可解释的 `partial` 字段。

```yaml
p0_acceptance_fields:
  - field: request_runtime_profile.queue_wait_us
    status: measurable
    source: runtime_queue_trace.jsonl
    acceptance_rule: non-null for >=95% requests and timestamps are monotonic
    caveat:

  - field: transfer_overlap_profile.overlap_ratio
    status: partial
    source: copy_overlap_trace.csv
    acceptance_rule: present for H2D/D2H microbench sizes used in P3
    caveat: host-side estimate only until device stream alignment is verified
```

P3/P4/P5 实验卡只能把该文件中的字段作为 P0 硬验收字段。其他字段可以记录为探索性信息或缺口。

## 10. `server_observability_profile.md` 模板

人读总览文件只引用机器可读结果，不维护第二套事实。

推荐结构：

```md
# Server Observability Profile

## 1. Run Summary
来自 `manifest.yaml`。

## 2. Server And Tool Readiness
汇总 `probe_results/`。

## 3. Profile-Level Observability
按 profile 统计 measurable / partial / blocked / unknown / not_applicable。

## 4. P0 Acceptance Fields
引用 `p0_acceptance_fields.yaml`。

## 5. Join-Key And Time-Alignment Readiness
引用 `join_key_readiness.yaml`。

## 6. Gap Summary
按 `blocked_reason.category` 聚合。

## 7. Recommended Next Actions
列出先修哪些权限、工具、hook、join key 或 time alignment 缺口。
```

## 11. P0 完成判定

服务器体检 P0 完成条件：

1. Run 目录存在，且包含 `manifest.yaml`、`server_observability_profile.md`、`field_availability.yaml`、`join_key_readiness.yaml`、`p0_acceptance_fields.yaml`、`probe_results/`。
2. `manifest.yaml` 包含 `hardware_topology_hash`、`software_stack_hash`、`probe_script_version`。
3. 全量字段都进入 `field_availability.yaml`。
4. 每个字段都有元信息、`availability.status`、验收规则、验证方法、证据或阻塞原因。
5. 每个 profile 有明确结论。
6. 关键 profile pair 有 join key readiness 和 time alignment 判断。
7. P0 硬验收字段单独生成到 `p0_acceptance_fields.yaml`。
8. `blocked` 和 `unknown` 字段进入缺口清单，并能按原因分类。
9. SSD/I/O 完成能力体检，但 SSD cold tier 性能优化不作为 P0 完成条件。

## 12. 后续 P1/P2 扩展

P1 扩展重点：

- 让 `state_object_profile` 从字段设计进入 runtime hook，补齐 KV、Prefix、Expert、Weight、Activation、Workspace 的对象生命周期事件。
- 提升 `join_key_readiness`，把 request/runtime、operator timeline、transfer overlap、state object 关联到同一 `trace_id`、`phase`、`layer_id`、`stream_id`、`object_id`。
- 细化 MoE expert trace：top-k、entropy、expert hit/miss、miss tier、load latency、prefetch lead time、accuracy。
- 将 `partial` 字段中因时间戳或 join key 不完整导致的 caveat 收敛到可验收状态。

P2 扩展重点：

- SSD cold tier 性能实验：cold KV restore、cold expert restore、I/O size histogram、queue depth、page cache/direct I/O、submit path 和 p99/p999 抖动。
- trace-driven simulator：基于 `field_availability.yaml` 和 P0/P1 真实 trace，扫描 HBM、DRAM、H2D/D2H、SSD、expert cache、prefix/KV 命中率。
- power/stability 长稳：1h/6h/24h 漂移、能耗/token、温度、频率、thermal throttling、OOM 和 CANN error。

## Spec Self-Review

- Placeholder scan: no placeholder sections remain.
- Internal consistency: run manifest, field availability, probe results, join-key readiness, P0 acceptance fields, and human-readable summary all use one fact-source model.
- Scope check: this spec only covers observability capability profiling and does not include implementation or performance optimization.
- Ambiguity check: `blocked`, `unknown`, and `not_applicable` are distinct, and P0 hard acceptance fields are machine-readable.
