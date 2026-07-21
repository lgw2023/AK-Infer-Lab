import hashlib
import json
from pathlib import Path
import subprocess

import yaml

from tools.inference_contracts.finalize_deepseek_p8_1_observe_only_matrix import (
    finalize_matrix_artifacts,
)
from tools.inference_contracts.prepare_deepseek_p8_1_observe_matrix import (
    prepare_matrix_bodies,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/p8/"
    "p8_official_mtp_observe_matrix_contract.yaml"
)
WORKLOAD_PATH = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_1_vllm_ascend_official_mtp_observe_only_matrix.yaml"
)
RUNNER_PATH = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p8_1_observe_only_matrix.sh"
)
FINALIZER_PATH = (
    REPO_ROOT
    / "tools/inference_contracts/finalize_deepseek_p8_1_observe_only_matrix.py"
)


def test_matrix_baseline_freezes_three_accepted_official_mtp_contexts() -> None:
    contract = yaml.safe_load(BASELINE_PATH.read_text(encoding="utf-8"))

    assert contract["contract_status"] == "frozen_official"
    assert contract["claim_ceiling"] == "bounded_observe_only_matrix"
    assert contract["selected_workload"]["model_id"] == (
        "deepseek-ai/DeepSeek-V4-Flash-w8a8-mtp"
    )
    assert contract["selected_workload"]["request_success"] is True
    assert contract["selected_workload"]["validated"] is True
    cells = contract["observation_matrix"]["accepted_cells"]
    assert [cell["input_tokens"] for cell in cells] == [4096, 65536, 131072]
    assert all(cell["output_tokens"] == 64 for cell in cells)
    assert all(cell["concurrency"] == 1 for cell in cells)
    assert contract["observation_matrix"]["requests_per_context"] == 2
    assert contract["observation_matrix"]["request_count"] == 6
    assert contract["shared_prefix_probe"] == {
        "context_tokens": 65536,
        "token_lcp": 58880,
        "hybrid_lcm_tokens": 16384,
        "expected_prefix_hit_tokens": 49152,
        "source_grade": "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab",
        "performance_comparison_allowed": False,
    }
    assert contract["gate"]["real_vllm_ascend_adapter"] == "open_observe_only"
    assert contract["gate"]["p8_2_gate"] == "closed"


def test_matrix_workload_authorizes_six_sequential_observe_only_requests() -> None:
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))

    assert workload["task_id"] == (
        "p8_1_deepseek_v4_flash_official_mtp_observe_only_matrix_2026_0716"
    )
    assert workload["stage_contract"] == {
        "stage": "P8.1",
        "mode": "vllm_ascend_observe_only_bounded_matrix",
        "claim_boundary": "official_mtp_multicontext_shared_prefix_trace_only",
        "performance_comparison_authorized": False,
        "p8_2_execution_authorized": False,
    }
    assert workload["official_baseline"]["contract"].endswith(
        "p8_official_mtp_observe_matrix_contract.yaml"
    )
    runtime = workload["runtime_fixed"]
    assert runtime["tensor_parallel_size"] == 8
    assert runtime["enable_expert_parallel"] is True
    assert runtime["speculative_mtp"] == {
        "method": "mtp",
        "num_speculative_tokens": 1,
    }
    assert runtime["enable_chunked_prefill"] is True
    assert runtime["enable_prefix_caching"] is True
    assert runtime["cudagraph_mode"] == "FULL_DECODE_ONLY"
    assert runtime["max_model_len"] == 135168
    assert runtime["max_num_batched_tokens"] == 4096
    assert runtime["max_num_seqs"] == 1
    assert runtime["block_size"] == 128

    request_plan = workload["request_plan"]
    assert request_plan["request_count"] == 6
    assert request_plan["lifecycle_count"] == 1
    assert request_plan["concurrency"] == 1
    slots = request_plan["slots"]
    assert [slot["slot_id"] for slot in slots] == [
        "short_isolated_a",
        "medium_shared_prime",
        "medium_shared_follower",
        "long_isolated_a",
        "short_isolated_b",
        "long_isolated_b",
    ]
    assert [slot["input_tokens"] for slot in slots] == [
        4096,
        65536,
        65536,
        131072,
        4096,
        131072,
    ]
    assert [slot["expected_prefix_hit_tokens"] for slot in slots] == [
        0,
        0,
        49152,
        0,
        0,
        0,
    ]
    assert slots[2]["shared_prefix_with"] == "medium_shared_prime"
    assert slots[2]["token_lcp"] == 58880
    assert request_plan["all_other_pairwise_prefixes_less_than_tokens"] == 128
    assert request_plan["body_manifest_required"] is True
    assert request_plan["request_retries"] == 0

    observation = workload["observation_contract"]
    assert observation["per_request_prefix_mtp_health_queue"] is True
    assert observation["single_session_identity_required"] is True
    assert observation["deterministic_replay_bundle_count"] == 2
    assert observation["request_runtime_object_join_required"] is True
    assert observation["runtime_imports_allowed"] is False
    assert observation["payload_fields_allowed"] is False
    assert observation["placement_mutation_allowed"] is False
    assert workload["stop_policy"]["stop_on_first_request_failure"] is True
    assert workload["stop_policy"]["no_retry"] is True
    assert workload["stop_policy"]["no_profiler"] is True
    assert workload["stop_policy"]["no_offload"] is True
    assert workload["stop_policy"]["no_p8_2_p7_or_p9"] is True
    assert workload["execution_state"]["status"] == "completed_developer_reviewed_yellow"
    assert workload["execution_state"]["npu_execution_authorized"] is False
    assert workload["execution_state"]["result_transfer_authorized"] is False


def test_matrix_finalizer_accepts_six_joined_requests_and_deterministic_replay(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "p8_1_matrix"
    bundle_dir = artifact_dir / "observe_only_bundle"
    bundle_dir.mkdir(parents=True)

    slots = [
        ("short_isolated_a", "req_p8_short_isolated_a", 4096, 0),
        ("medium_shared_prime", "req_p8_medium_shared_prime", 65536, 0),
        (
            "medium_shared_follower",
            "req_p8_medium_shared_follower",
            65536,
            49152,
        ),
        ("long_isolated_a", "req_p8_long_isolated_a", 131072, 0),
        ("short_isolated_b", "req_p8_short_isolated_b", 4096, 0),
        ("long_isolated_b", "req_p8_long_isolated_b", 131072, 0),
    ]

    def write_json(path: Path, record: dict) -> None:
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    request_rows = []
    prefix_rows = []
    mtp_rows = []
    queue_rows = []
    transfer_rows = []
    events = []
    objects = []
    decisions = []
    for index, (slot_id, request_id, prompt_tokens, expected_hits) in enumerate(slots):
        request_rows.append(
            {
                "slot_id": slot_id,
                "request_id": request_id,
                "status": "success",
                "http_status": 200,
                "prompt_tokens": prompt_tokens,
                "generated_token_count": 64,
                "streamed_token_count": 64,
                "finish_reason": "length",
                "generated_text_retained": False,
                "token_ids_retained": False,
            }
        )
        prefix_rows.append(
            {
                "slot_id": slot_id,
                "request_id": request_id,
                "delta": {"queries": float(prompt_tokens), "hits": float(expected_hits)},
            }
        )
        mtp_rows.append(
            {
                "slot_id": slot_id,
                "counter_continuity": True,
                "delta": {
                    "num_drafts": 64.0,
                    "num_draft_tokens": 64.0,
                    "num_accepted_tokens": 32.0,
                },
            }
        )
        queue_rows.append(
            {
                "slot_id": slot_id,
                "health_before": True,
                "health_after": True,
                "running_after": 0.0,
                "waiting_after": 0.0,
            }
        )
        transfer_rows.append(
            {
                "slot_id": slot_id,
                "status": "unavailable",
                "event_emitted": False,
                "reason": "no_native_event",
            }
        )
        for stage in ("request_start", "first_token", "request_end"):
            events.append(
                {
                    "source_event_id": f"{request_id}:{stage}",
                    "trace_id": "trace_p8_matrix_0001",
                    "request_id": request_id,
                    "session_id": "session_p8_matrix_0001",
                    "event_type": "request_stage",
                    "action": stage,
                }
            )
        object_id = f"prefix_proxy:{request_id}"
        events.append(
            {
                "source_event_id": f"{request_id}:prefix_cache_counter_delta",
                "trace_id": "trace_p8_matrix_0001",
                "request_id": request_id,
                "session_id": "session_p8_matrix_0001",
                "event_type": "state_lifecycle",
                "action": "prefix_cache_counter_delta",
                "object_id": object_id,
            }
        )
        objects.append({"object_id": object_id, "payload_ref": None})
        decisions.append(
            {
                "object_id": object_id,
                "execution_mode": "observe_only",
                "action": "no_op",
                "executed": False,
                "execution_result": "skipped",
            }
        )

    write_json(artifact_dir / "request_matrix_summary.json", {"requests": request_rows})
    write_json(
        artifact_dir / "prefix_cache_metrics_summary.json", {"requests": prefix_rows}
    )
    write_json(artifact_dir / "mtp_metrics_summary.json", {"requests": mtp_rows})
    write_json(artifact_dir / "queue_health_summary.json", {"requests": queue_rows})
    write_json(
        artifact_dir / "transfer_availability_summary.json",
        {"requests": transfer_rows},
    )
    write_json(
        artifact_dir / "replay_determinism.json",
        {"deterministic": True, "compared_file_count": 5, "mismatches": []},
    )
    (artifact_dir / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (bundle_dir / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "emitted_event_count": 24,
                "placement_decision_count": 6,
                "runtime_label": "vllm_ascend",
                "server_validated": False,
                "state_object_count": 6,
                "trace_validation_errors": 0,
            }
        ),
        encoding="utf-8",
    )
    write_json(bundle_dir / "validation_report.json", {"trace_validation_errors": 0})
    (bundle_dir / "state_events.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in events), encoding="utf-8"
    )
    (bundle_dir / "state_objects.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in objects), encoding="utf-8"
    )
    (bundle_dir / "placement_decisions.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in decisions), encoding="utf-8"
    )

    grading = finalize_matrix_artifacts(artifact_dir)

    assert grading["grade"] == (
        "candidate_green_p8_1_official_mtp_observe_only_matrix"
    )
    assert grading["successful_request_count"] == 6
    assert grading["shared_prefix_exact"] is True
    assert grading["isolated_zero_hit"] is True
    assert grading["per_request_mtp_ok"] is True
    assert grading["health_queue_ok"] is True
    assert grading["replay_deterministic"] is True
    assert grading["join_coverage_complete"] is True
    assert grading["request_stage_event_count"] == 18
    assert grading["state_object_count"] == 6
    assert grading["placement_decision_count"] == 6
    assert grading["cleanup"] == "clean"
    join = json.loads((artifact_dir / "join_coverage.json").read_text())
    assert join["request_runtime_object_join_complete"] is True
    assert join["device_join_status"] == "unavailable_with_explicit_reason"
    assert "generated_text" not in (artifact_dir / "result_summary.md").read_text()


def test_matrix_body_preparer_freezes_shared_and_isolated_prefix_relationships(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source_payload.json"
    source.write_text(
        json.dumps(
            {
                "model": "deepseek-v4-flash-w8a8-mtp",
                "prompt": list(range(4096)),
                "max_tokens": 64,
                "min_tokens": 64,
                "ignore_eos": True,
                "temperature": 0.0,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "prepared"

    manifest = prepare_matrix_bodies(
        source,
        output,
        "deepseek-v4-flash-w8a8-mtp",
    )

    assert manifest["request_count"] == 6
    assert manifest["all_request_body_sha256_unique"] is True
    assert manifest["shared_prefix"] == {
        "prime_slot": "medium_shared_prime",
        "follower_slot": "medium_shared_follower",
        "token_lcp": 58880,
        "expected_prefix_hit_tokens": 49152,
    }
    assert manifest["all_other_pairwise_prefixes_less_than_tokens"] == 128
    assert manifest["all_other_pairwise_prefixes_valid"] is True
    records = manifest["records"]
    assert [record["input_tokens"] for record in records] == [
        4096,
        65536,
        65536,
        131072,
        4096,
        131072,
    ]
    bodies = {}
    for record in records:
        path = output / record["body_relative_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == (
            record["request_body_sha256"]
        )
        body = json.loads(path.read_text())
        assert len(body["prompt"]) == record["input_tokens"]
        assert body["return_token_ids"] is True
        assert body["stream"] is True
        bodies[record["slot_id"]] = body["prompt"]
    prime = bodies["medium_shared_prime"]
    follower = bodies["medium_shared_follower"]
    lcp = next(index for index, pair in enumerate(zip(prime, follower)) if pair[0] != pair[1])
    assert lcp == 58880
    assert manifest["generated_text_retained"] is False
    assert manifest["generated_token_ids_retained"] is False


def test_matrix_runner_freezes_one_lifecycle_six_requests_and_two_replays() -> None:
    syntax = subprocess.run(
        ["bash", "-n", str(RUNNER_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr

    audit = subprocess.run(
        ["bash", str(RUNNER_PATH), "/tmp/p8_1_matrix_audit_only"],
        check=False,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "P8_1_AUDIT_ONLY": "1",
            "REPO_ROOT": "/data/node0_disk1/liguowei/AK-Infer-Lab",
        },
    )
    assert audit.returncode == 0, audit.stderr.decode()
    assert hashlib.sha256(audit.stdout).hexdigest() == (
        "370f8d2570116da93eca4ec773c98093d8b8e385c27cc32e16785fb2d1824b19"
    )
    command = audit.stdout.decode()
    for token in (
        "--max-model-len 135168",
        "--max-num-batched-tokens 4096",
        "--max-num-seqs 1",
        "--tensor-parallel-size 8",
        "--enable-expert-parallel",
        "--quantization ascend",
        "--block-size 128",
        "--enable-chunked-prefill",
        "--enable-prefix-caching",
        "num_speculative_tokens",
        "FULL_DECODE_ONLY",
    ):
        assert token in command

    script = RUNNER_PATH.read_text(encoding="utf-8")
    assert "cp -a --no-preserve=ownership" in script
    assert "prepare_deepseek_p8_1_observe_matrix.py" in script
    assert script.count("collect-vllm-ascend-observations") == 1
    assert "--expected-prompt-tokens" in script
    assert "--trace-id trace_p8_matrix_0001" in script
    assert "--session-id session_p8_matrix_0001" in script
    assert script.count("build-vllm-ascend-observe-bundle") == 2
    assert "request_matrix_summary.json" in script
    assert "prefix_cache_metrics_summary.json" in script
    assert "mtp_metrics_summary.json" in script
    assert "queue_health_summary.json" in script
    assert "transfer_availability_summary.json" in script
    assert "replay_determinism.json" in script
    assert "finalize_deepseek_p8_1_observe_only_matrix.py" in script
    assert "msprof" not in script
    assert "upload-api" not in script
    assert "sendmail" not in script


def test_matrix_workload_hashes_every_executable_contract_artifact() -> None:
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))
    frozen = workload["runner"]["frozen_artifacts"]
    artifacts = {
        "official_matrix_contract_sha256": BASELINE_PATH,
        "preparer_sha256": (
            REPO_ROOT
            / "tools/inference_contracts/prepare_deepseek_p8_1_observe_matrix.py"
        ),
        "runner_sha256": RUNNER_PATH,
        "finalizer_sha256": FINALIZER_PATH,
        "observer_sha256": REPO_ROOT / "tools/ak_state_runtime/vllm_ascend_observer.py",
        "cli_sha256": REPO_ROOT / "tools/ak_state_runtime/cli.py",
        "adapter_sha256": (
            REPO_ROOT / "tools/ak_state_runtime/adapters/vllm_ascend.py"
        ),
    }
    for key, path in artifacts.items():
        assert frozen[key] == hashlib.sha256(path.read_bytes()).hexdigest(), path


def test_current_handoff_authorizes_only_k1a_r4_offline_closeout() -> None:
    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(
        encoding="utf-8"
    )

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert (
            "task_id: p8_2_k1a_r4_r1_store_only_source_semantics_replay_2026_0721"
        in handoff
    )
    assert (
        "execution_mode: authorized_read_only_r4_parent_validation_and_same_evidence_offline_source_semantics_replay"
        in handoff
    )
    assert "npu_execution_authorized: false" in handoff
    assert "next_task_authorized: false" in handoff
    assert "result_transfer_authorized: true" in handoff
    assert "runtime_or_dependency_mutation_authorized: false" in handoff
    assert "16384" in handoff
    assert "model_request_count_exact: 0" in handoff
    assert "merge --ff-only origin/main" in handoff
    assert "keep_alive_stop_authorized: false" in handoff
    assert "formal_model_lifecycle_count_exact: 0" in handoff
    assert "不得进入 K2" in handoff
    assert "email" in handoff
    assert "upload-api" in handoff
    assert "git push origin" not in handoff
    assert "git commit -m" not in handoff
