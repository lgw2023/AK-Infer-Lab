from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

from tools.inference_contracts.p8_2_k1a_simple_cpu_offload_observer import (
    classify_restore_hit_to_load_gap,
    classify_update_raise_subclass,
    observe_update_pairing_geometry,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r13_update_raise_geometry_2026_0724"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r13_update_raise_geometry_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r13_update_raise_geometry.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r13_update_raise_geometry.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r13_update_raise_geometry.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r13_server_task.sh"
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
    def __init__(self, block_size: int):
        self.block_size = block_size


class _Group:
    def __init__(self, block_size: int):
        self.kv_cache_spec = _Spec(block_size)


class _Cfg:
    def __init__(self, sizes):
        self.kv_cache_groups = [_Group(s) for s in sizes]


class _Sched:
    def __init__(self):
        self.fa_gidx = 0
        self.fa_block_size = 512
        self.block_size = 128
        self.cp_world_size = 1
        self.cpu_kv_cache_config = _Cfg([512, 16384, 128, 8, 32])


def test_audit_freezes_r12_update_raised_parent() -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    parent = audit["accepted_f1_r12_result"]
    decision = audit["developer_decision"]
    assert audit["task_id"] == TASK_ID
    assert parent["restore_hit_to_load_gap_class"] == "update_raised"
    assert parent["restore_pending_non_null_block_count"] == 40
    assert parent["restore_num_new_tokens_at_alloc"] == 0
    assert decision["update_raise_geometry_lineage_required"] is True
    assert "restore_update_error_type" in decision["required_bounded_fields"]
    assert "index_error_gpu_cpu_pairing" in decision["required_raise_subclasses"]


def test_classify_update_raised_surfaces_error_and_geometry() -> None:
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
            "early_return_reason": "update_raised",
            "entered_reqs_to_load": False,
            "error_type": "IndexError",
            "error_message": "list index out of range",
            "geometry_preflight_status": "would_fail",
            "geometry_preflight_failure_class": "index_error_gpu_cpu_pairing",
            "fa_gidx": 0,
            "fa_block_size": 512,
            "num_cached_fa_blocks": 0,
            "num_computed_tokens_from_fa": 0,
            "total_computed_tokens_expected": 16384,
            "gpu_group_count": 5,
            "pending_group_count": 5,
            "gpu_block_table_lens": [0, 0, 0, 0, 0],
            "pending_block_counts": [32, 1, 1, 1, 5],
            "pending_non_null_counts": [32, 1, 1, 1, 5],
            "n_take_by_group": [32, 1, 128, 2048, 512],
            "gpu_ext_start_by_group": [0],
            "first_pairing_overflow_group_index": 0,
            "first_overflow_needed_index": 0,
            "first_overflow_gpu_len": 0,
            "predicted_transfer_pair_count": 0,
        },
    ]
    gap = classify_restore_hit_to_load_gap(rows)
    assert gap["restore_hit_to_load_gap_class"] == "update_raised"
    assert gap["restore_update_error_type"] == "IndexError"
    assert "list index out of range" in gap["restore_update_error_message"]
    assert gap["restore_update_raise_subclass"] == "index_error_gpu_cpu_pairing"
    assert gap["restore_first_pairing_overflow_group_index"] == 0
    assert gap["restore_first_overflow_gpu_len"] == 0
    assert gap["restore_num_cached_fa_blocks"] == 0


def test_observe_pairing_geometry_detects_empty_gpu_tables() -> None:
    sched = _Sched()
    pending = (
        [
            [_Blk(block_id=i) for i in range(32)],
            [_Blk(block_id=100)],
            [_Blk(block_id=200)],
            [_Blk(block_id=300)],
            [_Blk(block_id=i) for i in range(400, 405)],
        ],
        16384,
    )
    blocks = _Blocks(
        ids_by_group=[[], [], [], [], []],
        blocks_by_group=[[] for _ in range(5)],
    )
    geo = observe_update_pairing_geometry(sched, blocks, 16384, pending)
    assert geo["geometry_preflight_status"] == "would_fail"
    assert geo["geometry_preflight_failure_class"] == (
        "index_error_gpu_cpu_pairing"
    )
    assert geo["first_pairing_overflow_group_index"] == 0
    assert geo["first_overflow_gpu_len"] == 0
    assert (
        classify_update_raise_subclass(
            {
                "early_return_reason": "update_raised",
                "error_type": "IndexError",
                "error_message": "list index out of range",
                **geo,
            }
        )
        == "index_error_gpu_cpu_pairing"
    )


def test_handoff_and_runners_point_at_r13() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    assert TASK_ID in handoff
    assert "authorized_single_lifecycle_update_raise_geometry" in handoff
    assert "restore_update_error_type" in handoff
    assert "restore_first_pairing_overflow_group_index" in handoff
    assert workload["task_id"] == TASK_ID
    assert RUNNER.is_file()
    assert LIFECYCLE.is_file()
    assert SERVER_TASK.is_file()


def test_lifecycle_audit_only_emits_r13_contract() -> None:
    result = subprocess.run(
        ["bash", str(LIFECYCLE), "/tmp/ak-r13-update-raise-audit"],
        check=True,
        capture_output=True,
        text=True,
        env={
            **dict(**{k: v for k, v in __import__("os").environ.items()}),
            "P8_2_K1A_LIFECYCLE_AUDIT_ONLY": "1",
        },
    )
    assert f"task_id={TASK_ID}" in result.stdout
    assert "update_raise_geometry_lineage=1" in result.stdout
    assert "update_raise_error_type_required=true" in result.stdout
    assert "parent_f1_r12_update_raised=true" in result.stdout
