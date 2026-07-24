from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _record(rank: int, run_id: str) -> dict[str, object]:
    return {
        "schema_version": "p8_2_k1a_r2_geometry_v1",
        "probe_run_id": run_id,
        "rank": rank,
        "world_size": 8,
        "block_size_tokens": 128,
        "required_restore_tokens": 16384,
        "required_cpu_blocks": 128,
        "num_npu_blocks": 5048,
        "unique_tensor_count": 2,
        "per_tensor_bytes_per_block": [
            {"name": "layer.0.k", "bytes_per_block": 1024},
            {"name": "layer.0.v", "bytes_per_block": 1024},
        ],
        "total_bytes_per_block": 2048,
        "required_capacity_bytes_per_rank": 262144,
        "allocation_attempted": False,
    }


def test_geometry_publish_waits_for_atomic_same_run_eight_rank_rendezvous(
    tmp_path: Path,
) -> None:
    from tools.inference_contracts.p8_2_k1a_r2_geometry_observer import (
        publish_and_wait_for_geometry_rendezvous,
    )

    run_id = "probe-run-001"
    completed: list[int] = []
    errors: list[BaseException] = []

    def worker(rank: int) -> None:
        try:
            publish_and_wait_for_geometry_rendezvous(
                tmp_path,
                _record(rank, run_id),
                timeout_seconds=2.0,
                poll_interval_seconds=0.01,
            )
            completed.append(rank)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(rank,)) for rank in range(7)]
    for thread in threads:
        thread.start()
    time.sleep(0.1)

    assert completed == []
    assert not (tmp_path / "geometry.rendezvous.complete.json").exists()
    assert len(list(tmp_path.glob("geometry.rank.*.json"))) == 7
    assert list(tmp_path.glob("*.tmp.*")) == []

    last = threading.Thread(target=worker, args=(7,))
    last.start()
    for thread in [*threads, last]:
        thread.join(timeout=3)

    assert errors == []
    assert sorted(completed) == list(range(8))
    marker = json.loads(
        (tmp_path / "geometry.rendezvous.complete.json").read_text(encoding="utf-8")
    )
    assert marker["probe_run_id"] == run_id
    assert marker["rank_coverage"] == list(range(8))
    assert marker["geometry_parity_exact"] is True
    assert marker["allocation_attempted"] is False


def test_geometry_record_freezes_run_identity_and_restore_budget() -> None:
    from tools.inference_contracts.p8_2_k1a_r2_geometry_observer import (
        build_geometry_record,
    )

    record = build_geometry_record(
        probe_run_id="probe-run-002",
        rank=5,
        world_size=8,
        num_npu_blocks=5048,
        descriptors=[("layer.0.v", 1024), ("layer.0.k", 2048)],
    )

    assert record["schema_version"] == "p8_2_k1a_r2_geometry_v1"
    assert record["probe_run_id"] == "probe-run-002"
    assert record["rank"] == 5
    assert record["required_cpu_blocks"] == 128
    assert record["total_bytes_per_block"] == 3072
    assert record["required_capacity_bytes_per_rank"] == 393216
    assert record["allocation_attempted"] is False


def test_r2_geometry_summary_requires_matching_rendezvous_marker(
    tmp_path: Path,
) -> None:
    from tools.inference_contracts.p8_2_k1a_r2_allocator import (
        summarize_geometry_directory,
    )

    run_id = "probe-run-003"
    for rank in range(8):
        (tmp_path / f"geometry.rank.{rank}.json").write_text(
            json.dumps(_record(rank, run_id)), encoding="utf-8"
        )
    (tmp_path / "geometry.rendezvous.complete.json").write_text(
        json.dumps(
            {
                "schema_version": "p8_2_k1a_r2_geometry_rendezvous_v1",
                "probe_run_id": run_id,
                "rank_coverage": list(range(8)),
                "world_size": 8,
                "geometry_parity_exact": True,
                "allocation_attempted": False,
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_geometry_directory(tmp_path)

    assert summary["stage"] == "P8.2-K1A-R2"
    assert summary["probe_run_id"] == run_id
    assert summary["rendezvous_gate_ok"] is True
    assert summary["rank_coverage"] == list(range(8))
    assert summary["required_capacity_bytes_per_rank"] == 262144
    assert summary["formal_lifecycle_authorized"] is False


def test_allocator_envelope_uses_r2_grade_after_rendezvous() -> None:
    from tools.inference_contracts.p8_2_k1a_r1_allocator import (
        assess_allocator_envelope,
    )

    geometry = {
        "stage": "P8.2-K1A-R2",
        "geometry_gate_ok": True,
        "rendezvous_gate_ok": True,
        "required_cpu_blocks": 128,
        "required_capacity_bytes_per_rank": 262144,
    }
    waves = [
        {"cpu_blocks": blocks, "rank_success_count": 8, "cleanup_ok": True}
        for blocks in (32, 64, 96, 128)
    ]

    result = assess_allocator_envelope(geometry, waves)

    assert result["grade"] == "candidate_ready_p8_2_k1a_r2_allocator_capacity"
    assert result["schema_version"] == "p8_2_k1a_r2_allocator_envelope_v1"
    assert result["formal_lifecycle_allowed"] is False


def test_k1a_r2_audit_preserves_r1_red_and_requires_rendezvous() -> None:
    audit = yaml.safe_load(
        (
            REPO_ROOT
            / "benchmarks/deepseek_v4_flash/p8_2_k1a_r2_geometry_rendezvous_audit.yaml"
        ).read_text(encoding="utf-8")
    )

    assert audit["stage"] == "P8.2-K1A-R2"
    assert audit["parent"]["grade"] == "red_p8_2_k1a_r1_geometry_probe_invalid"
    assert audit["parent"]["complete_rank_coverage"] == [0, 2]
    assert audit["parent"]["allocator_envelope_attempted"] is False
    assert audit["root_cause"]["first_rank_raised_before_eight_rank_rendezvous"] is True
    assert audit["r2"]["atomic_record_publish"] is True
    assert audit["r2"]["probe_run_id_required"] is True
    assert audit["r2"]["sentinel_after_rendezvous_only"] is True
    assert audit["r2"]["model_request_count_exact"] == 0
    assert audit["allocator_envelope"]["wave_cpu_blocks"] == [32, 64, 96, 128]
    assert audit["decision"]["formal_lifecycle_authorized"] is False
    assert audit["decision"]["p8_3_i1_authorized"] is False


def test_r2_geometry_summary_direct_file_cli_bootstraps_repo_root() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "tools/inference_contracts/p8_2_k1a_r2_allocator.py"
            ),
            "--help",
        ],
        cwd=Path("/tmp"),
        env=env,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "summarize-geometry" in completed.stdout


def test_current_handoff_authorizes_only_k1a_r5_f0_after_parent_blocks() -> None:
    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(
        encoding="utf-8"
    )
    task_id = (
        "p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724"
    )

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert f"task_id: {task_id}" in handoff
    for field in (
        "formal_model_lifecycle_count_exact: 1",
        "model_request_count_max: 4",
        "capacity_search_authorized: false",
        "result_transfer_authorized: true",
        "next_task_authorized: false",
    ):
        assert field in handoff
    for marker in (
        "ready_p8_2_k1a_r2_allocator_capacity",
        "green_p8_3_i0_r1_unclassified_taxonomy",
        "run_deepseek_p8_2_k1a_r5_f1_r4_restore_eligibility_alignment.sh",
        "cpu_bytes_to_use_per_rank=430604288",
        "candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout",
        "P8.3-I1",
    ):
        assert marker in handoff
    assert "result_transfer_authorized: false" not in handoff
