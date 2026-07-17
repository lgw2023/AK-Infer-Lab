from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


GEOMETRY_SCHEMA_VERSION = "p8_2_k1a_r1_geometry_v1"


def summarize_geometry_directory(root: Path) -> dict[str, Any]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("geometry.rank.*.json"))
    ]
    if len(records) != 8:
        raise ValueError(f"expected 8 geometry records, got {len(records)}")
    if any(row.get("schema_version") != GEOMETRY_SCHEMA_VERSION for row in records):
        raise ValueError("geometry schema mismatch")
    ranks = [int(row["rank"]) for row in records]
    if sorted(ranks) != list(range(8)) or len(set(ranks)) != 8:
        raise ValueError(f"rank coverage mismatch: {ranks}")
    if any(int(row["world_size"]) != 8 for row in records):
        raise ValueError("world_size mismatch")

    parity_fields = (
        "block_size_tokens",
        "required_restore_tokens",
        "total_bytes_per_block",
        "unique_tensor_count",
    )
    for field in parity_fields:
        values = {int(row[field]) for row in records}
        if len(values) != 1:
            raise ValueError(f"rank geometry drift for {field}: {sorted(values)}")
    descriptor_sets = {
        json.dumps(row["per_tensor_bytes_per_block"], sort_keys=True)
        for row in records
    }
    if len(descriptor_sets) != 1:
        raise ValueError("rank geometry drift for per-tensor bytes")

    block_size = int(records[0]["block_size_tokens"])
    restore_tokens = int(records[0]["required_restore_tokens"])
    if restore_tokens % block_size:
        raise ValueError("restore token target is not block aligned")
    required_blocks = restore_tokens // block_size
    bytes_per_block = int(records[0]["total_bytes_per_block"])
    required_per_rank = required_blocks * bytes_per_block
    return {
        "schema_version": "p8_2_k1a_r1_geometry_summary_v1",
        "geometry_gate_ok": True,
        "rank_count": len(records),
        "rank_coverage": sorted(ranks),
        "block_size_tokens": block_size,
        "required_restore_tokens": restore_tokens,
        "required_cpu_blocks": required_blocks,
        "total_bytes_per_block": bytes_per_block,
        "required_capacity_bytes_per_rank": required_per_rank,
        "required_capacity_bytes_total": required_per_rank * 8,
        "unique_tensor_count": int(records[0]["unique_tensor_count"]),
        "per_tensor_bytes_per_block": records[0]["per_tensor_bytes_per_block"],
        "formal_lifecycle_authorized": False,
    }


def assess_allocator_envelope(
    geometry: dict[str, Any], waves: list[dict[str, Any]]
) -> dict[str, Any]:
    if geometry.get("geometry_gate_ok") is not True:
        raise ValueError("geometry gate is not green")
    if not waves:
        raise ValueError("allocator envelope is empty")
    block_counts = [int(row["cpu_blocks"]) for row in waves]
    if block_counts != sorted(set(block_counts)):
        raise ValueError("allocator waves must be unique and ascending")

    clean_passes = [
        int(row["cpu_blocks"])
        for row in waves
        if int(row.get("rank_success_count", 0)) == 8
        and row.get("cleanup_ok") is True
    ]
    highest_clean = max(clean_passes, default=0)
    required_blocks = int(geometry["required_cpu_blocks"])
    required_rows = [
        row for row in waves if int(row["cpu_blocks"]) == required_blocks
    ]
    if len(required_rows) != 1:
        raise ValueError("allocator envelope must include the required-block wave")
    required = required_rows[0]
    gate_ok = (
        int(required.get("rank_success_count", 0)) == 8
        and required.get("cleanup_ok") is True
    )
    candidate = (
        int(geometry["required_capacity_bytes_per_rank"]) if gate_ok else None
    )
    grade = (
        "candidate_ready_p8_2_k1a_r1_allocator_capacity"
        if gate_ok
        else "blocked_p8_2_k1a_r1_pinned_capacity_below_restore_requirement"
    )
    return {
        "schema_version": "p8_2_k1a_r1_allocator_envelope_v1",
        "acl_pinned_host_allocator_gate_ok": gate_ok,
        "required_cpu_blocks": required_blocks,
        "highest_eight_rank_clean_blocks": highest_clean,
        "candidate_cpu_bytes_per_rank": candidate,
        "candidate_cpu_bytes_total": candidate * 8 if candidate is not None else None,
        "capacity_candidate_ready": gate_ok,
        "formal_lifecycle_allowed": False,
        "formal_lifecycle_requires_new_handoff": True,
        "grade": grade,
        "waves": waves,
    }


def _summarize_geometry_command(args: argparse.Namespace) -> int:
    value = summarize_geometry_directory(Path(args.geometry_dir))
    Path(args.output).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    summarize = sub.add_parser("summarize-geometry")
    summarize.add_argument("--geometry-dir", required=True)
    summarize.add_argument("--output", required=True)
    summarize.set_defaults(func=_summarize_geometry_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
