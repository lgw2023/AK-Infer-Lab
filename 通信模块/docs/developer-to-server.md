# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1-R3 运行中窗口中止与单次恢复

~~~text
task_id: p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722
execution_mode: authorized_single_lifecycle_inflight_trigger_abort_idle_restore
server_sync_review_authorized: true
offline_parent_gate_required: true
npu_execution_authorized: true
keep_alive_stop_authorized: true
vllm_server_start_authorized: true
model_requests_authorized: true
keep_alive_card_ids_exact: 0,1,2,3,4,5,6,7
formal_model_lifecycle_count_exact: 1
model_request_count_exact: 4
completed_request_count_exact: 3
intentional_pressure_abort_count_exact: 1
pressure_request_count_exact: 1
request_retry_count_exact: 0
payload_file_count_max: 15
pressure_context_tokens_exact: 36800
context_change_authorized: false
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

本任务只修正 F1-R2 已证明的观测点错位：fixed `36800` L2 在 `pressure_01` 运行中出现完整
`CPU=64/GPU=0`，旧 controller 却同步等待 pressure 返回后才采 gate，因此只看到 endpoint
`CPU=54/GPU=0 / cpu_target_lost`。本轮不得再调 context、不得 sweep，也不得把观测点错位写成唯一根因。

新 controller 必须按以下顺序完成：

~~~text
warmup success
-> target_prime success + D2H store complete
-> async pressure_01
-> request-local exact single-request CPU=64/GPU=0 one-shot trigger
-> abort pressure streaming connection
-> pressure client thread exits
-> engine queue returns idle
-> post-abort residency gate remains trigger_ready
-> switch role to restore_follower
-> exactly one restore request
~~~

`max_num_seqs=1`，所以 pressure 仍 active 时发送 restore 只会排队，且会让全局 role marker 产生歧义；
本任务明确禁止这种并发。active role 在 pressure client exit 和 engine idle 均确认前必须保持 `pressure_01`。

任一 progress 歧义、CPU target eviction、pressure 自然完成、中止未确认、engine 未 idle、post-abort 窗口
消失或 restore 失败都按对应 red grade 停止；不得 retry、不得第二 lifecycle、不得改路径换 run02。

## 固定 NPU keep-alive 规则

服务器上的低优先级 keep-alive 是常规运行管理。本任务使用 NPU 0–7，可以在执行前直接停止这八张卡上的
keep-alive；任务完成后恢复相同的 0–7 即可。无论成功、失败、中断或提前退出，都必须恢复完全相同的卡集，
并在最终回报中写明实际停卡卡号、实际恢复卡号与恢复状态。

~~~bash
# 本任务使用全部八卡，开始前执行。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 所有退出路径都恢复完全相同的卡集。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

命令末尾数字是卡号。不得扩大到其他节点或其他机器。

## 0. 已接受 parent 与本轮证据边界

以下事实不重跑、不改写：

~~~text
parent_task_id=p8_2_k1a_r5_f1_r2_trace_alignment_2026_0722
parent_grade=candidate_p8_2_k1a_r5_f1_r2_mid_request_window_endpoint_mismatch
lineage_r5_l1_r1_task_id=p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721
parent_f1_pool_delta_gate_fail_closed: true
parent_transfer_file_count=6
parent_transfer_total_bytes=24760
parent_manifest_sha256=9a4b5c43501f5fa441e397feffb398aadaf67f8d5292f5854fe9452701d1ddaa
fixed_pressure_context_tokens=36800
l2_cpu_only_snapshot_count=69
l2_cpu_only_first_offset_ns=2952631690
l2_first_cpu_target_eviction_offset_ns=20898026629
l2_cpu_only_window_lead_ns=17945394939
l2_endpoint_cpu_target_block_count=54
l2_endpoint_gpu_target_block_count=0
l2_endpoint_decision=cpu_target_lost
l2_restore_sent=false
unique_cause_proven=false
h2d_restore_mechanism_accepted=false
performance_reference_accepted=false
~~~

已关闭且必须继续保持关闭的上游口径如下；这些只是 lineage，不授权重跑：

~~~text
green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab
blocked_p6_3c_not_strict_single_variable
green_p8_1_r1_official_mtp_observe_only_matrix
green_p8_2_k0_order_balanced_prefix_cache_baseline
blocked_p8_2_k1_frozen_stack_import_incompatible
ready_p8_2_k1a_r2_allocator_capacity
green_p8_3_i0_checkpoint_inventory
green_p8_3_i0_r1_unclassified_taxonomy
candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout
candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility
candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure
red_p8_2_k1a_r5_l1_r1_cpu_target_lost
red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost
~~~

F1-R3 继续冻结上游 accepted-capacity 与 request-local 证据，不重新搜索或重跑这些父任务：

~~~text
offline_first: true
result_directory_creation_authorized: true
parent_r5_l1_r1_bounded_and_raw_replay_authorized: true
request_local_progress_analysis_authorized: true
parent_server_grade=red_p8_2_k1a_r5_l1_r1_cpu_target_lost
parent_request_count=3
parent_successful_request_count=3
parent_d2h_store_complete=true
parent_h2d_restore_complete=false
fixed_l2_cleanup=clean
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use_total=3444834304
restore_match_tokens_required=16384
pressure_request_count_exact=1
kv_connector=SimpleCPUOffloadConnector
manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b
block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283
lineage_runner=tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh
request_local_runner=tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.sh
~~~

R5-L1-R1 的有界包只作为已消费的父证据；当前直接 parent 是 F1-R2。不得进入 K2，
不得进入 P8.3-I1。

本轮只精确重放 R2 geometry/rendezvous/allocator 所冻结的容量与运行配置；不重新测容量。

F1-R2 服务器文字回报把 calibration/L2 raw trace 目录内文件总数各写为 20；bounded provenance 显示
analyzer 实际读取的 `h2d-residency.*.jsonl` 各为 10。后续回报需区分“目录总文件数”和“analyzer 读取的
residency JSONL 数”，不得混写；该口径差异不影响 F1-R2 grade。

## 1. 同步、tracked-clean 与仓库合同

只允许从干净 `main` 普通 fast-forward。不得 reset、stash、rebase、cherry-pick、server commit 或 push。
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

先在 keep-alive 仍运行时执行定向合同和语法门：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
cd "${REPO_ROOT}"

python3 -m pytest \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r2_trace_alignment.py \
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py

bash -n \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.sh

P8_2_K1A_F1_R3_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_r3_unused
~~~

audit-only 必须包含：

~~~text
task_id=p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722
npu_execution_authorized=true
formal_model_lifecycle_count_exact=1
model_request_count_exact=4
completed_request_count_exact=3
intentional_pressure_abort_count_exact=1
pressure_context_tokens=36800
request_retry_count_exact=0
request_local_inflight_trigger_required=true
pressure_abort_before_restore_required=true
engine_idle_before_restore_required=true
post_abort_cpu_only_window_required=true
context_change_authorized=false
pressure_search_or_sweep_authorized=false
result_transfer_authorized=true
transfer_method_selected=false
next_task_authorized=false
~~~

以下 repo 文件 SHA-256 必须精确匹配：

~~~text
30b800e7c1ff5289d5b5139edb8e3509cde6dfce92399fecbabc486c51cc2469  benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r3_inflight_abort_restore_audit.yaml
0de2285e219fb38bb27351924b667caeaa1b6b05251d910f698b90f027714bc6  benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_r3_inflight_abort_restore.yaml
fc61a1e33adbd5f84a8037c5282fa08dac413cc2a83bd3b02c78e41a291e6e64  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
39f3373ceed92b5d277185c3d9d3926ebda5bc06d2f3a28a136c505129aa9b60  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.sh
b6f7b6ac4e4277de58c9918aeb8c808d3dc84e119c8bd269594ad06a229d4525  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py
5435592911e388daa047fe6d976cc351ab41b8b34de1bee990cc010f66fa3055  benchmarks/deepseek_v4_flash/patches/p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch
~~~

Section 1 任一失败：报告 `blocked_p8_2_k1a_r5_f1_r3_repository_contract_gate` 并停止；不得停卡。

## 2. F1-R2 parent、资源与冻结配置前门（keep-alive 仍运行）

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
F1_R2_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r2_trace_alignment_2026_0722_run01
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
cd "${REPO_ROOT}"

test -d "${F1_R2_ROOT}"
test "$(sha256sum "${F1_R2_ROOT}/task_grade.txt" | awk '{print $1}')" = \
  3e348983bf313546abe4e8276ecdf14f80d14fa7ca80f91625c66d0c9a94a63b
test "$(sha256sum "${F1_R2_ROOT}/trace_alignment_summary.json" | awk '{print $1}')" = \
  da448a1f83e293a2bd33f0a26fb76f7ed75875f2347c2651995cc6ff90d4a863
test "$(sha256sum "${F1_R2_ROOT}/grading_summary.json" | awk '{print $1}')" = \
  b93d523fa482aa7e51ac7e21a22f7087f4961900c638c5dee8f8bba748c3708a
test "$(sha256sum "${F1_R2_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = \
  9a4b5c43501f5fa441e397feffb398aadaf67f8d5292f5854fe9452701d1ddaa
test -d "${MODEL_PATH}"
test -r "${MODEL_PATH}/config.json"
test -z "$(ss -ltnp | awk '$4 ~ /:7000$/ {print}')"
test -z "$(pgrep -af 'vllm.*serve.*DeepSeek-V4-Flash-w8a8-mtp' || true)"

python3 - "${F1_R2_ROOT}/trace_alignment_summary.json" <<'PY'
import json
from pathlib import Path
import sys

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert value["server_grade"] == "candidate_p8_2_k1a_r5_f1_r2_mid_request_window_endpoint_mismatch"
assert value["calibration_candidate_context_tokens"] == 36800
assert value["calibration_window_reproduced_in_fixed_l2"] is True
assert value["l2_cpu_only_before_first_cpu_eviction"] is True
assert value["l2_cpu_only_snapshot_count"] == 69
assert value["l2_cpu_only_first_offset_ns"] == 2952631690
assert value["l2_first_cpu_target_eviction_offset_ns"] == 20898026629
assert value["mid_request_window_to_endpoint_gate_mismatch_observed"] is True
assert value["l2_endpoint_decision"] == "cpu_target_lost"
assert value["unique_cause_proven"] is False
assert value["h2d_restore_mechanism_accepted"] is False
assert value["context_search_or_sweep_authorized"] is False
PY
~~~

同时按现有 accepted-capacity 前门复核：

- `vLLM=0.22.1+empty`，commit=`0decac0d96c42b49572498019f0a0e3600f50398`；
- `vLLM-Ascend=0.22.1rc1`，commit=`5f6faa0cb8830f667266f3b8121cd1383606f2a1`；
- `430604288 bytes/rank / 3444834304 bytes total`，128 CPU blocks/rank；
- canonical server argv SHA-256=`89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f`；
- TP8+EP、MTP=1、FULL_DECODE_ONLY、`max_model_len=135168`、`max_num_batched_tokens=4096`、
  `max_num_seqs=1`、block size=128、Chunked Prefill on、Prefix Cache on、lazy offload=true；
- installed source/import/connector/worker/copy backend、R2 repair、observer method resolution 全过；
- 8 卡健康、MemAvailable 不低于 384 GiB、swap 未用；keep-alive 当前覆盖 `#0#..#7#`。

Section 2 任一失败：报告 `blocked_p8_2_k1a_r5_f1_r3_parent_or_resource_gate` 并停止；不得停卡、不得猜相邻 run。

## 3. 唯一 F1-R3 lifecycle

结果根固定为 run01；存在即停止，不得覆盖或换 run02 重试。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722_run01
F1_R2_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r2_trace_alignment_2026_0722_run01
STOPPED_CARDS=()
RESTORE_EXIT=not_run

restore_keep_alive() {
  if test "${#STOPPED_CARDS[@]}" -gt 0; then
    set +e
    bash /data/node0_disk1/Public/npu_keep_alive.sh "${STOPPED_CARDS[@]}"
    RESTORE_EXIT=$?
    set -e
    if test "${RESTORE_EXIT}" = 0; then
      STOPPED_CARDS=()
    fi
  fi
}
trap restore_keep_alive EXIT INT TERM

cd "${REPO_ROOT}"
test ! -e "${RESULT_ROOT}"

bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7
STOPPED_CARDS=(0 1 2 3 4 5 6 7)

set +e
P8_2_K1A_F1_R2_ROOT="${F1_R2_ROOT}" \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.sh \
  "${RESULT_ROOT}"
RUN_EXIT=$?
set -e
printf '%s\n' "${RUN_EXIT}" > "${RESULT_ROOT}/initial_runner_exit_code.txt"

# mode runner 已在自身 EXIT trap 中清理 vLLM；现在恢复相同的 0–7。
restore_keep_alive
test "${RESTORE_EXIT}" = 0
trap - EXIT INT TERM

test "$(cat "${RESULT_ROOT}/cleanup_status.txt")" = clean
test -z "$(ss -ltnp | awk '$4 ~ /:7000$/ {print}')"
test -z "$(pgrep -af 'vllm.*serve.*DeepSeek-V4-Flash-w8a8-mtp' || true)"
~~~

上式通过即记录 `cleanup_status.txt=clean`。

正常 candidate 路径必须精确形成四个 role：

~~~text
warmup=success
target_prime=success
pressure_01=aborted_on_trigger
restore_follower=success
~~~

pressure 的预期 `aborted_on_trigger` 是本合同要求的有意中止，不是第四个完整请求。其硬门包括：

- trigger 来自 `request_local_pressure_progress`；`contract_role=pressure_01`；
- `scheduled_request_count=1`、`request_local_progress_exact=true`；
- `target_block_count=64 / CPU=64 / GPU=0`；
- 中止时 pressure thread 仍 active，未见完整 response / `[DONE]`；
- socket shutdown 后 client thread 必须退出，queue running/waiting 都回到 0；
- idle 前 role 不得切换；idle 后 post-abort gate 仍须 `trigger_ready`；
- restore 只允许一次，必须在 post-abort gate 之后。

## 4. 恢复核对与 finalization

确认 keep-alive 的 16 个 process markers 完整覆盖 `#0#..#7#`，8 卡健康、7000 空闲、无 vLLM residual、
tracked clean。然后写 recovery summary 并 finalization：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722_run01
PYTHON_BIN=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
cd "${REPO_ROOT}"

KEEP_ALIVE_MARKERS=$(ps -eo args= | grep -E '#[0-7]#' | grep -v grep | wc -l)
test "${KEEP_ALIVE_MARKERS}" -eq 16
for card in 0 1 2 3 4 5 6 7; do
  ps -eo args= | grep -F "#${card}#" | grep -v grep >/dev/null
done

PORT_FREE=true
VLLM_RESIDUAL=0
TRACKED_CLEAN=true
test -z "$(ss -ltnp | awk '$4 ~ /:7000$/ {print}')" || PORT_FREE=false
VLLM_RESIDUAL=$(pgrep -af 'vllm.*serve.*DeepSeek-V4-Flash-w8a8-mtp' | wc -l || true)
test -z "$(git status --porcelain --untracked-files=no)" || TRACKED_CLEAN=false

"${PYTHON_BIN}" - \
  "${RESULT_ROOT}/resource_recovery_summary.json" \
  "${KEEP_ALIVE_MARKERS}" "${PORT_FREE}" "${VLLM_RESIDUAL}" "${TRACKED_CLEAN}" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

output, marker_count, port_free, residual, tracked_clean = sys.argv[1:]
npu = subprocess.run(["npu-smi", "info"], text=True, capture_output=True)
value = {
    "stopped_card_ids": list(range(8)),
    "restored_card_ids": list(range(8)),
    "keep_alive_marker_count": int(marker_count),
    "keep_alive_restored_exact": int(marker_count) == 16,
    "port_7000_free": port_free == "true",
    "vllm_residual_process_count": int(residual),
    "all_eight_npu_healthy": npu.returncode == 0,
    "tracked_worktree_clean": tracked_clean == "true",
    "generated_content_retained": False,
    "token_ids_retained": False,
}
Path(output).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
assert value["keep_alive_restored_exact"]
assert value["port_7000_free"]
assert value["vllm_residual_process_count"] == 0
assert value["all_eight_npu_healthy"]
assert value["tracked_worktree_clean"]
PY

set +e
"${PYTHON_BIN}" \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py \
  finalize --artifact-dir "${RESULT_ROOT}"
FINALIZE_EXIT=$?
set -e
printf '%s\n' "${FINALIZE_EXIT}" > "${RESULT_ROOT}/finalize_exit_code.txt"
cat "${RESULT_ROOT}/result_summary.md"
~~~

允许的机器 grade 以首个失败点为准，主要包括：

~~~text
candidate_green_p8_2_k1a_r5_f1_r3_inflight_abort_restore
red_p8_2_k1a_r5_f1_r3_request_local_progress_ambiguous
red_p8_2_k1a_r5_f1_r3_cpu_target_lost
red_p8_2_k1a_r5_f1_r3_pressure_completed_without_trigger
red_p8_2_k1a_r5_f1_r3_inflight_trigger_timeout
red_p8_2_k1a_r5_f1_r3_pressure_abort_not_confirmed
red_p8_2_k1a_r5_f1_r3_pressure_not_idle_after_abort
red_p8_2_k1a_r5_f1_r3_window_lost_after_abort
red_p8_2_k1a_r5_f1_r3_h2d_evidence_incomplete
red_p8_2_k1a_r5_f1_r3_cleanup_or_recovery_incomplete
~~~

candidate green 也只接受一个 accepted-capacity lifecycle 内的 in-flight trigger→abort→idle→restore H2D
机制候选；不证明唯一根因、性能收益、普遍稳定性、K2 或 P8.3-I1 就绪。

## 5. 有界包、完整清单与传输停点

raw vLLM log、raw metrics、request bodies、raw trace、active-role marker、客户端 timing、request IDs、
generated output 和 token IDs 全部留服务器本地。候选 payload 最多 15 个，加 manifest 后最多 16 个，
完整 transfer 总量必须包含 manifest 且不超过 `71680 bytes`。

用 manifest 逐文件复核并输出完整清单：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
RESULT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r3_inflight_abort_restore_2026_0722_run01
python3 - "${RESULT_ROOT}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
manifest_path = root / "candidate_manifest.server_local.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
rows = []
for name, expected in sorted(manifest["files"].items()):
    path = root / name
    size = path.stat().st_size
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert size == expected["bytes"]
    assert digest == expected["sha256"]
    rows.append((name, size, digest, expected["sensitivity"]))
manifest_size = manifest_path.stat().st_size
manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
total = sum(row[1] for row in rows) + manifest_size
assert len(rows) <= 15
assert len(rows) + 1 <= 16
assert total <= 71680
for row in rows:
    print("\t".join(map(str, row)))
print("candidate_manifest.server_local.json", manifest_size, manifest_sha,
      "bounded_operational_metadata_no_content_or_token_ids", sep="\t")
print(f"transfer_file_count={len(rows) + 1}")
print(f"transfer_total_bytes={total}")
PY
~~~

最终回报必须一次性包含：

1. HEAD、`origin/main`、ahead/behind、tracked-clean；
2. F1-R2 四个 parent 文件现场 SHA-256 与 parent grade；
3. repo hash/test/compile/Bash/audit-only 各 section pass/fail；
4. 实际 lifecycle/request/完整请求/有意中止/retry 数；
5. trigger 的 progress before/scheduled/after、CPU/GPU、pressure start→trigger 延迟；
6. pressure abort requested/confirmed、client exit、engine idle、post-abort gate、restore sent 的精确顺序；
7. restore CPU hit/load、D2H/H2D worker/pipeline/completion 与最终 grade；
8. cleanup、7000、vLLM residual、八卡健康、实际停卡集合、实际恢复集合和恢复状态；
9. `result_summary.md` 绝对路径，以及完整候选范围每个文件的 path/bytes/SHA-256/sensitivity；
10. 可选方法 `email` / `upload-api` / `server-local`，推荐 `server-local`，因为结果已经在服务器且 raw 大产物无需移动。

`result_transfer_authorized:true` 只表示完整有界包可供选择，不选择渠道。报告完整清单后暂停，等待用户对
同一完整范围明确选择 email / upload-api / server-local；不得先发状态邮件、不得自动上传、不得拆分，
失败后不得自动换渠道。

## 6. 完成后停止

~~~text
next_task_authorized=false
k2_authorized=false
p8_3_i1_authorized=false
performance_reference_accepted=false
cause_proven_as_unique=false
~~~

任务完成后不要自动进入下一轮。
