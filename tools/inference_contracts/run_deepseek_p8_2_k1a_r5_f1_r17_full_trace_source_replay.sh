#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
TASK_ID=p8_2_k1a_r5_f1_r17_full_trace_source_replay_2026_0727
ANALYZER=${SCRIPT_DIR}/p8_2_k1a_r5_f1_r17_full_trace_source_replay.py
AUDIT=${REPO_ROOT}/benchmarks/deepseek_v4_flash/p8_2_k1a_r5_f1_r17_full_trace_source_replay_audit.yaml
R15_ROOT=${P8_2_K1A_F1_R15_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725_run01}
R16_ROOT=${P8_2_K1A_F1_R16_ROOT:-${REPO_ROOT}/server_local/p8_2_k1a_r5_f1_r16_async_completion_semantics_2026_0727_run01}
PYTHON_BIN=${PYTHON_BIN:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1/bin/python}
RESULT_DIR=$1

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=authorized_offline_r15_complete_trace_source_replay\n'
  printf 'r15_parent_task_id=p8_2_k1a_r5_f1_r15_restore_step_lineage_2026_0725\n'
  printf 'r16_parent_task_id=p8_2_k1a_r5_f1_r16_async_completion_semantics_2026_0727\n'
  printf 'canonical_trace_reader=combined_json_else_all_jsonl\n'
  printf 'dual_trace_file_family_coverage_required=true\n'
  printf 'r15_replay_field_parity_required=true\n'
  printf 'coverage_mismatch_is_mechanism_red=false\n'
  printf 'parent_source_sha_gate_required=true\n'
  printf 'repository_input_sha_gate_required=true\n'
  printf 'npu_execution_authorized=false\n'
  printf 'vllm_server_start_authorized=false\n'
  printf 'model_requests_authorized=false\n'
  printf 'keep_alive_action=leave_running\n'
  printf 'result_package_self_verification_required=true\n'
  printf 'copy_ready_server_report_emitted=true\n'
  printf 'bounded_transfer_max_bytes=71680\n'
  printf 'result_transfer_authorized=true\n'
  printf 'transfer_method_selected=false\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K1A_F1_R17_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test -f "${ANALYZER}"
test -f "${AUDIT}"
test -x "${PYTHON_BIN}"
test -d "${R15_ROOT}"
test -d "${R15_ROOT}/runtime/offload_trace"
test -d "${R16_ROOT}"
test ! -e "${RESULT_DIR}"

HEAD_SHA=$(git -C "${REPO_ROOT}" rev-parse HEAD)
ORIGIN_MAIN_SHA=$(git -C "${REPO_ROOT}" rev-parse origin/main)
read -r AHEAD_COUNT BEHIND_COUNT <<EOF
$(git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main)
EOF
test "${HEAD_SHA}" = "${ORIGIN_MAIN_SHA}"
test "${AHEAD_COUNT}" = 0
test "${BEHIND_COUNT}" = 0
test -z "$(
  git -C "${REPO_ROOT}" status --porcelain --untracked-files=no
)"

"${PYTHON_BIN}" "${ANALYZER}" preflight \
  --r15-root "${R15_ROOT}" \
  --r16-root "${R16_ROOT}" \
  --audit "${AUDIT}"

if test "${P8_2_K1A_F1_R17_PREFLIGHT_ONLY:-0}" = 1; then
  exit 0
fi

"${PYTHON_BIN}" "${ANALYZER}" analyze \
  --r15-root "${R15_ROOT}" \
  --r16-root "${R16_ROOT}" \
  --output-dir "${RESULT_DIR}" \
  --audit "${AUDIT}"

"${PYTHON_BIN}" "${ANALYZER}" verify-output \
  --output-dir "${RESULT_DIR}"

END_HEAD_SHA=$(git -C "${REPO_ROOT}" rev-parse HEAD)
END_ORIGIN_MAIN_SHA=$(git -C "${REPO_ROOT}" rev-parse origin/main)
read -r END_AHEAD_COUNT END_BEHIND_COUNT <<EOF
$(git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main)
EOF
test "${END_HEAD_SHA}" = "${HEAD_SHA}"
test "${END_ORIGIN_MAIN_SHA}" = "${ORIGIN_MAIN_SHA}"
test "${END_HEAD_SHA}" = "${END_ORIGIN_MAIN_SHA}"
test "${END_AHEAD_COUNT}" = 0
test "${END_BEHIND_COUNT}" = 0
test -z "$(
  git -C "${REPO_ROOT}" status --porcelain --untracked-files=no
)"

printf '%s\n' 'R17_SERVER_REPORT_BEGIN'
printf 'HEAD=%s\n' "${END_HEAD_SHA}"
printf 'origin_main=%s\n' "${END_ORIGIN_MAIN_SHA}"
printf 'ahead_behind=%s %s\n' "${END_AHEAD_COUNT}" "${END_BEHIND_COUNT}"
printf 'tracked_clean=true\n'
printf 'npu_started=false\n'
printf 'vllm_started=false\n'
printf 'model_requests_sent=0\n'
printf 'stopped_card_ids=[]\n'
printf 'restored_card_ids=[]\n'
printf 'keep_alive_action=leave_running\n'
printf 'result_summary_path=%s\n' "${RESULT_DIR}/result_summary.md"
cat "${RESULT_DIR}/result_summary.md"
printf '%s\n' 'R17_GRADING_SUMMARY'
cat "${RESULT_DIR}/grading_summary.json"
printf '%s\n' 'R17_FULL_TRACE_REPLAY'
cat "${RESULT_DIR}/full_trace_replay_summary.json"
printf '%s\n' 'R17_TRACE_SOURCE_COVERAGE'
cat "${RESULT_DIR}/trace_source_coverage_summary.json"
printf '%s\n' 'R17_WORKER_COMPLETION_ROLLUP'
cat "${RESULT_DIR}/worker_completion_rollup.json"
printf '%s\n' 'R17_SOURCE_EVIDENCE_PROVENANCE'
cat "${RESULT_DIR}/source_evidence_provenance.json"
printf '%s\n' 'R17_COMPLETE_CANDIDATE_MANIFEST'
cat "${RESULT_DIR}/candidate_manifest.server_local.json"
printf '%s\n' 'R17_SERVER_REPORT_END'
