#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 1; then
  echo "usage: $0 RESULT_DIR" >&2
  exit 64
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${REPO_ROOT:-$(cd -- "${SCRIPT_DIR}/../.." && pwd)}
RESULT_DIR=$1
TASK_ID=p8_2_k2_r0_run03_fawa_startup_attribution_2026_0729
RUN_ID=${TASK_ID}_run01
PARENT_TASK_ID=p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728
PARENT_RESULT_DIR=${PARENT_RESULT_DIR:-${REPO_ROOT}/server_results/${PARENT_TASK_ID}_run03}
UCM_COMMIT=01cbf9b71892c88319862fa57f195b0bef93fa6f
UCM_SOURCE_ROOT=${UCM_SOURCE_ROOT:-${REPO_ROOT}/server_local/third_party/unified-cache-management-01cbf9b}
BASE_ENV_PREFIX=${BASE_ENV_PREFIX:-${REPO_ROOT}/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1}
PYTHON_BIN=${BASE_ENV_PREFIX}/bin/python
ANALYZER=${SCRIPT_DIR}/run_deepseek_p8_2_k2_r0_run03_fawa_startup_attribution.py
PARENT_MANIFEST_SHA256=a278c44dbf879c42fe2119ca8a7708b7bc0aea8103e4387af1ff3c73b974cbe4
PARENT_MANIFEST_BYTES=3434
EXPECTED_KEEP_ALIVE_MARKER_COUNT=16
EXPECTED_CARD_IDS_CSV=0,1,2,3,4,5,6,7
TEMP_ROOT=

audit_contract() {
  printf 'task_id=%s\n' "${TASK_ID}"
  printf 'run_id=%s\n' "${RUN_ID}"
  printf 'execution_mode=zero_npu_read_only_run03_raw_startup_and_pinned_source_attribution\n'
  printf 'parent_task_id=%s\n' "${PARENT_TASK_ID}"
  printf 'parent_result_dir=%s\n' "${PARENT_RESULT_DIR}"
  printf 'parent_manifest_sha256=%s\n' "${PARENT_MANIFEST_SHA256}"
  printf 'parent_manifest_bytes=%s\n' "${PARENT_MANIFEST_BYTES}"
  printf 'ucm_commit=%s\n' "${UCM_COMMIT}"
  printf 'ucm_source_root=%s\n' "${UCM_SOURCE_ROOT}"
  printf 'parent_and_source_mutation=false\n'
  printf 'npu_started=false\n'
  printf 'vllm_started=false\n'
  printf 'model_requests_sent=0\n'
  printf 'keep_alive_action=left_running\n'
  printf 'npu_stop_authorized=false\n'
  printf 'npu_restore_required=false\n'
  printf 'run04_authorized=false\n'
  printf 'server_side_code_edit_authorized=false\n'
  printf 'result_transfer_authorized=true\n'
  printf 'automatic_transfer_allowed=false\n'
  printf 'next_task_authorized=false\n'
}

if test "${P8_2_K2_R0_RUN03_ATTRIBUTION_AUDIT_ONLY:-0}" = 1; then
  audit_contract
  exit 0
fi

cleanup_temp() {
  if test -n "${TEMP_ROOT}" && test -d "${TEMP_ROOT}"; then
    rm -r -- "${TEMP_ROOT}"
  fi
}
trap cleanup_temp EXIT INT TERM

test "$(basename -- "${RESULT_DIR}")" = "${RUN_ID}"
test ! -e "${RESULT_DIR}"
test -x "${PYTHON_BIN}"
test -f "${ANALYZER}"
test -d "${PARENT_RESULT_DIR}"
test -f "${PARENT_RESULT_DIR}/runtime/vllm_server.log"
test -d "${UCM_SOURCE_ROOT}/.git"
test "$(git -C "${REPO_ROOT}" branch --show-current)" = main
test "$(git -C "${REPO_ROOT}" rev-parse HEAD)" = \
  "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)"
test "$(git -C "${UCM_SOURCE_ROOT}" rev-parse HEAD)" = "${UCM_COMMIT}"
test -z "$(git -C "${UCM_SOURCE_ROOT}" status --porcelain --untracked-files=no)"
test "$(wc -c < "${PARENT_RESULT_DIR}/candidate_manifest.server_local.json" | tr -d ' ')" = \
  "${PARENT_MANIFEST_BYTES}"
test "$(sha256sum "${PARENT_RESULT_DIR}/candidate_manifest.server_local.json" | awk '{print $1}')" = \
  "${PARENT_MANIFEST_SHA256}"

TEMP_ROOT=$(mktemp -d \
  "${REPO_ROOT}/server_local/.${RUN_ID}.working.XXXXXX")
RESOURCE_OBSERVATION=${TEMP_ROOT}/resource_observation_summary.json

snapshot_runtime() {
  local phase=$1
  local output_dir=${TEMP_ROOT}/${phase}
  mkdir -p "${output_dir}"
  ps -eo args= > "${output_dir}/processes.txt"
  ss -ltnp > "${output_dir}/listening_ports.txt" 2>&1
  grep -E '#[0-7]#' "${output_dir}/processes.txt" \
    > "${output_dir}/keep_alive_processes.txt" || true
  pgrep -af '[v]llm.*serve.*DeepSeek-V4-Flash-w8a8-mtp' \
    > "${output_dir}/vllm_processes.txt" 2>&1 || true
}

snapshot_runtime before
snapshot_runtime observed_after

PHASE_BEFORE=${TEMP_ROOT}/before \
PHASE_AFTER=${TEMP_ROOT}/observed_after \
REPO_ROOT="${REPO_ROOT}" \
EXPECTED_MARKERS="${EXPECTED_KEEP_ALIVE_MARKER_COUNT}" \
EXPECTED_CARD_IDS="${EXPECTED_CARD_IDS_CSV}" \
"${PYTHON_BIN}" - "${RESOURCE_OBSERVATION}" <<'PY'
import json
import os
import re
import subprocess
import sys
from pathlib import Path

before = Path(os.environ["PHASE_BEFORE"])
after = Path(os.environ["PHASE_AFTER"])
expected_markers = int(os.environ["EXPECTED_MARKERS"])
expected_cards = [int(item) for item in os.environ["EXPECTED_CARD_IDS"].split(",")]

def snapshot(root):
    processes = (root / "processes.txt").read_text(encoding="utf-8", errors="replace")
    ports = (root / "listening_ports.txt").read_text(encoding="utf-8", errors="replace")
    vllm = (root / "vllm_processes.txt").read_text(encoding="utf-8", errors="replace")
    markers = re.findall(r"#([0-7])#", processes)
    return {
        "keep_alive_marker_count": len(markers),
        "keep_alive_card_ids": sorted({int(item) for item in markers}),
        "port_7000_listener_count": sum(
            re.search(r":7000\s", line) is not None for line in ports.splitlines()
        ),
        "vllm_residual_process_count": sum(bool(line.strip()) for line in vllm.splitlines()),
    }

before_value = snapshot(before)
after_value = snapshot(after)
if before_value["keep_alive_marker_count"] != expected_markers:
    raise SystemExit("keep-alive marker count is not the expected 16 before analysis")
if before_value["keep_alive_card_ids"] != expected_cards:
    raise SystemExit("keep-alive card set is not 0-7 before analysis")
if before_value["port_7000_listener_count"] != 0:
    raise SystemExit("port 7000 was already occupied")
if before_value["vllm_residual_process_count"] != 0:
    raise SystemExit("pre-existing DeepSeek vLLM process found")
if after_value != before_value:
    raise SystemExit("runtime state changed during zero-NPU pre-analysis observation")
tracked_clean = subprocess.check_output(
    [
        "git",
        "-C",
        os.environ["REPO_ROOT"],
        "status",
        "--porcelain",
        "--untracked-files=no",
    ],
    text=True,
).strip() == ""
summary = {
    "npu_started": False,
    "vllm_started": False,
    "model_requests_sent": 0,
    "keep_alive_action": "left_running",
    "npu_stop_attempted": False,
    "npu_restore_attempted": False,
    "keep_alive_marker_count_before": before_value["keep_alive_marker_count"],
    "keep_alive_marker_count_after": after_value["keep_alive_marker_count"],
    "keep_alive_card_ids_before": before_value["keep_alive_card_ids"],
    "keep_alive_card_ids_after": after_value["keep_alive_card_ids"],
    "port_7000_listener_count_before": before_value["port_7000_listener_count"],
    "port_7000_listener_count_after": after_value["port_7000_listener_count"],
    "vllm_residual_process_count_before": before_value["vllm_residual_process_count"],
    "vllm_residual_process_count_after": after_value["vllm_residual_process_count"],
    "tracked_worktree_clean": tracked_clean,
    "post_analyzer_runtime_state_verified": False,
}
Path(sys.argv[1]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY

"${PYTHON_BIN}" "${ANALYZER}" analyze \
  --parent-result-dir "${PARENT_RESULT_DIR}" \
  --result-dir "${RESULT_DIR}" \
  --ucm-source-root "${UCM_SOURCE_ROOT}" \
  --resource-observation "${RESOURCE_OBSERVATION}"

snapshot_runtime verified_after
PHASE_BEFORE=${TEMP_ROOT}/before \
PHASE_AFTER=${TEMP_ROOT}/verified_after \
RESULT_RESOURCE=${RESULT_DIR}/resource_observation_summary.json \
EXPECTED_MARKERS="${EXPECTED_KEEP_ALIVE_MARKER_COUNT}" \
EXPECTED_CARD_IDS="${EXPECTED_CARD_IDS_CSV}" \
"${PYTHON_BIN}" - <<'PY'
import json
import os
import re
from pathlib import Path

def snapshot(root):
    root = Path(root)
    processes = (root / "processes.txt").read_text(encoding="utf-8", errors="replace")
    ports = (root / "listening_ports.txt").read_text(encoding="utf-8", errors="replace")
    vllm = (root / "vllm_processes.txt").read_text(encoding="utf-8", errors="replace")
    markers = re.findall(r"#([0-7])#", processes)
    return {
        "keep_alive_marker_count": len(markers),
        "keep_alive_card_ids": sorted({int(item) for item in markers}),
        "port_7000_listener_count": sum(
            re.search(r":7000\s", line) is not None for line in ports.splitlines()
        ),
        "vllm_residual_process_count": sum(bool(line.strip()) for line in vllm.splitlines()),
    }

before = snapshot(os.environ["PHASE_BEFORE"])
after = snapshot(os.environ["PHASE_AFTER"])
expected_markers = int(os.environ["EXPECTED_MARKERS"])
expected_cards = [int(item) for item in os.environ["EXPECTED_CARD_IDS"].split(",")]
if after != before:
    raise SystemExit("runtime state changed while analyzer was running")
if after["keep_alive_marker_count"] != expected_markers:
    raise SystemExit("keep-alive marker count changed")
if after["keep_alive_card_ids"] != expected_cards:
    raise SystemExit("keep-alive card set changed")
path = Path(os.environ["RESULT_RESOURCE"])
summary = json.loads(path.read_text(encoding="utf-8"))
summary["keep_alive_marker_count_after"] = after["keep_alive_marker_count"]
summary["keep_alive_card_ids_after"] = after["keep_alive_card_ids"]
summary["port_7000_listener_count_after"] = after["port_7000_listener_count"]
summary["vllm_residual_process_count_after"] = after["vllm_residual_process_count"]
summary["post_analyzer_runtime_state_verified"] = True
path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY

"${PYTHON_BIN}" "${ANALYZER}" package --result-dir "${RESULT_DIR}"

printf '%s\n' 'K2_R0_RUN03_ATTRIBUTION_REPORT_BEGIN'
printf 'task_id=%s\n' "${TASK_ID}"
printf 'run_id=%s\n' "${RUN_ID}"
printf 'head=%s\n' "$(git -C "${REPO_ROOT}" rev-parse HEAD)"
printf 'origin_main=%s\n' "$(git -C "${REPO_ROOT}" rev-parse origin/main)"
printf 'ahead_behind=%s\n' \
  "$(git -C "${REPO_ROOT}" rev-list --left-right --count HEAD...origin/main)"
printf 'tracked_clean=%s\n' \
  "$(test -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no)" && printf true || printf false)"
printf 'task_grade=%s\n' "$(cat "${RESULT_DIR}/task_grade.txt")"
printf 'result_summary=%s\n' "${RESULT_DIR}/result_summary.md"
printf '%s\n' 'parent_provenance:'
cat "${RESULT_DIR}/parent_provenance.json"
printf '%s\n' 'startup_exception_summary:'
cat "${RESULT_DIR}/startup_exception_summary.json"
printf '%s\n' 'fawa_store_geometry:'
cat "${RESULT_DIR}/fawa_store_geometry.json"
printf '%s\n' 'source_constructor_lineage:'
cat "${RESULT_DIR}/source_constructor_lineage.json"
printf '%s\n' 'resource_observation_summary:'
cat "${RESULT_DIR}/resource_observation_summary.json"
printf '%s\n' 'grading_summary:'
cat "${RESULT_DIR}/grading_summary.json"
printf '%s\n' 'result_summary_body:'
cat "${RESULT_DIR}/result_summary.md"
printf '%s\n' 'startup_traceback_excerpt:'
cat "${RESULT_DIR}/startup_traceback_excerpt.txt"
printf '%s\n' 'candidate_manifest:'
cat "${RESULT_DIR}/candidate_manifest.server_local.json"
printf 'candidate_manifest_bytes=%s\n' \
  "$(wc -c < "${RESULT_DIR}/candidate_manifest.server_local.json" | tr -d ' ')"
printf 'candidate_manifest_sha256=%s\n' \
  "$(sha256sum "${RESULT_DIR}/candidate_manifest.server_local.json" | awk '{print $1}')"
printf '%s\n' 'K2_R0_RUN03_ATTRIBUTION_REPORT_END'
