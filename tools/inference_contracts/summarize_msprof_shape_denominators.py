from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_MODES = ("msprof_prefix_cache_on", "msprof_prefix_cache_off")
DEFAULT_RUN_ID = "runtime_vllm_api_msprof_shape_denominators_2026_0708_p1_029"
POLICY = "shape_derived_denominator_no_hbm_bandwidth_or_bottleneck_claim"

DTYPE_BYTES = {
    "bool": 1,
    "int8": 1,
    "uint8": 1,
    "float8": 1,
    "bfloat16": 2,
    "bf16": 2,
    "float16": 2,
    "fp16": 2,
    "half": 2,
    "int16": 2,
    "uint16": 2,
    "float32": 4,
    "fp32": 4,
    "float": 4,
    "int32": 4,
    "uint32": 4,
    "float64": 8,
    "double": 8,
    "int64": 8,
    "uint64": 8,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize msprof op shapes into FLOPs/bytes denominator candidates."
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--source-artifact-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--msprof-root-on", type=Path, required=True)
    parser.add_argument("--msprof-root-off", type=Path, required=True)
    parser.add_argument("--mode", action="append", choices=DEFAULT_MODES, default=None)
    parser.add_argument("--top-limit", type=int, default=80)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = summarize_shape_denominators(
        run_id=args.run_id,
        source_artifact_dir=args.source_artifact_dir,
        artifact_dir=args.artifact_dir,
        msprof_roots={
            "msprof_prefix_cache_on": args.msprof_root_on,
            "msprof_prefix_cache_off": args.msprof_root_off,
        },
        modes=tuple(args.mode or DEFAULT_MODES),
        top_limit=args.top_limit,
    )
    return 0 if result["overall_status"] == "success" else 1


def summarize_shape_denominators(
    *,
    run_id: str,
    source_artifact_dir: Path,
    artifact_dir: Path,
    msprof_roots: dict[str, Path],
    modes: tuple[str, ...] = DEFAULT_MODES,
    top_limit: int = 80,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shape_rows: list[dict[str, Any]] = []
    mode_summaries: list[dict[str, Any]] = []

    for mode in modes:
        result_path = find_result_path(source_artifact_dir, mode)
        requests = load_request_windows(result_path)
        ai_core_db = find_ai_core_op_summary_db(msprof_roots[mode])
        if not requests or ai_core_db is None:
            mode_summaries.append(
                {
                    "mode": mode,
                    "result_path": str(result_path or ""),
                    "request_count": len(requests),
                    "ai_core_op_summary_db": str(ai_core_db or ""),
                    "shape_row_count": 0,
                    "status": "missing_request_windows_or_ai_core_db",
                }
            )
            continue
        mode_rows = query_shape_rows(mode=mode, db_path=ai_core_db, requests=requests, top_limit=top_limit)
        shape_rows.extend(mode_rows)
        mode_summaries.append(
            {
                "mode": mode,
                "result_path": str(result_path or ""),
                "request_count": len(requests),
                "ai_core_op_summary_db": str(ai_core_db),
                "shape_row_count": len(mode_rows),
                "status": "success" if mode_rows else "no_shape_rows",
            }
        )

    op_rows = summarize_by_op_type(shape_rows)
    unit_rows = build_unit_mapping_rows()
    mapping_rows = build_hardware_mapping_rows(op_rows)

    write_tsv(artifact_dir / "msprof_shape_denominator_summary.tsv", shape_rows)
    write_tsv(artifact_dir / "msprof_shape_denominator_by_op_type.tsv", op_rows)
    write_tsv(artifact_dir / "msprof_unit_mapping.tsv", unit_rows)
    write_tsv(artifact_dir / "hardware_denominator_mapping.tsv", mapping_rows)

    overall_status = "success" if shape_rows and all(row["status"] == "success" for row in mode_summaries) else "failed"
    result = {
        "run_id": run_id,
        "source_artifact_dir": str(source_artifact_dir),
        "artifact_dir": str(artifact_dir),
        "overall_status": overall_status,
        "mode_summaries": mode_summaries,
        "shape_row_count": len(shape_rows),
        "op_type_row_count": len(op_rows),
        "policy": POLICY,
        "flops_policy": "matmul_flops_estimated_from_msprof_shapes_when_available",
        "bytes_policy": "input_output_tensor_footprint_not_hbm_traffic",
        "duration_policy": "raw_msprof_duration_time_not_user_latency",
        "bottleneck_policy": "no_bottleneck_claim_without_hbm_bytes_utilization_and_request_token_join",
    }
    (artifact_dir / "msprof_shape_denominator_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(artifact_dir / "summary.txt", result, op_rows)
    write_mail_attachment_candidates(artifact_dir)
    return result


def find_result_path(source_artifact_dir: Path, mode: str) -> Path | None:
    candidates = [
        source_artifact_dir / mode / "vllm" / "vllm_api_streaming_perf_result.json",
        source_artifact_dir / mode / "vllm_api_streaming_perf_result.json",
        source_artifact_dir / mode / "vllm" / "vllm_api_concurrency_result.json",
        source_artifact_dir / mode / "vllm_api_concurrency_result.json",
    ]
    return next((path for path in candidates if path.is_file()), None)


def load_request_windows(result_path: Path | None) -> list[dict[str, Any]]:
    if result_path is None or not result_path.is_file():
        return []
    data = json.loads(result_path.read_text(encoding="utf-8"))
    requests = []
    for row in data.get("rows", []):
        start_ns = int_value(row.get("request_start_ns"))
        end_ns = int_value(row.get("response_end_ns"))
        if not start_ns or end_ns <= start_ns:
            continue
        requests.append(
            {
                "case_id": row.get("case_id", ""),
                "prompt_id": row.get("prompt_id", ""),
                "prefix_reuse_group": row.get("prefix_reuse_group", ""),
                "request_start_ns": start_ns,
                "response_end_ns": end_ns,
                "input_token_count": row.get("input_token_count", ""),
                "generated_token_count": row.get("generated_token_count", ""),
                "status": row.get("status", ""),
            }
        )
    return requests


def find_ai_core_op_summary_db(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = sorted(root.rglob("ai_core_op_summary.db"))
    return candidates[0] if candidates else None


def query_shape_rows(
    *,
    mode: str,
    db_path: Path,
    requests: list[dict[str, Any]],
    top_limit: int,
) -> list[dict[str, Any]]:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"task_time", "ge_summary"}.issubset(tables):
            return []
        conn.execute("PRAGMA automatic_index = ON")
        conn.execute("PRAGMA temp_store = MEMORY")
        prepare_request_window_table(conn, requests)
        prepare_overlap_task_table(conn)
        prepare_ge_summary_join_table(conn)
        sql = """
            SELECT
              g.op_type AS op_type,
              MIN(g.op_name) AS op_name_sample,
              g.input_data_types AS input_data_types,
              g.input_shapes AS input_shapes,
              g.output_data_types AS output_data_types,
              g.output_shapes AS output_shapes,
              COUNT(*) AS occurrence_count,
              COUNT(DISTINCT o.request_index) AS request_count,
              SUM(o.duration_time_i) AS duration_time_raw_sum
            FROM overlap_task AS o
            JOIN ge_summary_join AS g
              ON o.model_id_t = g.model_id_t
             AND o.task_id_t = g.task_id_t
             AND o.stream_id_t = g.stream_id_t
             AND o.batch_id_t = g.batch_id_t
             AND o.index_id_t = g.index_id_t
            GROUP BY
              g.op_type,
              g.input_data_types,
              g.input_shapes,
              g.output_data_types,
              g.output_shapes
            ORDER BY SUM(o.duration_time_i) DESC
            LIMIT ?
        """
        rows = []
        for row in conn.execute(sql, (max(1, top_limit),)):
            estimate = estimate_denominators(
                op_type=row["op_type"] or "",
                input_shapes=row["input_shapes"] or "",
                output_shapes=row["output_shapes"] or "",
                input_data_types=row["input_data_types"] or "",
                output_data_types=row["output_data_types"] or "",
            )
            occurrence_count = int_value(row["occurrence_count"])
            rows.append(
                {
                    "mode": mode,
                    "op_type": row["op_type"] or "",
                    "op_name_sample": row["op_name_sample"] or "",
                    "input_data_types": row["input_data_types"] or "",
                    "input_shapes": row["input_shapes"] or "",
                    "output_data_types": row["output_data_types"] or "",
                    "output_shapes": row["output_shapes"] or "",
                    "occurrence_count": occurrence_count,
                    "request_count": int_value(row["request_count"]),
                    "duration_time_raw_sum": int_value(row["duration_time_raw_sum"]),
                    "estimated_flops_per_occurrence": estimate["flops_per_occurrence"],
                    "estimated_flops_total": multiply_optional(estimate["flops_per_occurrence"], occurrence_count),
                    "estimated_tensor_bytes_per_occurrence": estimate["tensor_bytes_per_occurrence"],
                    "estimated_tensor_bytes_total": multiply_optional(
                        estimate["tensor_bytes_per_occurrence"],
                        occurrence_count,
                    ),
                    "denominator_status": estimate["status"],
                    "policy": POLICY,
                }
            )
        return rows


def prepare_request_window_table(conn: sqlite3.Connection, requests: list[dict[str, Any]]) -> None:
    conn.execute("DROP TABLE IF EXISTS temp.request_windows")
    conn.execute(
        """
        CREATE TEMP TABLE request_windows(
          request_index INTEGER PRIMARY KEY,
          case_id TEXT,
          prompt_id TEXT,
          prefix_reuse_group TEXT,
          request_start_ns INTEGER,
          response_end_ns INTEGER,
          input_token_count TEXT,
          generated_token_count TEXT,
          status TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO request_windows(
          request_index, case_id, prompt_id, prefix_reuse_group,
          request_start_ns, response_end_ns, input_token_count, generated_token_count, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                index,
                request["case_id"],
                request["prompt_id"],
                request["prefix_reuse_group"],
                request["request_start_ns"],
                request["response_end_ns"],
                request["input_token_count"],
                request["generated_token_count"],
                request["status"],
            )
            for index, request in enumerate(requests)
        ],
    )


def prepare_overlap_task_table(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS temp.overlap_task")
    conn.execute(
        """
        CREATE TEMP TABLE overlap_task AS
        SELECT
          r.request_index,
          CAST(t.start_time AS INTEGER) AS start_time_i,
          CAST(t.duration_time AS INTEGER) AS duration_time_i,
          CAST(t.task_id AS TEXT) AS task_id_t,
          CAST(t.stream_id AS TEXT) AS stream_id_t,
          CAST(t.batch_id AS TEXT) AS batch_id_t,
          CAST(t.model_id AS TEXT) AS model_id_t,
          CAST(t.index_id AS TEXT) AS index_id_t
        FROM request_windows AS r
        JOIN task_time AS t
          ON CAST(t.start_time AS INTEGER) < r.response_end_ns
         AND CAST(t.start_time AS INTEGER) + CAST(t.duration_time AS INTEGER) > r.request_start_ns
        """
    )
    conn.execute(
        "CREATE INDEX temp.idx_overlap_task_ge ON overlap_task("
        "model_id_t, task_id_t, stream_id_t, batch_id_t, index_id_t)"
    )


def prepare_ge_summary_join_table(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS temp.ge_summary_join")
    conn.execute(
        """
        CREATE TEMP TABLE ge_summary_join AS
        SELECT
          CAST(model_id AS TEXT) AS model_id_t,
          CAST(task_id AS TEXT) AS task_id_t,
          CAST(stream_id AS TEXT) AS stream_id_t,
          CAST(batch_id AS TEXT) AS batch_id_t,
          CAST(index_id AS TEXT) AS index_id_t,
          COALESCE(CAST(op_name AS TEXT), '') AS op_name,
          COALESCE(CAST(op_type AS TEXT), '') AS op_type,
          COALESCE(CAST(input_data_types AS TEXT), '') AS input_data_types,
          COALESCE(CAST(input_shapes AS TEXT), '') AS input_shapes,
          COALESCE(CAST(output_data_types AS TEXT), '') AS output_data_types,
          COALESCE(CAST(output_shapes AS TEXT), '') AS output_shapes
        FROM ge_summary
        """
    )
    conn.execute(
        "CREATE INDEX temp.idx_ge_summary_join ON ge_summary_join("
        "model_id_t, task_id_t, stream_id_t, batch_id_t, index_id_t)"
    )


def estimate_denominators(
    *,
    op_type: str,
    input_shapes: str,
    output_shapes: str,
    input_data_types: str,
    output_data_types: str,
) -> dict[str, Any]:
    input_groups = parse_shape_groups(input_shapes)
    output_groups = parse_shape_groups(output_shapes)
    input_dtypes = parse_dtype_tokens(input_data_types)
    output_dtypes = parse_dtype_tokens(output_data_types)
    tensor_bytes = estimate_tensor_bytes(input_groups, input_dtypes) + estimate_tensor_bytes(output_groups, output_dtypes)
    flops = estimate_flops(op_type, input_groups, output_groups)
    if flops:
        status = "estimated_matmul_flops_and_tensor_footprint"
    elif tensor_bytes:
        status = "estimated_tensor_footprint_only"
    else:
        status = "shape_or_dtype_unavailable"
    return {
        "flops_per_occurrence": flops or "",
        "tensor_bytes_per_occurrence": tensor_bytes or "",
        "status": status,
    }


def parse_shape_groups(text: str) -> list[list[int]]:
    if not text:
        return []
    groups: list[list[int]] = []
    for match in re.finditer(r"\[[^\[\]]+\]|\([^\(\)]+\)", text):
        numbers = [int(token) for token in re.findall(r"-?\d+", match.group(0)) if int(token) > 0]
        if numbers:
            groups.append(numbers)
    if groups:
        return groups
    parts = [part for part in re.split(r"[;|]", text) if part.strip()]
    for part in parts:
        numbers = [int(token) for token in re.findall(r"-?\d+", part) if int(token) > 0]
        if numbers:
            groups.append(numbers)
    if groups:
        return groups
    numbers = [int(token) for token in re.findall(r"-?\d+", text) if int(token) > 0]
    return [numbers] if numbers else []


def parse_dtype_tokens(text: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", text or ""):
        normalized = normalize_dtype(token)
        if normalized:
            tokens.append(normalized)
    return tokens


def normalize_dtype(token: str) -> str:
    item = token.lower()
    if item.startswith("dt_"):
        item = item[3:]
    item = item.replace("acl_", "")
    if item in {"float", "float32", "fp32"}:
        return "float32"
    if item in {"float16", "fp16", "half"}:
        return "float16"
    if item in {"bfloat16", "bf16"}:
        return "bfloat16"
    if item in DTYPE_BYTES:
        return item
    return ""


def estimate_tensor_bytes(shape_groups: list[list[int]], dtype_tokens: list[str]) -> int:
    total = 0
    for index, shape in enumerate(shape_groups):
        dtype = dtype_tokens[index] if index < len(dtype_tokens) else (dtype_tokens[-1] if dtype_tokens else "")
        bytes_per_element = DTYPE_BYTES.get(dtype, 0)
        if bytes_per_element:
            total += product(shape) * bytes_per_element
    return total


def estimate_flops(op_type: str, input_groups: list[list[int]], output_groups: list[list[int]]) -> int:
    op = op_type.lower()
    if "matmul" not in op and "batchmatmul" not in op:
        return 0
    if output_groups and input_groups and len(input_groups[0]) >= 1:
        k_dim = input_groups[0][-1]
        return 2 * k_dim * product(output_groups[0])
    if len(input_groups) >= 2 and len(input_groups[0]) >= 2 and len(input_groups[1]) >= 2:
        left = input_groups[0]
        right = input_groups[1]
        m_total = product(left[:-1])
        k_dim = left[-1]
        n_dim = right[-1]
        return 2 * m_total * k_dim * n_dim
    return 0


def summarize_by_op_type(shape_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    for row in shape_rows:
        key = (row["mode"], row["op_type"])
        item = grouped[key]
        item["mode"] = row["mode"]
        item["op_type"] = row["op_type"]
        item["shape_variant_count"] += 1
        item["occurrence_count"] += int_value(row["occurrence_count"])
        item["request_count_max"] = max(int_value(item["request_count_max"]), int_value(row["request_count"]))
        item["duration_time_raw_sum"] += int_value(row["duration_time_raw_sum"])
        item["estimated_flops_total"] += int_value(row["estimated_flops_total"])
        item["estimated_tensor_bytes_total"] += int_value(row["estimated_tensor_bytes_total"])
    rows = []
    for item in grouped.values():
        flops_status = "available" if item["estimated_flops_total"] else "missing"
        bytes_status = "available" if item["estimated_tensor_bytes_total"] else "missing"
        rows.append(
            {
                "mode": item["mode"],
                "op_type": item["op_type"],
                "shape_variant_count": item["shape_variant_count"],
                "occurrence_count": item["occurrence_count"],
                "request_count_max": item["request_count_max"],
                "duration_time_raw_sum": item["duration_time_raw_sum"],
                "estimated_flops_total": item["estimated_flops_total"],
                "estimated_tensor_bytes_total": item["estimated_tensor_bytes_total"],
                "flops_denominator_status": flops_status,
                "bytes_denominator_status": bytes_status,
                "policy": POLICY,
            }
        )
    return sorted(rows, key=lambda row: row["duration_time_raw_sum"], reverse=True)


def build_unit_mapping_rows() -> list[dict[str, Any]]:
    return [
        {
            "metric": "request_start_ns,response_end_ns,first_token_ns",
            "source": "client time.monotonic_ns",
            "unit": "ns",
            "confidence": "HIGH",
            "boundary": "host client wall-clock; not device execution time",
        },
        {
            "metric": "ttft_us,tpot_us,client_wall_us",
            "source": "streaming client derived fields",
            "unit": "us",
            "confidence": "HIGH",
            "boundary": "user-visible client metric; affected by server/client/profiler mode",
        },
        {
            "metric": "task_time.start_time,duration_time",
            "source": "msprof ai_core_op_summary.db task_time",
            "unit": "raw profiler time column",
            "confidence": "MEDIUM",
            "boundary": "used for overlap/grouping; do not publish as wall latency without unit confirmation",
        },
        {
            "metric": "ai_core_metrics.*_time,*_ratio",
            "source": "msprof ai_core_metrics",
            "unit": "raw CANN metric",
            "confidence": "LOW",
            "boundary": "raw counter only; no utilization/bottleneck claim without denominator",
        },
        {
            "metric": "input_shapes,output_shapes,input_data_types,output_data_types",
            "source": "msprof ge_summary",
            "unit": "tensor shape and dtype strings",
            "confidence": "HIGH",
            "boundary": "sufficient for tensor footprint and selected MatMul FLOPs estimates",
        },
    ]


def build_hardware_mapping_rows(op_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in op_rows:
        op_type = row["op_type"]
        if "matmul" in op_type.lower():
            rows.append(
                {
                    "mode": row["mode"],
                    "runtime_metric": f"{op_type} shape-derived FLOPs",
                    "hardware_ceiling_metric": "P0/P3 FP16 square matmul observed ceiling 290.448949 TFLOPS",
                    "comparability": "PARTIALLY_COMPARABLE",
                    "denominator_available": int(row["estimated_flops_total"] > 0),
                    "missing_for_claim": "runtime dtype confirmation, exact duration unit, non-overlapped op time, hardware peak by actual shape",
                    "policy": POLICY,
                }
            )
        if row["estimated_tensor_bytes_total"]:
            rows.append(
                {
                    "mode": row["mode"],
                    "runtime_metric": f"{op_type} input/output tensor footprint",
                    "hardware_ceiling_metric": "HBM bandwidth ceiling",
                    "comparability": "NOT_COMPARABLE",
                    "denominator_available": 1,
                    "missing_for_claim": "HBM read/write bytes, cache reuse, MTE traffic, bandwidth counter and utilization denominator",
                    "policy": POLICY,
                }
            )
    return rows


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, result: dict[str, Any], op_rows: list[dict[str, Any]]) -> None:
    lines = [
        f"run_id={result['run_id']}",
        f"overall_status={result['overall_status']}",
        f"shape_row_count={result['shape_row_count']}",
        f"op_type_row_count={result['op_type_row_count']}",
        f"policy={result['policy']}",
        f"flops_policy={result['flops_policy']}",
        f"bytes_policy={result['bytes_policy']}",
        f"duration_policy={result['duration_policy']}",
        f"bottleneck_policy={result['bottleneck_policy']}",
        "",
        "## mode_summaries",
    ]
    for row in result["mode_summaries"]:
        lines.append(
            "\t".join(
                [
                    row["mode"],
                    row["status"],
                    f"requests={row['request_count']}",
                    f"shape_rows={row['shape_row_count']}",
                    row["ai_core_op_summary_db"],
                ]
            )
        )
    lines.append("")
    lines.append("## top_op_type_denominators")
    for row in op_rows[:12]:
        lines.append(
            "\t".join(
                [
                    row["mode"],
                    row["op_type"],
                    f"occurrences={row['occurrence_count']}",
                    f"flops_total={row['estimated_flops_total']}",
                    f"tensor_bytes_total={row['estimated_tensor_bytes_total']}",
                ]
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mail_attachment_candidates(artifact_dir: Path) -> None:
    relpaths = [
        "summary.txt",
        "msprof_shape_denominator_result.json",
        "msprof_shape_denominator_summary.tsv",
        "msprof_shape_denominator_by_op_type.tsv",
        "msprof_unit_mapping.tsv",
        "hardware_denominator_mapping.tsv",
    ]
    lines = ["path\tsize_bytes\tmail_ok"]
    for relpath in relpaths:
        path = artifact_dir / relpath
        if not path.exists():
            continue
        size = path.stat().st_size
        lines.append(f"{path}\t{size}\t{str(size <= 70 * 1024).lower()}")
    (artifact_dir / "mail_attachment_candidates.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def product(values: list[int]) -> int:
    return math.prod(int(value) for value in values if int(value) > 0)


def multiply_optional(value: Any, factor: int) -> Any:
    if value in {"", None}:
        return ""
    return int_value(value) * factor


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
