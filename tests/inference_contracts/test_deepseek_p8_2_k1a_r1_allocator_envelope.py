from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_geometry(root: Path, rank: int, *, bytes_per_block: int) -> None:
    value = {
        "schema_version": "p8_2_k1a_r1_geometry_v1",
        "rank": rank,
        "world_size": 8,
        "block_size_tokens": 128,
        "required_restore_tokens": 16384,
        "num_npu_blocks": 1056,
        "unique_tensor_count": 2,
        "per_tensor_bytes_per_block": [
            {"name": "layer.0.k", "bytes_per_block": bytes_per_block // 2},
            {"name": "layer.0.v", "bytes_per_block": bytes_per_block // 2},
        ],
        "total_bytes_per_block": bytes_per_block,
    }
    (root / f"geometry.rank.{rank}.json").write_text(
        json.dumps(value), encoding="utf-8"
    )


def test_geometry_summary_requires_eight_equal_rank_records(tmp_path: Path) -> None:
    from tools.inference_contracts.p8_2_k1a_r1_allocator import (
        summarize_geometry_directory,
    )

    for rank in range(8):
        _write_geometry(tmp_path, rank, bytes_per_block=2 * 1024 * 1024)

    summary = summarize_geometry_directory(tmp_path)

    assert summary["geometry_gate_ok"] is True
    assert summary["rank_count"] == 8
    assert summary["required_cpu_blocks"] == 128
    assert summary["required_capacity_bytes_per_rank"] == 256 * 1024 * 1024
    assert summary["required_capacity_bytes_total"] == 2 * 1024 * 1024 * 1024
    assert summary["formal_lifecycle_authorized"] is False


def test_allocator_envelope_blocks_when_required_wave_fails() -> None:
    from tools.inference_contracts.p8_2_k1a_r1_allocator import assess_allocator_envelope

    geometry = {
        "geometry_gate_ok": True,
        "required_cpu_blocks": 128,
        "total_bytes_per_block": 2 * 1024 * 1024,
        "required_capacity_bytes_per_rank": 256 * 1024 * 1024,
    }
    waves = [
        {"cpu_blocks": 32, "rank_success_count": 8, "cleanup_ok": True},
        {"cpu_blocks": 64, "rank_success_count": 8, "cleanup_ok": True},
        {"cpu_blocks": 96, "rank_success_count": 8, "cleanup_ok": True},
        {"cpu_blocks": 128, "rank_success_count": 4, "cleanup_ok": True},
    ]

    result = assess_allocator_envelope(geometry, waves)

    assert result["acl_pinned_host_allocator_gate_ok"] is False
    assert result["highest_eight_rank_clean_blocks"] == 96
    assert result["candidate_cpu_bytes_per_rank"] is None
    assert result["formal_lifecycle_allowed"] is False
    assert result["grade"] == "blocked_p8_2_k1a_r1_pinned_capacity_below_restore_requirement"


def test_geometry_observer_builds_exact_block_budget_without_allocating() -> None:
    from tools.inference_contracts.p8_2_k1a_r1_geometry_observer import (
        build_geometry_record,
    )

    record = build_geometry_record(
        rank=3,
        world_size=8,
        num_npu_blocks=1056,
        descriptors=[("layer.0.k", 1048576), ("layer.0.v", 1048576)],
    )

    assert record["rank"] == 3
    assert record["total_bytes_per_block"] == 2097152
    assert record["required_cpu_blocks"] == 128
    assert record["required_capacity_bytes_per_rank"] == 268435456
    assert record["allocation_attempted"] is False


def test_allocator_probe_plan_is_bounded_shaped_and_stops_at_requirement() -> None:
    from tools.inference_contracts.probe_deepseek_p8_2_k1a_r1_pinned_allocator import (
        build_wave_plan,
    )

    geometry = {
        "required_cpu_blocks": 128,
        "total_bytes_per_block": 2 * 1024 * 1024,
        "required_capacity_bytes_per_rank": 256 * 1024 * 1024,
    }

    plan = build_wave_plan(geometry)

    assert [row["cpu_blocks"] for row in plan] == [32, 64, 96, 128]
    assert plan[-1]["bytes_per_rank"] == 256 * 1024 * 1024
    assert plan[-1]["is_required_restore_wave"] is True
    assert all(row["world_size"] == 8 for row in plan)
    assert all(row["allocation_shape"] == "per_tensor_bytes_per_block_x_cpu_blocks" for row in plan)


def test_geometry_summary_cli_writes_bounded_json(tmp_path: Path) -> None:
    from tools.inference_contracts.p8_2_k1a_r1_allocator import main

    geometry = tmp_path / "geometry"
    geometry.mkdir()
    for rank in range(8):
        _write_geometry(geometry, rank, bytes_per_block=2 * 1024 * 1024)
    output = tmp_path / "summary.json"

    assert main(["summarize-geometry", "--geometry-dir", str(geometry), "--output", str(output)]) == 0
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["geometry_gate_ok"] is True
    assert value["formal_lifecycle_authorized"] is False


def test_k1a_r1_contract_stays_red_while_r3_has_new_formal_authorization() -> None:
    audit = yaml.safe_load(
        (
            REPO_ROOT
            / "benchmarks/deepseek_v4_flash/p8_2_k1a_r1_allocator_feasibility_audit.yaml"
        ).read_text(encoding="utf-8")
    )
    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(encoding="utf-8")

    assert audit["stage"] == "P8.2-K1A-R1"
    assert audit["parent"]["grade"] == "red_p8_2_k1a_simple_cpu_offload_no_success"
    assert audit["parent"]["proc_memavailable_gate_ok"] is True
    assert audit["parent"]["acl_pinned_host_allocator_gate_ok"] is False
    assert audit["geometry_probe"]["model_request_count_exact"] == 0
    assert audit["geometry_probe"]["cpu_offload_allocation_attempted"] is False
    assert audit["allocator_envelope"]["wave_cpu_blocks"] == [32, 64, 96, 128]
    assert audit["decision"]["formal_lifecycle_authorized"] is False
    assert audit["decision"]["k2_authorized"] is False
    assert "p8_2_k1a_r5_l1_lazy_h2d_trigger_lifecycle_2026_0721" in handoff
    assert "ready_p8_2_k1a_r2_allocator_capacity" in handoff
    assert "formal_model_lifecycle_count_max: 1" in handoff
    assert "model_request_count_max: 8" in handoff
    assert "capacity_search_authorized: false" in handoff
    assert "result_transfer_authorized: true" in handoff
    assert "next_task_authorized: false" in handoff
    assert "cpu_bytes_to_use_per_rank=430604288" in handoff


def test_pinned_probe_direct_file_cli_bootstraps_repo_root() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "tools/inference_contracts/probe_deepseek_p8_2_k1a_r1_pinned_allocator.py"
            ),
            "--help",
        ],
        cwd=Path("/tmp"),
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "{envelope,worker}" in completed.stdout
