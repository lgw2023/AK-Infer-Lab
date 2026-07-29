from __future__ import annotations

import csv
from contextlib import contextmanager
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (
    run_deepseek_p6_3c_r1_scheduler_pressure as base,
)


TASK_ID = "p6_3c_r2_chunked_prefill_capacity_calibrated_2026_0729_run01"
MAX_MODEL_LEN = 12288
MAX_NUM_BATCHED_TOKENS = 12288
MAX_NUM_SEQS = 2
CELLS = (
    {
        "cell_id": "no_pressure_4k_4k",
        "prompt_tokens": (4096, 4096),
        "request_roles": ("peer_a", "peer_b"),
        "total_prefill_tokens": 8192,
        "pressure": False,
    },
    {
        "cell_id": "asymmetric_pressure_10k_6k",
        "prompt_tokens": (10240, 6144),
        "request_roles": ("long", "short"),
        "total_prefill_tokens": 16384,
        "pressure": True,
    },
    {
        "cell_id": "symmetric_pressure_8k_8k",
        "prompt_tokens": (8192, 8192),
        "request_roles": ("peer_a", "peer_b"),
        "total_prefill_tokens": 16384,
        "pressure": True,
    },
)
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab.yaml"
)
STARTUP_FIELDS = (
    "lifecycle_id",
    "track",
    "mode",
    "server_ready",
    "server_ready_exit_code",
    "startup_failure_class",
    "expected_max_model_len",
    "expected_max_num_batched_tokens",
    "expected_max_num_seqs",
    "available_kv_cache_gib",
    "required_kv_cache_gib",
    "estimated_max_model_len",
    "gpu_kv_cache_tokens",
    "model_weight_gb_max_observed",
    "maximum_concurrency",
)

def build_run_plan() -> dict[str, list[dict[str, Any]]]:
    plan: dict[str, list[dict[str, Any]]] = {}
    for track in base.TRACKS:
        repeats = 1 if track == "mechanism" else 3
        warmup_id = f"p6_3c_r2_{track}_warmup"
        batches: list[dict[str, Any]] = [
            {
                "track": track,
                "phase": "warmup",
                "batch_id": warmup_id,
                "request_id": warmup_id,
                "cell_id": "warmup_4k",
                "repeat_index": 1,
                "prompt_tokens": [4096],
                "request_roles": ["warmup"],
                "total_prefill_tokens": 4096,
                "pressure": False,
                "output_tokens": 64,
            }
        ]
        for cell in CELLS:
            for repeat_index in range(1, repeats + 1):
                batch_id = (
                    f"p6_3c_r2_{track}_{cell['cell_id']}_r{repeat_index:02d}"
                )
                batches.append(
                    {
                        "track": track,
                        "phase": "measured",
                        "batch_id": batch_id,
                        "request_id": batch_id,
                        "cell_id": cell["cell_id"],
                        "repeat_index": repeat_index,
                        "prompt_tokens": list(cell["prompt_tokens"]),
                        "request_roles": list(cell["request_roles"]),
                        "total_prefill_tokens": cell["total_prefill_tokens"],
                        "pressure": cell["pressure"],
                        "output_tokens": 64,
                    }
                )
        plan[track] = batches
    return plan


def _mechanism_evidence(
    artifact_dir: Path,
    schedule: list[dict[str, Any]],
    plan: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summaries: list[dict[str, Any]] = []
    request_rows: list[dict[str, Any]] = []
    for lifecycle in [item for item in schedule if item["track"] == "mechanism"]:
        lifecycle_dir = artifact_dir / "lifecycles" / lifecycle["lifecycle_id"]
        trace_rows = base._read_trace_rows(lifecycle_dir)
        installed = any(row.get("event") == "observer_installed" for row in trace_rows)
        for batch in [
            item for item in plan["mechanism"] if item["phase"] == "measured"
        ]:
            request_marker = f"cmpl-{batch['request_id']}-"
            selected_steps = [
                row
                for row in trace_rows
                if row.get("event") == "scheduler_step"
                and request_marker in json.dumps(row, separators=(",", ":"))
            ]
            summary = base.summarize_scheduler_rows(selected_steps)
            partial_count = int(summary["partial_prefill_request_count"])
            waiting_observed = any(
                any(
                    request_marker in request_id
                    for request_id in (
                        (step.get("waiting_order_before") or [])
                        + (step.get("waiting_order_after") or [])
                    )
                )
                for step in selected_steps
            )
            summaries.append(
                {
                    "lifecycle_id": lifecycle["lifecycle_id"],
                    "mode": lifecycle["mode"],
                    "cell_id": batch["cell_id"],
                    "pressure": bool(batch["pressure"]),
                    "observer_installed": installed,
                    "scheduler_step_count": summary["scheduler_step_count"],
                    "prefill_request_count": summary["prefill_request_count"],
                    "partial_prefill_request_count": partial_count,
                    "waiting_observed": waiting_observed,
                    "chunking_observed": partial_count > 0,
                }
            )
            for row in summary["request_rows"]:
                request_rows.append(
                    {
                        "lifecycle_id": lifecycle["lifecycle_id"],
                        "mode": lifecycle["mode"],
                        "cell_id": batch["cell_id"],
                        **row,
                    }
                )

    off_rows = [row for row in summaries if row["mode"] == base.MODES[0]]
    on_rows = [row for row in summaries if row["mode"] == base.MODES[1]]
    low_pressure_cell = next(
        cell["cell_id"] for cell in CELLS if not cell["pressure"]
    )
    off_no_partial = len(off_rows) == len(CELLS) and all(
        row["partial_prefill_request_count"] == 0 for row in off_rows
    )
    on_pressure_chunked = all(
        any(
            row["cell_id"] == cell["cell_id"]
            and row["partial_prefill_request_count"] > 0
            for row in on_rows
        )
        for cell in CELLS
        if cell["pressure"]
    )
    low_pressure_no_partial = all(
        any(
            row["cell_id"] == low_pressure_cell
            and row["mode"] == mode
            and row["partial_prefill_request_count"] == 0
            for row in summaries
        )
        for mode in base.MODES
    )
    observer_exact = len(summaries) == len(CELLS) * 2 and all(
        row["observer_installed"] for row in summaries
    )
    return (
        {
            "track": "mechanism",
            "cell_summaries": summaries,
            "observer_installed_both_modes": observer_exact,
            "off_prefill_partial_absent_all_cells": off_no_partial,
            "on_prefill_partial_present_both_pressure_cells": on_pressure_chunked,
            "low_pressure_partial_absent_both_modes": low_pressure_no_partial,
            "mechanism_gate_complete": (
                observer_exact
                and off_no_partial
                and on_pressure_chunked
                and low_pressure_no_partial
            ),
            "claim_boundary": (
                "direct_scheduler_mechanism_evidence_in_three_"
                "capacity_calibrated_frozen_cells_only"
            ),
        },
        request_rows,
    )


def _mapped_grade(grade: str) -> str:
    return {
        (
            "candidate_green_p6_3c_r1_chunked_prefill_"
            "scheduler_pressure_matched_ab"
        ): (
            "candidate_green_p6_3c_r2_chunked_prefill_"
            "capacity_calibrated_matched_ab"
        ),
        "red_p6_3c_r1_scheduler_pressure_no_success": (
            "red_p6_3c_r2_scheduler_pressure_no_success"
        ),
        "yellow_p6_3c_r1_scheduler_pressure_partial": (
            "yellow_p6_3c_r2_scheduler_pressure_partial"
        ),
        "red_p6_3c_r1_scheduler_pressure_evidence_incomplete": (
            "red_p6_3c_r2_scheduler_pressure_evidence_incomplete"
        ),
    }.get(grade, grade)


def _startup_rows(artifact_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for lifecycle in base.LIFECYCLE_SCHEDULE:
        path = (
            artifact_dir
            / "lifecycles"
            / lifecycle["lifecycle_id"]
            / "runtime"
            / "startup_resource_summary.json"
        )
        if not path.is_file():
            continue
        rows.append(
            {
                "lifecycle_id": lifecycle["lifecycle_id"],
                "track": lifecycle["track"],
                "mode": lifecycle["mode"],
                **json.loads(path.read_text(encoding="utf-8")),
            }
        )
    return rows


def _repair_identity_exact(artifact_dir: Path) -> bool:
    identities = []
    resolved_repair_values = []
    for lifecycle in base.LIFECYCLE_SCHEDULE:
        lifecycle_dir = artifact_dir / "lifecycles" / lifecycle["lifecycle_id"]
        identity = lifecycle_dir / "repair_identity.tsv"
        resolved = lifecycle_dir / "runtime" / "resolved_scheduler_config.json"
        if identity.is_file():
            identities.append(identity.read_text(encoding="utf-8"))
        if resolved.is_file():
            resolved_repair_values.append(
                json.loads(resolved.read_text(encoding="utf-8")).get(
                    "shared_hybrid_kv_repair_enabled"
                )
            )
    return (
        len(identities) == len(base.LIFECYCLE_SCHEDULE)
        and len(set(identities)) == 1
        and "disabled" not in identities[0]
        and resolved_repair_values == [True] * len(base.LIFECYCLE_SCHEDULE)
    )


def _write_result_summary(
    artifact_dir: Path,
    grade: str,
    grading: dict[str, Any],
    mechanism: dict[str, Any],
    mode_cell_rows: list[dict[str, Any]],
) -> None:
    asymmetric_rows = [
        row
        for row in mode_cell_rows
        if row.get("cell_id") == "asymmetric_pressure_10k_6k"
    ]
    startup_rows = _startup_rows(artifact_dir)
    first_startup = startup_rows[0] if startup_rows else {}
    lines = [
        f"# {TASK_ID} 结果摘要",
        "",
        f"- server grade: `{_mapped_grade(grade)}`",
        "- 原 P6.3C blocked 与 P6.3C-R1 RED 均保持不变，本任务是独立 R2 结果链。",
        (
            "- 共同冻结环境：`max_model_len=12288`、"
            "`max_num_batched_tokens=12288`、`max_num_seqs=2`、"
            "Prefix Cache 显式关闭、两侧加载同一 validated hybrid-KV deferred repair。"
        ),
        (
            f"- 请求：`{grading['successful_request_count']}/90` 成功；"
            f"机制门：`{mechanism['mechanism_gate_complete']}`；"
            f"keep-alive 精确恢复：`{grading['keep_alive_restore_exact']}`。"
        ),
        (
            "- 首个启动资源摘要："
            f"ready=`{first_startup.get('server_ready')}`，"
            f"available KV=`{first_startup.get('available_kv_cache_gib')}` GiB，"
            f"required KV=`{first_startup.get('required_kv_cache_gib')}` GiB，"
            f"class=`{first_startup.get('startup_failure_class')}`。"
        ),
        "",
        "## 机制轨道",
        "",
        (
            "- Off 三个 cell 均无 partial prefill："
            f"`{mechanism['off_prefill_partial_absent_all_cells']}`。"
        ),
        (
            "- On 两个压力 cell 均观测到 partial prefill："
            f"`{mechanism['on_prefill_partial_present_both_pressure_cells']}`。"
        ),
        (
            "- 4K+4K 两侧均无 partial prefill："
            f"`{mechanism['low_pressure_partial_absent_both_modes']}`。"
        ),
        "",
        "## 性能轨道",
        "",
        "- 采用 Off→On→On→Off 四个 fresh lifecycle；observer 与 profiler 均关闭。",
    ]
    for row in asymmetric_rows:
        lines.append(
            f"- `{row['mode']}` 10K+6K 短请求 TTFT mean="
            f"`{row.get('short_request_ttft_ms_mean')}` ms，"
            "仅作冻结样本内描述。"
        )
    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- R2 缩小共同容量边界是对 R1 启动 RED 的修复，不回写或重判 R1。",
            "- shared hybrid-KV repair 在两侧相同，不能把 R2 与 R1 的启动差异归因为单一因素。",
            "- 候选结果须由开发机复核；不声明普遍收益、统计显著性或生产吞吐。",
            "- 完整清单得到用户明确传输渠道选择前，不外发任何文件。",
            "",
        ]
    )
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def _finalize_artifacts_configured(artifact_dir: Path) -> dict[str, Any]:
    startup_rows = _startup_rows(artifact_dir)
    base._write_tsv(
        artifact_dir / "startup_resource_summary.tsv",
        startup_rows,
        list(STARTUP_FIELDS),
    )
    grading = base.finalize_artifacts(artifact_dir)
    repair_exact = _repair_identity_exact(artifact_dir)
    startup_complete = (
        len(startup_rows) == len(base.LIFECYCLE_SCHEDULE)
        and all(row.get("server_ready") is True for row in startup_rows)
    )
    grade = _mapped_grade(str(grading["server_grade"]))
    if grade != "red_cleanup_incomplete" and any(
        row.get("startup_failure_class") == "insufficient_kv_cache_capacity"
        for row in startup_rows
    ) and int(grading.get("successful_request_count") or 0) == 0:
        grade = "red_p6_3c_r2_startup_kv_capacity_no_success"
    elif grade.startswith("candidate_green") and not (
        startup_complete and repair_exact
    ):
        grade = "red_p6_3c_r2_scheduler_pressure_evidence_incomplete"

    grading.update(
        {
            "task_id": TASK_ID,
            "server_grade": grade,
            "parent_p6_3c_r1_grade_preserved": (
                "red_p6_3c_r1_scheduler_pressure_no_success"
            ),
            "startup_resource_summary_count": len(startup_rows),
            "startup_resource_gate_complete": startup_complete,
            "shared_hybrid_kv_repair_exact_all_lifecycles": repair_exact,
        }
    )
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    environment_path = artifact_dir / "environment_and_hashes.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    environment.update(
        {
            "task_id": TASK_ID,
            "workload_path": WORKLOAD_RELATIVE_PATH,
            "workload_sha256": base._optional_repo_sha256(WORKLOAD_RELATIVE_PATH),
            "runner_sha256": base._sha256_path(Path(__file__)),
            "base_runner_sha256": base._optional_repo_sha256(
                "tools/inference_contracts/"
                "run_deepseek_p6_3c_r1_scheduler_pressure.py"
            ),
            "max_model_len": MAX_MODEL_LEN,
            "max_num_batched_tokens": MAX_NUM_BATCHED_TOKENS,
            "max_num_seqs": MAX_NUM_SEQS,
            "shared_hybrid_kv_repair_enabled": True,
        }
    )
    environment_path.write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    mechanism = json.loads(
        (artifact_dir / "mechanism_scheduler_summary.json").read_text(
            encoding="utf-8"
        )
    )
    mode_rows = []
    with (artifact_dir / "performance_mode_cell_summary.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        mode_rows = list(csv.DictReader(handle, delimiter="\t"))
    _write_result_summary(artifact_dir, grade, grading, mechanism, mode_rows)
    if grade.startswith("candidate_green"):
        (artifact_dir / "first_failure_excerpt.txt").write_text(
            "none\n", encoding="utf-8"
        )
    return grading


R2_BOUNDED_CANDIDATES = (
    *base.BOUNDED_CANDIDATES[:-2],
    "startup_resource_summary.tsv",
    *base.BOUNDED_CANDIDATES[-2:],
)


@contextmanager
def _configured_base():
    replacements = {
        "TASK_ID": TASK_ID,
        "CELLS": CELLS,
        "build_run_plan": build_run_plan,
        "_mechanism_evidence": _mechanism_evidence,
        "_write_result_summary": _write_result_summary,
        "BOUNDED_CANDIDATES": R2_BOUNDED_CANDIDATES,
    }
    originals = {name: getattr(base, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(base, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(base, name, value)


def prepare_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    with _configured_base():
        return base.prepare_artifacts(source_payload, artifact_dir, model_name)


def execute_mode(
    artifact_dir: Path,
    lifecycle_dir: Path,
    base_url: str,
    server_pid: int,
    track: str,
    mode: str,
) -> int:
    with _configured_base():
        return base.execute_mode(
            artifact_dir,
            lifecycle_dir,
            base_url,
            server_pid,
            track,
            mode,
        )


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    with _configured_base():
        return _finalize_artifacts_configured(artifact_dir)


def package_results(artifact_dir: Path) -> dict[str, Any]:
    with _configured_base():
        return base.package_results(artifact_dir)


def main(argv: list[str] | None = None) -> int:
    args = base.parse_args(argv)
    if args.command == "prepare":
        prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run-mode":
        return execute_mode(
            args.artifact_dir,
            args.lifecycle_dir,
            args.base_url,
            args.server_pid,
            args.track,
            args.mode,
        )
    if args.command == "finalize":
        grading = finalize_artifacts(args.artifact_dir)
        return 0 if str(grading["server_grade"]).startswith("candidate_green") else 2
    if args.command == "package":
        package_results(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
