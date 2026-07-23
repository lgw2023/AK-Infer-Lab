from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    _observe_target_cache_stamp,
    accumulate_target_cache_stamp_lineage,
    observer_self_test_contract,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r10_cache_stamp_lineage_2026_0723"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r10_cache_stamp_lineage_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r10_cache_stamp_lineage.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r10_cache_stamp_lineage.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r10_server_task.sh"
)


class _Block:
    def __init__(
        self,
        block_hash: object | None,
        *,
        is_null: bool = False,
    ) -> None:
        self.block_hash = block_hash
        self.is_null = is_null


class _Mapping:
    def __init__(self, keys: set[object]) -> None:
        self.keys = keys

    def get_one_block(self, key: object) -> object | None:
        return object() if key in self.keys else None


class _Pool:
    def __init__(self, keys: set[object]) -> None:
        self.cached_block_hash_to_block = _Mapping(keys)
        self.blocks: dict[int, _Block] = {}


class _Coordinator:
    @staticmethod
    def _get_effective_block_size(spec: object) -> int:
        return int(spec.block_size) * max(
            1, int(getattr(spec, "compress_ratio", 1) or 1)
        )


def test_sparse_runtime_mask_defines_required_target_keys() -> None:
    blocks = [
        _Block(None),
        _Block(None),
        _Block(None),
        _Block("g2-3"),
        _Block(None),
        _Block(None),
        _Block(None),
        _Block("g2-7"),
    ]
    state: dict[str, object] = {}

    row = accumulate_target_cache_stamp_lineage(
        state,
        blocks=blocks,
        num_cached_blocks=0,
        num_full_blocks=8,
        block_size_tokens=128,
        block_mask=[False, False, False, True] * 2,
        restore_match_tokens=1024,
    )

    assert row["dense_physical_position_count"] == 8
    assert row["scanned_position_count"] == 8
    assert row["cacheable_position_count"] == 2
    assert row["masked_position_count"] == 6
    assert row["required_block_count"] == 2
    assert row["captured_block_count"] == 2
    assert row["group_applicable"] is True
    assert row["logical_coverage_exact"] is True
    assert set(state["hashes_by_position"].values()) == {"g2-3", "g2-7"}


def test_zero_cacheable_group_is_not_applicable_only_after_full_scan() -> None:
    blocks = [_Block(None) for _ in range(8)]
    state: dict[str, object] = {}

    partial = accumulate_target_cache_stamp_lineage(
        state,
        blocks=blocks,
        num_cached_blocks=0,
        num_full_blocks=4,
        block_size_tokens=128,
        block_mask=[False] * 4,
        restore_match_tokens=1024,
    )
    complete = accumulate_target_cache_stamp_lineage(
        state,
        blocks=blocks,
        num_cached_blocks=4,
        num_full_blocks=8,
        block_size_tokens=128,
        block_mask=[False] * 4,
        restore_match_tokens=1024,
    )

    assert partial["group_applicable"] is True
    assert partial["selected_geometry_exact"] is False
    assert complete["selected_geometry_exact"] is True
    assert complete["group_applicable"] is False
    assert complete["required_block_count"] == 0
    assert complete["logical_coverage_exact"] is True


def test_progressive_cache_stamps_build_exact_cross_group_lineage() -> None:
    fa_blocks = [_Block(f"fa-{index}") for index in range(32)]
    swa_blocks = [
        _Block(f"swa-{index}" if index in {31, 63, 95, 127} else None)
        for index in range(128)
    ]
    all_keys = {
        *(block.block_hash for block in fa_blocks),
        *(
            block.block_hash
            for block in swa_blocks
            if block.block_hash is not None
        ),
    }
    groups = (
        type(
            "Group",
            (),
            {
                "kv_cache_spec": type(
                    "AscendMLAAttentionSpec",
                    (),
                    {"block_size": 128, "compress_ratio": 4},
                )()
            },
        )(),
        type(
            "Group",
            (),
            {
                "kv_cache_spec": type(
                    "AscendSlidingWindowMLASpec",
                    (),
                    {"block_size": 128, "compress_ratio": 1},
                )()
            },
        )(),
    )
    scheduler = type("Scheduler", (), {})()
    scheduler.cpu_kv_cache_config = type(
        "CPUConfig", (), {"kv_cache_groups": groups}
    )()
    scheduler.cpu_coordinator = _Coordinator()
    scheduler.cpu_block_pool = _Pool(set())
    scheduler._gpu_block_pool = _Pool(all_keys)
    scheduler._store_event_to_blocks = {}
    scheduler.fa_gidx = 0
    scheduler.cp_world_size = 1
    request = type(
        "Request",
        (),
        {"block_hashes": tuple(f"h-{index}" for index in range(128))},
    )()

    partial = _observe_target_cache_stamp(
        scheduler,
        request,
        group_index=0,
        blocks=fa_blocks,
        num_cached_blocks=0,
        num_full_blocks=32,
        block_size_tokens=512,
        block_mask=None,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
    )
    complete = _observe_target_cache_stamp(
        scheduler,
        request,
        group_index=1,
        blocks=swa_blocks,
        num_cached_blocks=0,
        num_full_blocks=128,
        block_size_tokens=128,
        block_mask=[index % 32 == 31 for index in range(128)],
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
    )

    assert partial["target_store_lineage_capture_exact"] is False
    assert complete["target_store_lineage_capture_exact"] is True
    assert complete["target_fa_key_count"] == 32
    assert complete["target_store_key_count"] == 36
    assert complete["target_logical_block_count"] == 128
    assert complete["target_logical_coverage_exact"] is True
    rows = complete["restore_group_rows"]
    assert rows[1]["dense_physical_position_count"] == 128
    assert rows[1]["cacheable_position_count"] == 4
    assert rows[1]["captured_block_count"] == 4
    assert rows[1]["capture_exact"] is True


def test_observer_declares_runtime_cache_stamp_boundary() -> None:
    contract = observer_self_test_contract()

    assert "cache_full_blocks" in contract["wrapped_block_pool_methods"]
    assert (
        contract["target_group_wrapped_keys_captured_at_runtime_cache_stamp"]
        is True
    )
    assert contract["runtime_sparse_cache_mask_is_lineage_source"] is True
    assert (
        contract["request_finish_null_block_table_is_not_lineage_source"]
        is True
    )


def test_r10_contract_and_single_server_entrypoint_are_executable(
    tmp_path: Path,
) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    assert audit["stage"] == "P8.2-K1A-R5-F1-R10"
    assert audit["task_id"] == TASK_ID
    assert audit["developer_decision"]["cpu_blocks_per_rank"] == 128
    assert audit["developer_decision"]["pressure_context_tokens"] == 36800
    lineage = workload["cache_stamp_lineage"]
    assert lineage["instrumentation_boundary"] == (
        "gpu_block_pool_cache_full_blocks"
    )
    assert lineage["request_finish_block_id_recapture_enabled"] is False
    assert workload["runtime_config"]["pressure_context_tokens"] == 36800

    source = tmp_path / "source_payload.json"
    source.write_text(
        json.dumps({"prompt": list(range(4096))}, separators=(",", ":")),
        encoding="utf-8",
    )
    artifact = tmp_path / "artifact"
    prepared = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "prepare",
            "--source-payload",
            str(source),
            "--artifact-dir",
            str(artifact),
            "--model-name",
            "deepseek-v4-flash-w8a8-mtp",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert prepared.returncode == 0, prepared.stderr or prepared.stdout
    manifest = json.loads(
        (artifact / "request_body_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["task_id"] == TASK_ID
    assert manifest["target_prefix_blocks"] == 128

    audited = subprocess.run(
        ["bash", str(LIFECYCLE), str(tmp_path / "unused")],
        cwd=ROOT,
        env={**os.environ, "P8_2_K1A_LIFECYCLE_AUDIT_ONLY": "1"},
        text=True,
        capture_output=True,
    )
    assert audited.returncode == 0, audited.stderr or audited.stdout
    for line in (
        f"task_id={TASK_ID}",
        "execution_mode=authorized_single_lifecycle_cache_stamp_lineage",
        "parent_f1_r9_runtime_geometry_red_accepted=true",
        "accepted_capacity_invalidated=false",
        "logical_target_block_count=128",
        "target_lineage_capture_boundary=runtime_gpu_block_pool_cache_full_blocks",
        "runtime_sparse_block_mask_is_authoritative=true",
        "request_finish_null_block_table_used_for_lineage=false",
        "fixed_pressure_must_execute_after_cache_stamp_lineage=true",
        "pressure_context_tokens=36800",
        "request_retry_count_exact=0",
        "result_transfer_authorized=true",
        "automatic_transfer_allowed=false",
    ):
        assert line in audited.stdout

    server_audit = subprocess.run(
        ["bash", str(SERVER_TASK), str(tmp_path / "unused-server")],
        cwd=ROOT,
        env={
            **os.environ,
            "P8_2_K1A_F1_R10_SERVER_TASK_AUDIT_ONLY": "1",
        },
        text=True,
        capture_output=True,
    )
    assert server_audit.returncode == 0, (
        server_audit.stderr or server_audit.stdout
    )
    assert f"task_id={TASK_ID}" in server_audit.stdout
    assert (
        "server_task_driver=preflight_stop_run_cleanup_restore_probe_record_finalize"
        in server_audit.stdout
    )
    assert "keep_alive_card_ids=0,1,2,3,4,5,6,7" in server_audit.stdout
