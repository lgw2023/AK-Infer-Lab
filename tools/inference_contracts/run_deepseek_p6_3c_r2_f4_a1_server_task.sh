#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 2; then
  echo "usage: $0 SOURCE_RESULT_DIR DERIVED_RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
PYTHON_BIN=${PYTHON_BIN:-python3}
SOURCE_RESULT_DIR=$1
DERIVED_RESULT_DIR=$2
REVIEWER=${SCRIPT_DIR}/review_deepseek_p6_3c_r2_f4_adaptive_run.py

test -f "${REVIEWER}"
test -d "${SOURCE_RESULT_DIR}"
if test -e "${DERIVED_RESULT_DIR}"; then
  echo "derived result already exists: ${DERIVED_RESULT_DIR}" >&2
  exit 73
fi

cd "${REPO_ROOT}"

echo "task_id=p6_3c_r2_f4_a1_adaptive_acceptance_2026_0801"
echo "npu_required=false"
echo "keep_alive_action=leave_running"
echo "source_result_mutation_allowed=false"
echo "adaptive_execution_policy=docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md"

"${PYTHON_BIN}" "${REVIEWER}" \
  --source-result-dir "${SOURCE_RESULT_DIR}" \
  --validate-only >/dev/null

"${PYTHON_BIN}" "${REVIEWER}" \
  --source-result-dir "${SOURCE_RESULT_DIR}" \
  --derived-result-dir "${DERIVED_RESULT_DIR}"

test -f "${DERIVED_RESULT_DIR}/adaptive_execution_review.json"
test -f "${DERIVED_RESULT_DIR}/candidate_manifest.server_local.json"
echo "p6_3c_r2_f4_a1_complete=true"
