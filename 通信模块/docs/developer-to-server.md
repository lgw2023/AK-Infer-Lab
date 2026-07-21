# Developer to Server

## 当前唯一服务器动作：P8.2-K1A-R5-F1 raw pressure-window 归因与条件式 L2

~~~text
task_id: p8_2_k1a_r5_f1_pressure_window_conditional_l2_2026_0721
execution_mode: authorized_offline_raw_pressure_window_then_conditional_one_fixed_lifecycle
server_sync_review_authorized: true
offline_first: true
parent_r5_l1_r1_bounded_and_raw_replay_authorized: true
frozen_source_and_installed_runtime_audit_authorized: true
result_directory_creation_authorized: true
npu_execution_authorized: conditional
conditional_npu_gate: candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window_only
keep_alive_stop_and_restore_authorized: conditional
vllm_server_start_authorized: conditional
model_requests_authorized: conditional
formal_model_lifecycle_count_min: 0
formal_model_lifecycle_count_max: 1
pressure_request_count_exact: 1
model_request_count_min: 3
model_request_count_max: 4
model_request_count_exact_if_trigger_observed: 4
request_retry_count_exact: 0
runtime_overlay_authorized: true
runtime_behavior_patch_authorized: false
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

这是一个复合但 fail-closed 的任务：先在 keep-alive 不变、零 NPU、零 vLLM、零请求状态下，对
R5-L1-R1 的有界包、raw request windows、residency/eviction trace 和冻结 source 做原位归因。只有机器输出
`candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window`，才允许暂退 keep-alive 并运行一个预先冻结的
fixed-pressure L2 lifecycle。任何缺失、歧义或 blocked grade 都必须在零 NPU 处停止。

`result_transfer_authorized:true` 只表示最终完整有界包可进入渠道选择，不是 upload-api、email 或其他自动传输授权。

## 固定 NPU 占卡程序规则（每份服务器任务必须保留）

内部昇腾服务器上有低优先级 NPU 占卡程序在运行。任何需要使用 NPU 的任务都可以只停掉实际要使用的卡，
但无论任务成功、失败、中断或提前退出，任务结束后都必须在完全相同的卡号上重新拉起占卡程序。
末尾数字是卡号，应按实际需要删减；不使用 NPU 的分支不得停卡。本任务若进入 Section 4，将使用全部 8 卡，
因此停卡与恢复命令分别为：

~~~bash
# 停掉本任务实际使用的 0–7 卡上的低优先级占卡程序。
bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7

# 任务结束后，在完全相同的 0–7 卡上恢复占卡程序。
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

最终回报必须列出实际停卡卡号、实际恢复卡号与恢复状态。若 Section 4 未启动，必须报告未停卡且占卡程序保持运行。

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

R5-L1-R1 parent 必须原样保留：

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
parent_request_evidence_exact=true
parent_d2h_store_complete=true
parent_d2h_completed_worker_count=8
parent_d2h_bytes_total=6270674944
parent_store_event_completed_count=14
parent_after_target_prime_cpu_blocks=0
parent_after_target_prime_gpu_blocks=64
parent_after_pressure_01_cpu_blocks=0
parent_after_pressure_01_gpu_blocks=0
parent_cpu_target_eviction_observed=true
parent_actual_cpu_eviction_proven=false
parent_restore_sent=false
parent_h2d_restore_complete=false
parent_cleanup=clean
~~~

L2 固定 runtime/capacity 常量如下；这些值不得因离线候选而改变：

~~~text
kv_connector=SimpleCPUOffloadConnector
cpu_blocks_per_rank=128
cpu_bytes_to_use_per_rank=430604288
cpu_bytes_to_use_total=3444834304
required_restore_tokens=16384
block_size_tokens=128
lazy_offload=true
~~~

R1 已证明 controller 修复有效：`CPU=0/GPU=64` 保持 `continue_pressure`，且只在 D2H 8/8 完成后发送
`pressure_01`。新首错是请求后 target 终态为 `CPU=0/GPU=0`。这是终态观察，不等于已证明全量
CPU-tier eviction。本轮只回答：raw trace 中是否曾在首个 CPU-target eviction 之前出现完整
`CPU=64/GPU=0` 时间窗，并且是否能从该窗口的 GPU free-block delta 唯一推导一个非搜索 context。

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
  tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_pressure_window.py -q

python3 -m py_compile \
  tools/inference_contracts/p8_2_k1a_r5_f1_pressure_window.py \
  tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py \
  tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py

bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_pressure_window.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l2_fixed_pressure.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh
bash -n tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh

P8_2_K1A_R5_F1_AUDIT_ONLY=1 \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_pressure_window.sh \
  /tmp/opencode/p8_2_k1a_r5_f1_unused_result \
  > /tmp/opencode/p8_2_k1a_r5_f1_audit.txt

grep -Fx 'task_id=p8_2_k1a_r5_f1_pressure_window_conditional_l2_2026_0721' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'offline_first=true' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'npu_execution_authorized=conditional' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'formal_model_lifecycle_count_max=1' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'pressure_request_count_exact=1' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'request_count_min=3' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'request_count_max=4' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'request_count_exact_if_trigger_observed=4' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'terminal_pre_restore_request_count=3' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'request_retry_count=0' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'result_transfer_authorized=true' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'transfer_method_selected=false' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
grep -Fx 'next_task_authorized=false' /tmp/opencode/p8_2_k1a_r5_f1_audit.txt
~~~

冻结 repo 文件 SHA-256 必须逐项匹配后才能进入 Section 2：

~~~json
{
  "benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_pressure_window_audit.yaml": "5c19070df40f78a58b84478162296b7bcf9395f1674d405ff895ecb44baec8fd",
  "benchmarks/deepseek_v4_flash/workloads/p8_2_k1a_r5_f1_pressure_window_conditional_lifecycle.yaml": "96eeb14e39fc23de85ccd204092501e2f38baafe230b6be74c6efd8e6a779096",
  "tools/inference_contracts/p8_2_k1a_r5_f1_pressure_window.py": "362e8710bd716c15013f4ca995d81604afb46c5a1f954ec9befe2a25e8ac7fa9",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_pressure_window.sh": "9da4bdfa8597bdbb7e2c871241dbe0c22f4bf431bc14b4bc4b05ad89f0d78a18",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l2_fixed_pressure.sh": "d5dac2894d333e7b0b732d1b26994629b408b1843642198b5810a9bcc1da0654",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py": "94a045b3695d0d62946842a716aa8abf91dda63eb7500c8cfaee70830f975d41",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.sh": "04cce2dc5a6a632c06b9c35f1cbed4f268fa9854d9462fc0d1caec6bb0f0e0b7",
  "tools/inference_contracts/p8_2_k1a_h2d_residency_observer.py": "549b3fc0c5cb01b222f3310b882e3f86a6e5664ed05b0f3659e7dc689a10c2dd",
  "tools/inference_contracts/p8_2_k1a_simple_cpu_offload_observer.py": "b63c02e92c7f6d9ff4a161e3a418199eff8938c8ebcc8d9535c10ab38d125ee2",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py": "2707099971bf71cbec4add841907d864360e60d3e9eac0586ea3eb0c1c5f5ae7",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.sh": "0d190d51ad15d321fa25db94b82b0c0c6c5f7bbc271a0b6c739fd2d22d36999d",
  "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh": "d1c874110847d927f832b2675f12642e704bab8bff5b5f16b2b82c1a37c6d0dd",
  "tests/inference_contracts/test_deepseek_p8_2_k1a_r5_f1_pressure_window.py": "2b63b0ab3ca55201148b9737cadfdf93560a533bba8366ebe048319ecd8b57d4"
}
~~~

Section 1 任一失败：`blocked_p8_2_k1a_r5_f1_repository_contract_gate`；不得停 keep-alive。

## 2. Parent 有界包、raw tree 不变性与 pressure-window 归因（零 NPU）

parent bounded 与 raw 必须来自同一个已完成 R1 结果根；不得复制、改写、删除或重生 raw 证据。

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
PARENT_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l1_r1_lazy_h2d_trigger_lifecycle_2026_0721_run01
ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_pressure_window_2026_0721_run01
cd "${REPO_ROOT}"

test -d "${PARENT_ROOT}"
test -f "${PARENT_ROOT}/runtime/request_control/raw_request_results.jsonl"
test -d "${PARENT_ROOT}/runtime/request_control/raw_metrics"
test -n "$(find "${PARENT_ROOT}/runtime/offload_trace" -name 'h2d-residency.*.jsonl' -print -quit)"
test ! -e "${ANALYSIS_ROOT}"
test "$(sha256sum "${PARENT_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = 1209e22dc67aa1c15e80efcd26b453d7303665a5cd1a982ca2c41152334bb022

P8_2_K1A_R5_F1_PARENT_ROOT="${PARENT_ROOT}" \
P8_2_K1A_R5_F1_RAW_RESULT_ROOT="${PARENT_ROOT}" \
  bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_f1_pressure_window.sh \
  "${ANALYSIS_ROOT}"
~~~

analyzer 必须完成以下所有门：

1. 按 parent manifest 重算 14 个 payload 的 bytes/SHA-256/sensitivity；
2. 在分析前后对 parent raw tree 做 file-count/bytes/per-file SHA 聚合盘点，必须 byte-identical；
3. 用 `raw_metrics/*_before.prom` 与 `*_after.prom` 的 `mtime_ns` 重建 warmup、target-prime、pressure-01 时间窗；
4. 按 timestamp 归因 target capture、residency snapshot 和 CPU/GPU target eviction，不保留 raw hash 值；
5. 核对 target-prime 终态必须为 `CPU=0/GPU=64`；
6. 仅在首个 CPU-target eviction 之前有完整 `CPU=64/GPU=0` snapshot 时才认为有安全窗口；
7. target-prime 终态与第一个安全窗口的 GPU free-block delta 必须正数且唯一；
8. 固定 pressure context 只能用 `delta_blocks * 128 - 64 output tokens` 推导，不得搜索或人工挑数。

读取结果：

~~~bash
set -euo pipefail
ANALYSIS_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab/server_local/p8_2_k1a_r5_f1_pressure_window_2026_0721_run01
cat "${ANALYSIS_ROOT}/task_grade.txt"
python3 - "${ANALYSIS_ROOT}" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
grade = (root / "task_grade.txt").read_text().strip()
attribution = json.loads((root / "pressure_window_attribution.json").read_text())
candidate = json.loads((root / "pressure_candidate.json").read_text())
grading = json.loads((root / "grading_summary.json").read_text())
assert grading["server_grade"] == grade
assert grading["raw_source_evidence_unchanged"] is True
assert grading["npu_started"] is False
assert grading["model_request_sent"] is False
assert attribution["raw_hash_values_retained"] is False
print(json.dumps({
    "grade": grade,
    "safe_pressure_window_proven": attribution["safe_pressure_window_proven"],
    "pressure_cpu_target_peak_blocks": attribution["pressure_cpu_target_peak_blocks"],
    "pressure_gpu_target_min_blocks": attribution["pressure_gpu_target_min_blocks"],
    "cpu_target_eviction_event_count": attribution["cpu_target_eviction_event_count"],
    "candidate_pressure_total_blocks": candidate["candidate_pressure_total_blocks"],
    "candidate_pressure_context_tokens": candidate["candidate_pressure_context_tokens"],
    "formal_conditional_lifecycle_allowed": candidate["formal_conditional_lifecycle_allowed"],
}, indent=2, sort_keys=True))
PY
~~~

若 grade 不是 `candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window`，立即跳过 Section 3–5，不得停 keep-alive、
启动 vLLM/NPU 或发请求。有效 blocked grade 是 `blocked_p8_2_k1a_r5_f1_no_exact_pressure_window`；这不是新 runtime red。

## 3. Ready 分支的候选冻结、source/runtime 与资源前门

只在 Section 2 ready 时执行。先冻结 candidate：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_pressure_window_2026_0721_run01
L2_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l2_fixed_pressure_2026_0721_run01
cd "${REPO_ROOT}"

test "$(cat "${ANALYSIS_ROOT}/task_grade.txt")" = candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window
FIXED_CONTEXT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidate_pressure_context_tokens"])' "${ANALYSIS_ROOT}/pressure_candidate.json")
FIXED_BLOCKS=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidate_pressure_total_blocks"])' "${ANALYSIS_ROOT}/pressure_candidate.json")
test "${FIXED_CONTEXT}" -gt 0
test "${FIXED_CONTEXT}" -lt 131072
test "$((FIXED_BLOCKS * 128 - 64))" -eq "${FIXED_CONTEXT}"
test ! -e "${L2_ROOT}"
printf 'fixed_context=%s fixed_total_blocks=%s\n' "${FIXED_CONTEXT}" "${FIXED_BLOCKS}"
~~~

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

任一前门失败：`blocked_p8_2_k1a_r5_f1_source_or_provenance_gate`，保持 keep-alive 不变并停止。

## 4. Ready 分支的唯一 fixed-pressure L2 lifecycle

先执行上面的 `npu_stop.sh 0 1 2 3 4 5 6 7`，确认 8 卡空闲后，只允许执行下面一次：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_pressure_window_2026_0721_run01
L2_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l2_fixed_pressure_2026_0721_run01
cd "${REPO_ROOT}"

FIXED_CONTEXT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidate_pressure_context_tokens"])' "${ANALYSIS_ROOT}/pressure_candidate.json")
export P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS=${FIXED_CONTEXT}
export P8_2_K1A_R5_F1_ANALYSIS_ROOT=${ANALYSIS_ROOT}

set +e
bash tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l2_fixed_pressure.sh "${L2_ROOT}"
L2_RUNNER_EXIT=$?
set -e
printf '%s\n' "${L2_RUNNER_EXIT}" > "${L2_ROOT}/initial_runner_exit_code.txt"
~~~

server argv/capacity/runtime 必须与 R1 相同，canonical server argv SHA 仍为
`89a9a105da5a04a3207c638b6999858ed32bff0f438c2cfb617b03905d1efe2f`。唯一改变是从离线证据公式冻结的
pressure body context；不是 server 参数，不允许第二值或 sweep。

全部 body 必须在 server start 前生成并冻结 token count/bytes/SHA-256。顺序和请求上限为：

~~~text
warmup
target_prime
fixed_pressure
restore_follower
request_count_min=3
request_count_max=4
request_count_exact_if_trigger_observed=4
terminal_pre_restore_request_count=3
pressure_request_count_exact=1
request_retry_count_exact=0
~~~

fixed pressure 后仍必须由新 lifecycle 自身的 runtime observer 再次证明 `CPU=64/GPU=0`；否则禁止 restore 并停止。
此时三请求是合规终态，不得为了凑四请求绕过 trigger gate。
每个已发请求必须 HTTP 200、prompt/generated/streamed token 精确、finish reason=`length`、SSE done、MTP activity、
health/queue/counter continuity 全过。无 retry，无第五请求，无第二 lifecycle。

## 5. Cleanup、keep-alive 恢复与 L2 finalization

只要 Section 4 曾启动，无论成败都必须先停 vLLM、释放 7000、确认 residual=0 和 cleanup clean，再恢复：

~~~bash
bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7
~~~

恢复后必须是 16 markers、`#0#..#7#`、8 卡健康、7000 空闲、无 vLLM residual、tracked clean，且
`cleanup_status.txt=clean`。然后才可运行
finalizer，并必须重新传入同一 fixed context 与 single-pressure 环境：

~~~bash
set -euo pipefail

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
ANALYSIS_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_pressure_window_2026_0721_run01
L2_ROOT=${REPO_ROOT}/server_local/p8_2_k1a_r5_l2_fixed_pressure_2026_0721_run01
PYTHON_BIN=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python
cd "${REPO_ROOT}"

export P8_2_K1A_TASK_ID=p8_2_k1a_r5_f1_pressure_window_conditional_l2_2026_0721
export P8_2_K1A_STAGE_LABEL=P8.2-K1A-R5-L2
export P8_2_K1A_PRESSURE_CONTEXT_TOKENS=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidate_pressure_context_tokens"])' "${ANALYSIS_ROOT}/pressure_candidate.json")
export P8_2_K1A_PRESSURE_REQUEST_COUNT_MAX=1
export P8_2_K1A_CANDIDATE_GREEN=candidate_green_p8_2_k1a_r5_l2_fixed_pressure_h2d_trigger
export P8_2_K1A_NO_SUCCESS_GRADE=red_p8_2_k1a_r5_l2_fixed_pressure_no_success
export P8_2_K1A_CPU_TARGET_LOST_GRADE=red_p8_2_k1a_r5_l2_fixed_pressure_target_lost
export P8_2_K1A_PARTIAL_GRADE=red_p8_2_k1a_r5_l2_fixed_pressure_trigger_not_reached
export P8_2_K1A_EVIDENCE_INCOMPLETE_GRADE=red_p8_2_k1a_r5_l2_fixed_pressure_evidence_incomplete

set +e
"${PYTHON_BIN}" tools/inference_contracts/run_deepseek_p8_2_k1a_r5_l1_lazy_h2d.py \
  finalize --artifact-dir "${L2_ROOT}"
FINALIZE_EXIT=$?
set -e
printf '%s\n' "${FINALIZE_EXIT}" > "${L2_ROOT}/finalize_exit_code.txt"
~~~

## 6. 分级与停止边界

- repository 合同失败：`blocked_p8_2_k1a_r5_f1_repository_contract_gate`；
- parent/raw/source provenance 失败：`blocked_p8_2_k1a_r5_f1_source_or_provenance_gate`；
- 无完整或唯一 pressure window：`blocked_p8_2_k1a_r5_f1_no_exact_pressure_window`，零 NPU 停止；
- 离线窗口可行：`candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window`，才可条件式进入 L2；
- L2 无成功请求：`red_p8_2_k1a_r5_l2_fixed_pressure_no_success`；
- L2 target 终态丢失：`red_p8_2_k1a_r5_l2_fixed_pressure_target_lost`；
- L2 请求成功但 residency/H2D/cleanup 链不完整：`red_p8_2_k1a_r5_l2_fixed_pressure_evidence_incomplete`；
- 只有四请求首次成功、fixed pressure 前 D2H complete、pressure 后 runtime `CPU=64/GPU=0`、restore 为 16K CPU hit/load、
  D2H/H2D 8-worker submit/enqueue/copy/poll/complete、repair/MTP/health/queue 和 cleanup/recovery 全过，才给
  `candidate_green_p8_2_k1a_r5_l2_fixed_pressure_h2d_trigger`。

candidate green 仍只是服务器候选，不证明唯一根因、性能收益、普遍可用性或 K2 就绪。

## 7. 小结果包、完整清单与传输停点

raw vLLM log、raw metrics、request bodies、raw trace、active-role marker、generated output/token IDs 全部留服务器。

- 若 Section 2 blocked：只报告 `ANALYSIS_ROOT` 的 8 payload + manifest；
- 若 Section 4 执行：同时报告 `ANALYSIS_ROOT` 与 `L2_ROOT` 两个完整 manifest；
- 所有拟传文件合计不得超过 71680 bytes，每项必须含 relative/absolute path、bytes、SHA-256、sensitivity；
- sensitivity 只能为 `bounded_operational_metadata_no_content_or_token_ids`；
- manifest 自身也必须计入完整传输范围和总量。

完成后先报告 task id、HEAD/origin/tracked、各 section pass/fail、首错、offline grade、是否进入 L2、固定 context/
blocks、实际 lifecycle/request 数、D2H/H2D/residency/cleanup/recovery 以及完整候选清单。然后列出
`email / upload-api / server-local` 三种方法并推荐一种；用户未对该完整范围选择唯一渠道前，
不得外发、不得预先 upload-api、不得发状态邮件、失败后不得自动换渠道。

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
