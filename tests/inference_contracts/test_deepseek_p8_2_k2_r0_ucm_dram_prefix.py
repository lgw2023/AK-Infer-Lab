from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.inference_contracts.run_deepseek_p8_2_k2_r0_ucm_dram_prefix import (
    TASK_ID,
    finalize,
    package,
)


ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    / "p8_2_k2_r0_ucm_dram_external_prefix_path.yaml"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    / "p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"
READINESS = (
    ROOT / "benchmarks/deepseek_v4_flash/p5_readiness_card.yaml"
)


def _request(role: str, delta: dict[str, float]) -> dict:
    return {
        "request_role": role,
        "status": "success",
        "context_tokens": 4096 if role == "warmup" else 32768,
        "output_tokens": 64,
        "http_status": 200,
        "prompt_tokens": 4096 if role == "warmup" else 32768,
        "generated_token_count": 64,
        "ttft_ms": 100.0,
        "tpot_ms": 10.0,
        "itl_p95_ms": 12.0,
        "e2el_ms": 730.0,
        "counter_delta": delta,
    }


def test_contract_targets_real_ucm_path_without_performance_precondition() -> None:
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    readiness = yaml.safe_load(READINESS.read_text(encoding="utf-8"))
    assert workload["task_id"] == TASK_ID
    assert workload["ucm_store"]["pipeline"] == "Cache|Posix"
    assert workload["ucm_store"]["use_layerwise"] is True
    assert workload["implementation_acceptance"][
        "latency_sign_is_not_a_path_gate"
    ] is True
    assert audit["developer_decision"][
        "performance_benefit_is_not_an_implementation_prerequisite"
    ] is True
    assert audit["pinned_ucm_source"]["commit"] == (
        "01cbf9b71892c88319862fa57f195b0bef93fa6f"
    )
    assert readiness["artifacts"]["current_server_handoff_task"] == TASK_ID
    assert readiness["artifacts"]["next_workload"].endswith(
        "p8_2_k2_r0_ucm_dram_external_prefix_path.yaml"
    )
    assert readiness["acceptance"]["p8_2_k1a_r5_f1_r17_grade"] == (
        "green_p8_2_k1a_r5_f1_r17_restore_h2d_mechanism_closed"
    )
    assert readiness["acceptance"]["p8_2_k2_r0_execution_authorized"] is True


def test_finalize_accepts_dram_hit_and_h2d_load_independent_of_latency(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "result"
    runtime = artifact / "runtime"
    runtime.mkdir(parents=True)
    rows = [
        _request("warmup", {}),
        _request(
            "prime",
            {
                "ucm:save_bytes_total": 4096,
                "ucm:cache_dump_bytes_total": 4096,
            },
        ),
        _request(
            "follower",
            {
                "ucm:ucm_hit_tokens_total": 32768,
                "ucm:gpu_hbm_hit_tokens_total": 0,
                "ucm:cache_lookup_hit_blocks_total": 256,
                "ucm:load_bytes_total": 4096,
                "ucm:cache_load_bytes_total": 4096,
                "ucm:posix_s2h_bytes_total": 0,
            },
        ),
    ]
    (runtime / "request_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    (runtime / "vllm_server.log").write_text(
        "request_id: bounded, hit hbm: 0, hit external: 256\n",
        encoding="utf-8",
    )
    (artifact / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (artifact / "dependency_and_environment_summary.json").write_text(
        "{}\n", encoding="utf-8"
    )
    (artifact / "resource_recovery_summary.json").write_text(
        json.dumps(
            {
                "stopped_card_ids": list(range(8)),
                "restored_card_ids": list(range(8)),
                "keep_alive_restored_exact": True,
                "port_7000_listener_count": 0,
                "vllm_residual_process_count": 0,
                "tracked_worktree_clean": True,
            }
        ),
        encoding="utf-8",
    )
    grade = finalize(artifact)
    assert grade == "implemented_p8_2_k2_r0_ucm_dram_external_prefix_path"
    summary = json.loads(
        (artifact / "ucm_path_summary.json").read_text(encoding="utf-8")
    )
    assert summary["mechanism_implemented"] is True
    assert summary["posix_read_absent_on_follower"] is True
    assert summary["performance_benefit_required_for_mechanism_acceptance"] is False
    package(artifact)
    manifest = json.loads(
        (artifact / "candidate_manifest.server_local.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["payload_file_count"] == 9
    assert manifest["transfer_file_count"] == 10
    assert manifest["manifest_bytes"] == (
        artifact / "candidate_manifest.server_local.json"
    ).stat().st_size
    assert manifest["transfer_total_bytes"] <= 71680


def test_handoff_is_current_only_and_operationally_complete() -> None:
    text = HANDOFF.read_text(encoding="utf-8")
    assert text.count("## 当前唯一服务器动作：") == 1
    assert TASK_ID in text
    assert "01cbf9b71892c88319862fa57f195b0bef93fa6f" in text
    assert "run_deepseek_p8_2_k2_r0_server_task.sh" in text
    assert "npu_stop.sh 0 1 2 3 4 5 6 7" in text
    assert "npu_keep_alive.sh 0 1 2 3 4 5 6 7" in text
    assert "性能收益不是本轮实现通过的前置条件" in text
    assert "transfer_method_selected: false" in text
