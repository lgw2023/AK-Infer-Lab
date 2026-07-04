from pathlib import Path
import json
import subprocess

import tools.observability_profile.microbench as microbench_module
from tools.observability_profile.microbench import run_microbench_suite


def _by_name(results: list[dict], bench_name: str) -> dict:
    return next(result for result in results if result["bench_name"] == bench_name)


def test_torch_npu_ready_uses_current_python_executable(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(microbench_module.importlib_metadata, "version", lambda package: "2.9.0.post2")

    def fake_run(command, check, capture_output, text, timeout):
        captured["command"] = command
        captured["timeout"] = timeout
        return subprocess.CompletedProcess(command, 0, stdout="torch_npu_import_ok\n", stderr="")

    monkeypatch.setattr(microbench_module.subprocess, "run", fake_run)

    reason = microbench_module._torch_npu_ready(python_executable="/project/env/bin/python")

    assert reason == {"category": None, "detail": None}
    assert captured["command"][0] == "/project/env/bin/python"
    assert captured["timeout"] == 30


def test_torch_npu_timeout_detail_names_python_executable(monkeypatch):
    monkeypatch.setattr(microbench_module.importlib_metadata, "version", lambda package: "2.9.0.post2")

    def fake_run(command, check, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(microbench_module.subprocess, "run", fake_run)

    reason = microbench_module._torch_npu_ready(python_executable="/project/env/bin/python")

    assert reason["category"] == "timeout"
    assert "/project/env/bin/python" in reason["detail"]
    assert "30 seconds" in reason["detail"]


def test_run_microbench_suite_records_measurable_npu_metrics(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(microbench_module, "_torch_npu_ready", lambda: {"category": None, "detail": None})

    def fake_run(command, check, capture_output, text, timeout):
        payload = {
            "status": "measurable",
            "duration_ms": 12.5,
            "metrics": [
                {
                    "metric_name": "h2d_latency_us",
                    "metric_value": 42.0,
                    "unit": "us",
                }
            ],
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(microbench_module.subprocess, "run", fake_run)

    results = run_microbench_suite(
        run_dir=tmp_path,
        scratch_dir=tmp_path / "scratch",
        copy_sizes="4K,1M",
        fio_qdepth="1",
        duration_s=1,
        command_exists=lambda command: False,
    )

    result = _by_name(results, "npu_copy_h2d")
    artifact = tmp_path / result["artifact_path"]

    assert result["status"] == "measurable"
    assert result["duration_ms"] == 12.5
    assert artifact.exists()
    assert "h2d_latency_us" in artifact.read_text()


def test_run_microbench_suite_blocks_ssd_fio_without_scratch(tmp_path: Path):
    results = run_microbench_suite(
        run_dir=tmp_path,
        scratch_dir=None,
        copy_sizes="4K,1M",
        fio_qdepth="1,4",
        duration_s=1,
        command_exists=lambda command: True,
    )

    result = _by_name(results, "ssd_fio")
    artifact = tmp_path / result["artifact_path"]

    assert result["status"] == "blocked"
    assert result["blocked_reason"]["category"] == "scratch_missing"
    assert artifact.exists()
    assert "scratch_missing" in artifact.read_text()


def test_run_microbench_suite_blocks_missing_fio_with_scratch(tmp_path: Path):
    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir()

    results = run_microbench_suite(
        run_dir=tmp_path,
        scratch_dir=scratch_dir,
        copy_sizes="4K,1M",
        fio_qdepth="1,4",
        duration_s=1,
        command_exists=lambda command: command != "fio",
    )

    result = _by_name(results, "ssd_fio")
    artifact = tmp_path / result["artifact_path"]

    assert result["status"] == "blocked"
    assert result["blocked_reason"]["category"] == "tool_missing"
    assert artifact.exists()
    assert "tool_missing" in artifact.read_text()


def test_run_microbench_suite_blocks_unusable_scratch_path(tmp_path: Path):
    scratch_path = tmp_path / "scratch-file"
    scratch_path.write_text("not a directory")

    results = run_microbench_suite(
        run_dir=tmp_path,
        scratch_dir=scratch_path,
        copy_sizes="4K,1M",
        fio_qdepth="1",
        duration_s=1,
        command_exists=lambda command: command == "fio",
    )

    result = _by_name(results, "ssd_fio")

    assert result["status"] == "blocked"
    assert result["blocked_reason"]["category"] == "permission"
