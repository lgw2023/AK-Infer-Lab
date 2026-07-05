from pathlib import Path
import csv
import json
import subprocess

import pytest

import tools.observability_profile.microbench as microbench_module
from tools.observability_profile.microbench import run_microbench_suite


def _by_name(results: list[dict], bench_name: str) -> dict:
    return next(result for result in results if result["bench_name"] == bench_name)


def _metrics_by_name(result: dict) -> dict[str, dict]:
    return {metric["metric_name"]: metric for metric in result["metrics"]}


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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
        command_exists=lambda command: False,
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
        command_exists=lambda command: False,
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


def test_run_microbench_suite_parses_fio_json_metrics(tmp_path: Path, monkeypatch):
    scratch_dir = tmp_path / "scratch"
    monkeypatch.setattr(
        microbench_module,
        "_torch_npu_ready",
        lambda: {"category": "tool_missing", "detail": "torch-npu unavailable in unit test"},
    )
    fio_payload = {
        "jobs": [
            {
                "read": {
                    "iops": 1234.5,
                    "bw_bytes": 10 * 1024 * 1024,
                    "clat_ns": {
                        "mean": 12000,
                        "percentile": {
                            "95.000000": 45000,
                            "99.000000": 88000,
                        },
                    },
                },
                "write": {
                    "iops": 678.25,
                    "bw_bytes": 5 * 1024 * 1024,
                    "clat_ns": {
                        "mean": 34000,
                        "percentile": {
                            "95.000000": 99000,
                            "99.000000": 150000,
                        },
                    },
                },
            }
        ]
    }

    def fake_run(command, check, capture_output, text, timeout):
        assert command[0] == "fio"
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(fio_payload), stderr="")

    monkeypatch.setattr(microbench_module.subprocess, "run", fake_run)

    results = run_microbench_suite(
        run_dir=tmp_path,
        scratch_dir=scratch_dir,
        copy_sizes="4K,1M",
        fio_qdepth="1",
        duration_s=1,
        command_exists=lambda command: command == "fio",
    )

    result = _by_name(results, "ssd_fio")
    metrics = _metrics_by_name(result)
    artifact = tmp_path / result["artifact_path"]

    assert result["status"] == "measurable"
    assert metrics["fio_read_iops"]["metric_value"] == pytest.approx(1234.5)
    assert metrics["fio_write_iops"]["metric_value"] == pytest.approx(678.25)
    assert metrics["fio_total_iops"]["metric_value"] == pytest.approx(1912.75)
    assert metrics["fio_read_bw_mib_s"]["metric_value"] == pytest.approx(10.0)
    assert metrics["fio_write_bw_mib_s"]["metric_value"] == pytest.approx(5.0)
    assert metrics["fio_read_clat_mean_us"]["metric_value"] == pytest.approx(12.0)
    assert metrics["fio_write_clat_p99_us"]["metric_value"] == pytest.approx(150.0)
    assert "fio_completed" not in metrics
    assert {row["metric_name"] for row in _csv_rows(artifact)} >= {
        "fio_read_iops",
        "fio_write_iops",
        "fio_total_iops",
    }


def test_run_microbench_suite_parses_perf_stat_metrics(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        microbench_module,
        "_torch_npu_ready",
        lambda: {"category": "tool_missing", "detail": "torch-npu unavailable in unit test"},
    )
    perf_output = "\n".join(
        [
            "100.50,msec,task-clock,100500000,100.00,,",
            "123456,,cycles,100500000,100.00,,",
            "789012,,instructions,100500000,100.00,,",
        ]
    )

    def fake_run(command, check, capture_output, text, timeout):
        assert command[0] == "perf"
        assert "stat" in command
        return subprocess.CompletedProcess(command, 0, stdout="", stderr=perf_output)

    monkeypatch.setattr(microbench_module.subprocess, "run", fake_run)

    results = run_microbench_suite(
        run_dir=tmp_path,
        scratch_dir=None,
        copy_sizes="4K,1M",
        fio_qdepth="1",
        duration_s=1,
        command_exists=lambda command: command == "perf",
    )

    result = _by_name(results, "cpu_perf")
    metrics = _metrics_by_name(result)

    assert result["status"] == "measurable"
    assert metrics["perf_task_clock_ms"]["metric_value"] == pytest.approx(100.5)
    assert metrics["perf_cycles"]["metric_value"] == pytest.approx(123456)
    assert metrics["perf_instructions"]["metric_value"] == pytest.approx(789012)
    assert metrics["perf_ipc"]["metric_value"] == pytest.approx(789012 / 123456, rel=1e-6)


def test_run_microbench_suite_falls_back_to_task_clock_when_perf_counters_are_restricted(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        microbench_module,
        "_torch_npu_ready",
        lambda: {"category": "tool_missing", "detail": "torch-npu unavailable in unit test"},
    )
    calls: list[list[str]] = []

    def fake_run(command, check, capture_output, text, timeout):
        assert command[0] == "perf"
        calls.append(command)
        if command[command.index("-e") + 1] == "task-clock":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="50.0,msec,task-clock,50000000,100.00,,")
        return subprocess.CompletedProcess(command, 255, stdout="", stderr="No permission to enable cycles event.")

    monkeypatch.setattr(microbench_module.subprocess, "run", fake_run)

    results = run_microbench_suite(
        run_dir=tmp_path,
        scratch_dir=None,
        copy_sizes="4K,1M",
        fio_qdepth="1",
        duration_s=1,
        command_exists=lambda command: command == "perf",
    )

    result = _by_name(results, "cpu_perf")
    metrics = _metrics_by_name(result)

    assert len(calls) == 2
    assert result["status"] == "partial"
    assert result["blocked_reason"]["category"] == "permission"
    assert "cycles" in result["blocked_reason"]["detail"]
    assert metrics["perf_task_clock_ms"]["metric_value"] == pytest.approx(50.0)
    assert "perf_cycles" not in metrics


def test_run_microbench_suite_parses_numactl_topology_metrics(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        microbench_module,
        "_torch_npu_ready",
        lambda: {"category": "tool_missing", "detail": "torch-npu unavailable in unit test"},
    )
    numactl_output = "\n".join(
        [
            "available: 2 nodes (0-1)",
            "node 0 cpus: 0 1 2 3",
            "node 0 size: 128000 MB",
            "node 0 free: 64000 MB",
            "node 1 cpus: 4 5 6 7",
            "node 1 size: 128000 MB",
            "node 1 free: 63000 MB",
            "node distances:",
            "node   0   1",
            "  0:  10  20",
            "  1:  20  10",
        ]
    )

    def fake_run(command, check, capture_output, text, timeout):
        assert command == ["numactl", "--hardware"]
        return subprocess.CompletedProcess(command, 0, stdout=numactl_output, stderr="")

    monkeypatch.setattr(microbench_module.subprocess, "run", fake_run)

    results = run_microbench_suite(
        run_dir=tmp_path,
        scratch_dir=None,
        copy_sizes="4K,1M",
        fio_qdepth="1",
        duration_s=1,
        command_exists=lambda command: command == "numactl",
    )

    result = _by_name(results, "numa_topology")
    metrics = _metrics_by_name(result)

    assert result["status"] == "measurable"
    assert metrics["numa_node_count"]["metric_value"] == 2
    assert metrics["numa_node_0_cpus"]["metric_value"] == "0 1 2 3"
    assert metrics["numa_node_0_cpu_count"]["metric_value"] == 4
    assert metrics["numa_node_0_memory_mb"]["metric_value"] == 128000
    assert metrics["numa_node_1_free_mb"]["metric_value"] == 63000
    assert metrics["numa_distance_0_1"]["metric_value"] == 20
