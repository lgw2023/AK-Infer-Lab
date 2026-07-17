from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml


LAYER_RE = re.compile(r"(?:^|\.)layers\.(\d+)(?:\.|$)")
EXPERT_RE = re.compile(r"(?:^|\.)experts\.(\d+)(?:\.|$)")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_safetensors_header(path: Path) -> tuple[dict[str, Any], int]:
    with path.open("rb") as handle:
        raw = handle.read(8)
        if len(raw) != 8:
            raise ValueError(f"truncated safetensors header length: {path}")
        header_size = int.from_bytes(raw, byteorder="little", signed=False)
        header_raw = handle.read(header_size)
    if len(header_raw) != header_size:
        raise ValueError(f"truncated safetensors JSON header: {path}")
    value = json.loads(header_raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid safetensors header object: {path}")
    value.pop("__metadata__", None)
    return value, header_size


def _classify(name: str) -> tuple[str, int | None, int | None]:
    layer_match = LAYER_RE.search(name)
    expert_match = EXPERT_RE.search(name)
    layer_id = int(layer_match.group(1)) if layer_match else None
    expert_id = int(expert_match.group(1)) if expert_match else None
    lower = name.lower()
    if expert_id is not None:
        role = "routed_expert"
    elif "shared_expert" in lower:
        role = "shared_expert"
    elif "mtp" in lower or "draft" in lower:
        role = "mtp_draft"
    elif "embed_tokens" in lower or "embedding" in lower:
        role = "embedding"
    elif lower.startswith("lm_head") or ".lm_head" in lower:
        role = "lm_head"
    elif "self_attn" in lower or ".attention." in lower:
        role = "attention"
    elif ".mlp." in lower:
        role = "dense_mlp"
    elif "norm" in lower:
        role = "norm"
    else:
        role = "unclassified"
    return role, layer_id, expert_id


def _is_quantization_metadata(name: str) -> bool:
    lower = name.lower()
    return any(
        marker in lower
        for marker in ("scale_inv", "inv_scale", "weight_scale", "zero_point")
    )


def _inventory_schema() -> pa.Schema:
    return pa.schema(
        [
            ("tensor_name", pa.string()),
            ("tensor_role", pa.string()),
            ("layer_id", pa.int32()),
            ("expert_id", pa.int32()),
            ("source_shard", pa.string()),
            ("source_shard_bytes", pa.int64()),
            ("source_shard_sha256", pa.string()),
            ("checkpoint_bytes", pa.int64()),
            ("dtype", pa.string()),
            ("shape", pa.list_(pa.int64())),
            ("layout", pa.string()),
            ("is_quantization_metadata", pa.bool_()),
            ("tp8_owner", pa.string()),
            ("tp8_owner_reason", pa.string()),
            ("candidate_tp4_owner", pa.string()),
            ("candidate_owner_status", pa.string()),
            ("materialized_bytes", pa.int64()),
            ("materialized_bytes_reason", pa.string()),
            ("provenance", pa.string()),
        ]
    )


def resolve_safetensors_index(
    model_dir: Path, index_file: Path | None = None
) -> tuple[Path, str]:
    model_dir = Path(model_dir)
    if index_file is not None:
        index_path = Path(index_file)
        if not index_path.is_absolute():
            index_path = model_dir / index_path
        if not index_path.is_file():
            raise ValueError(f"explicit safetensors index is not a file: {index_path}")
        if index_path.is_symlink():
            raise ValueError(f"safetensors index symlink is not accepted: {index_path}")
        return index_path, "explicit_index_file"
    candidates = sorted(model_dir.glob("*.safetensors.index.json"))
    if len(candidates) != 1:
        names = [path.name for path in candidates]
        raise ValueError(
            "expected exactly one safetensors index or explicit --index-file, "
            f"got {len(candidates)}: {names}"
        )
    if candidates[0].is_symlink():
        raise ValueError(f"safetensors index symlink is not accepted: {candidates[0]}")
    return candidates[0], "unique_safetensors_index_discovery"


def build_checkpoint_inventory(
    model_dir: Path,
    output_dir: Path,
    *,
    tp_size: int = 4,
    shard_hash_mode: str = "full",
    index_file: Path | None = None,
) -> dict[str, Any]:
    model_dir = Path(model_dir)
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    if tp_size != 4:
        raise ValueError("P8.3-I0 freezes candidate TP size to 4")
    if shard_hash_mode != "full":
        raise ValueError("formal P8.3-I0 requires full shard SHA-256")
    index_path, index_resolution = resolve_safetensors_index(model_dir, index_file)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, dict) or not weight_map:
        raise ValueError("model.safetensors.index.json has no weight_map")

    shard_names = sorted(set(str(value) for value in weight_map.values()))
    shard_meta: dict[str, dict[str, Any]] = {}
    header_owner: dict[str, str] = {}
    duplicate_names: set[str] = set()
    header_tensors: dict[str, dict[str, Any]] = {}
    for shard_name in shard_names:
        shard_path = model_dir / shard_name
        header, header_size = _read_safetensors_header(shard_path)
        shard_meta[shard_name] = {
            "bytes": shard_path.stat().st_size,
            "sha256": _sha256(shard_path),
            "header_bytes": header_size,
            "tensor_count": len(header),
        }
        for tensor_name, tensor_meta in header.items():
            if tensor_name in header_owner:
                duplicate_names.add(tensor_name)
            header_owner[tensor_name] = shard_name
            header_tensors[tensor_name] = tensor_meta

    indexed_names = set(str(name) for name in weight_map)
    header_names = set(header_tensors)
    missing = sorted(indexed_names - header_names)
    unindexed = sorted(header_names - indexed_names)
    wrong_shard = sorted(
        name
        for name in indexed_names & header_names
        if str(weight_map[name]) != header_owner[name]
    )
    if missing or duplicate_names or unindexed or wrong_shard:
        raise ValueError(
            "checkpoint index/header mismatch: "
            f"missing={len(missing)} duplicate={len(duplicate_names)} "
            f"unindexed={len(unindexed)} wrong_shard={len(wrong_shard)}"
        )

    rows: list[dict[str, Any]] = []
    for tensor_name in sorted(indexed_names):
        shard_name = str(weight_map[tensor_name])
        meta = header_tensors[tensor_name]
        offsets = meta.get("data_offsets")
        if not isinstance(offsets, list) or len(offsets) != 2:
            raise ValueError(f"invalid data_offsets for {tensor_name}")
        checkpoint_bytes = int(offsets[1]) - int(offsets[0])
        shape = [int(value) for value in meta.get("shape", [])]
        if checkpoint_bytes < 0 or any(value < 0 for value in shape):
            raise ValueError(f"invalid tensor geometry for {tensor_name}")
        role, layer_id, expert_id = _classify(tensor_name)
        if role == "routed_expert":
            assert expert_id is not None
            candidate_owner = f"rank_{expert_id % tp_size}"
        elif role == "unclassified":
            candidate_owner = "unresolved_unclassified"
        else:
            candidate_owner = "replicated_all_ranks"
        rows.append(
            {
                "tensor_name": tensor_name,
                "tensor_role": role,
                "layer_id": layer_id,
                "expert_id": expert_id,
                "source_shard": shard_name,
                "source_shard_bytes": int(shard_meta[shard_name]["bytes"]),
                "source_shard_sha256": str(shard_meta[shard_name]["sha256"]),
                "checkpoint_bytes": checkpoint_bytes,
                "dtype": str(meta.get("dtype")),
                "shape": shape,
                "layout": "safetensors_contiguous",
                "is_quantization_metadata": _is_quantization_metadata(tensor_name),
                "tp8_owner": None,
                "tp8_owner_reason": "checkpoint_header_does_not_encode_runtime_ownership",
                "candidate_tp4_owner": candidate_owner,
                "candidate_owner_status": "planning_candidate_not_runtime_validated",
                "materialized_bytes": None,
                "materialized_bytes_reason": "not_measured_from_runtime",
                "provenance": "frozen_checkpoint_index_and_safetensors_header",
            }
        )

    output_dir.mkdir(parents=True)
    table = pa.Table.from_pylist(rows, schema=_inventory_schema())
    pq.write_table(
        table,
        output_dir / "expert_weight_inventory.parquet",
        compression="zstd",
        use_dictionary=False,
        write_statistics=True,
    )

    replicated = sum(
        row["checkpoint_bytes"]
        for row in rows
        if row["candidate_tp4_owner"] == "replicated_all_ranks"
    )
    unclassified_bytes = sum(
        row["checkpoint_bytes"]
        for row in rows
        if row["candidate_tp4_owner"] == "unresolved_unclassified"
    )
    rank_rows = []
    for rank in range(tp_size):
        routed = sum(
            row["checkpoint_bytes"]
            for row in rows
            if row["candidate_tp4_owner"] == f"rank_{rank}"
        )
        rank_rows.append(
            {
                "rank": rank,
                "replicated_checkpoint_bytes": replicated,
                "routed_expert_checkpoint_bytes": routed,
                "candidate_checkpoint_bytes": replicated + routed,
                "materialized_bytes": None,
                "materialized_bytes_reason": "not_measured_from_runtime",
            }
        )
    budget = {
        "schema_version": "p8_3_i0_tp4_rank_weight_budget_v1",
        "tp_size": tp_size,
        "ownership_status": "planning_candidate_not_runtime_validated",
        "budget_basis": "checkpoint_logical_bytes_not_runtime_materialized_bytes",
        "budget_complete": unclassified_bytes == 0,
        "unclassified_checkpoint_bytes_unassigned": unclassified_bytes,
        "ranks": rank_rows,
        "formal_tp4_runtime_claim_allowed": False,
    }
    (output_dir / "tp4_rank_weight_budget.yaml").write_text(
        yaml.safe_dump(budget, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    total_checkpoint_bytes = sum(row["checkpoint_bytes"] for row in rows)
    summary = {
        "schema_version": "p8_3_i0_checkpoint_inventory_summary_v1",
        "model_dir": str(model_dir),
        "index_path": str(index_path),
        "index_basename": index_path.name,
        "index_resolution": index_resolution,
        "index_sha256": _sha256(index_path),
        "shard_hash_mode": shard_hash_mode,
        "shard_count": len(shard_names),
        "indexed_tensor_count": len(indexed_names),
        "header_tensor_count": len(header_names),
        "missing_index_tensor_count": len(missing),
        "duplicate_header_tensor_count": len(duplicate_names),
        "unindexed_header_tensor_count": len(unindexed),
        "wrong_shard_tensor_count": len(wrong_shard),
        "unclassified_tensor_count": sum(row["tensor_role"] == "unclassified" for row in rows),
        "unclassified_checkpoint_bytes": unclassified_bytes,
        "checkpoint_logical_bytes": total_checkpoint_bytes,
        "materialized_bytes_complete": False,
        "materialized_bytes_reason": "not_measured_from_runtime",
        "candidate_tp4_ownership_status": "planning_candidate_not_runtime_validated",
        "formal_tp4_runtime_claim_allowed": False,
        "claim_boundary": "checkpoint_header_inventory_and_tp4_planning_budget_only",
        "shards": shard_meta,
    }
    (output_dir / "inventory_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_files = {}
    for name in (
        "expert_weight_inventory.parquet",
        "tp4_rank_weight_budget.yaml",
        "inventory_summary.json",
    ):
        path = output_dir / name
        manifest_files[name] = {"bytes": path.stat().st_size, "sha256": _sha256(path)}
    (output_dir / "inventory_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "p8_3_i0_inventory_manifest_v1",
                "files": manifest_files,
                "generated_content_retained": False,
                "token_ids_retained": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--index-file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tp-size", type=int, default=4)
    parser.add_argument("--shard-hash-mode", choices=("full",), default="full")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    build_checkpoint_inventory(
        args.model_dir,
        args.output_dir,
        tp_size=args.tp_size,
        shard_hash_mode=args.shard_hash_mode,
        index_file=args.index_file,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
