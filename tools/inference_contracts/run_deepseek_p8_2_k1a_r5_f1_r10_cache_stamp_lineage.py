from __future__ import annotations

import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _configure_runtime() -> None:
    values = {
        "P8_2_K1A_TASK_ID": (
            "p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723"
        ),
        "P8_2_K1A_STAGE_LABEL": "P8.2-K1A-R5-F1-R10",
        "P8_2_K1A_F1_SCHEMA_TAG": "p8_2_k1a_r5_f1_r10",
        "P8_2_K1A_F1_GRADE_PREFIX": "red_p8_2_k1a_r5_f1_r10",
        "P8_2_K1A_CANDIDATE_GREEN": (
            "candidate_green_p8_2_k1a_r5_f1_r10_"
            "cache_stamp_lineage_attributed_h2d_restore"
        ),
        "P8_2_K1A_H2D_TARGET_BLOCK_COUNT": "128",
        "P8_2_K1A_RESTORE_MATCH_TOKENS": "16384",
        "P8_2_K1A_BLOCK_SIZE_TOKENS": "128",
        "P8_2_K1A_REQUIRE_RESTORE_GROUP_ELIGIBILITY": "1",
        "P8_2_K1A_REQUIRE_EFFECTIVE_GROUP_GEOMETRY": "1",
        "P8_2_K1A_TARGET_CACHE_STAMP_LINEAGE": "1",
        "P8_2_K1A_STOP_ON_FIRST_CPU_TARGET_EVICTION": "0",
        "P8_2_K1A_ALLOW_PRESSURE_BEFORE_KEYSPACE_EXACT": "1",
        "P8_2_K1A_LOGICAL_KEYSPACE_DIAGNOSTICS": "1",
        "P8_2_K1A_TARGET_STORE_LINEAGE_DIAGNOSTICS": "1",
        "P8_2_K1A_REQUIRE_TARGET_STORE_LINEAGE": "1",
        "P8_2_K1A_REQUIRE_POST_ABORT_FRESH_REVALIDATION": "1",
        "P8_2_K1A_REQUIRE_LOGICAL_RESTORE_WINDOW_FOR_RESTORE": "1",
        "P8_2_K1A_RESULT_SUMMARY_TITLE": (
            "logical 128-block target from runtime cache-stamp lineage"
        ),
        "P8_2_K1A_CLAIM_BOUNDARY": (
            "accepted_capacity_single_lifecycle_runtime_cache_stamp_lineage_"
            "logical_128_block_window_and_conditional_h2d_candidate_only"
        ),
    }
    for key, value in values.items():
        os.environ.setdefault(key, value)


_configure_runtime()


from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore import (  # noqa: E402
    main,
)


if __name__ == "__main__":
    raise SystemExit(main())
