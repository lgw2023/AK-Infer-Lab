# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-L1-R1 corrected observable-gate lazy H2D 单生命周期

~~~text
task_id: p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721
execution_mode: authorized_corrected_observable_gate_single_lazy_dynamic_pressure_h2d_trigger_lifecycle
server_sync_review_authorized: true
parent_r5_l1_package_replay_authorized: true
frozen_source_and_installed_runtime_audit_authorized: true
result_directory_creation_authorized: true
npu_execution_authorized: true
keep_alive_stop_and_restore_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
formal_model_lifecycle_count_max: 1
model_request_count_min: 4
model_request_count_max: 8
pressure_request_count_max: 5
request_retry_count_exact: 0
runtime_overlay_authorized: true
runtime_behavior_patch_authorized: false
capacity_search_authorized: false
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

这是一个完整但仍有界的 R1 任务。它一次关闭 parent package replay、controller regression、observer binding、
installed runtime identity、资源、单 lifecycle、D2H/H2D、cleanup/recovery 和 bounded package 九类门。它不是
容量搜索或性能实验。`result_transfer_authorized:true` 只表示最终有界结果可进入渠道选择，不是自动上传命令。

## 0. Parent 结论、R1 问题与不可变边界

以下既有事实保留，不重跑、不撤销：

~~~text
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p6_3c_not_strict_single_variable
blocked_p8_2_k1_frozen_stack_import_incompatible
ready_p8_2_k1a_r2_allocator_capacity
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
~~~

直接 parent R5-L1 已执行一次 lifecycle，服务器 grade 必须原样保留：

~~~text
parent_task_id=p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721
parent_server_grade=red_p8_2_k1a_r5_l1_h2d_evidence_incomplete
parent_request_count=2
parent_successful_request_count=2
parent_request_evidence_exact=true
parent_d2h_store_complete=true
parent_d2h_completed_worker_count=8
parent_d2h_bytes_total=2206846976
parent_target_hashes_captured_exact=true
parent_latest_cpu_target_block_count=0
parent_latest_gpu_target_block_count=64
parent_pressure_request_count_executed=0
parent_restore_sent=false
parent_h2d_restore_complete=false
parent_cleanup=clean
parent_transport_success_count_after_developer_refinalization=6
parent_server_grade=red_p8_2_k1a_r3_r2_r2_r1_r1_r1_evidence_incomplete
parent_developer_grade=yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
connector=SimpleCPUOffloadConnector
~~~

parent timeline 的 `CPU=0 / GPU=64` 只能来自有效 `target_residency_snapshot`；仓库 gate 对该状态返回
`continue_pressure`。旧 controller 却在等待 CPU full 超时后无条件改写为 `unobservable`，在
`pressure_01` 前停止。R1 只修复这个控制面缺陷并加强两个只读证据点：

1. 有 capture + snapshot 的 observable-not-ready 状态在 timeout 后保持 `continue_pressure`；
2. observer 在原 `update_connector_output` 成功返回后追加 `after_connector_output` snapshot；
3. `pressure_01` 还必须等到 D2H store complete；
4. restore 仍只允许 target `CPU-present + GPU-absent`，即 `CPU=64 / GPU=0`。

R1 与 parent 使用完全相同的 W8A8、TP8+EP、MTP、R2 repair、Prefix Cache、Chunked Prefill、server argv
和 `430604288 bytes/rank / 3444834304 bytes total`。不得调参、改 source/site-packages、增加 patch、改 eager、
运行第二 lifecycle 或 retry。parent red 不证明 H2D runtime failure；R1 也不得预设 candidate green。

## 1. 同步、tracked-clean、仓库合同与冻结 hash

服务器只允许从干净 `main` 普通 fast-forward。不得 reset、stash、rebase、cherry-pick、运行 `sync.sh`、
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

正式 R1 结果根必须不存在；parent 根只读保留：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
PARENT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721_run01
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721_run01
cd "${REPO_ROOT}"
test -d "${PARENT_ROOT}"
test ! -e "${RESULT_ROOT}"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_l1_lazy_h2d_lifecycle.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_l1_r1_lazy_h2d_lifecycle.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_r1_lazy_h2d.sh

P8_2_K1A_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_r1_lazy_h2d.sh \
  "${RESULT_ROOT}" > /tmp/opencode/p8_2_k1a_r5_l1_r1_top_audit.txt
P8_2_K1A_MODE_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_r1_lazy_h2d.sh \
  "${RESULT_ROOT}" > /tmp/opencode/p8_2_k1a_r5_l1_r1_mode_audit.txt

grep -Fx 'task_id=p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721' /tmp/opencode/p8_2_k1a_r5_l1_r1_top_audit.txt
grep -Fx 'execution_mode=authorized_corrected_observable_gate_single_lazy_dynamic_pressure_h2d_trigger_lifecycle' /tmp/opencode/p8_2_k1a_r5_l1_r1_top_audit.txt
grep -Fx 'lifecycle_count=1' /tmp/opencode/p8_2_k1a_r5_l1_r1_top_audit.txt
grep -Fx 'request_count_min=4' /tmp/opencode/p8_2_k1a_r5_l1_r1_top_audit.txt
grep -Fx 'request_count_max=8' /tmp/opencode/p8_2_k1a_r5_l1_r1_top_audit.txt
grep -Fx 'npu_execution_authorized=true' /tmp/opencode/p8_2_k1a_r5_l1_r1_top_audit.txt
grep -Fx 'lazy_offload=true' /tmp/opencode/p8_2_k1a_r5_l1_r1_mode_audit.txt
grep -Fx 'server_command_sha256=89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f' /tmp/opencode/p8_2_k1a_r5_l1_r1_mode_audit.txt
~~~

冻结 repo 文件 SHA-256 必须逐项匹配后才可进入 Section 2：

~~~json
{
  "benchmarks/deepseek_v4_flash/p8_2_k1a_r5_l1_r1_lazy_h2d_lifecycle_audit.yaml": "b0d91c73cbe8ccd980c4a54bc0be982c155da082ee4319a56118bfc19ceffab9",
  "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle.yaml": "d92145b76862836ea0ffd142e3aabc904e3a4d2e01c69d8759e43c8bc7be9ecc",
  "tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py": "549b3fc0c5cb01b222f3310b882e3f86a6e5664ed05b0f3659e7dc689a10c2dd",
  "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py": "647be3d184c2a2df53f2362be1fbca040c278ceb8c49e8d9b68b670596adde78",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh": "786400770a7088bc6e0edd67296200ff91abc589e168d3d1370840fd5fc50ddf",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_r1_lazy_h2d.sh": "0ff39b0473a7693101e49c87619facb0c8920aa0ed8376e0f3e18a15d63b3eb8",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh": "0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "d1c874110847d927f832b2675f12642e704bab8bff5b5f16b2b82c1a37c6d0dd",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f0_h2d_trigger_feasibility.py": "f77ee60f90977084aa4b7f0d08a3e7678be473501e8a51cc1046c2de7d94fdd8",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r5_l1_lazy_h2d_lifecycle.py": "f5333888c6c7363f5a9c86022bab95cc168cb987f8a5a2c50b5b430eaa524b10",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r5_l1_r1_lazy_h2d_lifecycle.py": "944db7fee6b7d2cb21c17a09e5c7c749db8abe4d3143eaa30d06ff1da269b47b",
  "benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_simple_cpu_offload_observer_overlay.patch": "5db6a0c78d36eb9821474cfef21245b45bd858d07361b7f9afd36ef49e76c2b6"
}
~~~

Section 1 任一失败：`blocked_p8_2_k1a_r5_l1_r1_repository_contract_gate`；不得停止 keep-alive。

## 2. Parent package、controller regression 与 source/runtime 前门（零 NPU）

R5-L1 已继承并精确重放 R4-R1 bounded package，并精确重放 R2 geometry/rendezvous/allocator；R1 不重跑旧任务，
但必须先逐文件验证直接 parent manifest，严禁修改 parent 根：

~~~bash
set -euo pipefail
export PARENT_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721_run01
test "$(sha256sum "${PARENT_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = a80231f8268c239016f7b2ed1d8b2a7521e250b52728e9e123f8d344eddf1725

python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["PARENT_ROOT"])
manifest = json.loads((root / "candidate_manifest.server_local.json").read_text())
assert manifest["payload_file_count"] == 14
assert manifest["candidate_total_bytes"] == 14291
assert manifest["result_transfer_authorized"] is True
assert manifest["transfer_method_selected"] is False
for name, expected in manifest["files"].items():
    path = root / name
    assert path.stat().st_size == expected["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]
assert sum(path.stat().st_size for path in root.iterdir() if path.is_file()) == 17868

grading = json.loads((root / "grading_summary.json").read_text())
timeline = json.loads((root / "residency_gate_timeline.json").read_text())
transfer = json.loads((root / "transfer_trace_summary.json").read_text())
assert grading["server_grade"] == "red_p8_2_k1a_r5_l1_h2d_evidence_incomplete"
assert grading["successful_request_count"] == 2
assert grading["request_evidence_exact"] is True
assert timeline["pressure_request_count_executed"] == 0
assert timeline["restore_sent"] is False
sample = timeline["gate_samples"][-1]
assert sample["target_hashes_captured_exact"] is True
assert sample["latest_cpu_target_block_count"] == 0
assert sample["latest_gpu_target_block_count"] == 64
assert transfer["d2h_store_complete"] is True
assert transfer["d2h_completed_worker_count"] == 8
assert transfer["d2h_bytes_total"] == 2206846976
assert transfer["h2d_restore_complete"] is False
print("parent_r5_l1_replay=pass")
PY
~~~

随后在 keep-alive 仍运行时完成：

1. frozen vLLM HEAD=`0decac0d96c42b49572498019f0a0e3600f50398`；vLLM-Ascend 安装态 9-file hash、
   SimpleCPUOffload connector/worker/copy backend import 与 R2 hybrid repair 全过；
2. observer self-test 的 wrapped scheduler methods 必须含 `update_connector_output`；
3. installed runtime method/signature probe 必须证明该方法存在且 observer 只在原返回后 snapshot；
4. 用公开 `wait-for-residency` 回放两类 bounded trace：
   - capture + snapshot + D2H complete + `CPU=0/GPU=64` -> exit 3 / `continue_pressure`；
   - capture + snapshot 但 D2H 未完成 -> exit 4 / `unobservable`，不得 pressure；
5. `decide-next` 必须证明 `continue_pressure + count=0 -> pressure_01`，而只有
   `trigger_ready + restore_allowed=true -> restore_follower`。

本节不得启动 NPU/vLLM 或发请求。任一失败定级
`blocked_p8_2_k1a_r5_l1_r1_source_or_resource_gate`，保持 keep-alive 原样并停止。

## 3. 资源前门与 keep-alive 安全暂退

记录 tracked HEAD/status、7000 端口、vLLM process、8 卡健康/HBM、MemAvailable/swap 和 keep-alive 所有
marker PID/PGID/设备号。要求模型路径可读、端口空闲、无残留 vLLM、8 卡健康、MemAvailable 不低于既有
384 GiB 门、swap 未用。

只允许终止已证明完全属于官方 keep-alive 的 process group；marker 必须覆盖 `#0#..#7#` 且没有未知命令。
不能证明就 blocked，不得发信号。不得触碰 unattended-upgrades 或其他进程。暂退后确认 16 marker 归零、
8 卡无运行进程、AICore 0、7000 空闲，再进入唯一 lifecycle。

## 4. 唯一 corrected lifecycle

固定 `lazy_offload=true`、`cpu_bytes_to_use=3444834304`、
`cpu_bytes_to_use_per_rank=430604288`。server argv SHA 必须继续为
`89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f`；其他配置与 parent 逐项相同。

准备全部 8 个冻结 body：warmup、target prime、pressure_01..pressure_05、restore follower。token count、bytes、
SHA-256 在 server start 前冻结；pressure 与 target 不共享 cacheable block；restore/target LCP 为 16384。
generated text/token IDs 不保留。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721_run01
cd "${REPO_ROOT}"
test ! -e "${RESULT_ROOT}"

set +e
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_r1_lazy_h2d.sh "${RESULT_ROOT}"
MODE_OR_CONTROLLER_EXIT=$?
set -e
printf '%s\n' "${MODE_OR_CONTROLLER_EXIT}" > "${RESULT_ROOT}/initial_runner_exit_code.txt"
~~~

controller 顺序：

~~~text
warmup
target_prime
等待 D2H store complete + 有效 residency snapshot
observable-not-ready -> pressure_01
每个 pressure 后重新读取 gate
CPU=64/GPU=0 -> restore_follower
否则按需 pressure_02 ... pressure_05
CPU target lost / truly unobservable / request failure / 上限未 trigger -> 停止且不 restore
~~~

每个已发送请求必须 HTTP 200、prompt/generated/streamed token 精确、finish reason=`length`、SSE done、MTP
activity、health/queue/counter continuity 全过。任一请求失败首错停止，无 retry。observer 不得改变原方法返回值、
异常、scheduler decision、request order 或 copy arguments。controller role marker 仍只含 role/schema/timestamp，
不含 raw hash 或 token 值；服务器随机 request ID 只作诊断。

## 5. Cleanup、keep-alive 恢复与延后 finalization

无论 Section 4 成败，先停止 vLLM、释放 7000、确认 residual=0 和 `cleanup_status.txt=clean`，再恢复官方 keep-alive：

~~~bash
set -euo pipefail
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

恢复后必须为 16 markers、`#0#..#7#`、8 卡健康、7000 空闲、无 vLLM residual、tracked clean，并写
`resource_recovery_summary.json`。随后才运行 R1 finalizer：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721_run01
PYTHON_BIN=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
cd "${REPO_ROOT}"

export P8_2_K1A_TASK_ID=p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721
export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-L1-R1
export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle
export P8_2_K1A_NO_SUCCESS_GRADE=red_p8_2_k1a_r5_l1_r1_lazy_h2d_no_success
export P8_2_K1A_CPU_TARGET_LOST_GRADE=red_p8_2_k1a_r5_l1_r1_cpu_target_lost
export P8_2_K1A_PARTIAL_GRADE=yellow_p8_2_k1a_r5_l1_r1_trigger_not_reached
export P8_2_K1A_EVIDENCE_INCOMPLETE_GRADE=red_p8_2_k1a_r5_l1_r1_h2d_evidence_incomplete

set +e
"${PYTHON_BIN}" tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py \
  finalize --artifact-dir "${RESULT_ROOT}"
FINALIZE_EXIT=$?
set -e
printf '%s\n' "${FINALIZE_EXIT}" > "${RESULT_ROOT}/finalize_exit_code.txt"
~~~

## 6. 分级与停止边界

- repository contract 失败：`blocked_p8_2_k1a_r5_l1_r1_repository_contract_gate`；
- provenance/source/resource 失败：`blocked_p8_2_k1a_r5_l1_r1_source_or_resource_gate`；
- 无成功请求：`red_p8_2_k1a_r5_l1_r1_lazy_h2d_no_success`；
- target 从 CPU tier 丢失：`red_p8_2_k1a_r5_l1_r1_cpu_target_lost`；
- pressure_05 后仍未 trigger：`yellow_p8_2_k1a_r5_l1_r1_trigger_not_reached`；
- 请求成功但 D2H/H2D/residency/cleanup 任一链不完整：
  `red_p8_2_k1a_r5_l1_r1_h2d_evidence_incomplete`；
- 只有所有实际请求首次成功、pressure 严格晚于 D2H complete、restore 严格晚于 CPU-only trigger、
  target GPU eviction、16K CPU hit/load、D2H/H2D 8-worker submit/enqueue/copy-enter/copy-return/poll/complete、
  load completion、repair/health/queue、cleanup/recovery 全过，才给
  `candidate_green_p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle`。

candidate green 仍只是服务器候选；不证明 CPU tier 自身 eviction、唯一根因、性能收益或普遍可用性。
不得自动进入 K2/P8.3-I1。

## 7. 小结果包、完整清单与传输停点

raw vLLM log、metrics、request bodies、raw trace、active role marker、generated output/token IDs 留服务器。候选范围
最多 16 files（15 payload + manifest），含 manifest 总量不超过 71680 bytes，全部标记
`bounded_operational_metadata_no_content_or_token_ids`。payload 可包括：

~~~text
result_summary.md
environment_and_hashes.json
request_body_manifest.json
request_summary.tsv
residency_gate_timeline.json
h2d_trigger_summary.json
transfer_trace_summary.json
connector_resolution_summary.json
mtp_queue_health_summary.json
repair_diagnostic_summary.json
host_memory_summary.json
grading_summary.json
cleanup_status.txt
resource_recovery_summary.json
first_failure_excerpt.txt（仅失败时）
candidate_manifest.server_local.json（控制文件）
~~~

`environment_and_hashes.json` 必须记录 task_id、HEAD、origin/main、ahead/behind、tracked-clean、runtime/commit、
canonical argv SHA、repo hashes 和 source hashes。完成后先报告精确 RESULT_ROOT、grade、首错、实际 request/pressure、
每项 gate、cleanup/recovery 和完整清单的 relative path/bytes/SHA-256/sensitivity/总量。

随后列出 `email / upload-api / server-local` 三种可用方法并推荐一种；在用户针对该完整范围明确选择前不得外发。
不得预先 upload-api、发状态邮件或失败后自动换渠道。

## 8. 完成后等待

~~~text
next_task_authorized=false
k2_authorized=false
p8_3_i1_authorized=false
performance_reference_accepted=false
cause_proven_as_unique=false
~~~

不得因为本任务 blocked/red/yellow 撤销既有 P6/P8 窄边界结论；不得进入 K2；不得进入 P8.3-I1；
不得自行执行下一任务。
