from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml

from tools.inference_contracts.p8_2_k1a_r5_f1_r16_async_completion_adjudication import (
    GREEN_GRADE,
    TASK_ID,
    build_worker_completion_rollup,
)
from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    summarize_trace_rows,
)


ROOT = Path(__file__).resolve().parents[2]
ANALYZER = (
    ROOT
    / "tools/inference_contracts/"
    "p8_2_k1a_r5_f1_r16_async_completion_adjudication.py"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r16_async_completion_semantics.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r16_server_task.sh"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r16_async_completion_semantics_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r16_async_completion_semantics.yaml"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _trace_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for direction in ("d2h", "h2d"):
        for rank in range(8):
            pid = 1000 + rank
            live_pending = not (direction == "h2d" and rank == 7)
            rows.extend(
                [
                    {"event": "copy_thread_started", "pid": pid},
                    {
                        "event": "device_copy_submitted",
                        "direction": direction,
                        "pid": pid,
                        "byte_count": 1024,
                    },
                    {
                        "event": "device_copy_enqueued",
                        "direction": direction,
                        "pid": pid,
                    },
                    {
                        "event": "copy_blocks_entered",
                        "direction": direction,
                        "pid": pid,
                    },
                    {
                        "event": "copy_blocks_returned",
                        "direction": direction,
                        "pid": pid,
                    },
                    {
                        "event": "transfer_poll_entered",
                        "direction": direction,
                        "pid": pid,
                        "pending_event_count": 1 if live_pending else 0,
                        "copy_thread_alive": live_pending,
                    },
                    {
                        "event": "transfer_poll_returned",
                        "direction": direction,
                        "pid": pid,
                    },
                    {
                        "event": "transfer_completed",
                        "direction": direction,
                        "pid": pid,
                    },
                ]
            )
    rows.extend(
        [
            {"event": "store_event_completed"},
            {
                "event": "cpu_hit_matched",
                "contract_role": "restore_follower",
                "num_new_tokens": 16384,
            },
            {
                "event": "load_scheduled",
                "contract_role": "restore_follower",
                "block_count": 40,
            },
            {
                "event": "load_request_completed",
                "contract_role": "restore_follower",
            },
        ]
    )
    return rows


def test_completion_exact_does_not_require_live_pending_at_poll_entry() -> None:
    rows = _trace_rows()
    summary = summarize_trace_rows(
        rows,
        expected_world_size=8,
        restore_request_suffix="restore_follower",
    )
    rollup = build_worker_completion_rollup(rows)

    assert summary["h2d_completed_worker_count"] == 8
    assert summary["h2d_poll_entered_worker_count"] == 8
    assert summary["h2d_poll_returned_worker_count"] == 8
    assert summary["h2d_poll_live_pending_worker_count"] == 7
    assert summary["h2d_poll_live_pending_coverage_exact"] is False
    assert summary["h2d_poll_returned_completion_exact"] is True
    assert summary["h2d_async_copy_pipeline_exact"] is True
    assert summary["h2d_restore_complete"] is True
    assert rollup["completion_without_live_pending_worker_count"] == 1
    assert all(
        "pid" not in key
        for row in rollup["worker_rows"]
        for key in row
    )


def test_missing_completion_still_fails_async_pipeline() -> None:
    rows = _trace_rows()
    removed = False
    filtered: list[dict[str, object]] = []
    for row in rows:
        if (
            not removed
            and row.get("event") == "transfer_completed"
            and row.get("direction") == "h2d"
            and row.get("pid") == 1007
        ):
            removed = True
            continue
        filtered.append(row)
    summary = summarize_trace_rows(
        filtered,
        expected_world_size=8,
        restore_request_suffix="restore_follower",
    )
    assert summary["h2d_completed_worker_count"] == 7
    assert summary["h2d_async_copy_pipeline_exact"] is False
    assert summary["h2d_restore_complete"] is False


def test_offline_analyzer_regrades_the_exact_r15_shape_without_npu(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "r15"
    trace = parent / "runtime/offload_trace/h2d-residency.1.jsonl"
    trace.parent.mkdir(parents=True)
    trace.write_text(
        "".join(json.dumps(row) + "\n" for row in _trace_rows()),
        encoding="utf-8",
    )
    parent_values = {
        "grading_summary.json": {
            "server_grade": (
                "red_p8_2_k1a_r5_f1_r15_h2d_evidence_incomplete"
            ),
            "experimental_terminal": "restore_request_completed",
            "operational_grade": "operational_recovery_clean",
            "restore_step_lineage_primary_class": (
                "delayed_external_then_reqs_to_load"
            ),
            "restore_h2d_path_class": "via_reqs_to_load",
            "restore_pairing_repair_applied": True,
            "restore_any_entered_reqs_to_load": True,
        },
        "h2d_trigger_summary.json": {
            "h2d_restore_mechanism_candidate": True,
            "target_cpu_only_residency_observed": True,
        },
        "transfer_trace_summary.json": {
            "h2d_restore_complete": True,
            "h2d_async_copy_pipeline_exact": False,
            "h2d_poll_event_visible_worker_count": 7,
            "h2d_completed_worker_count": 8,
            "async_copy_failure_event_count": 0,
        },
        "resource_recovery_summary.json": {
            "resource_recovery_exact": True,
        },
        "candidate_manifest.server_local.json": {"fixture": True},
    }
    for name, value in parent_values.items():
        _write_json(parent / name, value)
    (parent / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")

    source_files = {
        name: _sha256(parent / name)
        for name in (*parent_values, "cleanup_status.txt")
    }
    audit_path = tmp_path / "audit.yaml"
    audit_path.write_text(
        yaml.safe_dump(
            {
                "task_id": TASK_ID,
                "accepted_f1_r15_result": {
                    "source_file_sha256": source_files
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "r16"
    completed = subprocess.run(
        [
            sys.executable,
            str(ANALYZER),
            "analyze",
            "--parent-root",
            str(parent),
            "--output-dir",
            str(output),
            "--audit",
            str(audit_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert (output / "task_grade.txt").read_text().strip() == GREEN_GRADE
    grading = json.loads((output / "grading_summary.json").read_text())
    assert grading["h2d_restore_mechanism_accepted"] is True
    assert grading["r15_false_negative_gate_observed"] is True
    provenance = json.loads(
        (output / "source_evidence_provenance.json").read_text()
    )
    assert provenance["all_source_files_unchanged"] is True
    manifest = json.loads(
        (output / "candidate_manifest.server_local.json").read_text()
    )
    assert manifest["transfer_file_count"] == 7
    assert manifest["transfer_total_bytes"] <= 71680
    assert manifest["bounded_transfer_package_exact"] is True


def test_r16_contract_is_zero_npu_and_current_handoff_only() -> None:
    completed = subprocess.run(
        ["bash", str(RUNNER), "/tmp/unused"],
        cwd=ROOT,
        env={"P8_2_K1A_F1_R16_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert f"task_id={TASK_ID}" in completed.stdout
    assert "npu_execution_authorized=false" in completed.stdout
    assert "model_requests_authorized=false" in completed.stdout
    assert "keep_alive_action=leave_running" in completed.stdout
    assert "h2d_poll_live_pending_is_diagnostic_only=true" in completed.stdout

    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert audit["task_id"] == TASK_ID
    assert workload["task_id"] == TASK_ID
    assert workload["authorization"]["npu_execution_authorized"] is False
    assert TASK_ID in SERVER_TASK.read_text(encoding="utf-8") or (
        "r16_async_completion_semantics.sh"
        in SERVER_TASK.read_text(encoding="utf-8")
    )
    assert TASK_ID in handoff
    assert (
        "authorized_offline_r15_raw_trace_completion_adjudication"
        in handoff
    )
    assert "npu_execution_authorized: false" in handoff
    assert "keep_alive_action: leave_running" in handoff
    assert "result_transfer_authorized: true" in handoff
    assert "next_task_authorized: false" in handoff
