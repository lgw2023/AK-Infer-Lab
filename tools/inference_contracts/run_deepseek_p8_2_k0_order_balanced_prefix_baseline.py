from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    _common_prefix_length,
    _read_jsonl,
    execute_mode,
    prepare_artifacts,
)
from tools.inference_contracts.run_deepseek_p6_3b_r1_hybrid_kv_repair import (
    summarize_hybrid_diagnostics,
)
from tools.inference_contracts.run_deepseek_p6_3b_r3_repaired_matched_ab import (
    _git_value,
    _read_repair_identity,
)
from tools.inference_contracts.run_deepseek_p6_1_unprofiled_baseline import (
    percentile,
)


TASK_ID = (
    "p8_2_k0_deepseek_v4_flash_order_balanced_"
    "prefix_cache_baseline_2026_0717"
)
REFINALIZATION_TASK_ID = (
    "p8_2_k0_r1_offline_refinalization_2026_0717"
)
CONTEXT_TOKENS = 65536
OUTPUT_TOKENS = 64
BLOCK_SIZE = 128
HYBRID_LCM_TOKENS = 16384
PRIMARY_GROUP = "ctx65536_prefix90"
WARMUP_GROUP = "ctx65536_prefix50"
LIFECYCLE_SCHEDULE = (
    {
        "lifecycle_id": "lifecycle_01",
        "pair_id": "pair_01",
        "pair_position": "first",
        "mode": "prefix_cache_off",
    },
    {
        "lifecycle_id": "lifecycle_02",
        "pair_id": "pair_01",
        "pair_position": "second",
        "mode": "prefix_cache_on",
    },
    {
        "lifecycle_id": "lifecycle_03",
        "pair_id": "pair_02",
        "pair_position": "first",
        "mode": "prefix_cache_on",
    },
    {
        "lifecycle_id": "lifecycle_04",
        "pair_id": "pair_02",
        "pair_position": "second",
        "mode": "prefix_cache_off",
    },
)
EXPECTED_COMMAND_SHA256 = {
    "prefix_cache_off": (
        "def3dd8bf71ee4cac1922b0d4fa14321e1df5369fd8a5997771d00f3be6418ea"
    ),
    "prefix_cache_on": (
        "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19"
    ),
}
METRIC_FIELDS = (
    "ttft_ms",
    "tpot_ms",
    "itl_p50_ms",
    "itl_p95_ms",
    "itl_p99_ms",
    "e2el_ms",
    "output_tokens_per_second",
)
CANDIDATE_NAMES = (
    "result_summary.md",
    "environment_and_hashes.json",
    "request_body_manifest.json",
    "lifecycle_summary.tsv",
    "measured_request_summary.tsv",
    "paired_request_summary.tsv",
    "mode_statistics.json",
    "prefix_cache_metrics_summary.json",
    "mtp_queue_health_summary.json",
    "repair_diagnostic_summary.json",
    "resolved_prefix_cache_config_summary.json",
    "grading_inputs.json",
    "cleanup_status.txt",
    "first_failure_excerpt.txt",
)
SENSITIVITY = "bounded_operational_metadata_no_content_or_token_ids"


def _build_template_plan() -> list[dict[str, Any]]:
    primary_shared = (
        CONTEXT_TOKENS * 90 // 100 // BLOCK_SIZE * BLOCK_SIZE
    )
    plan = [
        {
            "request_id": "k0_warmup",
            "group_id": WARMUP_GROUP,
            "request_role": "warmup",
            "repeat_index": 0,
            "context_tokens": CONTEXT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "target_shared_prefix_ratio_pct": 50,
            "target_shared_prefix_tokens": (
                CONTEXT_TOKENS * 50 // 100 // BLOCK_SIZE * BLOCK_SIZE
            ),
        },
        {
            "request_id": "k0_prime",
            "group_id": PRIMARY_GROUP,
            "request_role": "prime",
            "repeat_index": 0,
            "context_tokens": CONTEXT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "target_shared_prefix_ratio_pct": 90,
            "target_shared_prefix_tokens": primary_shared,
        },
    ]
    for repeat_index in range(1, 4):
        plan.append(
            {
                "request_id": f"k0_measured_{repeat_index:02d}",
                "group_id": PRIMARY_GROUP,
                "request_role": "measured",
                "repeat_index": repeat_index,
                "context_tokens": CONTEXT_TOKENS,
                "output_tokens": OUTPUT_TOKENS,
                "target_shared_prefix_ratio_pct": 90,
                "target_shared_prefix_tokens": primary_shared,
            }
        )
    return plan


def _read_body(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_records(
    template_dir: Path, records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool]:
    prompts = {
        str(record["request_id"]): _read_body(
            template_dir / str(record["body_relative_path"])
        )["prompt"]
        for record in records
    }
    prime_prompt = prompts["k0_prime"]
    warmup_lcp = _common_prefix_length(
        prompts["k0_warmup"], prime_prompt
    )
    canonical: list[dict[str, Any]] = []
    for record in records:
        request_id = str(record["request_id"])
        if request_id == "k0_warmup":
            role = "warmup"
            pair_slot = "warmup"
            actual_lcp = warmup_lcp
            expected_hit = 0
        elif request_id == "k0_prime":
            role = "prime"
            pair_slot = "prime"
            actual_lcp = 0
            expected_hit = 0
        else:
            role = "measured"
            pair_slot = request_id.removeprefix("k0_")
            actual_lcp = _common_prefix_length(
                prime_prompt, prompts[request_id]
            )
            expected_hit = (
                actual_lcp // HYBRID_LCM_TOKENS * HYBRID_LCM_TOKENS
            )
        canonical_lcp = json.dumps(
            prompts[request_id][:actual_lcp], separators=(",", ":")
        ).encode("utf-8")
        canonical.append(
            {
                **record,
                "k0_role": role,
                "pair_slot": pair_slot,
                "planned_shared_tokens": (
                    record["target_shared_prefix_tokens"]
                    if role == "measured"
                    else 0
                ),
                "actual_token_lcp": actual_lcp,
                "actual_lcp_sha256": hashlib.sha256(
                    canonical_lcp
                ).hexdigest(),
                "actual_lcp_mod_128": actual_lcp % BLOCK_SIZE,
                "actual_lcp_mod_16384": actual_lcp % HYBRID_LCM_TOKENS,
                "expected_prefix_hit_tokens": expected_hit,
            }
        )
    if warmup_lcp >= BLOCK_SIZE:
        raise ValueError("K0 warmup shares a cacheable block with primary")
    measured = [row for row in canonical if row["k0_role"] == "measured"]
    if len(measured) != 3 or any(
        row["expected_prefix_hit_tokens"] != 49152 for row in measured
    ):
        raise ValueError("K0 measured hybrid-LCM expectation drift")
    return canonical, warmup_lcp < BLOCK_SIZE


def prepare_k0_artifacts(
    source_payload: Path,
    artifact_dir: Path,
    model_name: str,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    template_dir = artifact_dir / "body_template"
    template = prepare_artifacts(
        source_payload,
        template_dir,
        model_name,
        plan=_build_template_plan(),
    )
    canonical, warmup_lcp_ok = _canonical_records(
        template_dir, template["records"]
    )
    source_sha256 = hashlib.sha256(source_payload.read_bytes()).hexdigest()
    pairing: dict[str, set[str]] = {}

    for schedule in LIFECYCLE_SCHEDULE:
        lifecycle_dir = (
            artifact_dir / "lifecycles" / schedule["lifecycle_id"]
        )
        body_dir = lifecycle_dir / "bodies"
        body_dir.mkdir(parents=True, exist_ok=False)
        run_plan: list[dict[str, Any]] = []
        for record in canonical:
            pair_slot = str(record["pair_slot"])
            relative_path = Path("bodies") / f"{pair_slot}.json"
            source_body = template_dir / str(record["body_relative_path"])
            destination = lifecycle_dir / relative_path
            shutil.copyfile(source_body, destination)
            body_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
            if body_hash != record["request_body_sha256"]:
                raise ValueError("K0 lifecycle body copy hash drift")
            pairing.setdefault(pair_slot, set()).add(body_hash)
            run_plan.append(
                {
                    **record,
                    **schedule,
                    "request_id": (
                        f"{schedule['lifecycle_id']}_{pair_slot}"
                    ),
                    "request_role": record["k0_role"],
                    "body_relative_path": str(relative_path),
                }
            )
        lifecycle_manifest = {
            "task_id": TASK_ID,
            **schedule,
            "request_count": 5,
            "records": run_plan,
            "generated_text_retained": False,
            "token_ids_retained": False,
        }
        (lifecycle_dir / "run_plan.json").write_text(
            json.dumps(run_plan, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (lifecycle_dir / "request_body_manifest.json").write_text(
            json.dumps(lifecycle_manifest, separators=(",", ":"), sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        (lifecycle_dir / "source_payload_sha256.txt").write_text(
            source_sha256 + "\n", encoding="utf-8"
        )

    manifest = {
        "task_id": TASK_ID,
        "source_payload_sha256": source_sha256,
        "lifecycle_schedule": [dict(row) for row in LIFECYCLE_SCHEDULE],
        "canonical_body_count": len(canonical),
        "total_request_count": len(canonical) * len(LIFECYCLE_SCHEDULE),
        "matched_measured_pair_count": 6,
        "warmup_primary_lcp_less_than_128": warmup_lcp_ok,
        "body_pairing_exact": all(len(hashes) == 1 for hashes in pairing.values()),
        "canonical_bodies": canonical,
        "generated_text_retained": False,
        "token_ids_retained": False,
    }
    (artifact_dir / "request_body_manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _request_evidence_checks(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = (
        ("status_success", row.get("status"), "success", row.get("status") == "success"),
        ("http_200", row.get("http_status"), 200, row.get("http_status") == 200),
        (
            "prompt_tokens_exact",
            int(row.get("prompt_tokens") or 0),
            CONTEXT_TOKENS,
            int(row.get("prompt_tokens") or 0) == CONTEXT_TOKENS,
        ),
        (
            "context_tokens_exact",
            int(row.get("context_tokens") or 0),
            CONTEXT_TOKENS,
            int(row.get("context_tokens") or 0) == CONTEXT_TOKENS,
        ),
        (
            "output_tokens_exact",
            int(row.get("output_tokens") or 0),
            OUTPUT_TOKENS,
            int(row.get("output_tokens") or 0) == OUTPUT_TOKENS,
        ),
        (
            "generated_tokens_exact",
            int(row.get("generated_token_count") or 0),
            OUTPUT_TOKENS,
            int(row.get("generated_token_count") or 0) == OUTPUT_TOKENS,
        ),
        (
            "streamed_tokens_exact",
            int(row.get("streamed_token_count") or 0),
            OUTPUT_TOKENS,
            int(row.get("streamed_token_count") or 0) == OUTPUT_TOKENS,
        ),
        (
            "finish_reason_length",
            row.get("finish_reason"),
            "length",
            row.get("finish_reason") == "length",
        ),
        ("saw_done", row.get("saw_done"), True, row.get("saw_done") is True),
        (
            "token_chunk_width_within_mtp_bound",
            int(row.get("max_token_chunk_width") or 0),
            "<=2",
            0 < int(row.get("max_token_chunk_width") or 0) <= 2,
        ),
        (
            "queue_metrics_ok",
            row.get("queue_metrics_ok"),
            True,
            row.get("queue_metrics_ok") is True,
        ),
        (
            "counter_continuity_ok",
            row.get("counter_continuity_ok"),
            True,
            row.get("counter_continuity_ok") is True,
        ),
        (
            "spec_activity_ok",
            row.get("spec_activity_ok"),
            True,
            row.get("spec_activity_ok") is True,
        ),
        (
            "prefix_evidence_ok",
            row.get("prefix_evidence_ok"),
            True,
            row.get("prefix_evidence_ok") is True,
        ),
        (
            "accepted_token_delta_positive",
            float(row.get("accepted_token_delta") or 0),
            ">0",
            float(row.get("accepted_token_delta") or 0) > 0,
        ),
    )
    return {
        name: {"observed": observed, "expected": expected, "passed": passed}
        for name, observed, expected, passed in values
    }


def grade_k0_evidence(
    request_rows: list[dict[str, Any]],
    *,
    cleanup_by_lifecycle: dict[str, str],
    repair_identity_by_lifecycle: dict[str, dict[str, str]],
    resolved_prefix_by_lifecycle: dict[str, bool],
    server_command_sha256_by_lifecycle: dict[str, str],
    diagnostic_ok_by_lifecycle: dict[str, bool],
) -> dict[str, Any]:
    schedule_by_id = {
        row["lifecycle_id"]: row for row in LIFECYCLE_SCHEDULE
    }
    successful = [
        row for row in request_rows if row.get("status") == "success"
    ]
    by_role = {
        role: [row for row in request_rows if row.get("k0_role") == role]
        for role in ("warmup", "prime", "measured")
    }
    lifecycle_structure_exact = True
    for lifecycle_id, schedule in schedule_by_id.items():
        rows = [
            row
            for row in request_rows
            if row.get("lifecycle_id") == lifecycle_id
        ]
        lifecycle_structure_exact = lifecycle_structure_exact and (
            len(rows) == 5
            and [row.get("k0_role") for row in rows]
            == ["warmup", "prime", "measured", "measured", "measured"]
            and all(
                row.get("mode") == schedule["mode"]
                and row.get("pair_id") == schedule["pair_id"]
                and row.get("pair_position") == schedule["pair_position"]
                for row in rows
            )
        )
    order_balance_exact = (
        lifecycle_structure_exact
        and [row["mode"] for row in LIFECYCLE_SCHEDULE]
        == [
            "prefix_cache_off",
            "prefix_cache_on",
            "prefix_cache_on",
            "prefix_cache_off",
        ]
    )

    body_hashes_by_slot: dict[str, set[str]] = {}
    for row in request_rows:
        body_hashes_by_slot.setdefault(str(row.get("pair_slot")), set()).add(
            str(row.get("request_body_sha256"))
        )
    body_pairing_exact = (
        set(body_hashes_by_slot)
        == {"warmup", "prime", "measured_01", "measured_02", "measured_03"}
        and all(len(hashes) == 1 for hashes in body_hashes_by_slot.values())
    )

    matched_pair_count = 0
    for pair_id in ("pair_01", "pair_02"):
        for pair_slot in ("measured_01", "measured_02", "measured_03"):
            rows = [
                row
                for row in by_role["measured"]
                if row.get("pair_id") == pair_id
                and row.get("pair_slot") == pair_slot
            ]
            if (
                len(rows) == 2
                and {row.get("mode") for row in rows}
                == {"prefix_cache_off", "prefix_cache_on"}
                and len(
                    {row.get("request_body_sha256") for row in rows}
                )
                == 1
            ):
                matched_pair_count += 1

    single_variable_server_argv_exact = (
        set(server_command_sha256_by_lifecycle) == set(schedule_by_id)
        and all(
            server_command_sha256_by_lifecycle.get(lifecycle_id)
            == EXPECTED_COMMAND_SHA256[schedule["mode"]]
            for lifecycle_id, schedule in schedule_by_id.items()
        )
    )
    resolved_prefix_control_exact = (
        set(resolved_prefix_by_lifecycle) == set(schedule_by_id)
        and all(
            resolved_prefix_by_lifecycle.get(lifecycle_id)
            is (schedule["mode"] == "prefix_cache_on")
            for lifecycle_id, schedule in schedule_by_id.items()
        )
    )
    repair_identities = list(repair_identity_by_lifecycle.values())
    same_r2_repair = (
        set(repair_identity_by_lifecycle) == set(schedule_by_id)
        and bool(repair_identities)
        and all(repair_identities)
        and all(identity == repair_identities[0] for identity in repair_identities)
    )
    diagnostic_ok_all_lifecycles = (
        set(diagnostic_ok_by_lifecycle) == set(schedule_by_id)
        and all(diagnostic_ok_by_lifecycle.values())
    )

    on_measured = [
        row
        for row in by_role["measured"]
        if row.get("mode") == "prefix_cache_on"
    ]
    off_rows = [
        row for row in request_rows if row.get("mode") == "prefix_cache_off"
    ]
    on_non_measured = [
        row
        for row in request_rows
        if row.get("mode") == "prefix_cache_on"
        and row.get("k0_role") != "measured"
    ]
    on_measured_hit_exact_count = sum(
        float(row.get("prefix_hits_delta") or 0) == 49152
        and int(row.get("expected_prefix_hit_tokens") or 0) == 49152
        for row in on_measured
    )
    off_prefix_hit_total = sum(
        float(row.get("prefix_hits_delta") or 0) for row in off_rows
    )
    on_non_measured_prefix_hit_total = sum(
        float(row.get("prefix_hits_delta") or 0) for row in on_non_measured
    )
    request_checks = [_request_evidence_checks(row) for row in request_rows]
    predicate_names = list(request_checks[0]) if request_checks else []
    request_evidence_predicate_counts = {
        name: {
            "passed": sum(checks[name]["passed"] for checks in request_checks),
            "total": len(request_rows),
        }
        for name in predicate_names
    }
    first_request_evidence_failure = None
    for row, checks in zip(request_rows, request_checks, strict=True):
        failed_name = next(
            (name for name, result in checks.items() if not result["passed"]),
            None,
        )
        if failed_name is not None:
            failed = checks[failed_name]
            first_request_evidence_failure = {
                "request_id": row.get("request_id"),
                "lifecycle_id": row.get("lifecycle_id"),
                "mode": row.get("mode"),
                "pair_slot": row.get("pair_slot"),
                "predicate": failed_name,
                "observed": failed["observed"],
                "expected": failed["expected"],
            }
            break
    request_evidence_exact = bool(request_rows) and (
        first_request_evidence_failure is None
    )
    measured_metrics_complete = bool(by_role["measured"]) and all(
        all(float(row.get(field) or 0) > 0 for field in METRIC_FIELDS)
        for row in by_role["measured"]
    )
    cleanup = (
        "clean"
        if set(cleanup_by_lifecycle) == set(schedule_by_id)
        and all(value == "clean" for value in cleanup_by_lifecycle.values())
        else "incomplete"
    )
    structural_complete = (
        len(request_rows) == 20
        and len(successful) == 20
        and len(by_role["warmup"]) == 4
        and len(by_role["prime"]) == 4
        and len(by_role["measured"]) == 12
        and matched_pair_count == 6
        and order_balance_exact
        and body_pairing_exact
    )
    evidence_complete = (
        request_evidence_exact
        and measured_metrics_complete
        and on_measured_hit_exact_count == 6
        and off_prefix_hit_total == 0
        and on_non_measured_prefix_hit_total == 0
        and single_variable_server_argv_exact
        and resolved_prefix_control_exact
        and same_r2_repair
        and diagnostic_ok_all_lifecycles
        and cleanup == "clean"
    )
    any_measured_success = any(
        row.get("status") == "success" for row in by_role["measured"]
    )
    if not any_measured_success:
        server_grade = "red_p8_2_k0_order_balanced_prefix_baseline_no_success"
    elif not structural_complete:
        server_grade = "yellow_p8_2_k0_order_balanced_prefix_baseline_partial"
    elif not evidence_complete:
        server_grade = (
            "red_p8_2_k0_order_balanced_prefix_baseline_evidence_incomplete"
        )
    else:
        server_grade = (
            "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
        )
    return {
        "server_grade": server_grade,
        "successful_request_count": len(successful),
        "warmup_request_count": len(by_role["warmup"]),
        "prime_request_count": len(by_role["prime"]),
        "measured_request_count": len(by_role["measured"]),
        "matched_measured_pair_count": matched_pair_count,
        "order_balance_exact": order_balance_exact,
        "body_pairing_exact": body_pairing_exact,
        "single_variable_server_argv_exact": single_variable_server_argv_exact,
        "same_r2_repair_all_lifecycles": same_r2_repair,
        "diagnostic_ok_all_lifecycles": diagnostic_ok_all_lifecycles,
        "resolved_prefix_control_exact": resolved_prefix_control_exact,
        "on_measured_hit_exact_count": on_measured_hit_exact_count,
        "off_prefix_hit_total": off_prefix_hit_total,
        "on_non_measured_prefix_hit_total": on_non_measured_prefix_hit_total,
        "request_evidence_exact": request_evidence_exact,
        "request_evidence_predicate_counts": request_evidence_predicate_counts,
        "first_request_evidence_failure": first_request_evidence_failure,
        "measured_metrics_complete": measured_metrics_complete,
        "cleanup": cleanup,
        "performance_reference_accepted": False,
        "offload_evidence_accepted": False,
        "developer_review_required": True,
        "claim_boundary": (
            "order_balanced_64k_exact_reuse_prefix_cache_on_off_"
            "descriptive_baseline_only"
        ),
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _metric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    mean = statistics.fmean(values)
    return {
        "n": len(values),
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "mean": round(mean, 6),
        "p95": round(percentile(values, 0.95), 6),
        "p99": round(percentile(values, 0.99), 6),
        "max": round(max(values), 6),
        "cv": (
            round(statistics.pstdev(values) / mean, 6)
            if len(values) > 1 and mean
            else 0.0
        ),
    }


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _resolved_prefix_ok(value: dict[str, Any], expected: bool) -> bool:
    return all(
        (
            value.get("resolved_enable_prefix_caching") is expected,
            value.get("server_command_has_expected_flag") is True,
            value.get("server_command_has_opposite_flag") is False,
            value.get("process_cmdline_has_expected_flag") is True,
            value.get("process_cmdline_has_opposite_flag") is False,
        )
    )


def _diagnostic_ok(
    summary: dict[str, Any], *, mode: str, source_gate_ok: bool
) -> bool:
    if mode == "prefix_cache_off":
        return all(
            (
                summary.get("install_event_count", 0) > 0,
                summary.get("deferred_import_order_verified") is True,
                summary.get("source_hashes_ok") is True,
                summary.get("retention_interval_explicitly_unset") is True,
                source_gate_ok,
            )
        )
    return summary.get("hybrid_diagnostic_ok") is True and source_gate_ok


def _write_result_tables(
    artifact_dir: Path,
    request_rows: list[dict[str, Any]],
    *,
    cleanup_by_lifecycle: dict[str, str],
    resolved_by_lifecycle: dict[str, bool],
    server_hash_by_lifecycle: dict[str, str],
) -> None:
    lifecycle_rows: list[dict[str, Any]] = []
    for schedule in LIFECYCLE_SCHEDULE:
        lifecycle_id = schedule["lifecycle_id"]
        rows = [
            row
            for row in request_rows
            if row.get("lifecycle_id") == lifecycle_id
        ]
        lifecycle_rows.append(
            {
                **schedule,
                "request_count": len(rows),
                "successful_request_count": sum(
                    row.get("status") == "success" for row in rows
                ),
                "measured_request_count": sum(
                    row.get("k0_role") == "measured" for row in rows
                ),
                "prefix_queries_delta_total": round(
                    sum(float(row.get("prefix_queries_delta") or 0) for row in rows),
                    6,
                ),
                "prefix_hits_delta_total": round(
                    sum(float(row.get("prefix_hits_delta") or 0) for row in rows),
                    6,
                ),
                "accepted_token_delta_total": round(
                    sum(float(row.get("accepted_token_delta") or 0) for row in rows),
                    6,
                ),
                "resolved_enable_prefix_caching": resolved_by_lifecycle.get(
                    lifecycle_id
                ),
                "server_command_sha256": server_hash_by_lifecycle.get(
                    lifecycle_id
                ),
                "cleanup": cleanup_by_lifecycle.get(lifecycle_id),
            }
        )
    _write_tsv(artifact_dir / "lifecycle_summary.tsv", lifecycle_rows)

    measured = [
        row for row in request_rows if row.get("k0_role") == "measured"
    ]
    measured_rows = [
        {
            "lifecycle_id": row.get("lifecycle_id"),
            "pair_id": row.get("pair_id"),
            "pair_position": row.get("pair_position"),
            "mode": row.get("mode"),
            "pair_slot": row.get("pair_slot"),
            "status": row.get("status"),
            "request_body_sha256": row.get("request_body_sha256"),
            "expected_prefix_hit_tokens": row.get(
                "expected_prefix_hit_tokens"
            ),
            "prefix_hits_delta": row.get("prefix_hits_delta"),
            "accepted_token_delta": row.get("accepted_token_delta"),
            **{field: row.get(field) for field in METRIC_FIELDS},
        }
        for row in measured
    ]
    _write_tsv(
        artifact_dir / "measured_request_summary.tsv", measured_rows
    )

    paired_rows: list[dict[str, Any]] = []
    for pair_id in ("pair_01", "pair_02"):
        for pair_slot in ("measured_01", "measured_02", "measured_03"):
            pair = [
                row
                for row in measured
                if row.get("pair_id") == pair_id
                and row.get("pair_slot") == pair_slot
            ]
            by_mode = {str(row.get("mode")): row for row in pair}
            off = by_mode.get("prefix_cache_off", {})
            on = by_mode.get("prefix_cache_on", {})
            result: dict[str, Any] = {
                "pair_id": pair_id,
                "pair_slot": pair_slot,
                "body_sha256_equal": (
                    off.get("request_body_sha256")
                    == on.get("request_body_sha256")
                ),
                "prefix_cache_off_status": off.get("status"),
                "prefix_cache_on_status": on.get("status"),
                "prefix_cache_off_hits_delta": off.get("prefix_hits_delta"),
                "prefix_cache_on_hits_delta": on.get("prefix_hits_delta"),
            }
            for field in METRIC_FIELDS:
                off_value = float(off.get(field) or 0)
                on_value = float(on.get(field) or 0)
                delta = on_value - off_value
                result[f"prefix_cache_off_{field}"] = off_value
                result[f"prefix_cache_on_{field}"] = on_value
                result[f"on_minus_off_{field}"] = round(delta, 6)
                result[f"on_minus_off_relative_{field}"] = (
                    round(delta / off_value, 6) if off_value else None
                )
            paired_rows.append(result)
    _write_tsv(artifact_dir / "paired_request_summary.tsv", paired_rows)

    mode_statistics = {
        mode: {
            field: _metric_summary(
                [
                    float(row.get(field) or 0)
                    for row in measured
                    if row.get("mode") == mode
                ]
            )
            for field in METRIC_FIELDS
        }
        for mode in ("prefix_cache_off", "prefix_cache_on")
    }
    _write_json(artifact_dir / "mode_statistics.json", mode_statistics)


def _refresh_candidate_manifest(
    artifact_dir: Path, grading: dict[str, Any]
) -> None:
    grading_path = artifact_dir / "grading_inputs.json"
    other_paths = [
        artifact_dir / name
        for name in CANDIDATE_NAMES
        if name != "grading_inputs.json"
    ]
    if any(not path.is_file() for path in other_paths):
        missing = [str(path) for path in other_paths if not path.is_file()]
        raise FileNotFoundError(missing)
    other_total = sum(path.stat().st_size for path in other_paths)
    for _ in range(10):
        _write_json(grading_path, grading)
        total = other_total + grading_path.stat().st_size
        size_ok = total <= 71680
        if (
            grading.get("candidate_total_bytes") == total
            and grading.get("candidate_size_gate_pass") is size_ok
            and grading.get("candidate_file_count") == len(CANDIDATE_NAMES)
        ):
            break
        grading["candidate_total_bytes"] = total
        grading["candidate_size_gate_pass"] = size_ok
        grading["candidate_file_count"] = len(CANDIDATE_NAMES)
    else:
        raise RuntimeError("K0 candidate size did not converge")

    rows = []
    for name in CANDIDATE_NAMES:
        path = artifact_dir / name
        rows.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "sensitivity": SENSITIVITY,
            }
        )
    _write_tsv(artifact_dir / "delivery_candidates.tsv", rows)
    (artifact_dir / "candidate_total_bytes.txt").write_text(
        f"{grading['candidate_total_bytes']}\n", encoding="utf-8"
    )


def _required_k0_source_paths(artifact_dir: Path) -> list[Path]:
    paths = [artifact_dir / "request_body_manifest.json"]
    for schedule in LIFECYCLE_SCHEDULE:
        mode_dir = (
            artifact_dir
            / "lifecycles"
            / schedule["lifecycle_id"]
            / "modes"
            / schedule["mode"]
        )
        runtime_dir = mode_dir / "runtime"
        paths.extend(
            (
                mode_dir / "raw_request_results.jsonl",
                mode_dir / "cleanup_status.txt",
                mode_dir / "repair_identity.tsv",
                mode_dir / "server_command_sha256.txt",
                runtime_dir / "resolved_prefix_cache_config.json",
                runtime_dir / "source_gate_status.txt",
                runtime_dir / "hybrid_kv_runtime_diagnostic.jsonl",
            )
        )
    return paths


def inspect_k0_source_evidence(artifact_dir: Path) -> dict[str, Any]:
    required = _required_k0_source_paths(artifact_dir)
    missing = [str(path.relative_to(artifact_dir)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"K0 source evidence missing: {missing}")
    manifest = _read_json(artifact_dir / "request_body_manifest.json")
    if manifest.get("task_id") != TASK_ID:
        raise ValueError("K0 source task identity mismatch")
    if manifest.get("total_request_count") != 20:
        raise ValueError("K0 source request count mismatch")
    request_rows: list[dict[str, Any]] = []
    for schedule in LIFECYCLE_SCHEDULE:
        raw_path = (
            artifact_dir
            / "lifecycles"
            / schedule["lifecycle_id"]
            / "modes"
            / schedule["mode"]
            / "raw_request_results.jsonl"
        )
        rows = _read_jsonl(raw_path)
        if len(rows) != 5:
            raise ValueError(f"K0 source lifecycle row count mismatch: {raw_path}")
        request_rows.extend(rows)
    canonical_fields = {"generated_token_count", "streamed_token_count"}
    missing_canonical = [
        str(row.get("request_id"))
        for row in request_rows
        if not canonical_fields.issubset(row)
    ]
    if missing_canonical:
        raise ValueError(
            "K0 source rows missing canonical producer fields: "
            + ",".join(missing_canonical)
        )
    inventory = [
        {
            "relative_path": str(path.relative_to(artifact_dir)),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in required
    ]
    canonical = json.dumps(
        inventory, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return {
        "source_artifact_dir": str(artifact_dir.resolve()),
        "source_evidence_file_count": len(inventory),
        "source_evidence_inventory": inventory,
        "source_evidence_inventory_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def finalize_k0_artifacts(
    artifact_dir: Path,
    *,
    output_dir: Path | None = None,
    source_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result_dir = output_dir or artifact_dir
    if output_dir is not None:
        result_dir.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(
            artifact_dir / "request_body_manifest.json",
            result_dir / "request_body_manifest.json",
        )
    request_rows: list[dict[str, Any]] = []
    cleanup_by_lifecycle: dict[str, str] = {}
    repair_by_lifecycle: dict[str, dict[str, str]] = {}
    resolved_raw_by_lifecycle: dict[str, dict[str, Any]] = {}
    resolved_by_lifecycle: dict[str, bool] = {}
    server_hash_by_lifecycle: dict[str, str] = {}
    diagnostic_summary_by_lifecycle: dict[str, dict[str, Any]] = {}
    diagnostic_ok_by_lifecycle: dict[str, bool] = {}

    for schedule in LIFECYCLE_SCHEDULE:
        lifecycle_id = schedule["lifecycle_id"]
        mode = schedule["mode"]
        mode_dir = artifact_dir / "lifecycles" / lifecycle_id / "modes" / mode
        runtime_dir = mode_dir / "runtime"
        request_rows.extend(
            _read_jsonl(mode_dir / "raw_request_results.jsonl")
        )
        cleanup_by_lifecycle[lifecycle_id] = (
            (mode_dir / "cleanup_status.txt").read_text(encoding="utf-8").strip()
            if (mode_dir / "cleanup_status.txt").is_file()
            else "incomplete"
        )
        repair_by_lifecycle[lifecycle_id] = _read_repair_identity(
            mode_dir / "repair_identity.tsv"
        )
        resolved = _read_json(
            runtime_dir / "resolved_prefix_cache_config.json"
        )
        resolved_raw_by_lifecycle[lifecycle_id] = resolved
        expected_resolved = mode == "prefix_cache_on"
        resolved_by_lifecycle[lifecycle_id] = (
            expected_resolved
            if _resolved_prefix_ok(resolved, expected_resolved)
            else not expected_resolved
        )
        hash_path = mode_dir / "server_command_sha256.txt"
        server_hash_by_lifecycle[lifecycle_id] = (
            hash_path.read_text(encoding="utf-8").split()[0]
            if hash_path.is_file()
            else ""
        )
        diagnostics = _read_jsonl(
            runtime_dir / "hybrid_kv_runtime_diagnostic.jsonl"
        )
        diagnostic_summary = summarize_hybrid_diagnostics(
            diagnostics, require_deferred_install=True
        )
        source_gate_ok = (
            (runtime_dir / "source_gate_status.txt").is_file()
            and (runtime_dir / "source_gate_status.txt")
            .read_text(encoding="utf-8")
            .strip()
            == "pass"
        )
        diagnostic_summary["source_gate_ok"] = source_gate_ok
        diagnostic_summary_by_lifecycle[lifecycle_id] = diagnostic_summary
        diagnostic_ok_by_lifecycle[lifecycle_id] = _diagnostic_ok(
            diagnostic_summary, mode=mode, source_gate_ok=source_gate_ok
        )

    cleanup = (
        "clean"
        if all(value == "clean" for value in cleanup_by_lifecycle.values())
        else "incomplete"
    )
    (result_dir / "cleanup_status.txt").write_text(
        cleanup + "\n", encoding="utf-8"
    )
    grading = grade_k0_evidence(
        request_rows,
        cleanup_by_lifecycle=cleanup_by_lifecycle,
        repair_identity_by_lifecycle=repair_by_lifecycle,
        resolved_prefix_by_lifecycle=resolved_by_lifecycle,
        server_command_sha256_by_lifecycle=server_hash_by_lifecycle,
        diagnostic_ok_by_lifecycle=diagnostic_ok_by_lifecycle,
    )
    if source_evidence is not None:
        grading.update(
            {
                "refinalization_task_id": REFINALIZATION_TASK_ID,
                "source_evidence_file_count": source_evidence[
                    "source_evidence_file_count"
                ],
                "source_evidence_inventory_sha256": source_evidence[
                    "source_evidence_inventory_sha256"
                ],
                "source_evidence_unchanged": True,
            }
        )
    _write_result_tables(
        result_dir,
        request_rows,
        cleanup_by_lifecycle=cleanup_by_lifecycle,
        resolved_by_lifecycle=resolved_by_lifecycle,
        server_hash_by_lifecycle=server_hash_by_lifecycle,
    )
    _write_json(
        result_dir / "prefix_cache_metrics_summary.json",
        {
            "on_measured_hit_exact_count": grading[
                "on_measured_hit_exact_count"
            ],
            "expected_on_measured_hit_tokens": 49152,
            "off_prefix_hit_total": grading["off_prefix_hit_total"],
            "on_non_measured_prefix_hit_total": grading[
                "on_non_measured_prefix_hit_total"
            ],
            "claim_boundary": grading["claim_boundary"],
        },
    )
    _write_json(
        result_dir / "mtp_queue_health_summary.json",
        {
            "request_count": len(request_rows),
            "request_evidence_exact": grading["request_evidence_exact"],
            "request_evidence_predicate_counts": grading[
                "request_evidence_predicate_counts"
            ],
            "first_request_evidence_failure": grading[
                "first_request_evidence_failure"
            ],
            "accepted_token_delta_total": sum(
                float(row.get("accepted_token_delta") or 0)
                for row in request_rows
            ),
            "queue_metrics_ok": all(
                row.get("queue_metrics_ok") is True for row in request_rows
            ),
            "counter_continuity_ok": all(
                row.get("counter_continuity_ok") is True
                for row in request_rows
            ),
        },
    )
    _write_json(
        result_dir / "repair_diagnostic_summary.json",
        {
            "by_lifecycle": diagnostic_summary_by_lifecycle,
            "diagnostic_ok_by_lifecycle": diagnostic_ok_by_lifecycle,
            "repair_identity_by_lifecycle": repair_by_lifecycle,
            "same_r2_repair_all_lifecycles": grading[
                "same_r2_repair_all_lifecycles"
            ],
        },
    )
    _write_json(
        result_dir / "resolved_prefix_cache_config_summary.json",
        {
            "by_lifecycle": resolved_raw_by_lifecycle,
            "resolved_prefix_control_exact": grading[
                "resolved_prefix_control_exact"
            ],
        },
    )
    environment = {
        "git_head": _git_value("rev-parse", "HEAD"),
        "origin_main": _git_value("rev-parse", "origin/main"),
        "tracked_status": _git_value(
            "status", "--porcelain", "--untracked-files=no"
        ),
        "lifecycle_schedule": [dict(row) for row in LIFECYCLE_SCHEDULE],
        "server_command_sha256_by_lifecycle": server_hash_by_lifecycle,
        "normalized_server_argv_delta_count": 1,
        "single_variable_server_argv_exact": grading[
            "single_variable_server_argv_exact"
        ],
        "profiler_run": False,
        "hbm_sampler_run": False,
        "offload_run": False,
        "payload_or_placement_mutation": False,
    }
    if source_evidence is not None:
        environment.update(
            {
                **source_evidence,
                "refinalization_task_id": REFINALIZATION_TASK_ID,
                "execution_mode": "offline_existing_raw_evidence_only",
                "npu_started": False,
                "vllm_started": False,
                "model_request_sent": False,
            }
        )
    _write_json(result_dir / "environment_and_hashes.json", environment)
    failure = "none"
    if not grading["server_grade"].startswith("candidate_green"):
        request_failure = grading["first_request_evidence_failure"]
        failure = (
            json.dumps(request_failure, indent=2, sort_keys=True)[:8192]
            if request_failure is not None
            else grading["server_grade"]
        )
    (result_dir / "first_failure_excerpt.txt").write_text(
        failure + "\n", encoding="utf-8"
    )
    (result_dir / "result_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K0 order-balanced Prefix Cache baseline server result",
                "",
                f"- task_id: {TASK_ID}",
                f"- refinalization_task_id: {grading.get('refinalization_task_id', 'none')}",
                f"- server_grade: {grading['server_grade']}",
                f"- requests: {grading['successful_request_count']}/20 successful",
                f"- measured_requests: {grading['measured_request_count']}/12",
                f"- matched_measured_pairs: {grading['matched_measured_pair_count']}/6",
                f"- order_balance_exact: {str(grading['order_balance_exact']).lower()}",
                f"- body_pairing_exact: {str(grading['body_pairing_exact']).lower()}",
                f"- single_variable_server_argv_exact: {str(grading['single_variable_server_argv_exact']).lower()}",
                f"- resolved_prefix_control_exact: {str(grading['resolved_prefix_control_exact']).lower()}",
                f"- same_r2_repair_all_lifecycles: {str(grading['same_r2_repair_all_lifecycles']).lower()}",
                f"- on_measured_hit_exact_count: {grading['on_measured_hit_exact_count']}/6",
                f"- off_prefix_hit_total: {grading['off_prefix_hit_total']}",
                f"- request_evidence_exact: {str(grading['request_evidence_exact']).lower()}",
                f"- first_request_evidence_failure: {json.dumps(grading['first_request_evidence_failure'], sort_keys=True)}",
                f"- cleanup: {grading['cleanup']}",
                "- timing_boundary: descriptive only; no faster/slower conclusion is auto-accepted",
                "- offload_boundary: K1 and all payload movement remain closed",
                "- generated content and returned token IDs are not retained or packaged",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    _refresh_candidate_manifest(result_dir, grading)
    (result_dir / "server_grade.txt").write_text(
        grading["server_grade"] + "\n", encoding="utf-8"
    )
    return grading


def refinalize_k0_artifacts(
    source_artifact_dir: Path, output_dir: Path
) -> dict[str, Any]:
    source_resolved = source_artifact_dir.resolve()
    output_resolved = output_dir.resolve()
    if source_resolved == output_resolved or source_resolved in output_resolved.parents:
        raise ValueError("K0-R1 output must be outside the source artifact directory")
    if output_dir.exists():
        raise FileExistsError(f"K0-R1 output already exists: {output_dir}")
    before = inspect_k0_source_evidence(source_artifact_dir)
    grading = finalize_k0_artifacts(
        source_artifact_dir,
        output_dir=output_dir,
        source_evidence=before,
    )
    after = inspect_k0_source_evidence(source_artifact_dir)
    if after != before:
        raise RuntimeError("K0 source evidence changed during offline refinalization")
    return grading


def execute_k0_mode(
    lifecycle_dir: Path,
    base_url: str,
    server_pid: int,
    mode: str,
) -> int:
    manifest = _read_json(lifecycle_dir / "request_body_manifest.json")
    if manifest.get("task_id") != TASK_ID:
        raise ValueError("K0 lifecycle task identity mismatch")
    if manifest.get("mode") != mode:
        raise ValueError("K0 lifecycle mode mismatch")
    run_exit = execute_mode(
        lifecycle_dir,
        base_url,
        server_pid,
        mode,
        positive_hit_required_group_ids={PRIMARY_GROUP},
    )
    raw_path = (
        lifecycle_dir / "modes" / mode / "raw_request_results.jsonl"
    )
    rows = _read_jsonl(raw_path)
    plan_by_id = {
        str(row["request_id"]): row
        for row in _read_json(lifecycle_dir / "run_plan.json")
    }
    annotated = []
    for row in rows:
        plan = plan_by_id.get(str(row.get("request_id")), {})
        annotated.append(
            {
                **row,
                "lifecycle_id": manifest["lifecycle_id"],
                "pair_id": manifest["pair_id"],
                "pair_position": manifest["pair_position"],
                "mode": mode,
                "pair_slot": plan.get("pair_slot"),
                "k0_role": plan.get("k0_role", row.get("request_role")),
            }
        )
    raw_path.write_text(
        "".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
            for row in annotated
        ),
        encoding="utf-8",
    )
    return run_exit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the DeepSeek P8.2-K0 order-balanced explicit Prefix "
            "Cache on/off pilot."
        )
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
    run_mode.add_argument(
        "--mode",
        choices=("prefix_cache_off", "prefix_cache_on"),
        required=True,
    )
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--artifact-dir", type=Path, required=True)
    refinalize = subparsers.add_parser("refinalize")
    refinalize.add_argument("--source-artifact-dir", type=Path, required=True)
    refinalize.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        prepare_k0_artifacts(
            args.source_payload, args.artifact_dir, args.model_name
        )
        return 0
    if args.command == "run-mode":
        return execute_k0_mode(
            args.artifact_dir,
            args.base_url,
            args.server_pid,
            args.mode,
        )
    if args.command == "refinalize":
        grading = refinalize_k0_artifacts(
            args.source_artifact_dir, args.output_dir
        )
        return (
            0
            if grading["server_grade"]
            == "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
            else 2
        )
    grading = finalize_k0_artifacts(args.artifact_dir)
    return (
        0
        if grading["server_grade"]
        == "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
