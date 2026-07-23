# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R10 runtime cache-stamp lineage

~~~text
task_id: p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723
execution_mode: authorized_single_lifecycle_cache_stamp_lineage
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
accepted_cpu_blocks_per_rank_exact: 128
accepted_cpu_bytes_per_rank_exact: 430604288
accepted_cpu_bytes_total_exact: 3444834304
logical_target_block_count_exact: 128
logical_restore_match_tokens_exact: 16384
hash_block_size_tokens_exact: 128
pressure_context_tokens_exact: 36800
pressure_role_exact: pressure_01
target_cache_stamp_lineage_required: true
target_finish_block_table_used_for_lineage: false
runtime_sparse_block_mask_authoritative: true
target_lazy_store_schedule_attribution_required: true
target_store_all_worker_completion_attribution_required: true
physical_group_cpu_only_window_required_to_abort: true
logical_restore_window_required_before_restore: true
post_abort_fresh_revalidation_required: true
runtime_pool_key_count_fixed: false
physical_fa_key_count_fixed: false
kv_connector: SimpleCPUOffloadConnector
all_applicable_kv_groups_required: true
all_relevant_kv_groups_required: true
zero_cacheable_groups_count_as_complete: false
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

### 先读结论：R10 代码已经写完，服务器只需同步并执行

R9 的有效结果与限制：

- compressed full-attention group0 已正确得到 `effective=512 tokens`、
  `required=32`、`captured=32`；
- state group1 已正确得到 `effective=16384`、`required=1`、`captured=1`；
- groups2–5 是 `AscendSlidingWindowMLASpec`，R9 在 request finish 从 block table
  选取 dense 前缀时得到全 null，却仍按 `128/128/2048/512` dense positions
  要求 key capture；
- 所以 R9 在 pressure 前终止，`pressure_request_count_executed=0`；
- 该结果证明 R9 effective geometry 修复有效，但 finish-time sliding-window block
  table 不是恢复 lineage 的权威来源；
- 它没有执行 fixed pressure，不能否定 accepted 128 blocks/rank，也不能证明完整
  logical 128-block CPU-only 窗口无法形成。

冻结 vLLM `0decac0d96c42b49572498019f0a0e3600f50398` 的实际语义：

1. `SlidingWindowManager` 会移除窗口外的 request blocks 并用 null 补位；
2. `_cache_block_mask` 只允许未来 prefix lookup 能访问的 sparse positions 进入 cache；
3. `BlockPool.cache_full_blocks` 才会把 request block hash 加上 KV group ID，并写入
   GPU prefix-cache map；
4. lazy offload 只扫描 non-null、hashable GPU blocks。

R10 已在开发机把实质修复写入公共 observer：

1. 包装 GPU `BlockPool.cache_full_blocks`，先调用原方法；只有原方法成功返回后观察，
   不改变参数、返回值、异常、调度或 copy。
2. target prime 每次真实 cache stamp 后，按原 runtime `block_mask`、null 语义和
   实际 `block_size` 累计前 16384 tokens 的 group-wrapped keys。
3. 新 key 在 target 仍运行时立即进入 target lazy-store schedule/completion 与
   CPU/GPU eviction 归因，避免 finish 后才知道 key 而漏掉早期 D2H。
4. 每组记录 dense/scanned/cacheable/masked/null/captured counts 与 stamp call count。
5. 未观察或只扫描一部分的组保持 fail closed；完整扫描后 cacheable positions 确为
   0 的组才是 N/A，不能把 `0==0` 写成 CPU complete。
6. target finish 只 finalize 已累计的 stamp lineage，不再用 finish-time block IDs
   覆盖它。
7. logical 128 hash blocks 与 physical group keys 继续分单位；不要求 FA physical
   count 等于 128。
8. capture exact 后唯一 fixed 36800 pressure 必须执行。若真实 applicable keyspace
   大于 accepted 128-block capacity，也要通过 pressure 中逐组 residency/eviction 事实返回，
   不得在 capture 阶段提前放弃。

本轮没有降低或搜索目标：

~~~text
accepted CPU capacity = 128 blocks/rank = 430604288 bytes/rank
logical restore prefix = 16384 tokens = 128 hash blocks
fixed pressure context = 36800
formal lifecycle count = 1
pressure request count = 1
retry/sweep = 0
~~~

### 唯一正式入口

~~~text
tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_server_task.sh
~~~

driver 自动执行：

~~~text
R9 parent/repo/runtime preflight（keep-alive 仍运行）
-> routine stop 0-7
-> one accepted-capacity TP8 lifecycle
-> cleanup vLLM
-> restore exactly 0-7
-> keep-alive marker/NPU/port/process probe
-> resource recovery record
-> bounded finalize
~~~

不要手工拆内部步骤，不要直接运行 common lifecycle/mode，不要修改代码、dependency、
capacity、context 或 request，不要 retry，不要创建 run02。

## 0. 冻结 F1-R9 direct parent（停卡前自动验证）

parent 目录必须原位存在：

~~~text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723_run01
~~~

以下 SHA-256 必须精确匹配：

~~~text
04e87d5a5d3a1ada5dccf2925a5860cca4a6f83cbd7f5e0f925444eb4cba4f82  grading_summary.json
b918ec163720ce73e679db0be48cb48d87530200c199e93f1e0a9dedb79d8b4f  residency_gate_timeline.json
14e1a18b24947bd8b02c849b3eefa42fa1597f740bf54153d74b1c42cc6c087c  target_store_lineage_summary.json
aa94e2a9019749ec1fad01fc17fb210811c2af1c8d9f563c2e2d9295716ff8bb  transfer_trace_summary.json
65eb3136c608ef59c9def9a20a214e6cd6e835c565ab2fa1c1488b22b0a79ac1  resource_recovery_summary.json
8e08ee3d52ee2770f2795fe9588d420dedd5f9659663e1f5e8d22ec75ac2f2af  candidate_manifest.server_local.json
~~~

必须接受并保持这些 parent 事实：

~~~text
server_grade=red_p8_2_k1a_r5_f1_r9_target_store_lineage_unobservable_before_pressure
operational_grade=operational_recovery_clean
experimental_terminal=target_store_lineage_unobservable_before_pressure
request_count=2
successful_request_count=2
pressure_request_count_executed=0
required_restore_block_count=128
target_fa_key_count=32
target_store_key_count=33
target_store_scheduled_key_count_max=33
target_store_completed_key_count_max=0
restore_group_applicable_count=6
groups_2_to_5_captured_block_count=0
restore_sent=false
d2h_store_complete=true
d2h_worker_count=8
d2h_bytes_total=2206846976
h2d_worker_count=0
cleanup=clean
resource_recovery_exact=true
stopped_card_ids=0,1,2,3,4,5,6,7
restored_card_ids=0,1,2,3,4,5,6,7
accepted_capacity_invalidated=false
full_logical_128_block_cpu_only_window_disproven=false
~~~

R9 不得重跑。历史 R8/R7/R6/R5 只保留 lineage，不是本轮入口。不得进入 K2 或
P8.3-I1，也不得把历史 `CPU=64/GPU=0` 当作 R10 固定门槛。

以下是服务器助手必须保留的已关闭 lineage。它们只用于防止误改路线，不授权重跑；
其中 `restore_follower`、`request-local`、`CPU=64/GPU=0`、`#0#` 都是历史证据词，
不是 R10 的固定门槛或额外请求：

~~~text
不得进入 K2
不得进入 P8.3-I1
parent_task_id=p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722
parent_grade=red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
upstream_f1_r3_request_count=4
parent_successful_request_count=3
parent_d2h_store_complete=true
parent_h2d_worker_count=0
parent_cleanup=clean
parent_f1_r5_task=p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722
p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723
run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh
run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh
P8_2_K1A_F1_R7_SERVER_TASK_AUDIT_ONLY=1
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
required_restore_block_count_exact: 128
restore_follower
request-local
F1-R6 的实验 RED、运维 GREEN
logical_target_block_count=128
pressure_progress_runtime_keyspace_refresh_required=true
request_hash_candidate_count
logical_restore_match_tokens
target_pool_key_count
find_longest_cache_hit(request_hashes, 16384)
完整逻辑 128-block CPU-only 窗口
CPU=64/GPU=0
http_transport_success_count
experimental_grade
operational_grade
#0#
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
blocked_p6_3c_not_strict_single_variable
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p8_2_k1_frozen_stack_import_incompatible
red_p8_2_k1a_simple_cpu_offload_no_success_at_32_GiB_per_rank
red_p8_2_k1a_r1_geometry_probe_invalid
ready_p8_2_k1a_r2_allocator_capacity
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
red_p8_2_k1a_r5_l1_r1_cpu_target_lost
red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost
red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
red_p8_2_k1a_r5_f1_r6_h2d_evidence_incomplete
red_p8_2_k1a_r5_f1_r7_pressure_completed_without_trigger
red_p8_2_k1a_r5_f1_r8_target_store_lineage_unobservable_before_pressure
red_p8_2_k1a_r5_f1_r9_target_store_lineage_unobservable_before_pressure
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
~~~

R10 仍须在 accepted capacity 下用 runtime cache-stamp lineage 争取形成完整逻辑
128-block CPU-only 窗口；不得因为 SWA 的 finish-time null block table 再次在 pressure
之前提前放弃。

## 1. 同步 main 与离线门（此时不要停 keep-alive）

只允许 tracked-clean `main` 普通 fast-forward。`server_local/` 未跟踪结果不计入
tracked-clean。禁止 reset、stash、rebase、cherry-pick、服务器 commit 或 push。

~~~bash
set -euo pipefail
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"
git fetch origin main
git merge --ff-only origin/main
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -z "$(git status --porcelain --untracked-files=no)"
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git status --short --branch --untracked-files=no

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py \
  tests/inference_contracts/test_p8_current_plan_truth.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_server_task.sh

P8_2_K1A_F1_R10_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_server_task.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r10_unused
~~~

以下 16 个 direct contract input 的 SHA-256 必须在停卡前现场精确匹配：

~~~text
c1e79148b2afc32c90a76ef9a322125a2e56533202f03e9150d4b52363814b03  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r10_cache_stamp_lineage_audit.yaml
9173040ce2445dc43ab914b4fe7954a7503b80f198df5e6555faf539adea68fc  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r10_cache_stamp_lineage.yaml
0db27347d8fec7d7e190389147ffacecfd44b14b9d472d3565227e3c11ab1b2a  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
0a2cba3cd38f2c0d3841f2ecb0c6a1742646623b4fcc9bf0cfb58100d16290a3  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
3488140e597852c2de38a69942f87263ff92ecc8dafc530fc479faca9ebebecb  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
9b193867f0ecdd4098985eb041937f9e73c4e421b8afce1f5253a5b51f036e23  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
de635c2d880a546a1addf538f19f5f47af52fa35f3586a51a6c9bf3ba84e89ba  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py
8da9a6a8d7bcdfef0e194875948f51f4c2d22374b8ffb75fe524b8c401e6851e  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.sh
108a1ae10b8fdbc524a71e7dd0a5e2a037ddc7d95630424fba72332acc2468b8  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_server_task.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
f51bc92a0abe4c6e5e2f0a0193dd96358a54d7c8399ac8e4bcd654ffa727f4fe  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
~~~

audit-only 必须包含：

~~~text
task_id=p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723
execution_mode=authorized_single_lifecycle_cache_stamp_lineage
server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize
keep_alive_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_format=#card_id#
expected_keep_alive_marker_count=16
same_card_set_restore_on_every_exit=true
parent_f1_r9_runtime_geometry_red_accepted=true
accepted_capacity_invalidated=false
logical_target_block_count=128
target_lineage_capture_boundary=runtime_gpu_block_pool_cache_full_blocks
runtime_sparse_block_mask_is_authoritative=true
request_finish_null_block_table_used_for_lineage=false
unobserved_or_partial_group_fails_closed=true
fully_scanned_zero_cacheable_group_not_applicable=true
progressive_target_keys_feed_lazy_store_attribution=true
fixed_pressure_must_execute_after_cache_stamp_lineage=true
logical_restore_window_required_before_restore=true
pressure_context_tokens=36800
request_retry_count_exact=0
capacity_or_context_change_authorized=false
server_side_code_edit_authorized=false
resource_recovery_summary_always_recorded=true
finalize_after_recovery=true
result_transfer_authorized=true
automatic_transfer_allowed=false
next_task_authorized=false
~~~

任一离线门失败：keep-alive 保持运行，回报失败命令、退出码和不超过 200 行的
首尾摘要后停止；不得现场修代码继续。

## 2. keep-alive 是常规资源操作，由 driver 自动处理

本任务需要 0–7 八卡，可以直接停；停 keep-alive 本身不是事故。driver 使用：

~~~bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

两条命令的末尾数字是卡号，本轮必须保持同一个精确集合 `0 1 2 3 4 5 6 7`。
无论成功、实验 RED、失败、中断或提前退出，都必须恢复 exactly 0–7；也就是成功、失败、中断或提前退出
均不得遗漏恢复。最终报告：

~~~text
实际 stopped card IDs
实际 restored card IDs
restart exit code
16 个真实 #card_id# markers
marker card coverage
八卡健康
7000 端口
vLLM residual
keep_alive_restored_exact
~~~

## 3. 只执行一次正式 driver

结果目录必须是新的 run01：

~~~bash
set -euo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723_run01
test ! -e "${RESULT_DIR}"

bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r10_server_task.sh \
  "${RESULT_DIR}"
~~~

不要因为正式命令退出码非零而绕过 driver 的 cleanup/recovery/finalize。命令返回后直接
进入结果核验，不得 retry，不得创建 run02。

## 4. 本轮主线与精确判读

### 4.1 target cache-stamp lineage

必须报告：

~~~text
target_lineage_capture_basis=runtime_gpu_cache_stamp_sparse_mask_keys
target_cache_stamp_event_count
target_cache_stamp_observer_error_count
target_cache_stamp_observer_error_type_histogram
target_store_lineage_capture_exact
target_store_key_count
target_fa_key_count
target_fa_required_physical_key_count
target_logical_block_count=128
target_logical_coverage_tokens=16384
target_logical_coverage_exact
~~~

每个 KV group 必须报告完整有界行：

~~~text
group_index
kv_cache_spec_type
base_block_size_tokens
compress_ratio
coordinator_effective_block_size_tokens
coordinator_effective_geometry_source
cache_stamp_block_size_tokens
cache_block_size_matches_effective_geometry
dense_physical_position_count
scanned_position_count
cacheable_position_count
masked_position_count
null_position_count
cache_stamp_call_count
required_block_count
captured_block_count
group_applicable
capture_exact
logical_coverage_exact
effective_geometry_source
capture_basis
~~~

核心判定：

1. `scanned_position_count < dense_physical_position_count` 时不能把组标 N/A。
2. 完整扫描且 `cacheable_position_count=0` 才允许 `group_applicable=false`。
3. applicable group 必须 `captured=required` 才是 capture exact。
4. raw block IDs/hash values 不得进入有界包。
5. 如果 observer error count > 0 或 lineage incomplete，准确报告 group/error；不得改代码
   后重跑。
6. R10 不再要求 sliding-window dense positions 全部有 key。

### 4.2 pre-pressure 与唯一 fixed pressure

capture exact、128 logical candidates 与 D2H ready 后必须出现：

~~~text
pressure_request_count_executed=1
pressure_context_tokens=36800
request_retry_count=0
~~~

如果仍没有执行 pressure，必须返回阻断它的准确代码门、latest event 和逐组 stamp counts；
不能再写笼统的 “lineage unobservable”，不能现场修复，不得重跑。

pressure 中持续报告 target-specific：

~~~text
target_store_key_count
target_store_scheduled_key_count_max
target_store_completed_key_count_max
target_fa_required_physical_key_count
target_fa_store_scheduled_key_count_max
target_fa_store_completed_key_count_max
target_cpu_evicted_key_count
target_gpu_evicted_key_count
cpu_target_block_count_max
gpu_target_block_count_min
physical_cpu_only_window_event_count
logical_and_physical_window_event_count
restore_group_applicable_count
restore_groups_cpu_complete_count
restore_groups_gpu_absent_count
~~~

全局 D2H bytes 不能替代 target-specific completion/residency。

若真实 applicable target key count 大于 CPU pool 128：

- 仍执行完整唯一 pressure；
- 报每组 required/captured/CPU/GPU 与最接近窗口；
- 报 CPU/GPU eviction 顺序和 first/last best window；
- 只可说本 fixed lifecycle 未形成完整窗口；
- 未授权直接宣称唯一根因、永久不可能或擅自调容量。

### 4.3 trigger、abort、idle、restore

只在同一 `pressure_01` 仍 active 且以下全部成立时 trigger：

~~~text
request_local_progress_exact=true
scheduled_request_count=1
target_logical_coverage_exact=true
target_fa CPU complete
target_fa GPU absent
all applicable restore groups CPU complete
all applicable restore groups GPU absent
physical_target_window_exact=true
~~~

之后必须保持精确顺序：

~~~text
pressure start
-> trigger latched
-> abort requested
-> client exit observed
-> engine idle confirmed
-> post-abort fresh physical revalidation
-> logical 16384-token coordinator hit
-> one restore dispatched
-> restore completed
~~~

分支：

- pressure 自然结束且无窗口：不发 restore，保留
  `red_p8_2_k1a_r5_f1_r10_pressure_completed_without_trigger` 或更精确 terminal。
- 物理窗口后 abort，但窗口在 post-abort 消失：不发 restore。
- 物理窗口仍在但 logical 16K miss：不发 restore，明确
  `logical_restore_hit_incomplete_after_physical_window`。
- 只有 abort/exit/idle、新鲜物理窗口和 logical 16K hit 全部成立才发一次 restore。
- HTTP 200、Prefix Cache counter、accepted-token delta 或全局 D2H 不能单独证明 H2D。
- candidate green 必须还有 restore CPU hit/load、8-worker H2D schedule/copy/poll/completion。

## 5. cleanup 与有界结果包

最终必须满足并报告：

~~~text
cleanup_status.txt=clean
port 7000 free
vLLM residual process count=0
all eight NPUs healthy
stopped_card_ids=[0,1,2,3,4,5,6,7]
restored_card_ids=[0,1,2,3,4,5,6,7]
keep_alive_marker_count=16
keep_alive_marker_coverage_exact=true
keep_alive_restored_exact=true
tracked_worktree_clean=true
~~~

有界包最多 `71680 bytes`，只允许 driver manifest 白名单内的 operational metadata：

~~~text
cleanup_status.txt
connector_resolution_summary.json
grading_summary.json
h2d_trigger_summary.json
host_memory_summary.json
logical_keyspace_probe_diagnostic_summary.json
mtp_queue_health_summary.json
repair_diagnostic_summary.json
request_summary.tsv
residency_gate_timeline.json
resource_recovery_summary.json
result_summary.md
target_store_lineage_summary.json
transfer_trace_summary.json
candidate_manifest.server_local.json
~~~

raw vLLM log、raw metrics、request body、raw trace、request IDs、token IDs、generated
content、raw hash/block IDs 留服务器本地，只报告绝对路径，不进入有界包。

`payload_file_count`、`transfer_file_count` 和 `transfer_total_bytes` 必须从最终 manifest
实算，不要预填固定值。

`result_transfer_authorized:true` 只表示完整有界包具备候选资格。本任务没有选择
`email`、`upload-api` 或 `server-local`，不得自动发送或上传。先一次性报告完整
manifest（每文件 bytes/SHA-256/sensitivity）、result summary 绝对路径、三种可用方法
和一个推荐方法及理由，等待用户为完整范围选择单一渠道。

available result methods: `email / upload-api / server-local`

## 6. 一次性最终回报清单

完成后一次性回报以下 12 项，然后暂停：

1. `HEAD`、`origin/main`、ahead/behind、tracked-clean。
2. R9 parent 六个现场 SHA、parent grade/terminal 和 package integrity。
3. 聚焦 pytest、py_compile、Bash syntax、audit-only 与 16 个 repo input hash 结果。
4. lifecycle/request 总数，warmup/target/pressure/restore outcome，retry count。
5. cache-stamp 总事件/error 计数，逐组 dense/scanned/cacheable/masked/null/captured
   完整表，lineage capture basis/exact。
6. pressure 是否实际执行；若未执行，准确给出 gate、latest event 与逐组原因。
7. target store schedule/completion、CPU/GPU residency/eviction、最佳物理窗口与 logical
   window；全局 D2H 单列。
8. pressure start→trigger→abort→client exit→idle→post-abort gate→restore 的精确顺序
   和 monotonic 时间戳。
9. D2H/H2D worker、bytes、copy/poll/completion，restore CPU hit/load 与最终
   experimental/operational/server grade。
10. cleanup、7000、vLLM residual、八卡健康、实际停卡卡号、实际恢复卡号与恢复状态，
    并给出 16-marker 恢复状态。
11. `result_summary.md` 绝对路径、raw evidence 服务器路径。
12. 完整有界候选清单：逐文件 bytes、SHA-256、sensitivity、总文件数/bytes、全部
    校验结果、可用 `email/upload-api/server-local`、推荐方法及理由；不要执行传输。

报告后 `next_task_authorized=false`：不得继续 R10 run02、K2、P8.3-I1 或任何新任务。
