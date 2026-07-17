from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pyarrow.parquet as pq


DIGITS_RE = re.compile(r"\d+")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _family_signature(tensor_name: str) -> str:
    return DIGITS_RE.sub("{n}", tensor_name)


def _render_taxonomy(
    *,
    inventory_path: Path,
    summary_path: Path,
    groups: list[dict[str, Any]],
    reported_group_count: int,
    tensor_count: int,
    checkpoint_bytes: int,
) -> dict[str, Any]:
    reported = groups[:reported_group_count]
    omitted = groups[reported_group_count:]
    reported_tensor_count = sum(int(row["tensor_count"]) for row in reported)
    reported_bytes = sum(int(row["checkpoint_bytes"]) for row in reported)
    omitted_tensor_count = sum(int(row["tensor_count"]) for row in omitted)
    omitted_bytes = sum(int(row["checkpoint_bytes"]) for row in omitted)
    return {
        "schema_version": "p8_3_i0_r1_unclassified_taxonomy_v1",
        "source_inventory_basename": inventory_path.name,
        "source_inventory_bytes": inventory_path.stat().st_size,
        "source_inventory_sha256": _sha256(inventory_path),
        "source_inventory_summary_basename": summary_path.name,
        "source_inventory_summary_bytes": summary_path.stat().st_size,
        "source_inventory_summary_sha256": _sha256(summary_path),
        "normalization": "replace_decimal_runs_with_{n}_then_group_by_dtype_shape_and_quant_metadata",
        "unclassified_tensor_count": tensor_count,
        "unclassified_checkpoint_bytes": checkpoint_bytes,
        "taxonomy_group_count": len(groups),
        "reported_group_count": len(reported),
        "reported_tensor_count": reported_tensor_count,
        "reported_checkpoint_bytes": reported_bytes,
        "omitted_group_count": len(omitted),
        "omitted_tensor_count": omitted_tensor_count,
        "omitted_checkpoint_bytes": omitted_bytes,
        "taxonomy_complete": len(omitted) == 0,
        "accounted_tensor_count_exact": (
            reported_tensor_count + omitted_tensor_count == tensor_count
        ),
        "accounted_checkpoint_bytes_exact": (
            reported_bytes + omitted_bytes == checkpoint_bytes
        ),
        "groups": reported,
        "formal_reclassification_allowed": False,
        "formal_tp4_runtime_claim_allowed": False,
        "claim_boundary": "bounded_existing_parquet_unclassified_taxonomy_only",
        "generated_content_retained": False,
        "token_ids_retained": False,
    }


def build_unclassified_taxonomy(
    inventory_path: Path,
    summary_path: Path,
    output_path: Path,
    *,
    max_groups: int,
    max_output_bytes: int,
) -> dict[str, Any]:
    inventory_path = Path(inventory_path)
    summary_path = Path(summary_path)
    output_path = Path(output_path)
    if output_path.exists():
        raise ValueError(f"output path already exists: {output_path}")
    if max_groups <= 0 or max_output_bytes <= 0:
        raise ValueError("taxonomy bounds must be positive")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    table = pq.read_table(
        inventory_path,
        columns=[
            "tensor_name",
            "tensor_role",
            "checkpoint_bytes",
            "dtype",
            "shape",
            "is_quantization_metadata",
        ],
    )
    rows = [row for row in table.to_pylist() if row["tensor_role"] == "unclassified"]
    tensor_count = len(rows)
    checkpoint_bytes = sum(int(row["checkpoint_bytes"]) for row in rows)
    if tensor_count != int(summary["unclassified_tensor_count"]):
        raise ValueError("unclassified tensor count drift from inventory summary")
    if checkpoint_bytes != int(summary["unclassified_checkpoint_bytes"]):
        raise ValueError("unclassified byte count drift from inventory summary")

    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        name = str(row["tensor_name"])
        key = (
            _family_signature(name),
            str(row["dtype"]),
            tuple(int(value) for value in row["shape"]),
            bool(row["is_quantization_metadata"]),
        )
        group = grouped.setdefault(
            key,
            {
                "family_signature": key[0],
                "dtype": key[1],
                "shape": list(key[2]),
                "is_quantization_metadata": key[3],
                "tensor_count": 0,
                "checkpoint_bytes": 0,
                "example_tensor_name": name,
            },
        )
        group["tensor_count"] += 1
        group["checkpoint_bytes"] += int(row["checkpoint_bytes"])
        group["example_tensor_name"] = min(group["example_tensor_name"], name)
    groups = sorted(
        grouped.values(),
        key=lambda row: (
            -int(row["checkpoint_bytes"]),
            -int(row["tensor_count"]),
            str(row["family_signature"]),
            str(row["dtype"]),
            tuple(row["shape"]),
        ),
    )

    reported_group_count = min(max_groups, len(groups))
    while True:
        value = _render_taxonomy(
            inventory_path=inventory_path,
            summary_path=summary_path,
            groups=groups,
            reported_group_count=reported_group_count,
            tensor_count=tensor_count,
            checkpoint_bytes=checkpoint_bytes,
        )
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if len(payload) <= max_output_bytes:
            break
        if reported_group_count == 0:
            raise ValueError("taxonomy metadata exceeds max_output_bytes without groups")
        reported_group_count -= 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--inventory-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-groups", type=int, default=256)
    parser.add_argument("--max-output-bytes", type=int, default=65536)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    build_unclassified_taxonomy(
        args.inventory,
        args.inventory_summary,
        args.output,
        max_groups=args.max_groups,
        max_output_bytes=args.max_output_bytes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
