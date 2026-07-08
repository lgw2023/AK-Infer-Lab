from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
from typing import Any

DEFAULT_RUN_ID = "runtime_vllm_api_streaming_perf_pair_2026_0708_p1_029"
POLICY = "streaming_perf_pair_summary_no_bottleneck_claim"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize vLLM streaming performance on/off results.")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--prefix-cache-on-dir", type=Path, required=True)
    parser.add_argument("--prefix-cache-off-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = summarize_pair(
        run_id=args.run_id,
        prefix_cache_on_dir=args.prefix_cache_on_dir,
        prefix_cache_off_dir=args.prefix_cache_off_dir,
        artifact_dir=args.artifact_dir,
    )
    return 0 if result["overall_status"] == "success" else 1


def summarize_pair(
    *,
    run_id: str,
    prefix_cache_on_dir: Path,
    prefix_cache_off_dir: Path,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    mode_results = {
        "prefix_cache_on": load_result(prefix_cache_on_dir / "vllm_api_streaming_perf_result.json"),
        "prefix_cache_off": load_result(prefix_cache_off_dir / "vllm_api_streaming_perf_result.json"),
    }
    mode_rows = [summarize_mode(mode, result) for mode, result in mode_results.items()]
    delta_rows = summarize_deltas(mode_rows)
    parameter_rows = [
        row for mode, result in mode_results.items() for row in summarize_parameter_metrics(mode, result)
    ]
    common_metric_rows = [
        row for mode, result in mode_results.items() for row in summarize_common_metrics(mode, result)
    ]

    write_tsv(artifact_dir / "vllm_api_streaming_perf_mode_summary.tsv", mode_rows)
    write_tsv(artifact_dir / "vllm_api_streaming_perf_delta_summary.tsv", delta_rows)
    write_tsv(artifact_dir / "vllm_api_streaming_perf_parameters.tsv", parameter_rows)
    write_tsv(artifact_dir / "vllm_api_streaming_perf_common_metrics.tsv", common_metric_rows)

    overall_status = (
        "success"
        if all(result.get("status") == "success" for result in mode_results.values())
        and all(row["generated_token_count_mismatch_count"] == 0 for row in mode_rows)
        else "failed"
    )
    result = {
        "run_id": run_id,
        "overall_status": overall_status,
        "prefix_cache_on_dir": str(prefix_cache_on_dir),
        "prefix_cache_off_dir": str(prefix_cache_off_dir),
        "artifact_dir": str(artifact_dir),
        "mode_rows": mode_rows,
        "delta_rows": delta_rows,
        "parameter_rows": parameter_rows,
        "common_metric_rows": common_metric_rows,
        "policy": POLICY,
        "ttft_policy": "host_client_stream_first_nonempty_text_chunk",
        "tpot_policy": "host_client_response_end_minus_first_token_div_generated_tokens_minus_one",
        "itl_policy": "host_client_stream_inter_chunk_median_per_request_not_runtime_native_decode_event",
        "aisbench_style_policy": "vllm_openai_streaming_client_metrics_not_mindie_native_timing",
        "bottleneck_policy": "no_bottleneck_claim",
    }
    (artifact_dir / "vllm_api_streaming_perf_pair_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(artifact_dir / "summary.txt", result)
    write_mail_attachment_candidates(artifact_dir)
    return result


def load_result(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "missing", "rows": [], "missing_path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_mode(mode: str, result: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in result.get("rows", []) if row.get("status") == "success"]
    total_generated = sum(int_value(row.get("generated_token_count")) for row in rows)
    total_input = sum(int_value(row.get("input_token_count")) for row in rows)
    total_wall_us = sum(int_value(row.get("client_wall_us")) for row in rows)
    return {
        "mode": mode,
        "status": result.get("status", "missing"),
        "request_count": int_value(result.get("request_count")),
        "success_case_count": int_value(result.get("success_case_count")),
        "failed_case_count": int_value(result.get("failed_case_count")),
        "generated_token_count_mismatch_count": int_value(result.get("generated_token_count_mismatch_count")),
        "total_input_token_count": total_input,
        "total_generated_token_count": total_generated,
        "ttft_us_median": stat(rows, "ttft_us", "median"),
        "ttft_us_p95": stat(rows, "ttft_us", "p95"),
        "tpot_us_median": stat(rows, "tpot_us", "median"),
        "tpot_us_p95": stat(rows, "tpot_us", "p95"),
        "client_wall_us_median": stat(rows, "client_wall_us", "median"),
        "client_wall_us_p95": stat(rows, "client_wall_us", "p95"),
        "output_tokens_per_s_median": stat(rows, "output_tokens_per_s", "median"),
        "aggregate_output_tokens_per_s": tokens_per_s(total_generated, total_wall_us),
        "server_stats_sample_count": int_value(result.get("server_stats_sample_count")),
        "server_stats_max_running_reqs": int_value(result.get("server_stats_max_running_reqs")),
        "server_stats_max_waiting_reqs": int_value(result.get("server_stats_max_waiting_reqs")),
        "server_stats_max_kv_cache_usage_pct": float_value(result.get("server_stats_max_kv_cache_usage_pct")),
        "server_stats_max_prefix_cache_hit_rate_pct": float_value(
            result.get("server_stats_max_prefix_cache_hit_rate_pct")
        ),
        "policy": POLICY,
    }


def summarize_deltas(mode_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_mode = {row["mode"]: row for row in mode_rows}
    on = by_mode.get("prefix_cache_on", {})
    off = by_mode.get("prefix_cache_off", {})
    metrics = [
        "ttft_us_median",
        "ttft_us_p95",
        "tpot_us_median",
        "tpot_us_p95",
        "client_wall_us_median",
        "client_wall_us_p95",
        "output_tokens_per_s_median",
        "aggregate_output_tokens_per_s",
        "server_stats_max_waiting_reqs",
        "server_stats_max_kv_cache_usage_pct",
        "server_stats_max_prefix_cache_hit_rate_pct",
    ]
    rows = []
    for metric in metrics:
        on_value = float_value(on.get(metric))
        off_value = float_value(off.get(metric))
        rows.append(
            {
                "metric": metric,
                "on_value": on_value,
                "off_value": off_value,
                "delta_on_minus_off": round_number(on_value - off_value),
                "ratio_on_div_off": round_number(on_value / off_value) if off_value else "",
                "policy": POLICY,
            }
        )
    return rows


def summarize_parameter_metrics(mode: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = success_rows(result)
    metric_specs = [
        ("E2EL", values_ms(rows, "client_wall_us"), "ms", "client_wall_us_div_1000"),
        ("TTFT", values_ms(rows, "ttft_us"), "ms", "host_client_first_nonempty_text_chunk"),
        (
            "TPOT",
            values_ms(rows, "tpot_us"),
            "ms",
            "response_end_minus_first_token_div_generated_tokens_minus_one",
        ),
        (
            "ITL",
            values_ms(rows, "stream_inter_chunk_median_us"),
            "ms",
            "host_stream_inter_chunk_median_per_request_not_runtime_native_decode_event",
        ),
        ("InputTokens", values_raw(rows, "input_token_count"), "token", "submitted_input_token_count"),
        ("OutputTokens", values_raw(rows, "generated_token_count"), "token", "generated_token_count"),
        (
            "OutputTokenThroughput",
            values_raw(rows, "output_tokens_per_s"),
            "token/s",
            "generated_tokens_div_client_wall_time",
        ),
        (
            "PrefillTokenThroughput",
            prefill_token_throughput_values(rows),
            "token/s",
            "input_tokens_div_ttft_host_client_approximation",
        ),
    ]
    return [describe_parameter(mode, name, values, unit, policy) for name, values, unit, policy in metric_specs]


def summarize_common_metrics(mode: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = success_rows(result)
    total_requests = int_value(result.get("request_count"))
    success_count = int_value(result.get("success_case_count"))
    failed_count = int_value(result.get("failed_case_count"))
    total_input = sum(int_value(row.get("input_token_count")) for row in rows)
    total_generated = sum(int_value(row.get("generated_token_count")) for row in rows)
    benchmark_duration_us = compute_benchmark_duration_us(rows)
    benchmark_duration_s = benchmark_duration_us / 1_000_000 if benchmark_duration_us > 0 else 0
    sum_wall_us = sum(int_value(row.get("client_wall_us")) for row in rows)

    metric_specs = [
        ("Benchmark Duration", benchmark_duration_us / 1000 if benchmark_duration_us else 0, "ms"),
        ("Total Requests", total_requests, "request"),
        ("Failed Requests", failed_count, "request"),
        ("Success Requests", success_count, "request"),
        (
            "Concurrency",
            round_number(sum_wall_us / benchmark_duration_us) if benchmark_duration_us else 0,
            "request",
        ),
        ("Max Concurrency", compute_max_concurrency(rows), "request"),
        ("Request Throughput", throughput(success_count, benchmark_duration_s), "req/s"),
        ("Total Input Tokens", total_input, "token"),
        (
            "Prefill Token Throughput",
            throughput(total_input, benchmark_duration_s),
            "token/s",
        ),
        ("Total generated tokens", total_generated, "token"),
        ("Input Token Throughput", throughput(total_input, benchmark_duration_s), "token/s"),
        ("Output Token Throughput", throughput(total_generated, benchmark_duration_s), "token/s"),
        ("Total Token Throughput", throughput(total_input + total_generated, benchmark_duration_s), "token/s"),
    ]
    return [
        {
            "mode": mode,
            "common_metric": name,
            "stage": "total",
            "value": round_number(value),
            "unit": unit,
            "policy": "benchmark_duration_based_vllm_openai_streaming_client_metric",
        }
        for name, value, unit in metric_specs
    ]


def success_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in result.get("rows", []) if row.get("status") == "success"]


def values_ms(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [float_value(row.get(field)) / 1000 for row in rows if float_value(row.get(field)) > 0]


def values_raw(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [float_value(row.get(field)) for row in rows if float_value(row.get(field)) > 0]


def prefill_token_throughput_values(rows: list[dict[str, Any]]) -> list[float]:
    values = []
    for row in rows:
        input_tokens = int_value(row.get("input_token_count"))
        ttft_us = int_value(row.get("ttft_us"))
        if input_tokens > 0 and ttft_us > 0:
            values.append(input_tokens / (ttft_us / 1_000_000))
    return values


def describe_parameter(mode: str, name: str, values: list[float], unit: str, policy: str) -> dict[str, Any]:
    stats = describe_values(values)
    return {
        "mode": mode,
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
        "policy": policy,
    }


def describe_values(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "average": 0.0,
            "min": 0.0,
            "max": 0.0,
            "median": 0.0,
            "p75": 0.0,
            "p90": 0.0,
            "p99": 0.0,
            "n": 0,
        }
    return {
        "average": round_number(sum(values) / len(values)),
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
    if not starts or not ends:
        return 0
    return max(0, (max(ends) - min(starts)) // 1000)


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
    if count <= 0 or duration_s <= 0:
        return 0.0
    return round_number(count / duration_s)


def stat(rows: list[dict[str, Any]], field: str, kind: str) -> float:
    values = [float_value(row.get(field)) for row in rows if float_value(row.get(field)) > 0]
    if not values:
        return 0.0
    if kind == "median":
        return round_number(median(values))
    if kind == "p95":
        return percentile(values, 95)
    raise ValueError(kind)


def percentile(values: list[float], pct: int) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return round_number(ordered[0])
    rank = (pct / 100) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return round_number(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def tokens_per_s(token_count: int, wall_us: int) -> float:
    if token_count <= 0 or wall_us <= 0:
        return 0.0
    return round_number(token_count / (wall_us / 1_000_000))


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, result: dict[str, Any]) -> None:
    lines = [
        f"run_id={result['run_id']}",
        f"overall_status={result['overall_status']}",
        f"prefix_cache_on_dir={result['prefix_cache_on_dir']}",
        f"prefix_cache_off_dir={result['prefix_cache_off_dir']}",
        f"policy={result['policy']}",
        f"ttft_policy={result['ttft_policy']}",
        f"tpot_policy={result['tpot_policy']}",
        f"itl_policy={result['itl_policy']}",
        f"aisbench_style_policy={result['aisbench_style_policy']}",
        f"bottleneck_policy={result['bottleneck_policy']}",
        "",
        "## mode_rows",
    ]
    for row in result["mode_rows"]:
        lines.append(
            "\t".join(
                [
                    row["mode"],
                    row["status"],
                    f"requests={row['request_count']}",
                    f"success={row['success_case_count']}",
                    f"ttft_median_us={row['ttft_us_median']}",
                    f"tpot_median_us={row['tpot_us_median']}",
                    f"aggregate_output_tokens_per_s={row['aggregate_output_tokens_per_s']}",
                    f"prefix_hit_max_pct={row['server_stats_max_prefix_cache_hit_rate_pct']}",
                ]
            )
        )
    lines.append("")
    lines.append("## deltas_on_minus_off")
    for row in result["delta_rows"]:
        lines.append(f"{row['metric']}\t{row['delta_on_minus_off']}\tratio={row['ratio_on_div_off']}")
    lines.append("")
    lines.append("## aisbench_style_outputs")
    lines.append("vllm_api_streaming_perf_parameters.tsv")
    lines.append("vllm_api_streaming_perf_common_metrics.tsv")
    lines.append("ITL is host streaming inter-chunk latency, not runtime native decode event timing.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mail_attachment_candidates(artifact_dir: Path) -> None:
    relpaths = [
        "summary.txt",
        "vllm_api_streaming_perf_mode_summary.tsv",
        "vllm_api_streaming_perf_delta_summary.tsv",
        "vllm_api_streaming_perf_parameters.tsv",
        "vllm_api_streaming_perf_common_metrics.tsv",
        "vllm_api_streaming_perf_pair_result.json",
    ]
    lines = ["path\tsize_bytes\tmail_ok"]
    for relpath in relpaths:
        path = artifact_dir / relpath
        if not path.exists():
            continue
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
