from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import yaml

from tools.inference_contracts.p8_2_k1a_r5_f1_r17_full_trace_source_replay import (
    BLOCKED_GRADE,
    GREEN_GRADE,
    TASK_ID,
    read_canonical_trace_source,
)
from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    summarize_trace_rows,
)


ROOT = Path(__file__).resolve().parents[2]
ANALYZER = (
    ROOT
    / "tools/inference_contracts/"
    "p8_2_k1a_r5_f1_r17_full_trace_source_replay.py"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r17_full_trace_source_replay.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r17_server_task.sh"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r17_full_trace_source_replay_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r17_full_trace_source_replay.yaml"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _async_rows() -> list[dict[str, object]]:
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
    rows.extend(
        {"event": "async_trace_padding"}
        for _ in range(1050 - len(rows))
    )
    assert len(rows) == 1050
    return rows


def _residency_rows() -> list[dict[str, object]]:
    rows = [
        {"event": "target_cpu_only_residency_observed"}
        for _ in range(319)
    ]
    assert len(rows) == 319
    return rows


def _fixture(
    tmp_path: Path,
    *,
    include_async_family: bool = True,
    include_combined: bool = False,
) -> tuple[Path, Path, Path, list[dict[str, object]]]:
    r15 = tmp_path / "r15"
    r16 = tmp_path / "r16"
    trace_dir = r15 / "runtime/offload_trace"
    async_rows = _async_rows()
    residency_rows = _residency_rows()
    full_rows = residency_rows + async_rows
    _write_jsonl(
        trace_dir / "h2d-residency.1000.jsonl",
        residency_rows,
    )
    if include_async_family:
        _write_jsonl(trace_dir / "trace.1000.jsonl", async_rows)
    if include_combined:
        _write_json(trace_dir / "combined.json", full_rows)

    transfer = summarize_trace_rows(
        full_rows,
        expected_world_size=8,
        restore_request_suffix="restore_follower",
    )
    transfer["h2d_async_copy_pipeline_exact"] = False
    r15_values = {
        "grading_summary.json": {
            "server_grade": (
                "red_p8_2_k1a_r5_f1_r15_h2d_evidence_incomplete"
            ),
            "experimental_terminal": "restore_request_completed",
            "operational_grade": "operational_recovery_clean",
            "restore_step_lineage_primary_class": transfer[
                "restore_step_lineage_primary_class"
            ],
            "restore_h2d_path_class": transfer[
                "restore_h2d_path_class"
            ],
            "restore_pairing_repair_applied": False,
            "restore_any_entered_reqs_to_load": transfer[
                "restore_any_entered_reqs_to_load"
            ],
            "cleanup": "clean",
            "resource_recovery_exact": True,
        },
        "h2d_trigger_summary.json": {
            "h2d_restore_mechanism_candidate": True,
            "target_cpu_only_residency_observed": True,
            "h2d_worker_completion_count": 8,
            "h2d_worker_completion_exact": True,
            "restore_cpu_hit_exact": True,
            "restore_cpu_hit_tokens_max": 16384,
        },
        "transfer_trace_summary.json": transfer,
        "resource_recovery_summary.json": {
            "resource_recovery_exact": True,
        },
        "candidate_manifest.server_local.json": {"fixture": "r15"},
    }
    for name, value in r15_values.items():
        _write_json(r15 / name, value)
    (r15 / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")

    r16_adjudication = {
        "server_grade": (
            "red_p8_2_k1a_r5_f1_r16_async_completion_trace_incomplete"
        ),
        "parent_contract_exact": True,
        "async_completion_evidence_exact": False,
        "h2d_poll_live_pending_coverage_exact": False,
        "recomputed_transfer": {
            "trace_event_count": 319,
            "d2h_worker_count": 0,
            "h2d_worker_count": 0,
            "d2h_bytes_total": 0,
            "h2d_bytes_total": 0,
            "async_copy_failure_event_count": 0,
        },
    }
    r16_values = {
        "grading_summary.json": {
            "server_grade": (
                "red_p8_2_k1a_r5_f1_r16_async_completion_trace_incomplete"
            ),
            "parent_source_hashes_exact": True,
            "source_evidence_unchanged": True,
            "async_completion_evidence_exact": False,
            "h2d_restore_mechanism_accepted": False,
            "new_npu_lifecycle_executed": False,
        },
        "async_completion_adjudication_summary.json": r16_adjudication,
        "source_evidence_provenance.json": {
            "task_id": (
                "p8_2_k1a_r5_f1_r16_async_completion_semantics_2026_0727"
            ),
            "all_source_files_unchanged": True,
            "raw_trace_content_retained": False,
            "raw_trace_before": {
                "file_count": 1,
                "total_bytes": 319,
                "tree_sha256": "fixture-r16-residency-only",
            },
        },
        "candidate_manifest.server_local.json": {"fixture": "r16"},
    }
    for name, value in r16_values.items():
        _write_json(r16 / name, value)
    (r16 / "task_grade.txt").write_text(
        "red_p8_2_k1a_r5_f1_r16_async_completion_trace_incomplete\n",
        encoding="utf-8",
    )

    r15_source_files = {
        name: _sha256(r15 / name)
        for name in (*r15_values, "cleanup_status.txt")
    }
    r16_source_files = {
        name: _sha256(r16 / name)
        for name in (*r16_values, "task_grade.txt")
    }
    audit = {
        "task_id": TASK_ID,
        "repository_input_sha256": {
            ANALYZER.relative_to(ROOT).as_posix(): _sha256(ANALYZER)
        },
        "accepted_f1_r15_result": {
            "grading_fields": r15_values["grading_summary.json"],
            "trigger_fields": r15_values["h2d_trigger_summary.json"],
            "transfer_fields": {
                key: transfer[key]
                for key in (
                    "trace_event_count",
                    "expected_world_size",
                    "d2h_worker_count",
                    "h2d_worker_count",
                    "d2h_completed_worker_count",
                    "h2d_completed_worker_count",
                    "d2h_enqueued_worker_count",
                    "h2d_enqueued_worker_count",
                    "d2h_copy_blocks_entered_worker_count",
                    "h2d_copy_blocks_entered_worker_count",
                    "d2h_copy_blocks_returned_worker_count",
                    "h2d_copy_blocks_returned_worker_count",
                    "d2h_poll_event_visible_worker_count",
                    "h2d_poll_event_visible_worker_count",
                    "copy_thread_started_worker_count",
                    "d2h_bytes_total",
                    "h2d_bytes_total",
                    "async_copy_failure_event_count",
                    "d2h_store_complete",
                    "h2d_restore_complete",
                    "restore_step_lineage_primary_class",
                    "restore_h2d_path_class",
                    "restore_any_pairing_repair_applied",
                    "restore_any_entered_reqs_to_load",
                    "h2d_async_copy_pipeline_exact",
                )
            },
            "source_file_sha256": r15_source_files,
        },
        "accepted_f1_r16_result": {
            "grading_fields": r16_values["grading_summary.json"],
            "adjudication_fields": {
                key: r16_adjudication[key]
                for key in (
                    "server_grade",
                    "parent_contract_exact",
                    "async_completion_evidence_exact",
                    "h2d_poll_live_pending_coverage_exact",
                )
            },
            "recomputed_transfer_fields": r16_adjudication[
                "recomputed_transfer"
            ],
            "provenance_fields": {
                "task_id": r16_values[
                    "source_evidence_provenance.json"
                ]["task_id"],
                "all_source_files_unchanged": True,
                "raw_trace_content_retained": False,
            },
            "raw_trace_fields": r16_values[
                "source_evidence_provenance.json"
            ]["raw_trace_before"],
            "source_file_sha256": r16_source_files,
        },
    }
    audit_path = tmp_path / "audit.yaml"
    audit_path.write_text(
        yaml.safe_dump(audit, sort_keys=False),
        encoding="utf-8",
    )
    return r15, r16, audit_path, full_rows


def _run_analyzer(
    command: str,
    *,
    r15: Path,
    r16: Path,
    audit: Path,
    output: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [
        sys.executable,
        str(ANALYZER),
        command,
        "--r15-root",
        str(r15),
        "--r16-root",
        str(r16),
        "--audit",
        str(audit),
    ]
    if output is not None:
        argv.extend(["--output-dir", str(output)])
    return subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_real_dual_file_family_layout_recovers_the_omitted_events(
    tmp_path: Path,
) -> None:
    r15, r16, audit, _ = _fixture(tmp_path)
    rows, source = read_canonical_trace_source(
        r15 / "runtime/offload_trace"
    )
    assert len(rows) == 1369
    assert source["selection_mode"] == "all_jsonl"
    assert (
        source["family_inventory"]["async_transfer_trace"][
            "selected_row_count"
        ]
        == 1050
    )
    assert (
        source["family_inventory"]["residency_trace"][
            "selected_row_count"
        ]
        == 319
    )

    output = tmp_path / "r17"
    completed = _run_analyzer(
        "analyze",
        r15=r15,
        r16=r16,
        audit=audit,
        output=output,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert (output / "task_grade.txt").read_text().strip() == GREEN_GRADE
    coverage = json.loads(
        (output / "trace_source_coverage_summary.json").read_text()
    )
    assert coverage["trace_source_coverage_exact"] is True
    assert coverage["r16_source_selector_fault_confirmed"] is True
    assert coverage["full_replay_trace_event_count"] == 1369
    assert coverage["r16_selected_trace_event_count"] == 319
    assert coverage["recovered_trace_event_count_vs_r16"] == 1050
    replay = json.loads(
        (output / "full_trace_replay_summary.json").read_text()
    )
    assert replay["h2d_restore_mechanism_accepted"] is True
    assert replay["recomputed_transfer"]["h2d_worker_count"] == 8
    assert replay["recomputed_transfer"]["h2d_completed_worker_count"] == 8
    assert (
        replay["recomputed_transfer"]["h2d_poll_returned_worker_count"]
        == 8
    )
    manifest = json.loads(
        (output / "candidate_manifest.server_local.json").read_text()
    )
    assert manifest["transfer_file_count"] == 8
    assert manifest["transfer_total_bytes"] <= 71680


def test_missing_async_file_family_is_blocked_not_mechanism_red(
    tmp_path: Path,
) -> None:
    r15, r16, audit, _ = _fixture(
        tmp_path,
        include_async_family=False,
    )
    preflight = _run_analyzer(
        "preflight",
        r15=r15,
        r16=r16,
        audit=audit,
    )
    assert preflight.returncode == 0, preflight.stderr or preflight.stdout
    assert "trace_source_coverage_exact=false" in preflight.stdout
    assert f"prospective_grade={BLOCKED_GRADE}" in preflight.stdout

    output = tmp_path / "r17-blocked"
    completed = _run_analyzer(
        "analyze",
        r15=r15,
        r16=r16,
        audit=audit,
        output=output,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert (output / "task_grade.txt").read_text().strip() == BLOCKED_GRADE
    grading = json.loads((output / "grading_summary.json").read_text())
    assert grading["trace_source_coverage_exact"] is False
    assert grading["mechanism_adjudication_performed"] is False
    assert grading["async_completion_evidence_exact"] is None
    assert grading["h2d_restore_mechanism_accepted"] is False


def test_combined_json_has_precedence_without_double_read(
    tmp_path: Path,
) -> None:
    r15, r16, audit, _ = _fixture(
        tmp_path,
        include_combined=True,
    )
    rows, source = read_canonical_trace_source(
        r15 / "runtime/offload_trace"
    )
    assert len(rows) == 1369
    assert source["selection_mode"] == "combined_json"
    assert source["selected_source_file_count"] == 1
    assert source["all_source_file_count"] == 3
    assert source["duplicate_combined_and_jsonl_read"] is False

    output = tmp_path / "r17-combined"
    completed = _run_analyzer(
        "analyze",
        r15=r15,
        r16=r16,
        audit=audit,
        output=output,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert (output / "task_grade.txt").read_text().strip() == GREEN_GRADE


def test_r17_contract_is_zero_npu_current_handoff_and_self_verifying() -> None:
    completed = subprocess.run(
        ["bash", str(RUNNER), "/tmp/unused"],
        cwd=ROOT,
        env={"P8_2_K1A_F1_R17_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert f"task_id={TASK_ID}" in completed.stdout
    assert "canonical_trace_reader=combined_json_else_all_jsonl" in (
        completed.stdout
    )
    assert "dual_trace_file_family_coverage_required=true" in (
        completed.stdout
    )
    assert "coverage_mismatch_is_mechanism_red=false" in completed.stdout
    assert "npu_execution_authorized=false" in completed.stdout
    assert "keep_alive_action=leave_running" in completed.stdout
    assert "result_package_self_verification_required=true" in (
        completed.stdout
    )

    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert audit["task_id"] == TASK_ID
    assert "TO_BE_FILLED" not in AUDIT.read_text(encoding="utf-8")
    assert audit["repository_input_sha256"]
    assert workload["task_id"] == TASK_ID
    assert workload["authorization"]["npu_execution_authorized"] is False
    assert (
        "r17_full_trace_source_replay.sh"
        in SERVER_TASK.read_text(encoding="utf-8")
    )
    assert TASK_ID in handoff
    assert (
        "authorized_offline_r15_complete_trace_source_replay"
        in handoff
    )
    assert "npu_execution_authorized: false" in handoff
    assert "keep_alive_action: leave_running" in handoff
    assert "result_transfer_authorized: true" in handoff
    assert "next_task_authorized: false" in handoff
