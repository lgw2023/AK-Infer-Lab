from pathlib import Path

from tools.observability_profile.microbench import run_microbench_suite


def _by_name(results: list[dict], bench_name: str) -> dict:
    return next(result for result in results if result["bench_name"] == bench_name)


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
