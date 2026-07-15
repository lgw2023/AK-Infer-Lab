from __future__ import annotations

import argparse
from pathlib import Path

from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    prepare_artifacts,
)
from tools.inference_contracts.run_deepseek_p6_3b_r1_hybrid_kv_repair import (
    _grade_for_lineage,
    build_r1_plan,
    finalize_artifacts as finalize_repair_artifacts,
    grade_r1_evidence,
)
from tools.inference_contracts.p6_3b_r1_hybrid_kv_runtime_patch import (
    EXPECTED_SOURCE_SHA256,
)


def finalize_artifacts(artifact_dir: Path):
    return finalize_repair_artifacts(artifact_dir, lineage="r2")


def grade_r2_evidence(request_rows, *, diagnostics, cleanup):
    grading = grade_r1_evidence(
        request_rows,
        diagnostics=diagnostics,
        cleanup=cleanup,
        require_deferred_install=True,
    )
    grading["server_grade"] = _grade_for_lineage(
        grading["server_grade"], "r2"
    )
    return grading


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "prepare":
        prepare_artifacts(
            args.source_payload,
            args.artifact_dir,
            args.model_name,
            plan=build_r1_plan(),
        )
        return 0
    grading = finalize_artifacts(args.artifact_dir)
    return (
        0
        if grading["server_grade"]
        == "candidate_green_p6_3b_r2_hybrid_kv_repair"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
