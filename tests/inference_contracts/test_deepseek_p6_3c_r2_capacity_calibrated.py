from __future__ import annotations

import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import shutil
import subprocess
from threading import Thread

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab.yaml"
)
TOP_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p6_3c_r2_scheduler_pressure.sh"
)
F1_SERVER_TASK = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p6_3c_r2_f1_server_task.sh"
)
F2_SERVER_TASK = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p6_3c_r2_f2_server_task.sh"
)
F1_WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_f1_runtime_layout_portable_matched_ab.yaml"
)
F2_WORKLOAD = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/workloads/"
    "p6_3c_r2_f2_loopback_proxy_safe_matched_ab.yaml"
)
P6_HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.P6.md"


def test_capacity_calibration_keeps_individual_prompts_legal_and_pairs_pressured():
    workload = yaml.safe_load(WORKLOAD.read_text(encoding="utf-8"))
    frozen = workload["shared_runtime_freeze"]
    assert workload["stage"] == "P6.3C-R2"
    assert frozen["max_model_len"] == 12288
    assert frozen["max_num_batched_tokens"] == 12288
    assert frozen["max_num_seqs"] == 2
    assert workload["shared_hybrid_kv_repair"][
        "enabled_both_modes_all_lifecycles"
    ]
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
    assert (
        layout["packages"]["vllm_ascend"]["source_kind"]
        == "environment_owned"
    )
    assert layout["base_vllm_root"] == str(
        (editable_root / "vllm").resolve()
    )
    assert layout["base_plugin_root"] == str(
        (site_packages / "vllm_ascend").resolve()
    )


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
    assert (
        mechanism["on_prefill_partial_present_both_pressure_cells"] is None
    )
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
    lifecycle_rows = (result / "lifecycle_summary.tsv").read_text(
        encoding="utf-8"
    )

    assert grading["server_grade"] == (
        "red_p6_3c_r2_scheduler_pressure_no_success"
    )
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
    assert output.count(
        "server_argv_sha256="
        "568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10"
    ) == 3
    assert output.count(
        "server_argv_sha256="
        "cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017"
    ) == 3


def test_r2_f1_server_audit_preserves_science_contract_and_new_lineage():
    result_dir = (
        "/audit/"
        "p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_"
        "2026_0729_run01"
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
        "task_id=p6_3c_r2_f1_chunked_prefill_runtime_layout_portable_"
        "2026_0729_run01"
    ) in output
    assert "experiment_label=P6_3C_R2_F1" in output
    assert output.count("max_model_len=12288") == 6
    assert output.count(
        "server_argv_sha256="
        "568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10"
    ) == 3
    assert output.count(
        "server_argv_sha256="
        "cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017"
    ) == 3


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
        "/audit/"
        "p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_"
        "2026_0730_run01"
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
        "task_id=p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_"
        "2026_0730_run01"
    ) in output
    assert "experiment_label=P6_3C_R2_F2" in output
    assert output.count("max_model_len=12288") == 6
    assert output.count("shell_local_http_proxy=explicitly_disabled") == 6
    assert output.count("python_local_http_proxy_handler=empty") == 6
    assert output.count(
        "server_argv_sha256="
        "568b32b1b105c0113a28cd71efe1b905dc5afd86690158e63c5bcbe9da55bb10"
    ) == 3
    assert output.count(
        "server_argv_sha256="
        "cb6687044ed1ad4d6661f90ff16b7c9686e8c3ef15e1300b67e40ad00383b017"
    ) == 3


def test_p6_handoff_asset_gate_matches_current_bytes():
    text = P6_HANDOFF.read_text(encoding="utf-8")
    rows = re.findall(
        r"^\| (\d+) \| `([^`]+)` \| (\d+) \| `([0-9a-f]{64})` \|$",
        text,
        re.MULTILINE,
    )
    assert len(rows) == 23
    for _, relative_path, expected_bytes, expected_sha256 in rows:
        payload = (REPO_ROOT / relative_path).read_bytes()
        assert len(payload) == int(expected_bytes)
        assert hashlib.sha256(payload).hexdigest() == expected_sha256
    assert "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1" in text
    assert "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f262a3d509ebc1" not in text
    assert "若有 K2、K3、P8.3、P9、其他 P6" in text
    assert (
        "p6_3c_r2_f2_chunked_prefill_loopback_proxy_safe_"
        "2026_0730_run01"
    ) in text
    assert "server_side_path_wrapper_authorized: false" in text
    assert "shell_local_http_proxy=explicitly_disabled" in text
    assert "python_local_http_proxy_handler=empty" in text
