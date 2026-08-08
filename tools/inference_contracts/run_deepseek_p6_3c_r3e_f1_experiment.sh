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
REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f1_profile_completion.py}
MODE_RUNNER=${MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_f1_mode.sh}
SOURCE_R3E_RESULT=${P6_3C_R3E_SOURCE_RESULT:-/data/node0_disk1/liguowei/AK-Infer-Lab/server_results/p6_3c_r3e_2026_0808_attempt_03/p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01}
TASK_ID=p6_3c_r3e_f1_request_scoped_profile_completion_2026_0808_run01

schedule() {
  cat <<'EOF'
profile_f1_01	admission_on_t4096	chunked_prefill_on
profile_f1_02	persistent_on_t128	chunked_prefill_on
EOF
}

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'source_task_id=p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01\n'
  printf 'source_host_lifecycles_reused=host_01,host_02,host_03\n'
  printf 'new_model_lifecycle_count_exact=2\n'
  printf 'new_engine_request_count_including_warmup_exact=20\n'
  printf 'new_http_request_count_including_warmup_exact=6\n'
  printf 'request_retry_count_exact=0\n'
  printf 'capacity_contract=max_model_len_12288,max_num_batched_tokens_12288,max_num_seqs_9\n'
  printf 'profiler_backend=vllm_torch_profile_api\n'
  printf 'model_loading_profiled=false\n'
  printf 'profile_control=/start_profile_then_measured_trial_then_/stop_profile\n'
  printf 'performance_comparison_allowed=false\n'
  printf 'result_transfer_authorized=true\n'
  while IFS=$'\t' read -r lifecycle_id policy_id mode; do
    P6_3C_R3E_F1_MODE_AUDIT_ONLY=1 \
      bash "${MODE_RUNNER}" \
      /audit/p6_3c_r3e_f1 "${lifecycle_id}" mechanism "${mode}" "${policy_id}"
  done < <(schedule)
}

if test "${P6_3C_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -d "${SOURCE_R3E_RESULT}"
test -f "${SOURCE_R3E_RESULT}/r3e_host_attribution.json"
test -f "${SOURCE_R3E_RESULT}/r3e_host_phase_summary.tsv"
test -x "${PYTHON_BIN}"
test -f "${SOURCE_PAYLOAD}"
test "$(stat -c '%s' "${SOURCE_PAYLOAD}")" = 19487
test "$(sha256sum "${SOURCE_PAYLOAD}" | awk '{print $1}')" = \
  48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1

"${PYTHON_BIN}" "${REQUEST_RUNNER}" prepare \
  --source-payload "${SOURCE_PAYLOAD}" \
  --artifact-dir "${RESULT_DIR}" \
  --model-name "${MODEL_NAME}"

test -f "${P6_3C_RUNTIME_LAYOUT_JSON:?runtime layout evidence is required}"
test -f "${P6_3C_RUNTIME_OVERLAY_PREFLIGHT_MANIFEST:?overlay preflight evidence is required}"
test -f "${P6_3C_RUNTIME_OVERLAY_PREFLIGHT_SMOKE:?overlay import smoke evidence is required}"
cp "${P6_3C_RUNTIME_LAYOUT_JSON}" "${RESULT_DIR}/runtime_layout.json"
cp "${P6_3C_RUNTIME_OVERLAY_PREFLIGHT_MANIFEST}" \
  "${RESULT_DIR}/runtime_overlay_preflight_manifest.json"
cp "${P6_3C_RUNTIME_OVERLAY_PREFLIGHT_SMOKE}" \
  "${RESULT_DIR}/runtime_overlay_preflight_smoke.json"

printf 'track\tlifecycle_id\tevidence_track\tconfig_id\tmode\n' \
  > "${RESULT_DIR}/executed_lifecycle_schedule.tsv"

while IFS=$'\t' read -r lifecycle_id policy_id mode; do
  printf 'mechanism\t%s\tvllm_torch_profile_api\t%s\t%s\n' \
    "${lifecycle_id}" "${policy_id}" "${mode}" \
    >> "${RESULT_DIR}/executed_lifecycle_schedule.tsv"
  bash "${MODE_RUNNER}" \
    "${RESULT_DIR}" "${lifecycle_id}" mechanism "${mode}" "${policy_id}"
done < <(schedule)
