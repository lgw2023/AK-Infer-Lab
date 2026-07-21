from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


R4_R1_GRADE = "candidate_green_p8_2_k1a_r4_r1_offline_store_only_closeout"
READY_GRADE = "candidate_ready_p8_2_k1a_r5_f0_h2d_trigger_feasibility"
BLOCKED_GRADE = "blocked_p8_2_k1a_r5_f0_source_or_provenance_gate"
SENSITIVITY = "bounded_operational_metadata_no_content_or_token_ids"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_r4_r1_package(root: Path) -> dict[str, Any]:
    manifest_path = root / "candidate_manifest.server_local.json"
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != "p8_2_k1a_r4_offline_closeout_manifest_v1":
        raise ValueError("unexpected R4-R1 manifest schema")
    if manifest.get("generated_content_retained") is not False:
        raise ValueError("R4-R1 package retained generated content")
    if manifest.get("token_ids_retained") is not False:
        raise ValueError("R4-R1 package retained token ids")
    if manifest.get("result_transfer_authorized") is not True:
        raise ValueError("R4-R1 result eligibility drift")
    if manifest.get("transfer_method_selected") is not False:
        raise ValueError("R4-R1 transfer method must remain unselected")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("R4-R1 manifest files missing")
    checked: list[dict[str, Any]] = []
    for row in files:
        relative = str(row["relative_path"])
        path = root / relative
        if not path.is_file():
            flattened = root / Path(relative).name
            if not flattened.is_file():
                raise ValueError(f"R4-R1 payload missing: {relative}")
            path = flattened
        actual = {
            "relative_path": relative,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "sensitivity": row.get("sensitivity"),
        }
        if actual["bytes"] != row.get("bytes"):
            raise ValueError(f"R4-R1 payload size drift: {relative}")
        if actual["sha256"] != row.get("sha256"):
            raise ValueError(f"R4-R1 payload hash drift: {relative}")
        if actual["sensitivity"] != SENSITIVITY:
            raise ValueError(f"R4-R1 payload sensitivity drift: {relative}")
        checked.append(actual)

    grade_path = root / "task_grade.txt"
    grading_path = root / "grading_summary.json"
    if grade_path.read_text(encoding="utf-8").strip() != R4_R1_GRADE:
        raise ValueError("R4-R1 task grade drift")
    grading = _read_json(grading_path)
    if grading.get("task_grade") != R4_R1_GRADE:
        raise ValueError("R4-R1 grading summary drift")
    required_false = (
        "capacity_churn_proven_for_parent_lifecycle",
        "h2d_absence_cause_proven_as_unique",
        "formal_h2d_trigger_lifecycle_allowed",
        "performance_reference_accepted",
    )
    if any(grading.get(field) is not False for field in required_false):
        raise ValueError("R4-R1 claim boundary widened")
    if grading.get("store_only_refinalization_accepted") is not True:
        raise ValueError("R4-R1 store-only acceptance missing")
    if grading.get("refinalized_runtime_grade") != (
        "yellow_p8_2_k1a_r3_r2_r2_r1_r1_r1_store_only_no_restore"
    ):
        raise ValueError("R4-R1 no-restore boundary drift")

    return {
        "schema_version": "p8_2_k1a_r5_f0_r4_r1_acceptance_replay_v1",
        "manifest_sha256": _sha256(manifest_path),
        "payload_file_count": len(checked),
        "payload_total_bytes": sum(int(row["bytes"]) for row in checked),
        "payloads_verified": True,
        "server_grade": R4_R1_GRADE,
        "store_only_refinalization_accepted": True,
        "actual_cpu_eviction_proven": False,
        "h2d_restore_mechanism_accepted": False,
        "performance_reference_accepted": False,
    }


def verify_geometry(
    geometry_path: Path,
    rendezvous_path: Path,
    allocator_path: Path,
    *,
    gpu_blocks_per_rank: int,
) -> dict[str, Any]:
    geometry = _read_json(geometry_path)
    rendezvous = _read_json(rendezvous_path)
    allocator = _read_json(allocator_path)
    if geometry.get("schema_version") != "p8_2_k1a_r2_geometry_summary_v1":
        raise ValueError("unexpected geometry schema")
    if rendezvous.get("schema_version") != "p8_2_k1a_r2_geometry_rendezvous_v1":
        raise ValueError("unexpected rendezvous schema")
    if allocator.get("schema_version") != "p8_2_k1a_r2_allocator_envelope_v1":
        raise ValueError("unexpected allocator schema")
    probe_run_id = geometry.get("probe_run_id")
    if not probe_run_id or rendezvous.get("probe_run_id") != probe_run_id:
        raise ValueError("R2 geometry/rendezvous run mismatch")
    coverage = list(range(8))
    if geometry.get("rank_count") != 8 or geometry.get("rank_coverage") != coverage:
        raise ValueError("R2 geometry rank coverage drift")
    if rendezvous.get("world_size") != 8 or rendezvous.get("rank_coverage") != coverage:
        raise ValueError("R2 rendezvous rank coverage drift")
    if geometry.get("geometry_gate_ok") is not True:
        raise ValueError("R2 geometry gate is not green")
    if rendezvous.get("geometry_parity_exact") is not True:
        raise ValueError("R2 geometry parity drift")
    expected = {
        "block_size_tokens": 128,
        "required_restore_tokens": 16384,
        "required_cpu_blocks": 128,
        "total_bytes_per_block": 3364096,
        "required_capacity_bytes_per_rank": 430604288,
        "required_capacity_bytes_total": 3444834304,
    }
    for field, value in expected.items():
        if geometry.get(field) != value:
            raise ValueError(f"R2 geometry drift: {field}")
    if geometry.get("num_npu_blocks", gpu_blocks_per_rank) != gpu_blocks_per_rank:
        raise ValueError("R2 NPU block count drift")
    allocator_expected = {
        "grade": "candidate_ready_p8_2_k1a_r2_allocator_capacity",
        "highest_eight_rank_clean_blocks": 128,
        "required_cpu_blocks": 128,
        "candidate_cpu_bytes_per_rank": 430604288,
        "candidate_cpu_bytes_total": 3444834304,
        "acl_pinned_host_allocator_gate_ok": True,
        "capacity_candidate_ready": True,
        "formal_lifecycle_allowed": False,
    }
    for field, value in allocator_expected.items():
        if allocator.get(field) != value:
            raise ValueError(f"R2 allocator drift: {field}")
    return {
        "schema_version": "p8_2_k1a_r5_f0_geometry_provenance_v1",
        "probe_run_id": probe_run_id,
        "geometry_sha256": _sha256(geometry_path),
        "rendezvous_sha256": _sha256(rendezvous_path),
        "allocator_sha256": _sha256(allocator_path),
        "rank_coverage": coverage,
        "gpu_blocks_per_rank": gpu_blocks_per_rank,
        **expected,
        "allocator_capacity_ready": True,
        "formal_lifecycle_allowed": False,
    }


def inspect_source(manager_path: Path, block_pool_path: Path) -> dict[str, Any]:
    manager = manager_path.read_text(encoding="utf-8")
    block_pool = block_pool_path.read_text(encoding="utf-8")
    manager_needles = (
        "class SimpleCPUOffloadScheduler",
        "def get_num_new_matched_tokens",
        "find_longest_cache_hit",
        "def update_state_after_alloc",
        "_reqs_to_load",
        "def build_connector_meta",
        "load_event",
        "def _prepare_eager_store_specs",
        "get_num_free_blocks",
        "get_new_blocks",
        "def _prepare_lazy_store_specs",
        "_cursor",
    )
    block_needles = (
        "class BlockPool",
        "def get_new_blocks",
        "popleft_n",
        "_maybe_evict_cached_block",
        "cached_block_hash_to_block.pop",
    )
    missing = [value for value in manager_needles if value not in manager]
    missing += [value for value in block_needles if value not in block_pool]
    if missing:
        raise ValueError("frozen source semantics missing: " + ", ".join(missing))
    return {
        "schema_version": "p8_2_k1a_r5_f0_frozen_source_semantics_v1",
        "manager_sha256": _sha256(manager_path),
        "block_pool_sha256": _sha256(block_pool_path),
        "cpu_lookup_to_load_chain_present": True,
        "eager_store_uses_evictable_cpu_free_queue": True,
        "lazy_store_cursor_path_present": True,
        "cached_hash_eviction_path_present": True,
        "free_block_queue_dequeue_method": "popleft_n",
        "source_semantics_gate": "pass",
    }


def build_trigger_plan(
    geometry: dict[str, Any], source: dict[str, Any]
) -> dict[str, Any]:
    block_size = int(geometry["block_size_tokens"])
    cpu_blocks = int(geometry["required_cpu_blocks"])
    gpu_blocks = int(geometry["gpu_blocks_per_rank"])
    target_tokens = 8192
    pressure_tokens = 131072
    target_blocks = target_tokens // block_size
    pressure_blocks = pressure_tokens // block_size
    minimum_pressure_count = (
        gpu_blocks - target_blocks + 1 + pressure_blocks - 1
    ) // pressure_blocks
    pressure_total_blocks = minimum_pressure_count * pressure_blocks
    return {
        "schema_version": "p8_2_k1a_r5_f0_trigger_geometry_plan_v1",
        "gpu_blocks_per_rank": gpu_blocks,
        "cpu_blocks_per_rank": cpu_blocks,
        "block_size_tokens": block_size,
        "target_prefix_tokens": target_tokens,
        "target_prefix_blocks": target_blocks,
        "target_cpu_capacity_margin_blocks": cpu_blocks - target_blocks,
        "pressure_context_tokens": pressure_tokens,
        "pressure_blocks_per_request": pressure_blocks,
        "minimum_pressure_request_count_to_exceed_gpu_pool": minimum_pressure_count,
        "minimum_pressure_blocks_total": pressure_total_blocks,
        "gpu_pool_oversubscription_blocks": (
            target_blocks + pressure_total_blocks - gpu_blocks
        ),
        "eager_mode_can_preserve_target_cpu_residency": False,
        "eager_mode_rejection_reason": (
            "pressure stores exceed the remaining CPU block margin and may evict "
            "the target before GPU eviction is proven"
        ),
        "lazy_mode_source_path_present": source["lazy_store_cursor_path_present"],
        "lazy_mode_requires_runtime_residency_observer": True,
        "fixed_pressure_count_is_candidate_not_runtime_fact": True,
        "formal_h2d_trigger_lifecycle_allowed": False,
        "next_required_runtime_predicates": [
            "target_hashes_captured_without_retaining_hash_values",
            "target_present_in_cpu_tier",
            "target_absent_from_gpu_tier",
            "cpu_hit_matched_for_restore_request",
            "h2d_load_scheduled_and_completed_on_all_workers",
        ],
    }


def _write_manifest(output_dir: Path, relative_paths: list[str]) -> None:
    rows = []
    for relative in relative_paths:
        path = output_dir / relative
        rows.append(
            {
                "relative_path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "sensitivity": SENSITIVITY,
            }
        )
    _write_json(
        output_dir / "candidate_manifest.server_local.json",
        {
            "schema_version": "p8_2_k1a_r5_f0_candidate_manifest_v1",
            "files": rows,
            "payload_file_count": len(rows),
            "payload_total_bytes": sum(row["bytes"] for row in rows),
            "max_total_bytes": 71680,
            "generated_content_retained": False,
            "token_ids_retained": False,
            "result_transfer_authorized": True,
            "transfer_method_selected": False,
            "automatic_transfer_allowed": False,
        },
    )


def analyze(args: argparse.Namespace) -> int:
    from p8_2_k1a_h2d_residency_observer import observer_self_test_contract

    output = args.output_dir
    if output.exists():
        raise ValueError(f"output directory already exists: {output}")
    r4_r1 = verify_r4_r1_package(args.r4_r1_root)
    geometry = verify_geometry(
        args.geometry_summary,
        args.rendezvous_summary,
        args.allocator_summary,
        gpu_blocks_per_rank=args.gpu_blocks_per_rank,
    )
    source = inspect_source(args.manager_source, args.block_pool_source)
    plan = build_trigger_plan(geometry, source)
    observer_contract = observer_self_test_contract()
    if observer_contract["scheduling_or_copy_arguments_mutated"] is not False:
        raise ValueError("H2D observer is not observe-only")
    if observer_contract["raw_hash_values_emitted"] is not False:
        raise ValueError("H2D observer would emit raw hash values")
    output.mkdir(parents=True)
    grading = {
        "schema_version": "p8_2_k1a_r5_f0_grading_v1",
        "server_grade": READY_GRADE,
        "claim_boundary": (
            "offline_existing_evidence_frozen_source_and_trigger_geometry_"
            "feasibility_only_no_runtime_or_performance_claim"
        ),
        "r4_r1_acceptance_replay": "pass",
        "r2_geometry_allocator_provenance": "pass",
        "frozen_source_semantics_gate": "pass",
        "trigger_plan_gate": "candidate",
        "formal_h2d_trigger_lifecycle_allowed": False,
        "npu_started": False,
        "vllm_started": False,
        "model_request_sent": False,
        "keep_alive_disrupted": False,
        "actual_cpu_eviction_proven": False,
        "h2d_restore_mechanism_accepted": False,
        "performance_reference_accepted": False,
        "k2_authorized": False,
        "p8_3_i1_authorized": False,
        "next_task_authorized": False,
    }
    outputs = {
        "r4_r1_acceptance_replay.json": r4_r1,
        "geometry_provenance.json": geometry,
        "frozen_source_semantics.json": source,
        "observer_contract_probe.json": observer_contract,
        "trigger_geometry_plan.json": plan,
        "grading_summary.json": grading,
    }
    for relative, value in outputs.items():
        _write_json(output / relative, value)
    (output / "task_grade.txt").write_text(READY_GRADE + "\n", encoding="utf-8")
    (output / "result_summary.md").write_text(
        "\n".join(
            (
                "# P8.2-K1A-R5-F0 H2D trigger feasibility",
                "",
                f"- grade: `{READY_GRADE}`",
                "- R4-R1 store-only closeout and R2 geometry were replayed.",
                "- eager pressure cannot preserve the target within the accepted CPU tier.",
                "- lazy trigger remains a candidate requiring residency/eviction observation.",
                "- no NPU, vLLM lifecycle, model request, H2D acceptance or performance claim.",
                "",
            )
        ),
        encoding="utf-8",
    )
    payloads = [*outputs, "task_grade.txt", "result_summary.md"]
    _write_manifest(output, payloads)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("analyze")
    command.add_argument("--r4-r1-root", type=Path, required=True)
    command.add_argument("--geometry-summary", type=Path, required=True)
    command.add_argument("--rendezvous-summary", type=Path, required=True)
    command.add_argument("--allocator-summary", type=Path, required=True)
    command.add_argument("--manager-source", type=Path, required=True)
    command.add_argument("--block-pool-source", type=Path, required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--gpu-blocks-per-rank", type=int, default=5048)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "analyze":
        return analyze(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
