from pathlib import Path
import hashlib
import json
import os
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
R1_WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml"
)
K0_WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k0_order_balanced_prefix_cache_baseline.yaml"
)
K0_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k0_order_balanced_prefix_baseline.sh"
)
K0_MODE_RUNNER = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p8_2_k0_mode.sh"
)
K0_PYTHON = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py"
)
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"
READINESS = REPO_ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _green_request_rows(runner) -> list[dict]:
    rows = []
    for schedule in runner.LIFECYCLE_SCHEDULE:
        for pair_slot, role in (
            ("warmup", "warmup"),
            ("prime", "prime"),
            ("measured_01", "measured"),
            ("measured_02", "measured"),
            ("measured_03", "measured"),
        ):
            is_on_measured = (
                schedule["mode"] == "prefix_cache_on" and role == "measured"
            )
            rows.append(
                {
                    **schedule,
                    "request_id": f"{schedule['lifecycle_id']}_{pair_slot}",
                    "pair_slot": pair_slot,
                    "k0_role": role,
                    "request_role": role,
                    "status": "success",
                    "http_status": 200,
                    "prompt_tokens": 65536,
                    "context_tokens": 65536,
                    "output_tokens": 64,
                    "generated_token_count": 64,
                    "streamed_token_count": 64,
                    "finish_reason": "length",
                    "saw_done": True,
                    "max_token_chunk_width": 2,
                    "request_body_sha256": f"sha-{pair_slot}",
                    "expected_prefix_hit_tokens": 49152 if role == "measured" else 0,
                    "prefix_queries_delta": 65536,
                    "prefix_hits_delta": 49152 if is_on_measured else 0,
                    "accepted_token_delta": 32,
                    "queue_metrics_ok": True,
                    "counter_continuity_ok": True,
                    "spec_activity_ok": True,
                    "prefix_evidence_ok": True,
                    "ttft_ms": 10.0,
                    "tpot_ms": 2.0,
                    "itl_p50_ms": 2.0,
                    "itl_p95_ms": 2.2,
                    "itl_p99_ms": 2.3,
                    "e2el_ms": 138.0,
                    "output_tokens_per_second": 463.0,
                }
            )
    return rows


def _write_green_raw_k0_artifacts(source_dir: Path, runner) -> None:
    rows = _green_request_rows(runner)
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "request_body_manifest.json").write_text(
        json.dumps(
            {
                "task_id": runner.TASK_ID,
                "canonical_body_count": 5,
                "total_request_count": 20,
                "generated_text_retained": False,
                "token_ids_retained": False,
                "canonical_bodies": [
                    {
                        "pair_slot": slot,
                        "request_body_sha256": f"sha-{slot}",
                        "context_tokens": 65536,
                        "body_bytes": 123,
                    }
                    for slot in (
                        "warmup",
                        "prime",
                        "measured_01",
                        "measured_02",
                        "measured_03",
                    )
                ],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    diagnostics = [
        {
            "event": "runtime_patch_installed",
            "retention_interval": None,
            "source_evidence": {"source": {"match": True}},
        },
        {
            "event": "coordinator_snapshot",
            "lcm_block_size": 16384,
            "eagle_group_ids": [1],
            "attention_groups": [{"group_ids": [0, 1]}],
            "managers": [
                {"group_id": 0, "manager_type": "Full", "use_eagle": True},
                {"group_id": 1, "manager_type": "Compress", "use_eagle": True},
            ],
            "prefix_cache_retention_interval": None,
        },
        {"event": "eagle_lookahead_cache_target"},
        {"event": "deferred_import_order_verified"},
    ]
    for schedule in runner.LIFECYCLE_SCHEDULE:
        mode_dir = (
            source_dir
            / "lifecycles"
            / schedule["lifecycle_id"]
            / "modes"
            / schedule["mode"]
        )
        runtime_dir = mode_dir / "runtime"
        runtime_dir.mkdir(parents=True)
        lifecycle_rows = [
            row
            for row in rows
            if row["lifecycle_id"] == schedule["lifecycle_id"]
        ]
        (mode_dir / "raw_request_results.jsonl").write_text(
            "".join(
                json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
                for row in lifecycle_rows
            ),
            encoding="utf-8",
        )
        (mode_dir / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
        (mode_dir / "repair_identity.tsv").write_text(
            "repair\tsame-r2\n", encoding="utf-8"
        )
        (mode_dir / "server_command_sha256.txt").write_text(
            runner.EXPECTED_COMMAND_SHA256[schedule["mode"]]
            + "  server_command.txt\n",
            encoding="utf-8",
        )
        (runtime_dir / "resolved_prefix_cache_config.json").write_text(
            json.dumps(
                {
                    "resolved_enable_prefix_caching": (
                        schedule["mode"] == "prefix_cache_on"
                    ),
                    "server_command_has_expected_flag": True,
                    "server_command_has_opposite_flag": False,
                    "process_cmdline_has_expected_flag": True,
                    "process_cmdline_has_opposite_flag": False,
                }
            ),
            encoding="utf-8",
        )
        (runtime_dir / "source_gate_status.txt").write_text(
            "pass\n", encoding="utf-8"
        )
        (runtime_dir / "hybrid_kv_runtime_diagnostic.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in diagnostics),
            encoding="utf-8",
        )


def test_p8_1_r1_server_result_is_closed_as_developer_accepted_green():
    workload = _load_yaml(R1_WORKLOAD)
    state = workload["execution_state"]
    result = workload["execution_result"]

    assert state == {
        "status": "completed_developer_accepted_green",
        "server_handoff": "consumed_historical",
        "server_result": "developer_reviewed",
        "npu_execution_authorized": False,
        "next_task_authorized": False,
        "result_transfer_authorized": False,
        "standing_npu_and_vllm_consumption_authorization": True,
    }
    assert result["server_grade"] == (
        "candidate_green_p8_1_r1_official_mtp_observe_only_matrix"
    )
    assert result["developer_grade"] == (
        "green_p8_1_r1_official_mtp_observe_only_matrix"
    )
    assert result["successful_request_count"] == "6_of_6"
    assert result["shared_follower_prefix_hit_tokens"] == 49152
    assert result["other_five_prefix_hit_tokens"] == [0, 0, 0, 0, 0]
    assert result["cause_supported_by_replay"] is True
    assert result["cause_proven_as_unique"] is False
    assert result["cleanup"] == "clean"
    assert result["candidate_file_count"] == 15
    assert result["candidate_total_bytes"] == 22664
    assert result["package_sha256_verified_by_developer"] is True
    assert result["aborted_pre_request_source_gate_invocations"] == 1
    assert result["request_lifecycle_count"] == 1
    assert result["request_retry_count"] == 0
    assert result["base_vllm_root"] == "/data/node0_disk1/vllm-0.22.1/vllm"


def test_k0_workload_is_an_order_balanced_single_variable_64k_pilot():
    workload = _load_yaml(K0_WORKLOAD)

    assert workload["stage_contract"] == {
        "stage": "P8.2-K0",
        "mode": "order_balanced_explicit_prefix_cache_on_off_unprofiled_pilot",
        "claim_boundary": (
            "order_balanced_64k_exact_reuse_prefix_cache_on_off_"
            "descriptive_baseline_only"
        ),
        "performance_reference_authorized": False,
        "offload_or_real_move_authorized": False,
        "p8_2_k1_execution_authorized": False,
    }
    assert workload["depends_on"]["p8_1_r1_grade"] == (
        "green_p8_1_r1_official_mtp_observe_only_matrix"
    )
    assert workload["depends_on"]["p6_3b_r4_r1_grade"] == (
        "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
    )

    assert workload["runtime_fixed"] == {
        "model_path": "/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp",
        "max_model_len": 135168,
        "max_num_batched_tokens": 4096,
        "max_num_seqs": 1,
        "block_size": 128,
        "tensor_parallel_size": 8,
        "enable_expert_parallel": True,
        "quantization": "ascend",
        "enable_chunked_prefill": True,
        "speculative_method": "mtp",
        "num_speculative_tokens": 1,
        "cudagraph_mode": "FULL_DECODE_ONLY",
    }
    variable = workload["single_variable"]
    assert variable["name"] == "enable_prefix_caching"
    assert variable["prefix_cache_off_flag"] == "--no-enable-prefix-caching"
    assert variable["prefix_cache_on_flag"] == "--enable-prefix-caching"
    assert variable["normalized_server_argv_delta_count"] == 1
    assert variable["all_other_argv_and_environment_equal"] is True

    schedule = workload["order_balance"]
    assert [row["mode"] for row in schedule["lifecycle_schedule"]] == [
        "prefix_cache_off",
        "prefix_cache_on",
        "prefix_cache_on",
        "prefix_cache_off",
    ]
    assert [row["pair_id"] for row in schedule["lifecycle_schedule"]] == [
        "pair_01",
        "pair_01",
        "pair_02",
        "pair_02",
    ]
    assert schedule["each_mode_first_once_and_second_once"] is True
    assert schedule["post_hoc_reordering_allowed"] is False

    requests = workload["request_plan"]
    assert requests["context_tokens"] == 65536
    assert requests["output_tokens"] == 64
    assert requests["concurrency"] == 1
    assert requests["lifecycle_count"] == 4
    assert requests["requests_per_lifecycle"] == 5
    assert requests["warmup_requests_total"] == 4
    assert requests["prime_requests_total"] == 4
    assert requests["measured_follower_requests_total"] == 12
    assert requests["total_request_count"] == 20
    assert requests["matched_measured_pair_count"] == 6
    assert requests["request_retries"] == 0
    assert requests["warmup_has_no_cacheable_lcp_with_primary"] is True
    assert requests["bodies_byte_identical_across_all_lifecycles"] is True

    evidence = workload["evidence_contract"]
    assert evidence["unprofiled"] is True
    assert evidence["prefix_cache_hit_exact"] is True
    assert evidence["per_request_mtp_health_queue"] is True
    assert evidence["streaming_metrics"] == [
        "ttft_ms",
        "tpot_ms",
        "itl_p50_ms",
        "itl_p95_ms",
        "itl_p99_ms",
        "e2el_ms",
        "output_tokens_per_second",
    ]
    assert workload["stop_policy"]["no_profiler_or_offload"] is True
    assert workload["stop_policy"]["no_k1_k2_k3_k4_p8_3_p9"] is True


def test_k0_preparer_freezes_five_64k_bodies_across_four_lifecycles(
    tmp_path: Path,
):
    from tools.inference_contracts import (
        run_deepseek_p8_2_k0_order_balanced_prefix_baseline as runner,
    )

    source = tmp_path / "source_payload.json"
    source.write_text(
        json.dumps({"prompt": list(range(4096))}), encoding="utf-8"
    )
    artifact_dir = tmp_path / "k0"
    manifest = runner.prepare_k0_artifacts(
        source, artifact_dir, "deepseek-v4-flash-w8a8-mtp"
    )

    assert manifest["lifecycle_schedule"] == [
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
    ]
    assert manifest["canonical_body_count"] == 5
    assert manifest["total_request_count"] == 20
    assert manifest["matched_measured_pair_count"] == 6
    assert manifest["warmup_primary_lcp_less_than_128"] is True
    assert manifest["body_pairing_exact"] is True
    assert manifest["generated_text_retained"] is False
    assert manifest["token_ids_retained"] is False

    canonical = manifest["canonical_bodies"]
    assert [row["k0_role"] for row in canonical] == [
        "warmup",
        "prime",
        "measured",
        "measured",
        "measured",
    ]
    assert all(row["context_tokens"] == 65536 for row in canonical)
    assert len({row["request_body_sha256"] for row in canonical}) == 5
    assert all(
        row["expected_prefix_hit_tokens"] == 49152
        for row in canonical
        if row["k0_role"] == "measured"
    )

    hashes_by_slot = {}
    for schedule in manifest["lifecycle_schedule"]:
        lifecycle_dir = artifact_dir / "lifecycles" / schedule["lifecycle_id"]
        plan = json.loads(
            (lifecycle_dir / "run_plan.json").read_text(encoding="utf-8")
        )
        assert len(plan) == 5
        assert [row["k0_role"] for row in plan] == [
            "warmup",
            "prime",
            "measured",
            "measured",
            "measured",
        ]
        assert all(row["mode"] == schedule["mode"] for row in plan)
        for row in plan:
            hashes_by_slot.setdefault(row["pair_slot"], set()).add(
                row["request_body_sha256"]
            )
            body = lifecycle_dir / row["body_relative_path"]
            assert body.is_file()
    assert all(len(hashes) == 1 for hashes in hashes_by_slot.values())


def test_k0_grading_accepts_only_complete_order_balanced_paired_evidence():
    from tools.inference_contracts import (
        run_deepseek_p8_2_k0_order_balanced_prefix_baseline as runner,
    )

    rows = _green_request_rows(runner)

    grade = runner.grade_k0_evidence(
        rows,
        cleanup_by_lifecycle={
            row["lifecycle_id"]: "clean"
            for row in runner.LIFECYCLE_SCHEDULE
        },
        repair_identity_by_lifecycle={
            row["lifecycle_id"]: {"repair": "same-r2"}
            for row in runner.LIFECYCLE_SCHEDULE
        },
        resolved_prefix_by_lifecycle={
            row["lifecycle_id"]: row["mode"] == "prefix_cache_on"
            for row in runner.LIFECYCLE_SCHEDULE
        },
        server_command_sha256_by_lifecycle={
            row["lifecycle_id"]: (
                "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19"
                if row["mode"] == "prefix_cache_on"
                else "def3dd8bf71ee4cac1922b0d4fa14321e1df5369fd8a5997771d00f3be6418ea"
            )
            for row in runner.LIFECYCLE_SCHEDULE
        },
        diagnostic_ok_by_lifecycle={
            row["lifecycle_id"]: True
            for row in runner.LIFECYCLE_SCHEDULE
        },
    )

    assert grade["server_grade"] == (
        "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
    )
    assert grade["successful_request_count"] == 20
    assert grade["warmup_request_count"] == 4
    assert grade["prime_request_count"] == 4
    assert grade["measured_request_count"] == 12
    assert grade["matched_measured_pair_count"] == 6
    assert grade["order_balance_exact"] is True
    assert grade["body_pairing_exact"] is True
    assert grade["single_variable_server_argv_exact"] is True
    assert grade["same_r2_repair_all_lifecycles"] is True
    assert grade["diagnostic_ok_all_lifecycles"] is True
    assert grade["resolved_prefix_control_exact"] is True
    assert grade["on_measured_hit_exact_count"] == 6
    assert grade["off_prefix_hit_total"] == 0
    assert grade["on_non_measured_prefix_hit_total"] == 0
    assert grade["cleanup"] == "clean"
    assert grade["performance_reference_accepted"] is False
    assert grade["offload_evidence_accepted"] is False


def test_k0_grading_reports_the_first_request_evidence_predicate_failure():
    from tools.inference_contracts import (
        run_deepseek_p8_2_k0_order_balanced_prefix_baseline as runner,
    )

    rows = _green_request_rows(runner)
    rows[7]["finish_reason"] = "stop"
    grade = runner.grade_k0_evidence(
        rows,
        cleanup_by_lifecycle={
            row["lifecycle_id"]: "clean" for row in runner.LIFECYCLE_SCHEDULE
        },
        repair_identity_by_lifecycle={
            row["lifecycle_id"]: {"repair": "same-r2"}
            for row in runner.LIFECYCLE_SCHEDULE
        },
        resolved_prefix_by_lifecycle={
            row["lifecycle_id"]: row["mode"] == "prefix_cache_on"
            for row in runner.LIFECYCLE_SCHEDULE
        },
        server_command_sha256_by_lifecycle={
            row["lifecycle_id"]: runner.EXPECTED_COMMAND_SHA256[row["mode"]]
            for row in runner.LIFECYCLE_SCHEDULE
        },
        diagnostic_ok_by_lifecycle={
            row["lifecycle_id"]: True for row in runner.LIFECYCLE_SCHEDULE
        },
    )

    assert grade["request_evidence_exact"] is False
    assert grade["request_evidence_predicate_counts"]["finish_reason_length"] == {
        "passed": 19,
        "total": 20,
    }
    assert grade["first_request_evidence_failure"] == {
        "request_id": rows[7]["request_id"],
        "lifecycle_id": rows[7]["lifecycle_id"],
        "mode": rows[7]["mode"],
        "pair_slot": rows[7]["pair_slot"],
        "predicate": "finish_reason_length",
        "observed": "stop",
        "expected": "length",
    }


def test_k0_finalizer_writes_only_bounded_sanitized_candidate_evidence(
    tmp_path: Path,
):
    from tools.inference_contracts import (
        run_deepseek_p8_2_k0_order_balanced_prefix_baseline as runner,
    )

    _write_green_raw_k0_artifacts(tmp_path, runner)

    grading = runner.finalize_k0_artifacts(tmp_path)
    assert grading["server_grade"] == (
        "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
    )
    candidate_names = {
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
    }
    manifest_rows = (tmp_path / "delivery_candidates.tsv").read_text(
        encoding="utf-8"
    ).splitlines()[1:]
    assert {Path(line.split("\t")[0]).name for line in manifest_rows} == candidate_names
    assert grading["candidate_file_count"] == 14
    assert grading["candidate_total_bytes"] <= 71680
    assert grading["candidate_size_gate_pass"] is True
    request_summary = json.loads(
        (tmp_path / "mtp_queue_health_summary.json").read_text(encoding="utf-8")
    )
    assert request_summary["request_evidence_predicate_counts"][
        "generated_tokens_exact"
    ] == {"passed": 20, "total": 20}
    assert request_summary["request_evidence_predicate_counts"][
        "finish_reason_length"
    ] == {"passed": 20, "total": 20}
    assert request_summary["first_request_evidence_failure"] is None
    assert (tmp_path / "first_failure_excerpt.txt").read_text(
        encoding="utf-8"
    ) == "none\n"
    candidate_text = "\n".join(
        (tmp_path / name).read_text(encoding="utf-8") for name in candidate_names
    )
    assert '"prompt":' not in candidate_text
    assert "generated_content" not in candidate_text
    assert "returned_token_ids" not in candidate_text


def test_k0_r1_refinalizes_existing_raw_evidence_without_mutating_source(
    tmp_path: Path,
):
    from tools.inference_contracts import (
        run_deepseek_p8_2_k0_order_balanced_prefix_baseline as runner,
    )

    source_dir = tmp_path / "p8_2_k0_run01"
    output_dir = tmp_path / "p8_2_k0_r1_refinalized"
    _write_green_raw_k0_artifacts(source_dir, runner)
    before = {
        str(path.relative_to(source_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_dir.rglob("*")
        if path.is_file()
    }

    grading = runner.refinalize_k0_artifacts(source_dir, output_dir)

    after = {
        str(path.relative_to(source_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_dir.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert grading["server_grade"] == (
        "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
    )
    assert grading["request_evidence_exact"] is True
    assert grading["refinalization_task_id"] == runner.REFINALIZATION_TASK_ID
    assert grading["source_evidence_file_count"] == 29
    assert grading["source_evidence_unchanged"] is True
    environment = json.loads(
        (output_dir / "environment_and_hashes.json").read_text(encoding="utf-8")
    )
    assert environment["execution_mode"] == "offline_existing_raw_evidence_only"
    assert environment["npu_started"] is False
    assert environment["vllm_started"] is False
    assert environment["model_request_sent"] is False
    assert environment["source_evidence_file_count"] == 29
    assert len(environment["source_evidence_inventory_sha256"]) == 64
    assert (output_dir / "request_body_manifest.json").read_bytes() == (
        source_dir / "request_body_manifest.json"
    ).read_bytes()


def test_k0_runners_freeze_editable_source_root_and_audit_four_lifecycles(
    tmp_path: Path,
):
    mode_runner = K0_MODE_RUNNER.read_text(encoding="utf-8")
    assert "run_deepseek_p6_3b_r4_r1_mode.sh" in mode_runner
    assert "run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py" in mode_runner
    assert (
        "BASE_VLLM_ROOT:-/data/node0_disk1/vllm-0.22.1/vllm"
        in mode_runner
    )
    assert "run_deepseek_p6_3b_r4_mode.sh" not in mode_runner
    top_runner = K0_RUNNER.read_text(encoding="utf-8")
    assert "append_no_proxy" in top_runner
    assert 'export no_proxy="$(append_no_proxy "${no_proxy:-}")"' in top_runner
    assert 'export NO_PROXY="$(append_no_proxy "${NO_PROXY:-}")"' in top_runner

    for script in (K0_RUNNER, K0_MODE_RUNNER):
        subprocess.run(["bash", "-n", str(script)], check=True)

    result_dir = tmp_path / "must_not_be_created"
    completed = subprocess.run(
        ["bash", str(K0_RUNNER), str(result_dir)],
        cwd=REPO_ROOT,
        env={**os.environ, "P8_2_K0_AUDIT_ONLY": "1"},
        check=True,
        text=True,
        capture_output=True,
    )
    assert not result_dir.exists()
    assert completed.stdout.splitlines() == [
        "task_id=p8_2_k0_deepseek_v4_flash_order_balanced_prefix_cache_baseline_2026_0717",
        "lifecycle_01\tpair_01\tfirst\tprefix_cache_off",
        "lifecycle_02\tpair_01\tsecond\tprefix_cache_on",
        "lifecycle_03\tpair_02\tfirst\tprefix_cache_on",
        "lifecycle_04\tpair_02\tsecond\tprefix_cache_off",
        "lifecycle_count=4",
        "request_count=20",
        "measured_request_count=12",
        "matched_measured_pair_count=6",
        "base_vllm_root=/data/node0_disk1/vllm-0.22.1/vllm",
        "prefix_cache_off_server_command_sha256=def3dd8bf71ee4cac1922b0d4fa14321e1df5369fd8a5997771d00f3be6418ea",
        "prefix_cache_on_server_command_sha256=370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19",
    ]

    help_result = subprocess.run(
        ["python3", str(K0_PYTHON), "--help"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "prepare" in help_result.stdout
    assert "run-mode" in help_result.stdout
    assert "finalize" in help_result.stdout
    assert "refinalize" in help_result.stdout


def test_k0_is_green_and_k1a_r5_f0_is_the_only_handoff():
    handoff = HANDOFF.read_text(encoding="utf-8")
    task_id = "p8_2_k1a_r5_f1_r5_effective_restore_contract_2026_0722"
    assert handoff.count("当前唯一服务器动作") == 1
    assert f"task_id: {task_id}" in handoff
    assert (
        "execution_mode: authorized_single_lifecycle_effective_restore_contract"
    ) in handoff
    assert "server_sync_review_authorized: true" in handoff
    assert "npu_execution_authorized: true" in handoff
    assert "next_task_authorized: false" in handoff
    assert "result_transfer_authorized: true" in handoff
    assert "formal_model_lifecycle_count_exact: 1" in handoff
    assert "model_request_count_max: 4" in handoff
    assert "profiler_authorized: false" in handoff
    assert "runtime_or_dependency_mutation_authorized: false" in handoff
    assert "keep_alive_stop_authorized: true" in handoff
    assert "vllm_server_start_authorized: true" in handoff
    assert "model_requests_authorized: true" in handoff
    assert "SimpleCPUOffloadConnector" in handoff
    assert "不得进入 K2" in handoff

    readiness = _load_yaml(READINESS)
    artifacts = readiness["artifacts"]
    assert artifacts["completed_p8_1_r1_workload"].endswith(
        "p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml"
    )
    assert artifacts["completed_p8_2_k0_workload"].endswith(
        "p8_2_k0_order_balanced_prefix_cache_baseline.yaml"
    )
    assert artifacts["next_workload"].endswith(
        "p8_2_k1a_r5_f1_r5_effective_restore_contract.yaml"
    )
    assert artifacts["current_server_handoff_task"] == task_id
    assert artifacts["current_p8_2_k0_refinalizer"].endswith(
        "run_deepseek_p8_2_k0_order_balanced_prefix_baseline.py"
    )
    acceptance = readiness["acceptance"]
    assert acceptance["p8_1_r1_grade"] == (
        "green_p8_1_r1_official_mtp_observe_only_matrix"
    )
    assert acceptance["p8_1_r1_execution_authorized"] is False
    assert acceptance["p8_2_k0_grade"] == (
        "green_p8_2_k0_order_balanced_prefix_cache_baseline"
    )
    assert acceptance["p8_2_k0_failure_class"] == (
        "finalizer_schema_mismatch_not_runtime_request_failure"
    )
    assert acceptance["p8_2_k0_execution_authorized"] is False
    assert acceptance["p8_2_k0_refinalization_authorized"] is False
    assert acceptance["p8_2_k1_feasibility_grade"] == (
        "blocked_p8_2_k1_frozen_stack_import_incompatible"
    )
    assert acceptance["p8_2_k1_execution_authorized"] is False
    assert acceptance["next_task_authorized"] is False

    workload = _load_yaml(K0_WORKLOAD)
    result = workload["execution_result"]
    assert result["original_server_grade"] == (
        "red_p8_2_k0_order_balanced_prefix_baseline_evidence_incomplete"
    )
    assert result["refinalized_server_grade"] == (
        "candidate_green_p8_2_k0_order_balanced_prefix_cache_baseline"
    )
    assert result["developer_grade"] == (
        "green_p8_2_k0_order_balanced_prefix_cache_baseline"
    )
    assert result["successful_request_count"] == "20_of_20"
    assert result["request_runtime_evidence_passed"] is True
    assert result["finalizer_schema_mismatch"] == {
        "producer_generated_field": "generated_token_count",
        "producer_streamed_field": "streamed_token_count",
        "old_finalizer_generated_field": "generated_tokens",
        "old_finalizer_streamed_field": "streamed_tokens",
    }
    assert workload["offline_refinalization"]["task_id"] == (
        "p8_2_k0_r1_offline_refinalization_2026_0717"
    )
    assert workload["offline_refinalization"]["developer_review"] == "accepted"
    assert workload["offline_refinalization"]["new_model_requests_authorized"] is False
    assert workload["offline_refinalization"]["source_result_must_remain_unchanged"] is True

    for relative_path in (
        "README.md",
        "docs/EXPERIMENT_PLAN.md",
        "docs/DEEPSEEK_V4_FLASH_ASCEND_PLAN.md",
        "docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md",
        "工作记录与进度笔记本/02_阶段计划.md",
        "工作记录与进度笔记本/05_下一步行动指导.md",
        "工作记录与进度笔记本/09_DeepSeek_V4_Flash_专项计划.md",
        "工作记录与进度笔记本/12_P5_P9_后续阶段重排计划.md",
    ):
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "P8.2-K0" in text, relative_path
        assert "K1A-R3" in text, relative_path
        assert "K1" in text, relative_path
        assert "blocked" in text, relative_path
