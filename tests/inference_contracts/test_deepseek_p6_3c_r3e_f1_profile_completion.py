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
        if row["evidence_domain"] == "device_kernel"
    }
    assert categories["collective_communication"]["summed_duration_us"] == 12.0
    assert categories["matmul_or_moe"]["summed_duration_us"] == 28.0


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
