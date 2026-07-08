import argparse
import json
from pathlib import Path

import pytest

from tools.observability_profile import hardware_ceiling


def test_parse_size_bytes_supports_binary_suffixes():
    assert hardware_ceiling.parse_size_bytes("4K") == 4 * 1024
    assert hardware_ceiling.parse_size_bytes("16M") == 16 * 1024**2
    assert hardware_ceiling.parse_size_bytes("1G") == 1024**3


def test_parse_size_bytes_rejects_empty_and_non_positive():
    with pytest.raises(ValueError):
        hardware_ceiling.parse_size_bytes("")
    with pytest.raises(ValueError):
        hardware_ceiling.parse_size_bytes("0")


def test_build_summary_reports_peaks_and_boundaries():
    summary = hardware_ceiling.build_summary(
        run_id="hardware_ceiling_test",
        copy_rows=[
            {"direction": "h2d", "best_gbps": 10.0},
            {"direction": "h2d", "best_gbps": 20.0},
            {"direction": "d2h", "best_gbps": 15.0},
        ],
        matmul_rows=[{"tflops": 123.0}],
        dram_rows=[{"read_best_gbps": 40.0, "copy_best_gbps": 35.0}],
        fio_rows=[{"fio_read_bw_mib_s": 1000.0, "fio_write_bw_mib_s": 900.0}],
        result={"overall_status": "success"},
    )

    assert "run_id=hardware_ceiling_test" in summary
    assert "h2d_best_gbps=20.0" in summary
    assert "d2h_best_gbps=15.0" in summary
    assert "matmul_best_tflops=123.0" in summary
    assert "does not run model inference" in summary


def test_write_mail_candidates_marks_large_files(tmp_path: Path):
    small = tmp_path / "small.txt"
    large = tmp_path / "large.txt"
    small.write_text("ok", encoding="utf-8")
    large.write_text("x" * (hardware_ceiling.MAIL_LIMIT_BYTES + 1), encoding="utf-8")

    hardware_ceiling.write_mail_candidates(tmp_path, [small, large])

    text = (tmp_path / "mail_attachment_candidates.tsv").read_text(encoding="utf-8")
    assert f"{small}\t2\ttrue" in text
    assert f"{large}\t{hardware_ceiling.MAIL_LIMIT_BYTES + 1}\tfalse" in text


def test_collect_writes_artifacts_with_stubbed_sweeps(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        hardware_ceiling,
        "run_npu_sweeps",
        lambda **kwargs: (
            [{"bench": "npu_copy", "direction": "h2d", "best_gbps": 10.0, "status": "measurable"}],
            [{"bench": "npu_matmul", "tflops": 20.0, "status": "measurable"}],
            {"status": "success"},
        ),
    )
    monkeypatch.setattr(
        hardware_ceiling,
        "run_cpu_dram_sweep",
        lambda **kwargs: ([{"bench": "cpu_dram_numpy", "read_best_gbps": 30.0, "copy_best_gbps": 25.0, "status": "measurable"}], {"status": "success"}),
    )
    monkeypatch.setattr(
        hardware_ceiling,
        "run_fio_sweep",
        lambda **kwargs: ([{"bench": "ssd_fio_sweep", "fio_read_bw_mib_s": 40.0, "fio_write_bw_mib_s": 35.0, "status": "measurable"}], {"status": "success"}),
    )
    args = argparse.Namespace(
        run_id="hardware_ceiling_test",
        output_base=str(tmp_path),
        scratch_dir=str(tmp_path / "scratch"),
        python_bin="python",
        npu_device="npu:0",
        copy_sizes="4K",
        copy_repeats=1,
        matmul_dims="512",
        matmul_dtypes="float16",
        matmul_repeats=1,
        dram_sizes="256M",
        dram_repeats=1,
        fio_block_sizes="4k",
        fio_queue_depths="1",
        fio_rw_modes="read",
        fio_runtime_s=1,
        fio_size="64M",
        npu_timeout_s=30,
        overwrite=False,
    )

    artifact_dir = hardware_ceiling.collect_hardware_ceiling(args)

    assert artifact_dir == tmp_path / "hardware_ceiling_test"
    assert (artifact_dir / "npu_copy_sweep.csv").exists()
    assert (artifact_dir / "npu_matmul_sweep.csv").exists()
    assert (artifact_dir / "cpu_dram_sweep.csv").exists()
    assert (artifact_dir / "ssd_fio_sweep.csv").exists()
    result = json.loads((artifact_dir / "hardware_ceiling_result.json").read_text(encoding="utf-8"))
    assert result["overall_status"] == "success"
    assert result["peaks"]["h2d_best_gbps"] == 10.0
