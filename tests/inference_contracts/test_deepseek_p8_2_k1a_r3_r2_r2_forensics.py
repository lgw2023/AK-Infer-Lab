from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess

from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    summarize_trace_rows,
)
from tools.inference_contracts.p8_2_k1a_failure_forensics import (
    build_failure_diagnostic,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUEST_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py"
)
FORENSICS = (
    REPO_ROOT / "tools/inference_contracts/p8_2_k1a_failure_forensics.py"
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def test_finalizer_promotes_the_first_failed_request_into_bounded_diagnostics(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact"
    request_root = artifact / "modes/prefix_cache_on"
    request_root.mkdir(parents=True)
    rows = [
        {
            "request_id": "lifecycle_01_warmup",
            "status": "success",
            "http_status": 200,
            "prompt_tokens": 4096,
            "context_tokens": 4096,
            "output_tokens": 64,
            "generated_token_count": 64,
            "streamed_token_count": 64,
            "finish_reason": "length",
            "saw_done": True,
            "max_token_chunk_width": 2,
            "queue_metrics_ok": True,
            "counter_continuity_ok": True,
            "spec_activity_ok": True,
            "accepted_token_delta": 32,
            "request_body_sha256": "1" * 64,
            "checks": {"http_200": True},
        },
        {
            "request_id": "lifecycle_01_prime",
            "status": "failed",
            "http_status": 500,
            "prompt_tokens": None,
            "context_tokens": 32768,
            "output_tokens": 64,
            "generated_token_count": None,
            "streamed_token_count": 0,
            "finish_reason": None,
            "saw_done": False,
            "max_token_chunk_width": 0,
            "queue_metrics_ok": False,
            "counter_continuity_ok": True,
            "spec_activity_ok": False,
            "accepted_token_delta": -32,
            "request_body_sha256": "2" * 64,
            "bounded_error_server_path": str(
                artifact / "request_errors/lifecycle_01_prime.body"
            ),
            "checks": {
                "server_alive": True,
                "http_200": False,
                "prompt_tokens_exact": False,
                "generated_tokens_exact": False,
                "streamed_tokens_exact": False,
                "finish_reason_length": False,
                "saw_done": False,
                "health_after_200": True,
                "queue_idle_after": False,
            },
        },
    ]
    (request_root / "raw_request_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    _write_json(
        artifact / "request_errors/lifecycle_01_prime.body",
        {
            "error": {
                "message": "NPU copy failed",
                "prompt": [1, 2, 3],
                "token_ids": [4, 5],
            }
        },
    )
    trace_root = artifact / "runtime/offload_trace"
    trace_root.mkdir(parents=True)
    (trace_root / "trace.test.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "event": "device_copy_submitted",
                    "direction": "d2h",
                    "pid": pid,
                    "event_idx": 1,
                    "block_count": 15,
                    "byte_count": 50461440,
                }
            )
            + "\n"
            for pid in range(100, 108)
        ),
        encoding="utf-8",
    )
    _write_json(
        artifact / "connector_resolution_summary.json",
        {
            "resolved_connector_exact": True,
            "resolved_cpu_capacity_exact": True,
            "cpu_bytes_to_use": 3444834304,
            "cpu_bytes_to_use_per_rank": 430604288,
        },
    )
    _write_json(
        artifact / "repair_diagnostic_summary.json", {"hybrid_diagnostic_ok": True}
    )
    _write_json(
        artifact / "host_memory_summary.json",
        {
            "preflight_gate_ok": True,
            "configured_cpu_tier_bytes_total": 3444834304,
            "configured_cpu_tier_bytes_per_rank": 430604288,
        },
    )
    (artifact / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "P8_2_K1A_TASK_ID": "p8_2_k1a_r3_r2_r2_forensic_replay_2026_0720",
            "P8_2_K1A_CPU_BYTES_TO_USE": "3444834304",
            "P8_2_K1A_CPU_BYTES_TO_USE_PER_RANK": "430604288",
            "P8_2_K1A_CANDIDATE_GREEN": "candidate_green_test",
            "P8_2_K1A_PARTIAL_GRADE": "yellow_partial_test",
        }
    )
    completed = subprocess.run(
        [
            "python3",
            str(REQUEST_RUNNER),
            "finalize",
            "--artifact-dir",
            str(artifact),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 2
    diagnostic = json.loads(
        (artifact / "failure_diagnostic_summary.json").read_text(encoding="utf-8")
    )
    assert diagnostic["failed_request_id"] == "lifecycle_01_prime"
    assert diagnostic["first_failed_predicate"] == "http_200"
    assert diagnostic["failure_classification"] == "http_or_client_error"
    assert diagnostic["cause_proven_as_unique"] is False
    excerpt = (artifact / "first_failure_excerpt.txt").read_text(encoding="utf-8")
    assert "lifecycle_01_prime" in excerpt
    assert "http_200" in excerpt
    assert "NPU copy failed" in excerpt
    assert "prompt" not in excerpt
    assert "token_ids" not in excerpt

    with (artifact / "request_summary.tsv").open(encoding="utf-8") as handle:
        summary_rows = list(csv.DictReader(handle, delimiter="\t"))
    prime = summary_rows[1]
    assert prime["http_status"] == "500"
    assert prime["generated_token_count"] == ""
    assert prime["streamed_token_count"] == "0"
    assert prime["finish_reason"] == ""
    assert prime["saw_done"] == "False"
    assert prime["first_failed_predicate"] == "http_200"
    assert "bounded_error_server_path" not in prime

    manifest = json.loads(
        (artifact / "candidate_manifest.server_local.json").read_text(
            encoding="utf-8"
        )
    )
    assert "failure_diagnostic_summary.json" in manifest["files"]
    assert manifest["candidate_total_bytes"] <= 71680


def test_offline_extractor_preserves_parent_evidence_and_builds_a_bounded_package(
    tmp_path: Path,
) -> None:
    source = tmp_path / "parent_result"
    output = tmp_path / "forensics"
    request_root = source / "modes/prefix_cache_on"
    request_root.mkdir(parents=True)
    failed = {
        "request_id": "lifecycle_01_prime",
        "status": "failed",
        "http_status": None,
        "context_tokens": 32768,
        "output_tokens": 64,
        "generated_token_count": None,
        "streamed_token_count": 0,
        "finish_reason": None,
        "saw_done": False,
        "max_token_chunk_width": 0,
        "request_body_sha256": "2" * 64,
        "request_start_ns": 100,
        "request_end_ns": 200,
        "token_arrival_ns": [123],
        "metrics_before": {
            "num_requests_running": 0,
            "num_requests_waiting": 0,
            "num_accepted_tokens": 32,
        },
        "metrics_after": {
            "num_requests_running": 0,
            "num_requests_waiting": 1,
            "num_accepted_tokens": 0,
        },
        "checks": {
            "server_alive": True,
            "http_200": False,
            "health_after_200": True,
            "queue_idle_after": False,
        },
    }
    (request_root / "raw_request_results.jsonl").write_text(
        json.dumps(failed) + "\n", encoding="utf-8"
    )
    trace_root = source / "runtime/offload_trace"
    trace_root.mkdir(parents=True)
    (trace_root / "trace.test.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "event": "device_copy_submitted",
                    "component": "npu_copy_backend",
                    "direction": "d2h",
                    "pid": pid,
                    "rank": str(pid - 100),
                    "timestamp_ns": pid,
                    "event_idx": 1,
                    "block_count": 15,
                    "byte_count": 50461440,
                    "secret": "must-not-leak",
                }
            )
            + "\n"
            for pid in range(100, 108)
        ),
        encoding="utf-8",
    )
    log_path = source / "runtime/vllm_server.log"
    log_path.write_text(
        "INFO server ready\n"
        "ERROR SimpleCPUOffload D2H completion timeout\n"
        "Traceback: worker copy wait failed\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "python3",
            str(FORENSICS),
            "extract",
            "--source-result-dir",
            str(source),
            "--output-dir",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    provenance = json.loads(
        (output / "source_evidence_provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["source_evidence_unchanged"] is True
    assert provenance["before"] == provenance["after"]
    assert provenance["before"]["file_count"] == 3

    sanitized = json.loads(
        (output / "failed_request_sanitized.json").read_text(encoding="utf-8")
    )
    assert sanitized["request_id"] == "lifecycle_01_prime"
    assert sanitized["first_failed_predicate"] == "http_200"
    assert sanitized["request_start_ns"] == 100
    assert sanitized["request_end_ns"] == 200
    assert "token_arrival_ns" not in sanitized
    assert "bounded_error_server_path" not in sanitized

    timeline = json.loads(
        (output / "transfer_trace_timeline.json").read_text(encoding="utf-8")
    )
    assert timeline["event_count"] == 8
    assert all("secret" not in row for row in timeline["events"])
    diagnostic = json.loads(
        (output / "failure_diagnostic_summary.json").read_text(encoding="utf-8")
    )
    assert diagnostic["failure_classification"] == "transfer_completion_absent_without_direct_exception"
    assert diagnostic["formal_replay_allowed"] is True
    assert diagnostic["cause_proven_as_unique"] is False

    excerpt = (output / "vllm_first_failure_excerpt.txt").read_bytes()
    assert len(excerpt) <= 16384
    assert b"D2H completion timeout" in excerpt
    manifest = json.loads(
        (output / "candidate_manifest.server_local.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["candidate_total_bytes"] <= 71680
    assert manifest["result_transfer_authorized"] is True
    assert manifest["transfer_method_selected"] is False
    assert manifest["missing_candidate_files"] == []


def test_source_audit_closes_the_exact_scheduler_worker_copy_surfaces(
    tmp_path: Path,
) -> None:
    vllm_root = tmp_path / "vllm"
    ascend_root = tmp_path / "vllm_ascend"
    sources = {
        vllm_root / "v1/simple_kv_offload/manager.py": """
class SimpleCPUOffloadScheduler:
    def get_num_new_matched_tokens(self): pass
    def build_connector_meta(self): pass
    def update_connector_output(self): pass
""",
        vllm_root / "v1/simple_kv_offload/worker.py": """
class SimpleCPUOffloadWorker:
    def _poll_stream_events(self, is_store): pass
""",
        ascend_root / "simple_kv_offload/worker.py": """
from vllm.v1.simple_kv_offload.worker import SimpleCPUOffloadWorker

class SimpleCPUOffloadNPUWorker(SimpleCPUOffloadWorker):
    pass
""",
        ascend_root / "simple_kv_offload/copy_backend.py": """
from vllm_ascend.simple_kv_offload.npu_mem_ops import copy_blocks

class NPUDmaCopyBackend:
    def _copy_loop(self): pass
    def launch_copy(self, src_blocks, dst_blocks, is_store, event_idx, events_list): pass
""",
        ascend_root / "simple_kv_offload/npu_mem_ops.py": """
def copy_blocks(src_blocks, dst_blocks, params): pass
""",
        ascend_root
        / "distributed/kv_transfer/kv_pool/simple_cpu_offload/simple_cpu_offload_connector.py": """
class AscendSimpleCPUOffloadConnector:
    pass
""",
    }
    for path, source in sources.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    output = tmp_path / "source_semantics.json"

    completed = subprocess.run(
        [
            "python3",
            str(FORENSICS),
            "source-audit",
            "--vllm-root",
            str(vllm_root),
            "--vllm-ascend-root",
            str(ascend_root),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["source_semantics_gate"] == "pass"
    assert audit["source_file_count"] == 6
    assert audit["required_symbols_present"] is True
    assert audit["copy_primitive_resolution"] == {
        "binding_imported_name": "copy_blocks",
        "binding_kind": "import_from",
        "binding_local_name": "copy_blocks",
        "binding_module": "vllm_ascend.simple_kv_offload.npu_mem_ops",
        "definition_label": "ascend_npu_mem_ops",
        "definition_present": True,
        "resolved": True,
        "symbol": "copy_blocks",
    }
    assert audit["inheritance_resolution"] == {
        "base_class": "SimpleCPUOffloadWorker",
        "base_method": "SimpleCPUOffloadWorker._poll_stream_events",
        "derived_class": "SimpleCPUOffloadNPUWorker",
        "derived_class_inherits_base": True,
        "method_resolution": "inherited_from_frozen_vllm",
        "resolved": True,
    }
    assert audit["frozen_launch_signature"] == {
        "parameters": [
            "self",
            "src_blocks",
            "dst_blocks",
            "is_store",
            "event_idx",
            "events_list",
        ],
        "observer_extra_parameters": [],
        "observer_signature_compatible": True,
    }
    assert audit["observer_surface"] == {
        "copy_backend_enqueue": "NPUDmaCopyBackend.launch_copy",
        "copy_backend_worker_loop": "NPUDmaCopyBackend._copy_loop",
        "copy_primitive": "copy_blocks",
        "scheduler_completion": "SimpleCPUOffloadScheduler.update_connector_output",
        "scheduler_match": "SimpleCPUOffloadScheduler.get_num_new_matched_tokens",
        "scheduler_schedule": "SimpleCPUOffloadScheduler.build_connector_meta",
        "worker_completion": "SimpleCPUOffloadNPUWorker._poll_stream_events",
    }


def test_runtime_log_audit_accepts_only_the_retired_wait_event_observer_defect(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vllm_server.log"
    log_path.write_text(
        """Traceback (most recent call last):
  File "/tmp/overlay/p8_2_k1a_simple_cpu_offload_observer.py", line 132, in observed_launch
    result = original_launch(self, src, dst, is_store, event_idx, events, wait_event)
TypeError: NPUDmaCopyBackend.launch_copy() takes 6 positional arguments but 7 were given
""",
        encoding="utf-8",
    )
    output = tmp_path / "runtime_exception_provenance.json"

    completed = subprocess.run(
        [
            "python3",
            str(FORENSICS),
            "runtime-log-audit",
            "--log",
            str(log_path),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["direct_runtime_exception_present"] is True
    assert audit["exception_count"] == 1
    assert audit["known_retired_observer_wait_event_defect_count"] == 1
    assert audit["unknown_runtime_exception_count"] == 0
    assert audit["runtime_log_gate"] == "pass_known_retired_observer_defect"
    assert audit["formal_lifecycle_runtime_log_condition"] is True
    assert audit["exceptions"][0]["exception_type"] == "TypeError"
    assert audit["exceptions"][0]["message_pattern"] == (
        "launch_copy_extra_positional_wait_event"
    )
    assert audit["exceptions"][0]["known_retired_observer_defect_match"] is True
    assert audit["exceptions"][0]["callsite_frames"][-1] == {
        "file": "p8_2_k1a_simple_cpu_offload_observer.py",
        "function": "observed_launch",
        "line": 132,
    }
    assert len(audit["exceptions"][0]["normalized_message_sha256"]) == 64
    assert audit["generated_content_retained"] is False
    assert audit["token_ids_retained"] is False


def test_runtime_log_audit_blocks_an_unrelated_caught_worker_exception(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vllm_server.log"
    log_path.write_text(
        """Traceback (most recent call last):
  File "/opt/vllm/multiproc_executor.py", line 91, in run
    output = worker.execute()
RuntimeError: device copy stream failed
""",
        encoding="utf-8",
    )
    output = tmp_path / "runtime_exception_provenance.json"

    completed = subprocess.run(
        [
            "python3",
            str(FORENSICS),
            "runtime-log-audit",
            "--log",
            str(log_path),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 2
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["runtime_log_gate"] == "fail_unknown_runtime_exception"
    assert audit["formal_lifecycle_runtime_log_condition"] is False
    assert audit["known_retired_observer_wait_event_defect_count"] == 0
    assert audit["unknown_runtime_exception_count"] == 1
    assert audit["exceptions"][0]["exception_type"] == "RuntimeError"
    assert audit["exceptions"][0]["message_pattern"] == (
        "unrecognized_runtime_exception"
    )


def test_runtime_log_audit_groups_frozen_worker_and_engine_wrappers_under_known_root(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vllm_server.log"
    log_path.write_text(
        """Traceback (most recent call last):
  File "/tmp/overlay/p8_2_k1a_simple_cpu_offload_observer.py", line 132, in observed_launch
TypeError: NPUDmaCopyBackend.launch_copy() takes 6 positional arguments but 7 were given
Traceback (most recent call last):
  File "/opt/vllm/v1/executor/multiproc_executor.py", line 390, in get_response
RuntimeError: Worker failed with error 'NPUDmaCopyBackend.launch_copy() takes 6 positional arguments but 7 were given', please check the stack trace above for the root cause
Traceback (most recent call last):
  File "/opt/vllm/v1/engine/core_client.py", line 1030, in get_output_async
EngineDeadError: EngineCore encountered an issue. See stack trace (above) for the root cause.
Traceback (most recent call last):
  File "/opt/vllm/entrypoints/openai/serving.py", line 305, in completion_stream_generator
  File "/opt/vllm/v1/engine/core_client.py", line 1030, in get_output_async
EngineDeadError: EngineCore encountered an issue. See stack trace (above) for the root cause.
""",
        encoding="utf-8",
    )
    output = tmp_path / "runtime_exception_provenance.json"

    completed = subprocess.run(
        [
            "python3",
            str(FORENSICS),
            "runtime-log-audit",
            "--log",
            str(log_path),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["schema_version"] == (
        "p8_2_k1a_runtime_exception_causal_provenance_v2"
    )
    assert audit["runtime_log_gate"] == (
        "pass_known_retired_observer_defect_with_deterministic_wrappers"
    )
    assert audit["root_known_observer_defect_count"] == 1
    assert audit["derived_worker_runtime_wrapper_count"] == 1
    assert audit["derived_engine_dead_wrapper_count"] == 2
    assert audit["independent_unknown_exception_count"] == 0
    assert audit["formal_lifecycle_runtime_log_condition"] is True
    assert audit["exception_record_count_exact"] is True
    assert sum(group["count"] for group in audit["exception_groups"]) == 4
    assert {group["causal_role"] for group in audit["exception_groups"]} == {
        "root_known_observer_defect",
        "derived_worker_runtime_wrapper",
        "derived_engine_dead_wrapper",
    }
    assert audit["frozen_wrapper_contract"] == {
        "engine_dead_message_sha256": (
            "988c82d7efef7bf00a3704ebde56ac21a2909a32bdbd1e13368341b475859130"
        ),
        "worker_runtime_message_sha256": (
            "42d6217fd6e2666b3bc6a403bfb201809cf500353095062c39eed6f113e5fd63"
        ),
        "vllm_commit": "0decac0d96c42b49572498019f0a0e3600f50398",
    }


def test_runtime_log_audit_requires_frozen_wrapper_source_templates_when_requested(
    tmp_path: Path,
) -> None:
    vllm_root = tmp_path / "vllm"
    executor = vllm_root / "v1/executor/multiproc_executor.py"
    exceptions = vllm_root / "v1/engine/exceptions.py"
    core_client = vllm_root / "v1/engine/core_client.py"
    executor.parent.mkdir(parents=True)
    exceptions.parent.mkdir(parents=True)
    executor.write_text(
        """def get_response():
    if status != WorkerProc.ResponseStatus.SUCCESS:
        raise RuntimeError(
            f"Worker failed with error '{result}', please check the"
            " stack trace above for the root cause"
        )
""",
        encoding="utf-8",
    )
    exceptions.write_text(
        """class EngineDeadError(Exception):
    def __init__(self):
        ENGINE_DEAD_MESSAGE = "EngineCore encountered an issue. See stack trace (above) for the root cause."
        super().__init__(ENGINE_DEAD_MESSAGE)
""",
        encoding="utf-8",
    )
    core_client.write_text(
        """async def get_output_async(self) -> EngineCoreOutputs:
    if isinstance(outputs, Exception):
        raise self._format_exception(outputs) from None
""",
        encoding="utf-8",
    )
    log_path = tmp_path / "vllm_server.log"
    log_path.write_text(
        """TypeError: NPUDmaCopyBackend.launch_copy() takes 6 positional arguments but 7 were given
  File "/opt/vllm/v1/executor/multiproc_executor.py", line 390, in get_response
RuntimeError: Worker failed with error 'NPUDmaCopyBackend.launch_copy() takes 6 positional arguments but 7 were given', please check the stack trace above for the root cause
  File "/opt/vllm/v1/engine/core_client.py", line 1030, in get_output_async
EngineDeadError: EngineCore encountered an issue. See stack trace (above) for the root cause.
""",
        encoding="utf-8",
    )
    output = tmp_path / "runtime_exception_provenance.json"

    completed = subprocess.run(
        [
            "python3",
            str(FORENSICS),
            "runtime-log-audit",
            "--log",
            str(log_path),
            "--vllm-root",
            str(vllm_root),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    audit = json.loads(output.read_text(encoding="utf-8"))
    source = audit["frozen_wrapper_source_templates"]
    assert source["gate"] == "pass"
    assert source["required_file_count"] == 3
    assert source["matched_file_count"] == 3
    assert source["multiproc_worker_wrapper_exact"] is True
    assert source["multiproc_get_response_raise_path_present"] is True
    assert source["engine_dead_message_exact"] is True
    assert source["engine_dead_raise_path_present"] is True
    assert all(len(row["sha256"]) == 64 for row in source["files"].values())
    assert audit["formal_lifecycle_runtime_log_condition"] is True


def test_runtime_log_audit_keeps_parent_scale_counts_exact_beyond_sample_limit(
    tmp_path: Path,
) -> None:
    known = (
        "TypeError: NPUDmaCopyBackend.launch_copy() takes 6 positional "
        "arguments but 7 were given\n"
    )
    worker = (
        '  File "/opt/vllm/v1/executor/multiproc_executor.py", line 390, in get_response\n'
        "RuntimeError: Worker failed with error 'NPUDmaCopyBackend.launch_copy() "
        "takes 6 positional arguments but 7 were given', please check the stack "
        "trace above for the root cause\n"
    )
    engine = (
        '  File "/opt/vllm/v1/engine/core_client.py", line 1030, in get_output_async\n'
        "EngineDeadError: EngineCore encountered an issue. See stack trace "
        "(above) for the root cause.\n"
    )
    log_path = tmp_path / "vllm_server.log"
    log_path.write_text(known * 16 + worker + engine * 2 + known * 16)
    output = tmp_path / "runtime_exception_provenance.json"

    completed = subprocess.run(
        [
            "python3",
            str(FORENSICS),
            "runtime-log-audit",
            "--log",
            str(log_path),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["exception_count"] == 35
    assert audit["root_known_observer_defect_count"] == 32
    assert audit["derived_worker_runtime_wrapper_count"] == 1
    assert audit["derived_engine_dead_wrapper_count"] == 2
    assert audit["independent_unknown_exception_count"] == 0
    assert audit["exception_records_truncated"] is True
    assert audit["exception_record_count_exact"] is True
    assert sum(group["count"] for group in audit["exception_groups"]) == 35
    assert output.stat().st_size < 71680


def test_runtime_log_audit_compact_mode_retains_exact_groups_without_record_samples(
    tmp_path: Path,
) -> None:
    known = (
        "TypeError: NPUDmaCopyBackend.launch_copy() takes 6 positional "
        "arguments but 7 were given\n"
    )
    worker = (
        '  File "/opt/vllm/v1/executor/multiproc_executor.py", line 390, in get_response\n'
        "RuntimeError: Worker failed with error 'NPUDmaCopyBackend.launch_copy() "
        "takes 6 positional arguments but 7 were given', please check the stack "
        "trace above for the root cause\n"
    )
    engine = (
        '  File "/opt/vllm/v1/engine/core_client.py", line 1030, in get_output_async\n'
        "EngineDeadError: EngineCore encountered an issue. See stack trace "
        "(above) for the root cause.\n"
    )
    log_path = tmp_path / "vllm_server.log"
    log_path.write_text(known * 32 + worker + engine * 2)
    output = tmp_path / "runtime_exception_provenance.compact.json"

    completed = subprocess.run(
        [
            "python3",
            str(FORENSICS),
            "runtime-log-audit",
            "--compact",
            "--log",
            str(log_path),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["exception_count"] == 35
    assert audit["exception_record_count_exact"] is True
    assert audit["exception_record_samples_included"] is False
    assert "exceptions" not in audit
    assert sum(group["count"] for group in audit["exception_groups"]) == 35
    assert output.stat().st_size < 16384


def test_runtime_log_audit_does_not_backlink_wrapper_that_precedes_the_root(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vllm_server.log"
    log_path.write_text(
        """  File "/opt/vllm/v1/executor/multiproc_executor.py", line 390, in get_response
RuntimeError: Worker failed with error 'NPUDmaCopyBackend.launch_copy() takes 6 positional arguments but 7 were given', please check the stack trace above for the root cause
TypeError: NPUDmaCopyBackend.launch_copy() takes 6 positional arguments but 7 were given
""",
        encoding="utf-8",
    )
    output = tmp_path / "runtime_exception_provenance.json"

    completed = subprocess.run(
        [
            "python3",
            str(FORENSICS),
            "runtime-log-audit",
            "--log",
            str(log_path),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 2
    audit = json.loads(output.read_text(encoding="utf-8"))
    assert audit["derived_worker_runtime_wrapper_count"] == 0
    assert audit["independent_unknown_exception_count"] == 1
    assert audit["runtime_log_gate"] == "fail_unknown_runtime_exception"


def test_transfer_summary_surfaces_copy_and_poll_exceptions_without_treating_them_as_completion() -> None:
    rows = [
        {
            "event": "device_copy_submitted",
            "direction": "d2h",
            "pid": 100,
            "byte_count": 1024,
        },
        {
            "event": "device_copy_launch_failed",
            "direction": "d2h",
            "pid": 100,
            "error_type": "RuntimeError",
            "error_message": "copy failed",
        },
        {
            "event": "transfer_poll_failed",
            "direction": "d2h",
            "pid": 101,
            "error_type": "TimeoutError",
            "error_message": "event not ready",
        },
    ]

    summary = summarize_trace_rows(
        rows, expected_world_size=8, restore_request_suffix="restore_follower"
    )

    assert summary["transfer_failure_event_count"] == 2
    assert summary["device_copy_launch_failed_count"] == 1
    assert summary["transfer_poll_failed_count"] == 1
    assert summary["d2h_completed_worker_count"] == 0
    assert summary["d2h_store_complete"] is False
    assert summary["runtime_evidence_exact"] is False


def test_transfer_summary_distinguishes_enqueue_from_background_copy_and_poll() -> None:
    rows: list[dict[str, object]] = []
    for pid in (100, 101):
        rows.extend(
            [
                {"event": "copy_thread_started", "pid": pid},
                {
                    "event": "device_copy_submitted",
                    "direction": "d2h",
                    "pid": pid,
                    "byte_count": 1024,
                },
                {"event": "device_copy_enqueued", "direction": "d2h", "pid": pid},
                {"event": "copy_blocks_entered", "direction": "d2h", "pid": pid},
                {"event": "copy_blocks_returned", "direction": "d2h", "pid": pid},
                {
                    "event": "transfer_poll_entered",
                    "direction": "d2h",
                    "pid": pid,
                    "pending_event_count": 1,
                    "copy_thread_alive": True,
                },
                {"event": "transfer_poll_returned", "direction": "d2h", "pid": pid},
                {"event": "transfer_completed", "direction": "d2h", "pid": pid},
            ]
        )
    rows.append({"event": "store_event_completed", "direction": "d2h", "pid": 90})

    summary = summarize_trace_rows(
        rows, expected_world_size=2, restore_request_suffix="restore_follower"
    )

    assert summary["d2h_enqueued_worker_count"] == 2
    assert summary["d2h_copy_blocks_entered_worker_count"] == 2
    assert summary["d2h_copy_blocks_returned_worker_count"] == 2
    assert summary["d2h_poll_event_visible_worker_count"] == 2
    assert summary["copy_thread_started_worker_count"] == 2
    assert summary["copy_thread_failed_count"] == 0
    assert summary["d2h_async_copy_pipeline_exact"] is True
    assert summary["async_copy_failure_event_count"] == 0


def test_bounded_client_exception_blocks_replay_even_without_an_http_status(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact"
    error = artifact / "request_errors/lifecycle_01_prime.txt"
    error.parent.mkdir(parents=True)
    error.write_text("TimeoutError: remote end closed connection\n", encoding="utf-8")
    rows = [
        {
            "request_id": "lifecycle_01_prime",
            "k1a_role": "prime",
            "status": "failed",
            "http_status": None,
            "bounded_error_server_path": str(error),
            "checks": {
                "server_alive": True,
                "http_200": False,
                "health_after_200": True,
            },
        }
    ]

    diagnostic, excerpt = build_failure_diagnostic(
        artifact,
        rows,
        {"d2h_worker_count": 8, "d2h_completed_worker_count": 0},
    )

    assert diagnostic["failure_classification"] == "http_or_client_error"
    assert diagnostic["cause_proven_as_unique"] is False
    assert "TimeoutError" in excerpt


def test_health_probe_loss_with_a_live_server_is_not_a_unique_process_failure(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "request_id": "lifecycle_01_prime",
            "status": "failed",
            "http_status": 200,
            "checks": {
                "server_alive": True,
                "http_200": True,
                "health_after_200": False,
                "queue_idle_after": False,
            },
        }
    ]

    diagnostic, _ = build_failure_diagnostic(
        tmp_path,
        rows,
        {
            "d2h_worker_count": 8,
            "d2h_completed_worker_count": 0,
            "transfer_failure_event_count": 0,
        },
    )

    assert diagnostic["failure_classification"] == (
        "request_health_loss_without_direct_exception"
    )
    assert diagnostic["server_alive"] is True
    assert diagnostic["health_after_200"] is False
    assert diagnostic["cause_proven_as_unique"] is False
