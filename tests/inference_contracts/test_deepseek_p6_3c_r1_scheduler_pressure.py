from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r1_chunked_prefill_scheduler_pressure_matched_ab.yaml"
)
PARENT_AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p6_3c_chunked_prefill_feasibility_audit.yaml"
)
RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p6_3c_r1_scheduler_pressure.py"
)
MODE_RUNNER = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r1_mode.sh"
)
TOP_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p6_3c_r1_scheduler_pressure.sh"
)
SERVER_TASK = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p6_3c_r1_server_task.sh"
)


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_workload_preserves_parent_block_and_defines_new_pressure_chain() -> None:
    workload = _load_yaml(WORKLOAD)
    parent = _load_yaml(PARENT_AUDIT)

    assert parent["grade"] == "blocked_p6_3c_not_strict_single_variable"
    assert parent["execution_boundary"]["executable_workload_created"] is False
    assert workload["stage"] == "P6.3C-R1"
    assert workload["relation_to_parent"] == {
        "parent_audit": (
            "benchmarks/deepseek_v4_flash/"
            "p6_3c_chunked_prefill_feasibility_audit.yaml"
        ),
        "parent_grade": "blocked_p6_3c_not_strict_single_variable",
        "parent_result_preserved": True,
        "parent_scope": "original_p6_reference_131k_c1_config_only",
        "parent_is_not_a_universal_chunked_prefill_infeasibility_claim": True,
        "this_workload_is_a_new_result_chain": True,
    }
    frozen = workload["shared_runtime_freeze"]
    assert frozen["max_model_len"] == 69632
    assert frozen["max_num_batched_tokens"] == 69632
    assert frozen["max_num_seqs"] == 2
    assert frozen["prefix_cache_flag_both_modes"] == "--no-enable-prefix-caching"
    assert frozen["speculative_config"] == {
        "method": "mtp",
        "num_speculative_tokens": 1,
    }
    assert workload["single_variable"] == {
        "name": "enable_chunked_prefill",
        "off_flag": "--no-enable-chunked-prefill",
        "on_flag": "--enable-chunked-prefill",
        "normalized_server_argv_delta_count_within_each_track": 1,
        "all_other_argv_equal_within_each_track": True,
        "resolved_value_required_before_requests": True,
        "off_resolved_value": False,
        "on_resolved_value": True,
    }


def test_three_cells_create_real_multi_request_budget_pressure() -> None:
    workload = _load_yaml(WORKLOAD)
    cells = {cell["cell_id"]: cell for cell in workload["cells"]}

    assert cells["no_pressure_32k_32k"]["prompt_tokens"] == [32768, 32768]
    assert cells["no_pressure_32k_32k"]["total_prefill_tokens"] == 65536
    assert cells["asymmetric_pressure_64k_32k"]["prompt_tokens"] == [
        65536,
        32768,
    ]
    assert cells["asymmetric_pressure_64k_32k"]["request_roles"] == [
        "long",
        "short",
    ]
    assert cells["symmetric_pressure_48k_48k"]["prompt_tokens"] == [
        49152,
        49152,
    ]
    assert cells["asymmetric_pressure_64k_32k"]["total_prefill_tokens"] > 69632
    assert cells["symmetric_pressure_48k_48k"]["total_prefill_tokens"] > 69632
    assert cells["no_pressure_32k_32k"]["total_prefill_tokens"] < 69632


def test_prepare_uses_one_batched_http_body_for_each_two_request_cell(
    tmp_path: Path,
) -> None:
    import tools.inference_contracts.run_deepseek_p6_3c_r1_scheduler_pressure as runner

    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    artifact_dir = tmp_path / "result"
    manifest = runner.prepare_artifacts(source, artifact_dir, "model")
    plan = json.loads((artifact_dir / "run_plan.json").read_text(encoding="utf-8"))

    assert manifest["canonical_batch_body_count"] == 14
    assert len(plan["mechanism"]) == 4
    assert len(plan["performance"]) == 10
    for track in runner.TRACKS:
        for batch in plan[track]:
            body = json.loads(
                (artifact_dir / batch["body_relative_path"]).read_text(
                    encoding="utf-8"
                )
            )
            if batch["phase"] == "measured":
                assert len(body["prompt"]) == 2
                assert [len(prompt) for prompt in body["prompt"]] == batch[
                    "prompt_tokens"
                ]
                assert body["request_id"] == batch["request_id"]
            assert body["stream"] is True
            assert body["return_token_ids"] is True
            assert body["max_tokens"] == body["min_tokens"] == 64


def test_observer_summary_distinguishes_partial_prefill_rounds() -> None:
    from tools.inference_contracts.p6_3c_r1_scheduler_observer import (
        summarize_scheduler_rows,
    )

    rows = [
        {
            "event": "scheduler_step",
            "step_index": 1,
            "scheduled_requests": [
                {
                    "request_id": "long",
                    "prompt_tokens": 65536,
                    "remaining_prompt_tokens_before": 65536,
                    "scheduled_tokens": 65536,
                    "prefill_scheduled": True,
                    "prefill_partial": False,
                },
                {
                    "request_id": "short",
                    "prompt_tokens": 32768,
                    "remaining_prompt_tokens_before": 32768,
                    "scheduled_tokens": 4096,
                    "prefill_scheduled": True,
                    "prefill_partial": True,
                },
            ],
        },
        {
            "event": "scheduler_step",
            "step_index": 2,
            "scheduled_requests": [
                {
                    "request_id": "short",
                    "prompt_tokens": 32768,
                    "remaining_prompt_tokens_before": 28672,
                    "scheduled_tokens": 28672,
                    "prefill_scheduled": True,
                    "prefill_partial": False,
                }
            ],
        },
    ]
    summary = summarize_scheduler_rows(rows)

    assert summary["scheduler_step_count"] == 2
    assert summary["prefill_request_count"] == 2
    assert summary["partial_prefill_request_count"] == 1
    by_id = {row["request_id"]: row for row in summary["request_rows"]}
    assert by_id["long"]["prefill_round_count"] == 1
    assert by_id["short"]["prefill_round_count"] == 2
    assert by_id["short"]["partial_prefill_round_count"] == 1
    assert by_id["short"]["scheduled_prefill_tokens"] == 32768


def test_mode_and_top_runner_audits_freeze_tracks_and_balanced_order() -> None:
    environment = {**dict(), "P6_3C_R1_AUDIT_ONLY": "1", "PYTHON_BIN": "python"}
    completed = subprocess.run(
        ["bash", str(TOP_RUNNER), "/audit/p6_3c_r1"],
        cwd=REPO_ROOT,
        env={**__import__("os").environ, **environment},
        check=True,
        capture_output=True,
        text=True,
    )
    output = completed.stdout

    assert "model_lifecycle_count_exact=6" in output
    assert "engine_request_count_exact=90" in output
    assert "request_retry_count_exact=0" in output
    assert output.splitlines().count("observer=enabled") == 2
    assert output.splitlines().count("observer=disabled") == 4
    assert output.index("performance_01") < output.index("performance_02")
    assert output.index("performance_02") < output.index("performance_03")
    assert output.index("performance_03") < output.index("performance_04")
    assert output.count(
        "server_argv_sha256=1176d6e37dd0be874eb0b3647a5317e171c26730e26f95a29cfbe5487675dc93"
    ) == 3
    assert output.count(
        "server_argv_sha256=114aae24f15f6338ab0446e83c1911fe27808c3050b1e7906535275c2e621f44"
    ) == 3


def _scheduler_step(
    batch: dict,
    mode: str,
) -> list[dict]:
    marker = f"cmpl-{batch['request_id']}-"
    prompt_a, prompt_b = batch["prompt_tokens"]
    if not batch["pressure"]:
        scheduled = [
            {
                "request_id": marker + "0",
                "prompt_tokens": prompt_a,
                "remaining_prompt_tokens_before": prompt_a,
                "scheduled_tokens": prompt_a,
                "prefill_scheduled": True,
                "prefill_partial": False,
            },
            {
                "request_id": marker + "1",
                "prompt_tokens": prompt_b,
                "remaining_prompt_tokens_before": prompt_b,
                "scheduled_tokens": prompt_b,
                "prefill_scheduled": True,
                "prefill_partial": False,
            },
        ]
        return [
            {
                "event": "scheduler_step",
                "step_index": 1,
                "scheduled_requests": scheduled,
                "waiting_order_before": [marker + "0", marker + "1"],
                "waiting_order_after": [],
            }
        ]
    if mode == "chunked_prefill_off":
        return [
            {
                "event": "scheduler_step",
                "step_index": 1,
                "scheduled_requests": [
                    {
                        "request_id": marker + "0",
                        "prompt_tokens": prompt_a,
                        "remaining_prompt_tokens_before": prompt_a,
                        "scheduled_tokens": prompt_a,
                        "prefill_scheduled": True,
                        "prefill_partial": False,
                    }
                ],
                "waiting_order_before": [marker + "0", marker + "1"],
                "waiting_order_after": [marker + "1"],
            },
            {
                "event": "scheduler_step",
                "step_index": 2,
                "scheduled_requests": [
                    {
                        "request_id": marker + "1",
                        "prompt_tokens": prompt_b,
                        "remaining_prompt_tokens_before": prompt_b,
                        "scheduled_tokens": prompt_b,
                        "prefill_scheduled": True,
                        "prefill_partial": False,
                    }
                ],
                "waiting_order_before": [marker + "1"],
                "waiting_order_after": [],
            },
        ]
    first_for_second = 69632 - prompt_a
    return [
        {
            "event": "scheduler_step",
            "step_index": 1,
            "scheduled_requests": [
                {
                    "request_id": marker + "0",
                    "prompt_tokens": prompt_a,
                    "remaining_prompt_tokens_before": prompt_a,
                    "scheduled_tokens": prompt_a,
                    "prefill_scheduled": True,
                    "prefill_partial": False,
                },
                {
                    "request_id": marker + "1",
                    "prompt_tokens": prompt_b,
                    "remaining_prompt_tokens_before": prompt_b,
                    "scheduled_tokens": first_for_second,
                    "prefill_scheduled": True,
                    "prefill_partial": True,
                },
            ],
            "waiting_order_before": [marker + "0", marker + "1"],
            "waiting_order_after": [],
        },
        {
            "event": "scheduler_step",
            "step_index": 2,
            "scheduled_requests": [
                {
                    "request_id": marker + "1",
                    "prompt_tokens": prompt_b,
                    "remaining_prompt_tokens_before": prompt_b - first_for_second,
                    "scheduled_tokens": prompt_b - first_for_second,
                    "prefill_scheduled": True,
                    "prefill_partial": False,
                }
            ],
            "waiting_order_before": [],
            "waiting_order_after": [],
        },
    ]


def test_synthetic_complete_result_closes_mechanism_and_package_gates(
    tmp_path: Path,
) -> None:
    import tools.inference_contracts.run_deepseek_p6_3c_r1_scheduler_pressure as runner

    artifact = tmp_path / "result"
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    runner.prepare_artifacts(source, artifact, "model")
    plan = json.loads((artifact / "run_plan.json").read_text(encoding="utf-8"))
    with (artifact / "executed_lifecycle_schedule.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "track",
                "lifecycle_id",
                "pair_id",
                "pair_position",
                "mode",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(runner.LIFECYCLE_SCHEDULE)

    for schedule in runner.LIFECYCLE_SCHEDULE:
        lifecycle = artifact / "lifecycles" / schedule["lifecycle_id"]
        runtime = lifecycle / "runtime"
        runtime.mkdir(parents=True)
        lifecycle_plan = plan[schedule["track"]]
        request_rows = []
        batch_rows = []
        for batch in lifecycle_plan:
            for choice in batch["choices"] if "choices" in batch else [
                {
                    "choice_index": index,
                    "request_role": role,
                    "prompt_tokens": tokens,
                }
                for index, (role, tokens) in enumerate(
                    zip(
                        batch["request_roles"],
                        batch["prompt_tokens"],
                        strict=True,
                    )
                )
            ]:
                request_rows.append(
                    {
                        "track": schedule["track"],
                        "mode": schedule["mode"],
                        "phase": batch["phase"],
                        "batch_id": batch["batch_id"],
                        "cell_id": batch["cell_id"],
                        "repeat_index": batch["repeat_index"],
                        "choice_index": choice["choice_index"],
                        "request_role": choice["request_role"],
                        "prompt_tokens": choice["prompt_tokens"],
                        "output_tokens": 64,
                            "request_body_sha256": batch["request_body_sha256"],
                        "status": "success",
                        "ttft_ms": 10.0,
                        "e2el_ms": 100.0,
                        "tpot_ms": 1.4,
                        "itl_p50_ms": 1.3,
                        "itl_p95_ms": 1.6,
                        "itl_p99_ms": 1.8,
                    }
                )
            batch_rows.append(
                {
                    "track": schedule["track"],
                    "mode": schedule["mode"],
                    "phase": batch["phase"],
                    "batch_id": batch["batch_id"],
                    "cell_id": batch["cell_id"],
                    "repeat_index": batch["repeat_index"],
                    "status": "success",
                    "batch_output_tokens_per_second": 10.0,
                    "two_request_completion_gap_ms": 1.0,
                }
            )
        (lifecycle / "raw_request_results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in request_rows),
            encoding="utf-8",
        )
        (lifecycle / "raw_batch_results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in batch_rows),
            encoding="utf-8",
        )
        (lifecycle / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
        (lifecycle / "lifecycle_exit_code.txt").write_text("0\n", encoding="utf-8")
        (runtime / "resolved_scheduler_config.json").write_text(
            json.dumps(
                {
                    "resolved_enable_chunked_prefill": (
                        schedule["mode"] == "chunked_prefill_on"
                    ),
                    "resolved_enable_prefix_caching": False,
                    "observer_enabled": schedule["track"] == "mechanism",
                }
            ),
            encoding="utf-8",
        )
        flag = (
            "--enable-chunked-prefill"
            if schedule["mode"] == "chunked_prefill_on"
            else "--no-enable-chunked-prefill"
        )
        (runtime / "server_argv.json").write_text(
            json.dumps(
                {
                    "schema_version": "ak_infer_lab_server_argv_v1",
                    "argv": [
                        "vllm",
                        "--max-model-len",
                        "69632",
                        flag,
                        "--no-enable-prefix-caching",
                    ],
                }
            ),
            encoding="utf-8",
        )
        if schedule["track"] == "mechanism":
            trace_dir = runtime / "scheduler_trace"
            trace_dir.mkdir()
            trace = [
                {"event": "observer_installed"},
            ]
            for batch in lifecycle_plan:
                if batch["phase"] == "measured":
                    trace.extend(_scheduler_step(batch, schedule["mode"]))
            (trace_dir / "trace.1.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in trace),
                encoding="utf-8",
            )

    (artifact / "resource_recovery_summary.json").write_text(
        json.dumps(
            {
                "stopped_card_ids": list(range(8)),
                "restored_card_ids": list(range(8)),
                "keep_alive_restored_exact": True,
            }
        ),
        encoding="utf-8",
    )
    grading = runner.finalize_artifacts(artifact)
    manifest = runner.package_results(artifact)

    assert grading["server_grade"] == (
        "candidate_green_p6_3c_r1_chunked_prefill_"
        "scheduler_pressure_matched_ab"
    )
    assert grading["request_count"] == 90
    assert grading["successful_request_count"] == 90
    assert grading["mechanism_gate_complete"] is True
    assert grading["single_variable_argv_exact"] is True
    assert manifest["candidate_total_within_limit"] is True
    assert manifest["selection_required_before_any_transfer"] is True


def test_server_wrapper_contains_keep_alive_and_no_transfer_action() -> None:
    text = SERVER_TASK.read_text(encoding="utf-8")
    assert 'CARD_IDS=(0 1 2 3 4 5 6 7)' in text
    assert 'bash /data/node0_disk1/Public/npu_stop.sh "${CARD_IDS[@]}"' in text
    assert 'bash /data/node0_disk1/Public/npu_keep_alive.sh "${CARD_IDS[@]}"' in text
    assert text.index("npu_stop.sh") < text.index("npu_keep_alive.sh")
    assert "result_transfer_authorized=true" in text
    assert "automatic_transfer_allowed=false" in text
    assert "transfer_method_selected=false" in text
    assert "send_notify.py" not in text
    assert "upload_file.py" not in text
