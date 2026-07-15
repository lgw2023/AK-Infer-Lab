import hashlib
import json
from pathlib import Path

import yaml

from tools.inference_contracts.p6_3b_r1_hybrid_kv_runtime_patch import (
    EXPECTED_SOURCE_SHA256,
    cache_target_tokens,
    eagle_reachable_block_mask,
)
from tools.inference_contracts.run_deepseek_p6_3b_prefix_cache_ab import (
    build_run_plan,
    prepare_artifacts,
)
from tools.inference_contracts.run_deepseek_p6_3b_r1_hybrid_kv_repair import (
    build_r1_plan,
    finalize_artifacts,
    grade_r1_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_hybrid_kv_patch_caches_the_eagle_lookahead_block_at_lcm_boundaries():
    mask = eagle_reachable_block_mask(
        start_block=0,
        end_block=129,
        alignment_tokens=4096,
        block_size=32,
        sliding_window=128,
        use_eagle=True,
    )

    assert mask is not None
    assert [index for index, cached in enumerate(mask) if cached] == [
        124,
        125,
        126,
        127,
        128,
    ]
    assert cache_target_tokens(
        num_computed_tokens=20000,
        alignment_tokens=16384,
        block_size=128,
        use_eagle=True,
    ) == 16512
    assert cache_target_tokens(
        num_computed_tokens=20000,
        alignment_tokens=16384,
        block_size=128,
        use_eagle=False,
    ) == 16384
    assert EXPECTED_SOURCE_SHA256 == {
        "vllm.v1.core.single_type_kv_cache_manager": (
            "d57ad1c8e3d32db4a9d929ee201ab169305ef703b5bda9eb933d0f2f2a2299a1"
        ),
        "vllm.v1.core.kv_cache_coordinator": (
            "a5f0683483508fcfd0b2e3477940825bae5953eec715a4f704becec805484b89"
        ),
    }


def test_ascend_overlay_propagates_eagle_to_every_same_spec_manager():
    patch_path = (
        REPO_ROOT
        / "benchmarks/deepseek_v4_flash/patches/"
        "vllm_ascend_v0221rc1_hybrid_kv_eagle_manager_overlay.patch"
    )
    patch = patch_path.read_text(encoding="utf-8")

    assert "for idx in self.eagle_attn_group_indices:" in patch
    assert "for gid in self.attention_groups[idx][1]:" in patch
    assert "self.single_type_managers[gid].use_eagle = True" in patch
    assert "site-packages" not in patch


def test_existing_body_builder_accepts_the_bounded_r1_plan(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"prompt": list(range(4096))}),
        encoding="utf-8",
    )
    r1_plan = [
        row
        for row in build_run_plan()
        if row["context_tokens"] in (32768, 65536, 131072)
        and row["target_shared_prefix_ratio_pct"] == 90
    ]

    manifest = prepare_artifacts(
        source,
        tmp_path / "run",
        "deepseek-test",
        plan=r1_plan,
    )

    assert manifest["request_count"] == 12
    assert manifest["group_count"] == 3
    assert len(manifest["records"]) == 12


def test_r1_grading_requires_real_hits_and_runtime_hybrid_evidence():
    rows = []
    for item in build_r1_plan():
        measured = item["request_role"] == "measured"
        rows.append(
            {
                **item,
                "mode": "prefix_cache_on",
                "status": "success",
                "prefix_queries_delta": 4096.0,
                "prefix_hits_delta": 2048.0 if measured else 0.0,
                "queue_metrics_ok": True,
                "counter_continuity_ok": True,
                "spec_activity_ok": True,
                "accepted_token_delta": 32.0,
            }
        )
    diagnostics = [
        {
            "event": "runtime_patch_installed",
            "retention_interval": None,
            "source_evidence": {
                name: {"match": True} for name in EXPECTED_SOURCE_SHA256
            },
        },
        {
            "event": "coordinator_snapshot",
            "lcm_block_size": 16384,
            "eagle_group_ids": [2],
            "attention_groups": [
                {"group_ids": [0]},
                {"group_ids": [1, 2]},
            ],
            "managers": [
                {"group_id": 0, "use_eagle": False},
                {"group_id": 1, "use_eagle": True},
                {"group_id": 2, "use_eagle": True},
            ],
            "prefix_cache_retention_interval": None,
        },
        {"event": "eagle_lookahead_cache_target"},
    ]

    green = grade_r1_evidence(rows, diagnostics=diagnostics, cleanup="clean")
    assert green["server_grade"] == "candidate_green_p6_3b_r1_hybrid_kv_repair"
    assert green["prime_success_count"] == 3
    assert green["measured_success_count"] == 9
    assert green["positive_hit_measured_count"] == 9
    assert green["hybrid_diagnostic_ok"] is True

    for row in rows:
        if row["request_role"] == "measured":
            row["prefix_hits_delta"] = 0.0
    zero_hit = grade_r1_evidence(rows, diagnostics=diagnostics, cleanup="clean")
    assert zero_hit["server_grade"] == "red_p6_3b_r1_hybrid_kv_zero_hit_persists"


def test_r1_finalizer_writes_only_bounded_structured_repair_evidence(tmp_path):
    mode_dir = tmp_path / "modes/prefix_cache_on"
    runtime_dir = mode_dir / "runtime"
    runtime_dir.mkdir(parents=True)
    rows = []
    for item in build_r1_plan():
        measured = item["request_role"] == "measured"
        rows.append(
            {
                **item,
                "mode": "prefix_cache_on",
                "status": "success",
                "prefix_queries_delta": 4096.0,
                "prefix_hits_delta": 2048.0 if measured else 0.0,
                "queue_metrics_ok": True,
                "counter_continuity_ok": True,
                "spec_activity_ok": True,
                "accepted_token_delta": 32.0,
                "ttft_ms": 1.0,
            }
        )
    diagnostics = [
        {
            "event": "runtime_patch_installed",
            "retention_interval": None,
            "source_evidence": {
                name: {"match": True} for name in EXPECTED_SOURCE_SHA256
            },
        },
        {
            "event": "coordinator_snapshot",
            "lcm_block_size": 16384,
            "eagle_group_ids": [1],
            "attention_groups": [{"group_ids": [0]}, {"group_ids": [1]}],
            "managers": [
                {"group_id": 0, "manager_type": "Full", "use_eagle": False},
                {"group_id": 1, "manager_type": "Compressed", "use_eagle": True},
            ],
            "prefix_cache_retention_interval": None,
        },
        {"event": "eagle_lookahead_cache_target"},
    ]
    (mode_dir / "raw_request_results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    (runtime_dir / "hybrid_kv_runtime_diagnostic.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in diagnostics),
        encoding="utf-8",
    )
    (mode_dir / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")

    grading = finalize_artifacts(tmp_path)

    assert grading["server_grade"] == "candidate_green_p6_3b_r1_hybrid_kv_repair"
    for name in (
        "result_summary.md",
        "group_summary.tsv",
        "grading_inputs.json",
        "hybrid_kv_diagnostic_summary.json",
        "cleanup_status.txt",
        "first_failure_excerpt.txt",
    ):
        content = (tmp_path / name).read_text(encoding="utf-8")
        assert "generated_text" not in content
        assert "token_ids" not in content


def test_r1_workload_hashes_and_mode_runner_freeze_the_task_local_repair():
    workload = yaml.safe_load(
        (
            REPO_ROOT
            / "benchmarks/deepseek_v4_flash/workloads/p6_3b_r1_hybrid_kv_repair.yaml"
        ).read_text(encoding="utf-8")
    )
    repair = workload["hybrid_kv_repair"]
    runtime_patch = REPO_ROOT / repair["vllm_runtime_patch_path"]
    ascend_patch = REPO_ROOT / repair["vllm_ascend_overlay_patch_path"]

    assert hashlib.sha256(runtime_patch.read_bytes()).hexdigest() == repair[
        "runtime_patch_sha256"
    ]
    assert hashlib.sha256(ascend_patch.read_bytes()).hexdigest() == repair[
        "vllm_ascend_overlay_patch_sha256"
    ]
    mode_runner = (
        REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3b_r1_mode.sh"
    ).read_text(encoding="utf-8")
    assert "P6_3B_R1_ENABLE_HYBRID_KV_PATCH=1" in mode_runner
    assert "unset VLLM_PREFIX_CACHE_RETENTION_INTERVAL" in mode_runner
    assert "--enable-prefix-caching" in mode_runner
    assert "--speculative-config" in mode_runner
    assert "--enable-chunked-prefill" in mode_runner
    assert "--max-num-seqs 1" in mode_runner
    assert "--enforce-eager" not in mode_runner
    assert "msprof" not in mode_runner
    assert "npu-smi" not in mode_runner
