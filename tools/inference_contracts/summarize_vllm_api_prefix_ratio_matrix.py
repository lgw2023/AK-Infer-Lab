from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, median
from typing import Any

DEFAULT_RUN_ID = "runtime_vllm_api_prefix_ratio_long_context_matrix_2026_0709_p1_031_summary"
POLICY = "prefix_ratio_matrix_summary_no_bottleneck_claim"
EXPECTED_INPUT_CAPS = (8192, 16384, 32768, 65536, 131072)
EXPECTED_PREFIX_RATIOS = (30, 60, 90)
AISBENCH_PARAMETERS = (
    "E2EL",
    "TTFT",
    "TPOT",
    "ITL",
    "InputTokens",
    "OutputTokens",
    "OutputTokenThroughput",
    "PrefillTokenThroughput",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize P1.31 vLLM prefix-ratio long-context matrix results.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--prefix-cache-on-dir", type=Path, required=True)
    parser.add_argument("--prefix-cache-off-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = summarize_matrix(
        run_id=args.run_id,
        prefix_cache_on_dir=args.prefix_cache_on_dir,
        prefix_cache_off_dir=args.prefix_cache_off_dir,
        artifact_dir=args.artifact_dir,
    )
    return 0 if result["overall_status"] == "success" else 1


def summarize_matrix(
    *,
    run_id: str,
    prefix_cache_on_dir: Path,
    prefix_cache_off_dir: Path,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    mode_results = {
        "prefix_cache_on": load_mode(prefix_cache_on_dir),
        "prefix_cache_off": load_mode(prefix_cache_off_dir),
    }
    mode_cell_rows = {
        mode: normalize_cell_rows(mode, result.get("cell_rows", [])) for mode, result in mode_results.items()
    }
    request_rows = {
        mode: read_tsv(Path(result.get("artifact_dir", "")) / "request_summary.tsv")
        if result.get("artifact_dir")
        else read_tsv((prefix_cache_on_dir if mode == "prefix_cache_on" else prefix_cache_off_dir) / "request_summary.tsv")
        for mode, result in mode_results.items()
    }
    phase_rows = {
        mode: read_tsv((prefix_cache_on_dir if mode == "prefix_cache_on" else prefix_cache_off_dir) / "phase_memory_summary.tsv")
        for mode in mode_results
    }

    completeness_rows = build_completeness_rows(mode_cell_rows)
    parameter_rows = [
        row
        for mode in ("prefix_cache_on", "prefix_cache_off")
        for row in build_parameter_rows(mode, request_rows[mode])
    ]
    common_metric_rows = [
        row
        for mode in ("prefix_cache_on", "prefix_cache_off")
        for row in build_common_metric_rows(mode, request_rows[mode])
    ]
    delta_rows = build_delta_rows(mode_cell_rows, phase_rows)

    write_tsv(artifact_dir / "prefix_ratio_matrix_completeness.tsv", completeness_rows)
    write_tsv(artifact_dir / "prefix_ratio_matrix_aisbench_parameters.tsv", parameter_rows)
    write_tsv(artifact_dir / "prefix_ratio_matrix_common_metrics.tsv", common_metric_rows)
    write_tsv(artifact_dir / "prefix_ratio_matrix_delta_summary.tsv", delta_rows)

    expected_cells = len(EXPECTED_INPUT_CAPS) * len(EXPECTED_PREFIX_RATIOS)
    mode_status_ok = all(result.get("status") == "success" for result in mode_results.values())
    complete = all(
        sum(1 for row in rows if row.get("cell_status") == "success") == expected_cells
        for rows in mode_cell_rows.values()
    )
    overall_status = "success" if mode_status_ok and complete else "failed"
    result = {
        "run_id": run_id,
        "overall_status": overall_status,
        "prefix_cache_on_dir": str(prefix_cache_on_dir),
        "prefix_cache_off_dir": str(prefix_cache_off_dir),
        "expected_cell_count_per_mode": expected_cells,
        "prefix_cache_on_status": mode_results["prefix_cache_on"].get("status", "missing"),
        "prefix_cache_off_status": mode_results["prefix_cache_off"].get("status", "missing"),
        "completeness_rows": completeness_rows,
        "delta_rows": delta_rows,
        "policy": POLICY,
        "length_policy": "input_cap_tokens_are_8k_16k_32k_64k_128k_output_tokens_fixed_1024",
        "prefix_ratio_policy": "target_prefix_ratio_is_shared_prefix_tokens_div_input_cap_not_observed_hit_rate",
        "aisbench_style_policy": "vllm_openai_streaming_client_metrics_not_mindie_native_timing",
        "itl_policy": "host_client_stream_inter_chunk_median_per_request_not_runtime_native_decode_event",
        "memory_policy": "phase_memory_is_process_group_rss_pss_and_whole_device_hbm_not_kv_object_bytes",
        "bottleneck_policy": "no_compute_memory_hbm_scheduler_or_prefix_cache_benefit_claim",
    }
    (artifact_dir / "prefix_ratio_matrix_summary_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(artifact_dir / "summary.txt", result)
    write_mail_attachment_candidates(artifact_dir)
    return result


def load_mode(mode_dir: Path) -> dict[str, Any]:
    path = mode_dir / "result.json"
    if not path.is_file():
        return {"status": "missing", "cell_rows": [], "artifact_dir": str(mode_dir)}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("artifact_dir", str(mode_dir))
    return data


def normalize_cell_rows(mode: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        item = dict(row)
        item["mode"] = item.get("mode") or mode
        item["input_cap_tokens"] = int_value(item.get("input_cap_tokens"))
        item["target_prefix_ratio_pct"] = int_value(item.get("target_prefix_ratio_pct"))
        normalized.append(item)
    return normalized


def build_completeness_rows(mode_cell_rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for mode in ("prefix_cache_on", "prefix_cache_off"):
        by_key = {
            (int_value(row.get("input_cap_tokens")), int_value(row.get("target_prefix_ratio_pct"))): row
            for row in mode_cell_rows.get(mode, [])
        }
        for input_cap in EXPECTED_INPUT_CAPS:
            for ratio_pct in EXPECTED_PREFIX_RATIOS:
                row = by_key.get((input_cap, ratio_pct), {})
                rows.append(
                    {
                        "mode": mode,
                        "input_cap_tokens": input_cap,
                        "target_prefix_ratio_pct": ratio_pct,
                        "cell_present": int(bool(row)),
                        "cell_status": row.get("cell_status", "missing"),
                        "measured_success_count": int_value(row.get("measured_success_count")),
                        "measured_request_count": int_value(row.get("measured_request_count")),
                        "generated_token_count_mismatch_count": int_value(
                            row.get("generated_token_count_mismatch_count")
                        ),
                        "observed_prefix_hit_rate_pct": float_value(
                            row.get("server_stats_max_prefix_cache_hit_rate_pct")
                        ),
                        "target_vs_observed_prefix_hit_rate_delta_pct": round_number(
                            float_value(row.get("server_stats_max_prefix_cache_hit_rate_pct")) - ratio_pct
                        )
                        if row
                        else "",
                        "policy": "complete_cell_required_no_silent_skip",
                    }
                )
    return rows


def build_parameter_rows(mode: str, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    result = []
    for (input_cap, ratio_pct), group_rows in grouped_success_measured_rows(rows).items():
        metric_specs = [
            ("E2EL", values_ms(group_rows, "client_wall_us"), "ms", "client_wall_us_div_1000"),
            ("TTFT", values_ms(group_rows, "ttft_us"), "ms", "host_client_first_nonempty_text_chunk"),
            (
                "TPOT",
                values_ms(group_rows, "tpot_us"),
                "ms",
                "response_end_minus_first_token_div_generated_tokens_minus_one",
            ),
            (
                "ITL",
                values_ms(group_rows, "stream_inter_chunk_median_us"),
                "ms",
                "host_stream_inter_chunk_median_per_request_not_runtime_native_decode_event",
            ),
            ("InputTokens", values_raw(group_rows, "actual_input_token_count"), "token", "submitted_input_token_count"),
            ("OutputTokens", values_raw(group_rows, "generated_token_count"), "token", "generated_token_count"),
            (
                "OutputTokenThroughput",
                values_raw(group_rows, "output_tokens_per_s"),
                "token/s",
                "generated_tokens_div_client_wall_time",
            ),
            (
                "PrefillTokenThroughput",
                prefill_token_throughput_values(group_rows),
                "token/s",
                "input_tokens_div_ttft_host_client_approximation",
            ),
        ]
        for name, values, unit, metric_policy in metric_specs:
            stats = describe_values(values)
            result.append(
                {
                    "mode": mode,
                    "input_cap_tokens": input_cap,
                    "target_prefix_ratio_pct": ratio_pct,
                    "performance_parameter": name,
                    "stage": "total",
                    "Average": stats["average"],
                    "Min": stats["min"],
                    "Max": stats["max"],
                    "Median": stats["median"],
                    "P75": stats["p75"],
                    "P90": stats["p90"],
                    "P99": stats["p99"],
                    "N": stats["n"],
                    "unit": unit,
                    "policy": metric_policy,
                }
            )
    return result


def build_common_metric_rows(mode: str, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    result = []
    for (input_cap, ratio_pct), group_rows in grouped_success_measured_rows(rows).items():
        total_requests = len([row for row in rows if cell_key(row) == (input_cap, ratio_pct) and row.get("request_role") == "measured"])
        success_count = len(group_rows)
        failed_count = total_requests - success_count
        total_input = sum(int_value(row.get("actual_input_token_count")) for row in group_rows)
        total_generated = sum(int_value(row.get("generated_token_count")) for row in group_rows)
        benchmark_duration_us = compute_benchmark_duration_us(group_rows)
        benchmark_duration_s = benchmark_duration_us / 1_000_000 if benchmark_duration_us > 0 else 0
        sum_wall_us = sum(int_value(row.get("client_wall_us")) for row in group_rows)
        metric_specs = [
            ("Benchmark Duration", benchmark_duration_us / 1000 if benchmark_duration_us else 0, "ms"),
            ("Total Requests", total_requests, "request"),
            ("Failed Requests", failed_count, "request"),
            ("Success Requests", success_count, "request"),
            ("Concurrency", round_number(sum_wall_us / benchmark_duration_us) if benchmark_duration_us else 0, "request"),
            ("Max Concurrency", compute_max_concurrency(group_rows), "request"),
            ("Request Throughput", throughput(success_count, benchmark_duration_s), "req/s"),
            ("Total Input Tokens", total_input, "token"),
            ("Prefill Token Throughput", throughput(total_input, benchmark_duration_s), "token/s"),
            ("Total generated tokens", total_generated, "token"),
            ("Input Token Throughput", throughput(total_input, benchmark_duration_s), "token/s"),
            ("Output Token Throughput", throughput(total_generated, benchmark_duration_s), "token/s"),
            ("Total Token Throughput", throughput(total_input + total_generated, benchmark_duration_s), "token/s"),
        ]
        for name, value, unit in metric_specs:
            result.append(
                {
                    "mode": mode,
                    "input_cap_tokens": input_cap,
                    "target_prefix_ratio_pct": ratio_pct,
                    "common_metric": name,
                    "stage": "total",
                    "value": round_number(value),
                    "unit": unit,
                    "policy": "benchmark_duration_based_vllm_openai_streaming_client_metric",
                }
            )
    return result


def build_delta_rows(
    mode_cell_rows: dict[str, list[dict[str, Any]]],
    phase_rows: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    on = {
        (int_value(row.get("input_cap_tokens")), int_value(row.get("target_prefix_ratio_pct"))): row
        for row in mode_cell_rows.get("prefix_cache_on", [])
    }
    off = {
        (int_value(row.get("input_cap_tokens")), int_value(row.get("target_prefix_ratio_pct"))): row
        for row in mode_cell_rows.get("prefix_cache_off", [])
    }
    rows = []
    for input_cap in EXPECTED_INPUT_CAPS:
        for ratio_pct in EXPECTED_PREFIX_RATIOS:
            on_row = on.get((input_cap, ratio_pct), {})
            off_row = off.get((input_cap, ratio_pct), {})
            on_hit = float_value(on_row.get("server_stats_max_prefix_cache_hit_rate_pct"))
            off_hit = float_value(off_row.get("server_stats_max_prefix_cache_hit_rate_pct"))
            rows.append(
                {
                    "input_cap_tokens": input_cap,
                    "target_prefix_ratio_pct": ratio_pct,
                    "on_cell_status": on_row.get("cell_status", "missing"),
                    "off_cell_status": off_row.get("cell_status", "missing"),
                    "on_observed_prefix_hit_rate_pct": on_hit,
                    "off_observed_prefix_hit_rate_pct": off_hit,
                    "observed_prefix_hit_rate_delta_on_minus_off_pct": round_number(on_hit - off_hit),
                    "on_target_vs_observed_prefix_hit_rate_delta_pct": round_number(on_hit - ratio_pct),
                    "off_target_vs_observed_prefix_hit_rate_delta_pct": round_number(off_hit - ratio_pct),
                    "ttft_us_median_on": float_value(on_row.get("ttft_us_median")),
                    "ttft_us_median_off": float_value(off_row.get("ttft_us_median")),
                    "ttft_us_median_ratio_on_div_off": ratio(
                        float_value(on_row.get("ttft_us_median")), float_value(off_row.get("ttft_us_median"))
                    ),
                    "tpot_us_median_on": float_value(on_row.get("tpot_us_median")),
                    "tpot_us_median_off": float_value(off_row.get("tpot_us_median")),
                    "tpot_us_median_ratio_on_div_off": ratio(
                        float_value(on_row.get("tpot_us_median")), float_value(off_row.get("tpot_us_median"))
                    ),
                    "client_wall_us_median_on": float_value(on_row.get("client_wall_us_median")),
                    "client_wall_us_median_off": float_value(off_row.get("client_wall_us_median")),
                    "client_wall_us_median_ratio_on_div_off": ratio(
                        float_value(on_row.get("client_wall_us_median")),
                        float_value(off_row.get("client_wall_us_median")),
                    ),
                    "output_tokens_per_s_median_on": float_value(on_row.get("output_tokens_per_s_median")),
                    "output_tokens_per_s_median_off": float_value(off_row.get("output_tokens_per_s_median")),
                    "server_stats_max_kv_cache_usage_pct_on": float_value(
                        on_row.get("server_stats_max_kv_cache_usage_pct")
                    ),
                    "server_stats_max_kv_cache_usage_pct_off": float_value(
                        off_row.get("server_stats_max_kv_cache_usage_pct")
                    ),
                    "rss_max_mb_on": phase_max(phase_rows.get("prefix_cache_on", []), input_cap, ratio_pct, "rss_max_mb"),
                    "rss_max_mb_off": phase_max(
                        phase_rows.get("prefix_cache_off", []), input_cap, ratio_pct, "rss_max_mb"
                    ),
                    "pss_max_mb_on": phase_max(phase_rows.get("prefix_cache_on", []), input_cap, ratio_pct, "pss_max_mb"),
                    "pss_max_mb_off": phase_max(
                        phase_rows.get("prefix_cache_off", []), input_cap, ratio_pct, "pss_max_mb"
                    ),
                    "hbm_used_max_mb_on": phase_max(
                        phase_rows.get("prefix_cache_on", []), input_cap, ratio_pct, "hbm_used_max_mb"
                    ),
                    "hbm_used_max_mb_off": phase_max(
                        phase_rows.get("prefix_cache_off", []), input_cap, ratio_pct, "hbm_used_max_mb"
                    ),
                    "policy": "target_prefix_ratio_is_not_observed_hit_rate_no_bottleneck_claim",
                }
            )
    return rows


def grouped_success_measured_rows(rows: list[dict[str, str]]) -> dict[tuple[int, int], list[dict[str, str]]]:
    grouped: dict[tuple[int, int], list[dict[str, str]]] = {}
    for row in rows:
        if row.get("request_role") != "measured" or row.get("status") != "success":
            continue
        grouped.setdefault(cell_key(row), []).append(row)
    return grouped


def cell_key(row: dict[str, Any]) -> tuple[int, int]:
    return int_value(row.get("input_cap_tokens")), int_value(row.get("target_prefix_ratio_pct"))


def values_ms(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [float_value(row.get(field)) / 1000 for row in rows if float_value(row.get(field)) > 0]


def values_raw(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [float_value(row.get(field)) for row in rows if float_value(row.get(field)) > 0]


def prefill_token_throughput_values(rows: list[dict[str, Any]]) -> list[float]:
    values = []
    for row in rows:
        input_tokens = int_value(row.get("actual_input_token_count"))
        ttft_us = int_value(row.get("ttft_us"))
        if input_tokens > 0 and ttft_us > 0:
            values.append(input_tokens / (ttft_us / 1_000_000))
    return values


def describe_values(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"average": 0.0, "min": 0.0, "max": 0.0, "median": 0.0, "p75": 0.0, "p90": 0.0, "p99": 0.0, "n": 0}
    return {
        "average": round_number(mean(values)),
        "min": round_number(min(values)),
        "max": round_number(max(values)),
        "median": round_number(median(values)),
        "p75": percentile(values, 75),
        "p90": percentile(values, 90),
        "p99": percentile(values, 99),
        "n": len(values),
    }


def compute_benchmark_duration_us(rows: list[dict[str, Any]]) -> int:
    starts = [int_value(row.get("request_start_ns")) for row in rows if int_value(row.get("request_start_ns")) > 0]
    ends = [int_value(row.get("response_end_ns")) for row in rows if int_value(row.get("response_end_ns")) > 0]
    return max(0, (max(ends) - min(starts)) // 1000) if starts and ends else 0


def compute_max_concurrency(rows: list[dict[str, Any]]) -> int:
    events: list[tuple[int, int]] = []
    for row in rows:
        start_ns = int_value(row.get("request_start_ns"))
        end_ns = int_value(row.get("response_end_ns"))
        if start_ns > 0 and end_ns > start_ns:
            events.append((start_ns, 1))
            events.append((end_ns, -1))
    active = 0
    max_active = 0
    for _, delta in sorted(events, key=lambda item: (item[0], 0 if item[1] < 0 else 1)):
        active = max(0, active + delta)
        max_active = max(max_active, active)
    return max_active


def throughput(count: int | float, duration_s: float) -> float:
    return round_number(count / duration_s) if count > 0 and duration_s > 0 else 0.0


def percentile(values: list[float], pct: int) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return round_number(ordered[0])
    rank = (pct / 100) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return round_number(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def phase_max(rows: list[dict[str, str]], input_cap: int, ratio_pct: int, field: str) -> float:
    values = [
        float_value(row.get(field))
        for row in rows
        if int_value(row.get("input_cap_tokens")) == input_cap
        and int_value(row.get("target_prefix_ratio_pct")) == ratio_pct
        and float_value(row.get(field)) > 0
    ]
    return round_number(max(values)) if values else 0.0


def ratio(numerator: float, denominator: float) -> float | str:
    return round_number(numerator / denominator) if denominator else ""


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, result: dict[str, Any]) -> None:
    lines = [
        f"run_id={result['run_id']}",
        f"overall_status={result['overall_status']}",
        f"prefix_cache_on_status={result['prefix_cache_on_status']}",
        f"prefix_cache_off_status={result['prefix_cache_off_status']}",
        f"expected_cell_count_per_mode={result['expected_cell_count_per_mode']}",
        f"policy={result['policy']}",
        f"length_policy={result['length_policy']}",
        f"prefix_ratio_policy={result['prefix_ratio_policy']}",
        f"aisbench_style_policy={result['aisbench_style_policy']}",
        f"itl_policy={result['itl_policy']}",
        f"memory_policy={result['memory_policy']}",
        f"bottleneck_policy={result['bottleneck_policy']}",
        "",
        "## delta_cells",
    ]
    for row in result["delta_rows"]:
        lines.append(
            "\t".join(
                [
                    f"cap={row['input_cap_tokens']}",
                    f"target_prefix_pct={row['target_prefix_ratio_pct']}",
                    f"on_status={row['on_cell_status']}",
                    f"off_status={row['off_cell_status']}",
                    f"on_observed_hit_pct={row['on_observed_prefix_hit_rate_pct']}",
                    f"off_observed_hit_pct={row['off_observed_prefix_hit_rate_pct']}",
                    f"ttft_ratio={row['ttft_us_median_ratio_on_div_off']}",
                    f"tpot_ratio={row['tpot_us_median_ratio_on_div_off']}",
                ]
            )
        )
    lines.extend(
        [
            "",
            "## outputs",
            "prefix_ratio_matrix_aisbench_parameters.tsv",
            "prefix_ratio_matrix_common_metrics.tsv",
            "prefix_ratio_matrix_delta_summary.tsv",
            "prefix_ratio_matrix_completeness.tsv",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mail_attachment_candidates(artifact_dir: Path) -> None:
    relpaths = [
        "summary.txt",
        "prefix_ratio_matrix_summary_result.json",
        "prefix_ratio_matrix_completeness.tsv",
        "prefix_ratio_matrix_aisbench_parameters.tsv",
        "prefix_ratio_matrix_common_metrics.tsv",
        "prefix_ratio_matrix_delta_summary.tsv",
    ]
    lines = ["path\tsize_bytes\tmail_ok"]
    for relpath in relpaths:
        path = artifact_dir / relpath
        if path.exists():
            size = path.stat().st_size
            lines.append(f"{path}\t{size}\t{str(size <= 70 * 1024).lower()}")
    (artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def round_number(value: float) -> float:
    return round(float(value), 6)


if __name__ == "__main__":
    raise SystemExit(main())
