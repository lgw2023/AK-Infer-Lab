"""Zero-NPU source/import smoke for the R3E-F2 dependency marker."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import pickle
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts import (  # noqa: E402
    p6_3c_r3e_f2_dependency_marker as marker,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_fingerprint(value: object) -> str:
    source = inspect.getsource(value).encode("utf-8")
    return hashlib.sha256(source).hexdigest()


def _source_row(label: str, value: object) -> dict[str, Any]:
    path = Path(inspect.getsourcefile(value) or "").resolve(strict=True)
    return {
        "label": label,
        "source_path": str(path),
        "source_sha256": _sha256(path),
        "callable_signature": str(inspect.signature(value)),
        "callable_source_sha256": _source_fingerprint(value),
    }


def collect_smoke_evidence() -> dict[str, Any]:
    """Resolve the exact installed targets and prove pickle propagation."""

    import torch
    import torch_npu
    from torch.profiler import record_function
    from vllm.v1.core.sched.output import SchedulerOutput
    from vllm.v1.core.sched.scheduler import Scheduler
    from vllm.v1.executor.multiproc_executor import MultiprocExecutor
    from vllm.v1.worker.worker_base import WorkerWrapperBase
    from vllm_ascend.worker.model_runner_v1 import NPUModelRunner
    from vllm_ascend.worker.worker import NPUWorker

    targets_before = [
        _source_row("Scheduler.schedule", Scheduler.schedule),
        _source_row("MultiprocExecutor.execute_model", MultiprocExecutor.execute_model),
        _source_row("WorkerWrapperBase.execute_model", WorkerWrapperBase.execute_model),
        _source_row("NPUWorker.execute_model", NPUWorker.execute_model),
        _source_row("NPUModelRunner.execute_model", NPUModelRunner.execute_model),
    ]
    source_sha_before = {
        row["source_path"]: row["source_sha256"] for row in targets_before
    }

    scheduler_output = SchedulerOutput.make_empty()
    context = marker.marker_context(
        lifecycle_id="f2_s0_pickle_probe",
        policy_id="source_mapping",
        timing_context_id="s0:0:0",
        step_index=0,
    )
    marker.attach_marker_context(scheduler_output, context)
    restored = pickle.loads(pickle.dumps(scheduler_output))
    restored_context = getattr(restored, marker.MARKER_ATTRIBUTE, None)
    marker_name = marker.build_marker_name(restored_context, 7)
    parsed = marker.parse_marker_name(marker_name)

    marker.install_p6_3c_r1_scheduler_observer()
    targets_after = [
        _source_row("Scheduler.schedule", Scheduler.schedule),
        _source_row("MultiprocExecutor.execute_model", MultiprocExecutor.execute_model),
        _source_row("WorkerWrapperBase.execute_model", WorkerWrapperBase.execute_model),
    ]
    source_sha_after = {
        row["source_path"]: _sha256(Path(row["source_path"]))
        for row in targets_before
    }
    marker_path = Path(marker.__file__).resolve(strict=True)
    torch_path = Path(torch.__file__).resolve(strict=True)
    torch_npu_path = Path(torch_npu.__file__).resolve(strict=True)
    checks = {
        "scheduler_output_has_instance_dict": hasattr(scheduler_output, "__dict__"),
        "private_context_pickle_roundtrip_exact": restored_context == context,
        "marker_name_roundtrip_exact": parsed
        == {
            **context,
            "worker_rank": 7,
        },
        "record_function_callable": callable(record_function),
        "scheduler_wrapper_installed": getattr(
            Scheduler, "_p6_3c_r3e_f2_scheduler_installed", False
        )
        is True,
        "executor_wrapper_installed": getattr(
            MultiprocExecutor, "_p6_3c_r3e_f2_executor_installed", False
        )
        is True,
        "worker_wrapper_installed": getattr(
            WorkerWrapperBase, "_p6_3c_r3e_f2_worker_marker_installed", False
        )
        is True,
        "installed_source_files_unchanged": source_sha_before == source_sha_after,
        "marker_contains_no_request_content_fields": not any(
            token in marker_name.lower()
            for token in ("prompt", "token_id", "generated", "request_id")
        ),
        "torch_source_resolved": torch_path.is_file(),
        "torch_npu_source_resolved": torch_npu_path.is_file(),
    }
    evidence = {
        "schema": "p6_3c_r3e_f2_zero_npu_source_import_smoke_v1",
        "vllm_version": importlib.metadata.version("vllm"),
        "vllm_ascend_version": importlib.metadata.version("vllm-ascend"),
        "torch_version": importlib.metadata.version("torch"),
        "torch_npu_version": importlib.metadata.version("torch-npu"),
        "torch_source_path": str(torch_path),
        "torch_source_sha256": _sha256(torch_path),
        "torch_npu_source_path": str(torch_npu_path),
        "torch_npu_source_sha256": _sha256(torch_npu_path),
        "targets_before_patch": targets_before,
        "targets_after_patch": targets_after,
        "installed_source_sha256_before": source_sha_before,
        "installed_source_sha256_after": source_sha_after,
        "marker_patch_path": str(marker_path),
        "marker_patch_sha256": _sha256(marker_path),
        "marker_name_example": marker_name,
        "marker_context_fields": sorted(context),
        "checks": checks,
        "scientific_contract_changed": False,
        "scientific_impact_statement": (
            "adds_only_a_private_scheduler_output_context_and_worker_profiler_"
            "scope;_measured_requests_policies_parameters_and_metrics_unchanged"
        ),
        "base_environment_mutated": False,
        "installed_source_files_mutated": False,
        "npu_operation_requested": False,
    }
    evidence["source_import_smoke_complete"] = all(checks.values())
    if not evidence["source_import_smoke_complete"]:
        raise RuntimeError(f"F2 source/import smoke failed: {evidence}")
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    evidence = collect_smoke_evidence()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("source_import_smoke_complete=true")
    print("npu_operation_requested=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
