from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    classify_restore_hit_to_load_gap,
    observe_compress_aware_pairing_geometry,
    observe_update_pairing_geometry,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    / "p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    / "p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    / "run_deepseek_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    / "run_deepseek_p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    / "run_deepseek_p8_2_k1a_r5_f1_r14_server_task.sh"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


class _Blk:
    def __init__(
        self, *, is_null: bool = False, block_hash=None, block_id: int = 0
    ):
        self.is_null = is_null
        self.block_hash = block_hash
        self.block_id = block_id


class _Blocks:
    def __init__(self, ids_by_group, blocks_by_group):
        self._ids = ids_by_group
        self.blocks = blocks_by_group

    def get_block_ids(self):
        return self._ids


class _Spec:
    def __init__(self, block_size: int, compress_ratio: int = 1):
        self.block_size = block_size
        self.compress_ratio = compress_ratio


class _Group:
    def __init__(self, block_size: int, compress_ratio: int = 1):
        self.kv_cache_spec = _Spec(block_size, compress_ratio)


class _Cfg:
    def __init__(self, specs):
        self.kv_cache_groups = [
            _Group(block_size, compress_ratio) for block_size, compress_ratio in specs
        ]


class _Sched:
    def __init__(self):
        self.fa_gidx = 0
        self.fa_block_size = 128
        self.block_size = 128
        self.cp_world_size = 1
        # Mirror R13 server: base 128 with compress 4 on FA group0.
        self.cpu_kv_cache_config = _Cfg(
            [
                (128, 4),
                (128, 128),
                (128, 1),
                (128, 1),
                (8, 1),
                (32, 1),
            ]
        )


def test_audit_freezes_r13_index_error_parent() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    parent = audit["accepted_f1_r13_result"]
    decision = audit["developer_decision"]
    assert audit["task_id"] == TASK_ID
    assert parent["restore_update_raise_subclass"] == "index_error_gpu_cpu_pairing"
    assert parent["restore_first_overflow_needed_index"] == 96
    assert parent["restore_first_overflow_gpu_len"] == 32
    assert decision["compress_aware_pairing_repair_required"] is True
    assert decision["task_local_observer_behavioral_repair_authorized"] is True
    assert decision["site_packages_edit_authorized"] is False


def test_compress_aware_geometry_repairs_r13_overflow() -> None:
    sched = _Sched()
    pending = (
        [
            [_Blk(block_id=i) for i in range(32)],
            [_Blk(block_id=100)],
            [_Blk(block_id=i, is_null=(i > 0)) for i in range(128)],
            [_Blk(block_id=i, is_null=(i > 0)) for i in range(128)],
            [_Blk(block_id=i, is_null=(i > 0)) for i in range(2048)],
            [_Blk(block_id=i, is_null=(i >= 4)) for i in range(512)],
        ],
        16384,
    )
    blocks = _Blocks(
        ids_by_group=[
            list(range(32)),
            [1000],
            list(range(2000, 2128)),
            list(range(3000, 3128)),
            list(range(4000, 6048)),
            list(range(7000, 7512)),
        ],
        blocks_by_group=[[_Blk() for _ in range(32)]] + [[] for _ in range(5)],
    )
    frozen = observe_update_pairing_geometry(sched, blocks, 16384, pending)
    repaired = observe_compress_aware_pairing_geometry(sched, blocks, 16384, pending)
    assert frozen["geometry_preflight_failure_class"] == "index_error_gpu_cpu_pairing"
    assert frozen["first_overflow_needed_index"] == 96
    assert frozen["first_overflow_gpu_len"] == 32
    assert repaired["compress_aware_geometry_status"] == "ok"
    assert repaired["compress_aware_block_sizes"][0] == 512
    assert repaired["compress_aware_n_take_by_group"][0] == 32
    assert repaired["compress_aware_gpu_ext_start_by_group"][0] == 0
    assert repaired["compress_aware_predicted_transfer_pair_count"] > 0


def test_classify_surfaces_repair_fields() -> None:
    rows = [
        {
            "event": "cpu_hit_matched",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 16384,
            "is_async": True,
            "pending_non_null_block_count": 40,
        },
        {
            "event": "allocate_slots_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_new_tokens": 0,
            "num_external_computed_tokens": 16384,
            "delay_cache_blocks": True,
            "allocate_slots_ok": True,
        },
        {
            "event": "update_state_after_alloc_observed",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "num_external_tokens": 16384,
            "pending_present": True,
            "pending_non_null_block_count": 40,
            "early_return_reason": "success",
            "entered_reqs_to_load": True,
            "gpu_block_ids_count": 40,
            "cpu_block_ids_count": 40,
            "pairing_repair_enabled": True,
            "pairing_repair_eligible": True,
            "pairing_repair_applied": True,
            "pairing_repair_skip_reason": "none",
            "manager_source_sha_matched": True,
            "compress_aware_geometry_status": "ok",
            "compress_aware_geometry_failure_class": "none",
            "compress_aware_block_sizes": [512, 16384, 128, 128, 8, 32],
            "compress_aware_n_take_by_group": [32, 1, 128, 128, 2048, 512],
            "compress_aware_gpu_ext_start_by_group": [0, 0, 0, 0, 0, 0],
            "compress_aware_predicted_transfer_pair_count": 40,
            "geometry_preflight_status": "would_fail",
            "geometry_preflight_failure_class": "index_error_gpu_cpu_pairing",
            "first_pairing_overflow_group_index": 0,
            "first_overflow_needed_index": 96,
            "first_overflow_gpu_len": 32,
            "num_cached_fa_blocks": 0,
        },
        {
            "event": "load_scheduled",
            "contract_role": "restore_follower",
            "request_id": "lifecycle_01_restore_follower",
            "block_count": 40,
            "gpu_block_ids_count": 40,
            "cpu_block_ids_count": 40,
            "pairing_repair_applied": True,
        },
    ]
    gap = classify_restore_hit_to_load_gap(rows)
    assert gap["restore_hit_to_load_gap_class"] == "load_scheduled"
    assert gap["restore_pairing_repair_applied"] is True
    assert gap["restore_compress_aware_geometry_status"] == "ok"
    assert gap["restore_compress_aware_n_take_by_group"][0] == 32
    assert gap["restore_compress_aware_predicted_transfer_pair_count"] == 40


def test_handoff_retains_r14_as_parent_marker() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert "p8_2_k1a_r5_f1_r14_compress_aware_pairing_repair_2026_0725" in handoff
    assert "authorized_single_lifecycle_compress_aware_pairing_repair" in handoff
    assert TASK_ID in LIFECYCLE.read_text(encoding="utf-8")
    assert TASK_ID in SERVER_TASK.read_text(encoding="utf-8")
    assert "P8_2_K1A_ENABLE_COMPRESS_AWARE_PAIRING_REPAIR" in RUNNER.read_text(
        encoding="utf-8"
    )



def test_lifecycle_audit_only_emits_r14_contract() -> None:
    result = subprocess.run(
        ["bash", str(LIFECYCLE), "/tmp/ak-r14-compress-aware-repair-audit"],
        check=True,
        capture_output=True,
        text=True,
        env={
            **dict(**{k: v for k, v in __import__("os").environ.items()}),
            "P8_2_K1A_LIFECYCLE_AUDIT_ONLY": "1",
        },
    )
    assert f"task_id={TASK_ID}" in result.stdout
    assert "compress_aware_pairing_repair=1" in result.stdout
    assert "parent_f1_r13_index_error_gpu_cpu_pairing=true" in result.stdout
    assert "task_local_observer_behavioral_repair_authorized=true" in result.stdout
