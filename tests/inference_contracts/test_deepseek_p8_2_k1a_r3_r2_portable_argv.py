from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
ARGV_IDENTITY = (
    REPO_ROOT
    / "tools/inference_contracts/canonicalize_server_argv.py"
)
R3_R1_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r3_r1_simple_cpu_offload.sh"
)
R3_R2_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/"
    "run_deepseek_p8_2_k1a_r3_r2_simple_cpu_offload.sh"
)
REQUEST_RUNNER = (
    REPO_ROOT
    / "tools/inference_contracts/run_deepseek_p8_2_k1a_simple_cpu_offload.py"
)
R3_R2_AUDIT = (
    REPO_ROOT
    / "benchmarks/deepseek_v4_flash/p8_2_k1a_r3_r2_portable_argv_audit.yaml"
)
HANDOFF = REPO_ROOT / "通信模块/docs/developer-to-server.md"


def test_server_argv_identity_hashes_exact_arguments_not_shell_rendering(
    tmp_path: Path,
) -> None:
    argv = [
        "/frozen/env/bin/vllm",
        "serve",
        "/frozen/model",
        "--kv-transfer-config",
        '{"kv_connector":"SimpleCPUOffloadConnector","lazy_offload":false}',
    ]
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(ARGV_IDENTITY),
            "--output",
            str(first),
            "--",
            *argv,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    repeated = subprocess.run(
        [
            sys.executable,
            str(ARGV_IDENTITY),
            "--output",
            str(second),
            "--",
            *argv,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert repeated.returncode == 0, repeated.stderr
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload == {
        "argv": argv,
        "schema_version": "ak_infer_lab_server_argv_v1",
    }
    expected = hashlib.sha256(first.read_bytes()).hexdigest()
    assert completed.stdout.strip() == expected
    assert repeated.stdout.strip() == expected


def test_mode_audit_exposes_the_canonical_argv_identity(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["P8_2_K1A_MODE_AUDIT_ONLY"] = "1"
    completed = subprocess.run(
        ["bash", str(R3_R1_RUNNER), str(tmp_path / "result")],
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
    argv = shlex.split(audit["server_command"])
    identity = subprocess.run(
        [sys.executable, str(ARGV_IDENTITY), "--", *argv],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert audit["server_command_identity_schema"] == (
        "ak_infer_lab_server_argv_v1"
    )
    assert audit["server_command_sha256"] == identity


def test_r3_r2_repairs_identity_without_changing_the_lifecycle(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["P8_2_K1A_AUDIT_ONLY"] = "1"
    completed = subprocess.run(
        ["bash", str(R3_R2_RUNNER), str(tmp_path / "result")],
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
            "authorized_portable_argv_same_accepted_capacity_single_"
            "lifecycle_six_request_mechanism"
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
            "p8_2_k1a_r3_r2_deepseek_v4_flash_simple_cpu_offload_store_"
            "restore_2026_0719"
        ),
    }


def test_prelaunch_failure_preserves_first_error_and_builds_bounded_manifest(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "result"
    artifact.mkdir()
    (artifact / "request_body_manifest.json").write_text("{}\n", encoding="utf-8")
    (artifact / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
    first_error = "server argv identity mismatch\nexpected=abc\nactual=def\n"
    (artifact / "first_failure_excerpt.txt").write_text(
        first_error, encoding="utf-8"
    )
    env = os.environ.copy()
    env.update(
        {
            "P8_2_K1A_TASK_ID": (
                "p8_2_k1a_r3_r2_deepseek_v4_flash_simple_cpu_offload_store_"
                "restore_2026_0719"
            ),
            "P8_2_K1A_CPU_BYTES_TO_USE": "3444834304",
            "P8_2_K1A_CPU_BYTES_TO_USE_PER_RANK": "430604288",
            "P8_2_K1A_NO_SUCCESS_GRADE": "red_p8_2_k1a_r3_r2_no_success",
            "P8_2_K1A_RESULT_TRANSFER_AUTHORIZED": "true",
        }
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(REQUEST_RUNNER),
            "finalize",
            "--artifact-dir",
            str(artifact),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2, completed.stderr
    assert (artifact / "first_failure_excerpt.txt").read_text() == first_error
    manifest = json.loads(
        (artifact / "candidate_manifest.server_local.json").read_text()
    )
    assert manifest["result_transfer_authorized"] is True
    assert manifest["candidate_total_bytes"] <= 71680
    assert "environment_and_hashes.json" in manifest["missing_candidate_files"]
    assert manifest["files"]["first_failure_excerpt.txt"]["sha256"] == (
        hashlib.sha256(first_error.encode()).hexdigest()
    )


def test_r3_r2_audit_preserves_the_failed_run_and_same_experiment_boundary() -> None:
    audit = yaml.safe_load(R3_R2_AUDIT.read_text(encoding="utf-8"))

    assert audit["stage"] == "P8.2-K1A-R3-R2"
    assert {
        key: audit["parent_r3_r1"][key]
        for key in (
            "task_id",
            "server_grade",
            "failure_class",
            "lifecycle_attempted",
            "vllm_started",
            "successful_request_count",
            "model_request_count",
            "cleanup",
        )
    } == {
        "task_id": (
            "p8_2_k1a_r3_r1_deepseek_v4_flash_simple_cpu_offload_store_"
            "restore_2026_0718"
        ),
        "server_grade": "red_p8_2_k1a_r3_r1_no_success",
        "failure_class": "nonportable_server_command_identity_contract",
        "lifecycle_attempted": 1,
        "vllm_started": False,
        "successful_request_count": 0,
        "model_request_count": 0,
        "cleanup": "clean",
    }
    assert audit["repair"]["identity_schema"] == "ak_infer_lab_server_argv_v1"
    assert audit["repair"]["canonical_server_argv_sha256"] == (
        "8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6"
    )
    assert audit["repair"]["bash_3_2_render_sha256"] == (
        "418d2796ec2dd15ab7504c264a6635a50d064cb7b6425f809cbfba550d2f5bb0"
    )
    assert audit["repair"]["bash_5_1_render_sha256"] == (
        "a65e8e69867e0772c85ccea1b4f8cbdab1957bb04ee77194fdd98a1415d05747"
    )
    assert audit["unchanged_experiment"] == {
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
    assert audit["decision"]["k2_authorized"] is False
    assert audit["decision"]["p8_3_i1_authorized"] is False
    assert audit["decision"]["next_task_authorized"] is False


def test_r3_r2_r1_is_the_only_current_handoff_and_preserves_portable_identity() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert handoff.count("\ntask_id: ") == 1
    assert (
        "task_id: p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_"
        "store_restore_2026_0720"
    ) in handoff
    for exact in (
        "execution_mode: authorized_installed_source_gate_repair_same_accepted_"
        "capacity_single_lifecycle_six_request_mechanism",
        "npu_execution_authorized: true",
        "formal_model_lifecycle_count_exact: 1",
        "model_request_count_exact: 6",
        "request_retry_count_exact: 0",
        "result_transfer_authorized: true",
        "next_task_authorized: false",
        "server_command_identity_schema=ak_infer_lab_server_argv_v1",
        "server_command_sha256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6",
        "P8_2_K1A_EXPECTED_COMMAND_SHA256=8301f4c4c4f203e42f7954e4e4c9b961b55725b132dcbd6fb4b8625bc271bde6",
        "p8_2_k1a_r3_r2_r1_deepseek_v4_flash_simple_cpu_offload_store_restore_2026_0720_run01",
        "不得进入 K2",
        "不得进入 P8.3-I1",
    ):
        assert exact in handoff
    assert "test ! -e \"${RESULT_DIR}\"" in handoff
    assert "candidate_manifest.server_local.json" in handoff
    assert "missing_candidate_files" in handoff
    assert "email / upload-api / server-local" in handoff
    assert "当前 `result_transfer_authorized:true`" in handoff
