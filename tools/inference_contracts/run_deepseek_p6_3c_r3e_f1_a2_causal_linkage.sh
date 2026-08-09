#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "usage: $0 SOURCE_R3E_F1_RESULT SOURCE_R3E_F1_A1_RESULT OUTPUT_DIR [TRACE_WORKSPACE]" >&2
  exit 64
fi

SOURCE_RESULT=$1
SOURCE_A1_RESULT=$2
OUTPUT_DIR=$3
TRACE_WORKSPACE=${4:-}
ENV_PREFIX=${ENV_PREFIX:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
RUNNER=tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a2_causal_linkage.py

test -x "${PYTHON_BIN}"
test -d "${SOURCE_RESULT}"
test -d "${SOURCE_A1_RESULT}"
test ! -e "${OUTPUT_DIR}"

TRACE_ARGS=()
if [[ -n "${TRACE_WORKSPACE}" ]]; then
  test -d "${TRACE_WORKSPACE}"
  TRACE_ARGS=(--trace-workspace "${TRACE_WORKSPACE}")
fi

"${PYTHON_BIN}" "${RUNNER}" validate-only \
  --source-artifact-dir "${SOURCE_RESULT}" \
  --source-a1-result "${SOURCE_A1_RESULT}" \
  --expected-ranks 8 \
  "${TRACE_ARGS[@]}"

"${PYTHON_BIN}" "${RUNNER}" analyze \
  --source-artifact-dir "${SOURCE_RESULT}" \
  --source-a1-result "${SOURCE_A1_RESULT}" \
  --output-dir "${OUTPUT_DIR}" \
  --expected-ranks 8 \
  "${TRACE_ARGS[@]}"

# Packaging is intentionally the final write.  If a task-local adaptation
# updates adaptive_execution_review.json, run this command again afterward.
"${PYTHON_BIN}" "${RUNNER}" package --output-dir "${OUTPUT_DIR}"

test -f "${OUTPUT_DIR}/candidate_manifest.server_local.json"
cat "${OUTPUT_DIR}/result_summary.md"
cat "${OUTPUT_DIR}/candidate_manifest.server_local.json"
