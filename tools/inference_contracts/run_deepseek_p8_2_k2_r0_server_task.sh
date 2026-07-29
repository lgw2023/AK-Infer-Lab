#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k2_r0_run04_fawa_posix_gc_geometry_2026_0729
RUNNER=${SCRIPT_DIR}/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.py
LIFECYCLE=${SCRIPT_DIR}/run_deepseek_p8_2_k2_r0_ucm_dram_prefix.sh
FAWA_GEOMETRY=${SCRIPT_DIR}/p8_2_k2_r0_fawa_posix_gc_geometry.py
CMAKE_PYTHON_WRAPPER=${SCRIPT_DIR}/run_ucm_cmake_python_wrapper.sh
BASE_ENV_PREFIX=${BASE_ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
BASE_PYTHON=${BASE_ENV_PREFIX}/bin/python
UCM_GIT_URL=https://github.com/ModelEngine-Group/unified-cache-management.git
UCM_COMMIT=01cbf9b71892c88319862fa57f195b0bef93fa6f
UCM_SHORT_COMMIT=01cbf9b
UCM_SOURCE_ROOT=${UCM_SOURCE_ROOT:-${REPO_ROOT}/server_local/third_party/unified-cache-management-${UCM_SHORT_COMMIT}}
UCM_ENV_PREFIX=${UCM_ENV_PREFIX:-${REPO_ROOT}/server_local/python_envs/ucm-vllm-ascend0221-${UCM_SHORT_COMMIT}}
RUN_LABEL=$(basename -- "${RESULT_DIR}")
EXPECTED_RUN_LABEL=${TASK_ID}_run01
UCM_STORAGE_ROOT=${RESULT_DIR}/runtime/ucm_posix_backend
PARENT_ATTRIBUTION_TASK_ID=p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729
PARENT_ATTRIBUTION_ROOT=${PARENT_ATTRIBUTION_ROOT:-${REPO_ROOT}/server_local/${PARENT_ATTRIBUTION_TASK_ID}_run01}
PARENT_ATTRIBUTION_MANIFEST_BYTES=3104
PARENT_ATTRIBUTION_MANIFEST_SHA256=7bb522ad5353d8d0b3ab3b9339a4e0bf92ce3f5a75f77a143c0d52ca664e1d71
DEPENDENCY_LOG=${REPO_ROOT}/server_local/ucm_dependency_build_${RUN_LABEL}.log
PROVISION_EVENT_LOG=${RESULT_DIR}/runtime/dependency_provision_events.jsonl
CMAKE_WRAPPER_LOG=${RESULT_DIR}/runtime/ucm_cmake_python_wrapper.log
CMAKE_WRAPPER_DIR=${RESULT_DIR}/runtime/dependency_tools
INSTALL_MARKER=.ak_ucm_${UCM_SHORT_COMMIT}_installed
EXPECTED_SHARED_GID=${EXPECTED_SHARED_GID:-3000}
UCM_CACHE_BUFFER_GIB=16
UCM_CACHE_STORE_COUNT=2
UCM_RUN03_FA_BLOCK_SIZE_BYTES=3186688
UCM_RUN03_WA_BLOCK_SIZE_BYTES=6627328
UCM_LOAD_EXCLUSIVE_BUFFER_NUMBER=1024
UCM_TP_SIZE=8
UCM_CAPACITY_HEADROOM_GIB=16
UCM_POSIX_TOTAL_CAPACITY_GIB=64
UCM_POSIX_SPLIT_COUNT=2
UCM_POSIX_DATA_DIR_SHARD_BYTES=2
UCM_POSIX_HEADROOM_GIB=16
CARD_IDS=(0 1 2 3 4 5 6 7)
CARD_IDS_CSV=0,1,2,3,4,5,6,7
EXPECTED_KEEP_ALIVE_MARKER_COUNT=16

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'execution_mode=authorized_single_lifecycle_fawa_split_aware_posix_gc_geometry_repair_and_external_prefix_path\n'
  printf 'ucm_git_url=%s\n' "${UCM_GIT_URL}"
  printf 'ucm_commit=%s\n' "${UCM_COMMIT}"
  printf 'dependency_install_scope=isolated_server_local_venv_only\n'
  printf 'base_conda_environment_mutation=false\n'
  printf 'server_side_code_edit_authorized=false\n'
  printf 'dependency_repair_attempt=run04_reuse_validated_dependency\n'
  printf 'expected_result_basename=%s\n' "${EXPECTED_RUN_LABEL}"
  printf 'nfs_no_root_squash_operator_verified=true\n'
  printf 'nfs_expected_new_object_uid=0\n'
  printf 'nfs_expected_new_object_gid=%s\n' "${EXPECTED_SHARED_GID}"
  printf 'dependency_default_root=repo_server_local_nfs\n'
  printf 'global_git_safe_directory_mutation=false\n'
  printf 'invalid_dependency_state_action=quarantine_then_atomic_rebuild\n'
  printf 'dependency_log_attempt_local_and_truncated=true\n'
  printf 'install_marker_written_after_import_probe_only=true\n'
  printf 'ucm_cmake_python_binding=tracked_wrapper_rewrites_to_Python_EXECUTABLE\n'
  printf 'parent_attribution_task_id=%s\n' "${PARENT_ATTRIBUTION_TASK_ID}"
  printf 'parent_attribution_manifest_bytes=%s\n' \
    "${PARENT_ATTRIBUTION_MANIFEST_BYTES}"
  printf 'parent_attribution_manifest_sha256=%s\n' \
    "${PARENT_ATTRIBUTION_MANIFEST_SHA256}"
  printf 'parent_run03_fa_block_size_bytes=%s\n' \
    "${UCM_RUN03_FA_BLOCK_SIZE_BYTES}"
  printf 'parent_run03_wa_block_size_bytes=%s\n' \
    "${UCM_RUN03_WA_BLOCK_SIZE_BYTES}"
  printf 'ucm_cache_buffer_capacity_gib_per_fawa_store=%s\n' \
    "${UCM_CACHE_BUFFER_GIB}"
  printf 'ucm_cache_fawa_store_count=%s\n' "${UCM_CACHE_STORE_COUNT}"
  printf 'ucm_load_exclusive_buffer_number=%s\n' "${UCM_LOAD_EXCLUSIVE_BUFFER_NUMBER}"
  printf 'ucm_required_buffer_number=2048\n'
  printf 'ucm_configured_fa_buffer_number=5391\n'
  printf 'ucm_configured_wa_buffer_number=2592\n'
  printf 'ucm_posix_total_capacity_gib_before_fawa_split=%s\n' \
    "${UCM_POSIX_TOTAL_CAPACITY_GIB}"
  printf 'ucm_posix_capacity_gib_per_store_after_fawa_split=32\n'
  printf 'ucm_posix_data_dir_shard_bytes=%s\n' \
    "${UCM_POSIX_DATA_DIR_SHARD_BYTES}"
  printf 'ucm_posix_directory_shard_count=256\n'
  printf 'ucm_posix_gc_trigger_threshold_ratio=0.7\n'
  printf 'ucm_posix_gc_recycle_percent=0.1\n'
  printf 'ucm_posix_fa_minimum_capacity_gib=12\n'
  printf 'ucm_posix_wa_minimum_capacity_gib=24\n'
  printf 'ucm_posix_fa_recycle_files_per_shard=2\n'
  printf 'ucm_posix_wa_recycle_files_per_shard=1\n'
  printf 'conservative_total_buffer_gib=%s\n' \
    "$((UCM_CACHE_BUFFER_GIB * UCM_CACHE_STORE_COUNT * UCM_TP_SIZE))"
  printf 'pre_npu_parent_geometry_shm_memavailable_and_storage_gate=true\n'
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
test -f "${FAWA_GEOMETRY}"
test -x "${CMAKE_PYTHON_WRAPPER}"
test "$(id -u)" -eq 0
test -x /data/node0_disk1/Public/npu_stop.sh
test -x /data/node0_disk1/Public/npu_keep_alive.sh
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = \
  "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
test -d "${PARENT_ATTRIBUTION_ROOT}"
test -f "${PARENT_ATTRIBUTION_ROOT}/candidate_manifest.server_local.json"
test -f "${PARENT_ATTRIBUTION_ROOT}/fawa_store_geometry.json"
test -f "${PARENT_ATTRIBUTION_ROOT}/task_grade.txt"
test "$(wc -c < "${PARENT_ATTRIBUTION_ROOT}/candidate_manifest.server_local.json" | tr -d ' ')" = \
  "${PARENT_ATTRIBUTION_MANIFEST_BYTES}"
test "$(sha256sum "${PARENT_ATTRIBUTION_ROOT}/candidate_manifest.server_local.json" | awk '{print $1}')" = \
  "${PARENT_ATTRIBUTION_MANIFEST_SHA256}"
test "$(cat "${PARENT_ATTRIBUTION_ROOT}/task_grade.txt")" = \
  attributed_p8_2_k2_r0_run03_fawa_startup_failure
"${BASE_PYTHON}" - "${PARENT_ATTRIBUTION_ROOT}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = json.loads(
    (root / "candidate_manifest.server_local.json").read_text(
        encoding="utf-8"
    )
)
for entry in manifest["files"]:
    path = root / entry["relative_path"]
    if not path.is_file():
        raise SystemExit(f"missing parent payload: {path}")
    if path.stat().st_size != entry["bytes"]:
        raise SystemExit(f"parent payload byte mismatch: {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit(f"parent payload SHA-256 mismatch: {path}")
PY
mkdir -p "${RESULT_DIR}" "$(dirname "${UCM_SOURCE_ROOT}")" \
  "$(dirname "${UCM_ENV_PREFIX}")" "$(dirname "${DEPENDENCY_LOG}")" \
  "$(dirname "${PROVISION_EVENT_LOG}")" "${CMAKE_WRAPPER_DIR}" \
  "${UCM_STORAGE_ROOT}"
: > "${DEPENDENCY_LOG}"
: > "${PROVISION_EVENT_LOG}"
: > "${CMAKE_WRAPPER_LOG}"

keep_alive_stopped=false
lifecycle_pid=
stop_attempted=false
lifecycle_started=false
stop_exit=0
restart_exit=0
experiment_exit=0
dependency_exit=1
capacity_exit=1
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

validate_nfs_creation_identity() {
  local parent
  local probe
  local uid
  local gid
  local detail
  for parent in "$(dirname -- "${UCM_SOURCE_ROOT}")" \
    "$(dirname -- "${UCM_ENV_PREFIX}")"; do
    probe=$(mktemp "${parent}/.ak_nfs_identity_${RUN_LABEL}.XXXXXX")
    uid=$(stat -c '%u' "${probe}")
    gid=$(stat -c '%g' "${probe}")
    detail=uid=${uid}_gid=${gid}_expected_uid_0_gid_${EXPECTED_SHARED_GID}
    rm -- "${probe}"
    if test "${uid}" -ne 0 || test "${gid}" -ne "${EXPECTED_SHARED_GID}"; then
      append_provision_event identity_failed nfs_creation_probe \
        "${parent}" "${parent}" "${detail}"
      return 1
    fi
    append_provision_event identity_passed nfs_creation_probe \
      "${parent}" "${parent}" "${detail}"
  done
}

tree_owned_by_current_user_and_group() {
  EXPECTED_SHARED_GID="${EXPECTED_SHARED_GID}" \
  "${BASE_PYTHON}" - "$1" <<'PY'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected_uid = os.geteuid()
expected_gid = int(os.environ["EXPECTED_SHARED_GID"])
paths = [root]
if root.is_dir():
    paths.extend(root.rglob("*"))
for path in paths:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        print(f"ownership probe raced with removal: {path}", file=sys.stderr)
        raise SystemExit(1)
    if stat.st_uid != expected_uid or stat.st_gid != expected_gid:
        print(
            "identity mismatch: "
            f"path={path} expected_uid={expected_uid} actual_uid={stat.st_uid} "
            f"expected_gid={expected_gid} actual_gid={stat.st_gid}",
            file=sys.stderr,
        )
        raise SystemExit(1)
PY
}

validate_ucm_source() {
  local source_root=$1
  test -d "${source_root}/.git" || return 1
  tree_owned_by_current_user_and_group "${source_root}" || return 1
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
  test -f "${source_root}/ucm/integration/vllm/hma_connector.py" || return 1
  test -f "${source_root}/ucm/store/posix/cc/shard_gc.cc" || return 1
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
  tree_owned_by_current_user_and_group "${env_root}" || return 1
  test -f "${marker}" || return 1
  test "$(cat "${marker}")" = "${UCM_COMMIT}" || return 1
  ucm_import_probe "${env_root}/bin/python" || return 1
}

build_and_promote_ucm_env() {
  local parent
  local env_stage
  local marker_tmp
  local real_cmake
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
    real_cmake=$(command -v cmake) || exit 1
    test -x "${real_cmake}" || exit 1
    test ! -e "${CMAKE_WRAPPER_DIR}/cmake" || exit 1
    ln -s "${CMAKE_PYTHON_WRAPPER}" "${CMAKE_WRAPPER_DIR}/cmake" || exit 1
    PATH="${CMAKE_WRAPPER_DIR}:${PATH}" \
    UCM_REAL_CMAKE="${real_cmake}" \
    UCM_BUILD_PYTHON="${env_stage}/bin/python" \
    UCM_CMAKE_WRAPPER_LOG="${CMAKE_WRAPPER_LOG}" \
    PLATFORM=ascend ENABLE_SPARSE=false \
      "${env_stage}/bin/python" -m pip install \
      --disable-pip-version-check --no-input \
      --no-build-isolation --no-deps "${UCM_SOURCE_ROOT}" || exit 1
    grep -F 'is_configure=1' "${CMAKE_WRAPPER_LOG}" >/dev/null || exit 1
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
  CMAKE_WRAPPER_LOG="${CMAKE_WRAPPER_LOG}" \
  CMAKE_PYTHON_WRAPPER="${CMAKE_PYTHON_WRAPPER}" \
  EXPECTED_SHARED_GID="${EXPECTED_SHARED_GID}" \
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
cmake_wrapper_log = Path(os.environ["CMAKE_WRAPPER_LOG"])
cmake_python_wrapper = Path(os.environ["CMAKE_PYTHON_WRAPPER"])
expected_uid = os.geteuid()
expected_gid = int(os.environ["EXPECTED_SHARED_GID"])

def tree_identity(path):
    if not path.exists():
        return False
    try:
        return all(
            candidate.lstat().st_uid == expected_uid
            and candidate.lstat().st_gid == expected_gid
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
source_owned = tree_identity(source)
venv_owned = tree_identity(venv)
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
    "ucm/integration/vllm/hma_connector.py",
    "ucm/store/posix/cc/shard_gc.cc",
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
cmake_wrapper_lines = (
    cmake_wrapper_log.read_text(encoding="utf-8", errors="replace").splitlines()
    if cmake_wrapper_log.is_file()
    else []
)
summary = {
    "dependency_status": os.environ["DEPENDENCY_STATUS"],
    "dependency_attempt": "run04_reuse_validated_dependency",
    "dependency_log_server_path": str(dependency_log),
    "dependency_log_bytes": dependency_log.stat().st_size if dependency_log.is_file() else 0,
    "dependency_log_truncated_before_attempt": True,
    "global_git_safe_directory_mutated": False,
    "ucm_git_url": os.environ["UCM_GIT_URL"],
    "ucm_expected_commit": os.environ["UCM_COMMIT"],
    "ucm_source_root": str(source),
    "ucm_source_owner_uid": source.stat().st_uid if source.exists() else None,
    "ucm_source_owner_gid": source.stat().st_gid if source.exists() else None,
    "expected_current_user_uid": expected_uid,
    "expected_shared_group_gid": expected_gid,
    "ucm_source_tree_owned_by_current_user": source_owned,
    "ucm_source_tree_has_expected_uid_gid": source_owned,
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
    "ucm_env_tree_has_expected_uid_gid": venv_owned,
    "ucm_install_marker_path": str(marker),
    "ucm_install_marker_value": marker_value,
    "ucm_install_marker_valid": marker_value == os.environ["UCM_COMMIT"],
    "base_conda_environment_mutated": False,
    "critical_source_sha256": critical,
    "python_import_probe": import_probe,
    "nfs_no_root_squash_operator_verified": True,
    "nfs_creation_identity_probe_count": sum(
        event.get("kind") == "nfs_creation_probe" for event in events
    ),
    "nfs_creation_identity_passed": (
        sum(
            event.get("event") == "identity_passed"
            and event.get("kind") == "nfs_creation_probe"
            for event in events
        )
        == 2
    ),
    "cmake_python_wrapper_path": str(cmake_python_wrapper),
    "cmake_python_wrapper_sha256": (
        hashlib.sha256(cmake_python_wrapper.read_bytes()).hexdigest()
        if cmake_python_wrapper.is_file()
        else None
    ),
    "cmake_wrapper_invocation_count": len(cmake_wrapper_lines),
    "cmake_wrapper_configure_invocation_count": sum(
        "is_configure=1" in line for line in cmake_wrapper_lines
    ),
    "cmake_wrapper_uppercase_rewrite_count": sum(
        "rewrote_uppercase=1" in line for line in cmake_wrapper_lines
    ),
    "cmake_python_binding_status": (
        "tracked_wrapper_exercised"
        if cmake_wrapper_lines
        else (
            "clean_validated_venv_reused_no_rebuild_needed"
            if os.environ["DEPENDENCY_STATUS"] == "ready"
            else "not_exercised_dependency_failed"
        )
    ),
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
  validate_nfs_creation_identity || return 1
  ensure_ucm_source || return 1
  ensure_ucm_env || return 1
}

write_startup_capacity_summary() {
  local dependency_status=$1
  free -b > "${RESULT_DIR}/runtime/host_memory_before_npu.txt"
  df -B1 /dev/shm > "${RESULT_DIR}/runtime/shm_before_npu.txt"
  df -B1 "${UCM_STORAGE_ROOT}" \
    > "${RESULT_DIR}/runtime/ucm_storage_before_npu.txt"
  "${BASE_PYTHON}" "${FAWA_GEOMETRY}" \
    --output "${RESULT_DIR}/startup_capacity_summary.json" \
    --dependency-status "${dependency_status}" \
    --parent-geometry \
      "${PARENT_ATTRIBUTION_ROOT}/fawa_store_geometry.json" \
    --storage-root "${UCM_STORAGE_ROOT}" \
    --cache-buffer-gib-per-store "${UCM_CACHE_BUFFER_GIB}" \
    --cache-store-count "${UCM_CACHE_STORE_COUNT}" \
    --tensor-parallel-size "${UCM_TP_SIZE}" \
    --cache-headroom-gib "${UCM_CAPACITY_HEADROOM_GIB}" \
    --total-posix-capacity-gib "${UCM_POSIX_TOTAL_CAPACITY_GIB}" \
    --fawa-split-count "${UCM_POSIX_SPLIT_COUNT}" \
    --posix-headroom-gib "${UCM_POSIX_HEADROOM_GIB}" \
    --data-dir-shard-bytes "${UCM_POSIX_DATA_DIR_SHARD_BYTES}" \
    --expected-fa-block-size-bytes "${UCM_RUN03_FA_BLOCK_SIZE_BYTES}" \
    --expected-wa-block-size-bytes "${UCM_RUN03_WA_BLOCK_SIZE_BYTES}" \
    --cache-load-exclusive-buffer-number \
      "${UCM_LOAD_EXCLUSIVE_BUFFER_NUMBER}"
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
  CAPACITY_EXIT="${capacity_exit}" \
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
        (
            int(os.environ["DEPENDENCY_EXIT"]) != 0
            or int(os.environ["CAPACITY_EXIT"]) != 0
        )
        and os.environ["STOP_ATTEMPTED"] != "true"
        and os.environ["LIFECYCLE_STARTED"] != "true"
    ),
    "experiment_exit_code": int(os.environ["EXPERIMENT_EXIT"]),
    "dependency_exit_code": int(os.environ["DEPENDENCY_EXIT"]),
    "startup_capacity_exit_code": int(os.environ["CAPACITY_EXIT"]),
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
  printf 'startup_capacity_exit=%s\n' "${capacity_exit}"
  printf 'experiment_exit=%s\n' "${experiment_exit}"
  printf 'restart_exit=%s\n' "${restart_exit}"
  printf 'cleanup_status=%s\n' "${cleanup_status}"
  printf 'result_summary=%s\n' "${RESULT_DIR}/result_summary.md"
  printf 'task_grade=%s\n' "$(cat "${RESULT_DIR}/task_grade.txt")"
  printf '%s\n' 'dependency_and_environment_summary:'
  cat "${RESULT_DIR}/dependency_and_environment_summary.json"
  printf '%s\n' 'startup_capacity_summary:'
  cat "${RESULT_DIR}/startup_capacity_summary.json"
  printf '%s\n' 'startup_failure_summary:'
  cat "${RESULT_DIR}/startup_failure_summary.json"
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
  set +e
  write_startup_capacity_summary dependency_failed
  capacity_exit=$?
  set -e
  experiment_exit=1
  exit 0
fi
write_dependency_summary ready

set +e
write_startup_capacity_summary ready
capacity_exit=$?
set -e
if test "${capacity_exit}" -ne 0; then
  experiment_exit=3
  exit 0
fi

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
