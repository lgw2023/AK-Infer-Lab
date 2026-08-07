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
REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r3d_persistent_prefill.py}
MODE_RUNNER=${MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3c_r3d_mode.sh}
TASK_ID=p6_3c_r3d_persistent_prefill_pressure_2026_0807_run01

schedule() {
  cat <<'EOF'
mechanism	mechanism_01	mechanism	admission_on_t4096	chunked_prefill_on	12288	admission_on_t4096
mechanism	mechanism_02	mechanism	persistent_on_t128	chunked_prefill_on	12288	persistent_on_t128
mechanism	mechanism_03	mechanism	persistent_on_t256	chunked_prefill_on	12288	persistent_on_t256
mechanism	mechanism_04	mechanism	persistent_on_t512	chunked_prefill_on	12288	persistent_on_t512
mechanism	mechanism_05	mechanism	persistent_on_t1024	chunked_prefill_on	12288	persistent_on_t1024
performance	performance_01	round_1	off_b12288	chunked_prefill_off	12288	off_b12288
performance	performance_02	round_1	admission_on_t4096	chunked_prefill_on	12288	admission_on_t4096
performance	performance_03	round_1	persistent_on_t128	chunked_prefill_on	12288	persistent_on_t128
performance	performance_04	round_1	persistent_on_t256	chunked_prefill_on	12288	persistent_on_t256
performance	performance_05	round_1	persistent_on_t512	chunked_prefill_on	12288	persistent_on_t512
performance	performance_06	round_1	persistent_on_t1024	chunked_prefill_on	12288	persistent_on_t1024
performance	performance_07	round_2	persistent_on_t1024	chunked_prefill_on	12288	persistent_on_t1024
performance	performance_08	round_2	persistent_on_t512	chunked_prefill_on	12288	persistent_on_t512
performance	performance_09	round_2	persistent_on_t256	chunked_prefill_on	12288	persistent_on_t256
performance	performance_10	round_2	persistent_on_t128	chunked_prefill_on	12288	persistent_on_t128
performance	performance_11	round_2	admission_on_t4096	chunked_prefill_on	12288	admission_on_t4096
performance	performance_12	round_2	off_b12288	chunked_prefill_off	12288	off_b12288
EOF
}

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'lineage=R3C_admission_only_to_R3D_persistent_prefill_variant\n'
  printf 'model_lifecycle_count_exact=17\n'
  printf 'engine_request_count_including_warmup_exact=1286\n'
  printf 'http_request_count_including_warmup_exact=243\n'
  printf 'request_retry_count_exact=0\n'
  printf 'capacity_contract=max_model_len_12288,max_num_batched_tokens_12288,max_num_seqs_9\n'
  printf 'policies=off_b12288,admission_on_t4096,persistent_on_t128,persistent_on_t256,persistent_on_t512,persistent_on_t1024\n'
  printf 'persistent_rule=pressure_while_waiting_or_running_unfinished_prefill\n'
  printf 'resident_contract=8x256_input_128_output,inject_after_each_has_16_output_tokens\n'
  printf 'cells=resident_only,admission_cliff_12281\n'
  printf 'mechanism_gate=complete_prefill_chunk_sequence\n'
  printf 'performance_observer=disabled\n'
  printf 'profiler=disabled\n'
  printf 'comparison_type=adaptive_policy_comparison_not_strict_single_variable_ab\n'
  printf 'result_transfer_authorized=true\n'
  while IFS=$'\t' read -r track lifecycle_id mirror_round config_id mode budget policy_id; do
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "${track}" "${lifecycle_id}" "${mirror_round}" "${config_id}" \
      "${mode}" "${budget}" "${policy_id}"
    P6_3C_R3D_MODE_AUDIT_ONLY=1 \
      bash "${MODE_RUNNER}" \
      /audit/p6_3c_r3d "${lifecycle_id}" "${track}" "${mode}" \
      "${policy_id}"
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
cp "${P6_3C_RUNTIME_LAYOUT_JSON}" "${RESULT_DIR}/runtime_layout.json"
cp "${P6_3C_RUNTIME_OVERLAY_PREFLIGHT_MANIFEST}" \
  "${RESULT_DIR}/runtime_overlay_preflight_manifest.json"

printf 'track\tlifecycle_id\tmirror_round\tconfig_id\tmode\tmax_num_batched_tokens\tpolicy_id\n' \
  > "${RESULT_DIR}/executed_lifecycle_schedule.tsv"

run_lifecycle() {
  local track=$1
  local lifecycle_id=$2
  local mirror_round=$3
  local config_id=$4
  local mode=$5
  local budget=$6
  local policy_id=$7
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "${track}" "${lifecycle_id}" "${mirror_round}" "${config_id}" \
    "${mode}" "${budget}" "${policy_id}" \
    >> "${RESULT_DIR}/executed_lifecycle_schedule.tsv"
  bash "${MODE_RUNNER}" \
    "${RESULT_DIR}" "${lifecycle_id}" "${track}" "${mode}" "${policy_id}"
}

while IFS=$'\t' read -r track lifecycle_id mirror_round config_id mode budget policy_id; do
  test "${track}" = mechanism || continue
  run_lifecycle "${track}" "${lifecycle_id}" "${mirror_round}" \
    "${config_id}" "${mode}" "${budget}" "${policy_id}"
done < <(schedule)
"${PYTHON_BIN}" "${REQUEST_RUNNER}" mechanism-gate \
  --artifact-dir "${RESULT_DIR}"

while IFS=$'\t' read -r track lifecycle_id mirror_round config_id mode budget policy_id; do
  test "${track}" = performance || continue
  run_lifecycle "${track}" "${lifecycle_id}" "${mirror_round}" \
    "${config_id}" "${mode}" "${budget}" "${policy_id}"
done < <(schedule)
