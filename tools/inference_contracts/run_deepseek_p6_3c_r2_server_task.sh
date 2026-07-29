#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_SERVER_TASK=${P6_3C_R2_BASE_SERVER_TASK:-${SCRIPT_DIR}/run_deepseek_p6_3c_r1_server_task.sh}
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
ENV_PREFIX=${ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
LAYOUT_RESOLVER=${P6_3C_LAYOUT_RESOLVER:-${SCRIPT_DIR}/resolve_p6_3c_runtime_layout.py}
OVERLAY_BUILDER=${P6_3C_RUNTIME_OVERLAY_BUILDER:-${SCRIPT_DIR}/prepare_p6_3c_runtime_overlay.py}
MTP_PATCH=${MTP_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch}
OBSERVER=${OBSERVER:-${SCRIPT_DIR}/p6_3c_r1_scheduler_observer.py}
OBSERVER_PATCH=${OBSERVER_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_p6_3c_r1_scheduler_observer_overlay.patch}
RUNTIME_IMPL=${RUNTIME_IMPL:-${SCRIPT_DIR}/p6_3b_r1_hybrid_kv_runtime_patch.py}
RUNTIME_LOADER=${RUNTIME_LOADER:-${SCRIPT_DIR}/p6_3b_r2_hybrid_kv_runtime_patch.py}
HYBRID_PATCH=${HYBRID_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch}
DEFERRED_PATCH=${DEFERRED_PATCH:-${REPO_ROOT}/benchmarks/deepseek_v4_flash/patches/vllm_ascend_v0221rc1_hybrid_kv_deferred_install_overlay.patch}
test -f "${BASE_SERVER_TASK}"
test -f "${LAYOUT_RESOLVER}"
test -f "${OVERLAY_BUILDER}"

if test "${P6_3C_SERVER_TASK_AUDIT_ONLY:-${P6_3C_R1_SERVER_TASK_AUDIT_ONLY:-0}}" != 1; then
  test -x "${ENV_PREFIX}/bin/python"
  preflight_root=$(mktemp -d /tmp/p6_3c_r2_f1_preflight.XXXXXX)
  cleanup_preflight() {
    case "${preflight_root}" in
      /tmp/p6_3c_r2_f1_preflight.*)
        rm -rf -- "${preflight_root}"
        ;;
      *)
        echo "refusing to remove unexpected preflight path: ${preflight_root}" >&2
        ;;
    esac
  }
  trap cleanup_preflight EXIT
  layout_json=${preflight_root}/runtime_layout.json
  layout_shell=${preflight_root}/runtime_layout.env
  "${ENV_PREFIX}/bin/python" "${LAYOUT_RESOLVER}" \
    --expected-env-prefix "${ENV_PREFIX}" \
    --output "${layout_json}" \
    --shell-output "${layout_shell}"
  # Generated only from importlib-resolved absolute paths in the pinned target
  # environment. No server operator path wrapper is accepted or required.
  # shellcheck disable=SC1090
  . "${layout_shell}"
  export ENV_PREFIX PYTHON_BIN BASE_PYTHON VLLM_BIN
  export BASE_PLUGIN_ROOT BASE_VLLM_ROOT
  export P6_3C_RUNTIME_LAYOUT_JSON=${layout_json}
  export P6_3C_RUNTIME_OVERLAY_BUILDER=${OVERLAY_BUILDER}

  source_gate=(
    "${BASE_VLLM_ROOT}/v1/core/single_type_kv_cache_manager.py:d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1"
    "${BASE_VLLM_ROOT}/v1/core/kv_cache_coordinator.py:a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89"
    "${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_coordinator.py:dc65ed2adbb05ea52d9e891f648b62a5391eb41b2a6b262b71d40efe31effe20"
    "${BASE_PLUGIN_ROOT}/patch/platform/patch_kv_cache_interface.py:a4969e2c1b2ebde9a3c5a4d02df5175879fb56ea43322869871a3868ec1981b2"
    "${BASE_PLUGIN_ROOT}/spec_decode/llm_base_proposer.py:0e58f5b5e97a4d34d31e66dedd026013ad637e27eccad75acdc39368e5dd05cb"
    "${BASE_PLUGIN_ROOT}/distributed/kv_transfer/__init__.py:dc693fd52eb44921e731b69021388ecc186f4e5fa5eca3b28fc1963661e355d1"
    "${BASE_VLLM_ROOT}/v1/core/sched/scheduler.py:41ff2e524c90d9aa72b72cd77492eb62ee2a729a773bd8233e970f39abbb5983"
  )
  for entry in "${source_gate[@]}"; do
    source_path=${entry%:*}
    expected_sha256=${entry##*:}
    test -f "${source_path}"
    test "$(sha256sum "${source_path}" | awk '{print $1}')" = \
      "${expected_sha256}"
  done

  overlay_preflight_runtime=${preflight_root}/overlay_preflight
  overlay_preflight_manifest=${preflight_root}/runtime_overlay_preflight_manifest.json
  if ! "${PYTHON_BIN}" "${OVERLAY_BUILDER}" \
    --base-plugin-root "${BASE_PLUGIN_ROOT}" \
    --runtime-dir "${overlay_preflight_runtime}" \
    --mtp-patch "${MTP_PATCH}" \
    --runtime-impl "${RUNTIME_IMPL}" \
    --runtime-loader "${RUNTIME_LOADER}" \
    --hybrid-patch "${HYBRID_PATCH}" \
    --deferred-patch "${DEFERRED_PATCH}" \
    --observer "${OBSERVER}" \
    --observer-patch "${OBSERVER_PATCH}" \
    --shared-hybrid-kv-repair \
    --enable-observer \
    --output "${overlay_preflight_manifest}" \
    --failure-excerpt "${preflight_root}/runtime_overlay_preflight_failure.txt"
  then
    printf '%s\n' 'P6_3C_RUNTIME_OVERLAY_PREFLIGHT_BLOCKED'
    cat "${preflight_root}/runtime_overlay_preflight_failure.txt"
    exit 2
  fi
  export P6_3C_RUNTIME_OVERLAY_PREFLIGHT_MANIFEST=${overlay_preflight_manifest}
fi

export P6_3C_TASK_ID=${P6_3C_TASK_ID:-p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01}
export P6_3C_REPORT_PREFIX=${P6_3C_REPORT_PREFIX:-P6_3C_R2}
export P6_3C_RUNNER=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_scheduler_pressure.py
export P6_3C_EXPERIMENT=${SCRIPT_DIR}/run_deepseek_p6_3c_r2_scheduler_pressure.sh

if test "${P6_3C_SERVER_TASK_AUDIT_ONLY:-${P6_3C_R1_SERVER_TASK_AUDIT_ONLY:-0}}" = 1; then
  exec bash "${BASE_SERVER_TASK}" "$@"
fi

set +e
bash "${BASE_SERVER_TASK}" "$@"
task_exit=$?
set -e
exit "${task_exit}"
