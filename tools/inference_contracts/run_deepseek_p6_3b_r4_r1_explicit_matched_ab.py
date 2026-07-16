from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (  # noqa: E402
    run_deepseek_p6_3b_r4_explicit_matched_ab as r4,
)


TASK_ID = (
    "p6_3b_r4_r1_deepseek_v4_flash_w8a8_mtp_explicit_"
    "prefix_cache_matched_ab_2026_0716"
)
CANDIDATE_GREEN = (
    "candidate_green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
)
GRADE_MAP = {
    "blocked_p6_3b_r4_source_or_resource_gate": (
        "blocked_p6_3b_r4_r1_source_or_resource_gate"
    ),
    "red_p6_3b_r4_explicit_prefix_cache_matched_ab_no_success": (
        "red_p6_3b_r4_r1_explicit_prefix_cache_matched_ab_no_success"
    ),
    "yellow_p6_3b_r4_explicit_prefix_cache_matched_ab_partial": (
        "yellow_p6_3b_r4_r1_explicit_prefix_cache_matched_ab_partial"
    ),
    "red_p6_3b_r4_explicit_prefix_cache_evidence_incomplete": (
        "red_p6_3b_r4_r1_explicit_prefix_cache_evidence_incomplete"
    ),
    "candidate_green_p6_3b_r4_explicit_prefix_cache_matched_ab": (
        CANDIDATE_GREEN
    ),
}
CANDIDATE_NAMES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "request_body_manifest.json",
    "mode_group_summary.tsv",
    "paired_request_summary.tsv",
    "grading_inputs.json",
    "hybrid_kv_diagnostic_summary.json",
    "resolved_prefix_cache_config_summary.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
)
SENSITIVITY = (
    "bounded_structured_explicit_prefix_cache_ab_evidence_no_content_payload"
)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _refresh_delivery_manifest(
    artifact_dir: Path, grading: dict[str, Any]
) -> None:
    grading_path = artifact_dir / "grading_inputs.json"
    other_paths = [
        artifact_dir / name
        for name in CANDIDATE_NAMES
        if name != "grading_inputs.json"
    ]
    for path in other_paths:
        if not path.exists():
            raise FileNotFoundError(path)
    other_total = sum(path.stat().st_size for path in other_paths)
    for _ in range(10):
        _write_json(grading_path, grading)
        total = other_total + grading_path.stat().st_size
        size_gate = total <= 71680
        if (
            grading.get("candidate_total_bytes") == total
            and grading.get("candidate_size_gate_pass") is size_gate
        ):
            break
        grading["candidate_total_bytes"] = total
        grading["candidate_size_gate_pass"] = size_gate
    else:
        raise RuntimeError("R4-R1 grading candidate size did not converge")

    rows = []
    for name in CANDIDATE_NAMES:
        path = artifact_dir / name
        rows.append(
            (
                str(path),
                path.stat().st_size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                SENSITIVITY,
            )
        )
    with (artifact_dir / "delivery_candidates.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "bytes", "sha256", "sensitivity"])
        writer.writerows(rows)
    (artifact_dir / "delivery_candidates_total_bytes.txt").write_text(
        f"{grading['candidate_total_bytes']}\n", encoding="utf-8"
    )


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    grading = r4.finalize_artifacts(artifact_dir)
    parent_grade = str(grading["server_grade"])
    grade = GRADE_MAP.get(parent_grade, parent_grade)
    grading.update(
        {
            "server_grade": grade,
            "parent_r4_server_grade_predicate": parent_grade,
            "task_id": TASK_ID,
            "execution_lineage": "P6.3B-R4-R1",
            "root_squash_portability_repair": (
                "cp_-a_--no-preserve=ownership"
            ),
        }
    )

    summary_path = artifact_dir / "result_summary.md"
    summary = summary_path.read_text(encoding="utf-8")
    summary = summary.replace("P6.3B-R4 ", "P6.3B-R4-R1 ", 1)
    summary = summary.replace(
        "p6_3b_r4_deepseek_v4_flash_w8a8_mtp_explicit_"
        "prefix_cache_matched_ab_2026_0716",
        TASK_ID,
    )
    summary = summary.replace(
        f"- server_grade: {parent_grade}", f"- server_grade: {grade}"
    )
    summary_path.write_text(summary, encoding="utf-8")

    environment_path = artifact_dir / "environment_and_hashes.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    environment.update(
        {
            "task_id": TASK_ID,
            "execution_lineage": "P6.3B-R4-R1",
            "overlay_copy_preserves_ownership": False,
        }
    )
    _write_json(environment_path, environment)

    first_failure_path = artifact_dir / "first_failure_excerpt.txt"
    first_failure = first_failure_path.read_text(encoding="utf-8")
    first_failure_path.write_text(
        first_failure.replace(parent_grade, grade), encoding="utf-8"
    )
    (artifact_dir / "server_grade.txt").write_text(
        grade + "\n", encoding="utf-8"
    )
    _refresh_delivery_manifest(artifact_dir, grading)
    return grading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the DeepSeek P6.3B-R4-R1 NFS-portable explicit Prefix "
            "Cache control matched A/B."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    run_mode = subparsers.add_parser("run-mode")
    run_mode.add_argument("--artifact-dir", type=Path, required=True)
    run_mode.add_argument("--base-url", required=True)
    run_mode.add_argument("--server-pid", type=int, required=True)
    run_mode.add_argument("--mode", choices=r4.MODES, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        r4.prepare_r4_artifacts(
            args.source_payload, args.artifact_dir, args.model_name
        )
        return 0
    if args.command == "run-mode":
        return r4.execute_mode(
            args.artifact_dir,
            args.base_url,
            args.server_pid,
            args.mode,
            positive_hit_required_group_ids=r4.POSITIVE_HIT_GROUPS,
        )
    grading = finalize_artifacts(args.artifact_dir)
    return 0 if grading["server_grade"] == CANDIDATE_GREEN else 2


if __name__ == "__main__":
    raise SystemExit(main())
