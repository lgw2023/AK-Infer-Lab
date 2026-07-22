#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723
LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.sh
MODE_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_simple_cpu_offload_mode.sh
REQUEST_RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r6_logical_keyspace_restore.py
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
CARD_IDS=(0 1 2 3 4 5 6 7)
CARD_IDS_CSV=0,1,2,3,4,5,6,7
EXPECTED_KEEP_ALIVE_MARKER_COUNT=16

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize\n'
  printf 'keep_alive_card_ids=%s\n' "${CARD_IDS_CSV}"
  printf 'keep_alive_marker_format=#card_id#\n'
  printf 'expected_keep_alive_marker_count=%s\n' \
    "${EXPECTED_KEEP_ALIVE_MARKER_COUNT}"
  printf 'same_card_set_restore_on_every_exit=true\n'
  printf 'resource_recovery_summary_always_recorded=true\n'
  printf 'finalize_after_recovery=true\n'
  P8_2_K1A_F1_R6_AUDIT_ONLY=1 bash "${LIFECYCLE}" "${RESULT_DIR}"
  P8_2_K1A_MODE_AUDIT_ONLY=1 \
  P8_2_K1A_TASK_ID="${TASK_ID}" \
  P8_2_K1A_CPU_BYTES_TO_USE=3444834304 \
  P8_2_K1A_CPU_BYTES_TO_USE_PER_RANK=430604288 \
  P8_2_K1A_LAZY_OFFLOAD=true \
  P8_2_K1A_ENABLE_H2D_RESIDENCY_OBSERVER=1 \
  P8_2_K1A_H2D_TARGET_BLOCK_COUNT=128 \
  P8_2_K1A_RESTORE_MATCH_TOKENS=16384 \
  P8_2_K1A_BLOCK_SIZE_TOKENS=128 \
  P8_2_K1A_REQUIRE_RESTORE_GROUP_ELIGIBILITY=1 \
  P8_2_K1A_REQUEST_COUNT_MIN=3 \
  P8_2_K1A_REQUEST_COUNT_MAX=4 \
    bash "${MODE_RUNNER}" "${RESULT_DIR}"
}

run_parent_and_contract_preflight() {
  P8_2_K1A_MODE_AUDIT_ONLY=1 bash "${LIFECYCLE}" "${RESULT_DIR}"
}

if test "${P8_2_K1A_F1_R6_SERVER_TASK_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -x /data/node0_disk1/Public/npu_stop.sh
test -x /data/node0_disk1/Public/npu_keep_alive.sh
test -x "${PYTHON_BIN}"
test -f "${LIFECYCLE}"
test -f "${REQUEST_RUNNER}"

run_parent_and_contract_preflight

keep_alive_stopped=false
stop_exit=1
restart_exit=1
experiment_exit=1

finish() {
  incoming_exit=$?
  trap - EXIT INT TERM
  set +e

  restored_card_ids=
  if test "${keep_alive_stopped}" = true; then
    bash "/data/node0_disk1/Public/npu_keep_alive.sh" "${CARD_IDS[@]}"
    restart_exit=$?
    if test "${restart_exit}" -eq 0; then
      restored_card_ids=${CARD_IDS_CSV}
    fi
  fi

  if test ! -d "${RESULT_DIR}"; then
    mkdir -p "${RESULT_DIR}"
  fi
  recovery_dir=${RESULT_DIR}/runtime/resource_recovery
  mkdir -p "${recovery_dir}"

  marker_card_ids=
  keep_alive_marker_count=0
  marker_wait_seconds=0
  while test "${marker_wait_seconds}" -lt 30; do
    ps -eo args= > "${recovery_dir}/keep_alive_processes.txt" 2>&1
    keep_alive_marker_count=$(grep -Ec '#[0-7]#' \
      "${recovery_dir}/keep_alive_processes.txt" || true)
    marker_card_ids=
    for card in "${CARD_IDS[@]}"; do
      if grep -F "#${card}#" "${recovery_dir}/keep_alive_processes.txt" \
        > /dev/null 2>&1; then
        if test -z "${marker_card_ids}"; then
          marker_card_ids=${card}
        else
          marker_card_ids=${marker_card_ids},${card}
        fi
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

  npu-smi info > "${recovery_dir}/npu_smi_info.txt" 2>&1
  npu_smi_exit=$?
  if test "${npu_smi_exit}" -eq 0; then
    healthy_card_ids=$(awk '
      $0 ~ /\|[[:space:]]*[0-7][[:space:]]+910B1[[:space:]]*\|/ &&
      $0 ~ /\|[[:space:]]*OK[[:space:]]*\|/ {print $2}
    ' "${recovery_dir}/npu_smi_info.txt" | sort -n -u | paste -sd, -)
  else
    healthy_card_ids=
  fi
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

  "${PYTHON_BIN}" "${REQUEST_RUNNER}" record-recovery \
    --artifact-dir "${RESULT_DIR}" \
    --stopped-card-ids "${CARD_IDS_CSV}" \
    --restored-card-ids "${restored_card_ids}" \
    --stop-exit-code "${stop_exit}" \
    --restart-exit-code "${restart_exit}" \
    --keep-alive-marker-count "${keep_alive_marker_count}" \
    --expected-keep-alive-marker-count 16 \
    --keep-alive-marker-card-ids "${marker_card_ids}" \
    --port-7000-listener-count "${port_7000_listener_count}" \
    --vllm-residual-process-count "${vllm_residual_process_count}" \
    --healthy-card-ids "${healthy_card_ids}" \
    --tracked-worktree-clean "${tracked_worktree_clean}"
  recovery_exit=$?

  finalize_exit=${incoming_exit}
  if test -f "${RESULT_DIR}/runtime/request_control/residency_gate_timeline.json"; then
    "${PYTHON_BIN}" "${REQUEST_RUNNER}" finalize \
      --artifact-dir "${RESULT_DIR}"
    finalize_exit=$?
    printf '%s\n' "${finalize_exit}" > "${RESULT_DIR}/finalize_exit_code.txt"
  fi
  printf '%s\n' "${experiment_exit}" > "${RESULT_DIR}/experiment_exit_code.txt"
  printf '%s\n' "${restart_exit}" > \
    "${RESULT_DIR}/keep_alive_restart_exit_code.txt"
  printf '%s\n' "${marker_wait_seconds}" > \
    "${RESULT_DIR}/keep_alive_marker_wait_seconds.txt"

  if test "${restart_exit}" -ne 0 || test "${recovery_exit}" -ne 0; then
    exit 5
  fi
  exit "${finalize_exit}"
}

trap finish EXIT INT TERM

keep_alive_stopped=true
set +e
bash "/data/node0_disk1/Public/npu_stop.sh" "${CARD_IDS[@]}"
stop_exit=$?
set -e
if test "${stop_exit}" -ne 0; then
  exit "${stop_exit}"
fi

set +e
bash "${LIFECYCLE}" "${RESULT_DIR}"
experiment_exit=$?
set -e
exit "${experiment_exit}"
