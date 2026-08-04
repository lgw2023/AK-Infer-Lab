"""Zero-NPU paired cost analysis for the completed P6.3C-R3A run.

The original R3A finalizer correctly established the admission-cliff TTFT
effect, but its bounded result package retained only aggregate cost medians.
This analyzer works in place over the server-local raw JSONL and exports a
small, manuscript-ready account of resident Decode interference.  It never
starts vLLM, touches an NPU, or modifies the source result directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics
from typing import Any, Iterable


SOURCE_TASK_ID = "p6_3c_r3a_decode_resident_admission_cliff_2026_0803_run01"
ANALYSIS_ID = "p6_3c_r3a_cost_reanalysis_2026_0804"
PERFORMANCE_LIFECYCLES = {
    "performance_01": {"mode": "chunked_prefill_off", "pair_id": "pair_01"},
    "performance_02": {"mode": "chunked_prefill_on", "pair_id": "pair_01"},
    "performance_03": {"mode": "chunked_prefill_on", "pair_id": "pair_02"},
    "performance_04": {"mode": "chunked_prefill_off", "pair_id": "pair_02"},
}
METRICS = (
    "injected_ttft_ms",
    "resident_interference_tbt_p99_ms",
    "resident_interference_max_stall_ms",
    "resident_all_max_stall_ms",
    "aggregate_output_tokens_per_second",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "median": None, "p95": None, "p99": None, "max": None}
    return {
        "n": len(values),
        "median": round(statistics.median(values), 6),
        "p95": round(_percentile(values, 0.95), 6),
        "p99": round(_percentile(values, 0.99), 6),
        "max": round(max(values), 6),
    }


def _intervals(
    arrivals: Iterable[int],
    *,
    start_ns: int | None = None,
    end_ns: int | None = None,
) -> list[float]:
    timestamps = list(arrivals)
    result: list[float] = []
    for left, right in zip(timestamps, timestamps[1:]):
        if start_ns is not None and right < start_ns:
            continue
        if end_ns is not None and right > end_ns:
            continue
        result.append((right - left) / 1_000_000)
    return result


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _bootstrap_median(
    values: list[float], *, samples: int = 10000, seed: int = 633
) -> dict[str, Any]:
    if not values:
        return {"n": 0, "median": None, "ci95_low": None, "ci95_high": None}
    rng = random.Random(seed)
    draws = [
        statistics.median([values[rng.randrange(len(values))] for _ in values])
        for _ in range(samples)
    ]
    return {
        "n": len(values),
        "median": round(statistics.median(values), 6),
        "ci95_low": round(_percentile(draws, 0.025), 6),
        "ci95_high": round(_percentile(draws, 0.975), 6),
        "samples": samples,
        "seed": seed,
        "unit": "trial_pair",
        "independence_caveat": "six trials share each fresh-model lifecycle pair",
    }


def validate_source(source_result: Path) -> dict[str, Any]:
    grading_path = source_result / "grading_inputs.json"
    grading = json.loads(grading_path.read_text(encoding="utf-8"))
    checks = {
        "source_task_id_exact": grading.get("task_id") == SOURCE_TASK_ID,
        "source_evidence_complete": grading.get("evidence_complete") is True,
        "source_mechanism_complete": grading.get("r3_s0_gate_complete") is True,
        "source_performance_complete": grading.get("performance_lifecycles_complete")
        is True,
        "source_cleanup_complete": grading.get("cleanup_complete") is True,
    }
    lifecycle_counts: dict[str, dict[str, int]] = {}
    for lifecycle_id in PERFORMANCE_LIFECYCLES:
        root = source_result / "lifecycles" / lifecycle_id
        trials = _read_jsonl(root / "raw_trial_results.jsonl")
        requests = _read_jsonl(root / "raw_request_results.jsonl")
        lifecycle_counts[lifecycle_id] = {
            "trial_rows": len(trials),
            "request_rows": len(requests),
        }
        checks[f"{lifecycle_id}_raw_counts_exact"] = (
            len(trials) == 19 and len(requests) == 157
        )
    return {
        "source_task_id": SOURCE_TASK_ID,
        "source_result": str(source_result.resolve()),
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "lifecycle_counts": lifecycle_counts,
        "grading_inputs_sha256": _sha256_path(grading_path),
        "npu_operations": 0,
        "source_result_modified": False,
    }


def build_trial_metrics(source_result: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lifecycle_id, lifecycle in PERFORMANCE_LIFECYCLES.items():
        root = source_result / "lifecycles" / lifecycle_id
        trials = {
            str(row["trial_id"]): row
            for row in _read_jsonl(root / "raw_trial_results.jsonl")
            if row.get("phase") == "measured"
        }
        requests_by_trial: dict[str, list[dict[str, Any]]] = {}
        for request in _read_jsonl(root / "raw_request_results.jsonl"):
            if request.get("phase") != "measured":
                continue
            requests_by_trial.setdefault(str(request["trial_id"]), []).append(request)

        for trial_id, trial in trials.items():
            request_rows = requests_by_trial.get(trial_id, [])
            residents = [
                row for row in request_rows if row.get("request_role") == "resident"
            ]
            injected = next(
                (row for row in request_rows if row.get("request_role") == "injected"),
                None,
            )
            dispatch_ns = (trial.get("arrival_contract") or {}).get(
                "injection_dispatch_ns"
            )
            first_injected_ns = (
                min(injected.get("token_arrival_ns") or []) if injected else None
            )
            all_tbt = [
                value
                for resident in residents
                for value in _intervals(resident.get("token_arrival_ns") or [])
            ]
            pre_tbt = [
                value
                for resident in residents
                for value in _intervals(
                    resident.get("token_arrival_ns") or [], end_ns=dispatch_ns
                )
            ]
            interference_tbt = [
                value
                for resident in residents
                for value in _intervals(
                    resident.get("token_arrival_ns") or [],
                    start_ns=dispatch_ns,
                    end_ns=first_injected_ns,
                )
            ]
            recovery_tbt = [
                value
                for resident in residents
                for value in _intervals(
                    resident.get("token_arrival_ns") or [], start_ns=first_injected_ns
                )
            ]
            pre = _summary(pre_tbt)
            interference = _summary(interference_tbt)
            recovery = _summary(recovery_tbt)
            rows.append(
                {
                    "lifecycle_id": lifecycle_id,
                    "pair_id": lifecycle["pair_id"],
                    "mode": lifecycle["mode"],
                    "trial_id": trial_id,
                    "cell_id": trial.get("cell_id"),
                    "repeat_index": int(trial.get("repeat_index") or 0),
                    "status": trial.get("status"),
                    "injected_ttft_ms": trial.get("injected_ttft_ms"),
                    "resident_pre_tbt_p99_ms": pre["p99"],
                    "resident_interference_tbt_p50_ms": interference["median"],
                    "resident_interference_tbt_p95_ms": interference["p95"],
                    "resident_interference_tbt_p99_ms": interference["p99"],
                    "resident_interference_max_stall_ms": interference["max"],
                    "resident_recovery_tbt_p99_ms": recovery["p99"],
                    "resident_all_max_stall_ms": round(max(all_tbt), 6)
                    if all_tbt
                    else None,
                    "interference_over_pre_p99": (
                        round(float(interference["p99"]) / float(pre["p99"]), 6)
                        if interference["p99"] is not None
                        and pre["p99"] not in (None, 0)
                        else None
                    ),
                    "aggregate_output_tokens_per_second": trial.get(
                        "aggregate_output_tokens_per_second"
                    ),
                    "resident_request_count": len(residents),
                    "raw_interval_count": len(all_tbt),
                }
            )
    return rows


def build_paired_effects(
    trial_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key = {
        (
            row["pair_id"],
            row["mode"],
            row["cell_id"],
            row["repeat_index"],
        ): row
        for row in trial_rows
    }
    paired: list[dict[str, Any]] = []
    deltas: dict[str, dict[str, list[float]]] = {}
    for pair_id in ("pair_01", "pair_02"):
        for cell_id in ("fit_control_12000", "admission_cliff_12281"):
            for repeat_index in range(1, 7):
                off = by_key.get(
                    (pair_id, "chunked_prefill_off", cell_id, repeat_index)
                )
                on = by_key.get((pair_id, "chunked_prefill_on", cell_id, repeat_index))
                valid = bool(
                    off
                    and on
                    and off.get("status") == "success"
                    and on.get("status") == "success"
                )
                row: dict[str, Any] = {
                    "pair_id": pair_id,
                    "cell_id": cell_id,
                    "repeat_index": repeat_index,
                    "valid_pair": valid,
                }
                for metric in METRICS:
                    off_value = off.get(metric) if off else None
                    on_value = on.get(metric) if on else None
                    delta = (
                        float(on_value) - float(off_value)
                        if valid and off_value is not None and on_value is not None
                        else None
                    )
                    row[f"off_{metric}"] = off_value
                    row[f"on_{metric}"] = on_value
                    row[f"on_minus_off_{metric}"] = delta
                    if delta is not None:
                        deltas.setdefault(cell_id, {}).setdefault(metric, []).append(
                            delta
                        )
                paired.append(row)

    uncertainty: dict[str, Any] = {}
    for cell_id, metric_values in deltas.items():
        uncertainty[cell_id] = {}
        for metric, values in metric_values.items():
            pair_blocks = {
                pair_id: [
                    row[f"on_minus_off_{metric}"]
                    for row in paired
                    if row["pair_id"] == pair_id
                    and row["cell_id"] == cell_id
                    and row.get(f"on_minus_off_{metric}") is not None
                ]
                for pair_id in ("pair_01", "pair_02")
            }
            uncertainty[cell_id][metric] = {
                "trial_pair_bootstrap": _bootstrap_median(values),
                "fresh_model_pair_medians": {
                    pair_id: (round(statistics.median(block), 6) if block else None)
                    for pair_id, block in pair_blocks.items()
                },
            }
    return paired, uncertainty


def analyze(source_result: Path, output_dir: Path) -> dict[str, Any]:
    validation = validate_source(source_result)
    if not validation["all_checks_pass"]:
        raise ValueError("R3A raw source validation failed")
    output_dir.mkdir(parents=True, exist_ok=False)
    trial_rows = build_trial_metrics(source_result)
    paired_rows, uncertainty = build_paired_effects(trial_rows)
    _write_tsv(output_dir / "r3a_cost_trial_metrics.tsv", trial_rows)
    _write_tsv(output_dir / "r3a_cost_paired_effects.tsv", paired_rows)
    (output_dir / "r3a_cost_uncertainty.json").write_text(
        json.dumps(uncertainty, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    provenance = {
        "analysis_id": ANALYSIS_ID,
        **validation,
        "trial_metric_rows": len(trial_rows),
        "paired_effect_rows": len(paired_rows),
        "metric_definition_correction": (
            "resident maximum stall is the maximum adjacent token-arrival gap, "
            "not the maximum of per-request ITL p99"
        ),
        "statistical_scope": (
            "trial-pair bootstrap is descriptive because six trials share each "
            "fresh-model lifecycle pair; both lifecycle-pair medians are reported"
        ),
    }
    (output_dir / "analysis_provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    cliff = uncertainty["admission_cliff_12281"]
    lines = [
        "# P6.3C-R3A resident Decode 代价侧配对复分析",
        "",
        "本分析只读取既有 R3A raw JSONL，不启动 vLLM、不触发 NPU，也不修改源结果。",
        "它把每个 resident choice 的 token arrival 重建为真实相邻 token gap，并按",
        "Off→On 与 On→Off 两个 fresh-model 生命周期对重新配对。",
        "",
        "## 解释边界",
        "",
        "- `resident_interference_max_stall_ms` 是干扰窗口内真实最大相邻 token gap。",
        "- trial-pair bootstrap 只作描述；六个 trial 共享同一个 fresh-model lifecycle。",
        "- 两个 lifecycle-pair 的中位效应分别保留，用于判断方向是否依赖单次模型生命周期。",
        "- 该分析不改变 R3A 的 `mechanism_confirmed_tradeoff_only` 结论，只补足代价侧证据。",
        "",
        "## admission-cliff 核心配对字段",
        "",
    ]
    for metric in METRICS:
        item = cliff.get(metric, {})
        lines.append(
            f"- `{metric}`: {json.dumps(item, sort_keys=True, ensure_ascii=False)}"
        )
    (output_dir / "r3a_cost_review.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    candidate_names = (
        "r3a_cost_review.md",
        "analysis_provenance.json",
        "r3a_cost_uncertainty.json",
        "r3a_cost_paired_effects.tsv",
        "r3a_cost_trial_metrics.tsv",
    )
    candidates = [
        {
            "path": name,
            "bytes": (output_dir / name).stat().st_size,
            "sha256": _sha256_path(output_dir / name),
            "sensitivity": "internal_project_evidence_no_generated_content",
        }
        for name in candidate_names
    ]
    total_bytes = sum(item["bytes"] for item in candidates)
    candidate_manifest = {
        "analysis_id": ANALYSIS_ID,
        "source_task_id": SOURCE_TASK_ID,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "automatic_transfer_allowed": False,
        "available_methods": ["email", "upload-api", "server-local"],
        "recommended_method": "upload-api",
        "bounded_transfer_max_bytes": 71680,
        "candidate_file_count": len(candidates),
        "candidate_total_bytes": total_bytes,
        "candidate_total_within_limit": total_bytes <= 71680,
        "candidates": candidates,
        "source_raw_result_remains_server_local": True,
        "selection_required_before_any_transfer": True,
    }
    (output_dir / "candidate_manifest.server_local.json").write_text(
        json.dumps(candidate_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if total_bytes > 71680:
        raise ValueError(f"bounded R3A cost package exceeds 70KB: {total_bytes}")
    return provenance


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-result", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validation = validate_source(args.source_result)
    if args.validate_only:
        print(json.dumps(validation, indent=2, sort_keys=True))
        return 0 if validation["all_checks_pass"] else 2
    if args.output_dir is None:
        raise SystemExit("--output-dir is required unless --validate-only is used")
    provenance = analyze(args.source_result, args.output_dir)
    print(json.dumps(provenance, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
