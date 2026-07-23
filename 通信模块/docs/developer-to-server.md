# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R9 runtime effective-group geometry

~~~text
task_id: p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723
execution_mode: authorized_single_lifecycle_effective_group_geometry
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
physical_fa_key_count_fixed: false
runtime_effective_group_geometry_required: true
pressure_context_tokens_exact: 36800
pressure_role_exact: pressure_01
target_store_lineage_capture_required: true
target_lazy_store_schedule_attribution_required: true
target_store_all_worker_completion_attribution_required: true
physical_group_cpu_only_window_required_to_abort: true
logical_restore_window_required_before_restore: true
post_abort_fresh_revalidation_required: true
runtime_pool_key_count_fixed: false
kv_connector: SimpleCPUOffloadConnector
all_applicable_kv_groups_required: true
all_relevant_kv_groups_required: true
zero_key_groups_count_as_complete: false
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

### 先读结论：R9 已把 R8 的实际代码问题修完，服务器只执行

R8 的 RED 不是 accepted capacity 失败，也不是“完整 logical 128-block CPU-only 窗口无法形成”：

- R8 只完成 warmup 与 target prime，pressure count=`0`；
- target finish 捕获 group0 `65 provided / 64 hashable`、group1 `2 hashable`，并归因 66 个
  target group-wrapped keys；
- R8 observer 把 `16384 / 128 = 128 logical hash blocks` 错当成 FA physical key count；
- 它只计算 `spec.block_size * cp_world_size`，漏掉 runtime Ascend coordinator 的
  `compress_ratio`，所以在 pressure 前以 `64/128` fail closed；
- target completion=`0` 发生在 pressure 未进入、后续 scheduler activity 被截断的 lifecycle，
  不能证明 mover 永远不会完成；
- R8 cleanup、八卡健康与 0–7 keep-alive 同卡恢复均 clean。

R9 已在代码里完成以下实质修复，服务器助手不要再设计或补实现：

1. target finish 时优先调用 runtime CPU coordinator
   `_get_effective_block_size(kv_cache_spec)`。
2. 每组 effective size 采用 runtime 真实语义：base block size、DCP×PCP、`compress_ratio`；
   只有 runtime method 不可见时才用同源码语义的 observe-only fallback。
3. logical 16K/128 hash-block 目标按
   `physical_required = 16384 / runtime_effective_block_size` 映射到每组。
4. capture exact 表示 logical 16K 在全部 applicable group 的真实 physical keys 上覆盖精确；
   不再要求 FA physical count 必须等于 128。
5. pre-pressure gate 要求 128 个逻辑候选、runtime geometry/capture exact、target lineage 可追踪和
   D2H ready。满足后唯一 fixed 36800 pressure 必须执行。
6. pressure 中逐 scheduler progress 读取 target-specific CPU/GPU residency。只有
   logical coverage exact、全部 applicable group CPU complete/GPU absent、单请求 progress exact
   才触发 abort。
7. abort 后等待 client exit 与 engine idle，再以 abort 之后的新鲜 snapshot 重验物理窗口；
   还必须获得 coordinator logical 16384-token hit，才发送唯一 restore follower。
8. target D2H completion 的期望值使用 runtime FA physical-required count，不再与 logical 128
   作错误比较。

本轮没有降低目标：仍是 accepted `128 CPU blocks/rank / 430604288 bytes/rank`、logical
`16384 tokens = 128 hash blocks`、fixed pressure `36800`。physical FA key 数只是同一逻辑覆盖
在压缩 group 上的真实表示，不是把目标从 128 降到 32/64。

### 唯一正式入口

~~~text
tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_server_task.sh
~~~

它自动执行：

~~~text
parent/repo/runtime preflight（keep-alive 仍运行）
-> routine stop 0-7
-> one accepted-capacity TP8 lifecycle
-> cleanup vLLM
-> restore exactly 0-7
-> real keep-alive marker/NPU/port/process probe
-> resource recovery record
-> bounded finalize
~~~

不要手工拆内部步骤，不要直接运行 common lifecycle/mode，不要修改代码、dependency、capacity、
context 或 request，不要 retry，不要创建 run02。

## 0. 冻结 F1-R8 direct parent（停卡前自动验证）

parent 目录必须原位存在：

~~~text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723_run01
~~~

以下 SHA-256 必须精确匹配：

~~~text
896bfcd9d8722d398b5ee34a5730839b5c6028fd9f23d176d8cb3fb8dcb1f8a7  grading_summary.json
7e2752bf178d7fa37ea5de29c4fa65f5ac7495f4dcd93a4ad0fc18c337080884  residency_gate_timeline.json
0c38987f4c9469989d64fb9713fb6d3558df56105e179efc0068466f199d155b  target_store_lineage_summary.json
2898cf42a8f44462220466a10192edfbf45775282e9060aa6829228dfe5f1876  transfer_trace_summary.json
e0ebfe458b8d9129465d872c0bb213e7d034bcacd3d5d468bfb4048040c27f4c  resource_recovery_summary.json
a8b1154213cbac77d1cd5892dedcb726f881168d31e7cb43edf4a7df962e393c  candidate_manifest.server_local.json
~~~

必须接受并保持这些 parent 事实：

~~~text
server_grade=red_p8_2_k1a_r5_f1_r8_target_store_lineage_unobservable_before_pressure
operational_grade=operational_recovery_clean
experimental_terminal=target_store_lineage_unobservable_before_pressure
request_count=2
successful_request_count=2
pressure_request_count_executed=0
required_restore_block_count=128
target_fa_key_count=64
target_store_key_count=66
target_store_scheduled_key_count_max=66
target_store_completed_key_count_max=0
observer_reported_fa_effective_block_size_tokens=128
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

R8 不得重跑。R7/R6/R5 等历史 parent 只保留 lineage，不是本轮入口。

以下已关闭 lineage 必须保留，列出它们只是防止服务器助手误改路线，不授权重跑：

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
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
~~~

这些是只读 lineage 字段；其中历史 `required_restore_block_count_exact: 128` 指 logical hash
blocks，不是 R9 的 physical FA key count。`CPU=64/GPU=0` 是旧轮次已观察到的 physical
snapshot，`#0#` 是历史 keep-alive marker 示例；二者都不是 R9 固定门槛。R9 仍须在 accepted
capacity 下用 runtime effective geometry 证明完整逻辑 128-block CPU-only 窗口。

## 1. 同步 main 与离线门（此时不要停 keep-alive）

只允许 tracked-clean `main` 普通 fast-forward。`server_local/` 未跟踪结果不计入 tracked-clean。
禁止 reset、stash、rebase、cherry-pick、服务器 commit 或 push。

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
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.py \
  tests/inference_contracts/test_p8_current_plan_truth.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_server_task.sh

P8_2_K1A_F1_R9_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_server_task.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r9_unused
~~~

以下 16 个 direct contract input 的 SHA-256 必须在停卡前现场精确匹配：

~~~text
dbddb4abd40d2ab965257ebcb81a69008d0e17694c29533469b813fa26ee91a4  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r9_effective_group_geometry_audit.yaml
c1fff191dd1bf23b9fed64e36423c3cf522a1652d57e6c0cd4e16f8690eeeaa5  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r9_effective_group_geometry.yaml
7093324b30135cb598c05f6f782fa5467abf160f47323527daafedaeb0f61de9  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
0a2cba3cd38f2c0d3841f2ecb0c6a1742646623b4fcc9bf0cfb58100d16290a3  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
3488140e597852c2de38a69942f87263ff92ecc8dafc530fc479faca9ebebecb  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
9b193867f0ecdd4098985eb041937f9e73c4e421b8afce1f5253a5b51f036e23  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
45fee1b8bd841dcaaca7e3ccd66f2618c7b183a533f97d6a8f0e82dcaf77bbd9  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.py
6273bae6748a120f8c3b192250555e98591eb2d78bcf96204280369026c74ee6  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.sh
845ae76093a2544faf38c21a39268d6b88dc0187da0a421f77276be1140f56c1  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_server_task.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
b3ef8726db9ca29c36bd810ce872175a2719a5077ece4918685093bef4e9dcb1  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r9_effective_group_geometry.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
~~~

audit-only 必须包含：

~~~text
task_id=p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723
execution_mode=authorized_single_lifecycle_effective_group_geometry
server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize
keep_alive_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_format=#card_id#
expected_keep_alive_marker_count=16
same_card_set_restore_on_every_exit=true
parent_f1_r8_geometry_contract_red_accepted=true
accepted_capacity_invalidated=false
logical_target_block_count=128
runtime_effective_group_geometry_required=true
physical_fa_key_count_fixed=false
target_group_wrapped_keys_captured_before_finish=true
target_lazy_store_schedule_completion_attributed=true
zero_key_groups_counted_complete=false
fixed_pressure_must_execute_after_geometry_capture=true
logical_restore_window_required_before_restore=true
pressure_context_tokens=36800
request_retry_count_exact=0
capacity_or_context_change_authorized=false
resource_recovery_summary_always_recorded=true
finalize_after_recovery=true
result_transfer_authorized=true
automatic_transfer_allowed=false
next_task_authorized=false
~~~

任一离线门失败：keep-alive 保持运行，回报失败命令、退出码和不超过 200 行的首尾摘要后停止；
不得现场修代码继续。

## 2. keep-alive 是常规资源操作，由 driver 自动处理

本任务需要 0–7 八卡，可以直接停；停 keep-alive 本身不是事故。driver 使用：
两条命令的末尾数字是卡号，本轮必须保持同一个精确集合 `0 1 2 3 4 5 6 7`。

~~~bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

无论成功、失败、中断或提前退出（包括实验 RED），都必须恢复 exactly 0–7，并报告 stopped/restored card IDs、
16 个真实 `#card_id#` markers、八卡健康、7000 端口与 vLLM residual。
等价地说：成功、实验 RED、失败、中断或提前退出，均不得跳过同卡恢复。
最终回报必须明确列出实际停卡卡号、实际恢复卡号与恢复状态。

## 3. 只执行一次正式 driver

结果目录必须是新的 run01：

~~~bash
set -euo pipefail
cd /data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r9_effective_group_geometry_2026_0723_run01
test ! -e "${RESULT_DIR}"

bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r9_server_task.sh \
  "${RESULT_DIR}"
~~~

不要因为正式命令退出码非零而绕过 driver 的 cleanup/recovery/finalize。driver 已负责把实验 RED 与运维恢复
分开；命令返回后直接进入结果核验，不得 retry。

## 4. 本轮必须观察和判读的主线

### 4.1 geometry capture

必须报告每个 KV group 的：

~~~text
group_index
kv_cache_spec_type
base_block_size_tokens
cp_world_size
compress_ratio
effective_block_size_tokens
effective_geometry_source
restore_match_tokens_required
physical_key_count_required
provided_block_id_count
selected_block_id_count
hashable_block_count
group_applicable
capture_exact
logical_coverage_exact
~~~

核心不变量：

~~~text
target_logical_block_count=128
target_logical_coverage_tokens=16384
target_logical_coverage_exact=true
target_fa_key_count=target_fa_required_physical_key_count
target_fa_required_physical_key_count 不要求等于 128
all applicable groups capture_exact=true
zero-key groups are N/A, not vacuous complete
~~~

如果 geometry/capture exact 后仍未执行 pressure，终态必须明确指出新的代码/运行门，不能再次用
`FA physical != 128` 阻断，也不能擅自修复后重跑。

### 4.2 fixed pressure 与 target lineage

必须实际出现：

~~~text
pressure_request_count_executed=1
pressure_context_tokens=36800
request_retry_count=0
~~~

持续报告 target-specific：

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
~~~

全局 D2H bytes 不能替代 target-specific completion/residency。

### 4.3 abort / restore

- pressure 未形成完整物理窗口：允许自然完成，grade 为
  `red_p8_2_k1a_r5_f1_r9_pressure_completed_without_trigger` 或更精确 terminal；不发 restore。
- physical window 出现：必须在 pressure 仍 active 时 abort，并确认 client exit、engine idle。
- abort 后物理窗口丢失：不发 restore。
- abort 后物理窗口仍在但 logical 16K miss：终态
  `logical_restore_hit_incomplete_after_physical_window`，不发 restore。
- 只有新鲜物理窗口与 logical 16K hit 同时成立才发一次 restore。
- HTTP 200、Prefix Cache counter、accepted token、全局 D2H 中任何一个都不能单独证明 H2D。
- candidate green 还必须有 8-worker H2D schedule/copy/poll/completion 与 target CPU hit/load 的完整证据。

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

raw vLLM log、raw metrics、request body、raw trace、request IDs、token IDs、generated content、raw hash/block IDs
留服务器本地，只报告绝对路径，不进入有界包。

`payload_file_count`、`transfer_file_count` 和 `transfer_total_bytes` 必须从最终白名单 manifest
实算并回报；不要预填一个与真实终态不一致的固定文件数。

`result_transfer_authorized:true` 只表示完整有界包具备候选资格。本任务没有选择 `email`、`upload-api`
或 `server-local`，不得自动发送或上传。先一次性报告完整 manifest（每文件 bytes/SHA-256/sensitivity）、
result summary 绝对路径、可用三种方法和推荐方法，等待用户为完整范围选择一个渠道。

available result methods: `email / upload-api / server-local`

## 6. 一次性最终回报清单

完成后一次性回报以下 12 项，然后暂停：

1. `HEAD`、`origin/main`、ahead/behind、tracked-clean。
2. R8 parent 六个现场 SHA 与 parent grade/terminal。
3. 聚焦 pytest、py_compile、Bash syntax、audit-only 与 repo input hash 结果。
4. lifecycle/request 总数，warmup/target/pressure/restore 各自 outcome，retry count。
5. 每组 runtime effective geometry 完整有界表；明确 logical 128 与 physical counts 的关系。
6. pressure 是否实际执行；若未执行，准确给出 gate 和代码/运行证据。
7. target store schedule/completion、CPU/GPU residency/eviction、首个物理窗口和 logical window。
8. pressure start→trigger→abort→client exit→idle→post-abort gate→restore 的精确顺序与时间戳。
9. D2H/H2D worker、bytes、copy/poll/completion，restore CPU hit/load 与最终 experimental/server grade。
10. cleanup、7000、vLLM residual、八卡健康、停卡集合、恢复集合与 16-marker 恢复状态。
11. `result_summary.md` 绝对路径、raw evidence 服务器路径。
12. 完整有界候选清单：逐文件 bytes、SHA-256、sensitivity、总文件数/bytes、全部校验结果、可用
    `email/upload-api/server-local`、推荐方法及理由；不要执行传输。

报告后 `next_task_authorized=false`：不得继续 R9 run02、K2、P8.3-I1 或任何新任务。
