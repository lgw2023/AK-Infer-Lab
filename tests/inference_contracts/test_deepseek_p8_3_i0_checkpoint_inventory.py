from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest
from safetensors.numpy import save_file
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_fixture(root: Path) -> None:
    tensors = {
        "model.embed_tokens.weight": np.zeros((4, 2), dtype=np.float16),
        "model.layers.0.self_attn.q_proj.weight": np.zeros((2, 2), dtype=np.float16),
        "model.layers.1.mlp.experts.0.gate_proj.weight": np.zeros((2, 2), dtype=np.int8),
        "model.layers.1.mlp.experts.0.gate_proj.weight_scale_inv": np.zeros((1,), dtype=np.float32),
        "model.layers.1.mlp.experts.1.down_proj.weight": np.zeros((2, 2), dtype=np.int8),
        "model.layers.1.mlp.shared_experts.down_proj.weight": np.zeros((2, 2), dtype=np.int8),
        "model.layers.2.mlp.gate_proj.weight": np.zeros((2, 2), dtype=np.float16),
        "model.norm.weight": np.zeros((2,), dtype=np.float16),
        "lm_head.weight": np.zeros((4, 2), dtype=np.float16),
        "model.unknown_tensor": np.zeros((3,), dtype=np.float32),
    }
    shard_a = {name: value for index, (name, value) in enumerate(tensors.items()) if index % 2 == 0}
    shard_b = {name: value for index, (name, value) in enumerate(tensors.items()) if index % 2 == 1}
    save_file(shard_a, root / "model-00001-of-00002.safetensors")
    save_file(shard_b, root / "model-00002-of-00002.safetensors")
    weight_map = {
        name: "model-00001-of-00002.safetensors" if index % 2 == 0 else "model-00002-of-00002.safetensors"
        for index, name in enumerate(tensors)
    }
    (root / "model.safetensors.index.json").write_text(
        json.dumps({"metadata": {}, "weight_map": weight_map}, sort_keys=True),
        encoding="utf-8",
    )


def test_checkpoint_inventory_preserves_unknowns_and_planning_only_owners(tmp_path: Path) -> None:
    from tools.inference_contracts.inventory_deepseek_p8_3_i0_checkpoint import (
        build_checkpoint_inventory,
    )

    model = tmp_path / "model"
    output = tmp_path / "output"
    model.mkdir()
    _build_fixture(model)

    summary = build_checkpoint_inventory(model, output, tp_size=4, shard_hash_mode="full")
    table = pq.read_table(output / "expert_weight_inventory.parquet")
    rows = table.to_pylist()
    budget = yaml.safe_load((output / "tp4_rank_weight_budget.yaml").read_text())

    assert summary["indexed_tensor_count"] == 10
    assert summary["missing_index_tensor_count"] == 0
    assert summary["duplicate_header_tensor_count"] == 0
    assert summary["unclassified_tensor_count"] == 1
    assert {row["tensor_role"] for row in rows} >= {
        "routed_expert",
        "shared_expert",
        "attention",
        "embedding",
        "unclassified",
    }
    routed = [row for row in rows if row["tensor_role"] == "routed_expert"]
    assert {row["expert_id"] for row in routed} == {0, 1}
    assert {row["candidate_tp4_owner"] for row in routed} == {"rank_0", "rank_1"}
    assert all(row["candidate_owner_status"] == "planning_candidate_not_runtime_validated" for row in rows)
    assert all(row["materialized_bytes"] is None for row in rows)
    assert all(row["materialized_bytes_reason"] == "not_measured_from_runtime" for row in rows)
    assert budget["ownership_status"] == "planning_candidate_not_runtime_validated"
    assert len(budget["ranks"]) == 4
    assert summary["formal_tp4_runtime_claim_allowed"] is False


def test_p8_3_i0_repo_contract_freezes_checkpoint_only_claim_boundary() -> None:
    contract = yaml.safe_load(
        (
            REPO_ROOT
            / "benchmarks/deepseek_v4_flash/p8_3_i0_checkpoint_inventory_contract.yaml"
        ).read_text(encoding="utf-8")
    )

    assert contract["stage"] == "P8.3-I0"
    assert contract["execution"]["npu_required"] is False
    assert contract["execution"]["model_requests_allowed"] is False
    assert contract["checkpoint"]["shard_hash_mode"] == "full_sha256"
    assert contract["checkpoint"]["index_resolution_policy"] == (
        "explicit_index_file_or_unique_safetensors_index_discovery"
    )
    assert contract["checkpoint"]["temporary_symlink_required"] is False
    assert contract["outputs"]["inventory"] == "expert_weight_inventory.parquet"
    assert contract["outputs"]["tp4_budget"] == "tp4_rank_weight_budget.yaml"
    assert contract["ownership"]["tp8_owner_from_header"] is False
    assert contract["ownership"]["tp4_status"] == "planning_candidate_not_runtime_validated"
    assert contract["acceptance"]["unclassified_bytes_must_be_explicit"] is True
    assert contract["acceptance"]["materialized_bytes_may_use_checkpoint_bytes"] is False
    assert contract["claims"]["tp4_runtime_validated"] is False


def test_checkpoint_inventory_is_byte_deterministic_for_same_checkpoint(tmp_path: Path) -> None:
    from tools.inference_contracts.inventory_deepseek_p8_3_i0_checkpoint import (
        build_checkpoint_inventory,
    )

    model = tmp_path / "model"
    model.mkdir()
    _build_fixture(model)
    first = tmp_path / "first"
    second = tmp_path / "second"

    build_checkpoint_inventory(model, first, tp_size=4, shard_hash_mode="full")
    build_checkpoint_inventory(model, second, tp_size=4, shard_hash_mode="full")

    for name in (
        "expert_weight_inventory.parquet",
        "tp4_rank_weight_budget.yaml",
        "inventory_summary.json",
        "inventory_manifest.json",
    ):
        assert _sha256(first / name) == _sha256(second / name)


def test_checkpoint_inventory_discovers_unique_quant_index_without_symlink(
    tmp_path: Path,
) -> None:
    from tools.inference_contracts.inventory_deepseek_p8_3_i0_checkpoint import (
        build_checkpoint_inventory,
    )

    model = tmp_path / "model"
    output = tmp_path / "output"
    model.mkdir()
    _build_fixture(model)
    (model / "model.safetensors.index.json").rename(
        model / "quant_model_weights.safetensors.index.json"
    )

    summary = build_checkpoint_inventory(
        model, output, tp_size=4, shard_hash_mode="full"
    )

    assert summary["index_basename"] == "quant_model_weights.safetensors.index.json"
    assert summary["index_resolution"] == "unique_safetensors_index_discovery"


def test_unclassified_taxonomy_accounts_existing_inventory_without_reclassification(
    tmp_path: Path,
) -> None:
    from tools.inference_contracts.analyze_deepseek_p8_3_i0_unclassified import (
        build_unclassified_taxonomy,
    )
    from tools.inference_contracts.inventory_deepseek_p8_3_i0_checkpoint import (
        build_checkpoint_inventory,
    )

    model = tmp_path / "model"
    inventory = tmp_path / "inventory"
    output = tmp_path / "unclassified_taxonomy.json"
    model.mkdir()
    _build_fixture(model)
    build_checkpoint_inventory(model, inventory, tp_size=4, shard_hash_mode="full")

    taxonomy = build_unclassified_taxonomy(
        inventory / "expert_weight_inventory.parquet",
        inventory / "inventory_summary.json",
        output,
        max_groups=128,
        max_output_bytes=71680,
    )

    assert taxonomy["unclassified_tensor_count"] == 1
    assert taxonomy["taxonomy_group_count"] == 1
    assert taxonomy["reported_group_count"] == 1
    assert taxonomy["taxonomy_complete"] is True
    assert taxonomy["accounted_checkpoint_bytes_exact"] is True
    assert taxonomy["groups"][0]["family_signature"] == "model.unknown_tensor"
    assert taxonomy["formal_reclassification_allowed"] is False
    assert taxonomy["formal_tp4_runtime_claim_allowed"] is False
    assert output.stat().st_size <= 71680


def test_i0_r1_audit_accepts_inventory_but_keeps_tp4_budget_incomplete() -> None:
    audit = yaml.safe_load(
        (
            REPO_ROOT
            / "benchmarks/deepseek_v4_flash/p8_3_i0_r1_inventory_taxonomy_audit.yaml"
        ).read_text(encoding="utf-8")
    )

    assert audit["stage"] == "P8.3-I0-R1"
    assert audit["parent"]["grade"] == "green_p8_3_i0_checkpoint_inventory"
    assert audit["parent"]["index_basename"] == (
        "quant_model_weights.safetensors.index.json"
    )
    assert audit["parent"]["indexed_tensor_count"] == 103176
    assert audit["parent"]["index_header_exact"] is True
    assert audit["parent"]["unclassified_tensor_count"] == 1135
    assert audit["parent"]["unclassified_checkpoint_bytes"] == 12319364956
    assert audit["parent"]["budget_complete"] is False
    assert audit["r1"]["rerun_full_shard_hashes"] is False
    assert audit["r1"]["existing_parquet_read_only"] is True
    assert audit["r1"]["max_taxonomy_output_bytes"] == 65536
    assert audit["claims"]["formal_tp4_runtime_claim_allowed"] is False
    assert audit["next"]["p8_3_i1_authorized"] is False


def test_explicit_index_rejects_symlink_workaround(tmp_path: Path) -> None:
    from tools.inference_contracts.inventory_deepseek_p8_3_i0_checkpoint import (
        resolve_safetensors_index,
    )

    model = tmp_path / "model"
    model.mkdir()
    _build_fixture(model)
    actual = model / "quant_model_weights.safetensors.index.json"
    (model / "model.safetensors.index.json").rename(actual)
    alias = model / "model.safetensors.index.json"
    alias.symlink_to(actual.name)

    with pytest.raises(ValueError, match="symlink"):
        resolve_safetensors_index(model, alias)
