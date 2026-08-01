from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterator


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TASK_ID = (
    "p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01"
)
ACCEPTANCE_TASK_ID = "p6_3c_r2_f4_a1_adaptive_acceptance_2026_0801"
EXPECTED_EXECUTED_CONTROLLER_SHA256 = (
    "a396ba49f94922592854192de139e497232e8952f718cc791d36e372a7a42f4b"
)
EXPECTED_PRE_ADAPTATION_CONTROLLER_SHA256 = (
    "6cf48b4f96d779a108bac30aba46bf075ba5e72fd39526d76f9699c1b3ee4a9d"
)
EXPECTED_SOURCE_RUNNER_SHA256 = (
    "98bdefed22613910e784b87f720d2fc59d7fdf008fb08c4044d86709b14adb06"
)
EXPECTED_SOURCE_WORKLOAD_SHA256 = (
    "0ffcccee719dceab21ce1f3ac893e144a4adf5870cf11db25ad526afb3d9a520"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_source_result(source_result_dir: Path) -> dict[str, Any]:
    required = {
        "environment_and_hashes.json",
        "grading_inputs.json",
        "atomic_pair_admission_summary.json",
        "mechanism_scheduler_summary.json",
        "resource_recovery_summary.json",
        "result_summary.md",
    }
    missing = sorted(
        name for name in required if not (source_result_dir / name).is_file()
    )
    if missing:
        raise ValueError(f"source result is missing required files: {missing}")

    environment = _read_json(source_result_dir / "environment_and_hashes.json")
    grading = _read_json(source_result_dir / "grading_inputs.json")
    atomic = _read_json(source_result_dir / "atomic_pair_admission_summary.json")
    mechanism = _read_json(source_result_dir / "mechanism_scheduler_summary.json")
    recovery = _read_json(source_result_dir / "resource_recovery_summary.json")

    source_task_id = str(environment.get("task_id") or grading.get("task_id") or "")
    checks = {
        "source_task_id_exact": source_task_id == SOURCE_TASK_ID,
        "executed_controller_matches_server_adaptation": (
            environment.get("f4_atomic_pair_admission_sha256")
            == EXPECTED_EXECUTED_CONTROLLER_SHA256
        ),
        "executed_runner_matches_source_run": (
            environment.get("f4_runner_sha256") == EXPECTED_SOURCE_RUNNER_SHA256
        ),
        "executed_workload_matches_source_run": (
            environment.get("workload_sha256") == EXPECTED_SOURCE_WORKLOAD_SHA256
        ),
        "all_lifecycles_success": grading.get("all_lifecycles_success") is True,
        "request_count_exact": grading.get("successful_request_count") == 90,
        "batch_count_exact": grading.get("successful_batch_count") == 48,
        "request_id_normalization_complete": (
            grading.get("request_id_normalization_gate_complete") is True
        ),
        "coarrival_complete": grading.get("coarrival_gate_complete") is True,
        "mechanism_complete": mechanism.get("mechanism_gate_complete") is True,
        "atomic_release_exact": (
            atomic.get("exact_pair_release_count") == 42
            and atomic.get("atomic_pair_release_gate_complete") is True
        ),
        "terminal_state_clean": (
            atomic.get("all_lifecycle_terminal_states_clean") is True
        ),
        "resource_recovery_clean": (
            recovery.get("keep_alive_restored_exact") is True
            and recovery.get("port_7000_listener_count") == 0
            and recovery.get("vllm_residual_process_count") == 0
            and recovery.get("tracked_worktree_clean") is True
        ),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ValueError(f"source result evidence is incomplete: {failed}")
    return {
        "source_task_id": source_task_id,
        "source_server_grade": grading.get("server_grade"),
        "source_environment": environment,
        "checks": checks,
    }


@contextmanager
def _f4_environment() -> Iterator[None]:
    updates = {
        "P6_3C_TASK_ID": SOURCE_TASK_ID,
        "P6_3C_REQUEST_ID_PREFIX": "p6_3c_r2_f4",
        "P6_3C_ATOMIC_PAIR_ADMISSION": "1",
        "P6_3C_ATOMIC_PAIR_REQUEST_PREFIX": "p6_3c_r2_f4",
        "P6_3C_ATOMIC_PAIR_ADMISSION_MODULE": (
            "p6_3c_r2_f4_atomic_pair_admission"
        ),
    }
    original = {name: os.environ.get(name) for name in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _prepare_derived_view(source_result_dir: Path, working_dir: Path) -> None:
    for source in source_result_dir.iterdir():
        if source.is_file():
            shutil.copy2(source, working_dir / source.name)
    lifecycle_root = source_result_dir / "lifecycles"
    if not lifecycle_root.is_dir():
        raise ValueError(
            "source raw result must retain lifecycles/ for evidence re-finalization"
        )
    (working_dir / "lifecycles").symlink_to(lifecycle_root.resolve(), target_is_directory=True)


def _source_top_level_manifest(source_result_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(source_result_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        rows.append(
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return rows


def refinalize_adaptive_run(
    source_result_dir: Path,
    derived_result_dir: Path,
) -> dict[str, Any]:
    source_result_dir = source_result_dir.resolve()
    if derived_result_dir.exists():
        raise FileExistsError(f"derived result already exists: {derived_result_dir}")
    source_review = validate_source_result(source_result_dir)

    published_controller = (
        REPO_ROOT
        / "tools/inference_contracts/p6_3c_r2_f4_atomic_pair_admission.py"
    )
    published_workload = (
        REPO_ROOT
        / "benchmarks/deepseek_v4_flash/workloads/"
        "p6_3c_r2_f4_request_id_normalized_atomic_coarrival_matched_ab.yaml"
    )
    published_controller_sha256 = _sha256(published_controller)
    published_workload_sha256 = _sha256(published_workload)
    if published_controller_sha256 != EXPECTED_EXECUTED_CONTROLLER_SHA256:
        raise ValueError(
            "published controller does not match the successful server adaptation: "
            f"{published_controller_sha256}"
        )

    with _f4_environment():
        from tools.inference_contracts import (
            run_deepseek_p6_3c_r2_f4_atomic_pair_admission as f4,
        )

    derived_result_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{ACCEPTANCE_TASK_ID}.",
        dir=derived_result_dir.parent,
    ) as temporary:
        working_dir = Path(temporary)
        _prepare_derived_view(source_result_dir, working_dir)
        with _f4_environment():
            grading = f4.finalize_artifacts(working_dir)

        if not str(grading.get("server_grade", "")).startswith("candidate_green"):
            raise ValueError(
                "corrected finalizer did not accept complete mechanism evidence: "
                f"{grading.get('server_grade')}"
            )
        if grading.get("f4_runtime_and_transport_gates_complete") is not True:
            raise ValueError("corrected runtime and transport capability gate is incomplete")

        derived_result_dir.mkdir()
        for name in f4.F4_BOUNDED_CANDIDATES:
            source = working_dir / name
            if source.is_file():
                shutil.copy2(source, derived_result_dir / name)

        source_manifest = _source_top_level_manifest(source_result_dir)
        source_manifest_payload = (
            json.dumps(source_manifest, indent=2, sort_keys=True) + "\n"
        )
        source_manifest_path = (
            derived_result_dir / "source_top_level_manifest.server_local.json"
        )
        source_manifest_path.write_text(
            source_manifest_payload,
            encoding="utf-8",
        )
        review = {
            "schema_version": 1,
            "acceptance_task_id": ACCEPTANCE_TASK_ID,
            "source_task_id": SOURCE_TASK_ID,
            "source_result_dir": str(source_result_dir),
            "source_server_grade_preserved": source_review["source_server_grade"],
            "corrected_evidence_outcome": (
                "accepted_chunked_prefill_scheduler_mechanism_observed"
            ),
            "corrected_server_grade": grading["server_grade"],
            "scientific_contract_changed_by_adaptation": False,
            "measured_pair_admission_changed_by_adaptation": False,
            "warmup_singleton_passthrough_only": True,
            "executed_workload_sha256": EXPECTED_SOURCE_WORKLOAD_SHA256,
            "published_workload_sha256": published_workload_sha256,
            "published_workload_science_contract_unchanged": True,
            "published_workload_updates": (
                "run01 outcome and superseding adaptive-execution policy only"
            ),
            "server_adaptation": {
                "reported_attempt_count": 3,
                "successful_attempt_index": 3,
                "reason": (
                    "warmup contains one request but its runtime ID matched the "
                    "measured-pair parser and waited for a nonexistent peer"
                ),
                "implementation": (
                    "pass normalized pair keys ending in _warmup directly to "
                    "the original EngineCore.add_request"
                ),
                "pre_adaptation_controller_sha256": (
                    EXPECTED_PRE_ADAPTATION_CONTROLLER_SHA256
                ),
                "executed_controller_sha256": (
                    EXPECTED_EXECUTED_CONTROLLER_SHA256
                ),
                "published_controller_sha256": published_controller_sha256,
                "executed_source_matches_published_source": True,
                "shared_worktree_restored_after_server_run": True,
            },
            "classification_repair": {
                "old_logic": "infer atomic admission from _r2_f3_ task-id substring",
                "new_logic": (
                    "read P6_3C_ATOMIC_PAIR_ADMISSION capability from the actual "
                    "execution environment"
                ),
                "mechanism_red_was_scientifically_incorrect": True,
            },
            "accepted_evidence": {
                "lifecycles": "6/6",
                "requests": "90/90",
                "batches": "48/48",
                "atomic_pairs": "42/42",
                "mechanism_first_step_contracts": "6/6",
                "off_partial_prefill_absent_all_cells": True,
                "on_partial_prefill_present_both_pressure_cells": True,
                "low_pressure_partial_prefill_absent_both_modes": True,
                "resource_recovery_clean": True,
            },
            "performance_conclusion": (
                "the controlled samples did not show a short-request latency or "
                "batch-throughput benefit; retain the measurements as descriptive"
            ),
            "claim_boundary": (
                "controlled atomic co-arrival mechanism evidence only; no universal "
                "performance or natural production arrival claim"
            ),
            "source_validation": source_review["checks"],
            "source_top_level_manifest": {
                "file_count": len(source_manifest),
                "total_bytes": sum(row["bytes"] for row in source_manifest),
                "sha256": hashlib.sha256(
                    source_manifest_payload.encode("utf-8")
                ).hexdigest(),
                "path": source_manifest_path.name,
                "retained_server_local": True,
            },
        }
        (derived_result_dir / f4.ADAPTIVE_EXECUTION_REVIEW).write_text(
            json.dumps(review, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with _f4_environment():
            manifest = f4.package_results(derived_result_dir)
        manifest["source_task_id"] = manifest["task_id"]
        manifest["task_id"] = ACCEPTANCE_TASK_ID
        manifest["result_summary_path"] = str(
            (derived_result_dir / "result_summary.md").resolve()
        )
        (derived_result_dir / "candidate_manifest.server_local.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return {
        "acceptance_task_id": ACCEPTANCE_TASK_ID,
        "derived_result_dir": str(derived_result_dir.resolve()),
        "corrected_server_grade": grading["server_grade"],
        "candidate_file_count": manifest["candidate_file_count"],
        "candidate_total_bytes": manifest["candidate_total_bytes"],
        "result_transfer_authorized": manifest["result_transfer_authorized"],
        "transfer_method_selected": manifest["transfer_method_selected"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-finalize the complete P6.3C-R2-F4 raw result without NPU use, "
            "preserving the server adaptation as reviewed provenance."
        )
    )
    parser.add_argument("--source-result-dir", type=Path, required=True)
    parser.add_argument("--derived-result-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.validate_only:
        result = validate_source_result(args.source_result_dir.resolve())
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.derived_result_dir is None:
        raise SystemExit("--derived-result-dir is required unless --validate-only is used")
    result = refinalize_adaptive_run(
        args.source_result_dir,
        args.derived_result_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
