# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R15 restore step lineage

~~~text
task_id: p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725
execution_mode: authorized_single_lifecycle_restore_step_lineage
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
compress_aware_pairing_repair_retained: true
restore_step_lineage_required: true
physical_fa_cpu_only_gate_required: true
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

## 先读结论：R15 的代码已经写好，服务器只同步、审计、执行、回报

### R14 已经证明的事实（父证据）

R14 run01 在同一 accepted capacity / fixed `36800` / 单 lifecycle 上得到：

~~~text
restore_cpu_hit_exact = true (16384)
restore_pairing_repair_enabled = true
restore_manager_source_sha_matched = true
restore_pairing_repair_applied = false
restore_pairing_repair_skip_reason = frozen_geometry_not_index_overflow
restore_num_external_tokens_at_alloc = 0
restore_num_new_tokens_at_alloc = 2
restore_delay_cache_blocks_at_alloc = false
restore_pending_present_at_update = false
restore_update_early_return_reason = num_external_zero
restore_entered_reqs_to_load = false
restore_load_scheduled = true
restore_load_request_completed = true
H2D workers / bytes = 8 / 1076510720
h2d_restore_mechanism_candidate = false
target_cpu_only_residency_observed = false
experimental_terminal = restore_request_completed
~~~

解释：

1. R14 **没有复现** R13 的 pairing IndexError 作为“最后一次 update”。
2. 摘要器当时只用 restore 的 **最后一次** allocate/update；R14 restore 成功后进入 decode，
   最后一次变成 `num_external=0 / num_new=2`，repair 因此正确 skip。
3. 同时出现了真实 H2D，但 `entered_reqs_to_load=false`（对最后一次 update），
   所以 **不能** 证明 H2D 走了 `_reqs_to_load` 规范路径。
4. mechanism candidate 还被 logical 128 vs physical FA 32 的 CPU-only 门卡住。

### R15 实际机制（多步 lineage + 路径归因）

本轮保留 R14 task-local repair（若某一步再次出现 IndexError 仍可接管），但主目标改为：

1. 记录 restore 上全部 allocate / update / load 步序
2. 区分 `delayed_external_prefill` 与 `decode_like`
3. 产出 `restore_step_lineage_primary_class` / `restore_h2d_path_class` /
   `restore_last_step_masks_earlier_delayed_external` 等有界字段
4. CPU-only mechanism 门接受 physical FA key unit
5. 不改 site-packages、不改 capacity/context

判别场景：

~~~text
A delayed_external_then_reqs_to_load -> via_reqs_to_load
B delayed_external_then_update_raise -> retained repair may apply
C load_scheduled_without_reqs_to_load_lineage
D last_step_masks_earlier_delayed_external=true
E decode_only_no_delayed_external
F physical FA gate + H2D worker completion
~~~

服务器必须在有界摘要里看到：

~~~text
restore_allocate_slots_observed_count
restore_update_observed_count
restore_load_scheduled_event_count
restore_alloc_step_classes
restore_last_alloc_step_class
restore_first_delayed_external_alloc_index
restore_first_delayed_external_num_external
restore_first_entered_reqs_to_load_update_index
restore_any_entered_reqs_to_load
restore_any_pairing_repair_applied
restore_any_update_raise_subclass
restore_last_step_masks_earlier_delayed_external
restore_step_lineage_primary_class
restore_h2d_path_class
restore_hit_to_load_gap_class
restore_load_scheduled
h2d_restore_mechanism_candidate
target_cpu_only_residency_observed
restore_step_lineage
physical_fa_cpu_only_gate
~~~

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
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725_run01
test ! -e "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"

# 可选：确认 R14 parent 仍在约定路径
# 默认 PARENT_ROOT=
#   ${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725_run01
# 若实际目录不同，导出：
# export P8_2_K1A_F1_R14_ROOT=/实际/R14/run01路径

bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r15_server_task.sh "${RESULT_DIR}"
~~~

该 driver 会：

1. 校验仓库合同与 R14 parent 9 个 SHA-256
2. stop keep-alive `0-7`
3. 执行唯一 fixed lifecycle（repair env 保留；step lineage 开启）
4. cleanup
5. 同卡恢复 keep-alive `0-7`
6. 写出有界候选包，并停下等待传输方式选择

## R14 parent 证据门（必须全部匹配）

父目录默认：

`server_local/p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725_run01`

~~~text
403b5fc007fbec07628319d46af50c4ecd6314eec39fda8f2fad39ed9189526b  grading_summary.json
78ba2fa1c27bdbb4a6512b852e1029d4acd9cf4fc2cdb127297f103bb26e7370  residency_gate_timeline.json
eab6d7161dfda5373bc5c20cfcb0efb38adbc6a10b7be29e7723fc2b944b15cd  h2d_trigger_summary.json
1266033f325bb8a1571dd46c563fd28feeb0753fb2b01439dc0830808f93c983  transfer_trace_summary.json
8b997ae5e0b8ddc1c9f13791888c27eebd4a6ae1b10a7f21de155908ae8dc8bf  logical_keyspace_probe_diagnostic_summary.json
5f0dcd40353412ea2d232332ba0aa9e3103c1a0bb35e6dbd4b01e2c4267b3d93  target_store_lineage_summary.json
459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862  repair_diagnostic_summary.json
aaf96cd771158866c72d4a2a6e3fa3f3242838c2cef0fe14dd42e043292f17ba  resource_recovery_summary.json
c739ce99cf7038f80cf0867787a2f850f7909e9306476a61956764abc926208a  candidate_manifest.server_local.json
~~~

父事实硬门槛：

~~~text
server_grade = red_p8_2_k1a_r5_f1_r14_h2d_evidence_incomplete
operational_grade = operational_recovery_clean
experimental_terminal = restore_request_completed
restore_hit_to_load_gap_class = load_scheduled
restore_pairing_repair_applied = false
restore_pairing_repair_skip_reason = frozen_geometry_not_index_overflow
restore_num_external_tokens_at_alloc = 0
restore_num_new_tokens_at_alloc = 2
restore_load_scheduled = true
restore_entered_reqs_to_load = false
h2d_worker_count = 8
h2d_bytes_total = 1076510720
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

`/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725_run01`

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
6c8302bd411b951493d2a4718afe38219220e133c2ab487f615db19f0d74c43c  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r15_server_task.sh
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

## 历史 marker（合同测试保留）

以下字符串必须继续出现在本文件中，供历史合同断言检索：

~~~text
"launch_copy_parameters"
"poll_method_owner"
AscendSimpleCPUOffloadConnector
KVConnectorFactory.get_connector_class_by_name
KVTransferConfig
NPUDmaCopyBackend
NPUDmaCopyBackend._copy_loop = observed_copy_loop
SimpleCPUOffloadNPUWorker
copy_backend_module.copy_blocks = observed_copy_blocks
copy_blocks_entered
copy_blocks_failed
copy_blocks_returned
copy_thread_exited
copy_thread_failed
copy_thread_started
device_copy_enqueued
inspect.signature
launch_copy_parameters
poll_method_owner
register_connector()
restore_first_pairing_overflow_group_index
restore_update_error_type
transfer_poll_entered
transfer_poll_returned

p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725
authorized_single_lifecycle_compress_aware_pairing_repair
P8.2-K1A-R5-F1-R14 task-local compress-aware pairing repair
P8.2-K1A-R5-F1-R14 compress-aware pairing repair
p8_2_k1a_r5_f1_r13_update_raise_geometry_2026_0724
authorized_single_lifecycle_update_raise_geometry
P8.2-K1A-R5-F1-R13 update_raised exception/geometry
p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724
authorized_single_lifecycle_hit_to_load_admission
P8.2-K1A-R5-F1-R12 CPU-hit → H2D-load 准入诊断
p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723
P8.2-K1A-R5-F1-R11 EAGLE-aware logical lookup lineage
restore_follower_with_hit_to_load_admission_lineage
restore_follower_with_update_raise_geometry_lineage
restore_follower
allocate_slots_observed
update_state_after_alloc_observed
restore_step_lineage
physical_fa_cpu_only_gate
restore_h2d_path_class
restore_step_lineage_primary_class
parent_f1_r12_task_id: p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724
parent_f1_r13_task_id: p8_2_k1a_r5_f1_r13_update_raise_geometry_2026_0724
parent_f1_r14_task_id: p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725
parent_grade: red_p8_2_k1a_r5_f1_r11_h2d_evidence_incomplete
~~~

## 仓库合同输入 SHA-256 清单

（服务器 driver 也会再核一次。）

~~~text
2f25960fa2300fa232074c01542f04d8accfebae3b84483c633aa2ca049420d0  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r15_restore_step_lineage_audit.yaml
28c9b9c48ce2752c3c2eabee93b4b3eba44481b586b9510e527514cf994b53ac  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r15_restore_step_lineage.yaml
fe10b56b3991e301b1e128842f51332aa46c4fa52844eb43e9fde539bbd7e4f3  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
29fa0b42abcb26753d3e65a893c2856f3a346c45a25320aed6eaf73ea506bfa2  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
fd5fd74fac8903c3e2e68bed7a4b9a5f599230f3257a4e721090a87655eb0e48  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py
ccbe0e4a87fd9fba6cfb8ceb5636cde98b08abed6d9f277fb45463d3393909ed  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
3488140e597852c2de38a69942f87263ff92ecc8dafc530fc479faca9ebebecb  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
9b193867f0ecdd4098985eb041937f9e73c4e421b8afce1f5253a5b51f036e23  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
bf4bb8d5b55be46b4d0d9b2ec735af21d860d3df109ecbeb4e49e169b19885a5  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r15_restore_step_lineage.py
bb3629ff05fa8175c07dbbfd3a7059fa2cf692ad13555a8f3b1a92a943ff0a6b  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r15_restore_step_lineage.sh
197ae0f516ed23c483c9c94ddd44e5da2de4aca70291a467ab6cb0f571393c98  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r15_server_task.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
27e27afddc242e329b47763b6005770ce5ab8e39f2c3da92230ae9c154644640  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r15_restore_step_lineage.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
~~~
