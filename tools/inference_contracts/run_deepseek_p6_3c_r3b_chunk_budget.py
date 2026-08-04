"""P6.3C-R3B Chunked Prefill chunk-budget Pareto experiment.

R3A established a real policy trade-off: a near-full 12272-token chunk removed
long-Prefill admission starvation but produced severe resident Decode stalls.
R3B keeps the staged-arrival workload fixed, treats the legal Off configuration
as a contemporaneous baseline, and scans five On-side scheduler budgets.  The
result is a Pareto comparison, not a strict single-variable A/B.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (  # noqa: E402
    analyze_deepseek_p6_3c_r3a_costs as cost_analysis,
)
from tools.inference_contracts import (  # noqa: E402
    run_deepseek_p6_3c_r3a_decode_resident as r3a,
)


TASK_ID = "p6_3c_r3b_chunk_budget_pareto_2026_0804_run01"
WORKLOAD_RELATIVE_PATH = (
    "benchmarks/deepseek_v4_flash/workloads/p6_3c_r3b_chunk_budget_pareto.yaml"
)
REQUEST_PREFIX = "p6_3c_r3b"
MAX_MODEL_LEN = 12288
MAX_NUM_SEQS = 9
INJECTED_PROMPT_TOKENS = 12281
CONFIGS = (
    {
        "config_id": "off_b12288",
        "mode": "chunked_prefill_off",
        "max_num_batched_tokens": 12288,
    },
    *(
        {
            "config_id": f"on_b{budget}",
            "mode": "chunked_prefill_on",
            "max_num_batched_tokens": budget,
        }
        for budget in (2048, 4096, 6144, 8192, 12288)
    ),
)
CONFIG_BY_ID = {row["config_id"]: row for row in CONFIGS}
ON_CONFIG_IDS = tuple(
    row["config_id"] for row in CONFIGS if row["mode"] == "chunked_prefill_on"
)
TRACKS = ("mechanism", "performance")
MODES = ("chunked_prefill_off", "chunked_prefill_on")


def _build_lifecycle_schedule() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for index, config_id in enumerate(ON_CONFIG_IDS, start=1):
        config = CONFIG_BY_ID[config_id]
        rows.append(
            {
                "track": "mechanism",
                "lifecycle_id": f"mechanism_{index:02d}",
                "mirror_round": "mechanism",
                **config,
            }
        )
    first_round = [row["config_id"] for row in CONFIGS]
    second_round = list(reversed(first_round))
    for index, (mirror_round, config_id) in enumerate(
        [
            *(("round_1", item) for item in first_round),
            *(("round_2", item) for item in second_round),
        ],
        start=1,
    ):
        config = CONFIG_BY_ID[config_id]
        rows.append(
            {
                "track": "performance",
                "lifecycle_id": f"performance_{index:02d}",
                "mirror_round": mirror_round,
                **config,
            }
        )
    return tuple(rows)


LIFECYCLE_SCHEDULE = _build_lifecycle_schedule()
MECHANISM_LIFECYCLES = tuple(
    row for row in LIFECYCLE_SCHEDULE if row["track"] == "mechanism"
)
PERFORMANCE_LIFECYCLES = tuple(
    row for row in LIFECYCLE_SCHEDULE if row["track"] == "performance"
)
PERFORMANCE_CELL_SEQUENCE = (
    "resident_only",
    "admission_cliff_12281",
    "admission_cliff_12281",
    "resident_only",
) * 3
EXPECTED_MODEL_LIFECYCLES = 17
EXPECTED_ENGINE_REQUESTS = 1286
EXPECTED_HTTP_REQUESTS = 243
BOUNDED_CANDIDATES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "payload_identity_summary.json",
    "lifecycle_summary.tsv",
    "r3b_mechanism_budget_summary.json",
    "r3b_mechanism_budget_cells.tsv",
    "r3b_policy_summary.tsv",
    "r3b_policy_paired_effects.tsv",
    "r3b_policy_uncertainty.json",
    "r3b_pareto_frontier.json",
    "scientific_outcome.json",
    "grading_inputs.json",
    "startup_resource_summary.tsv",
    "resource_recovery_summary.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_tsv(
    path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None
) -> None:
    selected_fields = fields or (list(rows[0]) if rows else ["empty"])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=selected_fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in selected_fields})


def _config(config_id: str) -> dict[str, Any]:
    try:
        return CONFIG_BY_ID[config_id]
    except KeyError as error:
        raise ValueError(f"unsupported config: {config_id}") from error


def _lifecycle(lifecycle_id: str) -> dict[str, Any]:
    try:
        return next(
            row for row in LIFECYCLE_SCHEDULE if row["lifecycle_id"] == lifecycle_id
        )
    except StopIteration as error:
        raise ValueError(f"unknown lifecycle: {lifecycle_id}") from error


def _trial_plan(track: str) -> list[dict[str, Any]]:
    sequence = (
        ["admission_cliff_12281"]
        if track == "mechanism"
        else list(PERFORMANCE_CELL_SEQUENCE)
    )
    repeats = {"resident_only": 0, "admission_cliff_12281": 0}
    rows: list[dict[str, Any]] = []
    for order_index, cell_id in enumerate(sequence, start=1):
        repeats[cell_id] += 1
        repeat_index = repeats[cell_id]
        trial_id = f"{REQUEST_PREFIX}_{track}_{cell_id}_r{repeat_index:02d}"
        injected = cell_id == "admission_cliff_12281"
        rows.append(
            {
                "track": track,
                "phase": "measured",
                "order_index": order_index,
                "trial_id": trial_id,
                "cell_id": cell_id,
                "repeat_index": repeat_index,
                "resident_request_id": f"{trial_id}_resident",
                "injected_request_id": f"{trial_id}_injected" if injected else None,
                "injected_prompt_tokens": INJECTED_PROMPT_TOKENS if injected else None,
            }
        )
    return rows


def build_run_plan() -> dict[str, Any]:
    return {
        "warmups": {
            track: {
                "track": track,
                "phase": "warmup",
                "request_id": f"{REQUEST_PREFIX}_{track}_warmup",
                "body_relative_path": f"bodies/{track}_warmup.json",
                "prompt_tokens": 512,
                "output_tokens": 32,
            }
            for track in TRACKS
        },
        "trials": {track: _trial_plan(track) for track in TRACKS},
    }


def prepare_artifacts(
    source_payload: Path, artifact_dir: Path, model_name: str
) -> dict[str, Any]:
    source = json.loads(source_payload.read_text(encoding="utf-8"))
    source_tokens = source.get("prompt")
    if (
        not isinstance(source_tokens, list)
        or len(source_tokens) != 4096
        or not all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in source_tokens
        )
    ):
        raise ValueError("source payload must contain exactly 4096 integer token IDs")
    artifact_dir.mkdir(parents=True, exist_ok=False)
    plan = build_run_plan()
    records: list[dict[str, Any]] = []
    body_index = 0
    for track, warmup in plan["warmups"].items():
        prompt = r3a._repeat_and_truncate(source_tokens, 512, body_index * 131)  # noqa: SLF001
        body_index += 1
        body = r3a._completion_body(  # noqa: SLF001
            model_name=model_name,
            request_id=warmup["request_id"],
            prompts=[prompt],
            output_tokens=32,
        )
        digest, size = r3a._write_body(  # noqa: SLF001
            artifact_dir, warmup["body_relative_path"], body
        )
        warmup["request_body_sha256"] = digest
        records.append(
            {
                "track": track,
                "phase": "warmup",
                "request_role": "warmup",
                "request_id": warmup["request_id"],
                "body_relative_path": warmup["body_relative_path"],
                "body_bytes": size,
                "request_body_sha256": digest,
                "prompt_token_lengths": [512],
                "output_tokens_per_choice": 32,
            }
        )
    for track, trials in plan["trials"].items():
        for trial in trials:
            resident_prompts = [
                r3a._repeat_and_truncate(  # noqa: SLF001
                    source_tokens,
                    r3a.RESIDENT_PROMPT_TOKENS,
                    (body_index * 521 + choice_index * 977) % len(source_tokens),
                )
                for choice_index in range(r3a.RESIDENT_COUNT)
            ]
            resident_relative = f"bodies/{trial['trial_id']}.resident.json"
            resident_body = r3a._completion_body(  # noqa: SLF001
                model_name=model_name,
                request_id=trial["resident_request_id"],
                prompts=resident_prompts,
                output_tokens=r3a.RESIDENT_OUTPUT_TOKENS,
            )
            digest, size = r3a._write_body(  # noqa: SLF001
                artifact_dir, resident_relative, resident_body
            )
            trial["resident_body_relative_path"] = resident_relative
            trial["resident_body_sha256"] = digest
            records.append(
                {
                    "track": track,
                    "phase": "measured",
                    "trial_id": trial["trial_id"],
                    "cell_id": trial["cell_id"],
                    "repeat_index": trial["repeat_index"],
                    "request_role": "resident",
                    "request_id": trial["resident_request_id"],
                    "body_relative_path": resident_relative,
                    "body_bytes": size,
                    "request_body_sha256": digest,
                    "prompt_token_lengths": [r3a.RESIDENT_PROMPT_TOKENS]
                    * r3a.RESIDENT_COUNT,
                    "output_tokens_per_choice": r3a.RESIDENT_OUTPUT_TOKENS,
                }
            )
            if trial["injected_request_id"] is not None:
                injected_prompt = r3a._repeat_and_truncate(  # noqa: SLF001
                    source_tokens,
                    INJECTED_PROMPT_TOKENS,
                    (body_index * 521 + 313) % len(source_tokens),
                )
                relative = f"bodies/{trial['trial_id']}.injected.json"
                body = r3a._completion_body(  # noqa: SLF001
                    model_name=model_name,
                    request_id=trial["injected_request_id"],
                    prompts=[injected_prompt],
                    output_tokens=r3a.INJECTED_OUTPUT_TOKENS,
                )
                injected_digest, injected_size = r3a._write_body(  # noqa: SLF001
                    artifact_dir, relative, body
                )
                trial["injected_body_relative_path"] = relative
                trial["injected_body_sha256"] = injected_digest
                records.append(
                    {
                        "track": track,
                        "phase": "measured",
                        "trial_id": trial["trial_id"],
                        "cell_id": trial["cell_id"],
                        "repeat_index": trial["repeat_index"],
                        "request_role": "injected",
                        "request_id": trial["injected_request_id"],
                        "body_relative_path": relative,
                        "body_bytes": injected_size,
                        "request_body_sha256": injected_digest,
                        "prompt_token_lengths": [INJECTED_PROMPT_TOKENS],
                        "output_tokens_per_choice": r3a.INJECTED_OUTPUT_TOKENS,
                    }
                )
            body_index += 1
    (artifact_dir / "run_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "task_id": TASK_ID,
        "source_prompt_tokens": len(source_tokens),
        "resident_count": r3a.RESIDENT_COUNT,
        "resident_prompt_tokens": r3a.RESIDENT_PROMPT_TOKENS,
        "resident_output_tokens": r3a.RESIDENT_OUTPUT_TOKENS,
        "resident_injection_gate_tokens": r3a.RESIDENT_INJECTION_GATE_TOKENS,
        "injected_prompt_tokens": INJECTED_PROMPT_TOKENS,
        "injected_output_tokens": r3a.INJECTED_OUTPUT_TOKENS,
        "mechanism_trial_count": len(plan["trials"]["mechanism"]),
        "performance_trial_count_per_lifecycle": len(plan["trials"]["performance"]),
        "body_record_count": len(records),
        "bodies_reused_byte_identically_across_all_policy_lifecycles": True,
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
        "records": records,
    }
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def execute_mode(
    artifact_dir: Path,
    lifecycle_dir: Path,
    base_url: str,
    server_pid: int,
    track: str,
    mode: str,
) -> int:
    lifecycle = _lifecycle(lifecycle_dir.name)
    if lifecycle["track"] != track or lifecycle["mode"] != mode:
        raise ValueError("lifecycle track/mode differs from preregistered schedule")
    plan = json.loads((artifact_dir / "run_plan.json").read_text(encoding="utf-8"))
    raw_metrics_dir = lifecycle_dir / "runtime/raw_metrics"
    request_rows: list[dict[str, Any]] = []
    trial_rows: list[dict[str, Any]] = []
    items = [plan["warmups"][track], *plan["trials"][track]]
    for item in items:
        health_before, _ = r3a.base._get(base_url, "/health", timeout=5)  # noqa: SLF001
        idle_before, metrics_before = r3a.base._wait_for_idle(  # noqa: SLF001
            base_url,
            raw_metrics_dir
            / f"{item.get('trial_id', item.get('request_id'))}.before.prom",
        )
        if (
            health_before != 200
            or not idle_before
            or metrics_before.get("spec_metrics_present") is not True
        ):
            rows: list[dict[str, Any]] = []
            trial_row = {
                "track": track,
                "phase": item["phase"],
                "trial_id": item.get("trial_id", item.get("request_id")),
                "cell_id": item.get("cell_id", "warmup"),
                "repeat_index": item.get("repeat_index", 0),
                "status": "failed",
                "failure_reason": "pre_trial_health_queue_or_mtp_metric_gate",
                "request_count": 0,
                "http_request_count": 0,
            }
        elif item["phase"] == "warmup":
            rows, trial_row = r3a._warmup(  # noqa: SLF001
                artifact_dir, base_url, server_pid, item
            )
        else:
            rows, trial_row = r3a.run_staged_trial(
                artifact_dir, base_url, server_pid, item
            )
        health_after, _ = r3a.base._get(base_url, "/health", timeout=5)  # noqa: SLF001
        idle_after, metrics_after = r3a.base._wait_for_idle(  # noqa: SLF001
            base_url,
            raw_metrics_dir
            / f"{item.get('trial_id', item.get('request_id'))}.after.prom",
        )
        spec_delta = {
            name: float(metrics_after.get(name) or 0)
            - float(metrics_before.get(name) or 0)
            for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
        }
        execution_health = (
            health_after == 200
            and idle_after
            and metrics_after.get("queue_metrics_present") is True
            and metrics_after.get("spec_metrics_present") is True
            and spec_delta["num_drafts"] > 0
            and spec_delta["num_draft_tokens"] > 0
            and r3a._process_alive(server_pid)  # noqa: SLF001
        )
        trial_row.update(
            {
                "lifecycle_id": lifecycle_dir.name,
                "mirror_round": lifecycle["mirror_round"],
                "config_id": lifecycle["config_id"],
                "mode": mode,
                "max_num_batched_tokens": lifecycle["max_num_batched_tokens"],
                "server_healthy_and_idle_after": execution_health,
                "mtp_counter_delta": spec_delta,
            }
        )
        if not execution_health:
            trial_row["status"] = "failed"
        for row in rows:
            row.update(
                {
                    "lifecycle_id": lifecycle_dir.name,
                    "mirror_round": lifecycle["mirror_round"],
                    "config_id": lifecycle["config_id"],
                    "mode": mode,
                    "max_num_batched_tokens": lifecycle["max_num_batched_tokens"],
                }
            )
        request_rows.extend(rows)
        trial_rows.append(trial_row)
        r3a._write_jsonl(lifecycle_dir / "raw_request_results.jsonl", request_rows)  # noqa: SLF001
        r3a._write_jsonl(lifecycle_dir / "raw_trial_results.jsonl", trial_rows)  # noqa: SLF001
        if trial_row["status"] != "success":
            break
    expected = {
        "mechanism": {"trials": 2, "requests": 10, "http": 3},
        "performance": {"trials": 13, "requests": 103, "http": 19},
    }[track]
    complete = (
        len(trial_rows) == expected["trials"]
        and len(request_rows) == expected["requests"]
        and sum(int(row.get("http_request_count") or 0) for row in trial_rows)
        == expected["http"]
        and all(row.get("status") == "success" for row in trial_rows)
        and all(row.get("status") == "success" for row in request_rows)
    )
    return 0 if complete else 2


def _read_trace(lifecycle_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (lifecycle_dir / "runtime/scheduler_trace").glob("trace.*.jsonl")
    ):
        rows.extend(r3a._read_jsonl(path))  # noqa: SLF001
    return rows


def mechanism_budget_summary(
    artifact_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trial = _trial_plan("mechanism")[0]
    injection_marker = f"cmpl-{trial['injected_request_id']}"
    resident_marker = f"cmpl-{trial['resident_request_id']}-"
    rows: list[dict[str, Any]] = []
    for lifecycle in MECHANISM_LIFECYCLES:
        trace = _read_trace(artifact_dir / "lifecycles" / lifecycle["lifecycle_id"])
        observer_installed = any(
            row.get("event") == "observer_installed"
            and row.get("schema") == "p6_3c_r3_decode_resident_v1"
            for row in trace
        )
        relevant = [
            row
            for row in trace
            if row.get("event") == "scheduler_step"
            and injection_marker in json.dumps(row, separators=(",", ":"))
        ]
        relevant.sort(key=lambda row: int(row.get("step_index") or 0))
        first = relevant[0] if relevant else {}
        scheduled_rows = [
            item
            for row in relevant
            for item in row.get("scheduled_requests") or []
            if injection_marker in str(item.get("request_id") or "")
            and int(item.get("scheduled_prefill_tokens") or 0) > 0
        ]
        chunk_sizes = [int(item["scheduled_prefill_tokens"]) for item in scheduled_rows]
        first_items = [
            item
            for item in first.get("scheduled_requests") or []
            if injection_marker in str(item.get("request_id") or "")
        ]
        first_tokens = sum(
            int(item.get("scheduled_prefill_tokens") or 0) for item in first_items
        )
        resident_count = sum(
            resident_marker in request_id
            for request_id in first.get("running_order_before") or []
        )
        resident_tokens = int(first.get("resident_decode_tokens") or 0)
        budget = int(lifecycle["max_num_batched_tokens"])
        expected_first_tokens = min(
            INJECTED_PROMPT_TOKENS, max(budget - resident_tokens, 0)
        )
        preempted = sorted(
            {
                str(request_id)
                for row in relevant
                for request_id in row.get("preempted_request_ids") or []
            }
        )
        row = {
            **lifecycle,
            "observer_installed": observer_installed,
            "relevant_step_count": len(relevant),
            "resident_running_count_first_step": resident_count,
            "resident_decode_tokens_first_step": resident_tokens,
            "token_budget_first_step": first.get("token_budget"),
            "expected_injected_tokens_first_step": expected_first_tokens,
            "injected_tokens_first_step": first_tokens,
            "first_step_partial": any(
                item.get("prefill_partial") is True for item in first_items
            ),
            "first_step_mixed": first.get("mixed_decode_prefill"),
            "prefill_chunk_count": len(chunk_sizes),
            "prefill_chunk_sizes": ",".join(str(value) for value in chunk_sizes),
            "observed_prefill_tokens": sum(chunk_sizes),
            "preempted_request_ids": ",".join(preempted),
        }
        row["mechanism_contract_complete"] = all(
            (
                observer_installed,
                bool(relevant),
                resident_count == r3a.RESIDENT_COUNT,
                resident_tokens > 0,
                first.get("token_budget") == budget,
                first_tokens == expected_first_tokens,
                0 < first_tokens < INJECTED_PROMPT_TOKENS,
                row["first_step_partial"] is True,
                row["first_step_mixed"] is True,
                sum(chunk_sizes) == INJECTED_PROMPT_TOKENS,
                not preempted,
            )
        )
        rows.append(row)
    summary = {
        "task_id": TASK_ID,
        "budget_count": len(rows),
        "expected_budget_count": len(ON_CONFIG_IDS),
        "all_budget_mechanisms_complete": len(rows) == len(ON_CONFIG_IDS)
        and all(row["mechanism_contract_complete"] for row in rows),
        "all_first_chunks_equal_remaining_budget": all(
            row["injected_tokens_first_step"]
            == row["expected_injected_tokens_first_step"]
            for row in rows
        ),
        "no_preemption_observed": all(not row["preempted_request_ids"] for row in rows),
        "performance_authorized": len(rows) == len(ON_CONFIG_IDS)
        and all(row["mechanism_contract_complete"] for row in rows),
        "scientific_contract_changed_from_r3a": True,
        "change": "On max_num_batched_tokens sweep; Off baseline remains 12288",
    }
    return summary, rows


def write_mechanism_evidence(artifact_dir: Path) -> dict[str, Any]:
    summary, rows = mechanism_budget_summary(artifact_dir)
    (artifact_dir / "r3b_mechanism_budget_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "mechanism_scheduler_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_tsv(artifact_dir / "r3b_mechanism_budget_cells.tsv", rows)
    return summary


def _enrich_trial(
    trial: dict[str, Any], request_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    residents = [row for row in request_rows if row.get("request_role") == "resident"]
    injected = next(
        (row for row in request_rows if row.get("request_role") == "injected"), None
    )
    dispatch_ns = (trial.get("arrival_contract") or {}).get("injection_dispatch_ns")
    first_injected_ns = (
        min(injected.get("token_arrival_ns") or []) if injected else None
    )
    all_tbt = [
        value
        for resident in residents
        for value in cost_analysis._intervals(resident.get("token_arrival_ns") or [])  # noqa: SLF001
    ]
    interference = [
        value
        for resident in residents
        for value in cost_analysis._intervals(  # noqa: SLF001
            resident.get("token_arrival_ns") or [],
            start_ns=dispatch_ns,
            end_ns=first_injected_ns,
        )
    ]
    summary = cost_analysis._summary(interference)  # noqa: SLF001
    return {
        **trial,
        "resident_all_tbt_values": all_tbt,
        "resident_interference_tbt_values": interference,
        "resident_interference_tbt_p99_ms": summary["p99"],
        "resident_interference_max_stall_ms": summary["max"],
        "resident_all_max_stall_ms": round(max(all_tbt), 6) if all_tbt else None,
    }


def _performance_rows(artifact_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lifecycle in PERFORMANCE_LIFECYCLES:
        root = artifact_dir / "lifecycles" / lifecycle["lifecycle_id"]
        requests_by_trial: dict[str, list[dict[str, Any]]] = {}
        for request in r3a._read_jsonl(root / "raw_request_results.jsonl"):  # noqa: SLF001
            if request.get("phase") == "measured":
                requests_by_trial.setdefault(str(request["trial_id"]), []).append(
                    request
                )
        for trial in r3a._read_jsonl(root / "raw_trial_results.jsonl"):  # noqa: SLF001
            if trial.get("phase") != "measured":
                continue
            rows.append(
                _enrich_trial(trial, requests_by_trial.get(str(trial["trial_id"]), []))
            )
    return rows


def _median(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return round(statistics.median(values), 6) if values else None


def _relative(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return round((new - old) / old, 6)


def performance_evidence(
    artifact_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    trial_rows = _performance_rows(artifact_dir)
    off_resident_only_tbt = [
        value
        for row in trial_rows
        if row["config_id"] == "off_b12288" and row["cell_id"] == "resident_only"
        for value in row["resident_all_tbt_values"]
    ]
    baseline_median_tbt = (
        statistics.median(off_resident_only_tbt) if off_resident_only_tbt else None
    )
    slo_threshold = baseline_median_tbt * 2 if baseline_median_tbt is not None else None
    for row in trial_rows:
        values = (
            row["resident_interference_tbt_values"]
            if row["cell_id"] == "admission_cliff_12281"
            else row["resident_all_tbt_values"]
        )
        row["resident_tbt_slo_attainment"] = (
            sum(value <= slo_threshold for value in values) / len(values)
            if slo_threshold is not None and values
            else None
        )

    summaries: list[dict[str, Any]] = []
    for config in CONFIGS:
        for cell_id in ("resident_only", "admission_cliff_12281"):
            selected = [
                row
                for row in trial_rows
                if row["config_id"] == config["config_id"]
                and row["cell_id"] == cell_id
                and row.get("status") == "success"
            ]
            summaries.append(
                {
                    **config,
                    "cell_id": cell_id,
                    "valid_trial_count": len(selected),
                    "injected_ttft_ms_median": _median(selected, "injected_ttft_ms"),
                    "injected_e2el_ms_median": _median(selected, "injected_e2el_ms"),
                    "resident_interference_tbt_p99_ms_median": _median(
                        selected, "resident_interference_tbt_p99_ms"
                    ),
                    "resident_interference_max_stall_ms_median": _median(
                        selected, "resident_interference_max_stall_ms"
                    ),
                    "resident_all_max_stall_ms_median": _median(
                        selected, "resident_all_max_stall_ms"
                    ),
                    "aggregate_output_tps_median": _median(
                        selected, "aggregate_output_tokens_per_second"
                    ),
                    "resident_tbt_slo_attainment_median": _median(
                        selected, "resident_tbt_slo_attainment"
                    ),
                }
            )

    by_key = {(row["config_id"], row["cell_id"]): row for row in summaries}
    off = by_key[("off_b12288", "admission_cliff_12281")]
    paired: list[dict[str, Any]] = []
    uncertainty: dict[str, Any] = {
        "resident_tbt_slo_definition": {
            "baseline": "Off B=12288 resident-only pooled token intervals",
            "baseline_median_tbt_ms": round(baseline_median_tbt, 6)
            if baseline_median_tbt is not None
            else None,
            "threshold_multiplier": 2.0,
            "threshold_ms": round(slo_threshold, 6)
            if slo_threshold is not None
            else None,
            "status": "project_analysis_threshold_not_external_standard",
        },
        "configs": {},
    }
    metric_fields = (
        "injected_ttft_ms",
        "resident_interference_tbt_p99_ms",
        "resident_interference_max_stall_ms",
        "aggregate_output_tokens_per_second",
        "resident_tbt_slo_attainment",
    )
    for config_id in ON_CONFIG_IDS:
        deltas = {metric: [] for metric in metric_fields}
        for mirror_round in ("round_1", "round_2"):
            for repeat_index in range(1, 7):
                off_trial = next(
                    (
                        row
                        for row in trial_rows
                        if row["config_id"] == "off_b12288"
                        and row["mirror_round"] == mirror_round
                        and row["cell_id"] == "admission_cliff_12281"
                        and int(row["repeat_index"]) == repeat_index
                    ),
                    None,
                )
                on_trial = next(
                    (
                        row
                        for row in trial_rows
                        if row["config_id"] == config_id
                        and row["mirror_round"] == mirror_round
                        and row["cell_id"] == "admission_cliff_12281"
                        and int(row["repeat_index"]) == repeat_index
                    ),
                    None,
                )
                paired_row: dict[str, Any] = {
                    "config_id": config_id,
                    "mirror_round": mirror_round,
                    "repeat_index": repeat_index,
                    "off_lifecycle_id": off_trial.get("lifecycle_id")
                    if off_trial
                    else None,
                    "on_lifecycle_id": on_trial.get("lifecycle_id")
                    if on_trial
                    else None,
                    "valid_pair": bool(
                        off_trial
                        and on_trial
                        and off_trial.get("status")
                        == on_trial.get("status")
                        == "success"
                    ),
                }
                for metric in metric_fields:
                    off_value = off_trial.get(metric) if off_trial else None
                    on_value = on_trial.get(metric) if on_trial else None
                    delta = (
                        float(on_value) - float(off_value)
                        if paired_row["valid_pair"]
                        and off_value is not None
                        and on_value is not None
                        else None
                    )
                    paired_row[f"off_{metric}"] = off_value
                    paired_row[f"on_{metric}"] = on_value
                    paired_row[f"on_minus_off_{metric}"] = delta
                    if delta is not None:
                        deltas[metric].append(delta)
                paired.append(paired_row)
        config_uncertainty: dict[str, Any] = {}
        for metric, values in deltas.items():
            mirror_medians: dict[str, float | None] = {}
            for mirror_round in ("round_1", "round_2"):
                mirror_values = [
                    row[f"on_minus_off_{metric}"]
                    for row in paired
                    if row["config_id"] == config_id
                    and row["mirror_round"] == mirror_round
                    and row.get(f"on_minus_off_{metric}") is not None
                ]
                mirror_medians[mirror_round] = (
                    round(statistics.median(mirror_values), 6)
                    if mirror_values
                    else None
                )
            config_uncertainty[metric] = cost_analysis._bootstrap_median(  # noqa: SLF001
                values
            ) | {"mirror_round_medians": mirror_medians}
        uncertainty["configs"][config_id] = config_uncertainty

    cliff_rows = [row for row in summaries if row["cell_id"] == "admission_cliff_12281"]
    for row in cliff_rows:
        row["ttft_relative_to_off"] = _relative(
            row["injected_ttft_ms_median"], off["injected_ttft_ms_median"]
        )
        row["resident_p99_relative_to_off"] = _relative(
            row["resident_interference_tbt_p99_ms_median"],
            off["resident_interference_tbt_p99_ms_median"],
        )
        row["throughput_relative_to_off"] = _relative(
            row["aggregate_output_tps_median"], off["aggregate_output_tps_median"]
        )
        row["within_preregistered_deployment_bounds"] = all(
            (
                row["ttft_relative_to_off"] is not None
                and row["ttft_relative_to_off"] <= -0.20,
                row["resident_p99_relative_to_off"] is not None
                and row["resident_p99_relative_to_off"] <= 0.10,
                row["throughput_relative_to_off"] is not None
                and row["throughput_relative_to_off"] >= -0.05,
            )
        )

    def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
        minimize = (
            "injected_ttft_ms_median",
            "resident_interference_tbt_p99_ms_median",
            "resident_interference_max_stall_ms_median",
        )
        maximize = (
            "aggregate_output_tps_median",
            "resident_tbt_slo_attainment_median",
        )
        if any(
            left.get(key) is None or right.get(key) is None
            for key in (*minimize, *maximize)
        ):
            return False
        no_worse = all(
            float(left[key]) <= float(right[key]) for key in minimize
        ) and all(float(left[key]) >= float(right[key]) for key in maximize)
        strictly_better = any(
            float(left[key]) < float(right[key]) for key in minimize
        ) or any(float(left[key]) > float(right[key]) for key in maximize)
        return no_worse and strictly_better

    for row in cliff_rows:
        dominators = [
            other["config_id"]
            for other in cliff_rows
            if other is not row and dominates(other, row)
        ]
        row["pareto_nondominated"] = not dominators
        row["dominated_by"] = ",".join(dominators)
    frontier = {
        "task_id": TASK_ID,
        "objective_directions": {
            "injected_ttft_ms_median": "minimize",
            "resident_interference_tbt_p99_ms_median": "minimize",
            "resident_interference_max_stall_ms_median": "minimize",
            "aggregate_output_tps_median": "maximize",
            "resident_tbt_slo_attainment_median": "maximize",
        },
        "pareto_config_ids": [
            row["config_id"] for row in cliff_rows if row["pareto_nondominated"]
        ],
        "deployment_bound_config_ids": [
            row["config_id"]
            for row in cliff_rows
            if row["config_id"] != "off_b12288"
            and row["within_preregistered_deployment_bounds"]
        ],
        "automatic_r3c_selection": False,
        "selection_requires_developer_review": True,
        "rows": cliff_rows,
    }
    public_trial_rows = [
        {key: value for key, value in row.items() if not key.endswith("_values")}
        for row in trial_rows
    ]
    _write_tsv(artifact_dir / "r3b_per_trial_metrics.tsv", public_trial_rows)
    return summaries, paired, uncertainty, frontier


def _startup_rows(artifact_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lifecycle in LIFECYCLE_SCHEDULE:
        path = (
            artifact_dir
            / "lifecycles"
            / lifecycle["lifecycle_id"]
            / "runtime/startup_resource_summary.json"
        )
        if path.is_file():
            rows.append(
                {
                    **lifecycle,
                    **json.loads(path.read_text(encoding="utf-8")),
                }
            )
    return rows


def _lifecycle_rows(artifact_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for expected in LIFECYCLE_SCHEDULE:
        root = artifact_dir / "lifecycles" / expected["lifecycle_id"]
        requests = r3a._read_jsonl(root / "raw_request_results.jsonl")  # noqa: SLF001
        trials = r3a._read_jsonl(root / "raw_trial_results.jsonl")  # noqa: SLF001
        resolved_path = root / "runtime/resolved_scheduler_config.json"
        resolved = (
            json.loads(resolved_path.read_text(encoding="utf-8"))
            if resolved_path.is_file()
            else {}
        )
        cleanup_path = root / "cleanup_status.txt"
        exit_path = root / "lifecycle_exit_code.txt"
        rows.append(
            {
                **expected,
                "request_count": len(requests),
                "successful_request_count": sum(
                    row.get("status") == "success" for row in requests
                ),
                "trial_count": len(trials),
                "successful_trial_count": sum(
                    row.get("status") == "success" for row in trials
                ),
                "http_request_count": sum(
                    int(row.get("http_request_count") or 0) for row in trials
                ),
                "resolved_enable_chunked_prefill": resolved.get(
                    "resolved_enable_chunked_prefill"
                ),
                "resolved_enable_prefix_caching": resolved.get(
                    "resolved_enable_prefix_caching"
                ),
                "resolved_max_model_len": resolved.get("max_model_len"),
                "resolved_max_num_batched_tokens": resolved.get(
                    "max_num_batched_tokens"
                ),
                "resolved_max_num_seqs": resolved.get("max_num_seqs"),
                "observer_enabled": resolved.get("observer_enabled"),
                "cleanup_status": cleanup_path.read_text(encoding="utf-8").strip()
                if cleanup_path.is_file()
                else "missing",
                "lifecycle_exit_code": exit_path.read_text(encoding="utf-8").strip()
                if exit_path.is_file()
                else "missing",
            }
        )
    return rows


def _payload_summary(artifact_dir: Path) -> dict[str, Any]:
    path = artifact_dir / "request_body_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    exact = all(
        (artifact_dir / row["body_relative_path"]).is_file()
        and _sha256_path(artifact_dir / row["body_relative_path"])
        == row["request_body_sha256"]
        for row in manifest["records"]
    )
    return {
        **{key: manifest[key] for key in manifest if key != "records"},
        "manifest_sha256": _sha256_path(path),
        "all_body_files_sha256_exact": exact,
    }


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unavailable"


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    mechanism = write_mechanism_evidence(artifact_dir)
    lifecycle_rows = _lifecycle_rows(artifact_dir)
    summaries, paired, uncertainty, frontier = performance_evidence(artifact_dir)
    payload = _payload_summary(artifact_dir)
    (artifact_dir / "payload_identity_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "r3b_policy_uncertainty.json").write_text(
        json.dumps(uncertainty, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (artifact_dir / "r3b_pareto_frontier.json").write_text(
        json.dumps(frontier, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_tsv(artifact_dir / "r3b_policy_summary.tsv", summaries)
    _write_tsv(artifact_dir / "performance_mode_cell_summary.tsv", summaries)
    _write_tsv(artifact_dir / "r3b_policy_paired_effects.tsv", paired)
    _write_tsv(artifact_dir / "performance_order_balanced_pairs.tsv", paired)
    _write_tsv(artifact_dir / "lifecycle_summary.tsv", lifecycle_rows)
    startup_rows = _startup_rows(artifact_dir)
    _write_tsv(artifact_dir / "startup_resource_summary.tsv", startup_rows)

    mechanism_complete = all(
        row["lifecycle_exit_code"] == "0"
        and row["request_count"] == 10
        and row["successful_request_count"] == 10
        and row["trial_count"] == 2
        and row["successful_trial_count"] == 2
        and row["http_request_count"] == 3
        for row in lifecycle_rows[: len(MECHANISM_LIFECYCLES)]
    )
    performance_complete = all(
        row["lifecycle_exit_code"] == "0"
        and row["request_count"] == 103
        and row["successful_request_count"] == 103
        and row["trial_count"] == 13
        and row["successful_trial_count"] == 13
        and row["http_request_count"] == 19
        for row in lifecycle_rows[len(MECHANISM_LIFECYCLES) :]
    )
    resolved_exact = all(
        row["resolved_enable_chunked_prefill"] == (row["mode"] == "chunked_prefill_on")
        and row["resolved_enable_prefix_caching"] is False
        and row["resolved_max_model_len"] == MAX_MODEL_LEN
        and row["resolved_max_num_batched_tokens"] == row["max_num_batched_tokens"]
        and row["resolved_max_num_seqs"] == MAX_NUM_SEQS
        and row["observer_enabled"] == (row["track"] == "mechanism")
        for row in lifecycle_rows
    )
    observer_absent_performance = all(
        not list(
            (
                artifact_dir
                / "lifecycles"
                / row["lifecycle_id"]
                / "runtime/scheduler_trace"
            ).glob("trace.*.jsonl")
        )
        for row in PERFORMANCE_LIFECYCLES
    )
    request_count = sum(row["request_count"] for row in lifecycle_rows)
    successful_count = sum(row["successful_request_count"] for row in lifecycle_rows)
    http_count = sum(row["http_request_count"] for row in lifecycle_rows)
    startup_complete = len(startup_rows) == EXPECTED_MODEL_LIFECYCLES and all(
        row.get("server_ready") is True for row in startup_rows
    )
    recovery_path = artifact_dir / "resource_recovery_summary.json"
    recovery = (
        json.loads(recovery_path.read_text(encoding="utf-8"))
        if recovery_path.is_file()
        else {}
    )
    global_cleanup = (
        (artifact_dir / "cleanup_status.txt").read_text(encoding="utf-8").strip()
        if (artifact_dir / "cleanup_status.txt").is_file()
        else "missing"
    )
    cleanup_complete = (
        all(row["cleanup_status"] == "clean" for row in lifecycle_rows)
        and recovery.get("keep_alive_restored_exact") is True
        and global_cleanup == "clean"
    )
    evidence_complete = all(
        (
            mechanism_complete,
            mechanism["all_budget_mechanisms_complete"],
            performance_complete,
            resolved_exact,
            observer_absent_performance,
            payload["all_body_files_sha256_exact"],
            request_count == successful_count == EXPECTED_ENGINE_REQUESTS,
            http_count == EXPECTED_HTTP_REQUESTS,
            startup_complete,
            cleanup_complete,
        )
    )
    if not mechanism["all_budget_mechanisms_complete"]:
        scientific = "chunk_budget_mechanism_incomplete"
    elif not performance_complete:
        scientific = "chunk_budget_performance_incomplete"
    elif frontier["deployment_bound_config_ids"]:
        scientific = "pareto_candidate_found_within_preregistered_bounds"
    else:
        scientific = "pareto_frontier_observed_no_candidate_within_bounds"
    outcome = {
        "task_id": TASK_ID,
        "scientific_outcome": scientific,
        "evidence_complete": evidence_complete,
        "mechanism_all_budgets_complete": mechanism["all_budget_mechanisms_complete"],
        "pareto_config_ids": frontier["pareto_config_ids"],
        "deployment_bound_config_ids": frontier["deployment_bound_config_ids"],
        "automatic_r3c_selection": False,
        "claim_boundary": "controlled_decode_resident_admission_cliff_policy_calibration_only",
    }
    (artifact_dir / "scientific_outcome.json").write_text(
        json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    grading = {
        "task_id": TASK_ID,
        "evidence_status": "complete" if evidence_complete else "incomplete",
        "scientific_outcome": scientific,
        "server_grade": "complete_p6_3c_r3b_policy_evidence"
        if evidence_complete
        else "incomplete_p6_3c_r3b_policy_evidence",
        "parent_r3a_outcome_preserved": "mechanism_confirmed_tradeoff_only",
        "parent_results_overwritten": False,
        "scientific_contract_changed_from_r3a": True,
        "mechanism_lifecycles_complete": mechanism_complete,
        "mechanism_all_budgets_complete": mechanism["all_budget_mechanisms_complete"],
        "performance_lifecycles_complete": performance_complete,
        "resolved_config_exact": resolved_exact,
        "observer_absent_performance": observer_absent_performance,
        "payload_identity_exact": payload["all_body_files_sha256_exact"],
        "request_count": request_count,
        "successful_request_count": successful_count,
        "expected_request_count": EXPECTED_ENGINE_REQUESTS,
        "http_request_count": http_count,
        "expected_http_request_count": EXPECTED_HTTP_REQUESTS,
        "startup_complete": startup_complete,
        "cleanup_complete": cleanup_complete,
        "keep_alive_restore_exact": recovery.get("keep_alive_restored_exact"),
        "pareto_config_ids": frontier["pareto_config_ids"],
        "deployment_bound_config_ids": frontier["deployment_bound_config_ids"],
        "developer_review_required": True,
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "next_task_authorized": False,
        "universal_benefit_claimed": False,
    }
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    environment = {
        "task_id": TASK_ID,
        "repo_head": _git_output("rev-parse", "HEAD"),
        "repo_origin_main": _git_output("rev-parse", "origin/main"),
        "workload_path": WORKLOAD_RELATIVE_PATH,
        "workload_sha256": _sha256_path(REPO_ROOT / WORKLOAD_RELATIVE_PATH),
        "runner_sha256": _sha256_path(Path(__file__)),
        "observer_sha256": _sha256_path(
            REPO_ROOT / "tools/inference_contracts/p6_3c_r3_decode_resident_observer.py"
        ),
        "max_model_len": MAX_MODEL_LEN,
        "max_num_seqs": MAX_NUM_SEQS,
        "off_budget": 12288,
        "on_budgets": [2048, 4096, 6144, 8192, 12288],
        "prefix_cache_enabled": False,
        "observer_enabled_tracks": ["mechanism"],
        "profiler_enabled": False,
        "generated_text_retained": False,
        "generated_token_ids_retained": False,
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        f"# {TASK_ID} 结果摘要",
        "",
        f"- evidence status: `{grading['evidence_status']}`",
        f"- scientific outcome: `{scientific}`",
        f"- 五个 On budget 的机制校准完整：`{mechanism['all_budget_mechanisms_complete']}`。",
        f"- 请求 `{successful_count}/{EXPECTED_ENGINE_REQUESTS}`；HTTP `{http_count}/{EXPECTED_HTTP_REQUESTS}`；keep-alive 精确恢复 `{recovery.get('keep_alive_restored_exact')}`。",
        "",
        "## Pareto 结论",
        "",
        f"- 非支配配置：`{frontier['pareto_config_ids']}`。",
        f"- 同时满足 TTFT 至少改善 20%、resident P99 TBT 增幅不超过 10%、吞吐下降不超过 5% 的 On 配置：`{frontier['deployment_bound_config_ids']}`。",
        "- 不自动进入 R3C；由开发机结合完整 effect size 与 lifecycle-pair 一致性选择候选。",
        "",
        "## 结论边界",
        "",
        "- R3B 是 On-side budget policy comparison，不是 strict single-variable A/B。",
        "- 结论只覆盖受控 decode-resident admission-cliff，不外推自然 API 流量或生产 SLO。",
        "- R3A、F4 与原 135168/4096/1 blocked 审计均保留。",
        "- 未经用户选择 email / upload-api / server-local，不传输候选结果。",
        "",
    ]
    (artifact_dir / "result_summary.md").write_text("\n".join(lines), encoding="utf-8")
    failure_path = artifact_dir / "first_failure_excerpt.txt"
    if evidence_complete:
        failure_path.write_text("none\n", encoding="utf-8")
    elif not failure_path.is_file():
        failure_path.write_text(
            f"mechanism_complete={mechanism['all_budget_mechanisms_complete']}\n"
            f"performance_complete={performance_complete}\n"
            f"successful_request_count={successful_count}/{EXPECTED_ENGINE_REQUESTS}\n",
            encoding="utf-8",
        )
    return grading


def package_results(artifact_dir: Path) -> dict[str, Any]:
    candidates = []
    for name in BOUNDED_CANDIDATES:
        path = artifact_dir / name
        if path.is_file():
            candidates.append(
                {
                    "path": name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_path(path),
                    "sensitivity": "internal_project_evidence_no_generated_content",
                }
            )
    total_bytes = sum(row["bytes"] for row in candidates)
    manifest = {
        "task_id": TASK_ID,
        "result_summary_path": str(artifact_dir / "result_summary.md"),
        "result_transfer_authorized": True,
        "transfer_method_selected": False,
        "automatic_transfer_allowed": False,
        "available_methods": ["email", "upload-api", "server-local"],
        "recommended_method": "upload-api",
        "recommended_reason": "atomic_multi_file_session_with_hash_validation",
        "bounded_transfer_max_bytes": 71680,
        "candidate_file_count": len(candidates),
        "candidate_total_bytes": total_bytes,
        "candidate_total_within_limit": total_bytes <= 71680,
        "candidates": candidates,
        "raw_token_timestamps_scheduler_traces_and_logs_remain_server_local": True,
        "selection_required_before_any_transfer": True,
    }
    (artifact_dir / "candidate_manifest.server_local.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_tsv(
        artifact_dir / "delivery_candidates.tsv",
        candidates,
        ["path", "bytes", "sha256", "sensitivity"],
    )
    if total_bytes > 71680:
        raise ValueError(f"bounded candidates exceed 70KB: {total_bytes}")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    run_mode = sub.add_parser("run-mode")
    run_mode.add_argument("--artifact-dir", type=Path, required=True)
    run_mode.add_argument("--lifecycle-dir", type=Path, required=True)
    run_mode.add_argument("--base-url", required=True)
    run_mode.add_argument("--server-pid", type=int, required=True)
    run_mode.add_argument("--track", choices=TRACKS, required=True)
    run_mode.add_argument("--mode", choices=MODES, required=True)
    gate = sub.add_parser("mechanism-gate")
    gate.add_argument("--artifact-dir", type=Path, required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    package = sub.add_parser("package")
    package.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
    if args.command == "mechanism-gate":
        summary = write_mechanism_evidence(args.artifact_dir)
        return 0 if summary["performance_authorized"] else 3
    if args.command == "finalize":
        grading = finalize_artifacts(args.artifact_dir)
        return 0 if grading["evidence_status"] == "complete" else 2
    if args.command == "package":
        package_results(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
