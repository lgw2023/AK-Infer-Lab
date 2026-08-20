#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

RESULT_DIR=$1
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
SOURCE_PAYLOAD=${SOURCE_PAYLOAD:-${REPO_ROOT}/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_w8a8_8card_no_mtp_tokenizer_mro_retry_v0221rc1_2026_0712/request_payload.json}
MODEL_NAME=${MODEL_NAME:-deepseek-v4-flash-w8a8-mtp}
REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f2_dependency_marker_canary.py}
MODE_RUNNER=${MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f2_mode.sh}
ANALYZER=${P6_3C_R3E_F2_ANALYZER:-${SCRIPT_DIR}/analyze_p6_3c_r3e_f2_dependency_markers.py}
TASK_ID=p6_3c_r3e_f2_request_scoped_dependency_marker_canary_2026_0820

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'S0=zero_npu_source_import_and_pickle_smoke\n'
  printf 'S1=f2_s1_01,admission_on_t4096,one_pressure_step\n'
  printf 'S1_gate=marker_8_of_8_and_full_host_runtime_actual_kernel_chain_8_of_8\n'
  printf 'S2=conditional_on_S1_only\n'
  printf 'S2_lifecycles=f2_s2_01_admission_on_t4096,f2_s2_02_persistent_on_t128\n'
  printf 'S2_pressure_steps_per_policy=2\n'
  printf 'maximum_model_lifecycles=3\n'
  printf 'budget_sweep=false\n'
  printf 'performance_comparison_allowed=false\n'
  printf 'result_transfer_authorized=true\n'
  P6_3C_R3E_F2_MODE_AUDIT_ONLY=1 \
    bash "${MODE_RUNNER}" /audit/f2 f2_s1_01 mechanism chunked_prefill_on admission_on_t4096
  P6_3C_R3E_F2_MODE_AUDIT_ONLY=1 \
    bash "${MODE_RUNNER}" /audit/f2 f2_s2_01 mechanism chunked_prefill_on admission_on_t4096
  P6_3C_R3E_F2_MODE_AUDIT_ONLY=1 \
    bash "${MODE_RUNNER}" /audit/f2 f2_s2_02 mechanism chunked_prefill_on persistent_on_t128
}

if test "${P6_3C_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -x "${PYTHON_BIN}"
test -f "${SOURCE_PAYLOAD}"
test -f "${REQUEST_RUNNER}"
test -f "${MODE_RUNNER}"
test -f "${ANALYZER}"
test -f "${P6_3C_R3E_F2_S0_EVIDENCE:?S0 evidence is required}"

"${PYTHON_BIN}" "${REQUEST_RUNNER}" prepare \
  --source-payload "${SOURCE_PAYLOAD}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name "${MODEL_NAME}"

cp "${P6_3C_R3E_F2_S0_EVIDENCE}" "${RESULT_DIR}/s0_source_import_smoke.json"
if test -f "${P6_3C_RUNTIME_LAYOUT_JSON:-}"; then
  cp "${P6_3C_RUNTIME_LAYOUT_JSON}" "${RESULT_DIR}/runtime_layout.json"
fi
if test -f "${P6_3C_RUNTIME_OVERLAY_PREFLIGHT_MANIFEST:-}"; then
  cp "${P6_3C_RUNTIME_OVERLAY_PREFLIGHT_MANIFEST}" \
    "${RESULT_DIR}/runtime_overlay_preflight_manifest.json"
fi
if test -f "${P6_3C_RUNTIME_OVERLAY_PREFLIGHT_SMOKE:-}"; then
  cp "${P6_3C_RUNTIME_OVERLAY_PREFLIGHT_SMOKE}" \
    "${RESULT_DIR}/runtime_overlay_preflight_smoke.json"
fi

printf 'stage\ttrack\tlifecycle_id\tevidence_track\tconfig_id\tmode\n' \
  > "${RESULT_DIR}/executed_lifecycle_schedule.tsv"
printf 'S1\tmechanism\tf2_s1_01\tdependency_marker_canary\tadmission_on_t4096\tchunked_prefill_on\n' \
  >> "${RESULT_DIR}/executed_lifecycle_schedule.tsv"

bash "${MODE_RUNNER}" \
  "${RESULT_DIR}" f2_s1_01 mechanism chunked_prefill_on admission_on_t4096

mkdir -p "${RESULT_DIR}/stage_analysis/s1"
"${PYTHON_BIN}" "${ANALYZER}" \
  --artifact-dir "${RESULT_DIR}" \
  --output-dir "${RESULT_DIR}/stage_analysis/s1" \
  --stage S1 \
  --lifecycle-id f2_s1_01

s2_authorized=$("${PYTHON_BIN}" - \
  "${RESULT_DIR}/stage_analysis/s1/marker_propagation_summary.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if payload.get("s2_authorized") is True else "false")
PY
)
printf '%s\n' "${s2_authorized}" > "${RESULT_DIR}/stage_analysis/s1/s2_authorized.txt"

if test "${s2_authorized}" != true; then
  printf '%s\n' 'S1 produced a complete bounded negative; S2 not authorized.' \
    > "${RESULT_DIR}/stage_analysis/s1/staged_stop_reason.txt"
  exit 0
fi

printf 'S2\tmechanism\tf2_s2_01\tdependency_marker_repetition\tadmission_on_t4096\tchunked_prefill_on\n' \
  >> "${RESULT_DIR}/executed_lifecycle_schedule.tsv"
bash "${MODE_RUNNER}" \
  "${RESULT_DIR}" f2_s2_01 mechanism chunked_prefill_on admission_on_t4096

printf 'S2\tmechanism\tf2_s2_02\tdependency_marker_repetition\tpersistent_on_t128\tchunked_prefill_on\n' \
  >> "${RESULT_DIR}/executed_lifecycle_schedule.tsv"
bash "${MODE_RUNNER}" \
  "${RESULT_DIR}" f2_s2_02 mechanism chunked_prefill_on persistent_on_t128
