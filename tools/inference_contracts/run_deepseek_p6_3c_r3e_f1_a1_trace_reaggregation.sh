#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 SOURCE_R3E_F1_RESULT OUTPUT_DIR [TRACE_WORKSPACE]" >&2
  exit 64
fi

SOURCE_RESULT=$1
OUTPUT_DIR=$2
TRACE_WORKSPACE=${3:-}
ENV_PREFIX=${ENV_PREFIX:-/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
RUNNER=tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation.py

test -x "${PYTHON_BIN}"
test -d "${SOURCE_RESULT}"
test ! -e "${OUTPUT_DIR}"

TRACE_ARGS=()
if [[ -n "${TRACE_WORKSPACE}" ]]; then
  test -d "${TRACE_WORKSPACE}"
  TRACE_ARGS=(--trace-workspace "${TRACE_WORKSPACE}")
fi

"${PYTHON_BIN}" "${RUNNER}" validate-only \
  --source-artifact-dir "${SOURCE_RESULT}" \
  --expected-ranks 8 \
  "${TRACE_ARGS[@]}"

"${PYTHON_BIN}" "${RUNNER}" reaggregate \
  --source-artifact-dir "${SOURCE_RESULT}" \
  --output-dir "${OUTPUT_DIR}" \
  --expected-ranks 8 \
  --top-n-ops 30 \
  "${TRACE_ARGS[@]}"

test -f "${OUTPUT_DIR}/candidate_manifest.server_local.json"
cat "${OUTPUT_DIR}/result_summary.md"
cat "${OUTPUT_DIR}/candidate_manifest.server_local.json"
