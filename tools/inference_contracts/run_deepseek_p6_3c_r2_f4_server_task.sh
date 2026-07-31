#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}
BASE_SERVER_TASK=${P6_3C_R2_F4_BASE_SERVER_TASK:-${SCRIPT_DIR}/run_deepseek_p6_3c_r2_server_task.sh}
test -f "${BASE_SERVER_TASK}"

export REPO_ROOT
export ENV_PREFIX=${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1
unset BASE_PLUGIN_ROOT BASE_VLLM_ROOT
export P6_3C_TASK_ID=p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01
export P6_3C_REPORT_PREFIX=P6_3C_R2_F4
export P6_3C_EXPERIMENT_LABEL=P6_3C_R2_F4
export P6_3C_WORKLOAD_RELATIVE_PATH=benchmarks/deepseek_v4_flash/workloads/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_matched_ab.yaml
export P6_3C_REQUEST_ID_PREFIX=p6_3c_r2_f4
export P6_3C_ATOMIC_PAIR_ADMISSION=1
export P6_3C_ATOMIC_PAIR_REQUEST_PREFIX=p6_3c_r2_f4
export P6_3C_ATOMIC_PAIR_TIMEOUT_SECONDS=30
export P6_3C_ATOMIC_PAIR_ADMISSION_MODULE=p6_3c_r2_f4_atomic_pair_admission
export P6_3C_ATOMIC_PAIR_ENGINE_MARKER=_p6_3c_r2_f4_atomic_pair_installed
export P6_3C_ATOMIC_PAIR_PROC_MARKER=_p6_3c_r2_f4_atomic_pair_timeout_handler_installed
export P6_3C_ATOMIC_PAIR_ADMISSION_CONTROLLER=${SCRIPT_DIR}/p6_3c_r2_f4_atomic_pair_admission.py
export P6_3C_ATOMIC_PAIR_ADMISSION_PATCH=${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r2_f4_atomic_pair_admission_overlay.patch
export P6_3C_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_f4_atomic_pair_admission.py
export P6_3C_EXPERIMENT=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_f4_scheduler_pressure.sh

PYTHON_BIN=${PYTHON_BIN:-${ENV_PREFIX}/bin/python}
command -v "${PYTHON_BIN}" >/dev/null
P6_3C_ATOMIC_PAIR_REQUEST_PREFIX=p6_3c_r2_f4 \
  "${PYTHON_BIN}" - <<'PY'
from tools.inference_contracts.p6_3c_r2_f4_atomic_pair_admission import (
    normalize_atomic_pair_request_id,
)

observed = (
    "cmpl-p6_3c_r2_f4_mechanism_no_pressure_4k_4k_"
    "r01-0-a19f074f"
)
parsed = normalize_atomic_pair_request_id(observed)
assert parsed is not None
assert parsed.actual_request_id == observed
assert parsed.canonical_request_id == observed.rsplit("-", 1)[0]
assert parsed.pair_index == 0
assert parsed.runtime_suffix == "a19f074f"
assert normalize_atomic_pair_request_id(
    "cmpl-p6_3c_r2_f4_mechanism_no_pressure_4k_4k_r01-1-NOTHEX00"
) is None
print("request_id_fixture_gate=observed_8hex_suffix_normalized_strict")
PY

exec bash "${BASE_SERVER_TASK}" "$@"
