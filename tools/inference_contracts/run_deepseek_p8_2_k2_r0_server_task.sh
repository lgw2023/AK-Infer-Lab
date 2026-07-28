#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728
RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh
BASE_ENV_PREFIX=${BASE_ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
BASE_PYTHON=${BASE_ENV_PREFIX}/bin/python
UCM_GIT_URL=https://github.com/ModelEngine-Group/unified-cache-management.git
UCM_COMMIT=01cbf9b71892c88319862fa57f195b0bef93fa6f
UCM_SHORT_COMMIT=01cbf9b
UCM_SOURCE_ROOT=${UCM_SOURCE_ROOT:-${REPO_ROOT}/server_local/third_party/unified-cache-management-${UCM_SHORT_COMMIT}}
UCM_ENV_PREFIX=${UCM_ENV_PREFIX:-${REPO_ROOT}/server_local/python_envs/ucm-vllm-ascend0221-${UCM_SHORT_COMMIT}}
DEPENDENCY_LOG=${REPO_ROOT}/server_local/ucm_dependency_build_${TASK_ID}.log
CARD_IDS=(0 1 2 3 4 5 6 7)
CARD_IDS_CSV=0,1,2,3,4,5,6,7
EXPECTED_KEEP_ALIVE_MARKER_COUNT=16

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=authorized_pinned_ucm_dependency_and_single_lifecycle_dram_external_prefix_path\n'
  printf 'ucm_git_url=%s\n' "${UCM_GIT_URL}"
  printf 'ucm_commit=%s\n' "${UCM_COMMIT}"
  printf 'dependency_install_scope=isolated_server_local_venv_only\n'
  printf 'base_conda_environment_mutation=false\n'
  printf 'server_side_code_edit_authorized=false\n'
  printf 'npu_card_ids=%s\n' "${CARD_IDS_CSV}"
  printf 'keep_alive_stop_then_same_set_restore=true\n'
  printf 'formal_model_lifecycle_count_exact=1\n'
  printf 'model_request_count_exact=3\n'
  printf 'request_retry_count_exact=0\n'
  printf 'result_transfer_authorized=true\n'
  printf 'automatic_transfer_allowed=false\n'
  printf 'next_task_authorized=false\n'
  P8_2_K2_R0_LIFECYCLE_AUDIT_ONLY=1 \
    UCM_ENV_PREFIX=/audit/ucm-env \
    bash "${LIFECYCLE}" "${RESULT_DIR}"
}

if test "${P8_2_K2_R0_SERVER_TASK_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

test ! -e "${RESULT_DIR}"
test -x "${BASE_PYTHON}"
test -f "${RUNNER}"
test -f "${LIFECYCLE}"
test -x /data/node0_disk1/Public/npu_stop.sh
test -x /data/node0_disk1/Public/npu_keep_alive.sh
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = \
  "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
mkdir -p "${RESULT_DIR}" "$(dirname "${UCM_SOURCE_ROOT}")" \
  "$(dirname "${UCM_ENV_PREFIX}")" "$(dirname "${DEPENDENCY_LOG}")"

keep_alive_stopped=false
lifecycle_pid=
stop_exit=1
restart_exit=1
experiment_exit=1
dependency_exit=1
finalize_exit=1

write_dependency_summary() {
  local status=$1
  UCM_SOURCE_ROOT="${UCM_SOURCE_ROOT}" \
  UCM_ENV_PREFIX="${UCM_ENV_PREFIX}" \
  UCM_COMMIT="${UCM_COMMIT}" \
  UCM_GIT_URL="${UCM_GIT_URL}" \
  DEPENDENCY_STATUS="${status}" \
  "${BASE_PYTHON}" - "${RESULT_DIR}/dependency_and_environment_summary.json" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

source = Path(os.environ["UCM_SOURCE_ROOT"])
venv = Path(os.environ["UCM_ENV_PREFIX"])
python = venv / "bin/python"
def output(command):
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as error:
        return f"{type(error).__name__}: {error}"
critical = {}
for relative in (
    "setup.py",
    "ucm/integration/vllm/ucm_connector.py",
    "ucm/integration/vllm/patch/apply_patch.py",
    "ucm/integration/vllm/patch/v0221/vllm_ascend/ascend_hybrid_cache_patch.py",
    "ucm/integration/vllm/rank_consistency.py",
):
    path = source / relative
    if path.is_file():
        critical[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
summary = {
    "dependency_status": os.environ["DEPENDENCY_STATUS"],
    "ucm_git_url": os.environ["UCM_GIT_URL"],
    "ucm_expected_commit": os.environ["UCM_COMMIT"],
    "ucm_source_root": str(source),
    "ucm_source_head": output(["git", "-C", str(source), "rev-parse", "HEAD"]) if source.is_dir() else None,
    "ucm_source_tracked_clean": (
        output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"]) == ""
        if source.is_dir() else False
    ),
    "ucm_isolated_env": str(venv),
    "base_conda_environment_mutated": False,
    "critical_source_sha256": critical,
    "python_import_probe": (
        output([
            str(python), "-c",
            "import importlib.metadata,ucm,vllm,vllm_ascend,wrapt;"
            "print('|'.join([importlib.metadata.version('uc-manager'),"
            "importlib.metadata.version('vllm'),"
            "importlib.metadata.version('vllm-ascend'),wrapt.__version__]))"
        ]) if python.is_file() else None
    ),
    "selected_model_support_source": "UCM develop support matrix at pinned commit",
    "selected_model": "DeepSeek V4 Flash",
    "selected_platform": "vLLM-Ascend / Atlas A2 / 910B",
}
Path(sys.argv[1]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY
}

provision_ucm() {
  if test ! -d "${UCM_SOURCE_ROOT}/.git"; then
    git clone --filter=blob:none --no-checkout \
      "${UCM_GIT_URL}" "${UCM_SOURCE_ROOT}" \
      >> "${DEPENDENCY_LOG}" 2>&1
    git -C "${UCM_SOURCE_ROOT}" fetch --depth=1 origin "${UCM_COMMIT}" \
      >> "${DEPENDENCY_LOG}" 2>&1
    git -C "${UCM_SOURCE_ROOT}" checkout --detach "${UCM_COMMIT}" \
      >> "${DEPENDENCY_LOG}" 2>&1
  fi
  test "$(git -C "${UCM_SOURCE_ROOT}" rev-parse HEAD)" = "${UCM_COMMIT}"
  test -z "$(git -C "${UCM_SOURCE_ROOT}" status --porcelain --untracked-files=no)"

  if test ! -x "${UCM_ENV_PREFIX}/bin/python"; then
    "${BASE_PYTHON}" -m venv --system-site-packages "${UCM_ENV_PREFIX}" \
      >> "${DEPENDENCY_LOG}" 2>&1
  fi
  set +u
  source /usr/local/Ascend/ascend-toolkit/set_env.sh
  source /usr/local/Ascend/nnal/atb/set_env.sh
  set -u
  if test ! -f "${UCM_ENV_PREFIX}/.ak_ucm_${UCM_SHORT_COMMIT}_installed"; then
    if ! "${UCM_ENV_PREFIX}/bin/python" -c \
      'import wrapt; assert wrapt.__version__ == "1.17.2"' \
      >> "${DEPENDENCY_LOG}" 2>&1; then
      "${UCM_ENV_PREFIX}/bin/python" -m pip install \
        --disable-pip-version-check --no-input 'wrapt==1.17.2' \
        >> "${DEPENDENCY_LOG}" 2>&1
    fi
    PLATFORM=ascend ENABLE_SPARSE=false \
      "${UCM_ENV_PREFIX}/bin/python" -m pip install \
      --disable-pip-version-check --no-input \
      --no-build-isolation --no-deps "${UCM_SOURCE_ROOT}" \
      >> "${DEPENDENCY_LOG}" 2>&1
    printf '%s\n' "${UCM_COMMIT}" \
      > "${UCM_ENV_PREFIX}/.ak_ucm_${UCM_SHORT_COMMIT}_installed"
  fi
  test "$(cat "${UCM_ENV_PREFIX}/.ak_ucm_${UCM_SHORT_COMMIT}_installed")" = \
    "${UCM_COMMIT}"
  ENABLE_UCM_PATCH=1 UCM_ENGINE_TYPE=vllm-ascend.a2 \
    "${UCM_ENV_PREFIX}/bin/python" - <<'PY' \
      >> "${DEPENDENCY_LOG}" 2>&1
import importlib.metadata
import ucm
import vllm
import vllm_ascend
from ucm.integration.vllm.ucm_connector import UCMConnector
from vllm_ascend.distributed.kv_transfer.kv_pool.ucm_connector import UCMConnectorV1
assert UCMConnector.__name__ == "UCMConnector"
assert UCMConnectorV1.__name__ == "UCMConnectorV1"
print(importlib.metadata.version("uc-manager"))
PY
}

finish() {
  incoming_exit=$?
  trap - EXIT INT TERM
  set +e
  if test -n "${lifecycle_pid}" && \
    kill -0 "${lifecycle_pid}" 2>/dev/null; then
    kill -TERM -- "-${lifecycle_pid}" 2>/dev/null
    for _ in $(seq 1 60); do
      kill -0 "${lifecycle_pid}" 2>/dev/null || break
      sleep 2
    done
    if kill -0 "${lifecycle_pid}" 2>/dev/null; then
      kill -KILL -- "-${lifecycle_pid}" 2>/dev/null
    fi
    wait "${lifecycle_pid}" 2>/dev/null
  fi
  restored_card_ids=
  if test "${keep_alive_stopped}" = true; then
    bash /data/node0_disk1/Public/npu_keep_alive.sh "${CARD_IDS[@]}"
    restart_exit=$?
    if test "${restart_exit}" -eq 0; then
      restored_card_ids=${CARD_IDS_CSV}
    fi
  else
    restart_exit=0
  fi

  recovery_dir=${RESULT_DIR}/runtime/resource_recovery
  mkdir -p "${recovery_dir}"
  marker_wait_seconds=0
  keep_alive_marker_count=0
  marker_card_ids=
  while test "${marker_wait_seconds}" -lt 30; do
    ps -eo args= > "${recovery_dir}/keep_alive_processes.txt" 2>&1
    keep_alive_marker_count=$(grep -Ec '#[0-7]#' \
      "${recovery_dir}/keep_alive_processes.txt" || true)
    marker_card_ids=
    for card in "${CARD_IDS[@]}"; do
      if grep -F "#${card}#" "${recovery_dir}/keep_alive_processes.txt" \
        >/dev/null 2>&1; then
        marker_card_ids=${marker_card_ids:+${marker_card_ids},}${card}
      fi
    done
    if test "${keep_alive_marker_count}" -eq \
      "${EXPECTED_KEEP_ALIVE_MARKER_COUNT}" && \
      test "${marker_card_ids}" = "${CARD_IDS_CSV}"; then
      break
    fi
    marker_wait_seconds=$((marker_wait_seconds + 1))
    sleep 1
  done
  ss -ltnp > "${recovery_dir}/listening_ports.txt" 2>&1
  port_7000_listener_count=$(awk \
    '$4 ~ /:7000$/ {count++} END {print count + 0}' \
    "${recovery_dir}/listening_ports.txt")
  pgrep -af '[v]llm.*serve.*DeepSeek-V4-Flash-w8a8-mtp' \
    > "${recovery_dir}/vllm_residual_processes.txt" 2>&1
  vllm_residual_process_count=$(wc -l \
    < "${recovery_dir}/vllm_residual_processes.txt" | tr -d ' ')
  if test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"; then
    tracked_worktree_clean=true
  else
    tracked_worktree_clean=false
  fi
  keep_alive_restored_exact=false
  if test "${keep_alive_stopped}" = false; then
    keep_alive_restored_exact=true
  elif test "${restart_exit}" -eq 0 && \
    test "${keep_alive_marker_count}" -eq "${EXPECTED_KEEP_ALIVE_MARKER_COUNT}" && \
    test "${marker_card_ids}" = "${CARD_IDS_CSV}"; then
    keep_alive_restored_exact=true
  fi
  STOPPED_CARD_IDS="${keep_alive_stopped}" \
  RESTORED_CARD_IDS="${restored_card_ids}" \
  STOP_EXIT="${stop_exit}" \
  RESTART_EXIT="${restart_exit}" \
  KEEP_ALIVE_MARKER_COUNT="${keep_alive_marker_count}" \
  KEEP_ALIVE_RESTORED_EXACT="${keep_alive_restored_exact}" \
  PORT_LISTENER_COUNT="${port_7000_listener_count}" \
  VLLM_RESIDUAL_COUNT="${vllm_residual_process_count}" \
  TRACKED_CLEAN="${tracked_worktree_clean}" \
  EXPERIMENT_EXIT="${experiment_exit}" \
  DEPENDENCY_EXIT="${dependency_exit}" \
  "${BASE_PYTHON}" - "${RESULT_DIR}/resource_recovery_summary.json" <<'PY'
import json
import os
import sys
def ints(value):
    return [int(item) for item in value.split(",") if item]
stopped = list(range(8)) if os.environ["STOPPED_CARD_IDS"] == "true" else []
summary = {
    "stopped_card_ids": stopped,
    "restored_card_ids": ints(os.environ["RESTORED_CARD_IDS"]),
    "stop_exit_code": int(os.environ["STOP_EXIT"]),
    "restart_exit_code": int(os.environ["RESTART_EXIT"]),
    "keep_alive_marker_count": int(os.environ["KEEP_ALIVE_MARKER_COUNT"]),
    "expected_keep_alive_marker_count": 16,
    "keep_alive_restored_exact": os.environ["KEEP_ALIVE_RESTORED_EXACT"] == "true",
    "port_7000_listener_count": int(os.environ["PORT_LISTENER_COUNT"]),
    "vllm_residual_process_count": int(os.environ["VLLM_RESIDUAL_COUNT"]),
    "tracked_worktree_clean": os.environ["TRACKED_CLEAN"] == "true",
    "experiment_exit_code": int(os.environ["EXPERIMENT_EXIT"]),
    "dependency_exit_code": int(os.environ["DEPENDENCY_EXIT"]),
}
open(sys.argv[1], "w").write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY
  cleanup_status=clean
  if test "${port_7000_listener_count}" -ne 0 || \
    test "${vllm_residual_process_count}" -ne 0 || \
    test "${tracked_worktree_clean}" != true || \
    test "${keep_alive_restored_exact}" != true; then
    cleanup_status=incomplete
  fi
  printf '%s\n' "${cleanup_status}" > "${RESULT_DIR}/cleanup_status.txt"

  "${BASE_PYTHON}" "${RUNNER}" finalize --artifact-dir "${RESULT_DIR}"
  finalize_exit=$?
  "${BASE_PYTHON}" "${RUNNER}" package --artifact-dir "${RESULT_DIR}"
  package_exit=$?

  printf '%s\n' 'K2_R0_SERVER_REPORT_BEGIN'
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'head=%s\n' "$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  printf 'origin_main=%s\n' "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
  printf 'ahead_behind=%s\n' \
    "$(git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main)"
  printf 'tracked_clean=%s\n' "${tracked_worktree_clean}"
  printf 'dependency_exit=%s\n' "${dependency_exit}"
  printf 'experiment_exit=%s\n' "${experiment_exit}"
  printf 'restart_exit=%s\n' "${restart_exit}"
  printf 'cleanup_status=%s\n' "${cleanup_status}"
  printf 'result_summary=%s\n' "${RESULT_DIR}/result_summary.md"
  printf 'task_grade=%s\n' "$(cat "${RESULT_DIR}/task_grade.txt")"
  printf '%s\n' 'dependency_and_environment_summary:'
  cat "${RESULT_DIR}/dependency_and_environment_summary.json"
  printf '%s\n' 'grading_summary:'
  cat "${RESULT_DIR}/grading_summary.json"
  printf '%s\n' 'ucm_path_summary:'
  cat "${RESULT_DIR}/ucm_path_summary.json"
  printf '%s\n' 'request_summary:'
  cat "${RESULT_DIR}/request_summary.tsv"
  printf '%s\n' 'ucm_metric_deltas:'
  cat "${RESULT_DIR}/ucm_metric_deltas.tsv"
  printf '%s\n' 'resource_recovery_summary:'
  cat "${RESULT_DIR}/resource_recovery_summary.json"
  printf '%s\n' 'result_summary_body:'
  cat "${RESULT_DIR}/result_summary.md"
  printf '%s\n' 'candidate_manifest:'
  cat "${RESULT_DIR}/candidate_manifest.server_local.json"
  printf 'candidate_manifest_bytes=%s\n' \
    "$(wc -c < "${RESULT_DIR}/candidate_manifest.server_local.json" | tr -d ' ')"
  printf 'candidate_manifest_sha256=%s\n' \
    "$(sha256sum "${RESULT_DIR}/candidate_manifest.server_local.json" | awk '{print $1}')"
  printf '%s\n' 'K2_R0_SERVER_REPORT_END'

  if test "${restart_exit}" -ne 0 || test "${package_exit}" -ne 0; then
    exit 5
  fi
  if test "${finalize_exit}" -ne 0; then
    exit "${finalize_exit}"
  fi
  exit "${incoming_exit}"
}
trap finish EXIT INT TERM

set +e
provision_ucm
dependency_exit=$?
set -e
if test "${dependency_exit}" -ne 0; then
  write_dependency_summary dependency_failed
  experiment_exit=1
  exit 0
fi
write_dependency_summary ready

set +e
bash /data/node0_disk1/Public/npu_stop.sh "${CARD_IDS[@]}"
stop_exit=$?
set -e
if test "${stop_exit}" -ne 0; then
  exit "${stop_exit}"
fi
keep_alive_stopped=true

BASE_ENV_PREFIX="${BASE_ENV_PREFIX}" \
UCM_ENV_PREFIX="${UCM_ENV_PREFIX}" \
  setsid bash "${LIFECYCLE}" "${RESULT_DIR}" &
lifecycle_pid=$!
set +e
wait "${lifecycle_pid}"
experiment_exit=$?
set -e
lifecycle_pid=
exit "${experiment_exit}"
