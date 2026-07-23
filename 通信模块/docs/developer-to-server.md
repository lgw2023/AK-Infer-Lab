# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R8 target-store lineage

~~~text
task_id: p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723
execution_mode: authorized_single_lifecycle_target_store_lineage
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
required_restore_block_count_exact: 128
block_size_tokens_exact: 128
restore_match_tokens_exact: 16384
pressure_context_tokens_exact: 36800
pre_pressure_runtime_keyspace_exact_required: false
pressure_progress_runtime_keyspace_refresh_required: true
target_store_lineage_capture_required: true
target_fa_key_count_exact: 128
target_lazy_store_schedule_attribution_required: true
target_store_all_worker_completion_attribution_required: true
physical_cpu_only_window_required_to_abort: true
logical_restore_window_required_before_restore: true
post_abort_fresh_revalidation_required: true
runtime_pool_key_count_fixed: false
kv_connector: SimpleCPUOffloadConnector
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

### 先读结论：代码、参数、判读和唯一入口都已写好，不要现场设计或修改

F1-R7 已真正执行一个固定 pressure，但没有触发。该结果不是 accepted capacity 失败：

- pressure 已执行一次并正常完成，控制链不再是 F1-R6 的 pre-pressure circular wait；
- observer 做了 134 次 logical probe，但 exact=0、logical hit max=0、target pool key max=0；
- 全局 D2H 8/8、`4467519488` bytes 只证明全局 lazy store 工作，不证明 target 的 128 个块已落 CPU；
- 旧 observer 只有 coordinator 首次命中后才认识 target pool key，因此无法把 lazy-store schedule/completion
  归因到 target，也无法可靠识别 target eviction；
- 旧 `restore_group_complete=6/6` 中五个 group 是零 key，属于 vacuous complete，不能作为 restore eligibility；
- 所以 F1-R7 只说明旧观测合同在这次 fixed lifecycle 没看到 trigger，不能证明完整 128-block CPU-only
  窗口无法形成。

换言之，完整逻辑 128-block CPU-only 窗口仍是开放目标，未被 parent 证伪。

F1-R6 的实验 RED、运维 GREEN也继续保留：其 task
`p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723` 是 circular-wait parent，不是当前入口；
F1-R7 的历史 audit 环境名 `P8_2_K1A_F1_R7_SERVER_TASK_AUDIT_ONLY=1` 只作 lineage 记录，不得执行。

本轮保留 accepted capacity，不降低目标、不轻易放弃：

- `128 CPU blocks/rank / 430604288 bytes/rank / 3444834304 bytes total`；
- fixed pressure context=`36800`；
- 一个 TP8 lifecycle、一个 `pressure_01`、零 retry、零 sweep；
- 不改 context/capacity，不创建 run02；
- near miss、短暂 unobservable 或 target CPU eviction 都继续观察到 pressure 自然结束，不提前停；
- 即使本轮仍 RED，也必须保留 128-block accepted capacity，只返回精确 lineage attribution 供开发机继续写代码。

### 本轮实质机制（服务器只执行，不再补实现）

代码已按 vLLM `v0.22.1` 的真实调用顺序写好：

1. `SimpleCPUOffloadScheduler.request_finished_all_groups` 收到所有 KV group 的 GPU block IDs。本轮 wrapper
   在调用原方法、释放 target 之前捕获 group-wrapped `block_hash`。
2. full-attention group 由 `fa_gidx` 确认，必须精确捕获 128 key；其它 group 按自己的有效 block size
   捕获。零 key group 标为 `not_applicable`，不再计入 CPU complete 或 GPU absent。
3. `_prepare_lazy_store_specs` 原方法返回后，用实际 CPU block IDs 的 `block_hash` 与 retained target keys
   求交，记录 target-specific scheduled counts；不改变任何调度参数或返回值。
4. `_process_store_event` 原方法完成后才记录 target-specific completed counts。此时所有 D2H worker 已完成，
   且原方法已经执行 CPU cache insert；因此不是“只提交了 copy”的假 completion。
5. `BlockPool._maybe_evict_cached_block` 识别 retained target key，分别累计 CPU/GPU target eviction。
6. 每个 exact single-request pressure progress 直接按 retained target keys 读取 CPU/GPU 物理驻留：
   full-attention 必须 `CPU=128/GPU=0`，全部 applicable groups 必须 CPU complete 且 GPU absent。
7. 上述物理窗口一出现就中止 pressure，不要求当场 coordinator logical hit，以免再次错过短窗口。
8. client exit 与 engine idle 后，必须用 abort 之后的新鲜 snapshot 重验物理窗口，并要求 coordinator
   只读调用 `find_longest_cache_hit(request_hashes, 16384)`；只有“物理窗口 + logical 16K hit”同时成立
   才发一个 `restore_follower`。
9. 若物理窗口成立但 coordinator 仍不接受，精确终态为
   `logical_restore_hit_incomplete_after_physical_window`，不发 restore；这会把实际问题从“有没有落 CPU”
   收紧到“为什么 coordinator 不接受这批物理 key”。

raw hash、block ID 只保留在 scheduler 进程内；有界结果只写 counts、booleans、timestamps 和 attribution。
不要把 HTTP 200、`accepted_token_delta`、Prefix Cache 命中、全局 D2H bytes 中任何一个单独写成 H2D restore。

本轮唯一正式入口：

~~~text
tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh
~~~

它自动完成：
`parent/repo/runtime preflight（keep-alive 仍运行） -> routine stop 0-7 -> one lifecycle -> cleanup ->
restore 0-7 -> real marker probe -> recovery record -> bounded finalize`。不要手工拆内部步骤，不要直接运行
common mode/lifecycle，不要补代码，不要 retry。

## 0. 冻结 F1-R7 direct parent（停卡前自动验证）

parent 目录必须原位存在：

~~~text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_2026_0723_run01
~~~

以下 SHA-256 必须精确匹配：

~~~text
fbe61292041d7902f7177cd9c71712a6aafa9b6bd5fe675dac803e89cdf9e023  grading_summary.json
e8e1f3b50e68a98cbd2a6673ee7cb15051b3659f6e757d9e2ef1c85d4fb16fe7  residency_gate_timeline.json
d06592e9609f29bf445de78f44de3a7ae2c45b4616ee9e7f8d010baadf93f560  transfer_trace_summary.json
c97a190c840e1b175ccd7ae66500c8f964ed27a1dd773390a5904745189efb2a  logical_keyspace_probe_diagnostic_summary.json
7999be2de5f4a90f99ecd7ab518ee92a297512e48e3f1f043ed503bd9de4f00c  resource_recovery_summary.json
ab04a826c07eb5ccaeed54048b3a74c086cc2c7b277fd6ac16d92e20a87528b7  candidate_manifest.server_local.json
~~~

必须接受并保持这些 parent 事实：

~~~text
server_grade=red_p8_2_k1a_r5_f1_r7_pressure_completed_without_trigger
operational_grade=operational_recovery_clean
experimental_terminal=pressure_completed_without_trigger
request_count=3
successful_request_count=3
pressure_request_count_executed=1
pressure_progress_event_count=41
logical_probe_event_count=134
logical_exact_probe_event_count=0
logical_restore_match_tokens_max=0
target_pool_key_count_max=0
restore_sent=false
d2h_store_complete=true
d2h_worker_count=8
d2h_bytes_total=4467519488
h2d_worker_count=0
cleanup=clean
resource_recovery_exact=true
stopped_card_ids=0,1,2,3,4,5,6,7
restored_card_ids=0,1,2,3,4,5,6,7
accepted_capacity_invalidated=false
full_logical_128_block_cpu_only_window_disproven=false
~~~

本轮只继承下列已关闭边界，不授权重跑；列出它们是为了防止服务器助手误改路线：

~~~text
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
blocked_p6_3c_not_strict_single_variable
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p8_2_k1_frozen_stack_import_incompatible
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
ready_p8_2_k1a_r2_allocator_capacity
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost
red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
red_p8_2_k1a_r5_f1_r6_h2d_evidence_incomplete
red_p8_2_k1a_r5_f1_r7_pressure_completed_without_trigger
parent_task_id=p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722
direct_parent_task_id=p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_2026_0723
parent_f1_r5_task=p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722
parent_grade=red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
upstream_f1_r3_request_count=4
parent_successful_request_count=3
parent_d2h_store_complete=true
parent_h2d_worker_count=0
parent_cleanup=clean
historical_single_group_window=CPU=64/GPU=0
current_exact_trigger=CPU=128/GPU=0
pressure_status_on_trigger=aborted_on_trigger
pressure_progress_runtime_keyspace_refresh_required=true
http_transport_success_count=3
historical_invalid_runner=tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
~~~

不得进入 K2；不得进入 P8.3-I1。

拉取后，以下 16 个 direct repo input 的 SHA-256 必须与本任务冻结值完全一致：

~~~text
380942132195374cece03c8ac295e80b084e6c37c89d0e658b07318b9ea6fa4f  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r8_target_store_lineage_audit.yaml
95a987f2668bcb14dd9616c1d155bc16c94133a4236be84a4ce1beaa24b1eeca  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r8_target_store_lineage.yaml
aad1595620d8ed7a7af5cd62754d30762d0ab4b9630988f52350f6879ab899c1  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
9f6dd26edeae8074f7e4ba2d024db0107c9ddf7f2b08baf07088f7df10a1de2f  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
3488140e597852c2de38a69942f87263ff92ecc8dafc530fc479faca9ebebecb  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
9b193867f0ecdd4098985eb041937f9e73c4e421b8afce1f5253a5b51f036e23  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
3ab1c2d19d9a8979adb7a0b71da0472c93e06957db9b85556a459b7e440a7199  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.py
955549bfa5262c2473d67e40f494257c6baa7350d42ba8b369d50a764415a9cc  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.sh
6fe981b5df18b6365313874ed4b66ece8d47c37cb17801da6f134aaa4b16c3ac  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
0da0d58b06d17b85bf8506caa8e847f86ed5d190191ba8f356fc1fb2811e5f8f  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
~~~

## 1. 同步 main 与离线门（此时不要停 keep-alive）

只允许 tracked-clean `main` 普通 fast-forward。`server_local/` 未跟踪结果不计入 tracked-clean。禁止
reset、stash、rebase、cherry-pick、server commit 或 push。

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
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_target_store_lineage.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh

P8_2_K1A_F1_R8_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r8_unused
~~~

audit-only 必须包含：

~~~text
task_id=p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723
execution_mode=authorized_single_lifecycle_target_store_lineage
server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize
keep_alive_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_format=#card_id#
expected_keep_alive_marker_count=16
same_card_set_restore_on_every_exit=true
parent_f1_r7_pressure_executed_without_trigger=true
accepted_capacity_invalidated=false
target_group_wrapped_keys_captured_before_finish=true
target_lazy_store_schedule_completion_attributed=true
zero_key_groups_counted_complete=false
physical_cpu_only_trigger_required=true
logical_restore_window_required_before_restore=true
pressure_before_keyspace_exact_allowed=1
logical_keyspace_diagnostics=1
pressure_context_tokens=36800
logical_target_block_count=128
request_retry_count_exact=0
capacity_or_context_change_authorized=false
resource_recovery_summary_always_recorded=true
finalize_after_recovery=true
result_transfer_authorized=true
automatic_transfer_allowed=false
next_task_authorized=false
~~~

任一离线门失败：keep-alive 保持运行，回报失败命令、退出码和不超过 200 行的首尾摘要后停止；不得现场
修代码继续。

## 2. keep-alive 是常规资源操作，由 driver 自动处理

本任务需要 0–7 八卡，可以直接停，停卡本身不是事故。末尾数字是卡号；本轮 driver 固定使用这两条：

~~~bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

无论成功、失败、中断或提前退出，必须恢复完全相同的 0–7，并回报 stopped/restored IDs、restart exit、
`#0#`…`#7#` coverage、marker count=`16` 和 restoration status，也就是实际停卡卡号、实际恢复卡号与恢复状态。
不要另开终端手工停/启；driver trap 统一收尾。只有外部硬杀导致 trap 未运行时，才允许只做恢复和健康检查，
不得补跑实验。

## 3. 唯一一次正式执行

`run01` 必须不存在；存在就停止，不覆盖、不删除、不改名、不建 run02。

~~~bash
set -euo pipefail
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p8_2_k1a_r5_f1_r8_target_store_lineage_2026_0723
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}_run01"
cd "${REPO_ROOT}"
test ! -e "${RESULT_DIR}"

set +e
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r8_server_task.sh \
  "${RESULT_DIR}"
TASK_EXIT=$?
set -e
printf 'server_task_exit=%s\n' "${TASK_EXIT}"
printf 'result_dir=%s\n' "${RESULT_DIR}"
~~~

非零退出可能是预期实验 RED，不得因此重跑。driver 会先恢复 keep-alive、记录 recovery，再 finalize。

## 4. 精确判读：先看 target lineage，再看逻辑接受，最后才看 H2D

必须按顺序读取：

1. `resource_recovery_summary.json`：操作恢复真值；
2. `target_store_lineage_summary.json`：target capture/schedule/completion/eviction/physical residency 真值；
3. `residency_gate_timeline.json`：admission、pressure、trigger/abort/idle/fresh post-abort gate；
4. `logical_keyspace_probe_diagnostic_summary.json`：coordinator logical lookup；
5. `h2d_trigger_summary.json` 与 `transfer_trace_summary.json`：D2H/CPU hit/load/H2D；
6. `grading_summary.json`：experimental、operational、server 三个 grade。

target lineage 至少回报：

~~~text
target_store_lineage_capture_event_count
target_store_lineage_capture_exact
target_store_key_count
target_fa_key_count
target_fa_capture_exact
restore_group_count
restore_group_applicable_count
每个 group 的 bounded geometry/capture counts
target_store_schedule_event_count
target_store_completion_event_count
target_store_scheduled_key_count_max
target_store_completed_key_count_max
target_fa_store_scheduled_key_count_max
target_fa_store_completed_key_count_max
target_cpu_evicted_key_count
target_gpu_evicted_key_count
cpu_target_block_count_max
gpu_target_block_count_min
physical_cpu_only_window_event_count
logical_and_physical_window_event_count
first_physical_cpu_only_window_timestamp_ns
first_logical_and_physical_window_timestamp_ns
target_lineage_attribution
~~~

逻辑与控制链至少回报：

~~~text
initial_gate.decision
initial_gate.pressure_allowed
initial_gate.d2h_store_complete_before_pressure
initial_gate.request_hash_candidate_count
initial_gate.target_store_lineage_capture_exact
initial_gate.target_fa_key_count
initial_gate.target_store_key_count
pressure_request_count_executed
pressure_progress_event_count
ambiguous_progress_event_count
exact_cpu_only_progress_event_count
logical_restore_match_tokens（best/exact）
coordinator_returned_pool_key_count（best/exact）
coordinator_cpu_pool_key_match_count（best/exact）
coordinator_gpu_pool_key_match_count（best/exact）
probe_error_type_histogram
probe_reason_histogram
first/latest/first_exact probe timestamp_ns
post_abort_candidate_event_count
post_abort_revalidation_fresh
post_abort logical_restore_window_exact
~~~

合法终态和精确含义：

- `target_store_lineage_unobservable_before_pressure`：finish 前无法精确捕获 FA=128 或 applicable group
  geometry；不得启动 pressure，不得补代码或改容量。
- `pressure_completed_without_trigger`：pressure 完整结束但物理窗口未出现。必须结合
  `target_lineage_attribution` 区分：
  `target_keys_never_scheduled_for_d2h`、`target_d2h_store_completion_incomplete`、
  `full_attention_target_d2h_incomplete`、`target_cpu_evicted_before_complete_cpu_only_window` 或
  `target_d2h_complete_without_cpu_only_window`。任何一种都不能宣称 accepted capacity 不可能形成窗口。
- 物理 `CPU=128/GPU=0` 出现：必须先报告精确 timestamp，再报告 abort requested、client exit、engine idle
  与 fresh gate；不要因为当时 logical hit=0 否认这个物理窗口。
- `logical_restore_hit_incomplete_after_physical_window`：物理窗口成立，但 abort 后 coordinator 仍未给
  16K logical hit；fail closed，不发 restore。这是有效实质结果，不是“测试代码红色”。
- restore 已发送：还必须证明 CPU hit/load、8-worker H2D、bytes、all-worker completion 与 async copy
  pipeline；HTTP 200 或 Prefix Cache delta 不能替代这些证据。
- request-local progress 歧义、请求失败、cleanup/recovery 不完整：精确 RED；运维与实验 grade 分开。

严禁在有界回包中包含 raw request/hash/block/token ID、生成内容、请求体、raw trace hash 或大日志。

## 5. cleanup、工作区与后续边界

最终必须确认：7000 无监听、无目标 vLLM 残留、八卡健康、keep-alive 0–7 恢复、tracked worktree clean。
大日志、request bodies、metrics、runtime 树与 raw trace 留服务器本地，只报告路径。禁止 server commit/push；
禁止第二 lifecycle、run02、retry、capacity/context 调整、sweep、K2、P8.3-I1、P8.4、P8.5 或 P9。

## 6. 有界结果包与传输选择

`result_transfer_authorized: true` 只表示完整有界包可被选择传输，不等于自动发送。总大小必须
`<=71680 bytes`，`payload_file_count_max=15`，`transfer_file_count_including_manifest_max=16`。
本轮正常应为最多 14 个 payload 加 1 个 manifest：

~~~text
result_summary.md
request_summary.tsv
residency_gate_timeline.json
target_store_lineage_summary.json
logical_keyspace_probe_diagnostic_summary.json
h2d_trigger_summary.json
transfer_trace_summary.json
connector_resolution_summary.json
mtp_queue_health_summary.json
repair_diagnostic_summary.json
host_memory_summary.json
grading_summary.json
cleanup_status.txt
resource_recovery_summary.json
candidate_manifest.server_local.json
~~~

先一次性回报 result summary 绝对路径与完整候选清单：逐文件 bytes、SHA-256、sensitivity、总文件数、总字节、
available methods=`email / upload-api / server-local`，并推荐一个方法及理由。然后暂停，等待用户对完整 scope
明确选择一个方法；不得先发 status email，不得自动传输，不得把 `result_transfer_authorized:true` 当渠道选择，
失败后也不得自动换渠道。用户选择 `server-local` 时只保留原位并报告路径。

## 7. 最终回报清单（一次性完整回报后暂停）

1. HEAD、origin/main、ahead/behind、tracked-clean；
2. 六个 F1-R7 parent SHA 与 parent grade/terminal；
3. 16 个 repo SHA、聚焦测试、py_compile、Bash、audit-only；
4. lifecycle/request counts，warmup/target/pressure/restore 每个 role 状态，retry=0；
5. initial admission、target capture geometry、pressure 是否进入；
6. target schedule/completion/CPU-GPU eviction/物理 residency 的全套 bounded counts 与 attribution；
7. logical probe count/reason/error/timestamps 和 best/exact coordinator counts；
8. 若触发，完整 physical window→abort→client exit→idle→fresh physical+logical gate→restore 顺序；
   否则精确 terminal；
9. D2H、CPU hit/load、H2D worker/bytes/pipeline/completion，以及 `experimental_grade`、
   `operational_grade` 与 task grade；
10. cleanup、7000、vLLM residual、八卡健康、实际 stopped/restored IDs、marker/recovery；
11. raw 大产物的 server-local 路径，确认未进入有界包；
12. `result_summary.md` 绝对路径、完整有界 manifest、总 bytes、可选渠道与推荐渠道。

回报后暂停；`next_task_authorized: false`。
