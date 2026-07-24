# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R12 CPU-hit → H2D-load 准入诊断

~~~text
task_id: p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724
execution_mode: authorized_single_lifecycle_hit_to_load_admission
server_sync_review_authorized: true
offline_parent_gate_required: true
npu_execution_authorized: true
keep_alive_stop_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
result_directory_creation_authorized: true
keep_alive_card_ids_exact: 0,1,2,3,4,5,6,7
server_task_driver_required: true
manual_internal_step_reconstruction_authorized: false
server_side_code_edit_authorized: false
formal_model_lifecycle_count_exact: 1
model_request_count_min: 3
model_request_count_max: 4
pressure_request_count_exact: 1
request_retry_count_exact: 0
restore_request_count_max: 1
accepted_cpu_blocks_per_rank_exact: 128
accepted_cpu_bytes_per_rank_exact: 430604288
accepted_cpu_bytes_total_exact: 3444834304
logical_target_block_count_exact: 128
accepted_restore_match_tokens_exact: 16384
target_restore_shared_prefix_tokens_exact: 32768
target_restore_prompt_identity_required: true
hash_block_size_tokens_exact: 128
pressure_context_tokens_exact: 36800
pressure_role_exact: pressure_01
target_cache_stamp_lineage_required: true
physical_group_cpu_only_window_required_to_abort: true
legacy_capped_probe_required: true
eagle_aware_logical_lookup_required: true
hit_to_load_admission_lineage_required: true
allocate_slots_observation_required: true
update_state_after_alloc_observation_required: true
connector_load_meta_observation_required: true
all_relevant_kv_groups_required: true
all_applicable_kv_groups_required: true
post_abort_fresh_revalidation_required: true
logical_restore_window_required_before_restore: true
runtime_pool_key_count_fixed: false
physical_fa_key_count_fixed: false
kv_connector: SimpleCPUOffloadConnector
full_request_window_watch_required: true
stop_on_first_near_miss: false
stop_on_first_unobservable_probe: false
stop_on_first_cpu_target_eviction: false
context_change_authorized: false
capacity_change_authorized: false
capacity_search_authorized: false
pressure_search_or_sweep_authorized: false
concurrent_restore_while_pressure_active_authorized: false
runtime_or_dependency_mutation_authorized: false
profiler_authorized: false
hbm_sampler_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
next_task_authorized: false
k2_authorized: false
p8_3_i1_authorized: false
no_k2_k3_k4_p8_3_i1_p8_4_p8_5_or_p9: true
~~~

## 先读结论：R12 的代码已经写好，服务器只同步、审计、执行、回报

### R11 已经证明的事实

R11 不是 accepted capacity 失败，也不是 logical lookup 仍为 0。它已经在唯一
fixed `36800` pressure 中得到：

~~~text
physical CPU-only window exact = true
EAGLE-aware / raw logical hit = 16384
legacy capped hit = 0
legacy_capped_false_negative_candidate_count = 67
post-abort logical_restore_window_exact = true
restore_allowed = true
restore_sent = true
restore_cpu_hit_exact = true
restore_cpu_hit_tokens_max = 16384
restore_load_scheduled = false
H2D workers / bytes = 0 / 0
restore_follower = HTTP 200, 0 streamed tokens, e2el ≈ 67ms, spec_activity_ok=false
~~~

因此当前阻断已经从“找不到 CPU hit”推进到：

**CPU hit 已见，但 hit 之后没有进入 H2D load schedule，restore 请求立刻失败。**

### R12 修复/观测的实际机制

冻结路径是：

~~~text
SimpleCPUOffloadScheduler.get_num_new_matched_tokens
  -> pin pending CPU hit, return (hit_length, is_async=True)
Scheduler.allocate_slots(..., num_external_computed_tokens, delay_cache_blocks=True)
  -> None 则永远不会调用 update_state_after_alloc
SimpleCPUOffloadScheduler.update_state_after_alloc
  -> num_external==0 / pending missing / null-filter empty / 或写入 _reqs_to_load
build_connector_meta
  -> load_event / load_gpu_blocks
worker H2D copy
~~~

R11 只证明了第一段 `cpu_hit_matched`。R12 在同一 accepted capacity / 同一 16K
窗口上，只补 observe-only 准入分支，不改 capacity、context、请求计划语义，也不改
服务器依赖。

服务器必须在有界摘要里看到：

~~~text
restore_hit_to_load_gap_class
restore_allocate_slots_observed / restore_allocate_slots_ok / restore_allocate_slots_none
restore_num_external_tokens_at_alloc
restore_num_new_tokens_at_alloc
restore_delay_cache_blocks_at_alloc
restore_update_after_alloc_called
restore_num_external_tokens_at_update
restore_pending_present_at_update
restore_update_early_return_reason
restore_entered_reqs_to_load
restore_transfer_gpu_block_count / restore_transfer_cpu_block_count
restore_connector_load_event_ready
~~~

这些字段会出现在 `h2d_trigger_summary.json`、`transfer_trace_summary.json` 和
`grading_summary.json`。

## 不要做

- 不要重跑 R10 / R11，不要改 capacity / context / pressure tokens
- 不要做 request retry、sweep、第二 lifecycle、K2、P8.3-I1
- 不要在服务器改代码、改依赖、打补丁、改 observer 合同
- 不要把 raw request id / hash / block id / token id / 生成内容写进有界包
- 不要把 `result_transfer_authorized: true` 理解成已选择传输方式
- 不要自动 email / upload；先完整清单，再等用户明确选择
- 不要授权下一任务：`next_task_authorized=false`

## keep-alive 操作规则

停 keep-alive 是常规资源操作。本任务 TP8，卡集固定 `0 1 2 3 4 5 6 7`。
成功、失败、中断、early exit 后都必须在完全相同卡集恢复，并回报 stopped / restored。

~~~bash
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

## 唯一执行入口

服务器先 `git pull` 到与远程 `main` 一致，然后只执行：

~~~bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724_run01
mkdir -p "${RESULT_DIR}"

# 可选：先确认 R11 parent 仍在约定路径
# 默认 PARENT_ROOT=
#   ${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723_run01
# 若实际目录不同，导出：
# export P8_2_K1A_F1_R11_ROOT=/实际/R11/run01路径

bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r12_server_task.sh "${RESULT_DIR}"
~~~

该 driver 会：

1. 校验仓库合同与 R11 parent 9 个 SHA-256
2. stop keep-alive `0-7`
3. 执行唯一 fixed lifecycle
4. cleanup
5. 同卡恢复 keep-alive `0-7`
6. 写出有界候选包，并停下等待传输方式选择

## R11 parent 证据门（必须全部匹配）

父目录默认：

`server_local/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723_run01`

~~~text
78be6275a0142918aff454bbda91e6bdcb359b20cdea6adefe31798c75fea633  grading_summary.json
8e29e91836490c80e932f19c0aced534e659454fded42abc04f351b27c18f5a9  residency_gate_timeline.json
c11b92b1af91759feedafbb697a58aaf0d7c4f2d5f8bbeaedf4781619b602d39  h2d_trigger_summary.json
9fe1cf8ff256d6cb120f3d7babec72527da8a90df03130651ae7a2cdf62b0d4f  transfer_trace_summary.json
cfbabbcbf74602ad60f20c1a6e20874a0a8bdb0ff150cdec263f0fd842a8dc15  logical_keyspace_probe_diagnostic_summary.json
d2b7f24a5f885f6026692badf590107b2b8082c40bff63edb13d60953e077343  target_store_lineage_summary.json
459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862  repair_diagnostic_summary.json
7374e1763cf2f20793c66865a31f860fe6040888319af1f433d69cc6eae234a6  resource_recovery_summary.json
bb04845f8e16a9acc8fd7f4f445b2c115a9124469e234ef00a3b3dbb6fa9827d  candidate_manifest.server_local.json
~~~

父事实硬门槛：

~~~text
server_grade = red_p8_2_k1a_r5_f1_r11_h2d_evidence_incomplete
operational_grade = operational_recovery_clean
experimental_terminal = restore_request_failure
restore_cpu_hit_exact = true
restore_load_scheduled = false
h2d_worker_count = 0
restore_cpu_hit_tokens_max = 16384
d2h_store_complete = true
d2h_bytes_total = 2206846976
~~~

## 判定场景（本轮核心）

### A. `allocate_slots_failed_after_hit`

`cpu_hit_matched` 有，`allocate_slots_ok=false`，`update_state_after_alloc` 未调用，
`load_scheduled=false`，H2D=0。这说明 scheduler 在 external tokens 上没有拿到 GPU
slots，H2D 根本进不去。

### B. `num_external_zero` 或 `pending_missing`

`update_state_after_alloc` 被调用，但 early return 是 `num_external_zero` /
`pending_missing`。这说明 connector hit 与 scheduler 传入的 external token 数不一致，
或 pending pin 已丢失。

### C. `empty_transfer_after_null_filter`

update 被调用且 pending 存在、`num_external>0`，但 transfer block count=0。说明
group 级 null/padding 过滤把可拷贝块清空。

### D. `load_scheduled` 但 H2D 仍为 0

`entered_reqs_to_load=true` / `load_scheduled=true`，但 worker H2D 仍 0。这已经越过
admission，下一轮才应看 connector/worker copy，而不是再扩 lookup。

### E. 完整 H2D candidate

load + 8-worker H2D completion exact。仍不得宣称唯一根因；只是机制候选。

## 有界结果包要求

结果目录：

`/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724_run01`

至少回报：

1. `result_summary.md`
2. `grading_summary.json`
3. `h2d_trigger_summary.json`（必须含 `restore_hit_to_load_gap_class`）
4. `transfer_trace_summary.json`
5. `residency_gate_timeline.json`
6. `logical_keyspace_probe_diagnostic_summary.json`
7. `target_store_lineage_summary.json`
8. `request_summary.tsv`
9. `repair_diagnostic_summary.json`
10. `connector_resolution_summary.json`
11. `mtp_queue_health_summary.json`
12. `host_memory_summary.json`
13. `resource_recovery_summary.json`
14. `cleanup_status.txt`
15. `candidate_manifest.server_local.json`

完整包（payload + manifest）目标尽量不超过 `71680` bytes；若超过 email 上限，
仍可走 `upload-api`，但必须先完整清单并等待用户选择。

每个邮件正文/附件仍服从 70KB 上限。raw profiler、大日志、请求体、hash、block IDs、
request IDs、token IDs、生成内容必须留服务器。

## 传输选择门

完成 lifecycle 后，先回报：

- result summary 路径
- 完整文件清单（文件名 / bytes / SHA-256 / sensitivity）
- payload 合计与 transfer 合计
- 可用方法：`email` / `upload-api` / `server-local`
- 推荐方法与原因

然后停下，等待用户明确选择一个方法。不要先发状态-only 邮件，不要自行切换方法。

`result_transfer_authorized: true` 只表示有界包具备候选资格，不选择渠道，不扩大文件范围。

## Direct contract input SHA-256 inventory

服务器在执行前应用下列 SHA 核对当前仓库文件（与本地发布一致）：

~~~text
dd337a31ed209ef215dc55dc6c00b592782f34eb940d5eb1203077f3ee7e94fb  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r12_hit_to_load_admission_audit.yaml
0320550ecd8acc53ce45ce31ba37ececf36cc98b2fc51348730a7690a2e998ab  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r12_hit_to_load_admission.yaml
9ab0d17e1281feb923115068cb990e1c68b971bc843209d3d8b6575631e1b19d  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
24f8256f33240349f0ca15f26fa83c98bb9ed1278e20ce2e02f7daa76db8c689  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
fd5fd74fac8903c3e2e68bed7a4b9a5f599230f3257a4e721090a87655eb0e48  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py
b27232c7ea1397078b052efe8fea10a92bb422e6efc0cb41bd3948734f1ee1db  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
3488140e597852c2de38a69942f87263ff92ecc8dafc530fc479faca9ebebecb  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
9b193867f0ecdd4098985eb041937f9e73c4e421b8afce1f5253a5b51f036e23  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
35ebddaf2016ee24c898642f55005800490711f968aaa333c25e4f4dcd3ddb4d  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.py
71301a3f9272fd304996f140b09e53c27a0c459cd5e33cb383bf6eb7183454dd  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.sh
db4a5fe4b7e5bc9ab1bb6b4dca927f0660c29b3cdd45354ca22e51962ba6e390  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r12_server_task.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
26f8b3e4e127483ae0185508080e017b7c0ac05e79a146f26e0370a608bdd3d6  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
~~~


## 历史标记（供合同测试对齐，不是当前入口）

~~~text
http_transport_success_count
expected_keep_alive_marker_count=16
#0#
成功、失败、中断或提前退出
experimental_grade
target_pool_key_count
logical_restore_match_tokens
request_hash_candidate_count
pressure_progress_runtime_keyspace_refresh_required=true
logical_target_block_count=128
P8_2_K1A_F1_R12_SERVER_TASK_AUDIT_ONLY=1
P8_2_K1A_F1_R7_SERVER_TASK_AUDIT_ONLY=1
完整逻辑 128-block CPU-only 窗口
不要手工拆内部步骤
request-local
find_longest_cache_hit(request_hashes, 16384)
F1-R6 的实验 RED、运维 GREEN
成功、实验 RED、失败、中断或提前退出
test ! -e "${RESULT_DIR}"
red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost
parent_h2d_worker_count=0
upstream_f1_r3_request_count=4
parent_f1_r5_task=p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722
p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723
p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_2026_0723
p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723
p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723
run_deepseek_p8_2_k1a_r5_f1_r11_server_task.sh
run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.sh
constructor_use_eagle=false
R10 已经证明的事实
16384 + 16384 = 32768
不要把 40 个 physical keys 写成缺少 88 个 logical blocks
CPU=64/GPU=0
P8.2-K1A-R1
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
blocked_p6_3c_not_strict_single_variable
candidate_green_mtp_profiled_evidence
candidate_ready_p8_2_k1a_r2_allocator_capacity
candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure
completed_blocked_sampling_calibration
completed_blocked_source_or_resource_gate
completed_p8_2_k1a_r5_f1_r2_runner
completed_p8_2_k1a_r5_f1_runner
completed_server_candidate_developer_accepted_green
current_p8_2_k1a_r5_f1_r5_runner
email / upload-api / server-local
green_mtp_decode_length_ladder_revalidated
green_mtp_minimal_request_success
green_p8_2_k0_order_balanced_prefix_cache_baseline
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
handoff_contains_transfer_command
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
measurement_green_protocol_deviation
p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_audit.yaml
p8_2_k1a_r5_f1_r12_hit_to_load_admission.yaml
p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722
p8_2_k1a_r5_f1_r2_grade
p8_2_k1a_r5_f1_r2_trace_alignment_2026_0722
parent_cleanup=clean
parent_d2h_store_complete=true
ready_p8_2_k1a_r2_allocator_capacity
run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.sh
run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh
run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh
workloads/p8_2_k1a_r5_f1_r12_hit_to_load_admission.yaml
不得进入 P8.3-I1
parent_grade: red_p8_2_k1a_r5_f1_r11_h2d_evidence_incomplete
parent_f1_r11_task_id: p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723
parent_f1_r10_task_id: p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723
parent_grade=red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
parent_successful_request_count=3
parent_task_id=p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722
required_restore_block_count_exact: 128
payload_file_count
transfer_file_count_including_manifest
result_transfer_authorized: true
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
green_p8_1_r1_official_mtp_observe_only_matrix
blocked_p8_2_k1_frozen_stack_import_incompatible
cpu_bytes_to_use_per_rank=430604288
P8.2-K1A-R5-F1-R11 EAGLE-aware logical lookup lineage
fetch origin main
merge --ff-only origin/main
不得进入 K2
K2
P8.3-I1
~~~

同步命令示例（只读对齐，不构成第二任务）：

~~~bash
git fetch origin main
git merge --ff-only origin/main
~~~

## 完成后立即停止

本轮结束后：

- `next_task_authorized=false`
- 不得自动开 R13 / run02 / K2 / P8.3-I1
- 只回报本轮有界证据与 keep-alive 恢复状态
