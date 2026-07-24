from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

from tools.inference_contracts.p8_2_k1a_h2d_residency_observer import (
    derive_eagle_aware_lookup_contract,
    observer_self_test_contract,
    probe_logical_restore_window,
)
from tools.inference_contracts.run_deepseek_p8_2_k1a_r5_f1_r3_inflight_abort_restore import (
    summarize_logical_keyspace_probe_diagnostics,
)


ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_2026_0723"
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r5_f1_r11_eagle_lookup_lineage_audit.yaml"
)
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.yaml"
)
RUNNER = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.py"
)
LIFECYCLE = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r11_eagle_lookup_lineage.sh"
)
SERVER_TASK = (
    ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r5_f1_r11_server_task.sh"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


@dataclass
class _Block:
    block_hash: object | None
    is_null: bool = False


class _Mapping:
    def __init__(self, keys: set[object]) -> None:
        self.keys = keys

    def get_one_block(self, key: object) -> object | None:
        return object() if key in self.keys else None


class _Pool:
    def __init__(self, keys: set[object]) -> None:
        self.cached_block_hash_to_block = _Mapping(keys)


class _Manager:
    def __init__(self, *, use_eagle: bool) -> None:
        self.use_eagle = use_eagle

    @classmethod
    def find_longest_cache_hit(
        cls,
        *,
        block_hashes: list[object],
        max_length: int,
        kv_cache_group_ids: list[int],
        block_pool: _Pool,
        kv_cache_spec: object,
        use_eagle: bool,
        alignment_tokens: int,
    ) -> tuple[list[_Block], ...]:
        del block_hashes, block_pool, alignment_tokens
        effective = int(kv_cache_spec.block_size) * int(
            kv_cache_spec.compress_ratio
        )
        count = min(
            max_length // effective,
            int(kv_cache_spec.available_blocks),
        )
        if use_eagle and count:
            count -= 1
        return tuple(
            [
                _Block(f"group{group_id}-{index}")
                for index in range(count)
            ]
            for group_id in kv_cache_group_ids
        )


class _Coordinator:
    def __init__(self, *, use_eagle: bool = True) -> None:
        full_spec = type(
            "AscendMLAAttentionSpec",
            (),
            {
                "block_size": 128,
                "compress_ratio": 4,
                # Enough effective blocks for the conservative 32K horizon so
                # the EAGLE group still sees a candidate above the accepted
                # 16K boundary before applying frozen spec.block_size delta.
                "available_blocks": 64,
            },
        )()
        eagle_spec = type(
            "AscendMLAAttentionSpec",
            (),
            {
                "block_size": 128,
                "compress_ratio": 128,
                "available_blocks": 2,
            },
        )()
        self.use_eagle = use_eagle
        self.attention_groups = (
            (full_spec, [0], _Manager),
            (eagle_spec, [1], _Manager),
        )
        # Frozen Ascend HybridKVCacheCoordinator populates this only when
        # constructed with use_eagle=True. SimpleCPUOffloadScheduler passes
        # use_eagle=False for the CPU coordinator.
        self.eagle_attn_group_indices = {1} if use_eagle else set()
        self.single_type_managers = (
            _Manager(use_eagle=False),
            _Manager(use_eagle=use_eagle),
        )
        self.block_pool = _Pool(set())
        self.calls: list[int] = []
        self.num_uncached_common_prefix_tokens = 17

    @staticmethod
    def _get_effective_block_size(spec: object) -> int:
        return int(spec.block_size) * int(spec.compress_ratio)

    def find_longest_cache_hit(
        self,
        request_hashes: list[object],
        max_length: int,
    ) -> tuple[tuple[list[_Block], ...], int]:
        self.calls.append(max_length)
        self.num_uncached_common_prefix_tokens = 99
        candidate = max_length
        by_group: list[list[_Block]] = [[], []]
        for index, (spec, group_ids, manager_class) in enumerate(
            self.attention_groups
        ):
            use_eagle = index in self.eagle_attn_group_indices
            manager_max = candidate
            if use_eagle:
                # Frozen Ascend: curr_hit_length + spec.block_size.
                manager_max = min(candidate + int(spec.block_size), max_length)
            result = manager_class.find_longest_cache_hit(
                block_hashes=request_hashes,
                max_length=manager_max,
                kv_cache_group_ids=group_ids,
                block_pool=self.block_pool,
                kv_cache_spec=spec,
                use_eagle=use_eagle,
                alignment_tokens=16384,
            )
            candidate = (
                len(result[0]) * self._get_effective_block_size(spec)
            )
            for group_id, blocks in zip(group_ids, result):
                by_group[group_id] = blocks
        return tuple(by_group), candidate


def test_eagle_lookup_horizon_is_derived_without_changing_accepted_target() -> None:
    coordinator = _Coordinator(use_eagle=True)
    request_hashes = [f"request-{index}" for index in range(256)]

    contract = derive_eagle_aware_lookup_contract(
        cpu_coordinator=coordinator,
        request_hashes=request_hashes,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
    )

    assert contract["accepted_restore_match_tokens"] == 16384
    assert contract["logical_lookup_lookahead_tokens"] == 16384
    assert contract["logical_lookup_horizon_basis"] == (
        "conservative_two_effective_block_ceiling"
    )
    assert contract["logical_lookup_desired_horizon_tokens"] == 32768
    assert contract["logical_lookup_probe_horizon_tokens"] == 32768
    assert contract["logical_lookup_horizon_exact"] is True
    assert contract["cpu_coordinator_use_eagle"] is True
    assert contract["eagle_lookahead_delta_tokens"] == 128
    assert contract["eagle_lookahead_required_tokens"] == 16384
    assert contract["eagle_lookahead_sufficient"] is False
    assert contract["logical_lookup_eagle_attention_group_count"] == 1
    assert contract["logical_lookup_group_contract_rows"][1][
        "manager_use_eagle_flags"
    ] == [True]


def test_frozen_cpu_coordinator_reports_use_eagle_false() -> None:
    coordinator = _Coordinator(use_eagle=False)
    request_hashes = [f"request-{index}" for index in range(256)]

    contract = derive_eagle_aware_lookup_contract(
        cpu_coordinator=coordinator,
        request_hashes=request_hashes,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
    )

    assert contract["cpu_coordinator_use_eagle"] is False
    assert contract["eagle_lookahead_delta_tokens"] == 0
    assert contract["eagle_lookahead_sufficient"] is False
    assert contract["logical_lookup_eagle_attention_group_count"] == 0
    # Conservative ceiling still enables a two-effective-block对照 probe.
    assert contract["logical_lookup_probe_horizon_tokens"] == 32768


def test_eagle_aware_probe_exposes_legacy_boundary_false_negative() -> None:
    coordinator = _Coordinator(use_eagle=True)
    request_hashes = [f"request-{index}" for index in range(256)]
    pool_keys = {
        *(f"group0-{index}" for index in range(64)),
        "group1-0",
        "group1-1",
    }

    summary, retained = probe_logical_restore_window(
        cpu_coordinator=coordinator,
        request_hashes=request_hashes,
        restore_match_tokens=16384,
        hash_block_size_tokens=128,
        cpu_pool=_Pool(pool_keys),
        gpu_pool=_Pool(set()),
        eagle_aware=True,
    )

    assert coordinator.calls == [16384, 32768]
    assert coordinator.num_uncached_common_prefix_tokens == 17
    assert summary["legacy_capped_logical_restore_match_tokens"] == 0
    assert summary["raw_logical_restore_match_tokens"] == 16384
    assert summary["logical_restore_match_tokens"] == 16384
    assert summary["logical_restore_window_exact"] is True
    assert summary["legacy_capped_false_negative_candidate"] is True
    assert summary["logical_lookup_group_lineage_observable"] is True
    assert summary["eagle_lookahead_delta_tokens"] == 128
    assert summary["eagle_lookahead_sufficient"] is False
    eagle_row = next(
        row
        for row in summary["logical_lookup_iteration_rows"]
        if row.get("attention_group_index") == 1
    )
    # Outer conservative horizon lets the eagle group read two effective
    # blocks even though frozen inner delta is only spec.block_size=128.
    assert eagle_row["eagle_inner_readable_blocks"] == 2
    assert eagle_row["eagle_lookahead_sufficient"] is True
    assert eagle_row["eagle_lookahead_requested"] is False
    assert summary["target_pool_key_count"] == 65
    assert summary["cpu_target_pool_key_match_count"] == 65
    assert len(retained) == 65


def test_bounded_diagnostic_keeps_logical_source_after_lineage_merge() -> None:
    rows = [
        {
            "event": "request_local_pressure_progress",
            "timestamp_ns": 100,
            "contract_role": "pressure_01",
            "target_capture_source": "runtime_gpu_cache_stamp_sparse_mask_keys",
            "logical_probe_source": "runtime_cpu_coordinator_longest_hit",
            "target_capture_exact": True,
            "logical_restore_match_tokens": 16384,
            "raw_logical_restore_match_tokens": 16384,
            "legacy_capped_logical_restore_match_tokens": 0,
            "logical_lookup_probe_horizon_tokens": 32768,
            "logical_lookup_lookahead_tokens": 16384,
            "legacy_capped_false_negative_candidate": True,
            "logical_lookup_group_lineage_observable": True,
            "logical_lookup_first_reduction_attention_group_index": 0,
            "logical_lookup_first_reduction_spec_type": (
                "AscendMLAAttentionSpec"
            ),
            "logical_lookup_first_zero_attention_group_index": -1,
            "logical_lookup_iteration_rows": [
                {
                    "attention_group_index": 0,
                    "candidate_in_tokens": 32768,
                    "returned_hit_tokens": 16384,
                    "raw_hash_values_retained": False,
                }
            ],
            "logical_lookup_group_contract_rows": [],
        }
    ]

    summary = summarize_logical_keyspace_probe_diagnostics(rows)

    assert summary["probe_event_count"] == 1
    assert summary["exact_probe_event_count"] == 1
    assert summary["legacy_capped_false_negative_candidate_count"] == 1
    assert summary["logical_lookup_probe_horizon_tokens_max"] == 32768
    assert summary["best_probe_first_reduction_attention_group_index"] == 0
    assert len(summary["best_probe_lookup_iteration_rows"]) == 1


def test_observer_contract_declares_eagle_aware_probe_without_runtime_mutation() -> None:
    contract = observer_self_test_contract()

    assert contract[
        "eagle_aware_lookup_horizon_derived_from_runtime_groups"
    ] is True
    assert contract[
        "lookup_horizon_basis_is_conservative_two_effective_block_ceiling"
    ] is True
    assert contract[
        "eagle_inner_delta_is_spec_block_size_not_effective"
    ] is True
    assert contract["cpu_coordinator_use_eagle_is_runtime_observed"] is True
    assert contract["accepted_restore_target_unchanged_by_lookup_horizon"] is True
    assert contract["legacy_capped_and_eagle_aware_probe_comparison"] is True
    assert contract["per_attention_group_lookup_lineage_bounded"] is True
    assert contract["scheduling_or_copy_arguments_mutated"] is False


def test_r11_contract_and_single_server_entrypoint_are_executable(
    tmp_path: Path,
) -> None:
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    assert audit["stage"] == "P8.2-K1A-R5-F1-R11"
    assert audit["task_id"] == TASK_ID
    assert audit["accepted_f1_r10_result"]["physical_cpu_only_window_event_count"] == 8
    assert audit["developer_decision"]["cpu_blocks_per_rank"] == 128
    assert audit["developer_decision"]["accepted_restore_match_tokens"] == 16384
    assert audit["developer_decision"]["legacy_capped_probe_retained"] is True
    assert audit["developer_decision"]["runtime_dependency_mutation_authorized"] is False
    assert audit["cpu_coordinator_source_contract"][
        "constructor_use_eagle"
    ] is False
    lookup = workload["eagle_aware_logical_lookup"]
    assert lookup["accepted_restore_match_tokens"] == 16384
    assert lookup["probe_horizon_source"] == (
        "conservative_two_effective_block_ceiling"
    )
    assert lookup["eagle_inner_delta_source"] == "spec_block_size"
    assert lookup["per_attention_group_lookup_lineage_required"] is True
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
    assert manifest["restore_match_tokens_required"] == 16384
    assert manifest["restore_shared_prefix_tokens"] == 32768
    assert manifest["restore_token_lcp"] == 32768
    assert manifest["target_restore_prompts_identical"] is True
    assert manifest["identical_target_restore_bodies_authorized"] is True
    assert manifest[
        "body_hashes_unique_except_authorized_target_restore_repeat"
    ] is True

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
        "execution_mode=authorized_single_lifecycle_eagle_lookup_lineage",
        "parent_f1_r10_physical_window_exact=true",
        "accepted_capacity_invalidated=false",
        "accepted_restore_match_tokens=16384",
        "restore_shared_prefix_tokens=32768",
        "eagle_aware_logical_lookup=1",
        "legacy_capped_probe_retained=true",
        "per_attention_group_lookup_lineage_required=true",
        "pressure_context_tokens=36800",
        "request_retry_count_exact=0",
        "runtime_dependency_mutation_authorized=false",
        "result_transfer_authorized=true",
        "automatic_transfer_allowed=false",
    ):
        assert line in audited.stdout

    server_audit = subprocess.run(
        ["bash", str(SERVER_TASK), str(tmp_path / "unused-server")],
        cwd=ROOT,
        env={
            **os.environ,
            "P8_2_K1A_F1_R11_SERVER_TASK_AUDIT_ONLY": "1",
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

    handoff = HANDOFF.read_text(encoding="utf-8")
    # Current handoff may already advance past R11; keep parent provenance markers.
    assert f"parent_f1_r11_task_id: {TASK_ID}" in handoff
    assert "parent_grade: red_p8_2_k1a_r5_f1_r11_h2d_evidence_incomplete" in handoff
    assert "result_transfer_authorized: true" in handoff
    assert "transfer_method_selected: false" in handoff
    assert "automatic_transfer_allowed: false" in handoff
    assert AUDIT.is_file()
    assert SERVER_TASK.is_file()
    assert "eagle_aware_probe_enabled: true" in AUDIT.read_text(encoding="utf-8")
