import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import yaml

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    build_request_local_pressure_progress,
    observer_self_test_contract,
)
from tools.inference_contracts.p8_2_k1a_r5_f1_r1_request_local_pressure import (
    derive_request_local_pressure_candidate,
)
from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_l1_lazy_h2d import (
    decide_next_action,
)

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_IMPL = ROOT / "tools/inference_contracts/p6_3b_r1_hybrid_kv_runtime_patch.py"
SHARED_MODE_PATCH = (
    ROOT
    / "benchmarks/deepseek_v4_flash/patches/"
    "p8_2_k1a_r5_f1_r1_shared_diagnostic_mode.patch"
)
ANALYZER = (
    ROOT
    / "tools/inference_contracts/"
    "p8_2_k1a_r5_f1_r1_request_local_pressure.py"
)
CALIBRATION_RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r1_request_local_calibration.sh"
)
REQUEST_LOCAL_TOOL = (
    ROOT
    / "tools/inference_contracts/"
    "p8_2_k1a_r5_f1_r1_request_local_pressure.py"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r1_request_local_pressure_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r1_request_local_pressure_conditional_lifecycle.yaml"
)
OFFLINE_RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r1_request_local_pressure.sh"
)
L2_RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r1_fixed_pressure_l2.sh"
)
READINESS = ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"
TASK_ID = "p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722"
READY_GRADE = "candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure"
CALIBRATION_REQUIRED_GRADE = (
    "candidate_requires_p8_2_k1a_r5_f1_r1_instrumented_calibration"
)


def test_request_local_progress_uses_the_single_cached_pressure_request() -> None:
    scheduler_output = SimpleNamespace(
        scheduled_new_reqs=[],
        scheduled_cached_reqs=SimpleNamespace(
            req_ids=["internal-request-id"],
            num_computed_tokens=[4096],
        ),
        num_scheduled_tokens={"internal-request-id": 4096},
    )

    row = build_request_local_pressure_progress(
        scheduler_output,
        contract_role="pressure_01",
        target_block_count=64,
        cpu_target_block_count=64,
        gpu_target_block_count=0,
    )

    assert row == {
        "schema_version": "p8_2_k1a_r5_f1_r1_request_local_progress_v1",
        "contract_role": "pressure_01",
        "scheduled_request_count": 1,
        "request_local_progress_exact": True,
        "num_computed_tokens_before_schedule": 4096,
        "num_scheduled_tokens": 4096,
        "num_computed_tokens_after_schedule": 8192,
        "target_block_count": 64,
        "cpu_target_block_count": 64,
        "gpu_target_block_count": 0,
        "request_id_retained": False,
        "token_ids_retained": False,
        "generated_content_retained": False,
    }


def test_request_local_progress_fails_closed_for_multiple_scheduled_requests() -> None:
    scheduler_output = SimpleNamespace(
        scheduled_new_reqs=[],
        scheduled_cached_reqs=SimpleNamespace(
            req_ids=["request-a", "request-b"],
            num_computed_tokens=[4096, 8192],
        ),
        num_scheduled_tokens={"request-a": 1024, "request-b": 1024},
    )

    row = build_request_local_pressure_progress(
        scheduler_output,
        contract_role="pressure_01",
        target_block_count=64,
        cpu_target_block_count=64,
        gpu_target_block_count=0,
    )

    assert row is not None
    assert row["scheduled_request_count"] == 2
    assert row["request_local_progress_exact"] is False
    assert row["num_computed_tokens_before_schedule"] is None
    assert row["num_scheduled_tokens"] is None
    assert row["num_computed_tokens_after_schedule"] is None
    assert "request_id" not in row


def test_request_local_progress_ignores_scheduler_steps_without_pressure_work() -> None:
    scheduler_output = SimpleNamespace(
        scheduled_new_reqs=[],
        scheduled_cached_reqs=SimpleNamespace(
            req_ids=[],
            num_computed_tokens=[],
        ),
        num_scheduled_tokens={},
    )

    row = build_request_local_pressure_progress(
        scheduler_output,
        contract_role="pressure_01",
        target_block_count=64,
        cpu_target_block_count=64,
        gpu_target_block_count=0,
    )

    assert row is None


def test_direct_progress_derives_one_fixed_candidate_with_a_full_chunk_margin() -> None:
    rows = [
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 100,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 0,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 4096,
            "target_block_count": 64,
            "cpu_target_block_count": 0,
            "gpu_target_block_count": 64,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 200,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 4096,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 8192,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 300,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 8192,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 12288,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
        {
            "event": "target_cache_evicted",
            "timestamp_ns": 400,
            "tier": "cpu",
            "target_evicted_count": 1,
        },
    ]

    result = derive_request_local_pressure_candidate(rows)

    assert result["request_local_progress_source_exact"] is True
    assert result["progress_event_count"] == 3
    assert result["exact_cpu_only_progress_event_count"] == 2
    assert result["candidate_pressure_total_tokens"] == 8192
    assert result["candidate_pressure_context_tokens"] == 8128
    assert result["observed_exact_window_margin_tokens"] == 4096
    assert result["required_completion_margin_tokens"] == 4096
    assert result["net_gpu_free_delta_used"] is False
    assert result["formal_fixed_l2_candidate_allowed"] is True
    assert result["target_cpu_cache_eviction_observed"] is True
    assert result["pressure_caused_target_eviction_proven"] is False
    assert result["cause_proven_as_unique"] is False


def test_missing_direct_progress_requires_one_instrumented_calibration() -> None:
    rows = [
        {
            "event": "target_residency_snapshot",
            "timestamp_ns": 200,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
            "gpu_free_block_count": 4929,
        }
    ]

    result = derive_request_local_pressure_candidate(rows)

    assert result["progress_event_count"] == 0
    assert result["request_local_progress_source_exact"] is False
    assert result["candidate_pressure_context_tokens"] is None
    assert result["formal_fixed_l2_candidate_allowed"] is False
    assert result["legacy_gpu_free_pool_delta_is_not_request_local"] is True
    assert result["next_required_action"] == (
        "one_observe_only_request_local_progress_calibration_lifecycle"
    )


def test_request_local_candidate_rejects_a_progress_gap() -> None:
    rows = [
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 100,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 4096,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 8192,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 200,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 12288,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 16384,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
    ]

    result = derive_request_local_pressure_candidate(rows)

    assert result["request_local_progress_source_exact"] is False
    assert result["formal_fixed_l2_candidate_allowed"] is False
    assert result["candidate_pressure_context_tokens"] is None


def test_calibration_analyzer_writes_a_bounded_ready_package(tmp_path: Path) -> None:
    source = tmp_path / "calibration"
    trace_dir = source / "runtime/offload_trace"
    trace_dir.mkdir(parents=True)
    rows = [
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 100,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 0,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 4096,
            "target_block_count": 64,
            "cpu_target_block_count": 0,
            "gpu_target_block_count": 64,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 200,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 4096,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 8192,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 300,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 8192,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 12288,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
    ]
    (trace_dir / "h2d-residency.1.jsonl").write_text(
        "".join(f"{__import__('json').dumps(row)}\n" for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "analysis"

    completed = subprocess.run(
        [
            sys.executable,
            str(ANALYZER),
            "analyze",
            "--source-result-root",
            str(source),
            "--trace-dir",
            str(trace_dir),
            "--analysis-mode",
            "calibration",
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    grading = __import__("json").loads(
        (output / "grading_summary.json").read_text(encoding="utf-8")
    )
    candidate = __import__("json").loads(
        (output / "pressure_candidate.json").read_text(encoding="utf-8")
    )
    manifest = __import__("json").loads(
        (output / "candidate_manifest.server_local.json").read_text(
            encoding="utf-8"
        )
    )
    assert grading["server_grade"] == (
        "candidate_ready_p8_2_k1a_r5_f1_r1_request_local_pressure"
    )
    assert grading["source_evidence_unchanged"] is True
    assert grading["formal_fixed_l2_candidate_allowed"] is True
    assert candidate["candidate_pressure_context_tokens"] == 8128
    assert candidate["candidate_is_fixed_not_search"] is True
    assert manifest["payload_file_count"] == 6
    assert manifest["payload_total_bytes"] + (
        output / "candidate_manifest.server_local.json"
    ).stat().st_size <= 71680
    assert manifest["result_transfer_authorized"] is True
    assert manifest["transfer_method_selected"] is False


def test_observer_contract_keeps_request_local_progress_observe_only() -> None:
    contract = observer_self_test_contract()

    assert contract["request_local_pressure_progress_capability"] is True
    assert contract["request_local_progress_source"] == (
        "SchedulerOutput.num_scheduled_tokens_and_request_num_computed_tokens"
    )
    assert contract["request_local_progress_requires_single_scheduled_request"] is True
    assert contract["request_id_retained"] is False
    assert contract["scheduling_or_copy_arguments_mutated"] is False
    assert contract["original_return_values_preserved"] is True
    assert contract["original_exceptions_preserved"] is True


def test_calibration_stops_at_trigger_without_sending_restore() -> None:
    value, exit_code = decide_next_action(
        {"decision": "trigger_ready", "restore_allowed": True},
        pressure_count=1,
        calibration_only=True,
    )

    assert exit_code == 0
    assert value == {
        "action": "stop_calibration_window_observed",
        "pressure_count": 1,
        "restore_allowed": False,
    }


def test_task_local_patch_normalizes_shared_evidence_mode(
    tmp_path: Path, monkeypatch,
) -> None:
    overlay_impl = tmp_path / "p6_3b_hybrid_kv_runtime_impl.py"
    shutil.copyfile(RUNTIME_IMPL, overlay_impl)
    completed = subprocess.run(
        ["patch", "-p1", "-d", str(tmp_path), "-i", str(SHARED_MODE_PATCH)],
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    spec = importlib.util.spec_from_file_location("task_local_runtime_impl", overlay_impl)
    assert spec is not None and spec.loader is not None
    runtime_impl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime_impl)

    path = tmp_path / "hybrid_kv_runtime_diagnostic.jsonl"
    monkeypatch.setenv(
        runtime_impl.DIAGNOSTIC_ENV,
        str(path),
    )
    old_umask = os.umask(0o077)
    try:
        runtime_impl._append_diagnostic({"event": "test"})
    finally:
        os.umask(old_umask)

    assert path.stat().st_mode & 0o777 == 0o660


def test_calibration_runner_freezes_observer_and_shared_mode_patch(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        ["bash", str(CALIBRATION_RUNNER), str(tmp_path / "result")],
        cwd=ROOT,
        env={
            **os.environ,
            "P8_2_K1A_F1_R1_CALIBRATION_AUDIT_ONLY": "1",
        },
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    for line in (
        "task_id=p8_2_k1a_r5_f1_r1_request_local_pressure_2026_0722",
        "lifecycle_role=request_local_progress_calibration",
        "calibration_only=true",
        "pressure_context_tokens=131072",
        "pressure_request_count_max=1",
        "request_count_min=3",
        "request_count_max=3",
        "request_local_pressure_observer=true",
        "shared_diagnostic_mode=0660_task_local_overlay",
        "restore_request_authorized=false",
        "request_retry_count=0",
    ):
        assert line in completed.stdout


def test_request_local_cli_reads_the_runtime_trace_directory(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "offload_trace"
    trace_dir.mkdir()
    rows = [
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 100,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 0,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 4096,
            "target_block_count": 64,
            "cpu_target_block_count": 0,
            "gpu_target_block_count": 64,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 200,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 4096,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 8192,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 300,
            "contract_role": "pressure_01",
            "scheduled_request_count": 1,
            "request_local_progress_exact": True,
            "num_computed_tokens_before_schedule": 8192,
            "num_scheduled_tokens": 4096,
            "num_computed_tokens_after_schedule": 12288,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
        },
    ]
    (trace_dir / "h2d-residency.1.jsonl").write_text(
        "".join(__import__("json").dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "request_local_pressure_attribution.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(REQUEST_LOCAL_TOOL),
            "derive",
            "--trace-dir",
            str(trace_dir),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    value = __import__("json").loads(output.read_text(encoding="utf-8"))
    assert value["candidate_pressure_context_tokens"] == 8128
    assert value["formal_fixed_l2_candidate_allowed"] is True
    assert value["request_id_retained"] is False


def test_parent_legacy_analysis_requires_one_instrumented_calibration(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy"
    trace_dir = source / "runtime/offload_trace"
    trace_dir.mkdir(parents=True)
    rows = [
        {
            "event": "target_residency_snapshot",
            "timestamp_ns": 200,
            "target_block_count": 64,
            "cpu_target_block_count": 64,
            "gpu_target_block_count": 0,
            "gpu_free_block_count": 4929,
        }
    ]
    (trace_dir / "h2d-residency.1.jsonl").write_text(
        "".join(__import__("json").dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "analysis"

    completed = subprocess.run(
        [
            sys.executable,
            str(ANALYZER),
            "analyze",
            "--source-result-root",
            str(source),
            "--trace-dir",
            str(trace_dir),
            "--analysis-mode",
            "parent_legacy",
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    grading = __import__("json").loads(
        (output / "grading_summary.json").read_text(encoding="utf-8")
    )
    attribution = __import__("json").loads(
        (output / "request_local_pressure_attribution.json").read_text(
            encoding="utf-8"
        )
    )
    assert grading["server_grade"] == CALIBRATION_REQUIRED_GRADE
    assert grading["formal_fixed_l2_candidate_allowed"] is False
    assert attribution["progress_event_count"] == 0
    assert attribution["next_required_action"] == (
        "one_observe_only_request_local_progress_calibration_lifecycle"
    )
    assert attribution["legacy_gpu_free_pool_delta_is_not_request_local"] is True


def test_f1_r1_contract_is_offline_first_with_at_most_two_lifecycles(
    tmp_path: Path,
) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    state = workload["execution_state"]
    calibration = workload["calibration_lifecycle"]
    fixed = workload["conditional_fixed_l2"]

    assert audit["stage"] == "P8.2-K1A-R5-F1-R1"
    assert audit["request_local_progress_gate"]["net_gpu_free_delta_may_unlock_l2"] is False
    assert audit["request_local_progress_gate"]["ready_grade"] == READY_GRADE
    assert audit["request_local_progress_gate"]["missing_progress_grade"] == (
        CALIBRATION_REQUIRED_GRADE
    )
    assert audit["developer_decision"]["formal_model_lifecycle_count_max"] == 2
    assert workload["task_id"] == TASK_ID
    assert workload["offline_first_gate"]["npu_started"] is False
    assert workload["offline_first_gate"]["model_request_sent"] is False
    assert calibration["pressure_context_tokens"] == 131072
    assert calibration["request_count_exact"] == 3
    assert calibration["restore_authorized"] is False
    assert calibration["calibration_only"] is True
    assert fixed["requires_ready_grade"] == READY_GRADE
    assert fixed["request_count_min"] == 3
    assert fixed["request_count_max"] == 4
    assert fixed["pressure_request_count_exact"] == 1
    assert fixed["request_retry_count"] == 0
    assert state["formal_model_lifecycle_count_max"] == 2
    assert state["second_calibration_authorized"] is False
    assert state["third_lifecycle_authorized"] is False
    assert state["result_transfer_authorized"] is True
    assert state["transfer_method_selected"] is False
    assert state["next_task_authorized"] is False
    assert state["k2_authorized"] is False
    assert state["p8_3_i1_authorized"] is False

    completed = subprocess.run(
        ["bash", str(OFFLINE_RUNNER), str(tmp_path / "analysis")],
        cwd=ROOT,
        env={**os.environ, "P8_2_K1A_F1_R1_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    for line in (
        f"task_id={TASK_ID}",
        "offline_first=true",
        "npu_execution_authorized=conditional",
        "formal_model_lifecycle_count_max=2",
        "calibration_lifecycle_count_max=1",
        "fixed_l2_lifecycle_count_max=1",
        "pressure_request_count_exact=1",
        "request_count_min=3",
        "request_count_max=4",
        "net_gpu_free_delta_may_unlock_l2=false",
        "result_transfer_authorized=true",
        "transfer_method_selected=false",
        "next_task_authorized=false",
    ):
        assert line in completed.stdout

    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    artifacts = readiness["artifacts"]
    assert artifacts["current_server_handoff_task"] == (
        "p8_2_k1a_r5_f1_r6_logical_keyspace_restore_2026_0723"
    )
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r6_logical_keyspace_restore.yaml"
    )
    assert artifacts["current_p8_2_k1a_r5_f1_r1_runner"].endswith(
        OFFLINE_RUNNER.name
    )
    assert artifacts["current_p8_2_k1a_r5_f1_r1_l2_runner"].endswith(
        L2_RUNNER.name
    )
    assert artifacts["current_p8_2_k1a_r5_f1_r1_calibration_runner"].endswith(
        CALIBRATION_RUNNER.name
    )

    acceptance = readiness["acceptance"]
    assert acceptance["p8_2_k1a_r5_f1_r1_grade"] == (
        "red_p8_2_k1a_r5_f1_r1_fixed_pressure_target_lost"
    )
    assert acceptance["p8_2_k1a_r5_f1_r1_formal_model_lifecycle_count_actual"] == 2
    assert acceptance["p8_2_k1a_r5_f1_r1_conditional_npu_execution_authorized"] is False


def test_f1_r1_l2_wrapper_requires_the_exact_ready_analysis_candidate(
    tmp_path: Path,
) -> None:
    result = tmp_path / "result"
    base_env = {
        **os.environ,
        "P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS": "8128",
        "P8_2_K1A_AUDIT_ONLY": "1",
    }
    missing = subprocess.run(
        ["bash", str(L2_RUNNER), str(result)],
        cwd=ROOT,
        env=base_env,
        text=True,
        capture_output=True,
    )
    assert missing.returncode != 0
    assert "P8_2_K1A_F1_R1_ANALYSIS_ROOT" in missing.stderr

    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "grading_summary.json").write_text(
        __import__("json").dumps(
            {
                "server_grade": READY_GRADE,
                "formal_fixed_l2_candidate_allowed": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (analysis / "pressure_candidate.json").write_text(
        __import__("json").dumps(
            {
                "candidate_pressure_context_tokens": 8128,
                "candidate_output_tokens": 64,
                "candidate_is_fixed_not_search": True,
                "formal_fixed_l2_candidate_allowed": True,
                "candidate_uses_request_local_progress": True,
                "candidate_uses_gpu_free_pool_delta": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (analysis / "task_grade.txt").write_text(READY_GRADE + "\n", encoding="utf-8")
    ready = subprocess.run(
        ["bash", str(L2_RUNNER), str(result)],
        cwd=ROOT,
        env={**base_env, "P8_2_K1A_F1_R1_ANALYSIS_ROOT": str(analysis)},
        text=True,
        capture_output=True,
    )
    assert ready.returncode == 0, ready.stderr or ready.stdout
    for line in (
        "offline_ready_grade_verified=true",
        "fixed_pressure_context_tokens=8128",
        f"task_id={TASK_ID}",
        "lifecycle_count=1",
        "request_count_min=3",
        "request_count_max=4",
        "pressure_request_count_max=1",
        "npu_execution_authorized=true",
        "next_task_authorized=false",
    ):
        assert line in ready.stdout


def test_f1_r1_l2_wrapper_rejects_legacy_f1_ready_grade(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "task_grade.txt").write_text(
        "candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window\n",
        encoding="utf-8",
    )
    (analysis / "grading_summary.json").write_text(
        __import__("json").dumps(
            {
                "server_grade": (
                    "candidate_ready_p8_2_k1a_r5_f1_exact_pressure_window"
                ),
                "formal_fixed_l2_candidate_allowed": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (analysis / "pressure_candidate.json").write_text(
        __import__("json").dumps(
            {
                "candidate_pressure_context_tokens": 8128,
                "candidate_output_tokens": 64,
                "candidate_is_fixed_not_search": True,
                "formal_fixed_l2_candidate_allowed": True,
                "candidate_uses_request_local_progress": False,
                "candidate_uses_gpu_free_pool_delta": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        ["bash", str(L2_RUNNER), str(tmp_path / "result")],
        cwd=ROOT,
        env={
            **os.environ,
            "P8_2_K1A_FIXED_PRESSURE_CONTEXT_TOKENS": "8128",
            "P8_2_K1A_F1_R1_ANALYSIS_ROOT": str(analysis),
            "P8_2_K1A_AUDIT_ONLY": "1",
        },
        text=True,
        capture_output=True,
    )
    assert completed.returncode != 0
