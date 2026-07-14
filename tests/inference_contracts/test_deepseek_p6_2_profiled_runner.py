import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tools.inference_contracts.analyze_msprof_sqlite_windows import discover_mode_paths
from tools.inference_contracts.run_deepseek_p6_2_profiled_evidence import (
    finalize_artifacts,
    parse_npu_smi_hbm_table,
    prepare_artifacts,
    run_cell,
    summarize_phase_memory,
)


def test_prepare_profiled_artifacts_freezes_six_unique_bodies(tmp_path):
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")

    manifest = prepare_artifacts(source_path, tmp_path / "run", "deepseek-test")

    assert manifest["request_count"] == 6
    assert len({row["request_body_sha256"] for row in manifest["records"]}) == 6
    assert all(row["common_prefix_upper_bound_tokens"] < 128 for row in manifest["records"])
    plan = json.loads((tmp_path / "run" / "profiled_plan.json").read_text())
    assert [row["cell_id"] for row in plan] == [
        "short_prefill",
        "long_prefill",
        "decode_heavy",
    ]
    assert all(row["warmup"]["context_tokens"] == 4096 for row in plan)
    assert [(row["measured"]["context_tokens"], row["measured"]["output_tokens"]) for row in plan] == [
        (4096, 64),
        (131072, 64),
        (4096, 256),
    ]


def test_npu_smi_parser_reads_one_eight_device_hbm_table():
    text = "\n".join(
        line
        for device in range(8)
        for line in (
            f"| {device}     910B1 | OK |",
            f"| {device} | 0000:00:00.{device} | 0 | 0 | {50000 + device} / 65536 |",
        )
    )

    devices = parse_npu_smi_hbm_table(text)

    assert [row["device_id"] for row in devices] == list(range(8))
    assert all(row["parser_ok"] for row in devices)
    assert devices[0]["hbm_used_mb"] == 50000.0
    assert devices[-1]["hbm_capacity_mb"] == 65536.0


def test_phase_memory_summary_counts_sweep_overlap_without_dropping_boundary():
    def sample(start, end, used, rss):
        return {
            "sweep_start_monotonic_ns": start,
            "sweep_end_monotonic_ns": end,
            "host_process_rss_mb": rss,
            "host_process_pss_mb": rss - 10,
            "devices": [
                {
                    "device_id": device,
                    "hbm_used_mb": used + device,
                    "hbm_capacity_mb": 65536.0,
                    "hbm_free_mb": 65536.0 - used - device,
                    "hbm_usage_pct": (used + device) * 100 / 65536,
                    "parser_ok": True,
                }
                for device in range(8)
            ],
        }

    rows = summarize_phase_memory(
        cell_id="short_prefill",
        samples=[
            sample(90, 110, 50000, 1000),
            sample(115, 130, 50100, 1010),
            sample(150, 160, 50200, 1020),
        ],
        request_start_ns=100,
        first_token_ns=120,
        response_end_ns=200,
    )

    assert [row["phase"] for row in rows] == ["prefill", "decode"]
    assert [row["sample_count"] for row in rows] == [2, 2]
    assert all(row["device_coverage_min"] == 8 for row in rows)
    assert rows[0]["host_process_rss_mb_max"] == 1010
    assert rows[1]["host_process_rss_mb_max"] == 1020


def test_run_cell_executes_warmup_then_profiled_request_with_phase_memory(tmp_path):
    state = {"drafts": 0, "draft_tokens": 0, "accepted": 0, "posts": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_GET(self):
            if self.path == "/health":
                body = b"ok"
            elif self.path == "/metrics":
                body = (
                    f"vllm:spec_decode_num_drafts_total {state['drafts']}\n"
                    f"vllm:spec_decode_num_draft_tokens_total {state['draft_tokens']}\n"
                    f"vllm:spec_decode_num_accepted_tokens_total {state['accepted']}\n"
                    "vllm:num_requests_running 0\n"
                    "vllm:num_requests_waiting 0\n"
                ).encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers["Content-Length"])
            payload = json.loads(self.rfile.read(length))
            output = int(payload["max_tokens"])
            state["posts"] += 1
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            token = 0
            while token < output:
                width = min(2, output - token)
                event = {
                    "choices": [
                        {
                            "token_ids": list(range(token, token + width)),
                            "finish_reason": "length" if token + width == output else None,
                        }
                    ]
                }
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                token += width
            usage = {
                "choices": [],
                "usage": {
                    "prompt_tokens": len(payload["prompt"]),
                    "completion_tokens": output,
                },
            }
            self.wfile.write(f"data: {json.dumps(usage)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            state["drafts"] += output
            state["draft_tokens"] += output
            state["accepted"] += output

    def fake_sample(_server_pid, _raw_dir, sequence):
        start = time.monotonic_ns()
        time.sleep(0.05)
        end = time.monotonic_ns()
        return {
            "sequence": sequence,
            "sweep_start_monotonic_ns": start,
            "sweep_end_monotonic_ns": end,
            "host_process_rss_mb": 1000.0,
            "host_process_pss_mb": 900.0,
            "devices": [
                {
                    "device_id": device,
                    "hbm_used_mb": 50000.0,
                    "hbm_capacity_mb": 65536.0,
                    "hbm_free_mb": 15536.0,
                    "hbm_usage_pct": 76.293945,
                    "parser_ok": True,
                }
                for device in range(8)
            ],
        }

    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    artifact_dir = tmp_path / "run"
    prepare_artifacts(source, artifact_dir, "deepseek-test")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = run_cell(
            artifact_dir=artifact_dir,
            cell_id="short_prefill",
            base_url=f"http://127.0.0.1:{server.server_port}",
            server_pid=os.getpid(),
            sample_once=fake_sample,
            sample_interval_seconds=0.01,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert state["posts"] == 2
    assert result["status"] == "success"
    assert result["warmup_status"] == "success"
    assert result["measured_status"] == "success"
    assert result["accepted_token_delta"] == 64.0
    assert result["phase_memory_ok"] is True
    vllm_result = json.loads(
        (artifact_dir / "source" / "short_prefill" / "vllm" / "vllm_api_concurrency_result.json").read_text()
    )
    assert vllm_result["status"] == "success"
    assert len(vllm_result["rows"]) == 1


def test_msprof_analyzers_accept_named_p6_2_cell_directories(tmp_path):
    mode_dir = tmp_path / "short_prefill"
    vllm_dir = mode_dir / "vllm"
    vllm_dir.mkdir(parents=True)
    (vllm_dir / "vllm_api_concurrency_result.json").write_text(
        json.dumps({"status": "success", "rows": []}), encoding="utf-8"
    )
    root = tmp_path / "short_prefill_msprof"
    prof_file = root / "PROF_1" / "device_0" / "sqlite" / "ascend_task.db"
    prof_file.parent.mkdir(parents=True)
    prof_file.touch()
    (mode_dir / "msprof_output_files.txt").write_text(str(prof_file) + "\n")

    paths = discover_mode_paths(tmp_path, "short_prefill", None)

    assert paths.result_path == vllm_dir / "vllm_api_concurrency_result.json"
    assert paths.msprof_root is not None
    assert prof_file.is_relative_to(paths.msprof_root)


def test_finalize_profiled_evidence_requires_all_cells_aggregates_memory_and_cleanup(
    tmp_path,
):
    artifact_dir = tmp_path / "run"
    prepare_source = tmp_path / "source.json"
    prepare_source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    prepare_artifacts(prepare_source, artifact_dir, "deepseek-test")
    cells = ("short_prefill", "long_prefill", "decode_heavy")
    for cell in cells:
        cell_dir = artifact_dir / "source" / cell
        cell_dir.mkdir(parents=True, exist_ok=True)
        (cell_dir / "profiled_cell_result.json").write_text(
            json.dumps(
                {
                    "cell_id": cell,
                    "status": "success",
                    "context_tokens": 131072 if cell == "long_prefill" else 4096,
                    "output_tokens": 256 if cell == "decode_heavy" else 64,
                    "prompt_tokens": 131072 if cell == "long_prefill" else 4096,
                    "generated_token_count": 256 if cell == "decode_heavy" else 64,
                    "streamed_token_count": 256 if cell == "decode_heavy" else 64,
                    "finish_reason": "length",
                    "saw_done": True,
                    "accepted_token_delta": 1.0,
                    "counter_evidence_ok": True,
                    "phase_memory_ok": True,
                    "diagnostic_ttft_ms": 1.0,
                    "diagnostic_tpot_ms": 2.0,
                    "diagnostic_e2el_ms": 3.0,
                }
            ),
            encoding="utf-8",
        )
        (cell_dir / "profiler_exit_code.txt").write_text("0\n", encoding="utf-8")
        (cell_dir / "msprof_output_files.txt").write_text(
            f"/tmp/{cell}/device_0/sqlite/ascend_task.db\n", encoding="utf-8"
        )
        (cell_dir / "phase_memory_summary.tsv").write_text(
            "cell_id\tphase\tsample_count\tdevice_coverage_min\tparse_failure_count\n"
            f"{cell}\tprefill\t1\t8\t0\n"
            f"{cell}\tdecode\t1\t8\t0\n",
            encoding="utf-8",
        )

    analysis = artifact_dir / "analysis"
    analysis.mkdir()
    (analysis / "msprof_request_device_aggregate_result.json").write_text(
        json.dumps(
            {
                "overall_status": "success",
                "heavy_joins_skipped": False,
                "mode_summaries": [
                    {
                        "mode": cell,
                        "aggregate_status": "request_device_aggregate_available",
                        "msprof_root_exists": 1,
                        "request_device_summary_rows": 1,
                        "top_op_summary_rows": 10,
                        "metric_summary_rows": 1,
                    }
                    for cell in cells
                ],
            }
        ),
        encoding="utf-8",
    )
    (analysis / "request_top_op_type_duration.tsv").write_text(
        "mode\top_type\ttotal_duration_time\nshort_prefill\tMatMul\t1\n",
        encoding="utf-8",
    )
    (analysis / "request_ai_core_metric_summary.tsv").write_text(
        "mode\taic_total_time\nshort_prefill\t1\n", encoding="utf-8"
    )

    grading = finalize_artifacts(
        artifact_dir=artifact_dir,
        cleanup_status="clean",
        aggregate_exit=0,
    )

    assert grading["server_grade"] == "candidate_green_mtp_profiled_evidence"
    assert grading["successful_profiled_cell_count"] == 3
    assert grading["accepted_token_delta_total"] == 3.0
    assert grading["performance_reference_baseline_remains_true"] is True
    assert (artifact_dir / "profiled_cell_summary.tsv").is_file()
    assert (artifact_dir / "phase_memory_summary.tsv").is_file()
    assert (artifact_dir / "request_device_aggregate_summary.tsv").is_file()
    assert int((artifact_dir / "delivery_candidates_total_bytes.txt").read_text()) <= 71680


def test_profiled_runner_supports_direct_file_execution():
    completed = subprocess.run(
        [
            sys.executable,
            "tools/inference_contracts/run_deepseek_p6_2_profiled_evidence.py",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "prepare" in completed.stdout
    assert "run-cell" in completed.stdout
    assert "finalize" in completed.stdout


def test_request_device_aggregate_supports_direct_file_execution():
    completed = subprocess.run(
        [
            sys.executable,
            "tools/inference_contracts/analyze_msprof_request_device_aggregate.py",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--mode" in completed.stdout


def test_profiled_cell_shell_keeps_the_frozen_runtime_and_cleans_each_lifecycle():
    path = "tools/inference_contracts/run_deepseek_p6_2_profiled_cell.sh"
    completed = subprocess.run(
        ["bash", "-n", path], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    text = open(path, encoding="utf-8").read()
    assert "--tensor-parallel-size 8" in text
    assert "--enable-expert-parallel" in text
    assert "--max-num-seqs 1" in text
    assert "--speculative-config" in text
    assert "num_speculative_tokens" in text
    assert '"${RUNNER_PATH}" run-cell' in text
    assert "cleanup_cell" in text
    assert "kill -TERM -- \"-${server_pid}\"" in text
