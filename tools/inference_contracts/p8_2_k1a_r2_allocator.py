from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.p8_2_k1a_r2_geometry_observer import (
    RENDEZVOUS_SCHEMA_VERSION,
    _validate_complete_records,
)


def summarize_geometry_directory(root: Path) -> dict[str, Any]:
    root = Path(root)
    paths = sorted(root.glob("geometry.rank.*.json"))
    records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    run_ids = {str(row.get("probe_run_id", "")) for row in records}
    if len(run_ids) != 1 or "" in run_ids:
        raise ValueError(f"geometry probe run identity mismatch: {sorted(run_ids)}")
    run_id = next(iter(run_ids))
    expected_marker = _validate_complete_records(records, run_id)
    marker_path = root / "geometry.rendezvous.complete.json"
    if not marker_path.is_file():
        raise ValueError("geometry rendezvous marker is missing")
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if marker.get("schema_version") != RENDEZVOUS_SCHEMA_VERSION:
        raise ValueError("geometry rendezvous schema mismatch")
    if marker != expected_marker:
        raise ValueError("geometry rendezvous marker does not match rank records")

    first = records[0]
    block_size = int(first["block_size_tokens"])
    restore_tokens = int(first["required_restore_tokens"])
    if restore_tokens % block_size:
        raise ValueError("restore token target is not block aligned")
    required_blocks = restore_tokens // block_size
    bytes_per_block = int(first["total_bytes_per_block"])
    required_per_rank = required_blocks * bytes_per_block
    return {
        "schema_version": "p8_2_k1a_r2_geometry_summary_v1",
        "stage": "P8.2-K1A-R2",
        "probe_run_id": run_id,
        "geometry_gate_ok": True,
        "rendezvous_gate_ok": True,
        "rank_count": len(records),
        "rank_coverage": marker["rank_coverage"],
        "block_size_tokens": block_size,
        "required_restore_tokens": restore_tokens,
        "required_cpu_blocks": required_blocks,
        "total_bytes_per_block": bytes_per_block,
        "required_capacity_bytes_per_rank": required_per_rank,
        "required_capacity_bytes_total": required_per_rank * 8,
        "unique_tensor_count": int(first["unique_tensor_count"]),
        "per_tensor_bytes_per_block": first["per_tensor_bytes_per_block"],
        "allocation_attempted": False,
        "formal_lifecycle_authorized": False,
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
