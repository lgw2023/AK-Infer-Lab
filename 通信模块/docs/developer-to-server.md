# Developer to Server

## 当前唯一服务器动作：同步并执行 P6.2 MTP profiled evidence

~~~text
task_id: p6_2_deepseek_v4_flash_w8a8_mtp_profiled_evidence_2026_0714
execution_mode: authorized_for_execution
workload: benchmarks/deepseek_v4_flash/workloads/p6_2_mtp_profiled_evidence.yaml
npu_execution_authorized: true
next_task_authorized: true
~~~

用户已明确授权 P6.2 MTP profiled evidence 服务器/NPU 执行。服务器必须先使用
`git fetch origin main` 与 `git merge --ff-only origin/main` 同步最终远程 `main`；
同步并通过全部硬门后立即执行当前唯一任务。不得使用 `pull-remote` alias、
`server_local_git_sync.sh`、reset、restore、stash、commit 或 push。

P6.1 已由开发机接受为 `green_mtp_unprofiled_baseline`：90/90 measured request、
24/24 batch、18/18 cell 全部首次成功，performance reference baseline 已成立。
本任务仅在三个代表 cell 上补齐 msprof、phase memory 和 request-device aggregate；
profiled latency 不回填 P6.1 性能表，不作为 P8 收益、瓶颈归因或硬件优先级结论。

## 1. 固定合同与宽松的任务内权限

三个 cell 各用一个 fresh profiler lifecycle，顺序为：

~~~text
short_prefill: 4096 input + 64 output + concurrency 1
long_prefill:  131072 input + 64 output + concurrency 1
decode_heavy:  4096 input + 256 output + concurrency 1
~~~

每个 lifecycle 内只有一个排除证据统计的 `4096+64` 显式 warmup 和一个 measured request；
无隐藏 warmup、无 request retry、无同 cell server restart。某个 cell 失败后，只要该 lifecycle
cleanup clean、port 7000 释放，就继续后续独立 cell，以尽量保全证据。

每个 lifecycle 都必须保持 DeepSeek-V4-Flash W8A8、NPU 0-7、TP8+EP、MTP、
`FULL_DECODE_ONLY`、`max_num_seqs=1`、prefix cache、chunked prefill 和已验收的 task-local overlay。
硬哈希不变：

~~~text
patch: 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
overlay proposer: 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
base proposer: 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
server command: 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19
source payload: 19487 bytes / 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
~~~

为减少无价值往返，服务器助手可直接修正任务内 server-local 的 `mkdir`、shell quoting、
`set -u` source 兼容、实际 msprof/SQLite 输出 parser 和等价错误处理；也可在不发新模型请求的前提下，
对同一 raw profiler 重跑离线 aggregate，或在 full aggregate 超时/失败后自动使用
`--skip-heavy-joins` 生成基础 request/device/task 摘要。所有适配必须记录在 result summary，并证明未改变
frozen runtime、body、cell、采样周期、请求语义或指标定义。

禁止修改 tracked 文件、runtime/site-packages、模型参数、MTP/graph/prefix/chunked-prefill 开关、
context/output、`max_num_seqs`、量化路径或 overlay。不得 eager fallback、版本升级、第二 patch、
自动进入 P6.3/P8/P9，也不得自动外发结果。

## 2. 同步、资源门与三个 profiled lifecycle

从一个 shell 完整执行以下区块：

~~~bash
set -euo pipefail

NPU_EXECUTION_AUTHORIZED=true
test "${NPU_EXECUTION_AUTHORIZED}" = true

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_2_deepseek_v4_flash_w8a8_mtp_profiled_evidence_2026_0714
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
ENV_PREFIX="${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1"
PYTHON_BIN="${ENV_PREFIX}/bin/python"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
SERVED_MODEL_NAME=deepseek-v4-flash-w8a8-mtp
WORKLOAD_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_2_mtp_profiled_evidence.yaml"
RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_2_profiled_evidence.py"
CELL_RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_2_profiled_cell.sh"
AGGREGATE_PATH="${REPO_ROOT}/tools/inference_contracts/analyze_msprof_request_device_aggregate.py"
PATCH_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch"
BASE_PROPOSER="${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend/spec_decode/llm_base_proposer.py"
PAYLOAD_PATH="${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json"

test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
git -C "${REPO_ROOT}" fetch origin main
git -C "${REPO_ROOT}" merge --ff-only origin/main
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
grep -F "task_id: ${TASK_ID}" "${REPO_ROOT}/通信模块/docs/developer-to-server.md"
grep -F "npu_execution_authorized: true" "${WORKLOAD_PATH}"
grep -F "next_task_authorized: true" "${WORKLOAD_PATH}"
test ! -e "${RESULT_DIR}"
mkdir -p "${RESULT_DIR}"/{source,analysis}

test "$(sha256sum "${PATCH_PATH}" | awk '{print $1}')" = 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
test "$(stat -c '%s' "${PAYLOAD_PATH}")" = 19487
test "$(sha256sum "${PAYLOAD_PATH}" | awk '{print $1}')" = 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
sha256sum "${PAYLOAD_PATH}" > "${RESULT_DIR}/source_payload_sha256.txt"

npu-smi info > "${RESULT_DIR}/npu_smi_before.txt" 2>&1
"${PYTHON_BIN}" - "${RESULT_DIR}/npu_smi_before.txt" "${RESULT_DIR}/resource_gate.json" <<'PY'
import json
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
health = {
    int(match.group(1)): match.group(2)
    for match in re.finditer(
        r"^\|\s*([0-7])\s+910B1\s+\|\s*(OK)\s+\|", text, re.MULTILINE
    )
}
idle = {int(value) for value in re.findall(r"No running processes found in NPU ([0-7])", text)}
result = {
    "health": health,
    "idle_devices": sorted(idle),
    "all_eight_healthy": health == {index: "OK" for index in range(8)},
    "all_eight_idle": idle == set(range(8)),
}
result["pass"] = result["all_eight_healthy"] and result["all_eight_idle"]
Path(sys.argv[2]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if result["pass"] else 2)
PY
if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
  printf '%s\n' blocked_port_7000 > "${RESULT_DIR}/first_failure_excerpt.txt"
  printf '%s\n' blocked_protocol_or_resource_gate > "${RESULT_DIR}/server_grade.txt"
  exit 2
fi

"${PYTHON_BIN}" "${RUNNER_PATH}" prepare \
  --source-payload "${PAYLOAD_PATH}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name "${SERVED_MODEL_NAME}"

set +u
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /usr/local/Ascend/nnal/atb/set_env.sh
set -u
command -v msprof >/dev/null

cells=(short_prefill long_prefill decode_heavy)
lifecycle_count=0
for cell_id in "${cells[@]}"; do
  cell_dir="${RESULT_DIR}/source/${cell_id}"
  msprof_root="/tmp/${TASK_ID}_${cell_id}_msprof"
  test ! -e "${msprof_root}"
  mkdir -p "${cell_dir}" "${msprof_root}"
  lifecycle_count=$((lifecycle_count + 1))
  printf '%s\n' "${lifecycle_count}" > "${RESULT_DIR}/server_lifecycle_count.txt"

  set +e
  msprof \
    --output "${msprof_root}" \
    --msproftx=on \
    --storage-limit=4096 \
    bash "${CELL_RUNNER_PATH}" "${RESULT_DIR}" "${cell_id}" \
    > "${cell_dir}/msprof_profiled_cell.log" 2>&1
  profiler_exit=$?
  set -e
  printf '%s\n' "${profiler_exit}" > "${cell_dir}/profiler_exit_code.txt"
  find "${msprof_root}" -type f -print 2>/dev/null | sort > "${cell_dir}/msprof_output_files.txt" || true
  du -ah "${msprof_root}" 2>/dev/null | sort -h > "${cell_dir}/msprof_du.txt" || true

  if test ! -f "${cell_dir}/cleanup_status.txt"; then
    printf '%s\n' incomplete > "${cell_dir}/cleanup_status.txt"
  fi
  if test "$(<"${cell_dir}/cleanup_status.txt")" != clean; then
    break
  fi
  if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
    printf '%s\n' port_7000_not_released >> "${RESULT_DIR}/first_failure_excerpt.txt"
    break
  fi
done

test "${lifecycle_count}" -le 3
first_command_hash="${RESULT_DIR}/source/short_prefill/runtime/server_command_sha256.txt"
if test -f "${first_command_hash}"; then
  cp "${first_command_hash}" "${RESULT_DIR}/server_command_sha256.txt"
fi
for cell_id in "${cells[@]}"; do
  command_hash="${RESULT_DIR}/source/${cell_id}/runtime/server_command_sha256.txt"
  if test -f "${command_hash}"; then
    test "$(awk '{print $1}' "${command_hash}")" = 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19
  fi
done

aggregate_exit=2
if test "${lifecycle_count}" -gt 0; then
  set +e
  if command -v timeout >/dev/null 2>&1; then
    timeout 45m "${PYTHON_BIN}" "${AGGREGATE_PATH}" \
      --run-id "${TASK_ID}" \
      --source-artifact-dir "${RESULT_DIR}/source" \
      --artifact-dir "${RESULT_DIR}/analysis" \
      --mode short_prefill --mode long_prefill --mode decode_heavy \
      --top-n-op-types 10 --workers 1 \
      > "${RESULT_DIR}/request_device_aggregate.log" 2>&1
  else
    "${PYTHON_BIN}" "${AGGREGATE_PATH}" \
      --run-id "${TASK_ID}" \
      --source-artifact-dir "${RESULT_DIR}/source" \
      --artifact-dir "${RESULT_DIR}/analysis" \
      --mode short_prefill --mode long_prefill --mode decode_heavy \
      --top-n-op-types 10 --workers 1 \
      > "${RESULT_DIR}/request_device_aggregate.log" 2>&1
  fi
  aggregate_exit=$?
  set -e

  if test "${aggregate_exit}" -ne 0; then
    printf '%s\n' "${aggregate_exit}" > "${RESULT_DIR}/full_aggregate_exit_code.txt"
    set +e
    if command -v timeout >/dev/null 2>&1; then
      timeout 15m "${PYTHON_BIN}" "${AGGREGATE_PATH}" \
        --run-id "${TASK_ID}_skip_heavy_joins" \
        --source-artifact-dir "${RESULT_DIR}/source" \
        --artifact-dir "${RESULT_DIR}/analysis" \
        --mode short_prefill --mode long_prefill --mode decode_heavy \
        --top-n-op-types 10 --workers 1 --skip-heavy-joins \
        > "${RESULT_DIR}/request_device_aggregate_fallback.log" 2>&1
    else
      "${PYTHON_BIN}" "${AGGREGATE_PATH}" \
        --run-id "${TASK_ID}_skip_heavy_joins" \
        --source-artifact-dir "${RESULT_DIR}/source" \
        --artifact-dir "${RESULT_DIR}/analysis" \
        --mode short_prefill --mode long_prefill --mode decode_heavy \
        --top-n-op-types 10 --workers 1 --skip-heavy-joins \
        > "${RESULT_DIR}/request_device_aggregate_fallback.log" 2>&1
    fi
    aggregate_exit=$?
    set -e
  fi
fi
printf '%s\n' "${aggregate_exit}" > "${RESULT_DIR}/aggregate_exit_code.txt"

cleanup_status=clean
for cell_id in "${cells[@]}"; do
  cell_cleanup="${RESULT_DIR}/source/${cell_id}/cleanup_status.txt"
  if test -f "${cell_cleanup}" && test "$(<"${cell_cleanup}")" != clean; then
    cleanup_status=incomplete
  fi
done
if ss -ltn | grep -Eq '[:.]7000[[:space:]]'; then
  cleanup_status=incomplete
fi

"${PYTHON_BIN}" "${RUNNER_PATH}" finalize \
  --artifact-dir "${RESULT_DIR}" \
  --cleanup-status "${cleanup_status}" \
  --aggregate-exit "${aggregate_exit}"

git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_after.txt"
test ! -s "${RESULT_DIR}/tracked_status_after.txt"
npu-smi info > "${RESULT_DIR}/npu_smi_after.txt" 2>&1 || true
~~~

## 3. 证据口径、停止与分级

P6.2 client 仅记录 token 数量、SSE 到达时间、request window、health/queue/metrics 和 MTP counters；
不保存 generated text 或 token IDs。MTP `num_speculative_tokens=1` 允许单个 SSE chunk 携带最多 2 个 token，
同 chunk token 共享同一 client-observed arrival timestamp。ITL 是 SSE delivery gap，不是 NPU decode-step latency。
每个 measured request 前后必须核对 `vllm:spec_decode_num_drafts_total`、
`vllm:spec_decode_num_draft_tokens_total`、`vllm:spec_decode_num_accepted_tokens_total`、
`vllm:num_requests_running` 和 `vllm:num_requests_waiting`。

phase memory 每 1.0s 发起一次 `npu-smi info` 八卡表 sweep，并采集 server root PID 及所有子进程的
RSS/PSS。以 sweep start/end 与 `request_start..first_token` / `first_token..response_end` 的区间重叠归档；
跨越 phase boundary 的 sweep 同时记入两个 phase，不丢弃。HBM 是 whole-device occupancy，
RSS/PSS 是 process-group footprint；它们不是 KV object bytes、HBM traffic 或单 request 精确分配。

raw msprof 仅留服务器。`duration_time`、task/op duration sum 和 AI Core metric 按 raw profiler 字段报告；
不得冒充用户 latency，不得在本任务直接写成 compute-bound、memory-bound、communication-bound 或优化收益。

分级：

- 请求前 resource/hash/parser/live-metrics 门失败：`blocked_protocol_or_resource_gate`。
- 三个 measured request 都未成功：`red_mtp_profiled_evidence_no_success`。
- 部分 cell、phase memory、SQLite/direct-overlap/request-device aggregate 不完整：
  `yellow_mtp_profiled_evidence_partial`。
- full aggregate 失败而同 raw 的 `--skip-heavy-joins` 基础聚合成功：
  `yellow_mtp_profiled_evidence_skip_heavy_joins`。
- 三 cell 全部首次成功，token/health/queue/MTP、三个 msprof SQLite root、每 cell direct overlap/
  request-device aggregate、prefill/decode phase memory 八卡解析和 cleanup 全过，才可给
  `candidate_green_mtp_profiled_evidence`。开发机复核后才能接受 `green_mtp_profiled_evidence`。

本任务任何失败都不撤销 P6.1 `green_mtp_unprofiled_baseline` 或 P6.1C-R1 official context green。

## 4. 结果回报与传输门

raw profiler tree、raw memory samples、raw metrics、server log、request bodies 和 raw token arrival 留在服务器。
候选小结果总和不得超过 71680 bytes，只允许 workload 中的有界结构化文件。
generated text 和 token IDs 不得进入小包。

不得发送 email、不得调用 upload-api、不得自动选择 `server-local`。完成后先在当前会话报告：

1. server grade 和三 cell 成功/失败摘要；
2. 每 cell profiler exit、SQLite/file count、request-device aggregate/direct overlap、phase memory 样本数与八卡解析；
3. MTP counter total、cleanup、raw result root 和任何 server-local 适配；
4. 精确 `result_summary.md` 路径、完整候选清单、逐文件 bytes/SHA-256/sensitivity、总 bytes；
5. 可用 `email / upload-api / server-local` 方法和一个推荐方法/理由。

等待用户对该完整范围重新选择唯一传输方法；不继承任何过去选择，失败后不得自动换方法。
