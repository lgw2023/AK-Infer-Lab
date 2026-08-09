from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from tools.inference_contracts import analyze_torch_profiler_traces as analysis
from tools.inference_contracts import (
    run_deepseek_p6_3c_r3e_f1_profile_completion as runner,
)
from tools.inference_contracts import (
    run_deepseek_p6_3c_r3e_f1_a1_trace_reaggregation as reaggregation,
)
from tools.inference_contracts import (
    run_deepseek_p6_3c_r3e_f1_a2_causal_linkage as causal_linkage,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def test_f1_runs_only_the_two_missing_profiler_endpoints() -> None:
    assert runner.PROFILE_LIFECYCLE_IDS == ("profile_f1_01", "profile_f1_02")
    assert len(runner.LIFECYCLE_SCHEDULE) == 2
    assert runner.EXPECTED_ENGINE_REQUESTS == 20
    assert runner.EXPECTED_HTTP_REQUESTS == 6
    assert {row["config_id"] for row in runner.LIFECYCLE_SCHEDULE} == {
        "admission_on_t4096",
        "persistent_on_t128",
    }


def test_trace_analyzer_streams_gzip_and_groups_device_categories(
    tmp_path: Path,
) -> None:
    root = tmp_path / "profile"
    root.mkdir()
    events = [
        {
            "name": "process_labels",
            "ph": "M",
            "pid": 7,
            "args": {"labels": "NPU 0"},
        },
        {
            "name": "HcomAllReduce",
            "cat": "kernel",
            "ph": "X",
            "pid": 7,
            "dur": 12.0,
            "args": {},
        },
        {
            "name": "GroupedMatmul",
            "cat": "kernel",
            "ph": "X",
            "pid": 7,
            "dur": 28.0,
            "args": {},
        },
        {
            "name": "aten::add",
            "cat": "cpu_op",
            "ph": "X",
            "pid": 99,
            "dur": 100.0,
            "args": {},
        },
    ]
    with gzip.open(root / "worker.pt.trace.json.gz", "wt", encoding="utf-8") as handle:
        json.dump({"traceEvents": events}, handle)

    result = analysis.analyze_trace_roots({"profile_f1_01": root})

    assert result["profiler_complete"] is True
    assert result["lifecycle_summaries"][0]["strong_device_event_count"] == 2
    categories = {
        row["op_category"]: row
        for row in result["category_rows"]
        if row["evidence_domain"] == "actual_device_kernel"
    }
    assert categories["collective_communication"]["summed_duration_us"] == 12.0
    assert categories["matmul_or_moe"]["summed_duration_us"] == 28.0


def test_device_analysis_timeline_is_not_reported_as_actual_kernel() -> None:
    free = {
        "name": "Free",
        "ph": "X",
        "pid": 7,
        "dur": 12.0,
        "args": {},
    }
    kernel = {
        "name": "HcomAllReduce",
        "cat": "kernel",
        "ph": "X",
        "pid": 7,
        "dur": 12.0,
        "args": {},
    }

    assert analysis.event_domain(free, {"7"}) == (
        "device_analysis_timeline",
        "derived_timeline_name",
    )
    assert analysis.event_domain(kernel, {"7"}) == (
        "actual_device_kernel",
        "trace_category",
    )


def test_trace_view_bare_array_preserves_evidence_domains_and_attention(
    tmp_path: Path,
) -> None:
    root = tmp_path / "profile"
    trace_dir = root / "dp0_tp0_rank0_123_ascend_pt" / "ASCEND_PROFILER_OUTPUT"
    trace_dir.mkdir(parents=True)
    events = [
        {
            "name": "Dequeue@HcclAllGather",
            "ph": "X",
            "ts": 1.0,
            "dur": 10.0,
            "args": {},
        },
        {
            "name": "_C_ascend::npu_sparse_attn_sharedkv",
            "ph": "X",
            "ts": 12.0,
            "dur": 20.0,
            "args": {},
        },
        {
            "name": "npu_fx_compiler inference",
            "ph": "X",
            "ts": 33.0,
            "dur": 30.0,
            "args": {},
        },
        {
            "name": "aclnnMatmul_MatMulV3",
            "ph": "X",
            "ts": 64.0,
            "dur": 40.0,
            "args": {},
        },
    ]
    (trace_dir / "trace_view.json").write_text(json.dumps(events), encoding="utf-8")

    result = analysis.analyze_trace_roots(
        {"profile_f1_01": root}, expected_ranks_per_lifecycle=1
    )

    inventory = result["trace_inventory"][0]
    assert inventory["top_level_schema"] == "bare_event_array"
    assert inventory["parse_complete"] is True
    assert inventory["rank_id"] == "0"
    assert inventory["runtime_or_queue_event_count"] == 1
    assert inventory["host_framework_event_count"] == 2
    assert inventory["name_inferred_event_count"] == 1
    attention = [
        row for row in result["category_rows"] if row["op_category"] == "attention"
    ]
    assert attention[0]["evidence_domain"] == "host_framework_range"
    compiler = [
        row
        for row in result["category_rows"]
        if row["op_category"] == "compiler_or_graph"
    ]
    assert compiler[0]["evidence_domain"] == "host_framework_range"


def test_event_limit_is_disclosed_as_incomplete(tmp_path: Path) -> None:
    root = tmp_path / "profile"
    root.mkdir()
    (root / "trace_view.json").write_text(
        json.dumps(
            [
                {"name": "aclnnMatmul", "ph": "X", "dur": 1.0, "args": {}},
                {"name": "aclnnMatmul", "ph": "X", "dur": 1.0, "args": {}},
            ]
        ),
        encoding="utf-8",
    )

    result = analysis.analyze_trace_roots(
        {"profile_f1_01": root}, max_events_per_trace=1
    )

    assert result["profiler_complete"] is False
    assert result["trace_inventory"][0]["event_limit_reached"] is True
    assert result["trace_inventory"][0]["parse_complete"] is False


def test_source_validation_accepts_completed_host_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "r3e_host_attribution.json").write_text(
        json.dumps(
            {
                "host_timing_complete": True,
                "mixed_engine_pipeline_fraction_at_least_0_80": True,
                "persistent_mixed_pipeline_target_insensitive": True,
            }
        ),
        encoding="utf-8",
    )
    (source / "environment_and_hashes.json").write_text(
        json.dumps({"task_id": runner.SOURCE_TASK_ID}), encoding="utf-8"
    )
    _write_tsv(
        source / "lifecycle_summary.tsv",
        [
            {
                "lifecycle_id": lifecycle_id,
                "lifecycle_exit_code": "0",
                "cleanup_status": "clean",
            }
            for lifecycle_id in ("host_01", "host_02", "host_03")
        ],
    )
    _write_tsv(
        source / "r3e_mechanism_cells.tsv",
        [
            {
                "lifecycle_id": lifecycle_id,
                "mechanism_contract_complete": "True",
            }
            for lifecycle_id in ("host_01", "host_02", "host_03")
        ],
    )
    _write_tsv(
        source / "r3e_host_phase_summary.tsv",
        [{"lifecycle_id": "host_01", "step_class": "mixed_prefill_decode"}],
    )

    evidence = runner.validate_source_host_evidence(source)

    assert evidence["source_host_evidence_complete"] is True
    assert evidence["source_result_overwritten"] is False


def test_f1_uses_vllm_profile_api_after_warmup_not_msprof_wrapper() -> None:
    base_mode = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh"
    ).read_text(encoding="utf-8")
    staged_driver = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r3b_chunk_budget.py"
    ).read_text(encoding="utf-8")
    f1_mode = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r3e_f1_mode.sh"
    ).read_text(encoding="utf-8")

    assert "--profiler-config" in base_mode
    assert "vllm_torch_profile_api" in base_mode
    assert 'profile_control("start")' in staged_driver
    assert 'profile_control("stop")' in staged_driver
    assert "P6_3C_DIAGNOSTIC_MSPROF=0" in f1_mode
    assert "P6_3C_PROFILE_API_ENABLED=1" in f1_mode


def test_a1_reaggregates_completed_source_without_overwriting_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "grading_inputs.json").write_text(
        json.dumps(
            {
                "task_id": reaggregation.SOURCE_TASK_ID,
                "evidence_status": "complete",
                "profiler_complete": True,
            }
        ),
        encoding="utf-8",
    )
    (source / "environment_and_hashes.json").write_text("{}", encoding="utf-8")
    _write_tsv(
        source / "lifecycle_summary.tsv",
        [
            {
                "lifecycle_id": lifecycle_id,
                "lifecycle_exit_code": "0",
                "cleanup_status": "clean",
            }
            for lifecycle_id in reaggregation.LIFECYCLE_IDS
        ],
    )
    _write_tsv(
        source / "r3e_mechanism_cells.tsv",
        [
            {
                "lifecycle_id": lifecycle_id,
                "config_id": reaggregation.EXPECTED_CONFIGS[lifecycle_id],
                "relevant_step_count": "5",
                "prefill_chunk_count": "2",
                "pressure_chunk_count": "1",
                "running_prefill_pressure_step_count": "0",
                "prefill_chunk_sizes": "4096,8185",
                "mechanism_contract_complete": "True",
            }
            for lifecycle_id in reaggregation.LIFECYCLE_IDS
        ],
    )
    _write_tsv(
        source / "r3e_f1_profile_control_summary.tsv",
        [
            {
                "lifecycle_id": lifecycle_id,
                "profile_start_stop_complete": "True",
            }
            for lifecycle_id in reaggregation.LIFECYCLE_IDS
        ],
    )
    (source / "resource_recovery_summary.json").write_text(
        json.dumps({"keep_alive_restored_exact": True}), encoding="utf-8"
    )
    (source / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    for lifecycle_id in reaggregation.LIFECYCLE_IDS:
        trace_dir = (
            source
            / "lifecycles"
            / lifecycle_id
            / "runtime/torch_profiler/dp0_rank0_1_ascend_pt/ASCEND_PROFILER_OUTPUT"
        )
        trace_dir.mkdir(parents=True)
        (trace_dir / "trace_view.json").write_text(
            json.dumps(
                [
                    {
                        "name": "aclnnMatmul_MatMulV3",
                        "cat": "kernel",
                        "ph": "X",
                        "ts": 1.0,
                        "dur": 2.0,
                        "args": {},
                    }
                ]
            ),
            encoding="utf-8",
        )

    before = reaggregation.source_evidence_manifest(source)
    output = tmp_path / "derived"
    grading = reaggregation.reaggregate(
        source,
        output,
        expected_ranks=1,
        top_n_ops=10,
        max_events_per_trace=None,
        trace_workspace=None,
    )

    assert grading["evidence_status"] == "complete"
    assert reaggregation.source_evidence_manifest(source) == before
    manifest = json.loads(
        (output / "candidate_manifest.server_local.json").read_text(encoding="utf-8")
    )
    assert manifest["candidate_total_bytes"] <= 70 * 1024
    assert manifest["transfer_method_selected"] is False

    adaptive = output / "adaptive_execution_review.json"
    adaptive.write_text(
        json.dumps({"task_id": reaggregation.TASK_ID, "server_note": "final"}) + "\n",
        encoding="utf-8",
    )
    refreshed = reaggregation.refresh_candidate_manifest(output)
    adaptive_row = next(
        row for row in refreshed["files"] if row["path"] == adaptive.name
    )
    assert adaptive_row["bytes"] == adaptive.stat().st_size
    assert adaptive_row["sha256"] == reaggregation._sha256(adaptive)  # noqa: SLF001


def _write_scheduler_trace(root: Path, lifecycle_id: str) -> None:
    trace_dir = root / "lifecycles" / lifecycle_id / "runtime/scheduler_trace"
    trace_dir.mkdir(parents=True, exist_ok=True)
    context = f"{lifecycle_id}:1"
    rows = [
        {
            "event": "scheduler_step",
            "timing_context_id": context,
            "step_index": 1,
            "timestamp_ns": 1_000_000,
            "monotonic_ns": 1_000_000,
            "resident_decode_tokens": 8,
            "injected_prefill_tokens": 128,
        },
        {
            "event": "executor_execute_submit",
            "timing_context_id": context,
            "submit_start_monotonic_ns": 100_000,
        },
        {
            "event": "executor_execute_complete",
            "timing_context_id": context,
            "executor_complete_monotonic_ns": 300_000,
        },
        {
            "event": "scheduler_update_complete",
            "timing_context_id": context,
            "update_start_monotonic_ns": 290_000,
        },
    ]
    (trace_dir / "trace.1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def test_a2_aligns_scheduler_steps_and_finds_cross_domain_correlation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "grading_inputs.json").write_text(
        json.dumps(
            {
                "task_id": reaggregation.SOURCE_TASK_ID,
                "evidence_status": "complete",
                "profiler_complete": True,
            }
        ),
        encoding="utf-8",
    )
    (source / "environment_and_hashes.json").write_text("{}", encoding="utf-8")
    _write_tsv(
        source / "lifecycle_summary.tsv",
        [
            {
                "lifecycle_id": lifecycle_id,
                "lifecycle_exit_code": "0",
                "cleanup_status": "clean",
            }
            for lifecycle_id in reaggregation.LIFECYCLE_IDS
        ],
    )
    _write_tsv(
        source / "r3e_mechanism_cells.tsv",
        [
            {
                "lifecycle_id": lifecycle_id,
                "config_id": reaggregation.EXPECTED_CONFIGS[lifecycle_id],
                "relevant_step_count": "1",
                "prefill_chunk_count": "1",
                "pressure_chunk_count": "1",
                "running_prefill_pressure_step_count": "1",
                "prefill_chunk_sizes": "128",
                "mechanism_contract_complete": "True",
            }
            for lifecycle_id in reaggregation.LIFECYCLE_IDS
        ],
    )
    _write_tsv(
        source / "r3e_f1_profile_control_summary.tsv",
        [
            {
                "lifecycle_id": lifecycle_id,
                "profile_start_stop_complete": "True",
            }
            for lifecycle_id in reaggregation.LIFECYCLE_IDS
        ],
    )
    (source / "resource_recovery_summary.json").write_text(
        json.dumps({"keep_alive_restored_exact": True}), encoding="utf-8"
    )
    (source / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")

    events = [
        {
            "name": "process_labels",
            "ph": "M",
            "pid": 7,
            "args": {"labels": "NPU 0"},
        },
        {
            "name": "aten::matmul",
            "cat": "cpu_op",
            "ph": "X",
            "pid": 99,
            "ts": 120.0,
            "dur": 10.0,
            "args": {"correlation_id": 42},
        },
        {
            "name": "Dequeue@HcclAllReduce",
            "ph": "X",
            "pid": 99,
            "ts": 150.0,
            "dur": 20.0,
            "args": {"correlation_id": 42},
        },
        {
            "name": "HcomAllReduce",
            "cat": "kernel",
            "ph": "X",
            "pid": 7,
            "ts": 180.0,
            "dur": 30.0,
            "args": {"correlation_id": 42},
        },
        {
            "name": "Communication(Not Overlapped)",
            "ph": "X",
            "pid": 7,
            "ts": 215.0,
            "dur": 20.0,
            "args": {},
        },
    ]
    for lifecycle_id in reaggregation.LIFECYCLE_IDS:
        _write_scheduler_trace(source, lifecycle_id)
        trace_dir = (
            source
            / "lifecycles"
            / lifecycle_id
            / "runtime/torch_profiler/dp0_rank0_1_ascend_pt/ASCEND_PROFILER_OUTPUT"
        )
        trace_dir.mkdir(parents=True)
        (trace_dir / "trace_view.json").write_text(
            json.dumps(events), encoding="utf-8"
        )

    source_a1 = tmp_path / "source_a1"
    source_a1.mkdir()
    (source_a1 / "scientific_outcome.json").write_text(
        json.dumps(
            {
                "task_id": reaggregation.TASK_ID,
                "cross_rank_trace_complete": True,
                "scientific_outcome": (
                    "descriptive_cross_rank_execution_path_complete_"
                    "causal_bottleneck_unresolved"
                ),
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "a2"
    grading = causal_linkage.analyze(
        source,
        source_a1,
        output,
        expected_ranks=1,
        trace_workspace=None,
        max_events_per_trace=None,
    )

    assert grading["evidence_status"] == "complete"
    assert grading["clock_alignment_complete"] is True
    assert grading["step_rank_coverage_complete"] is True
    assert grading["dependency_linkage_available"] is True
    review = json.loads(
        (output / "bottleneck_hypothesis_review.json").read_text(encoding="utf-8")
    )
    assert review["host_runtime_device_link_value_count"] == 2
    paths = list(
        csv.DictReader(
            (output / "step_rank_path_summary.tsv").open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    assert any(
        row["execution_role"] == "analysis_communication_not_overlapped"
        for row in paths
    )
    manifest = json.loads(
        (output / "candidate_manifest.server_local.json").read_text(encoding="utf-8")
    )
    assert manifest["manifest_generated_after_adaptive_review"] is True
    assert manifest["candidate_total_bytes"] <= 70 * 1024
