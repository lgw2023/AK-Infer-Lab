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
RUN_LABEL=$(basename -- "${RESULT_DIR}")
EXPECTED_RUN_LABEL=${TASK_ID}_run02
DEPENDENCY_LOG=${REPO_ROOT}/server_local/ucm_dependency_build_${RUN_LABEL}.log
PROVISION_EVENT_LOG=${RESULT_DIR}/runtime/dependency_provision_events.jsonl
INSTALL_MARKER=.ak_ucm_${UCM_SHORT_COMMIT}_installed
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
  printf 'dependency_repair_attempt=run02_explicit\n'
  printf 'expected_result_basename=%s\n' "${EXPECTED_RUN_LABEL}"
  printf 'global_git_safe_directory_mutation=false\n'
  printf 'invalid_dependency_state_action=quarantine_then_atomic_rebuild\n'
  printf 'dependency_log_attempt_local_and_truncated=true\n'
  printf 'install_marker_written_after_import_probe_only=true\n'
  printf 'preflight_failure_npu_touch=false\n'
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
test "${RUN_LABEL}" = "${EXPECTED_RUN_LABEL}"
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
  "$(dirname "${UCM_ENV_PREFIX}")" "$(dirname "${DEPENDENCY_LOG}")" \
  "$(dirname "${PROVISION_EVENT_LOG}")"
: > "${DEPENDENCY_LOG}"
: > "${PROVISION_EVENT_LOG}"

keep_alive_stopped=false
lifecycle_pid=
stop_attempted=false
lifecycle_started=false
stop_exit=0
restart_exit=0
experiment_exit=0
dependency_exit=1
finalize_exit=1

append_provision_event() {
  local event=$1
  local kind=$2
  local source_path=$3
  local destination_path=$4
  local detail=$5
  PROVISION_EVENT="${event}" \
  PROVISION_KIND="${kind}" \
  PROVISION_SOURCE="${source_path}" \
  PROVISION_DESTINATION="${destination_path}" \
  PROVISION_DETAIL="${detail}" \
    "${BASE_PYTHON}" - "${PROVISION_EVENT_LOG}" <<'PY'
import json
import os
import sys
import time

entry = {
    "event": os.environ["PROVISION_EVENT"],
    "kind": os.environ["PROVISION_KIND"],
    "source": os.environ["PROVISION_SOURCE"],
    "destination": os.environ["PROVISION_DESTINATION"],
    "detail": os.environ["PROVISION_DETAIL"],
    "time_ns": time.time_ns(),
}
with open(sys.argv[1], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(entry, separators=(",", ":"), sort_keys=True) + "\n")
PY
}

tree_owned_by_current_user() {
  "${BASE_PYTHON}" - "$1" <<'PY'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected = os.geteuid()
paths = [root]
if root.is_dir():
    paths.extend(root.rglob("*"))
for path in paths:
    try:
        owner = path.lstat().st_uid
    except FileNotFoundError:
        print(f"ownership probe raced with removal: {path}", file=sys.stderr)
        raise SystemExit(1)
    if owner != expected:
        print(
            f"owner mismatch: path={path} expected_uid={expected} actual_uid={owner}",
            file=sys.stderr,
        )
        raise SystemExit(1)
PY
}

validate_ucm_source() {
  local source_root=$1
  test -d "${source_root}/.git" || return 1
  tree_owned_by_current_user "${source_root}" || return 1
  test "$(git -C "${source_root}" remote get-url origin)" = \
    "${UCM_GIT_URL}" || return 1
  test "$(git -C "${source_root}" rev-parse HEAD)" = \
    "${UCM_COMMIT}" || return 1
  git -C "${source_root}" cat-file -e "${UCM_COMMIT}^{commit}" || return 1
  test -z "$(git -C "${source_root}" status \
    --porcelain --untracked-files=no)" || return 1
  test -f "${source_root}/pyproject.toml" || return 1
  test -f "${source_root}/setup.py" || return 1
  test -f "${source_root}/ucm/integration/vllm/ucm_connector.py" || return 1
  test -f \
    "${source_root}/ucm/integration/vllm/patch/apply_patch.py" || return 1
  test -f \
    "${source_root}/ucm/integration/vllm/patch/v0221/vllm_ascend/ascend_hybrid_cache_patch.py" \
    || return 1
  test -f \
    "${source_root}/ucm/integration/vllm/rank_consistency.py" || return 1
}

quarantine_path() {
  local target=$1
  local kind=$2
  local detail=$3
  local parent
  local quarantine_root
  local destination
  test -e "${target}" || return 0
  parent=$(dirname -- "${target}")
  quarantine_root=${parent}/quarantine
  mkdir -p "${quarantine_root}"
  destination=${quarantine_root}/$(basename -- "${target}").${RUN_LABEL}.$(date -u +%Y%m%dT%H%M%SZ).$$
  test ! -e "${destination}"
  mv -- "${target}" "${destination}"
  append_provision_event quarantined "${kind}" "${target}" \
    "${destination}" "${detail}"
}

clone_and_promote_ucm_source() {
  local parent
  local source_stage
  parent=$(dirname -- "${UCM_SOURCE_ROOT}")
  source_stage=$(mktemp -d \
    "${parent}/.$(basename -- "${UCM_SOURCE_ROOT}").staging.XXXXXX")
  append_provision_event staging_created source "" "${source_stage}" \
    current_user_owned_exact_commit_clone
  if ! (
    set -euo pipefail
    git clone --filter=blob:none --no-checkout \
      "${UCM_GIT_URL}" "${source_stage}" || exit 1
    git -C "${source_stage}" fetch --depth=1 origin \
      "${UCM_COMMIT}" || exit 1
    git -C "${source_stage}" checkout --detach \
      "${UCM_COMMIT}" || exit 1
    validate_ucm_source "${source_stage}" || exit 1
  ) >> "${DEPENDENCY_LOG}" 2>&1; then
    quarantine_path "${source_stage}" source_staging \
      clone_checkout_or_source_validation_failed
    return 1
  fi
  test ! -e "${UCM_SOURCE_ROOT}"
  mv -- "${source_stage}" "${UCM_SOURCE_ROOT}"
  append_provision_event promoted source "${source_stage}" \
    "${UCM_SOURCE_ROOT}" exact_commit_source_validated_before_atomic_rename
  validate_ucm_source "${UCM_SOURCE_ROOT}" \
    >> "${DEPENDENCY_LOG}" 2>&1
}

ensure_ucm_source() {
  if test -e "${UCM_SOURCE_ROOT}"; then
    if validate_ucm_source "${UCM_SOURCE_ROOT}" \
      >> "${DEPENDENCY_LOG}" 2>&1; then
      append_provision_event reused source "${UCM_SOURCE_ROOT}" \
        "${UCM_SOURCE_ROOT}" existing_source_fully_validated
      return 0
    fi
    quarantine_path "${UCM_SOURCE_ROOT}" source \
      untrusted_incomplete_or_wrong_pinned_source
  fi
  clone_and_promote_ucm_source
}

ucm_import_probe() {
  local python_bin=$1
  ENABLE_UCM_PATCH=1 UCM_ENGINE_TYPE=vllm-ascend.a2 \
    "${python_bin}" - <<'PY'
import importlib.metadata
import pathlib
import ucm
import vllm
import vllm_ascend
import wrapt
from ucm.integration.vllm.ucm_connector import UCMConnector
from vllm_ascend.distributed.kv_transfer.kv_pool.ucm_connector import UCMConnectorV1

assert importlib.metadata.version("uc-manager")
assert importlib.metadata.version("vllm")
assert importlib.metadata.version("vllm-ascend")
assert wrapt.__version__ == "1.17.2"
assert pathlib.Path(ucm.__file__).is_file()
assert UCMConnector.__name__ == "UCMConnector"
assert UCMConnectorV1.__name__ == "UCMConnectorV1"
print(importlib.metadata.version("uc-manager"))
PY
}

validate_ucm_env() {
  local env_root=$1
  local marker=${env_root}/${INSTALL_MARKER}
  test -x "${env_root}/bin/python" || return 1
  tree_owned_by_current_user "${env_root}" || return 1
  test -f "${marker}" || return 1
  test "$(cat "${marker}")" = "${UCM_COMMIT}" || return 1
  ucm_import_probe "${env_root}/bin/python" || return 1
}

build_and_promote_ucm_env() {
  local parent
  local env_stage
  local marker_tmp
  parent=$(dirname -- "${UCM_ENV_PREFIX}")
  env_stage=$(mktemp -d \
    "${parent}/.$(basename -- "${UCM_ENV_PREFIX}").staging.XXXXXX")
  append_provision_event staging_created venv "" "${env_stage}" \
    isolated_system_site_packages_venv
  if ! (
    set -euo pipefail
    "${BASE_PYTHON}" -m venv --system-site-packages \
      "${env_stage}" || exit 1
    set +u
    source /usr/local/Ascend/ascend-toolkit/set_env.sh || exit 1
    source /usr/local/Ascend/nnal/atb/set_env.sh || exit 1
    set -u
    if ! "${env_stage}/bin/python" -c \
      'import wrapt; assert wrapt.__version__ == "1.17.2"'; then
      "${env_stage}/bin/python" -m pip install \
        --disable-pip-version-check --no-input \
        'wrapt==1.17.2' || exit 1
    fi
    PLATFORM=ascend ENABLE_SPARSE=false \
      "${env_stage}/bin/python" -m pip install \
      --disable-pip-version-check --no-input \
      --no-build-isolation --no-deps "${UCM_SOURCE_ROOT}" || exit 1
    ucm_import_probe "${env_stage}/bin/python" || exit 1
    marker_tmp=$(mktemp \
      "${env_stage}/.${INSTALL_MARKER}.tmp.XXXXXX") || exit 1
    printf '%s\n' "${UCM_COMMIT}" > "${marker_tmp}" || exit 1
    mv -- "${marker_tmp}" "${env_stage}/${INSTALL_MARKER}" || exit 1
    validate_ucm_env "${env_stage}" || exit 1
  ) >> "${DEPENDENCY_LOG}" 2>&1; then
    quarantine_path "${env_stage}" venv_staging \
      venv_build_install_or_import_validation_failed
    return 1
  fi
  test ! -e "${UCM_ENV_PREFIX}"
  mv -- "${env_stage}" "${UCM_ENV_PREFIX}"
  append_provision_event promoted venv "${env_stage}" \
    "${UCM_ENV_PREFIX}" import_validated_before_atomic_rename
  if ! validate_ucm_env "${UCM_ENV_PREFIX}" \
    >> "${DEPENDENCY_LOG}" 2>&1; then
    quarantine_path "${UCM_ENV_PREFIX}" venv \
      post_promotion_import_validation_failed
    return 1
  fi
}

ensure_ucm_env() {
  if test -e "${UCM_ENV_PREFIX}"; then
    if validate_ucm_env "${UCM_ENV_PREFIX}" \
      >> "${DEPENDENCY_LOG}" 2>&1; then
      append_provision_event reused venv "${UCM_ENV_PREFIX}" \
        "${UCM_ENV_PREFIX}" marker_and_import_probe_valid
      return 0
    fi
    quarantine_path "${UCM_ENV_PREFIX}" venv \
      poisoned_incomplete_or_import_invalid_environment
  fi
  build_and_promote_ucm_env
}

write_dependency_summary() {
  local status=$1
  UCM_SOURCE_ROOT="${UCM_SOURCE_ROOT}" \
  UCM_ENV_PREFIX="${UCM_ENV_PREFIX}" \
  UCM_COMMIT="${UCM_COMMIT}" \
  UCM_GIT_URL="${UCM_GIT_URL}" \
  UCM_INSTALL_MARKER="${INSTALL_MARKER}" \
  DEPENDENCY_LOG="${DEPENDENCY_LOG}" \
  PROVISION_EVENT_LOG="${PROVISION_EVENT_LOG}" \
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
marker = venv / os.environ["UCM_INSTALL_MARKER"]
event_log = Path(os.environ["PROVISION_EVENT_LOG"])
dependency_log = Path(os.environ["DEPENDENCY_LOG"])
expected_uid = os.geteuid()

def tree_owned(path):
    if not path.exists():
        return False
    try:
        return all(
            candidate.lstat().st_uid == expected_uid
            for candidate in (path, *path.rglob("*"))
        )
    except OSError:
        return False

def output(command, allowed=True):
    if not allowed:
        return "skipped_untrusted_owner"
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as error:
        return f"{type(error).__name__}: {error}"

events = []
if event_log.is_file():
    for line in event_log.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
source_owned = tree_owned(source)
venv_owned = tree_owned(venv)
source_head = output(
    ["git", "-C", str(source), "rev-parse", "HEAD"],
    source_owned and source.is_dir(),
)
source_remote = output(
    ["git", "-C", str(source), "remote", "get-url", "origin"],
    source_owned and source.is_dir(),
)
source_status = output(
    ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
    source_owned and source.is_dir(),
)
required_files = (
    "pyproject.toml",
    "setup.py",
    "ucm/integration/vllm/ucm_connector.py",
    "ucm/integration/vllm/patch/apply_patch.py",
    "ucm/integration/vllm/patch/v0221/vllm_ascend/ascend_hybrid_cache_patch.py",
    "ucm/integration/vllm/rank_consistency.py",
)
critical = {}
required_presence = {}
for relative in required_files:
    path = source / relative
    required_presence[relative] = path.is_file()
    if path.is_file():
        critical[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
marker_value = marker.read_text(encoding="utf-8").strip() if marker.is_file() else None
import_probe = (
    output([
        str(python), "-c",
        "import importlib.metadata,ucm,vllm,vllm_ascend,wrapt;"
        "from ucm.integration.vllm.ucm_connector import UCMConnector;"
        "from vllm_ascend.distributed.kv_transfer.kv_pool.ucm_connector "
        "import UCMConnectorV1;"
        "assert wrapt.__version__=='1.17.2';"
        "print('|'.join([importlib.metadata.version('uc-manager'),"
        "importlib.metadata.version('vllm'),"
        "importlib.metadata.version('vllm-ascend'),wrapt.__version__,"
        "UCMConnector.__name__,UCMConnectorV1.__name__]))"
    ], venv_owned and python.is_file())
    if python.is_file()
    else None
)
summary = {
    "dependency_status": os.environ["DEPENDENCY_STATUS"],
    "dependency_attempt": "run02_explicit_repair",
    "dependency_log_server_path": str(dependency_log),
    "dependency_log_bytes": dependency_log.stat().st_size if dependency_log.is_file() else 0,
    "dependency_log_truncated_before_attempt": True,
    "global_git_safe_directory_mutated": False,
    "ucm_git_url": os.environ["UCM_GIT_URL"],
    "ucm_expected_commit": os.environ["UCM_COMMIT"],
    "ucm_source_root": str(source),
    "ucm_source_owner_uid": source.stat().st_uid if source.exists() else None,
    "expected_current_user_uid": expected_uid,
    "ucm_source_tree_owned_by_current_user": source_owned,
    "ucm_source_head": source_head,
    "ucm_source_remote_url": source_remote,
    "ucm_source_tracked_clean": source_status == "",
    "ucm_source_required_files": required_presence,
    "ucm_source_validation_complete": all((
        source_owned,
        source_head == os.environ["UCM_COMMIT"],
        source_remote == os.environ["UCM_GIT_URL"],
        source_status == "",
        all(required_presence.values()),
    )),
    "ucm_isolated_env": str(venv),
    "ucm_env_tree_owned_by_current_user": venv_owned,
    "ucm_install_marker_path": str(marker),
    "ucm_install_marker_value": marker_value,
    "ucm_install_marker_valid": marker_value == os.environ["UCM_COMMIT"],
    "base_conda_environment_mutated": False,
    "critical_source_sha256": critical,
    "python_import_probe": import_probe,
    "provision_event_count": len(events),
    "provision_events": events,
    "quarantine_paths": [
        event["destination"]
        for event in events
        if event.get("event") == "quarantined"
    ],
    "source_promoted_atomically": any(
        event.get("event") == "promoted" and event.get("kind") == "source"
        for event in events
    ),
    "venv_promoted_atomically": any(
        event.get("event") == "promoted" and event.get("kind") == "venv"
        for event in events
    ),
    "install_marker_written_after_import_probe_only": True,
    "preflight_failed_before_npu_touch": os.environ["DEPENDENCY_STATUS"] != "ready",
    "selected_model_support_source": "UCM develop support matrix at pinned commit",
    "selected_model": "DeepSeek V4 Flash",
    "selected_platform": "vLLM-Ascend / Atlas A2 / 910B",
}
Path(sys.argv[1]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY
}

provision_ucm() {
  ensure_ucm_source || return 1
  ensure_ucm_env || return 1
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
  if test "${stop_attempted}" = true; then
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
  if test "${stop_attempted}" = false; then
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
  STOP_ATTEMPTED="${stop_attempted}" \
  LIFECYCLE_STARTED="${lifecycle_started}" \
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
    "npu_stop_attempted": os.environ["STOP_ATTEMPTED"] == "true",
    "formal_model_lifecycle_started": os.environ["LIFECYCLE_STARTED"] == "true",
    "preflight_failed_before_npu_touch": (
        int(os.environ["DEPENDENCY_EXIT"]) != 0
        and os.environ["STOP_ATTEMPTED"] != "true"
        and os.environ["LIFECYCLE_STARTED"] != "true"
    ),
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
(
  set -euo pipefail
  provision_ucm
)
dependency_exit=$?
set -e
if test "${dependency_exit}" -ne 0; then
  write_dependency_summary dependency_failed
  experiment_exit=1
  exit 0
fi
write_dependency_summary ready

set +e
stop_attempted=true
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
lifecycle_started=true
set +e
wait "${lifecycle_pid}"
experiment_exit=$?
set -e
lifecycle_pid=
exit "${experiment_exit}"
