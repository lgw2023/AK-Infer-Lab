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
  printf 'repository_input_sha_gate_required=true\n'
  printf 'npu_execution_authorized=false\n'
  printf 'vllm_server_start_authorized=false\n'
  printf 'model_requests_authorized=false\n'
  printf 'keep_alive_action=leave_running\n'
  printf 'h2d_poll_live_pending_is_diagnostic_only=true\n'
  printf 'async_completion_same_worker_sets_required=true\n'
  printf 'result_package_self_verification_required=true\n'
  printf 'copy_ready_server_report_emitted=true\n'
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

HEAD_SHA=$(git -C "${REPO_ROOT}" rev-parse HEAD)
ORIGIN_MAIN_SHA=$(git -C "${REPO_ROOT}" rev-parse origin/main)
test "${HEAD_SHA}" = "${ORIGIN_MAIN_SHA}"
test -z "$(
  git -C "${REPO_ROOT}" status --porcelain --untracked-files=no
)"

"${PYTHON_BIN}" "${ANALYZER}" preflight \
  --parent-root "${PARENT_ROOT}" \
  --audit "${AUDIT}"

if test "${P8_2_K1A_F1_R16_PREFLIGHT_ONLY:-0}" = 1; then
  exit 0
fi

"${PYTHON_BIN}" "${ANALYZER}" analyze \
  --parent-root "${PARENT_ROOT}" \
  --output-dir "${RESULT_DIR}" \
  --audit "${AUDIT}"

"${PYTHON_BIN}" "${ANALYZER}" verify-output \
  --output-dir "${RESULT_DIR}"

END_HEAD_SHA=$(git -C "${REPO_ROOT}" rev-parse HEAD)
END_ORIGIN_MAIN_SHA=$(git -C "${REPO_ROOT}" rev-parse origin/main)
test "${END_HEAD_SHA}" = "${HEAD_SHA}"
test "${END_ORIGIN_MAIN_SHA}" = "${ORIGIN_MAIN_SHA}"
test "${END_HEAD_SHA}" = "${END_ORIGIN_MAIN_SHA}"
test -z "$(
  git -C "${REPO_ROOT}" status --porcelain --untracked-files=no
)"

printf '%s\n' 'R16_SERVER_REPORT_BEGIN'
printf 'HEAD=%s\n' "${END_HEAD_SHA}"
printf 'origin_main=%s\n' "${END_ORIGIN_MAIN_SHA}"
printf 'ahead_behind=0 0\n'
printf 'tracked_clean=true\n'
printf 'npu_started=false\n'
printf 'vllm_started=false\n'
printf 'model_requests_sent=0\n'
printf 'stopped_card_ids=[]\n'
printf 'restored_card_ids=[]\n'
printf 'keep_alive_action=leave_running\n'
printf 'result_summary_path=%s\n' "${RESULT_DIR}/result_summary.md"
cat "${RESULT_DIR}/result_summary.md"
printf '%s\n' 'R16_GRADING_SUMMARY'
cat "${RESULT_DIR}/grading_summary.json"
printf '%s\n' 'R16_ASYNC_COMPLETION_ADJUDICATION'
cat "${RESULT_DIR}/async_completion_adjudication_summary.json"
printf '%s\n' 'R16_WORKER_COMPLETION_ROLLUP'
cat "${RESULT_DIR}/worker_completion_rollup.json"
printf '%s\n' 'R16_SOURCE_EVIDENCE_PROVENANCE'
cat "${RESULT_DIR}/source_evidence_provenance.json"
printf '%s\n' 'R16_COMPLETE_CANDIDATE_MANIFEST'
cat "${RESULT_DIR}/candidate_manifest.server_local.json"
printf '%s\n' 'R16_SERVER_REPORT_END'
