# Developer to Server

## 当前唯一服务器动作：同步并执行 P6.1 MTP unprofiled baseline

~~~text
task_id: p6_1_deepseek_v4_flash_w8a8_mtp_unprofiled_baseline_2026_0714
execution_mode: authorized_for_execution
workload: benchmarks/deepseek_v4_flash/workloads/p6_1_mtp_unprofiled_baseline.yaml
npu_execution_authorized: true
next_task_authorized: true
~~~

用户已明确授权 P6.1 MTP unprofiled baseline 服务器/NPU 执行。服务器必须先使用
`git fetch origin main` 与 `git merge --ff-only origin/main` 同步最终远程 `main`；
同步并通过全部硬门后立即执行当前唯一任务，不需要再为 pilot 到 matrix 的自动扩展等待一次确认。

P6.1C-R1 已由开发机接受为 `green_mtp_official_context_ladder`，最高稳定上下文为 131072，
official MTP 功能/容量/稳定性 reference baseline 已成立。本任务只建立同一冻结 runtime 的
unprofiled streaming 性能 reference；不是 profiler、P8、优化 A/B 或瓶颈归因任务。

## 1. 固定范围与宽松执行边界

固定模型与 runtime 不变：DeepSeek-V4-Flash W8A8、NPU 0-7、TP8+EP、MTP、
`FULL_DECODE_ONLY`、`max_num_seqs=1`、prefix cache、chunked prefill，以及已验收的单行
task-local overlay。server command SHA-256 必须仍为：

~~~text
patch: 75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1
overlay proposer: 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
base proposer: 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb
server command: 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19
source payload: 19487 bytes / 48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
~~~

执行计划为一个 fresh lifecycle：显式 `4096+64+c1` warmup 一次并排除统计；随后 pilot
三个 cell 各 3 个 batch，pilot 全部功能/证据门通过后立即自动扩展到完整 18-cell matrix。
pilot 已覆盖的 3 个 cell 不再重复，其他 15 个 cell 各执行一个 batch：

~~~text
pilot:
  4096+64+c1 x 3 batches
  65536+64+c4 x 3 batches
  131072+64+c1 x 3 batches

matrix:
  context = 4096 / 65536 / 131072
  output = 64 / 256
  concurrency = 1 / 4 / 8
~~~

总预算为 1 warmup batch、24 measured batches、90 measured requests、0 retry。若 pilot 失败，
停止 matrix；matrix 中某个独立 cell 失败后，只要原 server 仍存活、health=200、metrics 完整且
running=waiting=0，就继续后续 cell，以尽量保全证据。不得重启 server、重试请求、改参数、
改 body、关闭 MTP、降低 context/output/concurrency、修改 `max_num_seqs`、eager fallback、
升级版本、运行 HBM sampler/profiler 或进入 P8。

为减少无价值往返，服务器助手可直接修正 server-local runner/调用脚手架中的 `mkdir`、shell
quoting、`set -u` source 兼容、实际命令输出 parser 和等价的错误处理问题，不必再次等待开发者；
但必须把修正及其不改变 frozen hash、runtime、body、矩阵和指标定义的证明写入结果摘要。
任何需要修改 tracked 文件、runtime/site-packages、模型参数、请求语义或性能口径的修复仍须停止。

## 2. 同步、资源、hash、执行与清理

从一个 shell 完整执行以下区块。不得运行 `pull-remote` alias、
`通信模块/server_local_git_sync.sh`、reset、restore、stash、commit 或 push。

~~~bash
set -euo pipefail

NPU_EXECUTION_AUTHORIZED=true
test "${NPU_EXECUTION_AUTHORIZED}" = true

REPO_ROOT=/data/node0_disk1/liguowei/AK-Infer-Lab
TASK_ID=p6_1_deepseek_v4_flash_w8a8_mtp_unprofiled_baseline_2026_0714
RESULT_DIR="${REPO_ROOT}/server_local/${TASK_ID}"
ENV_PREFIX="${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1"
PYTHON_BIN="${ENV_PREFIX}/bin/python"
VLLM_BIN="${ENV_PREFIX}/bin/vllm"
BASE_PLUGIN_ROOT="${ENV_PREFIX}/lib/python3.11/site-packages/vllm_ascend"
BASE_PROPOSER="${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py"
MODEL_PATH=/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp
SERVED_MODEL_NAME=deepseek-v4-flash-w8a8-mtp
HOST=127.0.0.1
PORT=7000
WORKLOAD_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/workloads/p6_1_mtp_unprofiled_baseline.yaml"
RUNNER_PATH="${REPO_ROOT}/tools/inference_contracts/run_deepseek_p6_1_unprofiled_baseline.py"
PATCH_PATH="${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch"
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
mkdir -p "${RESULT_DIR}"/{runtime,raw_metrics,request_errors}

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
CANN_GENERATED_PYTHONPATH="${PYTHONPATH:-}"
OVERLAY_ROOT="${RESULT_DIR}/runtime/overlay_root"
mkdir -p "${OVERLAY_ROOT}"
cp -a "${BASE_PLUGIN_ROOT}" "${OVERLAY_ROOT}/vllm_ascend"
OVERLAY_PROPOSER="${OVERLAY_ROOT}/vllm_ascend/spec_decode/llm_base_proposer.py"
patch -p1 -d "${OVERLAY_ROOT}" --dry-run < "${PATCH_PATH}" > "${RESULT_DIR}/runtime/patch_dry_run.txt"
patch -p1 -d "${OVERLAY_ROOT}" < "${PATCH_PATH}" > "${RESULT_DIR}/runtime/patch_apply.txt"
test "$(sha256sum "${OVERLAY_PROPOSER}" | awk '{print $1}')" = 7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02
test "$(sha256sum "${BASE_PROPOSER}" | awk '{print $1}')" = 0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb

export PYTHONPATH="${OVERLAY_ROOT}:${CANN_GENERATED_PYTHONPATH}"
export PYTHONNOUSERSITE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_PLUGINS=ascend,ascend_kv_connector,ascend_model_loader,ascend_service_profiling,ascend_model
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

cmd=(
  "${VLLM_BIN}" serve "${MODEL_PATH}"
  --safetensors-load-strategy prefetch
  --max-model-len 135168
  --max-num-batched-tokens 4096
  --served-model-name "${SERVED_MODEL_NAME}"
  --gpu-memory-utilization 0.92
  --max-num-seqs 1
  --data-parallel-size 1
  --tensor-parallel-size 8
  --enable-expert-parallel
  --quantization ascend
  --host "${HOST}"
  --port "${PORT}"
  --block-size 128
  --enable-chunked-prefill
  --enable-prefix-caching
  --tokenizer-mode deepseek_v4
  --tool-call-parser deepseek_v4
  --enable-auto-tool-choice
  --reasoning-parser deepseek_v4
  --async-scheduling
  --additional-config '{"enable_flashcomm1":true,"enable_dsa_cp":true,"enable_cpu_binding":true,"multistream_overlap_shared_expert":false}'
  --model-loader-extra-config '{"enable_multithread_load":true,"num_threads":16}'
  --compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[2,4,6,8,10,12,14,16,18,20,22,24,32,36,40]}'
  --speculative-config '{"method":"mtp","num_speculative_tokens":1}'
)
printf '%q ' "${cmd[@]}" > "${RESULT_DIR}/runtime/server_command.txt"
printf '\n' >> "${RESULT_DIR}/runtime/server_command.txt"
sha256sum "${RESULT_DIR}/runtime/server_command.txt" > "${RESULT_DIR}/server_command_sha256.txt"
test "$(awk '{print $1}' "${RESULT_DIR}/server_command_sha256.txt")" = 370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19

setsid "${cmd[@]}" > "${RESULT_DIR}/runtime/vllm_server.log" 2>&1 &
server_pid=$!
printf '%s\n' "${server_pid}" > "${RESULT_DIR}/runtime/server_pid.txt"
printf '%s\n' 1 > "${RESULT_DIR}/server_lifecycle_count.txt"
ready_exit=1
for _ in $(seq 1 180); do
  kill -0 "${server_pid}" 2>/dev/null || break
  if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    ready_exit=0
    break
  fi
  sleep 10
done
printf '%s\n' "${ready_exit}" > "${RESULT_DIR}/runtime/server_ready_exit_code.txt"

run_exit=2
if test "${ready_exit}" -eq 0; then
  set +e
  curl -fsS "http://${HOST}:${PORT}/metrics" > "${RESULT_DIR}/runtime/live_metrics_preflight.prom"
  metrics_preflight_exit=$?
  for metric_name in \
    'vllm:spec_decode_num_drafts_total' \
    'vllm:spec_decode_num_draft_tokens_total' \
    'vllm:spec_decode_num_accepted_tokens_total' \
    'vllm:num_requests_running' \
    'vllm:num_requests_waiting'; do
    grep -F "${metric_name}" "${RESULT_DIR}/runtime/live_metrics_preflight.prom" >/dev/null
    test "$?" -eq 0 || metrics_preflight_exit=2
  done
  set -e
  printf '%s\n' "${metrics_preflight_exit}" > "${RESULT_DIR}/runtime/live_metrics_preflight_exit_code.txt"
  if test "${metrics_preflight_exit}" -eq 0; then
    set +e
    "${PYTHON_BIN}" "${RUNNER_PATH}" run \
      --artifact-dir "${RESULT_DIR}" \
      --base-url "http://${HOST}:${PORT}" \
      --server-pid "${server_pid}"
    run_exit=$?
    set -e
  else
    printf '%s\n' blocked_protocol_or_resource_gate > "${RESULT_DIR}/server_grade.txt"
    printf '%s\n' live_metrics_preflight_failed > "${RESULT_DIR}/first_failure_excerpt.txt"
  fi
else
  printf '%s\n' red_mtp_unprofiled_server_not_ready > "${RESULT_DIR}/server_grade.txt"
fi

kill -TERM -- "-${server_pid}" 2>/dev/null || true
for _ in $(seq 1 60); do
  kill -0 "${server_pid}" 2>/dev/null || break
  sleep 2
done
if kill -0 "${server_pid}" 2>/dev/null; then
  kill -KILL -- "-${server_pid}" 2>/dev/null || true
fi
if kill -0 "${server_pid}" 2>/dev/null; then
  printf '%s\n' incomplete > "${RESULT_DIR}/cleanup_status.txt"
else
  printf '%s\n' clean > "${RESULT_DIR}/cleanup_status.txt"
fi

"${PYTHON_BIN}" "${RUNNER_PATH}" finalize \
  --artifact-dir "${RESULT_DIR}" \
  --cleanup-status "$(<"${RESULT_DIR}/cleanup_status.txt")" \
  --run-exit "${run_exit}"

git -C "${REPO_ROOT}" status --porcelain --untracked-files=no > "${RESULT_DIR}/tracked_status_after.txt"
test ! -s "${RESULT_DIR}/tracked_status_after.txt"
npu-smi info > "${RESULT_DIR}/npu_smi_after.txt" 2>&1 || true
~~~

## 3. 指标、分级与回报

client 固定请求 `/v1/completions`，只累计 token-ID 数量和到达时间，不保存 token IDs 或 generated text。TTFT、TPOT、
ITL、E2EL、per-request output throughput、batch output throughput 与 request throughput 均按
workload 的 `time.monotonic_ns` 公式计算。concurrency>1 的 E2EL 包含排队时间；这正是当前
冻结 `max_num_seqs=1` reference 的一部分，不允许偷偷提高 server concurrency 参数。

每个 batch 前后核对 `/health`、running/waiting 及三项 speculative counters。pilot 的
request/batch 指标报原值、min/median/max/mean/CV；n<20 的 request-level 分布不报 P95/P99；
ITL 只有同时报告样本数时才可报 P50/P95/P99。不得与历史 no-MTP control 做性能收益比较。

分级：pilot 未完整通过不得进入 matrix；matrix 部分失败为
`yellow_mtp_unprofiled_matrix_partial`。18 个 cell 均有代表、24 个 measured batch 和 90 个
measured request 全部首次成功、token/stream/finish/timestamp、health/queue/metrics/MTP 与
cleanup 全过，服务器才给 `candidate_green_mtp_unprofiled_baseline`。只有开发机复核后才能接受
`green_mtp_unprofiled_baseline` 并把 performance reference baseline 置为 true。任何失败不撤销
P6.1C-R1 的 official 功能/容量/稳定性 green。

raw timestamps、raw metrics、server log、request bodies 和错误正文留在服务器。候选小结果总和
不得超过 71680 bytes，只允许 workload 列出的结构化文件。
generated text 和 token IDs 不得进入结果包；runner 生成的 `delivery_candidates.tsv` 只用于报告候选范围。
不得发送 email、不得调用 upload-api、不得自动选择 `server-local`。完成后先在当前会话
报告：精确 `result_summary.md` 路径、完整候选清单、逐文件 bytes/SHA-256/sensitivity、总 bytes、
可用 `email / upload-api / server-local` 方法及一个推荐方法和理由，等待用户对该完整范围作新的
单一方法选择。

服务器最终回复还要包含：同步后的 HEAD/origin、tracked 状态、资源/hash/overlay/server command
门、server lifecycle/PID/ready、warmup、pilot 9 batch、matrix 18 cell/24 measured batch/90 request
汇总、失败后是否继续的依据、MTP counter 总量、cleanup、server grade、raw result root，以及任何
server-local runner 脚手架适配。开发机没有运行 NPU，服务器结果仍须独立复核。
