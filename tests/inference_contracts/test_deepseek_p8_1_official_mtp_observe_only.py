import hashlib
import json
from pathlib import Path
import subprocess

import yaml

from tools.inference_contracts.finalize_deepseek_p8_1_observe_only import (
    finalize_artifacts,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKLOAD_PATH = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_1_vllm_ascend_official_mtp_observe_only_adapter_smoke.yaml"
)
RUNNER_PATH = REPO_ROOT / "tools/inference_contracts/run_deepseek_p8_1_observe_only.sh"


def test_p8_1_workload_uses_the_official_mtp_cell_without_mutation() -> None:
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))

    assert workload["stage_contract"] == {
        "stage": "P8.1",
        "mode": "vllm_ascend_observe_only_tracer_bullet",
        "claim_boundary": "official_mtp_4096_64_c1_observe_only_trace",
        "performance_comparison_authorized": False,
        "p8_2_execution_authorized": False,
    }
    assert workload["official_baseline"]["contract"].endswith(
        "p8_official_mtp_baseline_contract.yaml"
    )
    assert workload["official_baseline"]["contract_status"] == "frozen_official"
    assert workload["official_baseline"]["successful_cell"] == (
        "p6_1_short_prefill_4096_64_c1"
    )
    assert workload["historical_degraded_provenance"]["preserved"] is True

    runtime = workload["runtime_fixed"]
    assert runtime["tensor_parallel_size"] == 8
    assert runtime["enable_expert_parallel"] is True
    assert runtime["quantization"] == "ascend"
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

    assert workload["request_plan"]["request_count"] == 1
    assert workload["request_plan"]["input_tokens"] == 4096
    assert workload["request_plan"]["output_tokens"] == 64
    assert workload["request_plan"]["streaming_required"] is True
    assert workload["observation_contract"]["adapter_mode"] == "observe_only"
    assert workload["observation_contract"]["runtime_imports_allowed"] is False
    assert workload["observation_contract"]["payload_fields_allowed"] is False
    assert workload["observation_contract"]["placement_mutation_allowed"] is False
    assert workload["acceptance"]["trace_validation_errors"] == 0
    assert workload["acceptance"]["every_decision_executed"] is False
    assert workload["stop_policy"]["no_profiler"] is True
    assert workload["stop_policy"]["no_offload"] is True
    assert workload["stop_policy"]["no_second_request"] is True
    assert workload["execution_state"]["npu_execution_authorized"] is True
    assert workload["execution_state"]["next_task_authorized"] is True

    frozen = workload["runner"]["frozen_artifacts"]
    artifacts = {
        "official_baseline_contract_sha256": (
            REPO_ROOT
            / "benchmarks/deepseek_v4_flash/p8/"
            "p8_official_mtp_baseline_contract.yaml"
        ),
        "runner_sha256": RUNNER_PATH,
        "finalizer_sha256": (
            REPO_ROOT
            / "tools/inference_contracts/finalize_deepseek_p8_1_observe_only.py"
        ),
        "adapter_sha256": (
            REPO_ROOT / "tools/ak_state_runtime/adapters/vllm_ascend.py"
        ),
    }
    for key, path in artifacts.items():
        assert frozen[key] == hashlib.sha256(path.read_bytes()).hexdigest(), path


def test_p8_1_finalizer_accepts_one_observe_only_mtp_trace(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "p8_1"
    bundle_dir = artifact_dir / "observe_only_bundle"
    bundle_dir.mkdir(parents=True)

    def write_json(path: Path, record: dict) -> None:
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    write_json(
        artifact_dir / "request_result.json",
        {
            "status": "success",
            "http_status": 200,
            "prompt_tokens": 4096,
            "generated_token_count": 64,
            "streamed_token_count": 64,
            "finish_reason": "length",
            "generated_text_retained": False,
            "token_ids_retained": False,
        },
    )
    write_json(
        artifact_dir / "prefix_cache_metrics.json",
        {"delta": {"queries": 4096.0, "hits": 0.0}},
    )
    write_json(
        artifact_dir / "mtp_metrics.json",
        {
            "delta": {
                "num_drafts": 64.0,
                "num_draft_tokens": 64.0,
                "num_accepted_tokens": 32.0,
            },
            "counter_continuity": True,
        },
    )
    write_json(
        artifact_dir / "transfer_availability.json",
        {"status": "unavailable", "event_emitted": False, "reason": "no_native_event"},
    )
    (artifact_dir / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (bundle_dir / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "emitted_event_count": 4,
                "placement_decision_count": 1,
                "runtime_label": "vllm_ascend",
                "server_validated": False,
                "state_object_count": 1,
                "trace_validation_errors": 0,
            }
        ),
        encoding="utf-8",
    )
    write_json(bundle_dir / "validation_report.json", {"trace_validation_errors": 0})
    (bundle_dir / "state_events.jsonl").write_text(
        "".join(
            json.dumps({"event_type": event_type}) + "\n"
            for event_type in (
                "request_stage",
                "request_stage",
                "request_stage",
                "state_lifecycle",
            )
        ),
        encoding="utf-8",
    )
    write_json(bundle_dir / "state_objects.jsonl", {"payload_ref": None})
    write_json(
        bundle_dir / "placement_decisions.jsonl",
        {
            "execution_mode": "observe_only",
            "action": "no_op",
            "executed": False,
            "execution_result": "skipped",
        },
    )

    grading = finalize_artifacts(artifact_dir)

    assert grading["grade"] == (
        "candidate_green_p8_1_official_mtp_observe_only_trace"
    )
    assert grading["request_exact"] is True
    assert grading["mtp_activity_ok"] is True
    assert grading["trace_validation_errors"] == 0
    assert grading["request_stage_event_count"] == 3
    assert grading["state_object_count"] == 1
    assert grading["placement_decision_count"] == 1
    assert grading["observe_only_decisions_ok"] is True
    assert grading["payload_refs_absent"] is True
    assert grading["cleanup"] == "clean"
    assert "generated_text" not in (artifact_dir / "result_summary.md").read_text()
    trace_summary = json.loads((artifact_dir / "trace_summary.json").read_text())
    assert trace_summary["transfer_status"] == "unavailable"
    assert trace_summary["synthetic_transfer_emitted"] is False


def test_p8_1_runner_freezes_the_official_command_and_one_request_flow() -> None:
    syntax = subprocess.run(
        ["bash", "-n", str(RUNNER_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr

    audit = subprocess.run(
        ["bash", str(RUNNER_PATH), "/tmp/p8_1_audit_only"],
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
        "--speculative-config",
        "num_speculative_tokens",
        "FULL_DECODE_ONLY",
    ):
        assert token in command

    script = RUNNER_PATH.read_text(encoding="utf-8")
    assert "cp -a --no-preserve=ownership" in script
    assert script.count("collect-vllm-ascend-observations") == 1
    assert script.count("build-vllm-ascend-observe-bundle") == 1
    assert "finalize_deepseek_p8_1_observe_only.py" in script
    assert "mtp_metrics.json" in script
    assert "cleanup_status.txt" in script
    assert "msprof" not in script
    assert "upload-api" not in script
    assert "sendmail" not in script


def test_single_request_tracer_is_preserved_but_superseded_before_execution() -> None:
    handoff = (REPO_ROOT / "通信模块/docs/developer-to-server.md").read_text(
        encoding="utf-8"
    )
    workload = yaml.safe_load(WORKLOAD_PATH.read_text(encoding="utf-8"))

    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert workload["task_id"] == (
        "p8_1_deepseek_v4_flash_official_mtp_observe_only_trace_2026_0716"
    )
    assert WORKLOAD_PATH.is_file()
    assert RUNNER_PATH.is_file()
    assert (
        REPO_ROOT
        / "benchmarks/deepseek_v4_flash/p8/p8_official_mtp_baseline_contract.yaml"
    ).is_file()
    assert (
        "task_id: p8_1_deepseek_v4_flash_official_mtp_observe_only_trace_2026_0716"
        not in handoff
    )
    assert (
            "task_id: p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723"
        in handoff
    )
