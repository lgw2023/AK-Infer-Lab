#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

exec bash \
  "${SCRIPT_DIR}/run_deepseek_p8_2_k1a_r5_f1_r17_full_trace_source_replay.sh" \
  "$@"
