from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_ARTIFACT_ROOT = Path("工作记录与进度笔记本/runtime_trace_smokes")
DEFAULT_SOURCE_RUN_ID = "runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026"
DEFAULT_RUN_ID = "runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027"
MAIL_ATTACHMENT_LIMIT_BYTES = 70 * 1024
POLICY = "raw_counter_readout_no_benchmark_hit_rate_or_bottleneck_claim"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize controlled vLLM msprof request-device aggregate outputs into small readout files."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--source-run-id", default=DEFAULT_SOURCE_RUN_ID)
    parser.add_argument(
        "--source-artifact-dir",
        type=Path,
        default=None,
        help="Source P1.26 artifact directory. Defaults to runtime_trace_smokes/<source-run-id>.",
    )
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=None,
        help="Directory containing P1.26 final_analysis TSV files.",
    )
    parser.add_argument(
        "--generated-token-summary",
        type=Path,
        default=None,
        help="Path to generated_token_length_summary.tsv.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to runtime_trace_smokes/<run-id>.",
    )
    parser.add_argument("--top-op-limit", type=int, default=40)
    parser.add_argument("--metric-limit", type=int, default=60)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_artifact_dir = args.source_artifact_dir or (DEFAULT_ARTIFACT_ROOT / args.source_run_id)
    analysis_dir = args.analysis_dir or (source_artifact_dir / "final_analysis")
    generated_token_summary = args.generated_token_summary or (
        source_artifact_dir / "generated_token_length_summary.tsv"
    )
    artifact_dir = args.artifact_dir or (DEFAULT_ARTIFACT_ROOT / args.run_id)

    result = summarize_controlled_replay(
        run_id=args.run_id,
        source_run_id=args.source_run_id,
        source_artifact_dir=source_artifact_dir,
        analysis_dir=analysis_dir,
        generated_token_summary=generated_token_summary,
        artifact_dir=artifact_dir,
        top_op_limit=args.top_op_limit,
        metric_limit=args.metric_limit,
    )
    return 0 if result["overall_status"] == "success" else 1


def summarize_controlled_replay(
    *,
    run_id: str,
    source_run_id: str,
    source_artifact_dir: Path,
    analysis_dir: Path,
    generated_token_summary: Path,
    artifact_dir: Path,
    top_op_limit: int = 40,
    metric_limit: int = 60,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)

    required_files = {
        "generated_token_length_summary": generated_token_summary,
        "prefix_cache_mode_request_delta": analysis_dir / "prefix_cache_mode_request_delta.tsv",
        "prefix_pair_candidate_delta": analysis_dir / "prefix_pair_candidate_delta.tsv",
        "request_top_op_type_duration": analysis_dir / "request_top_op_type_duration.tsv",
        "request_ai_core_metric_summary": analysis_dir / "request_ai_core_metric_summary.tsv",
    }
    missing_files = [str(path) for path in required_files.values() if not path.is_file()]

    generated_rows = read_tsv(generated_token_summary) if generated_token_summary.is_file() else []
    mode_delta_rows = read_tsv(required_files["prefix_cache_mode_request_delta"])
    pair_delta_rows = read_tsv(required_files["prefix_pair_candidate_delta"])
    top_op_rows = read_tsv(required_files["request_top_op_type_duration"])
    metric_rows = read_tsv(required_files["request_ai_core_metric_summary"])

    generated_status = summarize_generated_lengths(generated_rows)
    mode_delta_summary = summarize_mode_delta_groups(mode_delta_rows)
    pair_delta_summary = summarize_pair_delta_rows(pair_delta_rows)
    top_op_delta = summarize_top_op_deltas(top_op_rows, top_op_limit)
    metric_delta = summarize_metric_deltas(metric_rows, metric_limit)

    output_files = [
        write_tsv(artifact_dir / "controlled_replay_mode_delta_summary.tsv", mode_delta_summary),
        write_tsv(artifact_dir / "controlled_replay_pair_delta_summary.tsv", pair_delta_summary),
        write_tsv(artifact_dir / "controlled_replay_top_op_delta.tsv", top_op_delta),
        write_tsv(artifact_dir / "controlled_replay_ai_core_metric_delta.tsv", metric_delta),
    ]

    overall_status = "success" if not missing_files and generated_status["status"] == "fixed_64" else "failed"
    result = {
        "run_id": run_id,
        "source_run_id": source_run_id,
        "source_artifact_dir": str(source_artifact_dir),
        "analysis_dir": str(analysis_dir),
        "artifact_dir": str(artifact_dir),
        "overall_status": overall_status,
        "missing_files": missing_files,
        "generated_length_status": generated_status,
        "mode_delta_group_count": len(mode_delta_summary),
        "pair_delta_row_count": len(pair_delta_summary),
        "top_op_delta_row_count": len(top_op_delta),
        "metric_delta_row_count": len(metric_delta),
        "policy": POLICY,
    }
    result_path = artifact_dir / "controlled_replay_readout_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_files.append(result_path)
    output_files.append(write_summary(artifact_dir / "summary.txt", result, mode_delta_summary))
    output_files.append(write_mail_attachment_candidates(artifact_dir, output_files))
    return result


def summarize_generated_lengths(rows: list[dict[str, str]]) -> dict[str, Any]:
    mismatch_count = sum(int_value(row.get("generated_token_count_mismatch_count")) for row in rows)
    request_count = sum(int_value(row.get("request_count")) for row in rows)
    success_case_count = sum(int_value(row.get("success_case_count")) for row in rows)
    failed_case_count = sum(int_value(row.get("failed_case_count")) for row in rows)
    min_values = [int_value(row.get("min_generated_token_count")) for row in rows if row.get("min_generated_token_count")]
    max_values = [int_value(row.get("max_generated_token_count")) for row in rows if row.get("max_generated_token_count")]
    fixed_64 = (
        bool(rows)
        and mismatch_count == 0
        and failed_case_count == 0
        and all(value == 64 for value in min_values)
        and all(value == 64 for value in max_values)
    )
    return {
        "status": "fixed_64" if fixed_64 else "not_fixed_64",
        "mode_count": len(rows),
        "request_count": request_count,
        "success_case_count": success_case_count,
        "failed_case_count": failed_case_count,
        "generated_token_count_mismatch_count": mismatch_count,
        "min_generated_token_count": min(min_values) if min_values else "",
        "max_generated_token_count": max(max_values) if max_values else "",
    }


def summarize_mode_delta_groups(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[("all", "all")].append(row)
        grouped[("prompt_id", row.get("prompt_id", ""))].append(row)
        grouped[("prefix_reuse_group", row.get("prefix_reuse_group", ""))].append(row)

    summary = [summarize_mode_delta_group(scope, value, group_rows) for (scope, value), group_rows in grouped.items()]
    return sorted(summary, key=lambda row: (row["scope"], row["group_value"]))


def summarize_mode_delta_group(scope: str, group_value: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    deltas = [int_value(row.get("delta_total_duration_time_on_minus_off")) for row in rows]
    task_deltas = [int_value(row.get("delta_task_row_count_on_minus_off")) for row in rows]
    return {
        "scope": scope,
        "group_value": group_value,
        "request_count": len(rows),
        "on_task_row_count_sum": sum(int_value(row.get("on_task_row_count")) for row in rows),
        "off_task_row_count_sum": sum(int_value(row.get("off_task_row_count")) for row in rows),
        "delta_task_row_count_sum_on_minus_off": sum(task_deltas),
        "on_total_duration_time_sum": sum(int_value(row.get("on_total_duration_time")) for row in rows),
        "off_total_duration_time_sum": sum(int_value(row.get("off_total_duration_time")) for row in rows),
        "delta_total_duration_time_sum_on_minus_off": sum(deltas),
        "negative_duration_delta_request_count": sum(1 for value in deltas if value < 0),
        "positive_duration_delta_request_count": sum(1 for value in deltas if value > 0),
        "zero_duration_delta_request_count": sum(1 for value in deltas if value == 0),
        "negative_task_delta_request_count": sum(1 for value in task_deltas if value < 0),
        "positive_task_delta_request_count": sum(1 for value in task_deltas if value > 0),
        "policy": POLICY,
    }


def summarize_pair_delta_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        result.append(
            {
                "mode": row.get("mode", ""),
                "prefix_reuse_group": row.get("prefix_reuse_group", ""),
                "first_case_id": row.get("first_case_id", ""),
                "second_case_id": row.get("second_case_id", ""),
                "delta_task_row_count_second_minus_first": int_value(
                    row.get("delta_task_row_count_second_minus_first")
                ),
                "delta_total_duration_time_second_minus_first": int_value(
                    row.get("delta_total_duration_time_second_minus_first")
                ),
                "policy": "prefix_pair_candidate_delta_no_prefix_cache_hit_claim",
            }
        )
    return sorted(result, key=lambda row: (row["mode"], row["prefix_reuse_group"]))


def summarize_top_op_deltas(rows: list[dict[str, str]], limit: int) -> list[dict[str, Any]]:
    paired: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        paired[(row.get("case_id", ""), row.get("op_type", ""))][row.get("mode", "")] = row

    aggregate: dict[str, dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    for (_case_id, op_type), mode_rows in paired.items():
        on = mode_rows.get("msprof_prefix_cache_on")
        off = mode_rows.get("msprof_prefix_cache_off")
        if not on and not off:
            continue
        row = aggregate[op_type]
        row["op_type"] = op_type
        row["paired_case_count"] += 1
        row["on_task_row_count_sum"] += int_value((on or {}).get("task_row_count"))
        row["off_task_row_count_sum"] += int_value((off or {}).get("task_row_count"))
        row["on_total_duration_time_sum"] += int_value((on or {}).get("total_duration_time"))
        row["off_total_duration_time_sum"] += int_value((off or {}).get("total_duration_time"))

    result = []
    for row in aggregate.values():
        row = dict(row)
        row["delta_task_row_count_sum_on_minus_off"] = row["on_task_row_count_sum"] - row["off_task_row_count_sum"]
        row["delta_total_duration_time_sum_on_minus_off"] = (
            row["on_total_duration_time_sum"] - row["off_total_duration_time_sum"]
        )
        row["policy"] = POLICY
        result.append(row)
    return sorted(result, key=lambda row: abs(row["delta_total_duration_time_sum_on_minus_off"]), reverse=True)[
        :limit
    ]


def summarize_metric_deltas(rows: list[dict[str, str]], limit: int) -> list[dict[str, Any]]:
    numeric_columns = sorted(
        {
            key
            for row in rows
            for key, value in row.items()
            if key not in {"mode", "db_path", "case_id", "prompt_id", "prefix_reuse_group"}
            and value not in {"", None}
            and is_number(value)
        }
    )
    paired: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        paired[row.get("case_id", "")][row.get("mode", "")] = row

    result = []
    for metric_name in numeric_columns:
        on_sum = 0.0
        off_sum = 0.0
        paired_case_count = 0
        for mode_rows in paired.values():
            on = mode_rows.get("msprof_prefix_cache_on")
            off = mode_rows.get("msprof_prefix_cache_off")
            if not on and not off:
                continue
            paired_case_count += 1
            on_sum += float_value((on or {}).get(metric_name))
            off_sum += float_value((off or {}).get(metric_name))
        result.append(
            {
                "metric_name": metric_name,
                "paired_case_count": paired_case_count,
                "on_sum": round_number(on_sum),
                "off_sum": round_number(off_sum),
                "delta_sum_on_minus_off": round_number(on_sum - off_sum),
                "policy": POLICY,
            }
        )
    return sorted(result, key=lambda row: abs(float(row["delta_sum_on_minus_off"])), reverse=True)[:limit]


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> Path:
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_summary(path: Path, result: dict[str, Any], mode_delta_summary: list[dict[str, Any]]) -> Path:
    generated = result["generated_length_status"]
    all_delta = next((row for row in mode_delta_summary if row["scope"] == "all"), None)
    lines = [
        "## run_context",
        f"run_id={result['run_id']}",
        f"source_run_id={result['source_run_id']}",
        f"source_artifact_dir={result['source_artifact_dir']}",
        f"analysis_dir={result['analysis_dir']}",
        f"artifact_dir={result['artifact_dir']}",
        f"overall_status={result['overall_status']}",
        f"policy={result['policy']}",
        "",
        "## generated_length_status",
        "\t".join(f"{key}={value}" for key, value in generated.items()),
        "",
        "## aggregate_readout",
        f"mode_delta_group_count={result['mode_delta_group_count']}",
        f"pair_delta_row_count={result['pair_delta_row_count']}",
        f"top_op_delta_row_count={result['top_op_delta_row_count']}",
        f"metric_delta_row_count={result['metric_delta_row_count']}",
    ]
    if all_delta:
        lines.extend(
            [
                "",
                "## all_request_raw_delta",
                f"request_count={all_delta['request_count']}",
                f"delta_task_row_count_sum_on_minus_off={all_delta['delta_task_row_count_sum_on_minus_off']}",
                f"delta_total_duration_time_sum_on_minus_off={all_delta['delta_total_duration_time_sum_on_minus_off']}",
                f"negative_duration_delta_request_count={all_delta['negative_duration_delta_request_count']}",
                f"positive_duration_delta_request_count={all_delta['positive_duration_delta_request_count']}",
            ]
        )
    if result["missing_files"]:
        lines.extend(["", "## missing_files", *result["missing_files"]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_mail_attachment_candidates(artifact_dir: Path, paths: list[Path]) -> Path:
    rows = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        size_bytes = path.stat().st_size
        rows.append(
            {
                "path": str(path),
                "size_bytes": size_bytes,
                "line_count": text.count("\n"),
                "mail_ok": str(size_bytes <= MAIL_ATTACHMENT_LIMIT_BYTES).lower(),
            }
        )
    return write_tsv(artifact_dir / "mail_attachment_candidates.tsv", rows)


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def round_number(value: float) -> int | float:
    if value.is_integer():
        return int(value)
    return round(value, 6)


if __name__ == "__main__":
    raise SystemExit(main())
