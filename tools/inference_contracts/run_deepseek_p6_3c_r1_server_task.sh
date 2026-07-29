#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=${P6_3C_TASK_ID:-p6_3c_r1_chunked_prefill_scheduler_pressure_2026_0728_run01}
REPORT_PREFIX=${P6_3C_REPORT_PREFIX:-P6_3C_R1}
EXPECTED_RUN_LABEL=${TASK_ID}
RUN_LABEL=$(basename -- "${RESULT_DIR}")
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
BASE_PYTHON=${BASE_PYTHON:-${ENV_PREFIX}/bin/python}
RUNNER=${P6_3C_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_scheduler_pressure.py}
EXPERIMENT=${P6_3C_EXPERIMENT:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_scheduler_pressure.sh}
SOURCE_PAYLOAD=${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json
CARD_IDS=(0 1 2 3 4 5 6 7)
CARD_IDS_CSV=0,1,2,3,4,5,6,7
EXPECTED_KEEP_ALIVE_MARKER_COUNT=16

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'expected_result_basename=%s\n' "${EXPECTED_RUN_LABEL}"
  printf 'npu_card_ids=%s\n' "${CARD_IDS_CSV}"
  printf 'keep_alive_stop_then_same_set_restore=true\n'
  printf 'formal_model_lifecycle_count_exact=6\n'
  printf 'engine_request_count_exact=90\n'
  printf 'batched_http_call_count_exact=48\n'
  printf 'request_retry_count_exact=0\n'
  printf 'result_transfer_authorized=true\n'
  printf 'automatic_transfer_allowed=false\n'
  printf 'transfer_method_selected=false\n'
  printf 'next_task_authorized=false\n'
  PYTHON_BIN=${PYTHON_BIN:-${BASE_PYTHON}} \
    P6_3C_AUDIT_ONLY=1 bash "${EXPERIMENT}" "${RESULT_DIR}"
}

if test "${P6_3C_SERVER_TASK_AUDIT_ONLY:-${P6_3C_R1_SERVER_TASK_AUDIT_ONLY:-0}}" = 1; then
  audit_contract
  exit 0
fi

test "${RUN_LABEL}" = "${EXPECTED_RUN_LABEL}"
test ! -e "${RESULT_DIR}"
test -x "${BASE_PYTHON}"
test -f "${RUNNER}"
test -f "${EXPERIMENT}"
test -f "${SOURCE_PAYLOAD}"
test "$(stat -c '%s' "${SOURCE_PAYLOAD}")" = 19487
test "$(sha256sum "${SOURCE_PAYLOAD}" | awk '{print $1}')" = \
  48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
test -x /data/node0_disk1/Public/npu_stop.sh
test -x /data/node0_disk1/Public/npu_keep_alive.sh
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = \
  "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
if ss -ltn | awk '$4 ~ /:7000$/ {found=1} END {exit !found}'; then
  echo "port 7000 is already in use" >&2
  exit 2
fi
if pgrep -af '[v]llm.*serve.*DeepSeek-V4-Flash-w8a8-mtp' >/dev/null; then
  echo "a DeepSeek-V4-Flash vLLM process is already running" >&2
  exit 2
fi

keep_alive_stopped=false
stop_attempted=false
experiment_started=false
experiment_pid=
stop_exit=0
restart_exit=0
experiment_exit=1
finalize_exit=1
package_exit=1

finish() {
  incoming_exit=$?
  trap - EXIT INT TERM
  set +e
  if test -n "${experiment_pid}" && kill -0 "${experiment_pid}" 2>/dev/null; then
    kill -TERM -- "-${experiment_pid}" 2>/dev/null
    for _ in $(seq 1 60); do
      kill -0 "${experiment_pid}" 2>/dev/null || break
      sleep 2
    done
    if kill -0 "${experiment_pid}" 2>/dev/null; then
      kill -KILL -- "-${experiment_pid}" 2>/dev/null
    fi
    wait "${experiment_pid}" 2>/dev/null
  fi

  restored_card_ids=
  if test "${stop_attempted}" = true; then
    bash /data/node0_disk1/Public/npu_keep_alive.sh "${CARD_IDS[@]}"
    restart_exit=$?
    if test "${restart_exit}" -eq 0; then
      restored_card_ids=${CARD_IDS_CSV}
    fi
  else
    restart_exit=0
  fi

  mkdir -p "${RESULT_DIR}/runtime/resource_recovery"
  recovery_dir=${RESULT_DIR}/runtime/resource_recovery
  marker_wait_seconds=0
  keep_alive_marker_count=0
  marker_card_ids=
  while test "${marker_wait_seconds}" -lt 30; do
    ps -eo args= > "${recovery_dir}/keep_alive_processes.txt" 2>&1
    keep_alive_marker_count=$(grep -Ec '#[0-7]#' \
      "${recovery_dir}/keep_alive_processes.txt" || true)
    marker_card_ids=
    for card in "${CARD_IDS[@]}"; do
      if grep -F "#${card}#" "${recovery_dir}/keep_alive_processes.txt" \
        >/dev/null 2>&1; then
        marker_card_ids=${marker_card_ids:+${marker_card_ids},}${card}
      fi
    done
    if test "${keep_alive_marker_count}" -eq \
      "${EXPECTED_KEEP_ALIVE_MARKER_COUNT}" && \
      test "${marker_card_ids}" = "${CARD_IDS_CSV}"; then
      break
    fi
    marker_wait_seconds=$((marker_wait_seconds + 1))
    sleep 1
  done
  ss -ltnp > "${recovery_dir}/listening_ports.txt" 2>&1
  port_7000_listener_count=$(awk \
    '$4 ~ /:7000$/ {count++} END {print count + 0}' \
    "${recovery_dir}/listening_ports.txt")
  pgrep -af '[v]llm.*serve.*DeepSeek-V4-Flash-w8a8-mtp' \
    > "${recovery_dir}/vllm_residual_processes.txt" 2>&1
  vllm_residual_process_count=$(wc -l \
    < "${recovery_dir}/vllm_residual_processes.txt" | tr -d ' ')
  if test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"; then
    tracked_worktree_clean=true
  else
    tracked_worktree_clean=false
  fi
  keep_alive_restored_exact=false
  if test "${stop_attempted}" = false; then
    keep_alive_restored_exact=true
  elif test "${restart_exit}" -eq 0 && \
    test "${keep_alive_marker_count}" -eq "${EXPECTED_KEEP_ALIVE_MARKER_COUNT}" && \
    test "${marker_card_ids}" = "${CARD_IDS_CSV}"; then
    keep_alive_restored_exact=true
  fi

  STOPPED_CARD_IDS="${keep_alive_stopped}" \
  RESTORED_CARD_IDS="${restored_card_ids}" \
  STOP_EXIT="${stop_exit}" \
  RESTART_EXIT="${restart_exit}" \
  KEEP_ALIVE_MARKER_COUNT="${keep_alive_marker_count}" \
  KEEP_ALIVE_RESTORED_EXACT="${keep_alive_restored_exact}" \
  PORT_LISTENER_COUNT="${port_7000_listener_count}" \
  VLLM_RESIDUAL_COUNT="${vllm_residual_process_count}" \
  TRACKED_CLEAN="${tracked_worktree_clean}" \
  EXPERIMENT_STARTED="${experiment_started}" \
  EXPERIMENT_EXIT="${experiment_exit}" \
  "${BASE_PYTHON}" - "${RESULT_DIR}/resource_recovery_summary.json" <<'PY'
import json
import os
import sys

def ints(value):
    return [int(item) for item in value.split(",") if item]

summary = {
    "stopped_card_ids": list(range(8)) if os.environ["STOPPED_CARD_IDS"] == "true" else [],
    "restored_card_ids": ints(os.environ["RESTORED_CARD_IDS"]),
    "stop_exit_code": int(os.environ["STOP_EXIT"]),
    "restart_exit_code": int(os.environ["RESTART_EXIT"]),
    "keep_alive_marker_count": int(os.environ["KEEP_ALIVE_MARKER_COUNT"]),
    "expected_keep_alive_marker_count": 16,
    "keep_alive_restored_exact": os.environ["KEEP_ALIVE_RESTORED_EXACT"] == "true",
    "port_7000_listener_count": int(os.environ["PORT_LISTENER_COUNT"]),
    "vllm_residual_process_count": int(os.environ["VLLM_RESIDUAL_COUNT"]),
    "tracked_worktree_clean": os.environ["TRACKED_CLEAN"] == "true",
    "formal_experiment_started": os.environ["EXPERIMENT_STARTED"] == "true",
    "experiment_exit_code": int(os.environ["EXPERIMENT_EXIT"]),
}
open(sys.argv[1], "w").write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY

  cleanup_status=clean
  if test "${port_7000_listener_count}" -ne 0 || \
    test "${vllm_residual_process_count}" -ne 0 || \
    test "${tracked_worktree_clean}" != true || \
    test "${keep_alive_restored_exact}" != true; then
    cleanup_status=incomplete
  fi
  printf '%s\n' "${cleanup_status}" > "${RESULT_DIR}/cleanup_status.txt"

  "${BASE_PYTHON}" "${RUNNER}" finalize --artifact-dir "${RESULT_DIR}"
  finalize_exit=$?
  "${BASE_PYTHON}" "${RUNNER}" package --artifact-dir "${RESULT_DIR}"
  package_exit=$?

  printf '%s_SERVER_REPORT_BEGIN\n' "${REPORT_PREFIX}"
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'head=%s\n' "$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  printf 'origin_main=%s\n' "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
  printf 'ahead_behind=%s\n' \
    "$(git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main)"
  printf 'experiment_exit=%s\n' "${experiment_exit}"
  printf 'finalize_exit=%s\n' "${finalize_exit}"
  printf 'package_exit=%s\n' "${package_exit}"
  printf 'stopped_card_ids=%s\n' "$([ "${keep_alive_stopped}" = true ] && printf '%s' "${CARD_IDS_CSV}")"
  printf 'restored_card_ids=%s\n' "${restored_card_ids}"
  printf 'keep_alive_restored_exact=%s\n' "${keep_alive_restored_exact}"
  printf '%s\n' 'grading_inputs:'
  cat "${RESULT_DIR}/grading_inputs.json"
  printf '%s\n' 'lifecycle_summary:'
  cat "${RESULT_DIR}/lifecycle_summary.tsv"
  if test -f "${RESULT_DIR}/startup_resource_summary.tsv"; then
    printf '%s\n' 'startup_resource_summary:'
    cat "${RESULT_DIR}/startup_resource_summary.tsv"
  fi
  printf '%s\n' 'mechanism_scheduler_summary:'
  cat "${RESULT_DIR}/mechanism_scheduler_summary.json"
  printf '%s\n' 'performance_mode_cell_summary:'
  cat "${RESULT_DIR}/performance_mode_cell_summary.tsv"
  printf '%s\n' 'performance_order_balanced_pairs:'
  cat "${RESULT_DIR}/performance_order_balanced_pairs.tsv"
  printf '%s\n' 'resource_recovery_summary:'
  cat "${RESULT_DIR}/resource_recovery_summary.json"
  printf '%s\n' 'result_summary_body:'
  cat "${RESULT_DIR}/result_summary.md"
  printf '%s\n' 'candidate_manifest:'
  cat "${RESULT_DIR}/candidate_manifest.server_local.json"
  printf 'candidate_manifest_bytes=%s\n' \
    "$(wc -c < "${RESULT_DIR}/candidate_manifest.server_local.json" | tr -d ' ')"
  printf 'candidate_manifest_sha256=%s\n' \
    "$(sha256sum "${RESULT_DIR}/candidate_manifest.server_local.json" | awk '{print $1}')"
  printf '%s_SERVER_REPORT_END\n' "${REPORT_PREFIX}"

  if test "${restart_exit}" -ne 0 || test "${package_exit}" -ne 0; then
    exit 5
  fi
  if test "${finalize_exit}" -ne 0; then
    exit "${finalize_exit}"
  fi
  exit "${incoming_exit}"
}
trap finish EXIT INT TERM

set +e
stop_attempted=true
bash /data/node0_disk1/Public/npu_stop.sh "${CARD_IDS[@]}"
stop_exit=$?
set -e
if test "${stop_exit}" -ne 0; then
  exit "${stop_exit}"
fi
keep_alive_stopped=true

setsid bash "${EXPERIMENT}" "${RESULT_DIR}" &
experiment_pid=$!
experiment_started=true
set +e
wait "${experiment_pid}"
experiment_exit=$?
set -e
experiment_pid=
exit "${experiment_exit}"
