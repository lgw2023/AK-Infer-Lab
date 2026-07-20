import hashlib
import os
from pathlib import Path
import stat
import subprocess

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"
R3_R2_R1_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r3_r2_r1_simple_cpu_offload.sh"
)
R3_R2_R1_AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/"
    "p8_2_k1a_r3_r2_r1_installed_source_gate_audit.yaml"
)


def test_current_handoff_preserves_only_the_r4_frozen_source_gate() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert (
        "task_id: p8_2_k1a_r4_store_only_refinalization_and_trace_attribution_2026_0720"
    ) in handoff
    assert "manager.py=fdcb18a63db0131a0f59dabbb73de915773dcdf67f713e479f5ef301d4a9911b" in handoff
    assert "block_pool.py=36a1683a7341a27862b0301e991e76734d968701632775932fbeb0420e894283" in handoff
    assert "BASE_ASCEND_REPO=" not in handoff
    assert "vllm-ascend-0.22.1rc1" not in handoff
    assert "2a6dc169e9fe0b2fbdad4862697dc3c8b5e66a2f" not in handoff


def test_r3_r2_r1_keeps_the_same_argv_capacity_and_request_lifecycle(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["P8_2_K1A_AUDIT_ONLY"] = "1"
    completed = subprocess.run(
        ["bash", str(R3_R2_R1_RUNNER), str(tmp_path / "result")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    audit = dict(
        line.split("=", 1)
        for line in completed.stdout.splitlines()
        if "=" in line
    )
    assert audit == {
        "cpu_bytes_to_use": "3444834304",
        "cpu_bytes_to_use_per_rank": "430604288",
        "execution_mode": (
            "authorized_installed_source_gate_repair_same_accepted_capacity_"
            "single_lifecycle_six_request_mechanism"
        ),
        "lifecycle_count": "1",
        "next_task_authorized": "false",
        "npu_execution_authorized": "true",
        "request_count": "6",
        "request_order": (
            "warmup,prime,pressure,restore_follower,repeat_follower,"
            "isolated_control"
        ),
        "server_command_sha256": (
            "8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6"
        ),
        "task_id": (
            "p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_"
            "store_restore_2026_0720"
        ),
    }


def test_r3_r2_r1_audit_preserves_parent_block_and_repair_boundary() -> None:
    audit = yaml.safe_load(R3_R2_R1_AUDIT.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R3-R2-R1"
    assert {
        key: audit["parent_r3_r2"][key]
        for key in (
            "task_id",
            "server_grade",
            "failure_class",
            "portable_argv_contract_gate",
            "accepted_r2_capacity_provenance_gate",
            "vllm_started",
            "npu_started",
            "successful_request_count",
            "model_request_count",
            "keep_alive_disrupted",
        )
    } == {
        "task_id": (
            "p8_2_k1a_r3_r2_deepseek_v4_flash_simple_cpu_offload_store_"
            "restore_2026_0719"
        ),
        "server_grade": "blocked_p8_2_k1a_r3_r2_source_or_resource_gate",
        "failure_class": "unverified_vllm_ascend_checkout_path_contract",
        "portable_argv_contract_gate": "pass",
        "accepted_r2_capacity_provenance_gate": "pass",
        "vllm_started": False,
        "npu_started": False,
        "successful_request_count": 0,
        "model_request_count": 0,
        "keep_alive_disrupted": False,
    }
    assert audit["repair"] == {
        "remove_unverified_checkout_gate": True,
        "installed_vllm_ascend_root": (
            "${RUNTIME_PREFIX}/lib/python3.11/site-packages"
        ),
        "installed_content_hash_gate": True,
        "runtime_import_registration_gate": True,
        "frozen_vllm_ascend_commit": (
            "5f6faa0cb8830f667266f3b8121cd1383606f2a1"
        ),
        "alternate_checkout_commit_accepted": False,
    }
    assert audit["unchanged_experiment"] == {
        "canonical_server_argv_sha256": (
            "8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6"
        ),
        "cpu_bytes_to_use_per_rank": 430604288,
        "cpu_bytes_to_use_total": 3444834304,
        "formal_lifecycle_count_exact": 1,
        "model_request_count_exact": 6,
        "request_retry_count_exact": 0,
        "request_order": [
            "warmup",
            "prime",
            "pressure",
            "restore_follower",
            "repeat_follower",
            "isolated_control",
        ],
    }
    assert audit["decision"]["result_transfer_authorized"] is True
    assert audit["decision"]["next_task_authorized"] is False
    assert audit["decision"]["k2_authorized"] is False
    assert audit["decision"]["p8_3_i1_authorized"] is False


def test_r4_handoff_runs_the_full_bounded_offline_chain() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert handoff.count("\ntask_id: ") == 1
    for exact in (
        "execution_mode: authorized_read_only_offline_store_only_refinalization_"
        "trace_attribution_and_source_semantics",
        "formal_model_lifecycle_count_exact: 0",
        "model_request_count_exact: 0",
        "result_transfer_authorized: true",
        "next_task_authorized: false",
        "run_deepseek_p8_2_k1a_r4_offline_closeout.sh",
        "offline_refinalization_authorized: true",
        "raw_trace_attribution_authorized: true",
        "frozen_source_semantics_audit_authorized: true",
        "formal_h2d_trigger_lifecycle_allowed: false",
        "candidate_manifest.server_local.json",
        "9 个白名单 bounded metadata",
        "email / upload-api / server-local",
        "candidate_green_p8_2_k1a_r4_offline_store_only_closeout",
        "blocked_p8_2_k1a_r4_offline_closeout_gate",
        "不得进入 K2",
        "不得进入 P8.3-I1",
    ):
        assert exact in handoff
    assert 'test ! -e "${RESULT_ROOT}"' in handoff
    assert "trap cleanup EXIT" not in handoff
    assert "keep_alive_stop_authorized: false" in handoff


def test_r3_r2_r1_contract_files_remain_preserved_as_parent_provenance() -> None:
    paths = (
        R3_R2_R1_AUDIT,
        R3_R2_R1_RUNNER,
        Path(__file__),
    )

    for path in paths:
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest()
    assert R3_R2_R1_RUNNER.stat().st_mode & stat.S_IXUSR
