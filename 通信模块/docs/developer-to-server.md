# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R1 请求级压力进度校准与条件式 L2

~~~text
task_id: p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722
execution_mode: authorized_parent_legacy_then_one_calibration_then_conditional_fixed_l2
server_sync_review_authorized: true
offline_first: true
parent_r5_l1_r1_bounded_and_raw_replay_authorized: true
parent_f1_pool_delta_gate_fail_closed: true
request_local_progress_analysis_authorized: true
calibration_lifecycle_authorized: conditional
fixed_l2_lifecycle_authorized: conditional
result_directory_creation_authorized: true
npu_execution_authorized: conditional
conditional_calibration_gate: candidate_requires_p8_2_k1a_r5_f1_r1_instrumented_calibration_only
conditional_fixed_l2_gate: candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure_only
keep_alive_stop_and_restore_authorized: conditional
vllm_server_start_authorized: conditional
model_requests_authorized: conditional
formal_model_lifecycle_count_min: 0
formal_model_lifecycle_count_max: 2
calibration_lifecycle_count_max: 1
fixed_l2_lifecycle_count_max: 1
pressure_request_count_exact: 1
model_request_count_min: 3
model_request_count_max: 4
model_request_count_exact_if_trigger_observed: 4
request_retry_count_exact: 0
runtime_overlay_authorized: true
runtime_behavior_patch_authorized: false
task_local_diagnostic_mode_patch_authorized: true
capacity_search_authorized: false
pressure_search_or_sweep_authorized: false
profiler_authorized: false
hbm_sampler_authorized: false
runtime_or_dependency_mutation_authorized: false
result_transfer_authorized: true
transfer_method_selected: false
automatic_transfer_allowed: false
next_task_authorized: false
k2_authorized: false
p8_3_i1_authorized: false
no_k2_k3_k4_p8_3_i1_p8_4_p8_5_or_p9: true
standing_npu_and_vllm_consumption_authorization: true
~~~

旧 F1 已永久 fail-closed：即使存在 `CPU=64/GPU=0` exact window，`gpu_free_block_count` 净差也不是
request-local 分配证据，不得再解锁 L2。本任务改为只读 observer 记录单请求
`num_computed_tokens(before/after)` 与 `num_scheduled_tokens`；只有连续、单请求、从 `before=0`
起步且第一个 exact window 后仍保留至少 4096-token 安全余量时，才推导唯一 fixed context。

最多两个正式 NPU lifecycle：一次 observe-only calibration + 一次条件式 fixed L2。任一前门失败则减为
0 或 1，不得补跑、不得第二 calibration、不得 context sweep。`result_transfer_authorized:true` 只表示
最终有界包可进入渠道选择，不是自动外发授权。

## 固定 NPU 占卡程序规则（每份服务器任务必须保留）

内部昇腾服务器上有低优先级 NPU 占卡程序在运行。任何需要使用 NPU 的任务都可以只停掉实际要使用的卡，
但无论任务成功、失败、中断或提前退出，任务结束后都必须在完全相同的卡号上重新拉起占卡程序。
末尾数字是卡号，应按实际需要删减；不使用 NPU 的分支不得停卡。本任务若进入 Section 3 或 Section 4，
将使用全部 8 卡，因此停卡与恢复命令分别为：

~~~bash
# 停掉本任务实际使用的 0–7 卡上的低优先级占卡程序。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 任务结束后，在完全相同的 0–7 卡上恢复占卡程序。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

最终回报必须列出实际停卡卡号、实际恢复卡号与恢复状态。若 Section 3/4 均未启动，必须报告未停卡且占卡程序保持运行。

## 0. 已关闭门、parent 结论与本轮唯一问题

以下结论保留，不重跑、不撤销：

~~~text
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p6_3c_not_strict_single_variable
blocked_p8_2_k1_frozen_stack_import_incompatible
ready_p8_2_k1a_r2_allocator_capacity
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
red_p8_2_k1a_r5_l1_h2d_evidence_incomplete
red_p8_2_k1a_r5_l1_r1_cpu_target_lost
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
~~~

本任务仍以 R5-L1-R1 的有界包与 raw tree 为不可变 parent 证据。R5-L1-R1 parent 必须原样保留：

~~~text
parent_task_id=p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721
parent_head=b2c23ef5b151d130ff0fbbfaa50257c3136f519c
parent_server_grade=red_p8_2_k1a_r5_l1_r1_cpu_target_lost
parent_manifest_sha256=1209e22dc67aa1c15e80efcd26b453d7303665a5cd1a982ca2c41152334bb022
parent_payload_file_count=14
parent_payload_bytes=15788
parent_manifest_bytes=3578
parent_total_bytes=19366
parent_request_count=3
parent_successful_request_count=3
parent_d2h_store_complete=true
parent_d2h_completed_worker_count=8
parent_restore_sent=false
parent_h2d_restore_complete=false
parent_cleanup=clean
~~~

旧 F1 pool-delta 门永久 fail-closed，不得再用 net GPU-free delta 解锁 L2。

固定 runtime/capacity 常量如下；这些值不得因离线候选而改变：

~~~text
kv_connector=SimpleCPUOffloadConnector
cpu_blocks_per_rank=128
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use_total=3444834304
required_restore_tokens=16384
block_size_tokens=128
lazy_offload=true
~~~

本轮只回答：legacy/calibration 的 request-local progress 能否推导一个带 4096-token 余量的固定 context；
若 legacy 缺直接进度，只允许一次 131072-context、无 restore 的 observe-only calibration；只有
`candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure` 才允许一个 fixed L2。

## 1. 同步、tracked-clean、仓库合同与冻结 hash

只允许从干净 `main` 普通 fast-forward。不得 reset、stash、rebase、cherry-pick、运行 `sync.sh`、server commit
或 push。未跟踪服务器产物在 `--untracked-files=no` 边界保留。

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

同步后必须先运行：

~~~bash
set -euo pipefail
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_l1_lazy_h2d_lifecycle.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_l1_r1_lazy_h2d_lifecycle.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_pressure_window.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_r5_f1_r1_request_local_pressure.py \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py

bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_calibration.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_fixed_pressure_l2.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh

P8_2_K1A_F1_R1_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r1_unused_result \
  > /tmp/opencode/p8_2_k1a_r5_f1_r1_audit.txt

P8_2_K1A_F1_R1_CALIBRATION_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_calibration.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r1_cal_unused \
  > /tmp/opencode/p8_2_k1a_r5_f1_r1_cal_audit.txt

grep -Fx 'task_id=p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722' /tmp/opencode/p8_2_k1a_r5_f1_r1_audit.txt
grep -Fx 'formal_model_lifecycle_count_max=2' /tmp/opencode/p8_2_k1a_r5_f1_r1_audit.txt
grep -Fx 'net_gpu_free_delta_may_unlock_l2=false' /tmp/opencode/p8_2_k1a_r5_f1_r1_audit.txt
grep -Fx 'task_id=p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722' /tmp/opencode/p8_2_k1a_r5_f1_r1_cal_audit.txt
grep -Fx 'calibration_only=true' /tmp/opencode/p8_2_k1a_r5_f1_r1_cal_audit.txt
grep -Fx 'restore_request_authorized=false' /tmp/opencode/p8_2_k1a_r5_f1_r1_cal_audit.txt
~~~

冻结 repo 文件 SHA-256 必须逐项匹配后才能进入 Section 2：

~~~json
{
  "benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r1_request_local_pressure_audit.yaml": "9f4219c37fd7d989084f2a172e808135919b1f44cd7782d6d64af425fa5a1dc4",
  "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r1_request_local_pressure_conditional_lifecycle.yaml": "0c84fdbb42718f38e2335ea618726be4d4097b859537eff0f961a67977c8a093",
  "benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch": "5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055",
  "tools/inference_contracts/p8_2_k1a_r5_f1_r1_request_local_pressure.py": "553785959e81611e60377bce937beb6538a802fcc6bbd3aea7bfdf0e33600ff2",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.sh": "e85893554920353837e8f72984e0fba3c4c1bb76a890e14b9bb8b60f5bc895fc",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_calibration.sh": "9a6e899e80cdc4bf7f18ff94261366f9306f287fe6322a763d245fb6a776f80e",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_fixed_pressure_l2.sh": "8c0f20d22458507e105e3ab08ee20d3fe714b234cd06e3dc279fb288371adb3e",
  "tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py": "e6579e4e41b5e87e0a3c2716e0800e4ecfe307d21168c00c8ca898fb111b2f44",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py": "59d6552904fb677be2102549f2448d582ea11d4fc543a756aa99de6c275de08b",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh": "04cce2dc5a6a632c06b9c35f1cbed4f268fa9854d9462fc0d1caec6bb0f0e0b7",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "ff038cf51ac79d8eec4fa5b9d926178d494efa630265dafe3e8ade8ea06ce8b1",
  "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.py": "7d18595eba161263741721eabc1fd7d571e6651fafb1e2a05bc5061d686019b7"
}
~~~

Section 1 任一失败：`blocked_p8_2_k1a_r5_f1_r1_repository_contract_gate`；不得停 keep-alive。

## 2. Parent legacy request-local 归因（零 NPU）

parent bounded 与 raw 必须来自同一个已完成 R1 结果根；不得复制、改写、删除或重生 raw 证据。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
PARENT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721_run01
LEGACY_ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_parent_legacy_2026_0722_run01
cd "${REPO_ROOT}"

test -d "${PARENT_ROOT}"
test -n "$(find "${PARENT_ROOT}/runtime/offload_trace" -name 'h2d-residency.*.jsonl' -print -quit)"
test ! -e "${LEGACY_ANALYSIS_ROOT}"
test "$(sha256sum "${PARENT_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = 1209e22dc67aa1c15e80efcd26b453d7303665a5cd1a982ca2c41152334bb022

P8_2_K1A_F1_R1_ANALYSIS_MODE=parent_legacy \
P8_2_K1A_F1_R1_SOURCE_RESULT_ROOT="${PARENT_ROOT}" \
P8_2_K1A_F1_R1_TRACE_DIR="${PARENT_ROOT}/runtime/offload_trace" \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.sh \
  "${LEGACY_ANALYSIS_ROOT}"

cat "${LEGACY_ANALYSIS_ROOT}/task_grade.txt"
~~~

预期：legacy 无 `request_local_pressure_progress` 时输出
`candidate_requires_p8_2_k1a_r5_f1_r1_instrumented_calibration`，再进入 Section 3。
若为 `blocked_p8_2_k1a_r5_f1_r1_request_local_pressure_gate`：零 NPU 停止，不得停卡。
若意外得到 ready grade：跳过 Section 3，将该 analysis root 作为 Section 4 输入。
Section 2 不得停 keep-alive。

## 3. 唯一 observe-only calibration lifecycle（仅 calibration_required）

先执行 `npu_stop.sh 0 1 2 3 4 5 6 7`，确认 8 卡空闲后只允许一次：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
CALIBRATION_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_calibration_2026_0722_run01
CALIBRATION_ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_calibration_analysis_2026_0722_run01
cd "${REPO_ROOT}"
test ! -e "${CALIBRATION_ROOT}"
test ! -e "${CALIBRATION_ANALYSIS_ROOT}"

set +e
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_calibration.sh \
  "${CALIBRATION_ROOT}"
CAL_EXIT=$?
set -e
printf '%s\n' "${CAL_EXIT}" > "${CALIBRATION_ROOT}/initial_runner_exit_code.txt"

# 无论成败，先恢复占卡，再做离线分析。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7

test -n "$(find "${CALIBRATION_ROOT}/runtime/offload_trace" -name 'h2d-residency.*.jsonl' -print -quit)"

P8_2_K1A_F1_R1_ANALYSIS_MODE=calibration \
P8_2_K1A_F1_R1_SOURCE_RESULT_ROOT="${CALIBRATION_ROOT}" \
P8_2_K1A_F1_R1_TRACE_DIR="${CALIBRATION_ROOT}/runtime/offload_trace" \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.sh \
  "${CALIBRATION_ANALYSIS_ROOT}"

cat "${CALIBRATION_ANALYSIS_ROOT}/task_grade.txt"
~~~

calibration 合同：`warmup -> target_prime -> pressure_01`；pressure context=131072（只观测，不搜索）；
3/3 请求；restore 明确禁止；request-local observer 开启；task-local diagnostic mode patch=`0660`；
零 retry。runner 即使以 parent-like target-lost/yellow 退出，也要保留 raw trace 并允许离线 analyzer 复核，
不得把预期校准终态误当 shell 崩溃。

只有 `candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure` 才进入 Section 4。
禁止第二 calibration、禁止手工填 context、禁止 sweep。

随后在 keep-alive 仍运行时验证：

- 精确重放 R2 geometry/rendezvous/allocator，确认 8-rank parity、128 CPU blocks/rank、
  `430604288 bytes/rank / 3444834304 bytes total`；
- vLLM commit=`0decac0d96c42b49572498019f0a0e3600f50398`；
- vLLM-Ascend commit=`5f6faa0cb8830f667266f3b8121cd1383606f2a1`；
- `manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b`；
- `block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283`；
- installed source/import/connector/worker/copy backend、R2 hybrid repair 与 observer method resolution 全过；
- model path 可读、7000 端口空闲、无 vLLM 残留、8 卡健康、MemAvailable 不低于 384 GiB、swap 未用；
- keep-alive marker 精确覆盖 `#0#..#7#`，只能终止完全属于官方 keep-alive 的 process group。

任一前门失败：`blocked_p8_2_k1a_r5_f1_r1_source_or_provenance_gate`，保持 keep-alive 不变并停止。

## 4. 条件式 fixed L2（仅 ready）

先再次执行 `npu_stop.sh 0 1 2 3 4 5 6 7`（Section 3 已恢复过 keep-alive）。
若从 Section 2 直接 ready 跳过 Section 3，则此处首次停卡。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_calibration_analysis_2026_0722_run01
L2_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_fixed_l2_2026_0722_run01
cd "${REPO_ROOT}"

test "$(cat "${ANALYSIS_ROOT}/task_grade.txt")" = candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure
FIXED_CONTEXT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidate_pressure_context_tokens"])' "${ANALYSIS_ROOT}/pressure_candidate.json")
test "${FIXED_CONTEXT}" -gt 0
test ! -e "${L2_ROOT}"

export P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS=${FIXED_CONTEXT}
export P8_2_K1A_F1_R1_ANALYSIS_ROOT=${ANALYSIS_ROOT}

set +e
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_fixed_pressure_l2.sh "${L2_ROOT}"
L2_EXIT=$?
set -e
printf '%s\n' "${L2_EXIT}" > "${L2_ROOT}/initial_runner_exit_code.txt"
~~~

server argv/capacity/runtime 必须与 R1 相同，canonical server argv SHA 仍为
`89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f`。唯一改变是 signed candidate 的
pressure context；禁止手填、取整或搜索。

~~~text
request_order=warmup,target_prime,fixed_pressure,restore_follower_if_trigger
request_count_min=3
request_count_max=4
request_count_exact_if_trigger_observed=4
terminal_pre_restore_request_count=3
pressure_request_count_exact=1
request_retry_count_exact=0
~~~

只有本 lifecycle 自身再次观测 `CPU=64/GPU=0` 才发 restore；否则 3 请求合规停止。无第五请求、无第三 lifecycle。

## 5. Cleanup、keep-alive 恢复与 L2 finalization

只要 Section 3 或 4 曾启动，无论成败都必须先停 vLLM、释放 7000、确认 residual=0 和 cleanup clean，再恢复：

~~~bash
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

若执行了 Section 4，恢复后确认 16 markers、`#0#..#7#`、8 卡健康、7000 空闲、无 vLLM residual、tracked clean，
且 `cleanup_status.txt=clean`，再 finalization：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_calibration_analysis_2026_0722_run01
L2_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_fixed_l2_2026_0722_run01
PYTHON_BIN=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
cd "${REPO_ROOT}"

export P8_2_K1A_TASK_ID=p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722
export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-F1-R1-L2
export P8_2_K1A_PRESSURE_CONTEXT_TOKENS=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidate_pressure_context_tokens"])' "${ANALYSIS_ROOT}/pressure_candidate.json")
export P8_2_K1A_PRESSURE_REQUEST_COUNT_MAX=1
export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_f1_r1_fixed_pressure_h2d_trigger
export P8_2_K1A_NO_SUCCESS_GRADE=red_p8_2_k1a_r5_f1_r1_fixed_pressure_no_success
export P8_2_K1A_CPU_TARGET_LOST_GRADE=red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost
export P8_2_K1A_PARTIAL_GRADE=red_p8_2_k1a_r5_f1_r1_fixed_pressure_trigger_not_reached
export P8_2_K1A_EVIDENCE_INCOMPLETE_GRADE=red_p8_2_k1a_r5_f1_r1_fixed_pressure_evidence_incomplete

set +e
"${PYTHON_BIN}" tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py \
  finalize --artifact-dir "${L2_ROOT}"
FINALIZE_EXIT=$?
set -e
printf '%s\n' "${FINALIZE_EXIT}" > "${L2_ROOT}/finalize_exit_code.txt"
~~~

## 6. 分级与停止边界

- repository 合同失败：`blocked_p8_2_k1a_r5_f1_r1_repository_contract_gate`；
- parent/raw/source provenance 失败：`blocked_p8_2_k1a_r5_f1_r1_source_or_provenance_gate`；
- legacy 缺直接进度：`candidate_requires_p8_2_k1a_r5_f1_r1_instrumented_calibration`；
- progress gap / 余量不足：`blocked_p8_2_k1a_r5_f1_r1_request_local_pressure_gate`；
- request-local 候选就绪：`candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure`；
- calibration capture 相关：`candidate_green_..._calibration_capture` /
  `yellow_..._calibration_target_lost_after_capture` /
  `yellow_..._calibration_window_not_reached` /
  `red_..._calibration_no_success` /
  `red_..._calibration_evidence_incomplete`；
- L2：`candidate_green_p8_2_k1a_r5_f1_r1_fixed_pressure_h2d_trigger` 或对应 red grades。

candidate green 仍只是服务器候选，不证明唯一根因、性能收益或 K2 就绪。

## 7. 小结果包、完整清单与传输停点

raw vLLM log、raw metrics、request bodies、raw trace、active-role marker、generated output/token IDs/request IDs
全部留服务器。

- Section 2 only：报告 legacy analysis 6 payload + manifest；
- 进入 Section 3：另报 calibration raw 保留路径 + calibration analysis package；
- 进入 Section 4：再报 L2 bounded package；
- 所有拟传文件合计不得超过 71680 bytes，每项含 path/bytes/SHA-256/sensitivity；
- sensitivity 只能为 `bounded_operational_metadata_no_content_or_token_ids`；
- manifest 自身计入完整传输范围。

完成后先报告 task id、HEAD/origin/tracked、各 section pass/fail、首错、legacy/calibration/L2 grades（见 grading_summary.json）、
固定 context、实际 lifecycle/request 数、停卡/恢复卡号与状态，以及完整候选清单。然后列出
`email / upload-api / server-local` 三种方法并推荐一种；用户未对该完整范围选择唯一渠道前，
不得外发、不得预先 upload-api、不得发状态邮件、失败后不得自动换渠道。不得继承上一轮 upload-api 选择。

## 8. 完成后等待

~~~text
next_task_authorized=false
k2_authorized=false
p8_3_i1_authorized=false
performance_reference_accepted=false
cause_proven_as_unique=false
~~~

本任务 blocked/red/yellow 不撤销任何既有 P6/P8 窄边界结论。不得进入 K2。不得进入 P8.3-I1。
不得自行进入下一任务。
