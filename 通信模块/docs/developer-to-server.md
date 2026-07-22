# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R2 原始轨迹时序对齐（零 NPU）

~~~text
task_id: p8_2_k1a_r5_f1_r2_trace_alignment_2026_0722
execution_mode: authorized_server_local_read_only_trace_alignment_no_npu
server_sync_review_authorized: true
offline_first: true
server_local_raw_trace_read_authorized: true
source_result_mutation_authorized: false
result_directory_creation_authorized: true
npu_execution_authorized: false
keep_alive_stop_authorized: false
vllm_server_start_authorized: false
model_requests_authorized: false
formal_model_lifecycle_count_exact: 0
model_request_count_exact: 0
request_retry_count_exact: 0
context_change_authorized: false
capacity_search_authorized: false
pressure_search_or_sweep_authorized: false
runtime_overlay_authorized: false
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

本任务只读取已经完成的 F1-R1 calibration、calibration analysis 与 fixed L2 服务器本地产物，
对齐 `pressure_01` 起点后的 scheduler/residency/CPU target eviction 与请求结束后的 gate 结论。
不得启动新 vLLM、不得发模型请求、不得改变 36800 context、不得做 sweep，也不得把任一分析结论
自动解释为 H2D、性能收益或唯一根因。

不得进入 K2。不得进入 P8.3-I1。本轮结束后只回报证据和有界包，不得自动开始下一任务。

## 固定 NPU 占卡程序规则（每份服务器任务必须保留）

内部昇腾服务器上有低优先级 NPU 占卡程序在运行。本任务不使用 NPU，因此必须保持它运行，
不得停掉任何卡上的占卡程序。下面两条是项目固定命令，只用于说明统一规则，本任务严禁执行：

~~~bash
# 仅 NPU 任务可在实际需要的卡上执行；本任务不得执行。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 仅在同一 NPU 任务退出时恢复完全相同的卡集；本任务不得执行。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

最终回报必须写明：本任务实际停卡集合为空、实际恢复集合为空、keep-alive 全程保持运行。
命令末尾数字是卡号。未来任务若使用 NPU，只能停止实际需要的卡，并在成功、失败、中断或提前退出后
恢复完全相同的卡集，并回报实际停卡卡号、实际恢复卡号与恢复状态。

## 0. 已接受 parent 与本轮唯一问题

以下 parent 事实保持不变，不重跑：

~~~text
green_p8_1_r1_official_mtp_observe_only_matrix
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
blocked_p6_3c_not_strict_single_variable
blocked_p8_2_k1_frozen_stack_import_incompatible
ready_p8_2_k1a_r2_allocator_capacity
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
candidate_real_move_path=SimpleCPUOffloadConnector
cpu_bytes_to_use_per_rank=430604288
parent_target_prefix_tokens=16384
parent_task_id=p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721
parent_server_grade=red_p8_2_k1a_r5_l1_r1_cpu_target_lost
parent_request_count=3
parent_successful_request_count=3
parent_d2h_store_complete=true
parent_h2d_restore_complete=false
parent_f1_pool_delta_gate_fail_closed: true
parent_r5_l1_r1_bounded_and_raw_replay_authorized: true
parent_request_local_progress_analysis_authorized: true
parent_pressure_request_count_exact=1
parent_cleanup_status.txt=clean
consumed_parent_runner=tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh
consumed_f1_r1_runner=tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.sh
parent_candidate_manifest=candidate_manifest.server_local.json
accepted_installed_source_manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
accepted_installed_source_block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
calibration_root=server_local/p8_2_k1a_r5_f1_r1_calibration_2026_0722_run01
calibration_analysis_root=server_local/p8_2_k1a_r5_f1_r1_calibration_analysis_2026_0722_run01
calibration_grade=candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure
calibration_context_tokens=131072
calibration_candidate_context_tokens=36800
calibration_progress_event_count=64
calibration_exact_cpu_only_progress_event_count=56
fixed_l2_root=server_local/p8_2_k1a_r5_f1_r1_fixed_l2_2026_0722_run01
fixed_l2_grade=red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost
fixed_l2_request_count=3
fixed_l2_successful_request_count=3
fixed_l2_endpoint_cpu_target_block_count=54
fixed_l2_endpoint_gpu_target_block_count=0
fixed_l2_restore_sent=false
fixed_l2_cleanup=clean
~~~

R5-L1-R1 的有界包及上述早期 lineage 只作为已接受 parent，不授权重跑其脚本或生命周期。
已精确重放 R2 geometry/rendezvous/allocator；F1-R1 request-local 观察结果同样只作为 parent。

当前有界包能证明 calibration 的请求中途 `CPU=64/GPU=0` 窗口和 fixed L2 请求结束后的
`CPU=54/GPU=0` target-lost；不能证明 L2 中途是否也出现过完整 CPU-only 窗口，也不能独立复核
服务器报告中的“4096-token chunks”描述。

本任务只回答：

1. calibration raw trace 的实际 `num_scheduled_tokens` 分布是什么；
2. fixed L2 在 `pressure_01` 起点后是否出现过 `CPU=64/GPU=0` residency snapshot；
3. 若出现，是否早于首个 CPU target eviction，并与 post-request endpoint target-lost 形成观测点错位；
4. 若未出现，是否能在现有证据下明确归为“全过程没有完整窗口”，否则必须 blocked。

`request_start` 角色标记和 observer trace 都使用 `time.time_ns`；客户端 request timing 使用
`time.monotonic_ns`，且现有 trace 没有 request-end event。因此不得伪造精确 request-end timestamp；
请求完成在 endpoint gate 之前的顺序只从已冻结 controller 合同和 `residency_gate_timeline.json` 接受。

## 1. 同步、tracked-clean 与仓库合同

只允许从干净 `main` 普通 fast-forward。不得 reset、stash、rebase、cherry-pick、运行 `sync.sh`、
server commit 或 push。未跟踪服务器产物在 `--untracked-files=no` 边界保留。

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

同步后运行本轮定向合同：

~~~bash
set -euo pipefail
REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r2_trace_alignment.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_r5_f1_r1_request_local_pressure.py \
  tools/inference_contracts/p8_2_k1a_r5_f1_r2_trace_alignment.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r2_trace_alignment.sh

P8_2_K1A_F1_R2_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r2_trace_alignment.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r2_unused
~~~

audit-only 输出必须逐项包含：

~~~text
task_id=p8_2_k1a_r5_f1_r2_trace_alignment_2026_0722
execution_mode=authorized_server_local_read_only_trace_alignment_no_npu
npu_execution_authorized=false
vllm_server_start_authorized=false
model_requests_authorized=false
keep_alive_action=leave_running
context_change_authorized=false
pressure_search_or_sweep_authorized=false
result_transfer_authorized=true
transfer_method_selected=false
next_task_authorized=false
~~~

以下 repo 文件 SHA-256 必须匹配后才能继续：

~~~text
4964b3f6450c4982ac7fc88b67997002f6e2e12d9463eef0a3171dabd4a817e4  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r2_trace_alignment_audit.yaml
183dc450c583cf64910897447738569114e8c522029cb1758ad65ef202062be2  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r2_trace_alignment.yaml
b091e9144324240599a524ede3c23316264a396f215d7754af87ef625f02e42f  tools/inference_contracts/p8_2_k1a_r5_f1_r2_trace_alignment.py
019ca6bec0bcb3295d9aecb9d764189f02be1e8b7707f24863bdb583252d44fb  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r2_trace_alignment.sh
0d46912518b7e5cec62e3834b81ae54ca181e1f573593e96c0606ef13b305b91  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r2_trace_alignment.py
~~~

Section 1 任一失败：报告 `blocked_p8_2_k1a_r5_f1_r2_repository_contract_gate` 并停止；不得执行停卡命令。

## 2. Parent 原始证据前门（零 NPU）

所有源目录必须已存在且保持不可变。不得复制、改写、删除、压缩或重生 raw trace。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
CALIBRATION_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_calibration_2026_0722_run01
CALIBRATION_ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_calibration_analysis_2026_0722_run01
L2_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_fixed_l2_2026_0722_run01

test -d "${CALIBRATION_ROOT}"
test -d "${CALIBRATION_ANALYSIS_ROOT}"
test -d "${L2_ROOT}"
test -n "$(find "${CALIBRATION_ROOT}/runtime/offload_trace" -name 'h2d-residency.*.jsonl' -print -quit)"
test -n "$(find "${L2_ROOT}/runtime/offload_trace" -name 'h2d-residency.*.jsonl' -print -quit)"
test -f "${CALIBRATION_ROOT}/runtime/request_control/active_role.json"
test -f "${L2_ROOT}/runtime/request_control/active_role.json"
test -f "${L2_ROOT}/runtime/request_control/residency_gate_timeline.json"

test "$(sha256sum "${CALIBRATION_ANALYSIS_ROOT}/grading_summary.json" | awk '{print $1}')" = \
  9e06344bcb38f182009f731fb356635480e20d4ff52a50cef5d6590a6cb2dedb
test "$(sha256sum "${CALIBRATION_ANALYSIS_ROOT}/pressure_candidate.json" | awk '{print $1}')" = \
  af10135cf79d582c34fb2329f8115f6c1d9065791db837c2d79eefc2b183dc41
test "$(sha256sum "${L2_ROOT}/grading_summary.json" | awk '{print $1}')" = \
  118ceaebbfcbe83ebb8fb4780eebab1c84a3ae070f32cb1a1f131372f5791dd4
test "$(sha256sum "${L2_ROOT}/runtime/request_control/residency_gate_timeline.json" | awk '{print $1}')" = \
  952ca9f900f85dcd51906497bd7283bf47bbe13d9b41bc656944b8452fc9b745
~~~

Section 2 任一失败：报告 `blocked_p8_2_k1a_r5_f1_r2_parent_evidence_gate` 并停止；不得猜测替代路径、
不得寻找相邻 run、不得重跑模型。

## 3. 唯一只读分析

结果目录必须是新目录；存在即停止，不得覆盖或换成 run02 重试。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
CALIBRATION_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_calibration_2026_0722_run01
CALIBRATION_ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_calibration_analysis_2026_0722_run01
L2_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r1_fixed_l2_2026_0722_run01
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r2_trace_alignment_2026_0722_run01
cd "${REPO_ROOT}"

test ! -e "${RESULT_ROOT}"
P8_2_K1A_F1_R2_CALIBRATION_ROOT="${CALIBRATION_ROOT}" \
P8_2_K1A_F1_R2_CALIBRATION_ANALYSIS_ROOT="${CALIBRATION_ANALYSIS_ROOT}" \
P8_2_K1A_F1_R2_L2_ROOT="${L2_ROOT}" \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r2_trace_alignment.sh \
  "${RESULT_ROOT}"

cat "${RESULT_ROOT}/task_grade.txt"
~~~

只允许以下三个机器 grade：

~~~text
candidate_p8_2_k1a_r5_f1_r2_mid_request_window_endpoint_mismatch
candidate_p8_2_k1a_r5_f1_r2_no_l2_cpu_only_window
blocked_p8_2_k1a_r5_f1_r2_trace_alignment_incomplete
~~~

第一种只证明 fixed L2 中途完整 CPU-only 窗口与 post-request target-lost endpoint 的观测点错位；
不证明它是唯一根因。第二种只证明当前 L2 raw snapshot 中未见完整窗口。第三种保持证据不足。
三种都不授权新 lifecycle、context 调整、sweep、restore、H2D、性能、K2 或 P8.3-I1。

## 4. 有界包验证、回报与传输暂停

成功生成时必须只有 5 个 payload 加 1 个 manifest 控制文件：

~~~text
grading_summary.json
result_summary.md
source_evidence_provenance.json
task_grade.txt
trace_alignment_summary.json
candidate_manifest.server_local.json
~~~

`candidate_manifest.server_local.json` 必须同时给出 payload 与完整 transfer 口径：
`payload_file_count=5`、`transfer_file_count=6`，`transfer_total_bytes` 必须包含 manifest 自身且不超过
`71680`。逐文件 bytes/SHA-256 必须匹配；raw trace 内容、request ID、token ID、生成内容和 raw hash
不得进入有界包。

最终回报必须包含：

1. 同步后的 HEAD、`origin/main`、ahead/behind、tracked-clean；
2. source 三个根、四个 parent 文件 SHA-256 与 raw trace 文件数；
3. task grade、calibration scheduled-token histogram、L2 snapshot reason/state histogram；
4. L2 是否在首个 CPU target eviction 前出现完整 `CPU=64/GPU=0`；
5. endpoint `CPU/GPU/decision`、request-end timestamp 不可精确对齐的限制、claim boundary；
6. `npu_started=false`、`vllm_started=false`、`model_requests_sent=0`；
7. 实际停卡集合为空、实际恢复集合为空、keep-alive 全程保持运行；
8. 精确 `result_summary.md` 路径，以及完整 6 文件的文件名、bytes、SHA-256（manifest 自身可只报 bytes 与其现场 SHA-256）、sensitivity；
9. 可选方法 `email` / `upload-api` / `server-local`（即 email / upload-api / server-local 三选一），推荐 `server-local`，理由是本轮结果已经位于服务器且在用户选择前无需移动任何文件。

`result_transfer_authorized:true` 只表示完整有界包具备渠道选择资格，不表示已经选择渠道。
回报上述完整清单后暂停，等待用户对同一完整范围明确选择 `email`、`upload-api` 或 `server-local`；
不得先发状态邮件、不得自动上传、不得拆分发送、不得失败后自动换渠道。

## 5. 禁止事项与停止条件

- 不执行 `npu_stop.sh` 或 `npu_keep_alive.sh`；keep-alive 全程运行。
- 不启动 vLLM/NPU，不发任何模型请求，不接触 7000 端口服务。
- 不更改 36800/131072 context，不搜索、不 sweep、不补跑 calibration/L2。
- 不修改 runtime、依赖、overlay、observer 或 parent source/result tree。
- 不把 mid-request/endpoint mismatch 写成 H2D restore、性能收益或唯一根因。
- 不进入 K2、P8.3-I1、P8.4、P8.5 或 P9。
- 任一前门失败只报告第一失败点，不改路径、不换 run、不 retry。
- 不 commit、不 push、不清理服务器未跟踪产物。

任务完成不代表下一轮已授权；`next_task_authorized:false` 必须保持。
