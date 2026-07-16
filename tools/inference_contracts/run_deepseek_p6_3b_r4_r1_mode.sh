#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BASE_MODE_RUNNER=${P6_3B_R4_BASE_MODE_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3b_r4_mode.sh}
test -f "${BASE_MODE_RUNNER}"
REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p6_3b_r4_r1_explicit_matched_ab.py}
export REQUEST_RUNNER

# The new server stores the repository on root-squashed NFS. Preserve the
# archive copy semantics used by R4, except ownership, which cannot be set on
# that mount and does not affect any content hash or runtime behavior.
cp() {
  if test "$#" -eq 3 && test "$1" = -a; then
    command cp -a --no-preserve=ownership "$2" "$3"
    return
  fi
  command cp "$@"
}
export -f cp

exec bash "${BASE_MODE_RUNNER}" "$@"
