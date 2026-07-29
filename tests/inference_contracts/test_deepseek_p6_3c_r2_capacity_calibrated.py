from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

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


def test_p6_handoff_asset_gate_matches_current_bytes():
    text = P6_HANDOFF.read_text(encoding="utf-8")
    rows = re.findall(
        r"^\| (\d+) \| `([^`]+)` \| (\d+) \| `([0-9a-f]{64})` \|$",
        text,
        re.MULTILINE,
    )
    assert len(rows) == 17
    for _, relative_path, expected_bytes, expected_sha256 in rows:
        payload = (REPO_ROOT / relative_path).read_bytes()
        assert len(payload) == int(expected_bytes)
        assert hashlib.sha256(payload).hexdigest() == expected_sha256
    assert "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f261a3d509ebc1" in text
    assert "75156e56ce06554cfca79aef92167ec78521a28902f90389f8f262a3d509ebc1" not in text
    assert "若 K2、K3、P8.3、P9、其他 P6" in text
