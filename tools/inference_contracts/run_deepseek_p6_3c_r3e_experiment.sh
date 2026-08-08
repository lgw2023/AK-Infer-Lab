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
REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_latency_floor.py}
MODE_RUNNER=${MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r3e_mode.sh}
TASK_ID=p6_3c_r3e_mixed_step_latency_floor_attribution_2026_0808_run01

schedule() {
  cat <<'EOF'
host_01	host_timing	admission_on_t4096	chunked_prefill_on
host_02	host_timing	persistent_on_t1024	chunked_prefill_on
host_03	host_timing	persistent_on_t128	chunked_prefill_on
profile_01	diagnostic_msprof	admission_on_t4096	chunked_prefill_on
profile_02	diagnostic_msprof	persistent_on_t128	chunked_prefill_on
EOF
}

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'lineage=R3D_latency_floor_to_R3E_engine_path_attribution\n'
  printf 'model_lifecycle_count_exact=5\n'
  printf 'engine_request_count_including_warmup_exact=50\n'
  printf 'http_request_count_including_warmup_exact=15\n'
  printf 'request_retry_count_exact=0\n'
  printf 'capacity_contract=max_model_len_12288,max_num_batched_tokens_12288,max_num_seqs_9\n'
  printf 'host_timing_lifecycles=admission_on_t4096,persistent_on_t1024,persistent_on_t128\n'
  printf 'diagnostic_msprof_lifecycles=admission_on_t4096,persistent_on_t128\n'
  printf 'observer=read_only_schedule_execute_future_update_correlation\n'
  printf 'profiler_scope=diagnostic_only_not_performance_comparison\n'
  printf 'result_transfer_authorized=true\n'
  while IFS=$'\t' read -r lifecycle_id evidence_track policy_id mode; do
    printf '%s\t%s\t%s\t%s\n' \
      "${lifecycle_id}" "${evidence_track}" "${policy_id}" "${mode}"
    P6_3C_R3E_MODE_AUDIT_ONLY=1 \
      bash "${MODE_RUNNER}" \
      /audit/p6_3c_r3e "${lifecycle_id}" mechanism "${mode}" "${policy_id}"
  done < <(schedule)
}

if test "${P6_3C_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -x "${PYTHON_BIN}"
test -f "${SOURCE_PAYLOAD}"
test "$(stat -c '%s' "${SOURCE_PAYLOAD}")" = 19487
test "$(sha256sum "${SOURCE_PAYLOAD}" | awk '{print $1}')" = \
  48c701c3790ecabcdfffe446cbe84e7e54e56bbcbc2cf482553f665e420ecdb1
test -f "${REQUEST_RUNNER}"
test -f "${MODE_RUNNER}"

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

run_lifecycle() {
  local lifecycle_id=$1
  local evidence_track=$2
  local policy_id=$3
  local mode=$4
  printf 'mechanism\t%s\t%s\t%s\t%s\n' \
    "${lifecycle_id}" "${evidence_track}" "${policy_id}" "${mode}" \
    >> "${RESULT_DIR}/executed_lifecycle_schedule.tsv"
  bash "${MODE_RUNNER}" \
    "${RESULT_DIR}" "${lifecycle_id}" mechanism "${mode}" "${policy_id}"
}

while IFS=$'\t' read -r lifecycle_id evidence_track policy_id mode; do
  test "${evidence_track}" = host_timing || continue
  run_lifecycle "${lifecycle_id}" "${evidence_track}" "${policy_id}" "${mode}"
done < <(schedule)

"${PYTHON_BIN}" "${REQUEST_RUNNER}" host-gate --artifact-dir "${RESULT_DIR}"

while IFS=$'\t' read -r lifecycle_id evidence_track policy_id mode; do
  test "${evidence_track}" = diagnostic_msprof || continue
  run_lifecycle "${lifecycle_id}" "${evidence_track}" "${policy_id}" "${mode}"
done < <(schedule)
