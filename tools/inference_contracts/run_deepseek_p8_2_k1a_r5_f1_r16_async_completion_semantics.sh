#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
TASK_ID=p8_2_k1a_r5_f1_r16_async_completion_semantics_2026_0727
ANALYZER=${SCRIPT_DIR}/p8_2_k1a_r5_f1_r16_async_completion_adjudication.py
AUDIT=${REPO_ROOT}/benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r16_async_completion_semantics_audit.yaml
PARENT_ROOT=${P8_2_K1A_F1_R15_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725_run01}
PYTHON_BIN=${PYTHON_BIN:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python}
RESULT_DIR=$1

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=authorized_offline_r15_raw_trace_completion_adjudication\n'
  printf 'parent_task_id=p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725\n'
  printf 'parent_raw_trace_required=true\n'
  printf 'parent_source_sha_gate_required=true\n'
  printf 'npu_execution_authorized=false\n'
  printf 'vllm_server_start_authorized=false\n'
  printf 'model_requests_authorized=false\n'
  printf 'keep_alive_action=leave_running\n'
  printf 'h2d_poll_live_pending_is_diagnostic_only=true\n'
  printf 'async_completion_same_worker_sets_required=true\n'
  printf 'bounded_transfer_max_bytes=71680\n'
  printf 'result_transfer_authorized=true\n'
  printf 'transfer_method_selected=false\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K1A_F1_R16_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test -f "${ANALYZER}"
test -f "${AUDIT}"
test -x "${PYTHON_BIN}"
test -d "${PARENT_ROOT}"
test -d "${PARENT_ROOT}/runtime/offload_trace"
test ! -e "${RESULT_DIR}"

"${PYTHON_BIN}" "${ANALYZER}" analyze \
  --parent-root "${PARENT_ROOT}" \
  --output-dir "${RESULT_DIR}" \
  --audit "${AUDIT}"

cat "${RESULT_DIR}/task_grade.txt"
