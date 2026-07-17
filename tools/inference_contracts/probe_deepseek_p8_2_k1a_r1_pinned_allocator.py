from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inference_contracts.p8_2_k1a_r1_allocator import (
    assess_allocator_envelope,
)


def build_wave_plan(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    required = int(geometry["required_cpu_blocks"])
    if required <= 0 or required % 4:
        raise ValueError("required_cpu_blocks must be a positive multiple of four")
    step = required // 4
    bytes_per_block = int(geometry["total_bytes_per_block"])
    return [
        {
            "cpu_blocks": blocks,
            "bytes_per_rank": blocks * bytes_per_block,
            "world_size": 8,
            "allocation_shape": "per_tensor_bytes_per_block_x_cpu_blocks",
            "is_required_restore_wave": blocks == required,
        }
        for blocks in range(step, required + 1, step)
    ]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_worker(args: argparse.Namespace) -> int:
    geometry = json.loads(Path(args.geometry_summary).read_text(encoding="utf-8"))
    status_path = Path(args.status)
    release_path = Path(args.release)
    allocations: list[Any] = []
    started = time.monotonic()
    try:
        import torch
        import torch_npu  # noqa: F401

        for descriptor in geometry["per_tensor_bytes_per_block"]:
            size = int(descriptor["bytes_per_block"]) * int(args.cpu_blocks)
            allocations.append(
                torch.zeros(size, dtype=torch.uint8, device="cpu", pin_memory=True)
            )
        _write_json(
            status_path,
            {
                "rank": int(args.rank),
                "cpu_blocks": int(args.cpu_blocks),
                "success": True,
                "allocated_bytes": sum(value.numel() for value in allocations),
                "allocation_count": len(allocations),
                "pid": os.getpid(),
            },
        )
        deadline = time.monotonic() + float(args.hold_timeout_seconds)
        while not release_path.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not release_path.exists():
            raise TimeoutError("coordinator did not release allocation wave")
        return 0
    except BaseException as exc:
        _write_json(
            status_path,
            {
                "rank": int(args.rank),
                "cpu_blocks": int(args.cpu_blocks),
                "success": False,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[-2048:],
                "pid": os.getpid(),
            },
        )
        return 2
    finally:
        allocations.clear()
        elapsed = time.monotonic() - started
        done_path = status_path.with_suffix(".done.json")
        _write_json(done_path, {"rank": int(args.rank), "released": True, "elapsed_seconds": elapsed})


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def run_envelope(args: argparse.Namespace) -> int:
    geometry_path = Path(args.geometry_summary)
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    output_root = Path(args.output_dir)
    if output_root.exists():
        raise SystemExit(f"output directory already exists: {output_root}")
    output_root.mkdir(parents=True)
    waves: list[dict[str, Any]] = []
    for plan in build_wave_plan(geometry):
        blocks = int(plan["cpu_blocks"])
        wave_root = output_root / f"wave_{blocks:04d}_blocks"
        wave_root.mkdir()
        release = wave_root / "release"
        processes: list[subprocess.Popen[Any]] = []
        try:
            for rank in range(8):
                status = wave_root / f"rank_{rank}.status.json"
                env = os.environ.copy()
                env.update(
                    {
                        "RANK": str(rank),
                        "LOCAL_RANK": str(rank),
                        "WORLD_SIZE": "8",
                        "ASCEND_RT_VISIBLE_DEVICES": str(rank),
                    }
                )
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "worker",
                            "--geometry-summary",
                            str(geometry_path),
                            "--cpu-blocks",
                            str(blocks),
                            "--rank",
                            str(rank),
                            "--status",
                            str(status),
                            "--release",
                            str(release),
                            "--hold-timeout-seconds",
                            str(args.wave_timeout_seconds),
                        ],
                        env=env,
                        start_new_session=True,
                    )
                )
            deadline = time.monotonic() + float(args.wave_timeout_seconds)
            statuses = [wave_root / f"rank_{rank}.status.json" for rank in range(8)]
            while time.monotonic() < deadline:
                if all(path.exists() for path in statuses):
                    break
                if all(process.poll() is not None for process in processes):
                    break
                time.sleep(0.25)
            release.touch()
            for process in processes:
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    _terminate_process(process)
            rows = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in statuses
                if path.exists()
            ]
            done = list(wave_root.glob("rank_*.status.done.json"))
            wave = {
                **plan,
                "rank_status_count": len(rows),
                "rank_success_count": sum(row.get("success") is True for row in rows),
                "cleanup_ok": len(done) == 8 and all(process.poll() is not None for process in processes),
                "rank_status": rows,
            }
            waves.append(wave)
            _write_json(wave_root / "wave_summary.json", wave)
            if wave["rank_success_count"] != 8 or wave["cleanup_ok"] is not True:
                break
        finally:
            release.touch(exist_ok=True)
            for process in processes:
                _terminate_process(process)

    if not any(int(row["cpu_blocks"]) == int(geometry["required_cpu_blocks"]) for row in waves):
        waves.append(
            {
                "cpu_blocks": int(geometry["required_cpu_blocks"]),
                "bytes_per_rank": int(geometry["required_capacity_bytes_per_rank"]),
                "world_size": 8,
                "allocation_shape": "per_tensor_bytes_per_block_x_cpu_blocks",
                "is_required_restore_wave": True,
                "rank_status_count": 0,
                "rank_success_count": 0,
                "cleanup_ok": True,
                "not_attempted_reason": "lower_allocator_wave_failed_first",
            }
        )
    result = assess_allocator_envelope(geometry, waves)
    _write_json(output_root / "pinned_allocator_envelope.json", result)
    return 0 if result["acl_pinned_host_allocator_gate_ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    envelope = sub.add_parser("envelope")
    envelope.add_argument("--geometry-summary", required=True)
    envelope.add_argument("--output-dir", required=True)
    envelope.add_argument("--wave-timeout-seconds", type=float, default=180.0)
    envelope.set_defaults(func=run_envelope)
    worker = sub.add_parser("worker")
    worker.add_argument("--geometry-summary", required=True)
    worker.add_argument("--cpu-blocks", required=True, type=int)
    worker.add_argument("--rank", required=True, type=int)
    worker.add_argument("--status", required=True)
    worker.add_argument("--release", required=True)
    worker.add_argument("--hold-timeout-seconds", type=float, default=180.0)
    worker.set_defaults(func=run_worker)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
