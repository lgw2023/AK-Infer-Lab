import json
from pathlib import Path
import subprocess
import sys

import yaml

from tools.inference_contracts.p8_2_k1a_r5_f1_r2_trace_alignment import (
    MID_REQUEST_ENDPOINT_MISMATCH_GRADE,
    NO_L2_CPU_ONLY_WINDOW_GRADE,
    align_calibration_and_l2,
)


ROOT = Path(__file__).resolve().parents[2]
ANALYZER = (
    ROOT
    / "tools/inference_contracts/"
    "p8_2_k1a_r5_f1_r2_trace_alignment.py"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r2_trace_alignment.sh"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r2_trace_alignment_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r2_trace_alignment.yaml"
)
READINESS = ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"
TASK_ID = "p8_2_k1a_r5_f1_r2_trace_alignment_2026_0722"


def _progress(
    timestamp_ns: int,
    before: int,
    scheduled: int,
    cpu: int,
    gpu: int,
) -> dict[str, object]:
    return {
        "event": "request_local_pressure_progress",
        "timestamp_ns": timestamp_ns,
        "contract_role": "pressure_01",
        "scheduled_request_count": 1,
        "request_local_progress_exact": True,
        "num_computed_tokens_before_schedule": before,
        "num_scheduled_tokens": scheduled,
        "num_computed_tokens_after_schedule": before + scheduled,
        "target_block_count": 64,
        "cpu_target_block_count": cpu,
        "gpu_target_block_count": gpu,
    }


def _snapshot(timestamp_ns: int, cpu: int, gpu: int, reason: str) -> dict[str, object]:
    return {
        "event": "target_residency_snapshot",
        "timestamp_ns": timestamp_ns,
        "reason": reason,
        "target_block_count": 64,
        "cpu_target_block_count": cpu,
        "gpu_target_block_count": gpu,
        "raw_hash_values_retained": False,
    }


def _endpoint(cpu: int, gpu: int) -> dict[str, object]:
    return {
        "schema_version": "p8_2_k1a_r5_l1_residency_gate_timeline_v1",
        "terminal_decision": "cpu_target_lost",
        "restore_sent": False,
        "gate_samples": [
            {
                "after_role": "pressure_01",
                "decision": "cpu_target_lost",
                "target_block_count": 64,
                "latest_cpu_target_block_count": cpu,
                "latest_gpu_target_block_count": gpu,
                "restore_allowed": False,
            }
        ],
    }


def _calibration_rows() -> list[dict[str, object]]:
    return [
        _progress(110, 0, 32768, 0, 64),
        _progress(120, 32768, 4096, 64, 0),
        _progress(130, 36864, 4096, 64, 0),
    ]


def test_alignment_identifies_mid_request_window_then_endpoint_loss() -> None:
    l2_rows = [
        _snapshot(190, 0, 64, "after_connector_meta"),
        _snapshot(210, 64, 0, "after_connector_meta"),
        _snapshot(220, 64, 0, "after_connector_output"),
        {
            "event": "target_cache_evicted",
            "timestamp_ns": 230,
            "tier": "cpu",
            "target_evicted_count": 1,
        },
        _snapshot(240, 54, 0, "after_target_eviction"),
    ]

    value = align_calibration_and_l2(
        calibration_rows=_calibration_rows(),
        calibration_pressure_start_ns=100,
        l2_rows=l2_rows,
        l2_pressure_start_ns=200,
        l2_endpoint_timeline=_endpoint(54, 0),
    )

    assert value["server_grade"] == MID_REQUEST_ENDPOINT_MISMATCH_GRADE
    assert value["calibration_candidate_context_tokens"] == 36800
    assert value["calibration_scheduled_token_histogram"] == {
        "4096": 2,
        "32768": 1,
    }
    assert value["l2_pressure_snapshot_count"] == 3
    assert value["l2_cpu_only_snapshot_count"] == 2
    assert value["l2_cpu_only_before_first_cpu_eviction"] is True
    assert value["l2_endpoint_cpu_target_block_count"] == 54
    assert value["l2_endpoint_gpu_target_block_count"] == 0
    assert value["mid_request_window_to_endpoint_gate_mismatch_observed"] is True
    assert value["request_end_timestamp_alignment_exact"] is False
    assert value["unique_cause_proven"] is False
    assert value["new_npu_lifecycle_authorized"] is False


def test_alignment_distinguishes_no_complete_l2_cpu_only_window() -> None:
    l2_rows = [
        _snapshot(210, 48, 0, "after_connector_meta"),
        {
            "event": "target_cache_evicted",
            "timestamp_ns": 220,
            "tier": "cpu",
            "target_evicted_count": 1,
        },
        _snapshot(230, 47, 0, "after_target_eviction"),
    ]

    value = align_calibration_and_l2(
        calibration_rows=_calibration_rows(),
        calibration_pressure_start_ns=100,
        l2_rows=l2_rows,
        l2_pressure_start_ns=200,
        l2_endpoint_timeline=_endpoint(47, 0),
    )

    assert value["server_grade"] == NO_L2_CPU_ONLY_WINDOW_GRADE
    assert value["l2_cpu_only_snapshot_count"] == 0
    assert value["mid_request_window_to_endpoint_gate_mismatch_observed"] is False
    assert value["calibration_window_reproduced_in_fixed_l2"] is False


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _build_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    calibration = tmp_path / "calibration"
    calibration_analysis = tmp_path / "calibration_analysis"
    l2 = tmp_path / "fixed_l2"
    _write_json(
        calibration / "runtime/request_control/active_role.json",
        {"role": "pressure_01", "updated_timestamp_ns": 100},
    )
    trace = calibration / "runtime/offload_trace/h2d-residency.1.jsonl"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(
        "".join(json.dumps(row) + "\n" for row in _calibration_rows()),
        encoding="utf-8",
    )
    _write_json(
        calibration_analysis / "grading_summary.json",
        {
            "server_grade": "candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure",
            "formal_fixed_l2_candidate_allowed": True,
        },
    )
    _write_json(
        calibration_analysis / "pressure_candidate.json",
        {
            "candidate_pressure_context_tokens": 36800,
            "candidate_pressure_total_tokens": 36864,
            "candidate_output_tokens": 64,
            "candidate_is_fixed_not_search": True,
        },
    )
    _write_json(
        l2 / "runtime/request_control/active_role.json",
        {"role": "pressure_01", "updated_timestamp_ns": 200},
    )
    l2_trace = l2 / "runtime/offload_trace/h2d-residency.2.jsonl"
    l2_trace.parent.mkdir(parents=True, exist_ok=True)
    l2_trace.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                _snapshot(210, 64, 0, "after_connector_meta"),
                _snapshot(215, 64, 0, "after_connector_output"),
                {
                    "event": "target_cache_evicted",
                    "timestamp_ns": 220,
                    "tier": "cpu",
                    "target_evicted_count": 1,
                },
                _snapshot(230, 54, 0, "after_target_eviction"),
            )
        ),
        encoding="utf-8",
    )
    _write_json(
        l2 / "runtime/request_control/residency_gate_timeline.json",
        _endpoint(54, 0),
    )
    _write_json(
        l2 / "grading_summary.json",
        {
            "server_grade": "red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost",
            "request_count": 3,
            "successful_request_count": 3,
            "cleanup": "clean",
        },
    )
    return calibration, calibration_analysis, l2


def test_analyzer_writes_a_complete_bounded_package(tmp_path: Path) -> None:
    calibration, calibration_analysis, l2 = _build_fixture(tmp_path)
    output = tmp_path / "analysis"

    completed = subprocess.run(
        [
            sys.executable,
            str(ANALYZER),
            "analyze",
            "--calibration-root",
            str(calibration),
            "--calibration-analysis-root",
            str(calibration_analysis),
            "--l2-root",
            str(l2),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert (output / "task_grade.txt").read_text().strip() == (
        MID_REQUEST_ENDPOINT_MISMATCH_GRADE
    )
    manifest = json.loads(
        (output / "candidate_manifest.server_local.json").read_text()
    )
    assert manifest["payload_file_count"] == 5
    assert manifest["transfer_file_count"] == 6
    assert manifest["manifest_bytes"] == (
        output / "candidate_manifest.server_local.json"
    ).stat().st_size
    assert manifest["transfer_total_bytes"] == sum(
        path.stat().st_size for path in output.iterdir() if path.is_file()
    )
    assert manifest["transfer_total_bytes"] <= 71680
    assert manifest["result_transfer_authorized"] is True
    assert manifest["transfer_method_selected"] is False
    provenance = json.loads(
        (output / "source_evidence_provenance.json").read_text()
    )
    assert provenance["all_source_files_unchanged"] is True
    assert provenance["raw_trace_content_retained"] is False


def test_runner_audit_and_contract_surfaces_are_zero_npu() -> None:
    completed = subprocess.run(
        ["bash", str(RUNNER), "/tmp/unused"],
        cwd=ROOT,
        env={"P8_2_K1A_F1_R2_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert f"task_id={TASK_ID}" in completed.stdout
    assert "npu_execution_authorized=false" in completed.stdout
    assert "model_requests_authorized=false" in completed.stdout
    assert "keep_alive_action=leave_running" in completed.stdout
    audit = yaml.safe_load(AUDIT.read_text())
    workload = yaml.safe_load(WORKLOAD.read_text())
    readiness = yaml.safe_load(READINESS.read_text())
    assert audit["task_id"] == TASK_ID
    assert workload["task_id"] == TASK_ID
    assert workload["authorization"]["npu_execution_authorized"] is False
    assert workload["authorization"]["model_requests_authorized"] is False
    assert workload["authorization"]["next_task_authorized"] is False
    assert readiness["artifacts"]["current_server_handoff_task"] == TASK_ID

    handoff = HANDOFF.read_text(encoding="utf-8")
    assert f"task_id: {TASK_ID}" in handoff
    assert "npu_execution_authorized: false" in handoff
    assert "model_requests_authorized: false" in handoff
    assert "不得停掉" in handoff
    assert "npu_stop.sh 0 1 2 3 4 5 6 7" in handoff
    assert "npu_keep_alive.sh 0 1 2 3 4 5 6 7" in handoff
    assert "result_transfer_authorized: true" in handoff
    assert "transfer_method_selected: false" in handoff
    assert "next_task_authorized: false" in handoff
