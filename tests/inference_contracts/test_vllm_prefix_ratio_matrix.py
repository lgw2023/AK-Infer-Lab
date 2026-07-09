import csv
import json
from pathlib import Path

from tools.inference_contracts.run_vllm_api_prefix_ratio_matrix import (
    DEFAULT_INPUT_CAPS,
    DEFAULT_PREFIX_RATIOS,
    build_cell_request_specs,
    build_matrix_cells,
    prepare_cell_prompts,
)
from tools.inference_contracts.summarize_vllm_api_prefix_ratio_matrix import summarize_matrix


class FakeTokenizer:
    def __call__(self, text: str, add_special_tokens: bool = False):
        del add_special_tokens
        tokens = text.split()
        return type("Encoding", (), {"input_ids": list(range(len(tokens)))})()

    def decode(self, token_ids, skip_special_tokens: bool = False):
        del skip_special_tokens
        return " ".join(f"tok{index}" for index, _ in enumerate(token_ids))


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_prefix_ratio_matrix_defines_required_15_cells_and_fixed_output():
    cells = build_matrix_cells()

    assert len(cells) == 15
    assert {cell["input_cap_tokens"] for cell in cells} == set(DEFAULT_INPUT_CAPS)
    assert {cell["target_prefix_ratio"] for cell in cells} == set(DEFAULT_PREFIX_RATIOS)
    assert {cell["output_tokens"] for cell in cells} == {1024}
    assert all(cell["max_model_len"] == cell["input_cap_tokens"] + 2048 for cell in cells)
    assert {
        (cell["input_cap_tokens"], cell["target_prefix_ratio_pct"])
        for cell in cells
    } == {(cap, ratio) for cap in DEFAULT_INPUT_CAPS for ratio in (30, 60, 90)}


def test_prepared_prompts_hit_target_shared_prefix_ratio_with_roundtrip_tolerance():
    cell = build_matrix_cells(input_caps=(8192,), prefix_ratios=(0.60,), output_tokens=1024)[0]
    prepared = prepare_cell_prompts(FakeTokenizer(), cell, build_cell_request_specs(cell))

    assert len(prepared) == 4
    assert {item["row"]["request_role"] for item in prepared} == {"warmup", "measured"}
    assert all(item["row"]["max_new_tokens"] == 1024 for item in prepared)
    assert all(item["row"]["actual_input_token_count"] == 8192 for item in prepared)
    assert all(abs(float(item["row"]["actual_shared_prefix_ratio_pct"]) - 60.0) <= 0.5 for item in prepared)


def write_mode_artifacts(mode_dir: Path, mode: str, *, failed_key: tuple[int, int] | None = None) -> None:
    mode_dir.mkdir(parents=True, exist_ok=True)
    cell_rows = []
    request_rows = []
    phase_rows = []
    for cell in build_matrix_cells():
        key = (cell["input_cap_tokens"], cell["target_prefix_ratio_pct"])
        failed = key == failed_key
        observed_hit = 47.0 if mode == "prefix_cache_on" and key == (8192, 60) else 0.0
        if mode == "prefix_cache_on" and key != (8192, 60):
            observed_hit = float(cell["target_prefix_ratio_pct"] - 5)
        cell_rows.append(
            {
                "mode": mode,
                "cell_id": cell["cell_id"],
                "input_cap_tokens": cell["input_cap_tokens"],
                "target_prefix_ratio_pct": cell["target_prefix_ratio_pct"],
                "target_shared_prefix_tokens": cell["target_shared_prefix_tokens"],
                "output_tokens": 1024,
                "max_model_len": cell["max_model_len"],
                "measured_request_count": 3,
                "measured_success_count": 2 if failed else 3,
                "generated_token_count_mismatch_count": 1 if failed else 0,
                "ttft_us_median": 1000 if mode == "prefix_cache_on" else 2000,
                "tpot_us_median": 100 if mode == "prefix_cache_on" else 200,
                "client_wall_us_median": 5000 if mode == "prefix_cache_on" else 8000,
                "output_tokens_per_s_median": 200.0 if mode == "prefix_cache_on" else 128.0,
                "server_stats_max_kv_cache_usage_pct": 12.5,
                "server_stats_max_prefix_cache_hit_rate_pct": observed_hit,
                "cell_status": "failed" if failed else "success",
            }
        )
        for index in range(3):
            request_rows.append(
                {
                    "case_id": f"{cell['cell_id']}_{mode}_{index}",
                    "mode": mode,
                    "cell_id": cell["cell_id"],
                    "request_role": "measured",
                    "input_cap_tokens": cell["input_cap_tokens"],
                    "target_prefix_ratio_pct": cell["target_prefix_ratio_pct"],
                    "actual_input_token_count": cell["input_cap_tokens"],
                    "max_new_tokens": 1024,
                    "request_start_ns": 1_000_000_000 + index * 100_000_000,
                    "first_token_ns": 1_001_000_000 + index * 100_000_000,
                    "response_end_ns": 1_005_000_000 + index * 100_000_000,
                    "ttft_us": 1000,
                    "tpot_us": 4,
                    "client_wall_us": 5000,
                    "output_tokens_per_s": 204800.0,
                    "generated_token_count": 0 if failed and index == 2 else 1024,
                    "stream_inter_chunk_median_us": 4,
                    "status": "failed" if failed and index == 2 else "success",
                }
            )
        phase_rows.append(
            {
                "mode": mode,
                "cell_id": cell["cell_id"],
                "input_cap_tokens": cell["input_cap_tokens"],
                "target_prefix_ratio_pct": cell["target_prefix_ratio_pct"],
                "phase": "decode",
                "rss_max_mb": 5100,
                "pss_max_mb": 4400,
                "hbm_used_max_mb": 55000,
            }
        )
    (mode_dir / "result.json").write_text(
        json.dumps(
            {
                "status": "failed" if failed_key else "success",
                "mode": mode,
                "cell_rows": cell_rows,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    write_tsv(mode_dir / "request_summary.tsv", request_rows)
    write_tsv(mode_dir / "phase_memory_summary.tsv", phase_rows)


def write_tsv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_prefix_ratio_summarizer_keeps_failed_cell_failed_and_observed_hit_separate(tmp_path):
    on_dir = tmp_path / "on"
    off_dir = tmp_path / "off"
    out_dir = tmp_path / "summary"
    write_mode_artifacts(on_dir, "prefix_cache_on", failed_key=(131072, 90))
    write_mode_artifacts(off_dir, "prefix_cache_off")

    result = summarize_matrix(
        run_id="test_p1_031",
        prefix_cache_on_dir=on_dir,
        prefix_cache_off_dir=off_dir,
        artifact_dir=out_dir,
    )

    assert result["overall_status"] == "failed"
    completeness = read_tsv(out_dir / "prefix_ratio_matrix_completeness.tsv")
    failed_row = next(
        row
        for row in completeness
        if row["mode"] == "prefix_cache_on"
        and row["input_cap_tokens"] == "131072"
        and row["target_prefix_ratio_pct"] == "90"
    )
    assert failed_row["cell_status"] == "failed"
    assert failed_row["generated_token_count_mismatch_count"] == "1"

    delta_rows = read_tsv(out_dir / "prefix_ratio_matrix_delta_summary.tsv")
    ratio60 = next(row for row in delta_rows if row["input_cap_tokens"] == "8192" and row["target_prefix_ratio_pct"] == "60")
    assert float(ratio60["on_observed_prefix_hit_rate_pct"]) == 47.0
    assert float(ratio60["on_target_vs_observed_prefix_hit_rate_delta_pct"]) == -13.0
    assert float(ratio60["off_observed_prefix_hit_rate_pct"]) == 0.0

    parameter_rows = read_tsv(out_dir / "prefix_ratio_matrix_aisbench_parameters.tsv")
    output_rows = [row for row in parameter_rows if row["performance_parameter"] == "OutputTokens"]
    assert output_rows
    assert all(float(row["Median"]) == 1024.0 for row in output_rows if int(row["N"]) > 0)
