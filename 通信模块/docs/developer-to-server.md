# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R14 compress-aware pairing repair

~~~text
task_id: p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725
execution_mode: authorized_single_lifecycle_compress_aware_pairing_repair
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
site_packages_edit_authorized: false
task_local_observer_behavioral_repair_authorized: true
compress_aware_pairing_repair_required: true
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
update_raise_geometry_lineage_required: true
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

## 先读结论：R14 的代码已经写好，服务器只同步、审计、执行、回报

### R13 已经证明的事实

R13 run01 在同一 accepted capacity / fixed `36800` / 单 lifecycle 上得到：

~~~text
restore_hit_to_load_gap_class = update_raised
restore_update_error_type = IndexError
restore_update_error_message = list index out of range
restore_update_raise_subclass = index_error_gpu_cpu_pairing
restore_num_cached_fa_blocks = 0
restore_fa_block_size = 128
restore_gpu_block_table_lens = [32, 1, 128, 128, 2048, 512]
restore_n_take_by_group = [128]
restore_gpu_ext_start_by_group = [96]
restore_first_pairing_overflow_group_index = 0
restore_first_overflow_needed_index = 96
restore_first_overflow_gpu_len = 32
restore_entered_reqs_to_load = false
restore_load_scheduled = false
H2D workers / bytes = 0 / 0
~~~

机制算术：

~~~text
frozen g_block_size = spec.block_size = 128   # 不含 compress_ratio
n_take = 16384 / 128 = 128
n_ext  = min(128, pending0) = 32
n_computed = cdiv(16384, 128) = 128
gpu_ext_start = 128 - 32 = 96
group_gpu_ids[96] → IndexError   # 表长仅 32
~~~

若按 Ascend compress-aware 物理几何（FA `effective=512`）：

~~~text
n_take = 16384 / 512 = 32
gpu_ext_start = 0
gpu_len = 32 → 配对成立
~~~

因此当前阻断不是 lookup / allocate，而是 **冻结 `update_state_after_alloc` 用 raw `spec.block_size` 做 pairing，忽略了 compress_ratio 物理量纲**。

### R14 实际机制（task-local repair，不是改依赖）

本轮在仓库已交付的 observer overlay 内启用受控修复：

1. 环境变量 `P8_2_K1A_ENABLE_COMPRESS_AWARE_PAIRING_REPAIR=1`（runner 已设）
2. 运行时核对 `vllm/v1/simple_kv_offload/manager.py` SHA-256 必须等于
   `fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b`
3. 仅当冻结几何预检为 `index_error_gpu_cpu_pairing`，且 compress-aware 几何预检为 `ok` 时，
   才走 task-local `repaired_update_state_after_alloc`
4. 修复路径用 `base * cp * compress_ratio`（或 runtime coordinator `_get_effective_block_size`）
   替代冻结 `spec.block_size`，然后照常写入 `_reqs_to_load`
5. 不改 site-packages、不改服务器依赖、不改 capacity/context

服务器必须在有界摘要里看到：

~~~text
restore_pairing_repair_enabled
restore_pairing_repair_eligible
restore_pairing_repair_applied
restore_pairing_repair_skip_reason
restore_manager_source_sha_matched
restore_compress_aware_geometry_status
restore_compress_aware_block_sizes
restore_compress_aware_n_take_by_group
restore_compress_aware_gpu_ext_start_by_group
restore_compress_aware_predicted_transfer_pair_count
restore_entered_reqs_to_load
restore_load_scheduled
restore_hit_to_load_gap_class
~~~

成功主路径期望：

~~~text
restore_pairing_repair_applied = true
restore_compress_aware_geometry_status = ok
restore_compress_aware_n_take_by_group[0] = 32
restore_compress_aware_gpu_ext_start_by_group[0] = 0
restore_entered_reqs_to_load = true
restore_load_scheduled = true
restore_hit_to_load_gap_class = load_scheduled
~~~

然后继续观察 connector load meta / H2D workers / bytes / restore 请求是否完成。
仍不得宣称唯一根因或性能结论。

## 不要做

- 不要重跑 R10 / R11 / R12 / R13，不要改 capacity / context / pressure tokens
- 不要做 request retry、sweep、第二 lifecycle、K2、P8.3-I1
- 不要在服务器改代码、改依赖、改 site-packages；本轮 repair 已在仓库 observer 内
- 不要把 raw request id / hash / block id / token id / 生成内容写进有界包
- 不要把 `result_transfer_authorized: true` 理解成已选择传输方式
- 不要自动 email / upload；先完整清单，再等用户明确选择
- 不要授权下一任务：`next_task_authorized=false`

## keep-alive 操作规则

停 keep-alive 是常规资源操作。本任务 TP8，卡集固定 `0 1 2 3 4 5 6 7`。
成功、失败、中断、early exit 后都必须在完全相同卡集恢复，并回报 stopped / restored。

若 driver 恢复未持久（R12/R13 曾出现），允许手动：

~~~bash
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

启动前请确认 HBM 已从 keep-alive 占压释放。必要时先手动 `npu_stop.sh 0-7`，
确认每卡 HBM 降到可用后再跑 driver。

## 唯一执行入口

服务器先 `git pull` 到与远程 `main` 一致，然后只执行：

~~~bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725_run01
test ! -e "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"

# 可选：确认 R13 parent 仍在约定路径
# 默认 PARENT_ROOT=
#   ${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r13_update_raise_geometry_2026_0724_run01
# 若实际目录不同，导出：
# export P8_2_K1A_F1_R13_ROOT=/实际/R13/run01路径

bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r14_server_task.sh "${RESULT_DIR}"
~~~

该 driver 会：

1. 校验仓库合同与 R13 parent 9 个 SHA-256
2. stop keep-alive `0-7`
3. 执行唯一 fixed lifecycle（repair env 已开）
4. cleanup
5. 同卡恢复 keep-alive `0-7`
6. 写出有界候选包，并停下等待传输方式选择

## R13 parent 证据门（必须全部匹配）

父目录默认：

`server_local/p8_2_k1a_r5_f1_r13_update_raise_geometry_2026_0724_run01`

~~~text
ae89aa2e9c0373aa74a528ec732d8d12ebcc9e03d55e06d418aeb3e122b0a9a9  grading_summary.json
09904e8e605fd9112a9e55c9c6bdf53c79ce2e1c7d98ae2230f42f80271dbfa9  residency_gate_timeline.json
98e0cbca45929b8e67cfc5655c0a1afe7623c50316937479d5413d667023ba4d  h2d_trigger_summary.json
0463048453bec7813268e8f2891a001621c079cddbe93d6b9e7956861451fff1  transfer_trace_summary.json
77fbcf4290fe9a8bd76b227cc373d60687e229f3118b3a1635573e10ca0e31c1  logical_keyspace_probe_diagnostic_summary.json
61530a2c3fc20a57fd94922f1629b73e26b562085cea83371a4755b8a0b75515  target_store_lineage_summary.json
459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862  repair_diagnostic_summary.json
f64373b464356cdaae72dac2e645971c48c5df986b9eb4046195af031f0218ad  resource_recovery_summary.json
248655f8bfce690f0d2c19a01a1fb8b2a0be699377541f7d55542dd0098bdf4b  candidate_manifest.server_local.json
~~~

父事实硬门槛：

~~~text
server_grade = red_p8_2_k1a_r5_f1_r13_h2d_evidence_incomplete
operational_grade = operational_recovery_clean
experimental_terminal = restore_request_failure
restore_hit_to_load_gap_class = update_raised
restore_update_raise_subclass = index_error_gpu_cpu_pairing
restore_first_pairing_overflow_group_index = 0
restore_first_overflow_needed_index = 96
restore_first_overflow_gpu_len = 32
restore_num_cached_fa_blocks = 0
restore_load_scheduled = false
h2d_worker_count = 0
h2d_bytes_total = 0
d2h_store_complete = true
~~~

## 判定场景（本轮核心）

### A. repair applied → load scheduled（期望主路径）

~~~text
restore_pairing_repair_applied = true
restore_compress_aware_geometry_status = ok
restore_entered_reqs_to_load = true
restore_load_scheduled = true
restore_hit_to_load_gap_class = load_scheduled
~~~

继续回报 H2D workers/bytes、connector load meta、restore 请求终态。

### B. repair skipped（manager SHA / geometry 门失败）

回报 `restore_pairing_repair_skip_reason`：
`manager_sha_mismatch_or_unreadable` /
`frozen_geometry_not_index_overflow` /
`compress_aware_geometry_not_ok` /
`repair_disabled`

### C. repair applied but load/H2D still incomplete

`repair_applied=true` 但 `load_scheduled=false` 或 H2D=0。这是下一轮问题，不是 R13 重复分类。

### D. 仍 `update_raised`

repair 未生效或 repair 自身失败。必须带 error_type/message 与两边几何字段。

## 有界结果包要求

结果目录：

`/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725_run01`

至少回报：

1. `result_summary.md`
2. `grading_summary.json`
3. `h2d_trigger_summary.json`（必须含 repair / compress-aware 字段）
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

服务器在执行前应用下列 SHA 核对当前仓库文件（与本地发布一致；提交后会刷新）：

~~~
f4e917864fccc640be4c11c8196e8a8206e45cf2967cfe7add7c8643479a9ca9  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_audit.yaml
f45fa16069ea7f7dee3f72a492165909b793b48bcf91e12c47f6d383d0f9b9b5  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.yaml
9ab0d17e1281feb923115068cb990e1c68b971bc843209d3d8b6575631e1b19d  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
697b9f34a966decef947b367ffc7c660751f2113d158e14a0dde7bef5dae8ae0  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
fd5fd74fac8903c3e2e68bed7a4b9a5f599230f3257a4e721090a87655eb0e48  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py
835c5434805747d9c094770e67b82f1f7e89d906ce6f8fdcbcc18016af929338  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
3488140e597852c2de38a69942f87263ff92ecc8dafc530fc479faca9ebebecb  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
9b193867f0ecdd4098985eb041937f9e73c4e421b8afce1f5253a5b51f036e23  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
934c241d34e10bd84bb7df677db70a0511fc2bec345de7921cba60622a8e5eef  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.py
fd6c08e1e46547bb356c83cf573b8cbc20eea230f63eeba2cb18c2ea9f99e839  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.sh
6c8302bd411b951493d2a4718afe38219220e133c2ab487f615db19f0d74c43c  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r14_server_task.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
3c418d8f6df194d5863e29207185bc96846f3d8779d20e589f8165e8541df644  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
~~~

## 历史标记（供合同测试对齐，不是当前入口）

~~~text
restore_follower
restore_follower_with_update_raise_geometry_lineage
restore_follower_with_compress_aware_pairing_repair
P8.2-K1A-R5-F1-R12 CPU-hit → H2D-load 准入诊断
P8.2-K1A-R5-F1-R13 update_raised 异常与 pairing geometry
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
P8_2_K1A_F1_R14_SERVER_TASK_AUDIT_ONLY=1
P8_2_K1A_F1_R13_SERVER_TASK_AUDIT_ONLY=1
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
run_deepseek_p8_2_k1a_r5_f1_r12_server_task.sh
run_deepseek_p8_2_k1a_r5_f1_r12_hit_to_load_admission.sh
run_deepseek_p8_2_k1a_r5_f1_r13_server_task.sh
run_deepseek_p8_2_k1a_r5_f1_r13_update_raise_geometry.sh
constructor_use_eagle=false
R10 已经证明的事实
R12 已经证明的事实
R13 已经证明的事实
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
p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724
p8_2_k1a_r5_f1_r13_update_raise_geometry.yaml
p8_2_k1a_r5_f1_r13_update_raise_geometry_2026_0724
p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.yaml
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
workloads/p8_2_k1a_r5_f1_r13_update_raise_geometry.yaml
workloads/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.yaml
不得进入 P8.3-I1
parent_grade: red_p8_2_k1a_r5_f1_r13_h2d_evidence_incomplete
parent_grade: red_p8_2_k1a_r5_f1_r12_h2d_evidence_incomplete
parent_grade: red_p8_2_k1a_r5_f1_r11_h2d_evidence_incomplete
parent_f1_r13_task_id: p8_2_k1a_r5_f1_r13_update_raise_geometry_2026_0724
parent_f1_r12_task_id: p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724
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
allocate_slots_observed
update_state_after_alloc_observed
connector_load_meta_observed
restore_hit_to_load_gap_class
restore_pairing_repair_applied
P8.2-K1A-R5-F1-R12 CPU-hit to H2D-load admission
authorized_single_lifecycle_hit_to_load_admission
authorized_single_lifecycle_update_raise_geometry
authorized_single_lifecycle_compress_aware_pairing_repair
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
- 不得自动开 R15 / run02 / K2 / P8.3-I1
- 只回报本轮有界证据与 keep-alive 恢复状态
