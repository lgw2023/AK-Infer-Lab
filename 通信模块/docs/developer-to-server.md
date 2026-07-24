# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R11 EAGLE-aware logical lookup lineage

~~~text
task_id: p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723
execution_mode: authorized_single_lifecycle_eagle_lookup_lineage
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
per_attention_group_lookup_lineage_required: true
logical_probe_source_independent_from_target_lineage_required: true
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

## 先读结论：R11 的代码已经写好，服务器只同步、审计、执行、回报

### R10 已经证明的事实

R10 不是 accepted capacity 失败。它已经在唯一 fixed `36800` pressure 中得到：

~~~text
logical target = 16384 tokens = 128 request hash blocks
runtime physical representation = 40 group-wrapped pool keys
target_store captured/scheduled/completed = 40/40/40
all 40 target GPU keys evicted
target CPU evictions = 0
all 6 applicable groups CPU complete and GPU absent
physical CPU-only window events = 8
post-abort physical window exact = true
~~~

逻辑 `128 hash blocks` 与 runtime `40 physical group-wrapped keys` 是不同单位。
**不要把 40 个 physical keys 写成缺少 88 个 logical blocks**。R10 已经证明 accepted
`128 blocks/rank / 430604288 bytes/rank` 可以形成 16K 目标的完整物理表示。

R10 唯一未通过的是 observer 的逻辑 lookup：

~~~text
find_longest_cache_hit(request_hashes, 16384) -> 0 accepted tokens
coordinator_returned_pool_key_count = 1
restore_sent = false
h2d_worker_count = 0
~~~

这里的 `coordinator_returned_pool_key_count=1` 也不能解释为只找到 1/128 个物理块；
它是 coordinator 在失败 lookup 返回结构中的 pool-key count，不是 logical target
cardinality。

### R11 修复的实际机制

冻结 vLLM `0decac0d96c42b49572498019f0a0e3600f50398` 的
`HybridKVCacheCoordinator.find_longest_cache_hit` 对 EAGLE group 的合同是：

1. 从当前候选长度再多查一个该 attention-group block；
2. 确认额外 block 命中；
3. 再把最后一个 block pop 掉，返回可复用前缀。

R10 把 coordinator 的硬上限传成 accepted target 本身 `16384`。当当前候选已经是
16384 时：

~~~text
min(curr_hit_length + eagle_group_block_size, max_cache_hit_length)
= min(16384 + 16384, 16384)
= 16384
~~~

必要的 lookahead 被硬上限截掉；对于 effective block size 为 16384 的 EAGLE group，
单个命中 block 随后又被 pop，结果可能从有效的 16K 被观察成 0。

R11 不改变 accepted target、capacity、各请求 context、依赖或调度。它做两项彼此配套的
修复：

1. observe-only probe 改成两次同窗口对照；
2. target 与 restore follower 的 32768-token 输入改成完全相同，使真实 restore 请求
   同时携带 16K accepted target 和后续 16K EAGLE lookahead。

~~~text
target context = restore context = 32768
target/restore shared prefix = 32768
accepted restore target = 16384
legacy capped probe horizon = 16384
runtime-derived EAGLE lookahead = max effective block size of live EAGLE attention groups
R10 expected geometry lookahead = 16384
R10 expected EAGLE-aware probe horizon = 16384 + 16384 = 32768
accepted logical hit = min(raw coordinator hit, 16384)
logical target satisfied iff raw coordinator hit >= 16384
~~~

`32768` 不是硬编码的“精确 EAGLE 增量”；observer 使用 conservative two-effective-block
ceiling：`accepted_target + max(effective_block_size)`，并受已有 target request hashes
可用长度上限约束。`16384 + 16384 = 32768` 只是根据 R10 已回传的 effective geometry
得到的本轮预期值，必须由 R11 runtime 字段复核。

冻结源码合同（零 NPU / source-only）：

~~~text
vllm_commit=0decac0d96c42b49572498019f0a0e3600f50398
ascend_commit=5f6faa0cb8830f667266f3b8121cd1383606f2a1
SimpleCPUOffloadScheduler.path=vllm/v1/simple_kv_offload/manager.py
constructor_use_eagle=false
cpu_coordinator_factory=get_kv_cache_coordinator
frozen_eagle_inner_delta=spec.block_size
manager_eagle_propagation_ok_does_not_imply_cpu_coordinator_eagle=true
~~~

因此 R11 不预先宣称“已知 EAGLE boundary false negative”为唯一根因；本轮实质是
CPU coordinator lookup horizon + per-attention-group lineage discrimination。runtime 必须
回报 live `cpu_coordinator_use_eagle`、`eagle_attn_group_indices`、
`eagle_lookahead_delta_tokens` / `required` / `sufficient`。

R11 同时修复 R10 的诊断丢失：`logical_probe_source` 与 cache-stamp
`target_capture_source` 分开保存，不能再因 lineage merge 把逻辑 probe 从
`logical_keyspace_probe_diagnostic_summary.json` 过滤掉。

observe-only probe 会对实际 manager class 做**同步、临时、try/finally 恢复**的
wrapper，记录 bounded per-attention-group lineage：

~~~text
attention_group_index / kv_cache_group_ids / spec / manager
candidate_in_tokens / manager_max_length_tokens
base/effective block size / alignment
use_eagle
eagle_lookahead_delta_tokens
eagle_lookahead_required_tokens
eagle_lookahead_sufficient
eagle_lookahead_requested
eagle_lookahead_suppressed_by_horizon
eagle_inner_readable_blocks
returned_block_count / returned_hit_tokens
candidate_reduced
~~~

共享范围从 R10 的 16K 扩成 32K 是读取合同修复，不是把 accepted target 从 16K 提高到
32K，也不改变 target/restore 的 32768 context。因两次输入有意相同，本轮明确允许
target/restore request body hash 相同；warmup/pressure 仍必须隔离。

observer 不记录 raw hash、block ID、request ID、token ID 或生成内容；临时 lineage wrapper
不改变 lookup 参数、返回值、异常、pool、调度或 D2H/H2D copy。

### 不要做的事

- 不要再移植或修改 `#11107` manager propagation；R10 已证明
  `manager_eagle_propagation_ok=true`、`eagle_manager_count_max=2`。
- 不要改服务器代码、vLLM、vLLM-Ascend、CANN、patch、模型或 dependency。
- 不要把 probe horizon 或 32K shared prefix 误写成 accepted target、capacity、context
  或请求长度变更；也不要把 32768 写成精确 EAGLE 增量。
- 不要假设 CPU coordinator 已启用 EAGLE；以 runtime `constructor_use_eagle=false`
  与 live fields 为准。
- 不要改 `128 blocks/rank`、`430604288 bytes/rank`、fixed `36800`。
- 不要 retry、sweep、搜索 context/capacity，不创建 run02。
- 不要并发发送 restore；只有 pressure 已中止、client exit、engine idle、fresh physical
  gate 与 logical gate 都成立后，controller 才能发送唯一 restore。
- 不要手工拆内部步骤或 common lifecycle，不要临场写 Python/patch，不要根据颜色标签
  自行改路线。

以下冻结 lineage 词只用于让历史合同检查与服务器助手理解上下文，不是额外入口或授权。
R10 父任务已闭合为 physical-window-complete / logical-hit-incomplete；本轮标题是
`P8.2-K1A-R5-F1-R11 EAGLE-aware logical lookup lineage`，父证据仍保留
`P8.2-K1A-R5-F1-R10 runtime cache-stamp lineage` 字样仅作 lineage。

R10 不得重跑。历史 R9/R8/R7/R6/R5 只保留 lineage，不是本轮入口。不得进入 K2 或
P8.3-I1，也不得把历史 `CPU=64/GPU=0` 当作 R11 固定门槛。

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
expected_keep_alive_marker_count=16
resource_recovery_summary.json
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
red_p8_2_k1a_r5_f1_r10_logical_restore_hit_incomplete_after_physical_window
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
payload_file_count
~~~

这些历史 runner 不得执行。finalizer 对成功、实验 RED、失败、中断或提前退出都必须
cleanup 并恢复；换言之，成功、失败、中断或提前退出均不得遗留 vLLM 或停着 keep-alive。

## 0. 同步与 tracked-clean

执行代码库：

~~~bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
git fetch --prune origin
git fetch origin main
git switch main
git merge --ff-only origin/main
git pull --ff-only origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
~~~

必须满足：

~~~text
HEAD == origin/main
ahead/behind == 0 0
tracked worktree clean
~~~

服务器只 pull，不 commit、不 push、不改 tracked files。已有未跟踪 `server_local/` 结果可保留。
若 tracked 不干净、无法 fast-forward 或 HEAD 不等于 origin/main，停在零 NPU 状态回报，
不要 stash/reset/checkout 覆盖现场。

## 1. 冻结 F1-R10 direct parent（停卡前由 driver 自动验证）

parent 必须原位存在：

~~~text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723_run01
~~~

以下 SHA-256 必须精确匹配：

~~~text
75747dfbad514b7da6b925a3fc586313858ebecf7237c6294d3350f39e63b268  grading_summary.json
1fe69786191371be0017b6942dacd1117172cf7b1f1b4120fedcbe842fc4b889  residency_gate_timeline.json
23e9d7e6ebee999eb1ad7e299fa160d6dd8737b9bbf31665c9282d07aa763cb6  target_store_lineage_summary.json
efb7d4ae48b37fcbf6b619bd477a90337b3d67e0793dfd0c9b75e7332f2c3e17  logical_keyspace_probe_diagnostic_summary.json
e829673f21eab07af6f6a50d6a9bc9e25c8668561bade8b0a083fdcc3d5b3d77  transfer_trace_summary.json
459d0f9aa71587d5359a23aabdb44741d4b41195c6cd56a8e8775fc7d1ae1862  repair_diagnostic_summary.json
02715a7e142a53be15f8ff236c253fc12a233ce582e057998e529e53c148ded8  resource_recovery_summary.json
5067ac9f22f70eec8caf807189fb3f8f9ef6cab3c78588c53ee1d822268078a1  candidate_manifest.server_local.json
~~~

driver 还会验证：

~~~text
R10 grade = logical_restore_hit_incomplete_after_physical_window
operational = operational_recovery_clean
request_count = 3
pressure_count = 1
physical window events = 8
target lineage exact = true
target store = 40/40/40
target GPU eviction = 40
target CPU eviction = 0
post-abort physical exact = true
post-abort logical hit = 0
R10 bounded logical diagnostic probe_event_count = 0
D2H = 8 workers / 2206846976 bytes / complete
H2D workers = 0
manager EAGLE propagation = true
LCM = 16384
cleanup/resource recovery = exact
stopped/restored cards = 0-7 / 0-7
~~~

若 parent 缺失、hash 或字段不符，停在零 NPU 状态，回报 mismatch；不得重跑 R10。

## 2. 停卡规则是常规资源操作

本任务需要 TP8，允许按需停止 0–7 的低优先级 keep-alive。停 keep-alive 不是严重事件；
需要时正常停，任务完成后恢复即可。driver 会在 preflight 后执行 stop，并在 success、
failure、interruption、early exit 的 cleanup/finalizer 中恢复同一集合。
也就是成功、失败、中断或提前退出都必须恢复完全相同的卡集。

必须显式保留这两个命令合同：

~~~bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

不要在 driver 外重复停卡或恢复。最终必须回报：

~~~text
stopped_card_ids
restored_card_ids
same_card_set_restored
keep_alive_restored_exact
restart_exit_code
0-7 marker coverage
八卡健康
~~~

## 3. 先做零 NPU audit-only

~~~bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723_run01
RESULT_DIR="${RESULT_ROOT}"
test ! -e "${RESULT_ROOT}"
test ! -e "${RESULT_DIR}"

P8_2_K1A_F1_R11_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_server_task.sh \
  "${RESULT_ROOT}"
~~~

audit-only 必须输出并匹配：

~~~text
task_id=p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723
execution_mode=authorized_single_lifecycle_eagle_lookup_lineage
parent_f1_r10_physical_window_exact=true
accepted_capacity_invalidated=false
accepted_restore_match_tokens=16384
restore_shared_prefix_tokens=32768
eagle_aware_logical_lookup=1
legacy_capped_probe_retained=true
per_attention_group_lookup_lineage_required=true
logical_probe_source_independent_from_target_lineage=true
pressure_context_tokens=36800
formal_model_lifecycle_count_exact=1
pressure_request_count_exact=1
request_retry_count_exact=0
runtime_dependency_mutation_authorized=false
result_transfer_authorized=true
transfer_method_selected=false
automatic_transfer_allowed=false
next_task_authorized=false
~~~

还需执行仓库自检：

~~~bash
python3 -m pytest -q \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.py

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_server_task.sh
~~~

以下 16 个 direct contract input 的 SHA-256 必须在停卡前现场精确匹配：

~~~text
5563fdb5b36bb9c0782ea74891a6d2fca3404ef4c7b90b94688cf92429ec1c5c  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_audit.yaml
2df8bee68a4d2755e9c3a002ebad91b68ed5419d118a0a1cf209170ccd94ba9c  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.yaml
9ab0d17e1281feb923115068cb990e1c68b971bc843209d3d8b6575631e1b19d  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
013654bfb418d48c3e3511997aed479a1b04fa57ee3f7423e1b66ce32c16e0ff  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
3488140e597852c2de38a69942f87263ff92ecc8dafc530fc479faca9ebebecb  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
9b193867f0ecdd4098985eb041937f9e73c4e421b8afce1f5253a5b51f036e23  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
9f9da5b8fd24dbcdba2cdfb43da26bf19bc3eda09e76d98eec4c3bc426532b84  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.py
1f7f1bde59fe1eea9634d2738cae6f31b83b4939758844f9f72d273cb76fd676  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.sh
a0935afed780a569b7e774bfd6639af968fa0e61edddcf30b1c530354e7a01f2  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_server_task.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
eab083dae8b0b43a17f8547aa7535845a00befe84e518ff3780581a28660c516  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
~~~

任何一项失败都停在零 NPU 状态回报；不要临场修代码。

## 4. 唯一正式入口

只有 audit/preflight 全通过后执行：

~~~bash
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723_run01

bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r11_server_task.sh \
  "${RESULT_ROOT}"
~~~

driver 自动执行：

~~~text
Git/repo/R10 parent/runtime preflight（keep-alive 仍运行）
-> routine stop exactly 0-7
-> one accepted-capacity TP8 lifecycle
-> warmup
-> target prime + exact runtime cache-stamp lineage（与 follower 共享完整 32768 输入）
-> one fixed 36800 pressure
-> abort on exact physical CPU-only window
-> client exit + engine idle
-> fresh physical revalidation
-> legacy 16K capped probe + runtime-derived EAGLE-aware probe
-> conditional single restore only if accepted logical hit >= 16384
-> observe real H2D copy path if restore is dispatched
-> cleanup vLLM
-> restore exactly 0-7
-> keep-alive marker/NPU/port/process probe
-> bounded finalize
~~~

不要直接运行 common lifecycle/mode，不要手工构造请求。只允许这一个 lifecycle、一个
pressure、零 retry/sweep。即使发生 failure，也不要创建 run02。

## 5. 本轮最重要的判定

### A. 最强预期：证明旧 gate 是 EAGLE 边界假阴性

必须同时满足：

~~~text
physical_target_window_exact = true
legacy_capped_logical_restore_match_tokens < 16384
logical_lookup_probe_horizon_tokens = runtime-derived value
logical_lookup_horizon_exact = true
raw_logical_restore_match_tokens >= 16384
logical_restore_match_tokens = 16384
legacy_capped_false_negative_candidate = true
logical_restore_window_exact = true
~~~

这时允许发送唯一 restore。仍只有观察到真实：

~~~text
restore_load_scheduled
h2d worker count = 8
h2d bytes > 0
copy/poll/enqueue/completion all workers
restore CPU hit >= 16384
~~~

才能写 “H2D restore mechanism candidate”。HTTP 200、prefix-cache hit 或
accepted-token delta 不能替代 H2D copy 证据。不要仅凭一次对照写唯一根因。

### B. EAGLE-aware 仍为 0 或不足 16K

不发送 restore。必须从实际 `logical_lookup_iteration_rows` 回报：

~~~text
derived lookahead and horizon
attention-group contract rows
每次 lookup 的 candidate/max/use_eagle/returned
首个 candidate_reduced attention group
首个 returned 0 attention group
对应 spec/manager/effective block/alignment
manager_use_eagle_flags
是否仍发生 horizon suppression
~~~

这会给出下一轮应处理的精确 manager/group。不能据此宣称 accepted capacity 失败；
R10 的完整 40-key physical window 仍成立。

### C. EAGLE-aware 达到 16K，但 restore 未形成真实 H2D

把 logical gate 与 restore/H2D 分开：

~~~text
logical gate false-negative candidate = supported
restore dispatch/order = report exact
H2D mechanism = incomplete
~~~

不要把“逻辑资格已通过”和“H2D copy 已证明”混成一个结论。

### D. 本轮没有复现 physical window

完整看完唯一 pressure，不提前放弃。报告 cache-stamp lineage、D2H、每组 CPU/GPU、
eviction、进度和 endpoint。不得改变 capacity/context 或重跑，不得推翻 R10 已完成的
physical-window 事实。

## 6. 必须保留的有界逻辑诊断

`logical_keyspace_probe_diagnostic_summary.json` 本轮不能再是错误的 0-event 空摘要。
至少必须含：

~~~text
probe_event_count
pressure_probe_event_count
exact_probe_event_count
legacy_capped_false_negative_candidate_count
legacy_capped_logical_restore_match_tokens_max
raw_logical_restore_match_tokens_max
logical_restore_match_tokens_max
logical_lookup_lookahead_tokens_max
logical_lookup_probe_horizon_tokens_max
group_lineage_observable_event_count
best_probe_first_reduction_attention_group_index/spec
best_probe_first_zero_attention_group_index/spec
best_probe_group_contract_rows
best_probe_lookup_iteration_rows
stage_rows
~~~

若 runtime manager method 形态使 classmethod lineage 不可包装，实验不得崩溃；
`logical_lookup_group_lineage_error_type` 必须有界回报，仍完成同一 pressure watcher，
不修改依赖、不临场修补。

## 7. cleanup 与恢复

最终无论成功、RED、异常、中断或 early exit，都必须满足：

~~~text
cleanup_status.txt = clean
port 7000 free
vLLM residual process count = 0
all eight NPUs healthy
stopped cards = 0-7
restored cards = 0-7
same card set restored = true
keep-alive restored exact = true
tracked worktree clean = true
~~~

cleanup/recovery 不成立时，实验机制结论与运维结论分开报告；优先恢复资源，不重跑模型。

## 8. 完整最终回报（一次性，按此顺序）

1. `HEAD`、`origin/main`、ahead/behind、tracked-clean。
2. R10 parent 8 个文件逐项现场 SHA-256 与 parent grade/operational grade。
3. repo file hashes、4 个定向 pytest 文件、3 个 py_compile、2 个 `bash -n`、
   audit-only 完整字段。
4. lifecycle/request 数：formal lifecycle、warmup、target、pressure、restore、
   successful、intentional abort、retry。
5. R10 物理事实在 R11 的复现：logical 128、physical key total、逐组 capture/store/
   CPU/GPU/eviction、physical-window event count。
6. legacy 与 EAGLE-aware 同窗口对照：available、lookahead、desired horizon、actual
   horizon、target/restore LCP、legacy raw/accepted、aware raw/accepted、
   false-negative candidate。
7. bounded attention-group contract rows 与 lookup iteration rows；首个 reduction/zero
   group、spec、manager、effective geometry、EAGLE flags。
8. pressure start → physical trigger → abort requested → client exit → engine idle →
   fresh revalidation → logical decision → restore dispatch/completion 的 monotonic 顺序。
9. D2H 与 H2D：worker/bytes/copy/poll/enqueue/completion、restore CPU hit/load；明确
   是否真实 H2D，不以 HTTP/prefix-cache 代替。
10. experimental grade、operational grade、claim boundary；明确 accepted capacity
    是否被否定（本轮默认否）、unique cause 是否证明（本轮默认否）。
11. cleanup、7000、vLLM residual、八卡健康、stopped/restored card sets、keep-alive。
12. `result_summary.md` 绝对路径、raw evidence 目录、完整 bounded candidate manifest：
    每文件名/bytes/SHA-256/sensitivity、payload total、含 manifest 的完整总数/总 bytes、
    available methods、推荐方法及理由；然后暂停等待用户选择。

报告必须直接给数值和字段，不要只写“测试通过”“结果是红/绿”。服务器助手不需要决定
下一步，只需忠实执行当前代码并把上述证据完整返回。

## 9. 小载荷结果包与传输边界

所有 raw vLLM logs、trace shards、request bodies、metrics、raw hashes、block IDs、
request IDs、token IDs、生成内容留在服务器：

~~~text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723_run01/
~~~

有界候选包：

~~~text
每个邮件正文 <= 70KB
每个附件 <= 70KB
完整候选 transfer total <= 71680 bytes
payload <= 15 files
including manifest <= 16 files
sensitivity = bounded_operational_metadata_no_content_or_token_ids
~~~

`result_transfer_authorized: true` 只表示完整有界包具备候选资格，不代表自动发送，也不选择
渠道。正式运行后先在服务器本地生成并核验完整 manifest，然后一次性回报：

~~~text
result_summary.md absolute path
all candidate filenames
each bytes / SHA-256 / sensitivity
payload total
transfer total including manifest
available methods = email / upload-api / server-local
one recommended method and reason
~~~

随后暂停，等待用户对**完整 scope** 明确选择一个 `email` / `upload-api` /
`server-local`。不要先发状态邮件，不要自动 upload，不要把早先选择沿用到本轮，不要在失败
后自动换渠道。

## 10. 终止边界

完成一次正式 run01、cleanup、恢复、bounded finalize 和完整回报后：

~~~text
next_task_authorized=false
~~~

暂停等待开发机复核。不得执行 R11 run02、R12、K2、P8.3-I1 或任何其他 NPU 任务。
