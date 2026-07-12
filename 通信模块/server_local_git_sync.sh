#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
MIRROR_ROOT="${AK_SERVER_MIRROR_ROOT:-/data/node0_disk1/liguowei/AK-Infer-Lab}"
LOCAL_WORKTREE="${AK_SERVER_LOCAL_WORKTREE:-/data/node0_disk1/liguowei/AK-Infer-Lab-server-local}"
LOCAL_BRANCH="${AK_SERVER_LOCAL_BRANCH:-server-local/runtime-adaptations}"
REMOTE_NAME="${AK_SERVER_REMOTE_NAME:-origin}"
UPSTREAM_BRANCH="${AK_SERVER_UPSTREAM_BRANCH:-main}"
UPSTREAM_REF="${REMOTE_NAME}/${UPSTREAM_BRANCH}"
REPORT_ROOT="${AK_SERVER_GIT_REPORT_ROOT:-${MIRROR_ROOT}/server_local/git_sync_reports}"
ALLOW_SAME_PATH_OVERLAP="${AK_SERVER_ALLOW_SAME_PATH_OVERLAP:-0}"

usage() {
  printf 'usage: %s {init|check|sync}\n' "$0" >&2
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

validate_inputs() {
  case "${MODE}" in
    init|check|sync) ;;
    *) usage; exit 64 ;;
  esac

  case "${LOCAL_BRANCH}" in
    main|master|refs/heads/main|refs/heads/master)
      fail "server-local branch must not be main or master"
      ;;
  esac
  case "${ALLOW_SAME_PATH_OVERLAP}" in
    0|1) ;;
    *) fail "AK_SERVER_ALLOW_SAME_PATH_OVERLAP must be 0 or 1" ;;
  esac

  git -C "${MIRROR_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || fail "mirror root is not a Git worktree: ${MIRROR_ROOT}"
  [ "${LOCAL_WORKTREE}" != "${MIRROR_ROOT}" ] \
    || fail "server-local worktree must be separate from the mirror root"
}

fetch_upstream() {
  git -C "${MIRROR_ROOT}" fetch "${REMOTE_NAME}" "${UPSTREAM_BRANCH}"
  git -C "${MIRROR_ROOT}" rev-parse --verify "${UPSTREAM_REF}^{commit}" >/dev/null
}

ensure_local_worktree() {
  if ! git -C "${MIRROR_ROOT}" show-ref --verify --quiet "refs/heads/${LOCAL_BRANCH}"; then
    git -C "${MIRROR_ROOT}" branch "${LOCAL_BRANCH}" "${UPSTREAM_REF}"
  fi

  if [ -e "${LOCAL_WORKTREE}/.git" ]; then
    actual_branch=$(git -C "${LOCAL_WORKTREE}" symbolic-ref --quiet --short HEAD || true)
    [ "${actual_branch}" = "${LOCAL_BRANCH}" ] \
      || fail "worktree uses ${actual_branch:-detached}, expected ${LOCAL_BRANCH}"
    return
  fi

  if [ -e "${LOCAL_WORKTREE}" ]; then
    fail "local worktree path already exists but is not a Git worktree: ${LOCAL_WORKTREE}"
  fi
  git -C "${MIRROR_ROOT}" worktree add "${LOCAL_WORKTREE}" "${LOCAL_BRANCH}"
}

require_clean_local_worktree() {
  dirty=$(git -C "${LOCAL_WORKTREE}" status --porcelain)
  [ -z "${dirty}" ] || fail "server-local worktree has uncommitted changes; commit locally or report before sync"
}

write_path_sets() {
  git -C "${MIRROR_ROOT}" diff --name-only "${MERGE_BASE}..${LOCAL_HEAD}" \
    | LC_ALL=C sort -u > "${REPORT_DIR}/server_local_changed_paths.txt"
  git -C "${MIRROR_ROOT}" diff --name-only "${MERGE_BASE}..${UPSTREAM_HEAD}" \
    | LC_ALL=C sort -u > "${REPORT_DIR}/upstream_changed_paths.txt"
  LC_ALL=C comm -12 \
    "${REPORT_DIR}/server_local_changed_paths.txt" \
    "${REPORT_DIR}/upstream_changed_paths.txt" \
    > "${REPORT_DIR}/same_path_overlap.txt"
}

run_conflict_check() {
  mkdir -p "${REPORT_ROOT}"
  REPORT_DIR="${REPORT_ROOT}/$(date '+%Y%m%d_%H%M%S')_$$"
  mkdir -p "${REPORT_DIR}"

  LOCAL_HEAD=$(git -C "${LOCAL_WORKTREE}" rev-parse HEAD)
  UPSTREAM_HEAD=$(git -C "${MIRROR_ROOT}" rev-parse "${UPSTREAM_REF}")
  MERGE_BASE=$(git -C "${MIRROR_ROOT}" merge-base "${LOCAL_HEAD}" "${UPSTREAM_HEAD}")
  write_path_sets

  MERGE_TREE_MODE=write-tree
  set +e
  git -C "${MIRROR_ROOT}" merge-tree --write-tree --name-only --messages \
    "${LOCAL_HEAD}" "${UPSTREAM_HEAD}" \
    > "${REPORT_DIR}/merge_tree.txt" 2>&1
  MERGE_TREE_EXIT_CODE=$?
  set -e

  SAME_PATH_OVERLAP_COUNT=$(wc -l < "${REPORT_DIR}/same_path_overlap.txt" | tr -d ' ')
  if [ "${MERGE_TREE_EXIT_CODE}" -eq 1 ]; then
    STATUS=conflict
    sed -n '2,/^$/p' "${REPORT_DIR}/merge_tree.txt" \
      | sed '/^$/d' \
      | LC_ALL=C sort -u \
      > "${REPORT_DIR}/conflict_paths.txt"
  elif [ "${MERGE_TREE_EXIT_CODE}" -ne 0 ]; then
    STATUS=check_error
    : > "${REPORT_DIR}/conflict_paths.txt"
  elif [ "${SAME_PATH_OVERLAP_COUNT}" -gt 0 ]; then
    STATUS=overlap_review_required
    : > "${REPORT_DIR}/conflict_paths.txt"
  else
    STATUS=clean
    : > "${REPORT_DIR}/conflict_paths.txt"
  fi

  cat > "${REPORT_DIR}/summary.tsv" <<EOF
field	value
status	${STATUS}
mirror_root	${MIRROR_ROOT}
server_local_worktree	${LOCAL_WORKTREE}
server_local_branch	${LOCAL_BRANCH}
server_local_head	${LOCAL_HEAD}
upstream_ref	${UPSTREAM_REF}
upstream_head	${UPSTREAM_HEAD}
merge_base	${MERGE_BASE}
merge_tree_mode	${MERGE_TREE_MODE}
merge_tree_exit_code	${MERGE_TREE_EXIT_CODE}
same_path_overlap_count	${SAME_PATH_OVERLAP_COUNT}
same_path_overlap_acknowledged	${ALLOW_SAME_PATH_OVERLAP}
conflict_path_count	$(wc -l < "${REPORT_DIR}/conflict_paths.txt" | tr -d ' ')
EOF

  printf 'STATUS=%s\nREPORT_DIR=%s\n' "${STATUS}" "${REPORT_DIR}"
}

sync_local_branch() {
  if [ "${STATUS}" = check_error ]; then
    printf 'Conflict precheck failed; no merge was attempted. Report: %s\n' "${REPORT_DIR}" >&2
    return 5
  fi
  if [ "${STATUS}" = conflict ]; then
    printf 'Conflict detected; no merge was attempted. Report: %s\n' "${REPORT_DIR}" >&2
    return 2
  fi
  if [ "${STATUS}" = overlap_review_required ] \
    && [ "${ALLOW_SAME_PATH_OVERLAP}" != 1 ]; then
    printf 'Same-path overlap requires external developer review; no merge was attempted. Report: %s\n' "${REPORT_DIR}" >&2
    return 4
  fi

  before=$(git -C "${LOCAL_WORKTREE}" rev-parse HEAD)
  set +e
  git -C "${LOCAL_WORKTREE}" merge --no-edit "${UPSTREAM_REF}"
  merge_exit_code=$?
  set -e
  if [ "${merge_exit_code}" -ne 0 ]; then
    git -C "${LOCAL_WORKTREE}" merge --abort >/dev/null 2>&1 || true
    printf 'Merge failed after a clean precheck; local merge was aborted.\n' >&2
    return 3
  fi
  after=$(git -C "${LOCAL_WORKTREE}" rev-parse HEAD)
  printf 'SYNCED_FROM=%s\nSYNCED_TO=%s\n' "${before}" "${after}"
}

validate_inputs
fetch_upstream

if [ "${MODE}" = init ]; then
  mirror_dirty=$(git -C "${MIRROR_ROOT}" status --porcelain --untracked-files=no)
  [ -z "${mirror_dirty}" ] \
    || fail "mirror has tracked modifications; do not overwrite them during initialization"
  ensure_local_worktree
fi

[ -e "${LOCAL_WORKTREE}/.git" ] \
  || fail "server-local worktree is not initialized; run init first"
require_clean_local_worktree
run_conflict_check

if [ "${MODE}" = sync ]; then
  sync_local_branch
elif [ "${STATUS}" = check_error ]; then
  exit 5
elif [ "${STATUS}" = conflict ]; then
  exit 2
elif [ "${STATUS}" = overlap_review_required ]; then
  exit 4
fi
