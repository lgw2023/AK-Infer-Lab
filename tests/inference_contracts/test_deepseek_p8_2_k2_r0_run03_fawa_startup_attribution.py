from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from tools.inference_contracts.run_deepseek_p8_2_k2_r0_run03_fawa_startup_attribution import (
    MAX_TRANSFER_BYTES,
    RUN_ID,
    TASK_ID,
    package,
    parse_exception,
    parse_store_geometry,
    validate_parent,
)


ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = (
    ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    / "p8_2_k2_r0_run03_fawa_startup_attribution.yaml"
)
AUDIT = (
    ROOT
    / "benchmarks/deepseek_v4_flash/"
    / "p8_2_k2_r0_run03_fawa_startup_attribution_audit.yaml"
)
SERVER_DRIVER = (
    ROOT
    / "tools/inference_contracts/"
    / "run_deepseek_p8_2_k2_r0_run03_fawa_startup_attribution_server_task.sh"
)
HANDOFF = ROOT / "通信模块/docs/developer-to-server.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_parser_recovers_inner_exception_and_fawa_store_geometry(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    log = tmp_path / "vllm_server.log"
    log.write_text(
        "\n".join(
            (
                "create FAWA FA UcmPipelineStore with config: "
                "{'cache_buffer_capacity_gb': 16, 'device_id': -1, "
                "'block_size': 6627328, 'store_pipeline': 'Cache|Posix'}",
                "create FAWA WA UcmPipelineStore with config: "
                "{'cache_buffer_capacity_gb': 16, 'device_id': 0, "
                "'block_size': 134217728, 'shard_size': 134217728, "
                "'tensor_count': 43, 'tensor_bytes': 134217728, "
                "'store_pipeline': 'Cache|Posix'}",
                "Traceback (most recent call last):",
                f'  File "{source_root}/ucm/integration/vllm/ucm_connector.py", '
                "line 2669, in __init__",
                "    self.connector = UCMFAWAConnector(...)",
                f'  File "{source_root}/ucm/integration/vllm/hma_connector.py", '
                "line 749, in _create_store",
                "    return UcmConnectorFactoryV1.create_connector(...)",
                "RuntimeError: -50000, invalid shard size(134217728)",
                "RuntimeError: Worker failed with error '-50000'",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    geometry = parse_store_geometry(log.read_text().splitlines(), 16)
    summary, excerpt = parse_exception(
        log,
        source_root,
        geometry["observations"],
    )
    assert geometry["store_config_observation_count"] == 2
    assert geometry["role_label_counts"] == {
        "scheduler:FA": 1,
        "worker:WA": 1,
    }
    assert (
        geometry["predicted_combined_fa_wa_capacity_gib_per_connector_instance"] == 32
    )
    assert summary["primary_exception"]["exception_type"] == "RuntimeError"
    assert summary["primary_exception"]["exception_message"] == (
        "-50000, invalid shard size(134217728)"
    )
    assert summary["outer_fawa_dispatch_line_2669_observed"] is True
    assert summary["hma_inner_frame_observed"] is True
    assert summary["failure_stage"]["stage"] == "fawa_wa_store_factory_creation"
    assert "invalid shard size(134217728)" in excerpt


def test_parent_validation_verifies_manifest_payloads_and_raw_log(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728_run03"
    runtime = parent / "runtime"
    runtime.mkdir(parents=True)
    payloads = {
        "grading_summary.json": {
            "grade": "blocked_p8_2_k2_r0_lifecycle_startup",
            "path_class": "lifecycle_startup_failed_before_requests",
            "startup_class": "lifecycle_startup_failed_other",
            "formal_model_lifecycle_count": 1,
            "request_count": 0,
            "dependency_status": "ready",
            "startup_capacity_status": "ready",
        },
        "startup_failure_summary.json": {
            "ucm_too_small_buffer_observed": False,
        },
        "startup_capacity_summary.json": {"status": "ready"},
    }
    files = []
    for name, value in payloads.items():
        path = parent / name
        path.write_text(
            json.dumps(value, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        files.append(
            {
                "relative_path": name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "task_id": "p8_2_k2_r0_ucm_dram_external_prefix_path_2026_0728",
        "payload_file_count": len(files),
        "files": files,
    }
    manifest_path = parent / "candidate_manifest.server_local.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    raw_log = runtime / "vllm_server.log"
    raw_log.write_text("RuntimeError: bounded startup failure\n", encoding="utf-8")
    provenance, selected_log, _ = validate_parent(
        parent,
        expected_manifest_sha256=_sha256(manifest_path),
        expected_manifest_bytes=manifest_path.stat().st_size,
    )
    assert selected_log == raw_log
    assert provenance["parent_payloads_all_match_manifest"] is True
    assert provenance["parent_raw_log_hash_retained"] is False


def test_bounded_package_inventory_converges(tmp_path: Path) -> None:
    result = tmp_path / RUN_ID
    result.mkdir()
    payload_names = (
        "fawa_store_geometry.json",
        "grading_summary.json",
        "parent_provenance.json",
        "resource_observation_summary.json",
        "source_constructor_lineage.json",
        "startup_exception_summary.json",
    )
    for name in payload_names:
        (result / name).write_text("{}\n", encoding="utf-8")
    (result / "result_summary.md").write_text("# result\n", encoding="utf-8")
    (result / "startup_traceback_excerpt.txt").write_text(
        "RuntimeError: bounded\n",
        encoding="utf-8",
    )
    (result / "task_grade.txt").write_text(
        "attributed_p8_2_k2_r0_run03_fawa_startup_failure\n",
        encoding="utf-8",
    )
    manifest = package(result)
    persisted = json.loads(
        (result / "candidate_manifest.server_local.json").read_text(encoding="utf-8")
    )
    assert persisted == manifest
    assert manifest["payload_file_count"] == 9
    assert manifest["transfer_file_count"] == 10
    assert manifest["transfer_total_bytes"] <= MAX_TRANSFER_BYTES
    assert manifest["automatic_transfer_allowed"] is False


def test_zero_npu_contract_and_server_entry_are_explicit() -> None:
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    audit = yaml.safe_load(AUDIT.read_text(encoding="utf-8"))
    server = SERVER_DRIVER.read_text(encoding="utf-8")
    handoff = HANDOFF.read_text(encoding="utf-8")
    assert workload["task_id"] == TASK_ID
    assert workload["run_id"] == RUN_ID
    assert workload["authorization"]["npu_execution_authorized"] is False
    assert workload["authorization"]["formal_model_lifecycle_count"] == 0
    assert workload["authorization"]["model_request_count"] == 0
    assert workload["authorization"]["keep_alive_action"] == "leave_running"
    assert audit["developer_decision"]["blind_capacity_increase_or_run04_rejected"]
    assert "npu_stop.sh" not in server
    assert "npu_keep_alive.sh" not in server
    assert "keep_alive_action=left_running" in server
    assert "P8_2_K2_R0_RUN03_ATTRIBUTION_AUDIT_ONLY" in server
    assert "K2_R0_RUN03_ATTRIBUTION_REPORT_BEGIN" in server
    assert handoff.count("## 当前唯一服务器动作：") == 1
    assert TASK_ID in handoff
    assert "零 NPU" in handoff
