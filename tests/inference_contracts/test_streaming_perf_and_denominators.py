import csv
import json
from pathlib import Path

from tools.inference_contracts.run_vllm_api_streaming_perf import compute_tpot_us, extract_completion_delta
from tools.inference_contracts.summarize_msprof_shape_denominators import (
    estimate_denominators,
    parse_dtype_tokens,
    parse_shape_groups,
)
from tools.inference_contracts.summarize_vllm_api_streaming_perf_pair import summarize_pair


def test_streaming_delta_parser_handles_completion_text_and_chat_delta():
    assert extract_completion_delta({"choices": [{"text": "hello", "finish_reason": None}]}) == ("hello", "")
    assert extract_completion_delta({"choices": [{"delta": {"content": "x"}, "finish_reason": "stop"}]}) == (
        "x",
        "stop",
    )
    assert extract_completion_delta({"choices": []}) == ("", "")


def test_compute_tpot_uses_tokens_after_first_token():
    assert compute_tpot_us(1_000, 11_001_000, 12) == 1000
    assert compute_tpot_us(1_000, 11_001_000, 1) == 0
    assert compute_tpot_us(0, 11_001_000, 12) == 0


def test_shape_and_dtype_parsing_supports_msprof_like_strings():
    assert parse_shape_groups("[1, 8192, 4096];[4096, 4096]") == [[1, 8192, 4096], [4096, 4096]]
    assert parse_shape_groups("1,8192,4096|4096,4096") == [[1, 8192, 4096], [4096, 4096]]
    assert parse_dtype_tokens("DT_FLOAT16,DT_FLOAT16") == ["float16", "float16"]


def test_matmul_denominator_estimates_flops_and_tensor_bytes():
    estimate = estimate_denominators(
        op_type="MatMulV2",
        input_shapes="[2, 4];[4, 8]",
        output_shapes="[2, 8]",
        input_data_types="DT_FLOAT16,DT_FLOAT16",
        output_data_types="DT_FLOAT16",
    )

    assert estimate["flops_per_occurrence"] == 128
    assert estimate["tensor_bytes_per_occurrence"] == 112
    assert estimate["status"] == "estimated_matmul_flops_and_tensor_footprint"


def write_result(path: Path, *, status: str, ttft: int, tpot: int, wall: int, tokens_s: float, prefix_hit: float):
    path.mkdir(parents=True, exist_ok=True)
    data = {
        "status": status,
        "request_count": 1,
        "success_case_count": 1 if status == "success" else 0,
        "failed_case_count": 0 if status == "success" else 1,
        "generated_token_count_mismatch_count": 0,
        "server_stats_sample_count": 1,
        "server_stats_max_running_reqs": 1,
        "server_stats_max_waiting_reqs": 0,
        "server_stats_max_kv_cache_usage_pct": 1.5,
        "server_stats_max_prefix_cache_hit_rate_pct": prefix_hit,
        "rows": [
            {
                "case_id": "case",
                "status": "success",
                "input_token_count": 4096,
                "generated_token_count": 64,
                "ttft_us": ttft,
                "tpot_us": tpot,
                "client_wall_us": wall,
                "output_tokens_per_s": tokens_s,
            }
        ],
    }
    (path / "vllm_api_streaming_perf_result.json").write_text(json.dumps(data) + "\n", encoding="utf-8")


def write_result_rows(path: Path, *, status: str, rows: list[dict]):
    path.mkdir(parents=True, exist_ok=True)
    success_count = sum(1 for row in rows if row.get("status") == "success")
    data = {
        "status": status,
        "request_count": len(rows),
        "success_case_count": success_count,
        "failed_case_count": len(rows) - success_count,
        "generated_token_count_mismatch_count": 0,
        "server_stats_sample_count": 1,
        "server_stats_max_running_reqs": 2,
        "server_stats_max_waiting_reqs": 1,
        "server_stats_max_kv_cache_usage_pct": 3.5,
        "server_stats_max_prefix_cache_hit_rate_pct": 40.0,
        "rows": rows,
    }
    (path / "vllm_api_streaming_perf_result.json").write_text(json.dumps(data) + "\n", encoding="utf-8")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_streaming_pair_summary_outputs_mode_and_delta_tables(tmp_path):
    on_dir = tmp_path / "on"
    off_dir = tmp_path / "off"
    out_dir = tmp_path / "pair"
    write_result(on_dir, status="success", ttft=100, tpot=20, wall=1400, tokens_s=45.7, prefix_hit=50.0)
    write_result(off_dir, status="success", ttft=150, tpot=25, wall=1800, tokens_s=35.5, prefix_hit=0.0)

    result = summarize_pair(
        run_id="test_pair",
        prefix_cache_on_dir=on_dir,
        prefix_cache_off_dir=off_dir,
        artifact_dir=out_dir,
    )

    assert result["overall_status"] == "success"
    assert "ttft_us_median" in (out_dir / "vllm_api_streaming_perf_delta_summary.tsv").read_text(
        encoding="utf-8"
    )
    assert "prefix_cache_on" in (out_dir / "vllm_api_streaming_perf_mode_summary.tsv").read_text(
        encoding="utf-8"
    )


def test_streaming_pair_summary_outputs_aisbench_style_tables(tmp_path):
    on_dir = tmp_path / "on"
    off_dir = tmp_path / "off"
    out_dir = tmp_path / "pair"
    rows = [
        {
            "case_id": "case_1",
            "status": "success",
            "input_token_count": 1000,
            "generated_token_count": 64,
            "ttft_us": 100_000,
            "tpot_us": 30_000,
            "client_wall_us": 2_000_000,
            "output_tokens_per_s": 32.0,
            "stream_inter_chunk_median_us": 20_000,
            "request_start_ns": 1_000_000_000,
            "response_end_ns": 3_000_000_000,
        },
        {
            "case_id": "case_2",
            "status": "success",
            "input_token_count": 2000,
            "generated_token_count": 64,
            "ttft_us": 200_000,
            "tpot_us": 40_000,
            "client_wall_us": 3_000_000,
            "output_tokens_per_s": 21.333333,
            "stream_inter_chunk_median_us": 30_000,
            "request_start_ns": 2_000_000_000,
            "response_end_ns": 5_000_000_000,
        },
    ]
    write_result_rows(on_dir, status="success", rows=rows)
    write_result_rows(off_dir, status="success", rows=rows)

    result = summarize_pair(
        run_id="test_pair",
        prefix_cache_on_dir=on_dir,
        prefix_cache_off_dir=off_dir,
        artifact_dir=out_dir,
    )

    assert result["overall_status"] == "success"
    parameter_rows = read_tsv(out_dir / "vllm_api_streaming_perf_parameters.tsv")
    ttft = next(
        row
        for row in parameter_rows
        if row["mode"] == "prefix_cache_on" and row["performance_parameter"] == "TTFT"
    )
    assert float(ttft["Average"]) == 150.0
    assert float(ttft["P75"]) == 175.0
    assert float(ttft["P90"]) == 190.0
    assert float(ttft["P99"]) == 199.0
    assert ttft["N"] == "2"
    assert ttft["unit"] == "ms"

    prefill = next(
        row
        for row in parameter_rows
        if row["mode"] == "prefix_cache_on" and row["performance_parameter"] == "PrefillTokenThroughput"
    )
    assert float(prefill["Average"]) == 10000.0
    assert prefill["unit"] == "token/s"

    common_rows = read_tsv(out_dir / "vllm_api_streaming_perf_common_metrics.tsv")
    by_metric = {
        row["common_metric"]: row for row in common_rows if row["mode"] == "prefix_cache_on"
    }
    assert float(by_metric["Benchmark Duration"]["value"]) == 4000.0
    assert float(by_metric["Concurrency"]["value"]) == 1.25
    assert float(by_metric["Max Concurrency"]["value"]) == 2.0
    assert float(by_metric["Request Throughput"]["value"]) == 0.5
    assert float(by_metric["Output Token Throughput"]["value"]) == 32.0
    assert float(by_metric["Total Token Throughput"]["value"]) == 782.0


def test_streaming_pair_summary_failed_run_keeps_failed_status_and_skips_failed_rows(tmp_path):
    on_dir = tmp_path / "on"
    off_dir = tmp_path / "off"
    out_dir = tmp_path / "pair"
    write_result_rows(
        on_dir,
        status="failed",
        rows=[
            {
                "case_id": "ok",
                "status": "success",
                "input_token_count": 100,
                "generated_token_count": 64,
                "ttft_us": 100_000,
                "tpot_us": 20_000,
                "client_wall_us": 1_000_000,
                "output_tokens_per_s": 64.0,
                "stream_inter_chunk_median_us": 10_000,
                "request_start_ns": 1_000_000_000,
                "response_end_ns": 2_000_000_000,
            },
            {
                "case_id": "bad",
                "status": "failed",
                "input_token_count": 9000,
                "generated_token_count": 0,
                "ttft_us": 0,
                "client_wall_us": 9_000_000,
                "request_start_ns": 1_000_000_000,
                "response_end_ns": 10_000_000_000,
            },
        ],
    )
    write_result_rows(
        off_dir,
        status="success",
        rows=[
            {
                "case_id": "off",
                "status": "success",
                "input_token_count": 100,
                "generated_token_count": 64,
                "ttft_us": 100_000,
                "tpot_us": 20_000,
                "client_wall_us": 1_000_000,
                "output_tokens_per_s": 64.0,
                "stream_inter_chunk_median_us": 10_000,
                "request_start_ns": 1_000_000_000,
                "response_end_ns": 2_000_000_000,
            }
        ],
    )

    result = summarize_pair(
        run_id="test_pair",
        prefix_cache_on_dir=on_dir,
        prefix_cache_off_dir=off_dir,
        artifact_dir=out_dir,
    )

    assert result["overall_status"] == "failed"
    parameter_rows = read_tsv(out_dir / "vllm_api_streaming_perf_parameters.tsv")
    input_tokens = next(
        row
        for row in parameter_rows
        if row["mode"] == "prefix_cache_on" and row["performance_parameter"] == "InputTokens"
    )
    assert input_tokens["N"] == "1"
    assert float(input_tokens["Average"]) == 100.0
