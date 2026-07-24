from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from tools.inference_contracts.run_deepseek_p6_1_unprofiled_baseline import (
    _get,
    _process_alive,
    _repeat_and_truncate,
    _select_offsets,
    _stream_request,
)


MODES = ("prefix_cache_off", "prefix_cache_on")
CONTEXTS = (4096, 32768, 65536, 131072)
PREFIX_RATIOS = (50, 90)
OUTPUT_TOKENS = 64
BLOCK_SIZE = 128
METRIC_NAMES = {
    "vllm:num_requests_running": "num_requests_running",
    "vllm:num_requests_waiting": "num_requests_waiting",
    "vllm:prefix_cache_queries": "prefix_queries",
    "vllm:prefix_cache_queries_total": "prefix_queries",
    "vllm:prefix_cache_hits": "prefix_hits",
    "vllm:prefix_cache_hits_total": "prefix_hits",
    "vllm:spec_decode_num_drafts_total": "num_drafts",
    "vllm:spec_decode_num_draft_tokens_total": "num_draft_tokens",
    "vllm:spec_decode_num_accepted_tokens_total": "num_accepted_tokens",
}


def build_run_plan() -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for context_tokens in CONTEXTS:
        for ratio_pct in PREFIX_RATIOS:
            group_id = f"ctx{context_tokens}_prefix{ratio_pct}"
            shared_tokens = (
                context_tokens * ratio_pct // 100 // BLOCK_SIZE * BLOCK_SIZE
            )
            for role_index in range(4):
                request_role = "prime" if role_index == 0 else "measured"
                repeat_index = 0 if request_role == "prime" else role_index
                plan.append(
                    {
                        "request_id": (
                            f"{group_id}_{request_role}_"
                            f"{1 if request_role == 'prime' else repeat_index:02d}"
                        ),
                        "group_id": group_id,
                        "request_role": request_role,
                        "repeat_index": repeat_index,
                        "context_tokens": context_tokens,
                        "output_tokens": OUTPUT_TOKENS,
                        "target_shared_prefix_ratio_pct": ratio_pct,
                        "target_shared_prefix_tokens": shared_tokens,
                    }
                )
    return plan


def _common_prefix_length(left: list[int], right: list[int]) -> int:
    for index, (left_token, right_token) in enumerate(zip(left, right)):
        if left_token != right_token:
            return index
    return min(len(left), len(right))


def prepare_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
    *,
    plan: list[dict[str, Any]] | None = None,
    authorized_identical_body_request_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    source = json.loads(source_payload.read_text(encoding="utf-8"))
    source_tokens = source.get("prompt")
    if not isinstance(source_tokens, list) or len(source_tokens) != 4096:
        raise ValueError("source payload must contain exactly 4096 prompt token IDs")
    if not all(
        isinstance(token, int) and not isinstance(token, bool)
        for token in source_tokens
    ):
        raise ValueError("source prompt must contain integer token IDs")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    body_dir = artifact_dir / "bodies"
    body_dir.mkdir(parents=True, exist_ok=True)
    plan = build_run_plan() if plan is None else plan
    selected_offsets = _select_offsets(source_tokens, 40)
    group_offsets = iter(offset for offset, _ in selected_offsets[:8])
    suffix_offsets = iter(offset for offset, _ in selected_offsets[8:])
    records: list[dict[str, Any]] = []

    for group_id in dict.fromkeys(item["group_id"] for item in plan):
        group_rows = [item for item in plan if item["group_id"] == group_id]
        group_offset = next(group_offsets)
        shared_tokens = int(group_rows[0]["target_shared_prefix_tokens"])
        shared_prefix = _repeat_and_truncate(
            source_tokens,
            shared_tokens,
            group_offset,
        )
        prompts: list[list[int]] = []
        for row in group_rows:
            suffix_tokens = int(row["context_tokens"]) - shared_tokens
            suffix = _repeat_and_truncate(
                source_tokens,
                suffix_tokens,
                next(suffix_offsets),
            )
            prompt = shared_prefix + suffix
            prompts.append(prompt)
            body = {
                "ignore_eos": True,
                "max_tokens": int(row["output_tokens"]),
                "min_tokens": int(row["output_tokens"]),
                "model": model_name,
                "prompt": prompt,
                "return_token_ids": True,
                "stream": True,
                "stream_options": {"include_usage": True},
                "temperature": 0.0,
            }
            raw = json.dumps(
                body,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            relative_path = Path("bodies") / f"{row['request_id']}.json"
            (artifact_dir / relative_path).write_bytes(raw)
            row["body_relative_path"] = str(relative_path)
            row["request_body_sha256"] = hashlib.sha256(raw).hexdigest()
            row["body_bytes"] = len(raw)

        prime_prompt = prompts[0]
        for row, prompt in zip(group_rows, prompts):
            actual_shared = (
                0
                if row["request_role"] == "prime"
                else _common_prefix_length(prime_prompt, prompt)
            )
            if row["request_role"] == "measured" and not (
                shared_tokens <= actual_shared < shared_tokens + BLOCK_SIZE
            ):
                raise ValueError(
                    f"shared-prefix construction drift for {row['request_id']}: "
                    f"expected [{shared_tokens}, {shared_tokens + BLOCK_SIZE}), "
                    f"got {actual_shared}"
                )
            records.append(
                {
                    key: row[key]
                    for key in (
                        "request_id",
                        "group_id",
                        "request_role",
                        "repeat_index",
                        "context_tokens",
                        "output_tokens",
                        "target_shared_prefix_ratio_pct",
                        "target_shared_prefix_tokens",
                        "body_relative_path",
                        "body_bytes",
                        "request_body_sha256",
                    )
                }
                | {"actual_shared_prefix_tokens": actual_shared}
            )

    body_hashes = [str(row["request_body_sha256"]) for row in records]
    if authorized_identical_body_request_ids:
        authorized_ids = set(authorized_identical_body_request_ids)
        by_id = {str(row["request_id"]): row for row in records}
        missing = sorted(authorized_ids - by_id.keys())
        if missing:
            raise ValueError(
                "authorized identical body request ids are missing: "
                + ", ".join(missing)
            )
        authorized_hashes = {
            str(by_id[request_id]["request_body_sha256"])
            for request_id in authorized_ids
        }
        if len(authorized_hashes) != 1:
            raise ValueError(
                "authorized identical body request ids must share one hash"
            )
        shared_hash = next(iter(authorized_hashes))
        other_hashes = [
            str(row["request_body_sha256"])
            for row in records
            if str(row["request_id"]) not in authorized_ids
        ]
        if shared_hash in other_hashes:
            raise ValueError(
                "authorized identical body hash leaked outside the pair"
            )
        if len(set(other_hashes)) != len(other_hashes):
            raise ValueError("request body hashes are not unique")
    elif len(set(body_hashes)) != len(body_hashes):
        raise ValueError("request body hashes are not unique")
    manifest = {
        "source_prompt_tokens": len(source_tokens),
        "group_count": len({row["group_id"] for row in records}),
        "request_count": len(records),
        "mode_order": list(MODES),
        "modes_reuse_identical_body_bytes": True,
        "cross_group_common_prefix_tokens_less_than": BLOCK_SIZE,
        "shared_prefix_block_aligned": True,
        "authorized_identical_body_request_ids": sorted(
            authorized_identical_body_request_ids or ()
        ),
        "generated_text_retained": False,
        "token_ids_retained": False,
        "records": records,
    }
    (artifact_dir / "run_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_metrics(raw: bytes) -> dict[str, Any]:
    aliases = set(METRIC_NAMES.values())
    values = {alias: 0.0 for alias in aliases}
    found = {alias: False for alias in aliases}
    for raw_line in raw.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        alias = METRIC_NAMES.get(parts[0].split("{", 1)[0])
        if alias is None:
            continue
        try:
            values[alias] += float(parts[1])
            found[alias] = True
        except ValueError:
            continue
    values["queue_metrics_present"] = (
        found["num_requests_running"] and found["num_requests_waiting"]
    )
    values["prefix_metrics_present"] = (
        found["prefix_queries"] and found["prefix_hits"]
    )
    values["spec_metrics_present"] = all(
        found[name]
        for name in ("num_drafts", "num_draft_tokens", "num_accepted_tokens")
    )
    return values


def grade_evidence(
    request_rows: list[dict[str, Any]],
    *,
    cleanup_by_mode: dict[str, str],
) -> dict[str, Any]:
    prime_rows = [row for row in request_rows if row.get("request_role") == "prime"]
    measured_rows = [
        row for row in request_rows if row.get("request_role") == "measured"
    ]
    successful = [row for row in request_rows if row.get("status") == "success"]
    expected_groups = {item["group_id"] for item in build_run_plan()}
    represented_by_mode = {
        mode: {
            str(row.get("group_id"))
            for row in successful
            if row.get("mode") == mode
        }
        for mode in MODES
    }
    all_groups_matched = all(
        represented_by_mode[mode] == expected_groups for mode in MODES
    )
    bodies_by_mode = {
        mode: {
            str(row.get("request_id")): str(row.get("request_body_sha256"))
            for row in request_rows
            if row.get("mode") == mode
        }
        for mode in MODES
    }
    body_pairing_ok = (
        len(bodies_by_mode["prefix_cache_off"]) == 32
        and bodies_by_mode["prefix_cache_off"]
        == bodies_by_mode["prefix_cache_on"]
    )
    on_measured = [
        row
        for row in measured_rows
        if row.get("mode") == "prefix_cache_on"
    ]
    on_positive_hits = sum(
        float(row.get("prefix_hits_delta") or 0.0) > 0 for row in on_measured
    )
    on_hits_total = sum(
        float(row.get("prefix_hits_delta") or 0.0)
        for row in request_rows
        if row.get("mode") == "prefix_cache_on"
    )
    off_hits_total = sum(
        float(row.get("prefix_hits_delta") or 0.0)
        for row in request_rows
        if row.get("mode") == "prefix_cache_off"
    )
    accepted_by_mode = {
        mode: sum(
            float(row.get("accepted_token_delta") or 0.0)
            for row in request_rows
            if row.get("mode") == mode
        )
        for mode in MODES
    }
    structural_complete = (
        len(request_rows) == 64
        and len(successful) == 64
        and len(prime_rows) == 16
        and len(measured_rows) == 48
        and all_groups_matched
        and body_pairing_ok
    )
    evidence_complete = (
        all(row.get("queue_metrics_ok") is True for row in request_rows)
        and all(row.get("counter_continuity_ok") is True for row in request_rows)
        and all(row.get("spec_activity_ok") is True for row in request_rows)
        and all(row.get("prefix_evidence_ok") is True for row in request_rows)
        and on_positive_hits == 24
        and on_hits_total > 0
        and off_hits_total == 0
        and all(value > 0 for value in accepted_by_mode.values())
    )
    any_measured_success = any(row in successful for row in measured_rows)

    if any(cleanup_by_mode.get(mode) != "clean" for mode in MODES):
        grade = "red_cleanup_incomplete"
    elif not any_measured_success:
        grade = "red_p6_3b_prefix_cache_matched_ab_no_success"
    elif not structural_complete:
        grade = "yellow_p6_3b_prefix_cache_matched_ab_partial"
    elif not evidence_complete:
        grade = "red_p6_3b_prefix_cache_evidence_incomplete"
    else:
        grade = "candidate_green_p6_3b_prefix_cache_matched_ab"

    return {
        "server_grade": grade,
        "prime_request_count": len(prime_rows),
        "measured_request_count": len(measured_rows),
        "successful_request_count": len(successful),
        "all_eight_groups_matched": all_groups_matched,
        "represented_groups_by_mode": {
            mode: sorted(groups) for mode, groups in represented_by_mode.items()
        },
        "body_pairing_ok": body_pairing_ok,
        "prefix_cache_on_positive_hit_measured_count": on_positive_hits,
        "prefix_cache_on_hit_delta_total": on_hits_total,
        "prefix_cache_off_hit_delta_total": off_hits_total,
        "mtp_accepted_token_delta_by_mode": accepted_by_mode,
        "queue_metrics_ok": all(
            row.get("queue_metrics_ok") is True for row in request_rows
        ),
        "counter_continuity_ok": all(
            row.get("counter_continuity_ok") is True for row in request_rows
        ),
        "prefix_evidence_ok": evidence_complete,
        "cleanup_by_mode": cleanup_by_mode,
        "mechanism_effect_accepted": False,
        "developer_review_required": True,
        "existing_p6_references_remain_true": True,
        "claim_boundary": "matched_prefix_cache_on_off_mechanism_effect_only",
    }


def _metrics_snapshot(base_url: str, raw_path: Path) -> dict[str, Any]:
    status, raw = _get(base_url, "/metrics")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw)
    parsed = parse_metrics(raw) if status == 200 else {
        **{alias: 0.0 for alias in set(METRIC_NAMES.values())},
        "queue_metrics_present": False,
        "prefix_metrics_present": False,
        "spec_metrics_present": False,
    }
    parsed["http_status"] = status
    parsed["raw_server_path"] = str(raw_path)
    return parsed


def _wait_for_idle(
    base_url: str,
    raw_path: Path,
    timeout_seconds: float = 60.0,
) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _metrics_snapshot(base_url, raw_path)
        if (
            last.get("http_status") == 200
            and last.get("queue_metrics_present") is True
            and float(last.get("num_requests_running") or 0.0) == 0
            and float(last.get("num_requests_waiting") or 0.0) == 0
        ):
            return True, last
        time.sleep(0.5)
    return False, last


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def execute_mode(
    artifact_dir: Path,
    base_url: str,
    server_pid: int,
    mode: str,
    *,
    positive_hit_required_group_ids: set[str] | None = None,
) -> int:
    if mode not in MODES:
        raise ValueError(f"unsupported mode: {mode}")
    plan = json.loads((artifact_dir / "run_plan.json").read_text(encoding="utf-8"))
    mode_dir = artifact_dir / "modes" / mode
    rows: list[dict[str, Any]] = []
    previous_after: dict[str, Any] | None = None

    for item in plan:
        request_id = str(item["request_id"])
        health_before, _ = _get(base_url, "/health", timeout=5)
        idle_before, metrics_before = _wait_for_idle(
            base_url,
            mode_dir / "raw_metrics" / f"{request_id}_before.prom",
        )
        pre_checks = {
            "server_alive_before": _process_alive(server_pid),
            "health_before_200": health_before == 200,
            "queue_metrics_before_present": (
                metrics_before.get("queue_metrics_present") is True
            ),
            "queue_idle_before": idle_before,
            "spec_metrics_before_present": (
                metrics_before.get("spec_metrics_present") is True
            ),
            "prefix_metrics_before_present_if_on": (
                mode == "prefix_cache_off"
                or metrics_before.get("prefix_metrics_present") is True
            ),
        }
        if not all(pre_checks.values()):
            failed = {
                **item,
                "mode": mode,
                "status": "failed_pre_request_gate",
                "request_body_sha256": item.get("request_body_sha256"),
                "queue_metrics_ok": False,
                "counter_continuity_ok": False,
                "spec_activity_ok": False,
                "prefix_evidence_ok": False,
                "prefix_queries_delta": 0.0,
                "prefix_hits_delta": 0.0,
                "accepted_token_delta": 0.0,
                "checks": pre_checks,
                "generated_text_retained": False,
                "token_ids_retained": False,
            }
            rows.append(failed)
            _write_jsonl(mode_dir / "raw_request_results.jsonl", rows)
            break

        batch = {
            "batch_id": request_id,
            "phase": item["request_role"],
            "cell_id": item["group_id"],
            "context_tokens": item["context_tokens"],
            "output_tokens": item["output_tokens"],
            "concurrency": 1,
            "repeat_index": item["repeat_index"],
            "requests": [{**item, "request_index": 1}],
        }
        request_row = _stream_request(
            artifact_dir=artifact_dir,
            base_url=base_url,
            server_pid=server_pid,
            batch=batch,
            request_item=batch["requests"][0],
            start_barrier=threading.Barrier(1),
        )
        health_after, _ = _get(base_url, "/health", timeout=5)
        idle_after, metrics_after = _wait_for_idle(
            base_url,
            mode_dir / "raw_metrics" / f"{request_id}_after.prom",
        )
        delta = {
            name: float(metrics_after.get(name) or 0.0)
            - float(metrics_before.get(name) or 0.0)
            for name in (
                "prefix_queries",
                "prefix_hits",
                "num_drafts",
                "num_draft_tokens",
                "num_accepted_tokens",
            )
        }
        continuity_names = (
            "num_drafts",
            "num_draft_tokens",
            "num_accepted_tokens",
            "prefix_queries",
            "prefix_hits",
        )
        counter_continuity_ok = previous_after is None or all(
            float(metrics_before.get(name) or 0.0)
            >= float(previous_after.get(name) or 0.0)
            for name in continuity_names
        )
        spec_activity_ok = (
            metrics_before.get("spec_metrics_present") is True
            and metrics_after.get("spec_metrics_present") is True
            and delta["num_drafts"] > 0
            and delta["num_draft_tokens"] > 0
            and delta["num_accepted_tokens"] >= 0
        )
        if mode == "prefix_cache_on":
            positive_hit_required = (
                item["request_role"] == "measured"
                and (
                    positive_hit_required_group_ids is None
                    or item["group_id"] in positive_hit_required_group_ids
                )
            )
            prefix_evidence_ok = (
                metrics_before.get("prefix_metrics_present") is True
                and metrics_after.get("prefix_metrics_present") is True
                and delta["prefix_queries"] > 0
                and delta["prefix_hits"] >= 0
                and delta["prefix_hits"] <= delta["prefix_queries"]
                and (not positive_hit_required or delta["prefix_hits"] > 0)
            )
        else:
            prefix_evidence_ok = delta["prefix_hits"] == 0
        queue_metrics_ok = (
            metrics_before.get("queue_metrics_present") is True
            and metrics_after.get("queue_metrics_present") is True
            and idle_before
            and idle_after
        )
        checks = {
            **pre_checks,
            "health_after_200": health_after == 200,
            "queue_idle_after": idle_after,
            "queue_metrics_ok": queue_metrics_ok,
            "counter_continuity_ok": counter_continuity_ok,
            "spec_activity_ok": spec_activity_ok,
            "prefix_evidence_ok": prefix_evidence_ok,
        }
        request_row.update(
            {
                "mode": mode,
                "group_id": item["group_id"],
                "request_role": item["request_role"],
                "target_shared_prefix_ratio_pct": item[
                    "target_shared_prefix_ratio_pct"
                ],
                "target_shared_prefix_tokens": item[
                    "target_shared_prefix_tokens"
                ],
                "metrics_before": metrics_before,
                "metrics_after": metrics_after,
                "counter_delta": delta,
                "prefix_queries_delta": delta["prefix_queries"],
                "prefix_hits_delta": delta["prefix_hits"],
                "observed_prefix_hit_ratio": (
                    round(delta["prefix_hits"] / delta["prefix_queries"], 6)
                    if delta["prefix_queries"] > 0
                    else None
                ),
                "accepted_token_delta": delta["num_accepted_tokens"],
                "queue_metrics_ok": queue_metrics_ok,
                "counter_continuity_ok": counter_continuity_ok,
                "spec_activity_ok": spec_activity_ok,
                "prefix_evidence_ok": prefix_evidence_ok,
                "checks": {**request_row.get("checks", {}), **checks},
            }
        )
        for optional_key in (
            "planned_shared_tokens",
            "actual_token_lcp",
            "actual_lcp_sha256",
            "actual_lcp_mod_128",
            "actual_lcp_mod_16384",
            "expected_prefix_hit_tokens",
        ):
            if optional_key in item:
                request_row[optional_key] = item[optional_key]
        if request_row.get("status") != "success" or not all(checks.values()):
            request_row["status"] = "failed"
        rows.append(request_row)
        _write_jsonl(mode_dir / "raw_request_results.jsonl", rows)
        previous_after = metrics_after
        if not (
            _process_alive(server_pid)
            and health_after == 200
            and idle_after
        ):
            break

    complete = len(rows) == len(plan) and all(
        row.get("status") == "success" for row in rows
    )
    return 0 if complete else 2


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    average = statistics.fmean(values)
    return {
        "n": len(values),
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "max": round(max(values), 6),
        "mean": round(average, 6),
        "cv": (
            round(statistics.pstdev(values) / average, 6)
            if len(values) > 1 and average
            else 0.0
        ),
    }


def _paired_delta(on_value: float, off_value: float) -> tuple[float, float | None]:
    absolute = on_value - off_value
    relative = absolute / off_value if off_value else None
    return round(absolute, 6), round(relative, 6) if relative is not None else None


def _write_comparison_tables(
    artifact_dir: Path,
    request_rows: list[dict[str, Any]],
) -> None:
    measured = [row for row in request_rows if row.get("request_role") == "measured"]
    metric_names = ("ttft_ms", "tpot_ms", "e2el_ms", "output_tokens_per_second")
    group_rows: list[dict[str, Any]] = []
    for mode in MODES:
        for group in build_run_plan()[::4]:
            rows = [
                row
                for row in measured
                if row.get("mode") == mode
                and row.get("group_id") == group["group_id"]
            ]
            result: dict[str, Any] = {
                "mode": mode,
                "group_id": group["group_id"],
                "context_tokens": group["context_tokens"],
                "target_shared_prefix_ratio_pct": group[
                    "target_shared_prefix_ratio_pct"
                ],
                "target_shared_prefix_tokens": group["target_shared_prefix_tokens"],
                "request_n": len(rows),
                "request_success_n": sum(row.get("status") == "success" for row in rows),
                "prefix_queries_delta_total": round(
                    sum(float(row.get("prefix_queries_delta") or 0.0) for row in rows),
                    6,
                ),
                "prefix_hits_delta_total": round(
                    sum(float(row.get("prefix_hits_delta") or 0.0) for row in rows),
                    6,
                ),
            }
            for metric in metric_names:
                result[metric] = json.dumps(
                    _summary([float(row.get(metric) or 0.0) for row in rows]),
                    separators=(",", ":"),
                )
            group_rows.append(result)
    with (artifact_dir / "mode_group_summary.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(group_rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(group_rows)

    by_key = {
        (
            str(row.get("mode")),
            str(row.get("group_id")),
            int(row.get("repeat_index") or 0),
        ): row
        for row in measured
    }
    paired_rows: list[dict[str, Any]] = []
    for group in build_run_plan()[::4]:
        for repeat_index in range(1, 4):
            off = by_key.get(
                ("prefix_cache_off", str(group["group_id"]), repeat_index), {}
            )
            on = by_key.get(
                ("prefix_cache_on", str(group["group_id"]), repeat_index), {}
            )
            result = {
                "group_id": group["group_id"],
                "context_tokens": group["context_tokens"],
                "target_shared_prefix_ratio_pct": group[
                    "target_shared_prefix_ratio_pct"
                ],
                "repeat_index": repeat_index,
                "prefix_cache_off_status": off.get("status"),
                "prefix_cache_on_status": on.get("status"),
                "prefix_cache_off_hits_delta": off.get("prefix_hits_delta"),
                "prefix_cache_on_hits_delta": on.get("prefix_hits_delta"),
            }
            for metric in metric_names:
                off_value = float(off.get(metric) or 0.0)
                on_value = float(on.get(metric) or 0.0)
                absolute, relative = _paired_delta(on_value, off_value)
                result[f"prefix_cache_off_{metric}"] = off_value
                result[f"prefix_cache_on_{metric}"] = on_value
                result[f"on_minus_off_{metric}"] = absolute
                result[f"on_minus_off_relative_{metric}"] = relative
            paired_rows.append(result)
    with (artifact_dir / "paired_request_summary.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(paired_rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(paired_rows)


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parents[2]), *args],
            text=True,
        ).strip()
    except Exception:
        return ""


def finalize_artifacts(artifact_dir: Path) -> dict[str, Any]:
    request_rows = [
        row
        for mode in MODES
        for row in _read_jsonl(
            artifact_dir / "modes" / mode / "raw_request_results.jsonl"
        )
    ]
    cleanup_by_mode = {
        mode: (
            artifact_dir / "modes" / mode / "cleanup_status.txt"
        ).read_text(encoding="utf-8").strip()
        if (artifact_dir / "modes" / mode / "cleanup_status.txt").exists()
        else "incomplete"
        for mode in MODES
    }
    cleanup_status = (
        "clean"
        if all(value == "clean" for value in cleanup_by_mode.values())
        else "incomplete"
    )
    (artifact_dir / "cleanup_status.txt").write_text(
        cleanup_status + "\n", encoding="utf-8"
    )
    grading = grade_evidence(request_rows, cleanup_by_mode=cleanup_by_mode)
    _write_comparison_tables(artifact_dir, request_rows)
    (artifact_dir / "grading_inputs.json").write_text(
        json.dumps(grading, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "server_grade.txt").write_text(
        grading["server_grade"] + "\n", encoding="utf-8"
    )
    environment = {
        "git_head": _git_value("rev-parse", "HEAD"),
        "origin_main": _git_value("rev-parse", "origin/main"),
        "tracked_status": _git_value(
            "status", "--porcelain", "--untracked-files=no"
        ),
        "source_payload_sha256": (
            (artifact_dir / "source_payload_sha256.txt")
            .read_text(encoding="utf-8")
            .split()[0]
            if (artifact_dir / "source_payload_sha256.txt").exists()
            else None
        ),
        "server_command_sha256_by_mode": {
            mode: (
                (artifact_dir / "modes" / mode / "server_command_sha256.txt")
                .read_text(encoding="utf-8")
                .split()[0]
                if (
                    artifact_dir / "modes" / mode / "server_command_sha256.txt"
                ).exists()
                else None
            )
            for mode in MODES
        },
        "server_lifecycle_count": 2,
        "profiler_run": False,
        "hbm_sampler_run": False,
        "mode_order": list(MODES),
        "fixed_mode_order_is_a_reported_limitation": True,
    }
    (artifact_dir / "environment_and_hashes.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# P6.3B matched Prefix Cache on/off server result",
        "",
        "- task_id: p6_3b_deepseek_v4_flash_w8a8_mtp_prefix_cache_matched_ab_2026_0715",
        f"- server_grade: {grading['server_grade']}",
        f"- requests: {grading['successful_request_count']}/64 successful",
        f"- prime_requests: {grading['prime_request_count']}/16",
        f"- measured_requests: {grading['measured_request_count']}/48",
        f"- all_eight_groups_matched: {str(grading['all_eight_groups_matched']).lower()}",
        f"- body_pairing_ok: {str(grading['body_pairing_ok']).lower()}",
        "- prefix_cache_on_positive_hit_measured_count: "
        f"{grading['prefix_cache_on_positive_hit_measured_count']}/24",
        "- prefix_cache_on_hit_delta_total: "
        f"{grading['prefix_cache_on_hit_delta_total']}",
        "- prefix_cache_off_hit_delta_total: "
        f"{grading['prefix_cache_off_hit_delta_total']}",
        "- mechanism_effect_accepted: false (developer review required)",
        "- green_means_evidence_complete_not_prefix_cache_faster: true",
        "- fixed_mode_order_limitation: prefix_cache_off_then_prefix_cache_on",
        "- claim_boundary: matched_prefix_cache_on_off_mechanism_effect_only",
        f"- raw_result_root_server_local: {artifact_dir}",
        "- generated content and returned token ID payloads are not retained or packaged",
    ]
    (artifact_dir / "result_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    if grading["server_grade"] != "candidate_green_p6_3b_prefix_cache_matched_ab":
        first_failed = next(
            (row for row in request_rows if row.get("status") != "success"), None
        )
        if first_failed is not None:
            bounded = {
                key: value
                for key, value in first_failed.items()
                if key not in {"token_arrival_ns"}
            }
            (artifact_dir / "first_failure_excerpt.txt").write_text(
                json.dumps(bounded, indent=2, sort_keys=True)[:8192] + "\n",
                encoding="utf-8",
            )

    candidate_names = (
        "result_summary.md",
        "environment_and_hashes.json",
        "request_body_manifest.json",
        "mode_group_summary.tsv",
        "paired_request_summary.tsv",
        "grading_inputs.json",
        "cleanup_status.txt",
        "first_failure_excerpt.txt",
    )
    candidates: list[tuple[str, int, str, str]] = []
    total = 0
    for name in candidate_names:
        path = artifact_dir / name
        if not path.exists():
            continue
        size = path.stat().st_size
        total += size
        candidates.append(
            (
                str(path),
                size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                "bounded_structured_prefix_cache_ab_evidence_no_content_payload",
            )
        )
    with (artifact_dir / "delivery_candidates.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["path", "bytes", "sha256", "sensitivity"])
        writer.writerows(candidates)
    (artifact_dir / "delivery_candidates_total_bytes.txt").write_text(
        f"{total}\n", encoding="utf-8"
    )
    grading["candidate_total_bytes"] = total
    grading["candidate_size_gate_pass"] = total <= 71680
    return grading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the DeepSeek P6.3B matched Prefix Cache on/off client."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-payload", type=Path, required=True)
    prepare.add_argument("--artifact-dir", type=Path, required=True)
    prepare.add_argument("--model-name", required=True)
    run_mode = subparsers.add_parser("run-mode")
    run_mode.add_argument("--artifact-dir", type=Path, required=True)
    run_mode.add_argument("--base-url", required=True)
    run_mode.add_argument("--server-pid", type=int, required=True)
    run_mode.add_argument("--mode", choices=MODES, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        prepare_artifacts(args.source_payload, args.artifact_dir, args.model_name)
        return 0
    if args.command == "run-mode":
        return execute_mode(args.artifact_dir, args.base_url, args.server_pid, args.mode)
    if args.command == "finalize":
        finalize_artifacts(args.artifact_dir)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
