import json
import hashlib
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tools.inference_contracts.run_deepseek_p6_3a_matched_ab import (
    build_run_plan,
    execute_mode,
    finalize_artifacts,
    grade_evidence,
    prepare_artifacts,
)


def test_matched_ab_plan_covers_eight_cells_in_both_modes():
    plan = build_run_plan()

    expected_cells = {
        (4096, 64, 1),
        (4096, 256, 1),
        (4096, 256, 8),
        (65536, 64, 1),
        (65536, 64, 4),
        (65536, 256, 1),
        (131072, 64, 1),
        (131072, 256, 1),
    }
    assert len(plan) == 25
    assert sum(batch["phase"] == "warmup" for batch in plan) == 1
    assert sum(batch["phase"] == "measured" for batch in plan) == 24
    assert sum(len(batch["requests"]) for batch in plan) == 55
    assert sum(
        len(batch["requests"])
        for batch in plan
        if batch["phase"] == "measured"
    ) == 54
    assert {
        (batch["context_tokens"], batch["output_tokens"], batch["concurrency"])
        for batch in plan
        if batch["phase"] == "measured"
    } == expected_cells
    assert all(
        sum(
            batch["phase"] == "measured"
            and (
                batch["context_tokens"],
                batch["output_tokens"],
                batch["concurrency"],
            )
            == cell
            for batch in plan
        )
        == 3
        for cell in expected_cells
    )


def test_prepare_freezes_one_shared_body_set_for_both_modes(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")

    manifest = prepare_artifacts(source, tmp_path / "run", "deepseek-test")

    assert manifest["request_count"] == 55
    assert len({row["request_body_sha256"] for row in manifest["records"]}) == 55
    assert all(row["common_prefix_upper_bound_tokens"] < 128 for row in manifest["records"])
    assert manifest["modes_reuse_identical_body_bytes"] is True
    assert manifest["mode_order"] == ["mtp_off", "mtp_on"]
    assert manifest["generated_text_retained"] is False
    assert manifest["token_ids_retained"] is False


def test_grading_requires_complete_matched_modes_and_correct_mtp_activity():
    plan = build_run_plan()
    requests = [
        {
            "mode": mode,
            "phase": batch["phase"],
            "batch_id": batch["batch_id"],
            "cell_id": batch["cell_id"],
            "context_tokens": batch["context_tokens"],
            "output_tokens": batch["output_tokens"],
            "concurrency": batch["concurrency"],
            "repeat_index": batch["repeat_index"],
            "request_index": request["request_index"],
            "request_body_sha256": request["request_id"],
            "status": "success",
        }
        for mode in ("mtp_off", "mtp_on")
        for batch in plan
        for request in batch["requests"]
    ]
    batches = [
        {
            "mode": mode,
            "phase": batch["phase"],
            "cell_id": batch["cell_id"],
            "repeat_index": batch["repeat_index"],
            "status": "success",
            "queue_metrics_ok": True,
            "counter_continuity_ok": True,
            "spec_activity_ok": True,
            "accepted_token_delta": 1.0 if mode == "mtp_on" else 0.0,
        }
        for mode in ("mtp_off", "mtp_on")
        for batch in plan
    ]

    green = grade_evidence(
        requests,
        batches,
        cleanup_by_mode={"mtp_off": "clean", "mtp_on": "clean"},
    )
    assert green["server_grade"] == "candidate_green_p6_3a_mtp_matched_ab"
    assert green["measured_request_count"] == 108
    assert green["measured_batch_count"] == 48
    assert green["all_eight_cells_matched"] is True
    assert green["body_pairing_ok"] is True
    assert green["mtp_on_accepted_token_delta_total"] == 24.0

    on_rows = [
        row
        for row in requests
        if row["mode"] == "mtp_on" and row["phase"] == "measured"
    ]
    on_rows[0]["request_body_sha256"], on_rows[1]["request_body_sha256"] = (
        on_rows[1]["request_body_sha256"],
        on_rows[0]["request_body_sha256"],
    )
    reordered = grade_evidence(
        requests,
        batches,
        cleanup_by_mode={"mtp_off": "clean", "mtp_on": "clean"},
    )
    assert reordered["body_pairing_ok"] is False
    assert reordered["server_grade"] == "yellow_p6_3a_mtp_matched_ab_partial"
    on_rows[0]["request_body_sha256"], on_rows[1]["request_body_sha256"] = (
        on_rows[1]["request_body_sha256"],
        on_rows[0]["request_body_sha256"],
    )

    batches[-1]["spec_activity_ok"] = False
    inactive = grade_evidence(
        requests,
        batches,
        cleanup_by_mode={"mtp_off": "clean", "mtp_on": "clean"},
    )
    assert inactive["server_grade"] == "red_p6_3a_mtp_matched_ab_evidence_incomplete"

    batches[-1]["spec_activity_ok"] = True
    requests[-1]["status"] = "failed"
    partial = grade_evidence(
        requests,
        batches,
        cleanup_by_mode={"mtp_off": "clean", "mtp_on": "clean"},
    )
    assert partial["server_grade"] == "yellow_p6_3a_mtp_matched_ab_partial"
    assert partial["existing_p6_references_remain_true"] is True


def test_execute_mode_accepts_missing_off_counters_and_requires_on_activity(tmp_path):
    state = {"mode": "mtp_off", "drafts": 0, "draft_tokens": 0, "accepted": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_GET(self):
            if self.path == "/health":
                body = b"ok"
            elif self.path == "/metrics":
                lines = [
                    "vllm:num_requests_running 0",
                    "vllm:num_requests_waiting 0",
                ]
                if state["mode"] == "mtp_on":
                    lines.extend(
                        [
                            f"vllm:spec_decode_num_drafts_total {state['drafts']}",
                            f"vllm:spec_decode_num_draft_tokens_total {state['draft_tokens']}",
                            f"vllm:spec_decode_num_accepted_tokens_total {state['accepted']}",
                        ]
                    )
                body = ("\n".join(lines) + "\n").encode()
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
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for index in range(output):
                event = {
                    "choices": [
                        {
                            "token_ids": [index],
                            "finish_reason": "length" if index + 1 == output else None,
                        }
                    ]
                }
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
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
            if state["mode"] == "mtp_on":
                state["drafts"] += output
                state["draft_tokens"] += output
                state["accepted"] += output

    artifact_dir = tmp_path / "run"
    (artifact_dir / "bodies").mkdir(parents=True)
    body = json.dumps(
        {
            "prompt": [1, 2, 3],
            "max_tokens": 3,
            "min_tokens": 3,
            "temperature": 0.0,
            "ignore_eos": True,
            "stream": True,
            "return_token_ids": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (artifact_dir / "bodies" / "q1.json").write_bytes(body)
    plan = [
        {
            "batch_id": "warmup",
            "phase": "warmup",
            "cell_id": "warmup",
            "context_tokens": 3,
            "output_tokens": 3,
            "concurrency": 1,
            "repeat_index": 1,
            "requests": [
                {
                    "request_id": "q1",
                    "request_index": 1,
                    "body_relative_path": "bodies/q1.json",
                    "request_body_sha256": hashlib.sha256(body).hexdigest(),
                }
            ],
        }
    ]
    (artifact_dir / "run_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for mode in ("mtp_off", "mtp_on"):
            state["mode"] = mode
            assert execute_mode(
                artifact_dir,
                f"http://127.0.0.1:{server.server_port}",
                os.getpid(),
                mode,
            ) == 2
            batch = json.loads(
                (artifact_dir / "modes" / mode / "raw_batch_results.jsonl")
                .read_text()
                .splitlines()[0]
            )
            assert batch["status"] == "success"
            assert batch["queue_metrics_ok"] is True
            assert batch["spec_activity_ok"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_matched_ab_runner_supports_direct_file_execution():
    completed = subprocess.run(
        [
            sys.executable,
            "tools/inference_contracts/run_deepseek_p6_3a_matched_ab.py",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "prepare" in completed.stdout
    assert "run-mode" in completed.stdout
    assert "finalize" in completed.stdout


def test_finalize_builds_bounded_paired_evidence_for_all_eight_cells(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"prompt": list(range(4096))}), encoding="utf-8")
    artifact_dir = tmp_path / "run"
    prepare_artifacts(source, artifact_dir, "deepseek-test")
    plan = json.loads((artifact_dir / "run_plan.json").read_text())

    for mode in ("mtp_off", "mtp_on"):
        request_rows = []
        batch_rows = []
        for batch in plan:
            for request in batch["requests"]:
                request_rows.append(
                    {
                        "mode": mode,
                        "request_id": request["request_id"],
                        "batch_id": batch["batch_id"],
                        "phase": batch["phase"],
                        "cell_id": batch["cell_id"],
                        "context_tokens": batch["context_tokens"],
                        "output_tokens": batch["output_tokens"],
                        "concurrency": batch["concurrency"],
                        "repeat_index": batch["repeat_index"],
                        "request_index": request["request_index"],
                        "request_body_sha256": request["request_body_sha256"],
                        "status": "success",
                        "ttft_ms": 10.0,
                        "tpot_ms": 20.0,
                        "e2el_ms": 30.0,
                        "output_tokens_per_second": 4.0,
                    }
                )
            batch_rows.append(
                {
                    "mode": mode,
                    "batch_id": batch["batch_id"],
                    "phase": batch["phase"],
                    "cell_id": batch["cell_id"],
                    "context_tokens": batch["context_tokens"],
                    "output_tokens": batch["output_tokens"],
                    "concurrency": batch["concurrency"],
                    "repeat_index": batch["repeat_index"],
                    "status": "success",
                    "queue_metrics_ok": True,
                    "counter_continuity_ok": True,
                    "spec_activity_ok": True,
                    "accepted_token_delta": 1.0 if mode == "mtp_on" else 0.0,
                    "batch_output_tokens_per_second": 8.0,
                    "batch_requests_per_second": 1.0,
                }
            )
        mode_dir = artifact_dir / "modes" / mode
        mode_dir.mkdir(parents=True)
        (mode_dir / "raw_request_results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in request_rows),
            encoding="utf-8",
        )
        (mode_dir / "raw_batch_results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in batch_rows),
            encoding="utf-8",
        )
        (mode_dir / "cleanup_status.txt").write_text("clean\n", encoding="utf-8")
        (mode_dir / "server_command_sha256.txt").write_text(
            f"{'0' * 64}  server_command.txt\n", encoding="utf-8"
        )

    grading = finalize_artifacts(artifact_dir)

    assert grading["server_grade"] == "candidate_green_p6_3a_mtp_matched_ab"
    assert grading["candidate_size_gate_pass"] is True
    assert int((artifact_dir / "delivery_candidates_total_bytes.txt").read_text()) <= 71680
    assert len((artifact_dir / "mode_cell_summary.tsv").read_text().splitlines()) == 17
    assert len((artifact_dir / "paired_batch_summary.tsv").read_text().splitlines()) == 25
    assert "mechanism_effect_accepted: false" in (
        artifact_dir / "result_summary.md"
    ).read_text()
    for line in (artifact_dir / "delivery_candidates.tsv").read_text().splitlines()[1:]:
        path_text, size_text, digest, _sensitivity = line.split("\t")
        path = artifact_dir / path_text if not path_text.startswith("/") else type(artifact_dir)(path_text)
        assert path.stat().st_size == int(size_text)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
