import hashlib
from pathlib import Path

import yaml


P6_DIR = Path("benchmarks/deepseek_v4_flash/p6")


def test_p6_baseline_contract_materializes_the_accepted_reference_chain() -> None:
    contract = yaml.safe_load(
        (P6_DIR / "p6_baseline_contract.yaml").read_text(encoding="utf-8")
    )

    assert contract["schema_name"] == "ak_p6_baseline_contract"
    assert contract["schema_version"] == "1.0.0"
    assert contract["stage_status"] == "evidence_chain_complete"
    assert contract["runtime_pin"] == {
        "vllm": "0.22.1+empty",
        "vllm_commit": "0decac0d96c42b49572498019f0a0e3600f50398",
        "vllm_ascend": "0.22.1rc1",
        "vllm_ascend_commit": "5f6faa0cb8830f667266f3b8121cd1383606f2a1",
    }
    assert contract["official_reference"] == {
        "model_object_id": "deepseek_v4_flash_w8a8_mtp_modelscope",
        "quantization": "ascend",
        "tensor_parallel_size": 8,
        "expert_parallel": True,
        "mtp": {"method": "mtp", "num_speculative_tokens": 1},
        "cudagraph_mode": "FULL_DECODE_ONLY",
        "max_model_len": 135168,
        "max_num_batched_tokens": 4096,
        "max_num_seqs": 1,
        "enable_chunked_prefill": True,
        "enable_prefix_caching": True,
    }
    assert contract["accepted_gates"] == {
        "official_context": "green_mtp_official_context_ladder",
        "unprofiled_baseline": "green_mtp_unprofiled_baseline",
        "profiled_evidence": "green_mtp_profiled_evidence",
        "mtp_matched_ab": "green_p6_3a_mtp_matched_ab",
        "prefix_cache_matched_ab": (
            "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab"
        ),
        "chunked_prefill_feasibility": (
            "blocked_p6_3c_not_strict_single_variable"
        ),
    }
    assert contract["claim_boundary"]["p6_3c_executable_workload_created"] is False
    assert contract["claim_boundary"]["optimization_gain_claim_allowed"] is False


def test_p6_reports_separate_performance_profiled_and_ab_claims() -> None:
    unprofiled = (P6_DIR / "p6_unprofiled_baseline_report.md").read_text(
        encoding="utf-8"
    )
    profiled = (P6_DIR / "p6_profiled_evidence_report.md").read_text(
        encoding="utf-8"
    )
    matched_ab = (P6_DIR / "p6_single_variable_ab_report.md").read_text(
        encoding="utf-8"
    )

    assert "green_mtp_unprofiled_baseline" in unprofiled
    assert "18/18 cells" in unprofiled
    assert "24/24 measured batches" in unprofiled
    assert "90/90 measured requests" in unprofiled
    assert "P6 用户侧 streaming 性能 reference" in unprofiled

    assert "green_mtp_profiled_evidence" in profiled
    assert "3/3 representative cells" in profiled
    assert "6 phase-memory rows" in profiled
    assert "profiled latency 不是用户性能 baseline" in profiled
    assert "不形成硬件瓶颈或优化优先级归因" in profiled

    assert "green_p6_3a_mtp_matched_ab" in matched_ab
    assert "108/108 measured requests" in matched_ab
    assert "green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab" in matched_ab
    assert "9/9 primary positive hit" in matched_ab
    assert "blocked_p6_3c_not_strict_single_variable" in matched_ab
    assert "不构成可执行 matched A/B" in matched_ab
    assert "不声称普遍优化收益" in matched_ab


def test_p6_artifact_manifest_is_complete_and_hash_verifiable() -> None:
    manifest = yaml.safe_load(
        (P6_DIR / "p6_artifact_manifest.yaml").read_text(encoding="utf-8")
    )

    assert manifest["schema_name"] == "ak_p6_artifact_manifest"
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["manifest_status"] == "complete_repository_closeout"
    assert set(manifest["deliverables"]) == {
        "baseline_contract",
        "unprofiled_baseline_report",
        "profiled_evidence_report",
        "single_variable_ab_report",
    }
    assert set(manifest["accepted_evidence"]) == {
        "official_context",
        "unprofiled_baseline",
        "profiled_evidence",
        "mtp_matched_ab",
        "prefix_cache_matched_ab",
        "chunked_prefill_feasibility",
    }

    for group in ("deliverables", "accepted_evidence"):
        for artifact in manifest[group].values():
            path = Path(artifact["path"])
            content = path.read_bytes()
            assert artifact["bytes"] == len(content), path
            assert artifact["sha256"] == hashlib.sha256(content).hexdigest(), path

    assert manifest["claim_boundary"] == {
        "repository_evidence_only": True,
        "raw_server_artifacts_included": False,
        "generated_content_or_token_ids_included": False,
        "new_npu_execution": False,
    }
