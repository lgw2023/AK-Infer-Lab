from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from tools.inference_contracts import analyze_torch_profiler_traces as analysis
from tools.inference_contracts import (
    run_deepseek_p6_3c_r3e_f1_profile_completion as runner,
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
    assert result["lifecycle_summaries"][0]["device_event_count"] == 2
    categories = {
        row["op_category"]: row for row in result["category_rows"]
    }
    assert categories["collective_communication"]["summed_device_duration_us"] == 12.0
    assert categories["matmul_or_moe"]["summed_device_duration_us"] == 28.0


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
