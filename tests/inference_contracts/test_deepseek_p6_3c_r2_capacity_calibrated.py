from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
from threading import Thread

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = (
    REPO_ROOT / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab.yaml"
)
TOP_RUNNER = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r2_scheduler_pressure.sh"
)
F1_SERVER_TASK = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r2_f1_server_task.sh"
)
F2_SERVER_TASK = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r2_f2_server_task.sh"
)
F3_SERVER_TASK = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r2_f3_server_task.sh"
)
F4_SERVER_TASK = (
    REPO_ROOT / "tools/inference_contracts/run_deepseek_p6_3c_r2_f4_server_task.sh"
)
F1_WORKLOAD = (
    REPO_ROOT / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_f1_runtime_layout_portable_matched_ab.yaml"
)
F2_WORKLOAD = (
    REPO_ROOT / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_f2_loopback_proxy_safe_matched_ab.yaml"
)
F3_WORKLOAD = (
    REPO_ROOT / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_f3_atomic_pair_admission_matched_ab.yaml"
)
F4_WORKLOAD = (
    REPO_ROOT / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_f4_request_id_normalized_atomic_coarrival_matched_ab.yaml"
)
P6_HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.P6.md"


def test_capacity_calibration_keeps_individual_prompts_legal_and_pairs_pressured():
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    frozen = workload["shared_runtime_freeze"]
    assert workload["stage"] == "P6.3C-R2"
    assert frozen["max_model_len"] == 12288
    assert frozen["max_num_batched_tokens"] == 12288
    assert frozen["max_num_seqs"] == 2
    assert workload["shared_hybrid_kv_repair"]["enabled_both_modes_all_lifecycles"]
    cells = workload["cells"]
    assert [cell["simultaneous_prompt_tokens"] for cell in cells] == [
        [4096, 4096],
        [10240, 6144],
        [8192, 8192],
    ]
    assert max(cells[1]["simultaneous_prompt_tokens"]) <= 12288
    assert cells[0]["total_prefill_tokens"] < 12288
    assert cells[1]["total_prefill_tokens"] > 12288
    assert cells[2]["total_prefill_tokens"] > 12288


def test_r2_prepare_reuses_transport_without_mutating_r1_module(tmp_path: Path):
    import tools.inference_contracts.run_deepseek_p6_3c_r1_scheduler_pressure as r1
    import tools.inference_contracts.run_deepseek_p6_3c_r2_scheduler_pressure as r2

    original_task_id = r1.TASK_ID
    original_cells = r1.CELLS
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    result = tmp_path / "result"
    manifest = r2.prepare_artifacts(source, result, "model")
    plan = json.loads((result / "run_plan.json").read_text(encoding="utf-8"))

    assert manifest["task_id"] == r2.TASK_ID
    assert manifest["canonical_batch_body_count"] == 14
    assert plan["mechanism"][2]["prompt_tokens"] == [10240, 6144]
    assert plan["mechanism"][2]["batch_id"].startswith("p6_3c_r2_")
    assert r1.TASK_ID == original_task_id
    assert r1.CELLS == original_cells


def test_runtime_layout_resolver_handles_mixed_editable_and_environment_packages(
    tmp_path: Path,
    monkeypatch,
):
    import tools.inference_contracts.resolve_p6_3c_runtime_layout as resolver

    env_prefix = tmp_path / "env"
    env_bin = env_prefix / "bin"
    site_packages = env_prefix / "lib/python3.11/site-packages"
    editable_root = tmp_path / "editable"
    (editable_root / "vllm").mkdir(parents=True)
    (site_packages / "vllm_ascend").mkdir(parents=True)
    (editable_root / "vllm/__init__.py").write_text("", encoding="utf-8")
    (site_packages / "vllm_ascend/__init__.py").write_text("", encoding="utf-8")
    env_bin.mkdir(parents=True)
    python_bin = env_bin / "python"
    vllm_bin = env_bin / "vllm"
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    vllm_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    python_bin.chmod(0o755)
    vllm_bin.chmod(0o755)
    monkeypatch.syspath_prepend(str(site_packages))
    monkeypatch.syspath_prepend(str(editable_root))
    monkeypatch.setattr(resolver.sys, "executable", str(python_bin))
    monkeypatch.setattr(resolver.sys, "prefix", str(env_prefix))

    layout = resolver.resolve_runtime_layout(env_prefix)

    assert layout["packages"]["vllm"]["source_kind"] == "editable_external"
    assert layout["packages"]["vllm_ascend"]["source_kind"] == "environment_owned"
    assert layout["base_vllm_root"] == str((editable_root / "vllm").resolve())
    assert layout["base_plugin_root"] == str((site_packages / "vllm_ascend").resolve())


def test_overlay_materialization_rejects_symlink_preservation(tmp_path: Path):
    from tools.inference_contracts.prepare_p6_3c_runtime_overlay import (
        _assert_materialized_tree,
    )

    source = tmp_path / "source/vllm_ascend"
    source.mkdir(parents=True)
    (source / "target.py").write_text("value = 1\n", encoding="utf-8")
    (source / "linked.py").symlink_to(source / "target.py")
    overlay_root = tmp_path / "runtime/overlay_root"
    overlay_root.mkdir(parents=True)
    overlay_package = overlay_root / "vllm_ascend"
    shutil.copytree(source, overlay_package, symlinks=False)

    evidence = _assert_materialized_tree(overlay_root, overlay_package)

    assert evidence["symlink_count"] == 0
    assert evidence["realpath_escape_count"] == 0
    assert (overlay_package / "linked.py").is_file()
    assert not (overlay_package / "linked.py").is_symlink()


def test_overlay_builder_validates_task_local_admission_module_name():
    from tools.inference_contracts.prepare_p6_3c_runtime_overlay import (
        validated_python_module_name,
    )

    assert (
        validated_python_module_name("p6_3c_r2_f4_atomic_pair_admission")
        == "p6_3c_r2_f4_atomic_pair_admission"
    )
    with pytest.raises(ValueError):
        validated_python_module_name("../escape")
    with pytest.raises(ValueError):
        validated_python_module_name("module.py")


def test_empty_mechanism_trace_is_not_reported_as_negative_evidence(
    tmp_path: Path,
):
    import tools.inference_contracts.run_deepseek_p6_3c_r1_scheduler_pressure as r1
    import tools.inference_contracts.run_deepseek_p6_3c_r2_scheduler_pressure as r2

    mechanism, request_rows = r2._mechanism_evidence(
        tmp_path,
        list(r1.LIFECYCLE_SCHEDULE),
        r2.build_run_plan(),
    )

    assert request_rows == []
    assert mechanism["scheduler_evidence_complete"] is False
    assert mechanism["off_prefill_partial_absent_all_cells"] is None
    assert mechanism["on_prefill_partial_present_both_pressure_cells"] is None
    assert mechanism["low_pressure_partial_absent_both_modes"] is None
    assert mechanism["mechanism_gate_complete"] is False


def test_unrun_lifecycles_do_not_turn_clean_resource_recovery_red(
    tmp_path: Path,
):
    import tools.inference_contracts.run_deepseek_p6_3c_r2_scheduler_pressure as r2

    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    result = tmp_path / "result"
    r2.prepare_artifacts(source, result, "model")
    (result / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    (result / "resource_recovery_summary.json").write_text(
        json.dumps(
            {
                "keep_alive_restored_exact": True,
                "port_7000_listener_count": 0,
                "vllm_residual_process_count": 0,
                "tracked_worktree_clean": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    grading = r2.finalize_artifacts(result)
    lifecycle_rows = (result / "lifecycle_summary.tsv").read_text(encoding="utf-8")

    assert grading["server_grade"] == ("red_p6_3c_r2_scheduler_pressure_no_success")
    assert grading["cleanup_failure"] is False
    assert grading["body_pairing_observed"] is False
    assert grading["body_pairing_exact"] is None
    assert "\tnot_run\tnot_run\n" in lifecycle_rows
    assert (result / "cleanup_status.txt").read_text(encoding="utf-8") == "clean\n"


def test_startup_parser_returns_bounded_kv_capacity_failure():
    from tools.inference_contracts.p6_3c_startup_resource_summary import (
        bounded_failure_excerpt,
        summarize_startup_log,
    )

    text = """
Loading model weights took 41.65 GB
Available KV cache memory: 8.27 GiB
ValueError: To serve at least one request with the model's max seq len (69632),
36.66 GiB KV cache is needed, which is larger than the available KV cache memory.
Based on the available memory, the estimated maximum model length is 15672.
RuntimeError: Engine core initialization failed (ERR99999).
"""
    summary = summarize_startup_log(
        text,
        expected_max_model_len=69632,
        expected_max_num_batched_tokens=69632,
        expected_max_num_seqs=2,
        server_ready_exit_code=1,
    )
    assert summary["startup_failure_class"] == "insufficient_kv_cache_capacity"
    assert summary["available_kv_cache_gib"] == 8.27
    assert summary["required_kv_cache_gib"] == 36.66
    assert summary["estimated_max_model_len"] == 15672
    assert len(bounded_failure_excerpt(text)) <= 8192


def test_r2_audit_freezes_shared_capacity_and_one_flag_hashes():
    completed = subprocess.run(
        ["bash", str(TOP_RUNNER), "/audit/p6_3c_r2"],
        cwd=REPO_ROOT,
        env={**os.environ, "P6_3C_AUDIT_ONLY": "1", "PYTHON_BIN": "python"},
        check=True,
        capture_output=True,
        text=True,
    )
    output = completed.stdout
    assert "capacity_contract=max_model_len_12288" in output
    assert "shared_hybrid_kv_repair=enabled_both_modes_all_lifecycles" in output
    assert output.count("max_model_len=12288") == 6
    assert output.count("shared_hybrid_kv_repair=1") == 6
    assert (
        output.count(
            "server_argv_sha256="
            "568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10"
        )
        == 3
    )
    assert (
        output.count(
            "server_argv_sha256="
            "cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017"
        )
        == 3
    )


def test_r2_f1_server_audit_preserves_science_contract_and_new_lineage():
    result_dir = (
        "/audit/p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01"
    )
    completed = subprocess.run(
        ["bash", str(F1_SERVER_TASK), result_dir],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHON_BIN": "python",
            "P6_3C_SERVER_TASK_AUDIT_ONLY": "1",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    output = completed.stdout
    assert (
        "task_id=p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_2026_0729_run01"
    ) in output
    assert "experiment_label=P6_3C_R2_F1" in output
    assert output.count("max_model_len=12288") == 6
    assert (
        output.count(
            "server_argv_sha256="
            "568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10"
        )
        == 3
    )
    assert (
        output.count(
            "server_argv_sha256="
            "cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017"
        )
        == 3
    )


def test_r2_f2_inherits_science_contract_and_only_repairs_local_transport():
    f1 = yaml.safe_load(F1_WORKLOAD.read_text(encoding="utf-8"))
    f2 = yaml.safe_load(F2_WORKLOAD.read_text(encoding="utf-8"))

    assert f2["stage"] == "P6.3C-R2-F2"
    assert f2["scientific_contract"]["changed"] is False
    for key in (
        "max_model_len",
        "max_num_batched_tokens",
        "max_num_seqs",
        "prefix_cache_enabled",
        "shared_hybrid_kv_repair_both_modes",
        "only_ab_difference",
        "cells",
        "lifecycle_order",
        "exact_totals",
    ):
        assert f2["scientific_contract"][key] == f1["scientific_contract"][key]
    transport = f2["loopback_transport_repair"]
    assert transport["base_url"] == "http://127.0.0.1:7000"
    assert transport["non_loopback_host_allowed"] is False
    assert transport["shell"]["curl_noproxy_all"] is True
    assert transport["shell"]["curl_empty_proxy"] is True
    assert transport["python"]["proxy_handler"] == "empty"
    assert transport["python"]["environment_proxy_lookup_allowed"] is False


def test_python_loopback_transport_ignores_broken_environment_proxy(
    monkeypatch,
):
    from tools.inference_contracts.p6_3c_local_http_transport import (
        open_loopback,
        transport_contract,
        validate_loopback_url,
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"direct-loopback")

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost,::1")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost,::1")
    try:
        with open_loopback(base_url + "/health", timeout=2) as response:
            assert response.status == 200
            assert response.read() == b"direct-loopback"
        contract = transport_contract(base_url)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert contract["python_proxy_handler"] == "empty"
    assert contract["python_environment_proxy_lookup_allowed"] is False
    assert contract["environment_proxy_values_recorded"] is False
    assert contract["NO_PROXY_loopback_entries_complete"] is True
    assert contract["no_proxy_loopback_entries_complete"] is True
    with pytest.raises(ValueError):
        validate_loopback_url("http://example.com:7000")


def test_r2_f2_audit_freezes_proxy_safe_transport_and_science_contract():
    result_dir = (
        "/audit/p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01"
    )
    completed = subprocess.run(
        ["bash", str(F2_SERVER_TASK), result_dir],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHON_BIN": "python",
            "P6_3C_SERVER_TASK_AUDIT_ONLY": "1",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    output = completed.stdout
    assert (
        "task_id=p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_2026_0730_run01"
    ) in output
    assert "experiment_label=P6_3C_R2_F2" in output
    assert output.count("max_model_len=12288") == 6
    assert output.count("shell_local_http_proxy=explicitly_disabled") == 6
    assert output.count("python_local_http_proxy_handler=empty") == 6
    assert (
        output.count(
            "server_argv_sha256="
            "568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10"
        )
        == 3
    )
    assert (
        output.count(
            "server_argv_sha256="
            "cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017"
        )
        == 3
    )


def test_r2_f3_contract_adds_common_atomic_admission_without_changing_ab():
    workload = yaml.safe_load(F3_WORKLOAD.read_text(encoding="utf-8"))
    frozen = workload["scientific_contract"]["jointly_frozen_both_modes"]
    assert workload["stage"] == "P6.3C-R2-F3"
    assert frozen["max_model_len"] == 12288
    assert frozen["max_num_batched_tokens"] == 12288
    assert frozen["max_num_seqs"] == 2
    assert frozen["atomic_pair_admission"] is True
    assert workload["scientific_contract"]["only_ab_difference"] == {
        "off": "--no-enable-chunked-prefill",
        "on": "--enable-chunked-prefill",
    }
    assert (
        workload["scientific_contract"]["exact_totals"]["tagged_measured_pairs"] == 42
    )
    assert workload["atomic_pair_admission"]["request_scope"] == (
        "tagged_p6_3c_r2_f3_measured_pairs_only"
    )
    assert workload["atomic_pair_admission"]["scheduler_semantics_mutated"] is False


def test_r2_f3_prepare_tags_only_measured_pairs(tmp_path: Path):
    import tools.inference_contracts.run_deepseek_p6_3c_r2_f3_atomic_pair_admission as f3

    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    result = tmp_path / "result"
    manifest = f3.prepare_artifacts(source, result, "model")
    plan = json.loads((result / "run_plan.json").read_text(encoding="utf-8"))

    assert manifest["task_id"] == f3.TASK_ID
    assert plan["mechanism"][0]["batch_id"] == ("p6_3c_r2_f3_mechanism_warmup")
    assert plan["mechanism"][1]["batch_id"].startswith("p6_3c_r2_f3_mechanism_")
    assert plan["performance"][1]["batch_id"].startswith("p6_3c_r2_f3_performance_")


def test_r2_f3_audit_freezes_atomic_pair_and_existing_server_argv():
    result_dir = (
        "/audit/p6_3c_r2_f3_chunked_prefill_atomic_pair_admission_2026_0730_run01"
    )
    completed = subprocess.run(
        ["bash", str(F3_SERVER_TASK), result_dir],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHON_BIN": "python",
            "P6_3C_SERVER_TASK_AUDIT_ONLY": "1",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    output = completed.stdout
    assert "atomic_pair_admission=1" in output
    assert "tagged_measured_pair_count_exact=42" in output
    assert output.count("atomic_pair_request_prefix=p6_3c_r2_f3") == 7
    assert output.count("atomic_pair_timeout_seconds=30") == 7
    assert (
        output.count(
            "server_argv_sha256="
            "568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10"
        )
        == 3
    )
    assert (
        output.count(
            "server_argv_sha256="
            "cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017"
        )
        == 3
    )


def test_r2_f3_requires_exact_release_and_same_first_scheduler_step(
    tmp_path: Path,
):
    import tools.inference_contracts.run_deepseek_p6_3c_r2_f3_atomic_pair_admission as f3

    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    artifact = tmp_path / "result"
    f3.prepare_artifacts(source, artifact, "model")
    plan = json.loads((artifact / "run_plan.json").read_text(encoding="utf-8"))

    for lifecycle in f3.r2.base.LIFECYCLE_SCHEDULE:
        runtime = artifact / "lifecycles" / lifecycle["lifecycle_id"] / "runtime"
        atomic_dir = runtime / "atomic_pair_trace"
        atomic_dir.mkdir(parents=True)
        measured = [
            batch for batch in plan[lifecycle["track"]] if batch["phase"] == "measured"
        ]
        atomic_rows = [{"event": "atomic_pair_admission_installed"}]
        for batch in measured:
            atomic_rows.append(
                {
                    "event": "pair_complete_released",
                    "request_ids": [
                        f"cmpl-{batch['request_id']}-0",
                        f"cmpl-{batch['request_id']}-1",
                    ],
                    "pair_indices": [0, 1],
                    "prompt_tokens": batch["prompt_tokens"],
                    "member_buffer_wait_ns": [1_000_000, 100_000],
                    "release_order": (
                        "pair_index_ascending_before_next_scheduler_step"
                    ),
                }
            )
        atomic_rows.append(
            {
                "event": "atomic_pair_admission_shutdown_state",
                "pending_pair_count": 0,
                "failed_pair_count": 0,
                "completed_pair_count": len(measured),
            }
        )
        (atomic_dir / "trace.1.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in atomic_rows),
            encoding="utf-8",
        )

        if lifecycle["track"] != "mechanism":
            continue
        scheduler_dir = runtime / "scheduler_trace"
        scheduler_dir.mkdir()
        scheduler_rows = []
        for index, batch in enumerate(measured, start=1):
            ids = [
                f"cmpl-{batch['request_id']}-0",
                f"cmpl-{batch['request_id']}-1",
            ]
            prompt_0, prompt_1 = batch["prompt_tokens"]
            if not batch["pressure"]:
                amounts = [prompt_0, prompt_1]
            elif lifecycle["mode"] == "chunked_prefill_off":
                amounts = [prompt_0, 0]
            else:
                amounts = [prompt_0, 12288 - prompt_0]
            scheduler_rows.append(
                {
                    "event": "scheduler_step",
                    "step_index": index,
                    "waiting_order_before": ids,
                    "total_num_scheduled_tokens": sum(amounts),
                    "scheduled_requests": [
                        {
                            "request_id": request_id,
                            "scheduled_tokens": amount,
                        }
                        for request_id, amount in zip(ids, amounts, strict=True)
                        if amount
                    ],
                }
            )
        (scheduler_dir / "trace.1.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in scheduler_rows),
            encoding="utf-8",
        )

    releases, _ = f3._release_table_and_gate(artifact, plan)
    first_steps, rows = f3._first_step_table_and_gate(artifact, plan)

    assert releases["expected_pair_release_count"] == 42
    assert releases["exact_pair_release_count"] == 42
    assert releases["atomic_pair_release_gate_complete"] is True
    assert first_steps["mechanism_cell_count"] == 6
    assert first_steps["mechanism_atomic_coarrival_gate_complete"] is True

    trace_path = (
        artifact / "lifecycles/mechanism_01/runtime/scheduler_trace/trace.1.jsonl"
    )
    corrupted = [
        json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    corrupted[0]["waiting_order_before"] = corrupted[0]["waiting_order_before"][:1]
    trace_path.write_text(
        "".join(json.dumps(row) + "\n" for row in corrupted),
        encoding="utf-8",
    )
    failed_gate, _ = f3._first_step_table_and_gate(artifact, plan)
    assert failed_gate["mechanism_atomic_coarrival_gate_complete"] is False


def test_r2_f4_normalizes_observed_vllm_request_ids(monkeypatch):
    from tools.inference_contracts.p6_3c_r2_f4_atomic_pair_admission import (
        normalize_atomic_pair_request_id,
    )

    monkeypatch.setenv(
        "P6_3C_ATOMIC_PAIR_REQUEST_PREFIX",
        "p6_3c_r2_f4",
    )
    observed = normalize_atomic_pair_request_id(
        "cmpl-p6_3c_r2_f4_mechanism_no_pressure_4k_4k_r01-0-a19f074f"
    )

    assert observed is not None
    assert observed.actual_request_id.endswith("-0-a19f074f")
    assert observed.canonical_request_id.endswith("_r01-0")
    assert observed.pair_key.endswith("_r01")
    assert observed.pair_index == 0
    assert observed.runtime_suffix == "a19f074f"
    assert (
        normalize_atomic_pair_request_id(
            "cmpl-p6_3c_r2_f4_mechanism_no_pressure_4k_4k_r01-1-NOTHEX00"
        )
        is None
    )
    assert (
        normalize_atomic_pair_request_id(
            "cmpl-p6_3c_r2_f3_mechanism_no_pressure_4k_4k_r01-1-94c2f491"
        )
        is None
    )


def test_r2_f4_contract_changes_only_common_request_id_control_plane():
    f3_workload = yaml.safe_load(F3_WORKLOAD.read_text(encoding="utf-8"))
    f4_workload = yaml.safe_load(F4_WORKLOAD.read_text(encoding="utf-8"))

    assert f4_workload["stage"] == "P6.3C-R2-F4"
    assert f4_workload["parent_run"]["reported_grade"] == (
        "red_p6_3c_r2_f3_atomic_pair_admission_evidence_incomplete"
    )
    f3_frozen = f3_workload["scientific_contract"]["jointly_frozen_both_modes"]
    f4_frozen = f4_workload["scientific_contract"]["jointly_frozen_both_modes"]
    for key, value in f3_frozen.items():
        if key == "atomic_pair_request_prefix":
            assert f4_frozen[key] == "p6_3c_r2_f4"
        else:
            assert f4_frozen[key] == value
    assert (
        f4_workload["scientific_contract"]["only_ab_difference"]
        == f3_workload["scientific_contract"]["only_ab_difference"]
    )
    assert (
        f4_workload["scientific_contract"]["cells"]
        == f3_workload["scientific_contract"]["cells"]
    )
    assert (
        f4_workload["scientific_contract"]["lifecycle_order"]
        == f3_workload["scientific_contract"]["lifecycle_order"]
    )
    assert (
        f4_workload["scientific_contract"]["exact_totals"]
        == f3_workload["scientific_contract"]["exact_totals"]
    )
    assert f4_workload["request_id_normalization"]["actual_id_pattern"] == (
        "cmpl-<canonical_pair_key>-<pair_index:0|1>-<runtime_suffix:8hex>"
    )
    assert (
        f4_workload["request_id_normalization"]["release_and_scheduler_shared"] is True
    )


def test_r2_f4_audit_freezes_real_id_fixture_and_existing_server_argv():
    result_dir = (
        "/audit/p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01"
    )
    completed = subprocess.run(
        ["bash", str(F4_SERVER_TASK), result_dir],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHON_BIN": "python",
            "P6_3C_SERVER_TASK_AUDIT_ONLY": "1",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    output = completed.stdout
    assert ("request_id_fixture_gate=observed_8hex_suffix_normalized_strict") in output
    assert (
        "task_id=p6_3c_r2_f4_request_id_normalized_atomic_coarrival_2026_0731_run01"
    ) in output
    assert "experiment_label=P6_3C_R2_F4" in output
    assert "atomic_pair_admission=1" in output
    assert "tagged_measured_pair_count_exact=42" in output
    assert (
        output.count("atomic_pair_admission_module=p6_3c_r2_f4_atomic_pair_admission")
        == 6
    )
    assert output.count("atomic_pair_request_prefix=p6_3c_r2_f4") == 7
    assert (
        output.count(
            "server_argv_sha256="
            "568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10"
        )
        == 3
    )
    assert (
        output.count(
            "server_argv_sha256="
            "cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017"
        )
        == 3
    )


def test_r2_f4_controller_releases_actual_ids_and_persists_canonical_state(
    tmp_path: Path,
    monkeypatch,
):
    from tools.inference_contracts.p6_3c_r2_f4_atomic_pair_admission import (
        AtomicPairController,
    )

    monkeypatch.setenv("P6_3C_ATOMIC_PAIR_REQUEST_PREFIX", "p6_3c_r2_f4")
    monkeypatch.setenv(
        "P6_3C_ATOMIC_PAIR_TRACE_DIR",
        str(tmp_path / "trace"),
    )

    class Engine:
        pass

    class Request:
        def __init__(self, request_id: str, prompt_tokens: int):
            self.request_id = request_id
            self.num_prompt_tokens = prompt_tokens

    engine = Engine()
    added: list[str] = []
    aborted: list[str] = []

    def original_add(_engine, request, _wave):
        added.append(request.request_id)

    def original_abort(_engine, request_ids):
        aborted.extend(request_ids)

    controller = AtomicPairController(
        engine,
        original_add,
        original_abort,
        "WAKEUP",
    )
    member_0 = Request(
        "cmpl-p6_3c_r2_f4_mechanism_no_pressure_4k_4k_r01-0-a19f074f",
        4096,
    )
    member_1 = Request(
        "cmpl-p6_3c_r2_f4_mechanism_no_pressure_4k_4k_r01-1-94c2f491",
        4096,
    )

    controller.add(member_0, 0)
    assert added == []
    controller.add(member_1, 0)
    controller.shutdown()

    assert added == [member_0.request_id, member_1.request_id]
    assert aborted == []
    trace_rows = [
        json.loads(line)
        for path in (tmp_path / "trace").glob("trace.*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    release = next(
        row for row in trace_rows if row["event"] == "pair_complete_released"
    )
    assert release["actual_request_ids"] == added
    assert release["canonical_request_ids"] == [
        member_0.request_id.rsplit("-", 1)[0],
        member_1.request_id.rsplit("-", 1)[0],
    ]
    checkpoint = next(
        row
        for row in reversed(trace_rows)
        if row["event"] == "atomic_pair_admission_state_checkpoint"
    )
    assert checkpoint["reason"] == "shutdown"
    assert checkpoint["pending_pair_count"] == 0
    assert checkpoint["failed_pair_count"] == 0
    assert checkpoint["completed_pair_count"] == 1


def test_r2_f4_controller_passes_singleton_warmup_without_pair_wait(
    monkeypatch,
):
    from tools.inference_contracts.p6_3c_r2_f4_atomic_pair_admission import (
        AtomicPairController,
    )

    monkeypatch.setenv("P6_3C_ATOMIC_PAIR_REQUEST_PREFIX", "p6_3c_r2_f4")

    class Engine:
        pass

    class Request:
        request_id = "cmpl-p6_3c_r2_f4_mechanism_warmup-0-a19f074f"
        num_prompt_tokens = 4096

    engine = Engine()
    added: list[str] = []

    def original_add(_engine, request, _wave):
        added.append(request.request_id)

    controller = AtomicPairController(
        engine,
        original_add,
        lambda _engine, request_ids: request_ids,
        "WAKEUP",
    )

    controller.add(Request(), 0)

    assert added == [Request.request_id]
    assert controller._pending == {}
    assert controller._completed_pair_count == 0


def test_r2_runtime_layout_uses_enabled_capability_instead_of_task_name(
    tmp_path: Path,
    monkeypatch,
):
    import tools.inference_contracts.run_deepseek_p6_3c_r2_scheduler_pressure as r2

    (tmp_path / "runtime_layout.json").write_text(
        json.dumps(
            {
                "resolution_method": (
                    "target_environment_importlib_find_spec_then_realpath"
                ),
                "base_vllm_root": "/runtime/vllm",
                "base_plugin_root": "/runtime/vllm_ascend",
                "source_files_mutated": False,
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "copy_semantics": ("materialized_copy_dereference_symlinks_no_ownership"),
        "symlink_count": 0,
        "realpath_escape_count": 0,
        "shared_hybrid_kv_repair": True,
        "atomic_pair_admission": True,
        "observer": True,
        "base_environment_mutated": False,
        "site_packages_mutated": False,
    }
    (tmp_path / "runtime_overlay_preflight_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    for lifecycle in r2.base.LIFECYCLE_SCHEDULE:
        runtime = tmp_path / "lifecycles" / lifecycle["lifecycle_id"] / "runtime"
        runtime.mkdir(parents=True)
        lifecycle_manifest = {
            **manifest,
            "observer": lifecycle["track"] == "mechanism",
        }
        (runtime / "runtime_overlay_manifest.json").write_text(
            json.dumps(lifecycle_manifest),
            encoding="utf-8",
        )

    monkeypatch.setenv("P6_3C_ATOMIC_PAIR_ADMISSION", "1")
    evidence = r2._runtime_layout_evidence(tmp_path)

    assert evidence["atomic_pair_admission_overlay_expected"] is True
    assert evidence["runtime_overlay_preflight_complete"] is True
    assert evidence["runtime_overlay_lifecycles_exact"] is True
    assert evidence["runtime_layout_gate_complete"] is True


def test_r2_f4_analyzer_normalizes_release_and_scheduler_ids_with_checkpoint_fallback(
    tmp_path: Path,
):
    import tools.inference_contracts.run_deepseek_p6_3c_r2_f4_atomic_pair_admission as f4

    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    artifact = tmp_path / "result"
    f4.prepare_artifacts(source, artifact, "model")
    plan = json.loads((artifact / "run_plan.json").read_text(encoding="utf-8"))

    for lifecycle in f4.r2.base.LIFECYCLE_SCHEDULE:
        runtime = artifact / "lifecycles" / lifecycle["lifecycle_id"] / "runtime"
        atomic_dir = runtime / "atomic_pair_trace"
        atomic_dir.mkdir(parents=True)
        measured = [
            batch for batch in plan[lifecycle["track"]] if batch["phase"] == "measured"
        ]
        atomic_rows = [{"event": "atomic_pair_admission_installed"}]
        for completed_count, batch in enumerate(measured, start=1):
            canonical = [
                f"cmpl-{batch['request_id']}-0",
                f"cmpl-{batch['request_id']}-1",
            ]
            actual = [
                canonical[0] + "-a19f074f",
                canonical[1] + "-94c2f491",
            ]
            atomic_rows.extend(
                [
                    {
                        "event": "pair_complete_released",
                        "pair_key": canonical[0].rsplit("-", 1)[0],
                        "actual_request_ids": actual,
                        "canonical_request_ids": canonical,
                        "runtime_suffixes": ["a19f074f", "94c2f491"],
                        "pair_indices": [0, 1],
                        "prompt_tokens": batch["prompt_tokens"],
                        "member_buffer_wait_ns": [1_000_000, 100_000],
                        "completed_pair_count": completed_count,
                        "release_order": (
                            "pair_index_ascending_before_next_scheduler_step"
                        ),
                    },
                    {
                        "event": "atomic_pair_admission_state_checkpoint",
                        "reason": "pair_complete_released",
                        "pending_pair_count": 0,
                        "failed_pair_count": 0,
                        "completed_pair_count": completed_count,
                    },
                ]
            )
        (atomic_dir / "trace.1.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in atomic_rows),
            encoding="utf-8",
        )

        if lifecycle["track"] != "mechanism":
            continue
        scheduler_dir = runtime / "scheduler_trace"
        scheduler_dir.mkdir()
        scheduler_rows = []
        for index, batch in enumerate(measured, start=1):
            canonical = [
                f"cmpl-{batch['request_id']}-0",
                f"cmpl-{batch['request_id']}-1",
            ]
            actual = [
                canonical[0] + "-a19f074f",
                canonical[1] + "-94c2f491",
            ]
            prompt_0, prompt_1 = batch["prompt_tokens"]
            if not batch["pressure"]:
                amounts = [prompt_0, prompt_1]
            elif lifecycle["mode"] == "chunked_prefill_off":
                amounts = [prompt_0, 0]
            else:
                amounts = [prompt_0, 12288 - prompt_0]
            scheduler_rows.append(
                {
                    "event": "scheduler_step",
                    "step_index": index,
                    "waiting_order_before": actual,
                    "total_num_scheduled_tokens": sum(amounts),
                    "scheduled_requests": [
                        {
                            "request_id": request_id,
                            "scheduled_tokens": amount,
                        }
                        for request_id, amount in zip(
                            actual,
                            amounts,
                            strict=True,
                        )
                        if amount
                    ],
                }
            )
        (scheduler_dir / "trace.1.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in scheduler_rows),
            encoding="utf-8",
        )

    releases, release_rows = f4._release_table_and_gate(artifact, plan)
    first_steps, first_step_rows = f4._first_step_table_and_gate(artifact, plan)

    assert releases["exact_pair_release_count"] == 42
    assert releases["shutdown_state_observed_count"] == 0
    assert releases["checkpoint_terminal_state_used_count"] == 6
    assert releases["atomic_pair_release_gate_complete"] is True
    assert all(row["actual_id_contract_exact"] for row in release_rows)
    assert first_steps["first_scheduler_step_contract_exact_count"] == 6
    assert first_steps["mechanism_atomic_coarrival_gate_complete"] is True
    assert all(row["actual_id_contract_exact"] for row in first_step_rows)

    atomic_path = (
        artifact / "lifecycles/mechanism_01/runtime/atomic_pair_trace/trace.1.jsonl"
    )
    corrupted_atomic = [
        json.loads(line)
        for line in atomic_path.read_text(encoding="utf-8").splitlines()
    ]
    first_release = next(
        row for row in corrupted_atomic if row["event"] == "pair_complete_released"
    )
    first_release["actual_request_ids"][0] = (
        first_release["canonical_request_ids"][0] + "-NOTHEX00"
    )
    atomic_path.write_text(
        "".join(json.dumps(row) + "\n" for row in corrupted_atomic),
        encoding="utf-8",
    )
    failed_releases, _ = f4._release_table_and_gate(artifact, plan)
    assert failed_releases["atomic_pair_release_gate_complete"] is False

    scheduler_path = (
        artifact / "lifecycles/mechanism_01/runtime/scheduler_trace/trace.1.jsonl"
    )
    corrupted_scheduler = [
        json.loads(line)
        for line in scheduler_path.read_text(encoding="utf-8").splitlines()
    ]
    corrupted_scheduler[0]["waiting_order_before"][0] = (
        corrupted_scheduler[0]["waiting_order_before"][0].rsplit("-", 1)[0]
        + "-NOTHEX00"
    )
    scheduler_path.write_text(
        "".join(json.dumps(row) + "\n" for row in corrupted_scheduler),
        encoding="utf-8",
    )
    failed_first_steps, _ = f4._first_step_table_and_gate(artifact, plan)
    assert failed_first_steps["mechanism_atomic_coarrival_gate_complete"] is False


def test_r2_f4_finalizer_maps_complete_normalized_evidence_to_f4_candidate(
    tmp_path: Path,
    monkeypatch,
):
    import tools.inference_contracts.run_deepseek_p6_3c_r2_f4_atomic_pair_admission as f4

    artifact = tmp_path / "result"
    artifact.mkdir()
    atomic = {
        "atomic_pair_release_gate_complete": True,
        "mechanism_atomic_coarrival_gate_complete": True,
        "coarrival_gate_complete": True,
        "exact_pair_release_count": 42,
        "expected_pair_release_count": 42,
        "first_scheduler_step_contract_exact_count": 6,
        "all_lifecycle_terminal_states_clean": True,
        "shutdown_state_observed_count": 5,
        "checkpoint_terminal_state_used_count": 1,
    }
    (artifact / "atomic_pair_admission_summary.json").write_text(
        json.dumps(atomic),
        encoding="utf-8",
    )
    (artifact / "atomic_pair_release_summary.tsv").write_text(
        "actual_id_contract_exact\n" + "".join("True\n" for _ in range(42)),
        encoding="utf-8",
    )
    (artifact / "mechanism_atomic_pair_first_step.tsv").write_text(
        "actual_id_contract_exact\n" + "".join("True\n" for _ in range(6)),
        encoding="utf-8",
    )
    (artifact / "mechanism_scheduler_summary.json").write_text(
        json.dumps(
            {
                "mechanism_gate_complete": True,
                "atomic_pair_admission": {},
                "off_prefill_partial_absent_all_cells": True,
                "on_prefill_partial_present_both_pressure_cells": True,
                "low_pressure_partial_absent_both_modes": True,
            }
        ),
        encoding="utf-8",
    )
    (artifact / "environment_and_hashes.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    overlay_manifest = json.dumps(
        {"atomic_pair_admission_module": ("p6_3c_r2_f4_atomic_pair_admission")}
    )
    (artifact / "runtime_overlay_preflight_manifest.json").write_text(
        overlay_manifest,
        encoding="utf-8",
    )
    for lifecycle in f4.r2.base.LIFECYCLE_SCHEDULE:
        runtime = artifact / "lifecycles" / lifecycle["lifecycle_id"] / "runtime"
        runtime.mkdir(parents=True)
        (runtime / "runtime_overlay_manifest.json").write_text(
            overlay_manifest,
            encoding="utf-8",
        )

    def fake_f3_finalize(_artifact: Path):
        return {
            "server_grade": (
                "candidate_green_p6_3c_r2_chunked_prefill_"
                "capacity_calibrated_matched_ab"
            ),
            "all_lifecycles_success": True,
            "successful_request_count": 90,
            "successful_batch_count": 48,
            "startup_resource_gate_complete": True,
            "shared_hybrid_kv_repair_exact_all_lifecycles": True,
            "runtime_layout_gate_complete": True,
            "loopback_transport_gate_complete": True,
            "atomic_pair_admission_resolved_all_lifecycles": True,
            "keep_alive_restore_exact": True,
        }

    monkeypatch.setattr(f4.f3, "finalize_artifacts", fake_f3_finalize)

    grading = f4.finalize_artifacts(artifact)

    assert grading["server_grade"] == (
        "candidate_green_p6_3c_r2_f4_chunked_prefill_"
        "request_id_normalized_atomic_coarrival_matched_ab"
    )
    assert grading["request_id_normalization_gate_complete"] is True
    assert grading["f4_runtime_and_transport_gates_complete"] is True
    assert grading["f4_overlay_module_gate_complete"] is True
    assert grading["parent_p6_3c_r2_f3_overwritten"] is False
    assert (artifact / "first_failure_excerpt.txt").read_text(
        encoding="utf-8"
    ) == "none\n"


def test_r2_f4_adaptive_review_accepts_complete_server_evidence(tmp_path: Path):
    from tools.inference_contracts.review_deepseek_p6_3c_r2_f4_adaptive_run import (
        EXPECTED_EXECUTED_CONTROLLER_SHA256,
        EXPECTED_SOURCE_RUNNER_SHA256,
        EXPECTED_SOURCE_WORKLOAD_SHA256,
        SOURCE_TASK_ID,
        validate_source_result,
    )

    (tmp_path / "environment_and_hashes.json").write_text(
        json.dumps(
            {
                "task_id": SOURCE_TASK_ID,
                "f4_atomic_pair_admission_sha256": (
                    EXPECTED_EXECUTED_CONTROLLER_SHA256
                ),
                "f4_runner_sha256": EXPECTED_SOURCE_RUNNER_SHA256,
                "workload_sha256": EXPECTED_SOURCE_WORKLOAD_SHA256,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "grading_inputs.json").write_text(
        json.dumps(
            {
                "task_id": SOURCE_TASK_ID,
                "server_grade": (
                    "red_p6_3c_r2_f4_chunked_prefill_mechanism_evidence_incomplete"
                ),
                "all_lifecycles_success": True,
                "successful_request_count": 90,
                "successful_batch_count": 48,
                "request_id_normalization_gate_complete": True,
                "coarrival_gate_complete": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "atomic_pair_admission_summary.json").write_text(
        json.dumps(
            {
                "exact_pair_release_count": 42,
                "atomic_pair_release_gate_complete": True,
                "all_lifecycle_terminal_states_clean": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "mechanism_scheduler_summary.json").write_text(
        json.dumps({"mechanism_gate_complete": True}),
        encoding="utf-8",
    )
    (tmp_path / "resource_recovery_summary.json").write_text(
        json.dumps(
            {
                "keep_alive_restored_exact": True,
                "port_7000_listener_count": 0,
                "vllm_residual_process_count": 0,
                "tracked_worktree_clean": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "result_summary.md").write_text("complete\n", encoding="utf-8")

    review = validate_source_result(tmp_path)

    assert review["source_task_id"] == SOURCE_TASK_ID
    assert all(review["checks"].values())


def test_p6_handoff_tracks_current_r3d_persistent_prefill_task():
    text = P6_HANDOFF.read_text(encoding="utf-8")
    assert "p6_3c_r3d_persistent_prefill_pressure_2026_0807_run01" in text
    assert "p6_3c_r3c_adaptive_budget_2026_0805_run01" in text
    assert "docs/SERVER_ADAPTIVE_EXECUTION_POLICY.md" in text
    assert "max_model_len=12288" in text
    assert "max_num_seqs=9" in text
    assert "persistent_on_t128" in text
    assert "persistent_on_t1024" in text
    assert "full_prefill_sequence_gate_complete" in text
    assert "running_unfinished_prefill_count" in text
    assert "17 fresh-model lifecycle" in text
    assert "1286 EngineCore request" in text
    assert "243 local HTTP request" in text
    assert "npu_stop.sh 0 1 2 3 4 5 6 7" in text
    assert "npu_keep_alive.sh 0 1 2 3 4 5 6 7" in text
    assert "服务器 AI 有权并有责任" in text
    assert "不自动进入 R3E/P7/P8/P9" in text
    assert "candidate_total_bytes" in text
    assert "transfer_method_selected=false" in text
