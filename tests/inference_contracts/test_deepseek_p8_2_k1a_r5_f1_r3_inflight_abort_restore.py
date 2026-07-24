from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import yaml

from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore import (
    AbortableRequestHandle,
    PRESSURE_CONTEXT_TOKENS,
    TASK_ID,
    _build_inflight_candidate_manifest,
    _pressure_abort_evidence_exact,
    _stream_abortable_request,
    _timeline_order_exact,
    _write_bounded_request_summary,
    build_inflight_trigger_state,
)


ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore.sh"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r3_inflight_abort_restore_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r3_inflight_abort_restore.yaml"
)
READINESS = ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


def _progress(
    *,
    timestamp_ns: int,
    cpu: int,
    gpu: int,
    exact: bool = True,
    scheduled_request_count: int = 1,
) -> dict[str, object]:
    return {
        "event": "request_local_pressure_progress",
        "timestamp_ns": timestamp_ns,
        "contract_role": "pressure_01",
        "scheduled_request_count": scheduled_request_count,
        "request_local_progress_exact": exact,
        "num_computed_tokens_before_schedule": 4096,
        "num_scheduled_tokens": 4096,
        "num_computed_tokens_after_schedule": 8192,
        "target_block_count": 64,
        "cpu_target_block_count": cpu,
        "gpu_target_block_count": gpu,
    }


def test_inflight_trigger_requires_exact_request_local_cpu_only_state() -> None:
    state = build_inflight_trigger_state(
        [
            _progress(timestamp_ns=90, cpu=64, gpu=0),
            _progress(timestamp_ns=110, cpu=64, gpu=1),
            _progress(timestamp_ns=120, cpu=64, gpu=0),
        ],
        pressure_start_timestamp_ns=100,
    )

    assert state["decision"] == "trigger_ready"
    assert state["abort_allowed"] is True
    assert state["pressure_progress_event_count"] == 2
    assert state["exact_cpu_only_progress_event_count"] == 1
    assert state["trigger"] == {
        "timestamp_ns": 120,
        "contract_role": "pressure_01",
        "scheduled_request_count": 1,
        "request_local_progress_exact": True,
        "num_computed_tokens_before_schedule": 4096,
        "num_scheduled_tokens": 4096,
        "num_computed_tokens_after_schedule": 8192,
        "target_block_count": 64,
        "cpu_target_block_count": 64,
        "gpu_target_block_count": 0,
        "raw_hash_values_retained": False,
        "request_id_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }


def test_inflight_trigger_fails_closed_for_ambiguous_scheduling() -> None:
    state = build_inflight_trigger_state(
        [
            _progress(
                timestamp_ns=120,
                cpu=64,
                gpu=0,
                exact=False,
                scheduled_request_count=2,
            )
        ],
        pressure_start_timestamp_ns=100,
    )

    assert state["decision"] == "request_local_progress_ambiguous"
    assert state["abort_allowed"] is False
    assert state["ambiguous_progress_event_count"] == 1


def test_cpu_target_eviction_blocks_a_stale_cpu_only_trigger() -> None:
    state = build_inflight_trigger_state(
        [
            _progress(timestamp_ns=120, cpu=64, gpu=0),
            {
                "event": "target_cache_evicted",
                "timestamp_ns": 130,
                "tier": "cpu",
                "target_evicted_count": 1,
            },
        ],
        pressure_start_timestamp_ns=100,
    )

    assert state["decision"] == "cpu_target_lost"
    assert state["abort_allowed"] is False
    assert state["cpu_target_eviction_event_count"] == 1


def test_abortable_stream_closes_an_inflight_http_request(tmp_path: Path) -> None:
    response_started = threading.Event()
    release_handler = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            assert self.path == "/v1/completions"
            length = int(self.headers["Content-Length"])
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.flush()
            response_started.set()
            release_handler.wait(timeout=5)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    artifact = tmp_path / "artifact"
    body_path = artifact / "request_bodies/pressure.json"
    body_path.parent.mkdir(parents=True)
    body = json.dumps(
        {"prompt": list(range(16)), "max_tokens": 4, "stream": True}
    ).encode()
    body_path.write_bytes(body)
    item = {
        "request_id": "pressure-test",
        "body_relative_path": str(body_path.relative_to(artifact)),
        "request_body_sha256": hashlib.sha256(body).hexdigest(),
        "k1a_role": "pressure_01",
        "group_id": "pressure",
        "repeat_index": 0,
    }
    batch = {
        "batch_id": "pressure-test",
        "phase": "prime",
        "context_tokens": 16,
        "output_tokens": 4,
        "repeat_index": 0,
    }
    handle = AbortableRequestHandle()
    client_thread = threading.Thread(
        target=_stream_abortable_request,
        kwargs={
            "handle": handle,
            "artifact_dir": artifact,
            "base_url": f"http://127.0.0.1:{server.server_port}",
            "server_pid": os.getpid(),
            "batch": batch,
            "request_item": item,
        },
        daemon=True,
    )
    try:
        client_thread.start()
        assert response_started.wait(timeout=3)
        handle.abort()
        client_thread.join(timeout=3)
        assert not client_thread.is_alive()
        assert handle.row is not None
        assert handle.row["status"] == "aborted_on_trigger"
        assert handle.row["abort_requested"] is True
        assert handle.row["abort_confirmed_by_client_exit"] is True
        assert handle.row["full_response_observed"] is False
        assert handle.row["generated_text_retained"] is False
        assert handle.row["token_ids_retained"] is False
    finally:
        release_handler.set()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)


def test_pressure_abort_evidence_requires_idle_before_restore() -> None:
    row = {
        "k1a_role": "pressure_01",
        "status": "aborted_on_trigger",
        "http_status": 200,
        "context_tokens": 36800,
        "output_tokens": 64,
        "abort_requested": True,
        "abort_confirmed_by_client_exit": True,
        "full_response_observed": False,
        "queue_idle_after_abort": True,
        "queue_metrics_ok": True,
        "counter_continuity_ok": True,
        "health_after_200": True,
        "request_body_sha256": "a" * 64,
    }

    assert _pressure_abort_evidence_exact(row) is True
    row["queue_idle_after_abort"] = False
    assert _pressure_abort_evidence_exact(row) is False


def test_candidate_timeline_requires_monotonic_abort_idle_restore_order() -> None:
    timeline = {
        "terminal_decision": "restore_request_completed",
        "trigger_observed_before_abort": True,
        "pressure_abort_requested": True,
        "pressure_abort_confirmed": True,
        "pressure_idle_after_abort": True,
        "window_valid_after_abort": True,
        "restore_sent": True,
        "restore_request_completed": True,
        "pressure_start_monotonic_ns": 1,
        "trigger_latched_monotonic_ns": 2,
        "pressure_abort_requested_monotonic_ns": 3,
        "pressure_client_exit_observed_monotonic_ns": 4,
        "engine_idle_confirmed_monotonic_ns": 5,
        "post_abort_gate_checked_monotonic_ns": 6,
        "restore_dispatched_monotonic_ns": 7,
        "restore_completed_monotonic_ns": 8,
    }
    assert _timeline_order_exact(timeline) is True
    timeline["engine_idle_confirmed_monotonic_ns"] = 9
    assert _timeline_order_exact(timeline) is False


def test_bounded_package_excludes_request_ids_bodies_and_raw_hashes(
    tmp_path: Path,
) -> None:
    request_id = "sensitive-request-id"
    request_hash = "a" * 64
    _write_bounded_request_summary(
        tmp_path / "request_summary.tsv",
        [
            {
                "request_id": request_id,
                "request_body_sha256": request_hash,
                "k1a_role": "pressure_01",
                "status": "aborted_on_trigger",
                "context_tokens": 36800,
                "abort_requested": True,
            }
        ],
    )
    (tmp_path / "request_body_manifest.json").write_text(
        json.dumps({"request_id": request_id, "sha256": request_hash}),
        encoding="utf-8",
    )
    (tmp_path / "environment_and_hashes.json").write_text(
        json.dumps({"raw_hash": request_hash}), encoding="utf-8"
    )
    (tmp_path / "first_failure_excerpt.txt").write_text(
        request_id, encoding="utf-8"
    )
    summary = (tmp_path / "request_summary.tsv").read_text(encoding="utf-8")
    assert request_id not in summary
    assert request_hash not in summary
    assert "request_id" not in summary.splitlines()[0].split("\t")
    assert "request_body_sha256" not in summary.splitlines()[0].split("\t")

    manifest = _build_inflight_candidate_manifest(tmp_path)
    assert set(manifest["files"]) == {"request_summary.tsv"}
    assert manifest["request_ids_retained"] is False
    assert manifest["raw_request_or_trace_hash_values_retained"] is False
    assert manifest["manifest_integrity_digests_only"] is True


def test_prepare_freezes_one_fixed_four_request_protocol(tmp_path: Path) -> None:
    source = tmp_path / "source_payload.json"
    source.write_text(
        json.dumps({"prompt": list(range(4096))}, separators=(",", ":")),
        encoding="utf-8",
    )
    artifact = tmp_path / "artifact"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "prepare",
            "--source-payload",
            str(source),
            "--artifact-dir",
            str(artifact),
            "--model-name",
            "deepseek-v4-flash-w8a8-mtp",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    manifest = json.loads(
        (artifact / "request_body_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["task_id"] == TASK_ID
    assert manifest["pressure_context_tokens"] == PRESSURE_CONTEXT_TOKENS
    assert manifest["pressure_request_count_max"] == 1
    assert manifest["request_count_max"] == 4
    assert manifest["request_order_contract"] == [
        "warmup",
        "target_prime",
        "pressure_01_abort_on_request_local_cpu_only_trigger",
        "restore_follower_after_abort_and_idle_if_window_still_valid",
    ]
    assert manifest["pressure_request_abort_is_conditional"] is True
    assert manifest["restore_requires_abort_confirmed_idle_and_window_still_valid"] is True
    assert len(manifest["records"]) == 4


def test_f1_r3_contract_and_audit_only_are_bounded(tmp_path: Path) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    controller = workload["inflight_controller"]
    state = workload["execution_state"]

    assert audit["stage"] == "P8.2-K1A-R5-F1-R3"
    assert audit["received_f1_r2_package"]["fixed_l2_cpu_only_window_lead_ns"] == 17945394939
    assert audit["developer_decision"]["context_search_or_sweep_authorized"] is False
    assert workload["task_id"] == TASK_ID
    assert workload["runtime_config"]["max_num_seqs"] == 1
    assert workload["request_plan"]["pressure_context_tokens"] == 36800
    assert workload["request_plan"]["request_count_exact"] == 4
    assert workload["request_plan"]["intentional_pressure_abort_count_exact"] == 1
    assert controller["active_role_remains_pressure_until_abort_and_idle_confirmed"] is True
    assert controller["engine_idle_after_abort_required"] is True
    assert controller["post_abort_residency_gate_decision_required"] == "trigger_ready"
    assert controller["role_switch_before_idle_authorized"] is False
    assert state["formal_model_lifecycle_count_exact"] == 1
    assert state["result_transfer_authorized"] is True
    assert state["transfer_method_selected"] is False
    assert state["next_task_authorized"] is False

    completed = subprocess.run(
        ["bash", str(LIFECYCLE), str(tmp_path / "unused")],
        cwd=ROOT,
        env={**os.environ, "P8_2_K1A_F1_R3_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    for line in (
        f"task_id={TASK_ID}",
        "npu_execution_authorized=true",
        "formal_model_lifecycle_count_exact=1",
        "model_request_count_exact=4",
        "completed_request_count_exact=3",
        "intentional_pressure_abort_count_exact=1",
        "pressure_context_tokens=36800",
        "request_retry_count_exact=0",
        "request_local_inflight_trigger_required=true",
        "pressure_abort_before_restore_required=true",
        "engine_idle_before_restore_required=true",
        "context_change_authorized=false",
        "pressure_search_or_sweep_authorized=false",
        "result_transfer_authorized=true",
        "transfer_method_selected=false",
        "next_task_authorized=false",
    ):
        assert line in completed.stdout


def test_f1_r5_is_the_only_current_server_handoff() -> None:
    current_task_id = (
        "p8_2_k1a_r5_f1_r12_hit_to_load_admission_2026_0724"
    )
    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    assert artifacts["current_server_handoff_task"] == current_task_id
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r12_hit_to_load_admission.yaml"
    )
    assert artifacts["current_p8_2_k1a_r5_f1_r5_runner"].endswith(
        "run_deepseek_p8_2_k1a_r5_f1_r5_effective_restore_contract.sh"
    )

    handoff = HANDOFF.read_text(encoding="utf-8")
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert handoff.count("\ntask_id: ") == 1
    assert f"task_id: {current_task_id}" in handoff
    for marker in (
        "logical_target_block_count_exact: 128",
        "physical_fa_key_count_fixed: false",
        "36800",
        "pressure_01",
        "physical_group_cpu_only_window_required_to_abort: true",
        "restore_follower",
        "npu_stop.sh 0 1 2 3 4 5 6 7",
        "npu_keep_alive.sh 0 1 2 3 4 5 6 7",
        "成功、实验 RED、失败、中断或提前退出",
        "result_transfer_authorized: true",
        "transfer_method_selected: false",
        "automatic_transfer_allowed: false",
        "email",
        "upload-api",
        "server-local",
    ):
        assert marker in handoff
