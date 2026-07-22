# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R5 有效 128-block 恢复合同闭合

~~~text
task_id: p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722
execution_mode: authorized_single_lifecycle_effective_restore_contract
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
effective_target_block_count_exact: 128
required_restore_block_count_exact: 128
block_size_tokens_exact: 128
restore_match_tokens_exact: 16384
pressure_context_tokens_exact: 36800
all_relevant_kv_groups_required: true
full_request_window_watch_required: true
stop_on_first_near_miss: false
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

### 先读结论，不要自行推断

F1-R4 是无效运行合同证据，不是 accepted capacity 失败证据。外层 F1-R4 明确导出
`P8_2_K1A_H2D_TARGET_BLOCK_COUNT=128`，但旧的通用 mode 脚本在真正启动 vLLM 前又无条件
覆盖成 `64`。因此 F1-R4 看到的 `CPU=64/GPU=0`、零 trigger 和 pressure 自然完成都是
旧合同失真下的结果，不得写成“128-block CPU-only 窗口在 accepted capacity 下不可能”。

F1-R4 还暴露了两个报告问题：第 0 组为 `65 non-null / 64 hashable`，旧代码把末尾无 hash
partial block 错当成 restore lookup 必需块；同时 `resource_recovery_summary.json` 没有生成，导致
cleanup/recovery grade 覆盖了真正的实验终态。F1-R5 已在代码中修复这些问题，服务器助手
不需要再现场改代码、拼命令或补文件。

本轮的唯一执行入口是：

~~~text
tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh
~~~

它自动执行 `parent/effective preflight（keep-alive 运行）-> stop keep-alive -> one lifecycle -> vLLM cleanup -> restore same cards ->
record resource recovery -> finalize bounded package`。不要手工分步重现 runner 内部流程，不要跳过
driver 直接运行 mode runner，不要重跑 run02。

## 0. F1-R4 parent 证据与本轮边界

服务器 parent 目录必须原位存在：

~~~text
/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_2026_0722_run01
~~~

四个 parent 文件必须精确匹配：

~~~text
b84df30aed30cd50374cd9c8a18ce5ae6bc878643dbf4955f32602ac6d416cba  grading_summary.json
4b47a03bcda1cdc32beab382a22e03cd1ea3753b5bca21924cdfe64e56f3e47a  h2d_trigger_summary.json
234b3799f77035902cb0b39bdfd62a3dabc918adf46864ba22aed75cf15d6164  residency_gate_timeline.json
a69a426b8ae323129ea9ecf20ea5410b24da7b61ff062102ccb44006b4215bba  candidate_manifest.server_local.json
~~~

已接受 parent 事实：

~~~text
parent_server_grade=red_p8_2_k1a_r5_f1_r4_cleanup_or_recovery_incomplete
parent_experimental_terminal=pressure_completed_without_trigger
parent_formal_model_lifecycle_count=1
parent_request_count=3
parent_successful_request_count=3
parent_intentional_pressure_abort_count=0
parent_request_retry_count=0
parent_configured_target_blocks=128
parent_effective_runtime_target_blocks=64
parent_best_cpu_target_blocks=64
parent_best_gpu_target_blocks=0
parent_pressure_progress_event_count=41
parent_restore_sent=false
parent_d2h_store_complete=true
parent_h2d_worker_count=0
parent_h2d_bytes_total=0
parent_h2d_restore_attempted=false
parent_cleanup=clean
parent_resource_recovery_structured_artifact_present=false
parent_accepted_capacity_invalidated=false
~~~

F1-R4 所继承的上游 F1-R3 事实也继续冻结，仅用于避免服务器助手丢失完整 lineage；它不是
F1-R5 的直接 parent，不得重跑或用来替代上面的 F1-R4 gate：

~~~text
parent_task_id=p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722
parent_grade=red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
upstream_f1_r3_request_count=4
upstream_f1_r3_successful_request_count=3
upstream_f1_r3_d2h_worker_count=8
upstream_f1_r3_d2h_bytes_total=4548257792
upstream_f1_r3_restore_cpu_hit_exact=false
upstream_f1_r3_restore_load_scheduled=false
upstream_f1_r3_h2d_worker_count=0
upstream_f1_r3_h2d_bytes_total=0
upstream_f1_r3_prefix_hits_delta=0.0
~~~

以下已关闭 lineage 只作前置真值，不授权重跑；当前运行仍只有 F1-R5 server driver：

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
red_p8_2_k1a_r5_l1_r1_cpu_target_lost
red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost
candidate_p8_2_k1a_r5_f1_r2_mid_request_window_endpoint_mismatch
red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
historical_invalid_runner=tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh
~~~

不得进入 K2；不得进入 P8.3-I1。

拉取后以下 repo 文件 SHA-256 必须精确匹配。表中同时保留 F1-R4 历史合同与 F1-R5 当前入口，
目的是让服务器机器校验代码链，而不是授权重跑 F1-R4：

~~~text
6679e7abf67d3e4a2852273e54f1071a106933228a07a30e6b3987d7db5d4fc5  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment_audit.yaml
2acc928a5b351cd290e3496caaea5ebece58c1caa731a8a83068f3aa5f8b68c8  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.yaml
69005a9479eb899ab039f14dd6f810e93cf8464d65899355ee832a5ba6c3334d  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py
b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py
e6346b1ef8f89adb4028da02fb53c6dbfbac7dcccf09931c9434b1995f4ac4c1  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
2835fffdd7876125d947c50bf6246da9038edac4e417e188ca6fc5cd0716ac85  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py
5628a1109164146a33e082c9622c31a88c2fcf209808326219be7fd531c19ee9  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh
2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py
0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bcfb73b1faf64afd89e9231ea383500d2a01d38e673f39c3578425f51bd91a03  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
61bdd399a4742e3ae4b76614628b939a234bae6bd160ad7d22f8fe67ec54a89b  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6  benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch
557bec74ec427a2bc37165eea3c38eab6f809ec46ac6cd4f904c1e5386b30240  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r5_effective_restore_contract_audit.yaml
2ed46e8df421076b00a1d71a6dfb1a30e315c21a2ba5990ae1fce7bcedc4211d  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r5_effective_restore_contract.yaml
96cc47e1574e2f56eddef8b5e4886491d00af946dee30a66ea761c68eb03a143  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py
41fc23b2d793f62ff7ecd58ac091afd5c6200b2816a7845b5e72c89200405337  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.sh
c81be3a3cf7da92ce4c9279bb4cc1e1039991b2c7a01c398b87b51ae3655a4f7  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh
4588d3cad25206688ea7118016a329beb27d474430246d3880ef75065d11f069  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py
~~~

本轮不改 capacity、context、request order、runtime 版本、overlay 或依赖，不做 sweep 和 retry。已关闭
并保持关闭：performance reference、optimization gain、unique cause、K2、P8.3-I1、P8.4、P8.5、P9。

## 1. 同步与仓库合同（keep-alive 保持运行）

只允许从干净 `main` 普通 fast-forward。禁止 reset、stash、rebase、cherry-pick、server commit 或 push。
未跟踪服务器产物保留在 `--untracked-files=no` 边界外。

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
~~~

拉取后重新打开本文件，只执行这里的 F1-R5。首先在 keep-alive 运行时做离线合同门：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.sh \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh

P8_2_K1A_F1_R5_SERVER_TASK_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r5_unused
~~~

audit-only 必须在同一次输出中同时看到：

~~~text
task_id=p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722
server_task_driver=stop_run_cleanup_restore_record_finalize
keep_alive_card_ids=0,1,2,3,4,5,6,7
same_card_set_restore_on_every_exit=true
effective_target_block_count=128
h2d_target_block_count=128
restore_match_tokens=16384
block_size_tokens=128
restore_target_geometry_exact=true
target_capture_source_and_count_required=true
group_capture_geometry_required=true
resource_recovery_summary_always_recorded=true
finalize_after_recovery=true
request_retry_count_exact=0
capacity_search_authorized=false
result_transfer_authorized=true
automatic_transfer_allowed=false
next_task_authorized=false
~~~

若 `h2d_target_block_count` 不是 128，或 `restore_target_geometry_exact` 不是 true，立即报
`blocked_p8_2_k1a_r5_f1_r5_effective_runtime_contract_mismatch` 并停止；不得停卡，不得启动 vLLM，
不得修改脚本继续。这是 repo 合同问题，不是 capacity 结论。

## 2. NPU keep-alive 是常规资源操作

停 keep-alive 不是严重异常。本任务需要 0–7 八张卡，driver 会在模型运行前直接停止这八张卡，
在成功、失败、中断或提前退出后恢复完全相同的 0–7。driver 内部使用的两条固定命令是：

~~~bash
# Stop the low-priority keep-alive workload on the selected cards.
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# Restart the keep-alive workload on the same selected cards.
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

命令末尾数字是卡号；本任务只处理当前机器的 0–7，不扩大到其他节点或其他机器。
最终回报必须明确写出实际停卡卡号、实际恢复卡号与恢复状态。

正常情况不要在 driver 外重复停卡。如果 shell 被强制杀死、终端断开或 driver 返回后复核发现
keep-alive 没有恢复，立即手工执行上面的恢复命令，只恢复 0–7，然后更新
`resource_recovery_summary.json` 并重新 finalize；不得重跑模型 lifecycle。

## 3. 单次正式 lifecycle（只运行一条命令）

前门全部通过后，只允许一个新目录、一次 driver 调用。不得创建 run02，不得 retry，
不得修改 context/capacity 重跑。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_DIR=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722_run01
cd "${REPO_ROOT}"
test ! -e "${RESULT_DIR}"

set +e
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r5_server_task.sh \
  "${RESULT_DIR}"
TASK_EXIT=$?
set -e
printf 'server_task_exit=%s\n' "${TASK_EXIT}"
~~~

driver 返回非 0 可能只表示实验 red，不代表应该重跑。无论返回值是多少，都先检查原有
`RESULT_DIR`，检查 keep-alive 和 cleanup，然后按下面的分级回报；不得再次执行 driver。

### 3.1 冻结运行值

~~~text
model_path=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
quantization=ascend
tensor_parallel_size=8
expert_parallel=true
mtp_num_speculative_tokens=1
graph_mode=FULL_DECODE_ONLY
max_model_len=135168
max_num_batched_tokens=4096
max_num_seqs=1
block_size_tokens=128
chunked_prefill=true
prefix_caching=true
kv_connector=SimpleCPUOffloadConnector
kv_role=kv_both
lazy_offload=true
cpu_blocks_per_rank=128
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use_total=3444834304
pressure_context_tokens=36800
restore_match_tokens_required=16384
effective_target_block_count=128
request_retry_count=0
~~~

observer 只观测，不改 scheduler、copy、LRU、block retention、request order 或 runtime source。它对目标同时记录：

~~~text
configured_target_block_count
request_hash_candidate_count
fa_group_hash_candidate_count
selected_target_hash_count
target_capture_source
target_capture_exact
~~~

若 request block hashes 可完整提供 128 个可匹配键，优先使用它；FA-group 保留为 fallback 和差异诊断。
raw hash、block ID、request ID、token ID、请求体和生成内容不得进入有界包。

每个 KV group 必须报告 `theoretical/selected/non-null/hashable` 以及 required/captured/CPU/GPU 计数。
`unhashable_non_null_block_count` 是 partial-block 诊断字段；因为它没有 cache lookup hash，不得被当作
restore lookup 必需键。同时必须保留 `theoretical_block_count` 与 `provided_block_id_count`，不得用新
口径掩盖 hybrid geometry 的差异。

### 3.2 控制链与观察要求

~~~text
warmup success
-> target_prime success + D2H store complete
-> effective target capture exact=128 and all bounded group geometry captured
-> async pressure_01 with fixed context 36800
-> watch every request-local progress event for the complete pressure lifetime
-> only exact single-request CPU=128/GPU=0 + all-group eligibility may latch trigger
-> abort pressure streaming connection and record pressure_01 status=aborted_on_trigger
-> pressure client exits
-> engine queue returns idle
-> post-abort full gate remains trigger_ready
-> exactly one restore_follower
~~~

第一次 CPU 近失、GPU 未归零、group 不完整或 CPU target eviction 都不允许提前放弃。只要 pressure
还在运行，watcher 就继续；后续 scheduler step 仍可能形成完整 128-block CPU-only 窗口。只有完整
pressure 生命周期结束仍未命中，才可以结束本次 run。

## 4. 分级解释：必须同时报实验与运维结论

`grading_summary.json` 现在同时有：

~~~text
experimental_terminal
experimental_grade
operational_grade
server_grade
~~~

不得只报 `server_grade`。分类规则：

1. audit-only 的有效值不是 128/16384/128：报 effective runtime contract blocked，零 NPU，不评价 capacity。
2. target prime 后无法捕获 128 个可匹配 target hashes：报 target-capture/geometry blocked，不评价 capacity，不手工改代码。
3. 捕获精确，但完整 fixed pressure 生命周期无完整窗口：只报“本次 fixed lifecycle 未观察到”；不得证明 accepted capacity 永久不可能。
4. trigger/abort/idle/post-abort 闭合，但 CPU hit/load/H2D 不完整：报 H2D evidence incomplete，不得宣称 mechanism green。
5. 只有 exact 128 CPU-only、全组可恢复、控制顺序闭合、`cpu_hit_matched=16384`、load scheduled、8-rank H2D submit/enqueue/copy/poll/completion、D2H、connector、repair、queue、cleanup/recovery 全部闭合，才允许 candidate green。

任何 red/blocked 都不授权 run02、capacity/context 改动、sweep、K2 或 P8.3-I1。

## 5. Cleanup、recovery 与完整结果包

driver 必须生成 `resource_recovery_summary.json`，即使 restore 没有发送也不得缺失。它至少必须包含：

~~~text
stopped_card_ids
restored_card_ids
same_card_set_restored
stop_exit_code
restart_exit_code
keep_alive_marker_count
keep_alive_restored_exact
port_7000_listener_count
port_7000_free
vllm_residual_process_count
healthy_card_ids
all_eight_npu_healthy
tracked_worktree_clean
resource_recovery_exact
~~~

最终必须确认端口 7000 空闲、无目标 vLLM 残留、八卡 Health=OK、实际 stopped/restored 卡集完全一致、
keep-alive 恢复准确、tracked worktree clean。大型 raw vLLM log、metrics、request bodies、token IDs、generated
content、raw trace、raw hashes 与 recovery 命令输出保留在 `RESULT_DIR/runtime/`，只报路径。

有界包合同为 `payload_file_count <= 15`、`manifest_file_count=1`、
`transfer_file_count <= 16`，包含 manifest 在内严格不超过 `71680 bytes`。最终一次性回报：

1. `HEAD`、`origin/main`、ahead/behind、tracked-clean；
2. F1-R4 parent 四个 SHA-256、parent server grade 和 experimental terminal；
3. 定向 pytest、py_compile、三个 Bash 语法、driver audit-only 的有效 128 合同输出和 repo hashes；
4. lifecycle/request/complete/intentional abort/retry 精确计数与每个 role 终态；
5. target capture source，`request_hash_candidate_count`、`fa_group_hash_candidate_count`、selected count 与 exact；
6. 每个 KV group 的 theoretical/selected/non-null/hashable/unhashable/required/captured/CPU/GPU 最佳与终态计数；
7. 完整 pressure progress 数、最佳 near miss、target eviction 顺序，以及 trigger/abort/client exit/idle/post-abort/restore 时序；
8. restore CPU hit/load、D2H/H2D worker/bytes/pipeline/completion；
9. `experimental_terminal`、`experimental_grade`、`operational_grade`、`server_grade`与 claim boundary；
10. cleanup、7000、vLLM residual、八卡健康、实际停卡/恢复卡集、recovery exact；
11. `result_summary.md` 绝对路径和完整候选清单：每文件 bytes、SHA-256、sensitivity，另报 payload bytes、manifest bytes、完整 transfer bytes、payload/manifest/transfer file count 并逐文件双校验。

结果传输规则：`result_transfer_authorized: true` 只表示完整有界包可供选择，不选择渠道、不允许自动发送。
先在当前任务会话给出完整清单，可用方法原样报告为 `email / upload-api / server-local`，并推荐
`server-local`（raw trace 大，后续可能需要服务器原位分析）。然后暂停，等待用户对这个完整范围明确选择
一种方法。不得先发状态邮件，不得自动切换渠道，不得在本任务中写传输命令。

回报完成后暂停；不得自行进入 K2、P8.3-I1 或任何下一任务。
