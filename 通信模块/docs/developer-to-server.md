# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R7 压力内逻辑键空间刷新

~~~text
task_id: p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_2026_0723
execution_mode: authorized_single_lifecycle_inflight_keyspace_refresh
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
post_abort_fresh_revalidation_required: true
runtime_pool_key_count_fixed: false
kv_connector: SimpleCPUOffloadConnector
all_relevant_kv_groups_required: true
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

### 先读结论：代码、参数和唯一入口都已写好，不要现场设计

F1-R6 的实验 RED、运维 GREEN：D2H 8/8、cleanup 与 0–7 同卡恢复成立，但只发送 warmup 和
target prime，pressure/abort/idle/restore 全部没有进入。原因是 target finish 回调发生在异步 D2H
刚提交时，只做了一次 runtime keyspace probe；外部控制器随后只重读静态 trace，却要求 keyspace
exact 后才允许启动下一条 pressure，而 pressure 正是下一次 scheduler activity，形成 circular wait。

这不是 accepted capacity 失败，也没有证明完整逻辑 128-block CPU-only 窗口不可形成。本轮保持：

- `128 CPU blocks/rank / 430604288 bytes/rank / 3444834304 bytes total`；
- fixed pressure context=`36800`；
- 一个 TP8 lifecycle、一个 pressure、零 retry、零 sweep；
- 不降低 128 目标，不改 context/capacity，不创建 run02。

F1-R7 已修好控制链：D2H complete 且 128 个 logical request-hash candidates 捕获后，唯一 fixed
pressure 必须启动；每个 exact single-request pressure progress 都重新调用 runtime coordinator 的
`find_longest_cache_hit(request_hashes, 16384)`。调用前后会恢复 coordinator 的
`num_uncached_common_prefix_tokens`，不留下观察副作用。暂时 unobservable、keyspace near miss 或 CPU
target loss 都继续观察到 exact trigger 或 pressure 正常结束，不得提前放弃。

只有以下条件同时成立才允许中止 pressure：

1. request-local progress 唯一且 scheduled request count=1；
2. 128 个逻辑候选完整，logical hit=`16384 tokens = 128 blocks`；
3. runtime 返回的全部非空 group pool keys 均在 CPU；
4. 同一批实际 pool keys 的 GPU matches=0；
5. 全部相关 KV groups eligible。

trigger 后必须确认 client exit 和 engine idle，并且只接受 abort wall-clock 时间戳之后产生的新鲜
`target_residency_snapshot` 重验 retained pool keys；没有新鲜 snapshot、窗口丢失或 group 不完整都不发
restore。通过后只发送一个 restore follower。

本轮唯一正式入口：

~~~text
tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_server_task.sh
~~~

它自动完成：`parent/repo/runtime preflight（keep-alive 仍运行） -> routine stop 0-7 -> one lifecycle ->
cleanup -> restore 0-7 -> real marker probe -> recovery record -> bounded finalize`。不要手工拆内部步骤，
不要直接运行 common mode/lifecycle，不要补代码，不要 retry。

## 0. 冻结 F1-R6 parent（停卡前自动验证）

parent 目录必须原位存在：

~~~text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723_run01
~~~

以下 SHA-256 必须精确匹配：

~~~text
6c25e21e022de71319eab54d954fa803eb8d725e197e30e517bf11c1a92091f5  grading_summary.json
982bdc2d191929e1b369d872262db4fe8be58af0fa6eb5fe1c42cef2b5ebc7d9  residency_gate_timeline.json
602bd438fdb2300032912b991c4b12d11e2222a9a9bf9b7fe49ec0e0172c8971  transfer_trace_summary.json
c0c64cbc9c81080e1e5604277e3b2f7843f9272958f48c7ddea237d04734abd3  resource_recovery_summary.json
103557a871bf863d8eb2ed221a85fe650fa9444aa86263702318cb591a01829f  candidate_manifest.server_local.json
~~~

必须接受并保持这些 parent 事实：

~~~text
server_grade=red_p8_2_k1a_r5_f1_r6_h2d_evidence_incomplete
operational_grade=operational_recovery_clean
experimental_terminal=target_capture_unobservable_before_pressure
request_count=2
http_transport_success_count=2
pressure_request_count_executed=0
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
red_p8_2_k1a_r5_f1_r6_h2d_evidence_incomplete
parent_task_id=p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722
direct_parent_task_id=p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723
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
historical_invalid_runner=tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use=3444834304
~~~

不得进入 K2；不得进入 P8.3-I1。

拉取后，以下 repo 文件 SHA-256 必须与本任务冻结值完全一致：

~~~text
ec10b9652995262d92341d065141d16f2cfb1796493f2e9b2dcd0d8e2634b4ee  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_audit.yaml
75fd5b1a1ee2e4293a425c7039aae1738fb196d852a846c76ae07104bb6badc9  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.yaml
9aa709e73851f7c812f345f25528fdbeb61fd7180b81a651f3fdc08aa4e578e0  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
277328eef16869c4290e6a8bf9d23673015689f9f4bf27506ce1b7b89591636c  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
3488140e597852c2de38a69942f87263ff92ecc8dafc530fc479faca9ebebecb  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
9b193867f0ecdd4098985eb041937f9e73c4e421b8afce1f5253a5b51f036e23  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh
91c9c4dc83d46067acc0405aa627044d1b899a90b5079db25bc50be2449c9258  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py
a01a5bd4cbcc3ce52ba027f9bbe6fa35c8bace48a94945436a669a16c18591aa  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.sh
5a2c07394dd05039e6aab3c85b3d2fab72472bd5261fb397d03a7289143057c2  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_server_task.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
bc8a18c8ed745a8dd1d6802ea9318f682cb731d570ae3350081769bf6a200ed3  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py
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
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r6_server_task.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_server_task.sh

P8_2_K1A_F1_R7_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_server_task.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r7_unused
~~~

audit-only 必须包含：

~~~text
task_id=p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_2026_0723
server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize
keep_alive_card_ids=0,1,2,3,4,5,6,7
keep_alive_marker_format=#card_id#
expected_keep_alive_marker_count=16
same_card_set_restore_on_every_exit=true
parent_f1_r6_prepressure_circular_wait=true
accepted_capacity_invalidated=false
pressure_before_keyspace_exact_allowed=1
pressure_progress_runtime_keyspace_refresh_required=true
post_abort_fresh_revalidation_required=true
logical_keyspace_diagnostics=1
pressure_context_tokens=36800
logical_target_block_count=128
current_pressure_role=pressure_01
current_restore_role=restore_follower
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
TASK_ID=p8_2_k1a_r5_f1_r7_inflight_keyspace_refresh_2026_0723
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}_run01"
cd "${REPO_ROOT}"
test ! -e "${RESULT_DIR}"

set +e
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r7_server_task.sh \
  "${RESULT_DIR}"
TASK_EXIT=$?
set -e
printf 'server_task_exit=%s\n' "${TASK_EXIT}"
printf 'result_dir=%s\n' "${RESULT_DIR}"
~~~

非零退出可能是预期实验 RED，不得因此重跑。driver 会先恢复 keep-alive、记录 recovery，再 finalize。

## 4. 精确判读，不要脑补

必须优先读取：

1. `resource_recovery_summary.json`：操作恢复真值；
2. `residency_gate_timeline.json`：pre-pressure admission、pressure、trigger/abort/idle/fresh post-abort gate；
3. `logical_keyspace_probe_diagnostic_summary.json`：每阶段 probe counts/reasons/error types/timestamps；
4. `h2d_trigger_summary.json` 与 `transfer_trace_summary.json`：D2H/CPU hit/load/H2D workers/bytes/completion；
5. `grading_summary.json`：experimental、operational、server 三个 grade 都要报。

逻辑键空间至少回报：

~~~text
initial_gate.decision
initial_gate.pressure_allowed
initial_gate.d2h_store_complete_before_pressure
initial_gate.request_hash_candidate_count
initial_gate.target_capture_cardinality_exact
initial_gate.target_keyspace_matchable
initial_gate.target_capture_exact
pressure_request_count_executed
pressure_progress_event_count
ambiguous_progress_event_count
exact_cpu_only_progress_event_count
logical_restore_match_tokens（best/exact）
target_pool_key_count（best/exact）
cpu_target_pool_key_match_count（best/exact）
gpu_target_pool_key_match_count（best/exact）
restore_group_count 与每组 bounded counts
probe_error_type_histogram
probe_reason_histogram
first/latest/first_exact probe timestamp_ns
post_abort_candidate_event_count
post_abort_revalidation_fresh
~~~

合法终态：

- exact trigger：按 trigger→abort→client exit→idle→fresh post-abort gate→restore 顺序报告 wall/monotonic
  时间戳，再报告 CPU hit/load、H2D workers/bytes/completion；只有全部 evidence exact 才是 candidate green。
- pressure 完整结束仍无 trigger：`pressure_completed_without_trigger`；只表示本次 fixed lifecycle 未观察到，
  不得宣称 accepted capacity 不可能形成 128-block CPU-only window。
- probe 始终报错或近失：报告具体 error type/histogram、best counts 和原始大 trace 的 server-local 路径；
  不得改代码、调参或重跑。
- fresh post-abort snapshot 不存在或窗口丢失：fail closed，不发 restore；不得复用中止前旧快照。
- request-local progress 歧义、请求失败、cleanup/recovery 不完整：精确 RED；运维与实验 grade 分开。

严禁在回包中包含 raw request/hash/block/token ID、生成内容、请求体、raw trace hash 或大日志。

## 5. cleanup、工作区与后续边界

最终必须确认：7000 无监听、无目标 vLLM 残留、八卡健康、keep-alive 0–7 恢复、tracked worktree clean。
大日志、request bodies、metrics、runtime 树与 raw trace 留服务器本地，只报告路径。禁止 server commit/push；
禁止第二 lifecycle、run02、retry、capacity/context 调整、sweep、K2、P8.3-I1、P8.4、P8.5 或 P9。

## 6. 有界结果包与传输选择

`result_transfer_authorized: true` 只表示完整有界包可被选择传输，不等于自动发送。总大小必须
`<=71680 bytes`，`payload_file_count_max=15`，`transfer_file_count_including_manifest_max=16`。必须包含可用时的：

~~~text
result_summary.md
request_summary.tsv
residency_gate_timeline.json
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
2. 五个 F1-R6 parent SHA 与 parent grade/terminal；
3. repo SHA、聚焦测试、py_compile、Bash、audit-only；
4. lifecycle/request counts，warmup/target/pressure/restore 每个 role 状态，retry=0；
5. initial admission 与 pressure 是否必定进入；
6. probe count/reason/error-type/timestamp/stage rows 和 best/exact logical/pool/group counts；
7. 若触发，完整 trigger→abort→client exit→idle→fresh post-abort gate→restore 顺序；否则精确 terminal；
8. D2H、CPU hit/load、H2D worker/bytes/pipeline/completion，以及 `experimental_grade`、
   `operational_grade` 与 task grade；
9. cleanup、7000、vLLM residual、八卡健康、实际 stopped/restored IDs、marker/recovery；
10. `result_summary.md` 绝对路径、完整有界 manifest、总 bytes、可选渠道与推荐渠道。

回报后暂停；`next_task_authorized: false`。
