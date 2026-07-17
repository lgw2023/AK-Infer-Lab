#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export REQUEST_RUNNER=${REQUEST_RUNNER:-${SCRIPT_DIR}/run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py}
export BASE_VLLM_ROOT=${BASE_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm}

exec bash "${SCRIPT_DIR}/run_deepseek_p6_3b_r4_r1_mode.sh" "$@"
