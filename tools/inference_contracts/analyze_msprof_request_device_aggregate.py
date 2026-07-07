from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from tools.inference_contracts.analyze_msprof_sqlite_windows import (
    DEFAULT_ARTIFACT_ROOT,
    DEFAULT_MODES,
    DEFAULT_SOURCE_RUN_ID,
    discover_mode_paths,
    load_request_windows,
    quote_identifier,
    safe_int,
    write_tsv,
)


DEFAULT_RUN_ID = "runtime_vllm_api_msprof_request_device_aggregate_2026_0707_p1_025"
DEFAULT_TOP_N_OP_TYPES = 20
SUMMARY_METRIC_COLUMNS = (
    "aic_total_time",
    "aiv_total_time",
    "aic_mac_time",
    "aic_scalar_time",
    "aic_mte1_time",
    "aic_mte2_time",
    "aic_fixpipe_time",
    "aiv_vec_time",
    "aiv_scalar_time",
    "aiv_mte2_time",
    "aiv_mte3_time",
)
AVG_METRIC_COLUMNS = (
    "aic_mac_ratio_extra",
    "aic_scalar_ratio",
    "aic_mte1_ratio_extra",
    "aic_mte2_ratio",
    "aic_fixpipe_ratio",
    "aiv_vec_ratio",
    "aiv_scalar_ratio",
    "aiv_mte2_ratio",
    "aiv_mte3_ratio",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate direct-overlap msprof device rows by vLLM API request window."
    )
    parser.add_argument("--run-id", default=os.environ.get("RUN_ID", DEFAULT_RUN_ID))
    parser.add_argument(
        "--source-artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT / DEFAULT_SOURCE_RUN_ID,
        help="Artifact directory containing vLLM API result JSON and msprof_output_files.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to runtime_trace_smokes/<run-id>.",
    )
    parser.add_argument("--msprof-root-on", type=Path, default=None)
    parser.add_argument("--msprof-root-off", type=Path, default=None)
    parser.add_argument("--mode", action="append", choices=DEFAULT_MODES, default=None)
    parser.add_argument("--top-n-op-types", type=int, default=DEFAULT_TOP_N_OP_TYPES)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_dir = args.artifact_dir or (DEFAULT_ARTIFACT_ROOT / args.run_id)
    result = analyze_request_device_aggregate(
        run_id=args.run_id,
        source_artifact_dir=args.source_artifact_dir,
        artifact_dir=artifact_dir,
        modes=tuple(args.mode or DEFAULT_MODES),
        explicit_roots={
            "msprof_prefix_cache_on": args.msprof_root_on,
            "msprof_prefix_cache_off": args.msprof_root_off,
        },
        top_n_op_types=args.top_n_op_types,
    )
    return 0 if result["overall_status"] != "failed" else 1


def analyze_request_device_aggregate(
    *,
    run_id: str,
    source_artifact_dir: Path,
    artifact_dir: Path,
    modes: tuple[str, ...] = DEFAULT_MODES,
    explicit_roots: dict[str, Path | None] | None = None,
    top_n_op_types: int = DEFAULT_TOP_N_OP_TYPES,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    explicit_roots = explicit_roots or {}

    mode_summaries: list[dict[str, Any]] = []
    request_device_rows: list[dict[str, Any]] = []
    task_type_rows: list[dict[str, Any]] = []
    top_op_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []

    for mode in modes:
        paths = discover_mode_paths(source_artifact_dir, mode, explicit_roots.get(mode))
        requests, result_status = load_request_windows(paths.result_path)
        db_paths = discover_device_databases(paths.msprof_root)

        if db_paths["ai_core_op_summary"]:
            aggregate_ai_core_database(
                mode=mode,
                db_path=db_paths["ai_core_op_summary"],
                requests=requests,
                top_n_op_types=top_n_op_types,
                request_device_rows=request_device_rows,
                task_type_rows=task_type_rows,
                top_op_rows=top_op_rows,
                metric_rows=metric_rows,
            )
        if db_paths["ascend_task"]:
            aggregate_ascend_task_database(
                mode=mode,
                db_path=db_paths["ascend_task"],
                requests=requests,
                task_type_rows=task_type_rows,
            )

        mode_request_rows = [row for row in request_device_rows if row["mode"] == mode]
        mode_summaries.append(
            {
                "mode": mode,
                "result_path": str(paths.result_path or ""),
                "result_status": result_status,
                "request_count": len(requests),
                "successful_request_count": sum(1 for row in requests if row["status"] == "success"),
                "msprof_root": str(paths.msprof_root or ""),
                "msprof_root_exists": int(bool(paths.msprof_root and paths.msprof_root.exists())),
                "ai_core_op_summary_db": str(db_paths["ai_core_op_summary"] or ""),
                "ascend_task_db": str(db_paths["ascend_task"] or ""),
                "request_device_summary_rows": len(mode_request_rows),
                "top_op_summary_rows": sum(1 for row in top_op_rows if row["mode"] == mode),
                "metric_summary_rows": sum(1 for row in metric_rows if row["mode"] == mode),
                "aggregate_status": (
                    "request_device_aggregate_available"
                    if mode_request_rows
                    else "missing_direct_overlap_device_tables"
                ),
            }
        )

    mode_delta_rows = build_prefix_cache_mode_deltas(request_device_rows)
    pair_delta_rows = build_prefix_pair_deltas(request_device_rows)

    write_tsv(artifact_dir / "request_device_task_summary.tsv", request_device_rows)
    write_tsv(artifact_dir / "request_device_task_type_summary.tsv", task_type_rows)
    write_tsv(artifact_dir / "request_top_op_type_duration.tsv", top_op_rows)
    write_tsv(artifact_dir / "request_ai_core_metric_summary.tsv", metric_rows)
    write_tsv(artifact_dir / "prefix_cache_mode_request_delta.tsv", mode_delta_rows)
    write_tsv(artifact_dir / "prefix_pair_candidate_delta.tsv", pair_delta_rows)

    overall_status = (
        "success"
        if mode_summaries and all(row["aggregate_status"] == "request_device_aggregate_available" for row in mode_summaries)
        else "failed"
    )
    result = {
        "run_id": run_id,
        "source_artifact_dir": str(source_artifact_dir),
        "artifact_dir": str(artifact_dir),
        "overall_status": overall_status,
        "mode_summaries": mode_summaries,
        "policy": "evidence_extraction_only_no_benchmark_or_bottleneck_claim",
    }
    (artifact_dir / "msprof_request_device_aggregate_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(artifact_dir / "summary.txt", result)
    return result


def discover_device_databases(msprof_root: Path | None) -> dict[str, Path | None]:
    names = {
        "ai_core_op_summary": "ai_core_op_summary.db",
        "ascend_task": "ascend_task.db",
    }
    found: dict[str, Path | None] = {key: None for key in names}
    if not msprof_root or not msprof_root.exists():
        return found
    for key, name in names.items():
        candidates = sorted(msprof_root.rglob(name))
        found[key] = candidates[0] if candidates else None
    return found


def aggregate_ai_core_database(
    *,
    mode: str,
    db_path: Path,
    requests: list[dict[str, Any]],
    top_n_op_types: int,
    request_device_rows: list[dict[str, Any]],
    task_type_rows: list[dict[str, Any]],
    top_op_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
) -> None:
    with open_readonly(db_path) as conn:
        tables = set(list_tables(conn))
        if "task_time" not in tables:
            return
        task_columns = set(list_columns(conn, "task_time"))
        if not {"start_time", "duration_time"}.issubset(task_columns):
            return

        has_ge = "ge_summary" in tables
        has_metrics = "ai_core_metrics" in tables
        ge_columns = set(list_columns(conn, "ge_summary")) if has_ge else set()
        metric_columns = set(list_columns(conn, "ai_core_metrics")) if has_metrics else set()

        for request in requests:
            summary = query_task_time_summary(conn, mode, db_path, request)
            request_device_rows.append(summary)
            task_type_rows.extend(query_task_type_summary(conn, mode, db_path, request))
            if has_ge and "op_type" in ge_columns:
                top_op_rows.extend(query_top_op_types(conn, mode, db_path, request, top_n_op_types))
            if has_metrics:
                metric_rows.append(query_metric_summary(conn, mode, db_path, request, metric_columns))


def aggregate_ascend_task_database(
    *,
    mode: str,
    db_path: Path,
    requests: list[dict[str, Any]],
    task_type_rows: list[dict[str, Any]],
) -> None:
    with open_readonly(db_path) as conn:
        if "AscendTask" not in set(list_tables(conn)):
            return
        columns = set(list_columns(conn, "AscendTask"))
        if not {"start_time", "duration"}.issubset(columns):
            return
        for request in requests:
            for column in ("device_task_type", "host_task_type"):
                if column not in columns:
                    continue
                task_type_rows.extend(query_ascend_task_type_summary(conn, mode, db_path, request, column))


def query_task_time_summary(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    sql = """
        SELECT
          COUNT(*) AS task_row_count,
          MIN(CAST(start_time AS INTEGER)) AS min_start_time,
          MAX(CAST(start_time AS INTEGER) + CAST(duration_time AS INTEGER)) AS max_end_time,
          SUM(CAST(duration_time AS INTEGER)) AS total_duration_time,
          SUM(CAST(wait_time AS INTEGER)) AS total_wait_time,
          COUNT(DISTINCT CAST(stream_id AS TEXT)) AS distinct_stream_count,
          COUNT(DISTINCT CAST(task_id AS TEXT)) AS distinct_task_id_count
        FROM task_time
        WHERE CAST(start_time AS INTEGER) < ?
          AND CAST(start_time AS INTEGER) + CAST(duration_time AS INTEGER) > ?
    """
    row = conn.execute(sql, (request["response_end_ns"], request["request_start_ns"])).fetchone()
    return {
        "mode": mode,
        "db_path": str(db_path),
        "case_id": request["case_id"],
        "prompt_id": request["prompt_id"],
        "prefix_reuse_group": request["prefix_reuse_group"],
        "arrival_delay_ms": request["arrival_delay_ms"],
        "cap_tokens": request["cap_tokens"],
        "max_new_tokens": request["max_new_tokens"],
        "input_token_count": request["input_token_count"],
        "generated_token_count": request["generated_token_count"],
        "request_start_ns": request["request_start_ns"],
        "response_end_ns": request["response_end_ns"],
        "client_wall_us": request["client_wall_us"],
        "task_row_count": safe_int(row["task_row_count"]),
        "min_start_time": safe_int(row["min_start_time"]),
        "max_end_time": safe_int(row["max_end_time"]),
        "total_duration_time": safe_int(row["total_duration_time"]),
        "total_wait_time": safe_int(row["total_wait_time"]),
        "distinct_stream_count": safe_int(row["distinct_stream_count"]),
        "distinct_task_id_count": safe_int(row["distinct_task_id_count"]),
        "status": request["status"],
    }


def query_task_type_summary(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    if "task_type" not in set(list_columns(conn, "task_time")):
        return []
    sql = """
        SELECT CAST(task_type AS TEXT) AS value, COUNT(*) AS task_row_count,
               SUM(CAST(duration_time AS INTEGER)) AS total_duration_time
        FROM task_time
        WHERE CAST(start_time AS INTEGER) < ?
          AND CAST(start_time AS INTEGER) + CAST(duration_time AS INTEGER) > ?
        GROUP BY value
        ORDER BY task_row_count DESC
    """
    return [
        {
            "mode": mode,
            "db_path": str(db_path),
            "table": "task_time",
            "group_column": "task_type",
            "group_value": row["value"],
            "case_id": request["case_id"],
            "prompt_id": request["prompt_id"],
            "prefix_reuse_group": request["prefix_reuse_group"],
            "task_row_count": safe_int(row["task_row_count"]),
            "total_duration_time": safe_int(row["total_duration_time"]),
        }
        for row in conn.execute(sql, (request["response_end_ns"], request["request_start_ns"]))
    ]


def query_ascend_task_type_summary(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    request: dict[str, Any],
    column: str,
) -> list[dict[str, Any]]:
    column_q = quote_identifier(column)
    sql = f"""
        SELECT CAST({column_q} AS TEXT) AS value, COUNT(*) AS task_row_count,
               SUM(CAST(duration AS INTEGER)) AS total_duration_time
        FROM AscendTask
        WHERE CAST(start_time AS INTEGER) < ?
          AND CAST(start_time AS INTEGER) + CAST(duration AS INTEGER) > ?
        GROUP BY value
        ORDER BY task_row_count DESC
    """
    return [
        {
            "mode": mode,
            "db_path": str(db_path),
            "table": "AscendTask",
            "group_column": column,
            "group_value": row["value"],
            "case_id": request["case_id"],
            "prompt_id": request["prompt_id"],
            "prefix_reuse_group": request["prefix_reuse_group"],
            "task_row_count": safe_int(row["task_row_count"]),
            "total_duration_time": safe_int(row["total_duration_time"]),
        }
        for row in conn.execute(sql, (request["response_end_ns"], request["request_start_ns"]))
    ]


def query_top_op_types(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    request: dict[str, Any],
    top_n_op_types: int,
) -> list[dict[str, Any]]:
    sql = """
        SELECT COALESCE(CAST(g.op_type AS TEXT), '') AS op_type,
               COUNT(*) AS task_row_count,
               SUM(CAST(t.duration_time AS INTEGER)) AS total_duration_time,
               SUM(CAST(t.wait_time AS INTEGER)) AS total_wait_time
        FROM task_time AS t
        LEFT JOIN ge_summary AS g
          ON CAST(t.model_id AS TEXT) = CAST(g.model_id AS TEXT)
         AND CAST(t.task_id AS TEXT) = CAST(g.task_id AS TEXT)
         AND CAST(t.stream_id AS TEXT) = CAST(g.stream_id AS TEXT)
         AND CAST(t.batch_id AS TEXT) = CAST(g.batch_id AS TEXT)
         AND CAST(t.index_id AS TEXT) = CAST(g.index_id AS TEXT)
        WHERE CAST(t.start_time AS INTEGER) < ?
          AND CAST(t.start_time AS INTEGER) + CAST(t.duration_time AS INTEGER) > ?
        GROUP BY op_type
        ORDER BY total_duration_time DESC, task_row_count DESC
        LIMIT ?
    """
    rows = []
    for rank, row in enumerate(
        conn.execute(sql, (request["response_end_ns"], request["request_start_ns"], top_n_op_types)),
        start=1,
    ):
        rows.append(
            {
                "mode": mode,
                "db_path": str(db_path),
                "case_id": request["case_id"],
                "prompt_id": request["prompt_id"],
                "prefix_reuse_group": request["prefix_reuse_group"],
                "rank": rank,
                "op_type": row["op_type"],
                "task_row_count": safe_int(row["task_row_count"]),
                "total_duration_time": safe_int(row["total_duration_time"]),
                "total_wait_time": safe_int(row["total_wait_time"]),
            }
        )
    return rows


def query_metric_summary(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    request: dict[str, Any],
    metric_columns: set[str],
) -> dict[str, Any]:
    sum_exprs = [
        f"SUM(CAST(m.{quote_identifier(column)} AS REAL)) AS {quote_identifier(column + '_sum')}"
        for column in SUMMARY_METRIC_COLUMNS
        if column in metric_columns
    ]
    avg_exprs = [
        f"AVG(CAST(m.{quote_identifier(column)} AS REAL)) AS {quote_identifier(column + '_avg')}"
        for column in AVG_METRIC_COLUMNS
        if column in metric_columns
    ]
    select_exprs = ["COUNT(m.task_id) AS metric_row_count", *sum_exprs, *avg_exprs]
    sql = f"""
        SELECT {", ".join(select_exprs)}
        FROM task_time AS t
        LEFT JOIN ai_core_metrics AS m
          ON CAST(t.task_id AS TEXT) = CAST(m.task_id AS TEXT)
         AND CAST(t.stream_id AS TEXT) = CAST(m.stream_id AS TEXT)
         AND CAST(t.batch_id AS TEXT) = CAST(m.batch_id AS TEXT)
         AND CAST(t.subtask_id AS TEXT) = CAST(m.subtask_id AS TEXT)
        WHERE CAST(t.start_time AS INTEGER) < ?
          AND CAST(t.start_time AS INTEGER) + CAST(t.duration_time AS INTEGER) > ?
    """
    row = conn.execute(sql, (request["response_end_ns"], request["request_start_ns"])).fetchone()
    result: dict[str, Any] = {
        "mode": mode,
        "db_path": str(db_path),
        "case_id": request["case_id"],
        "prompt_id": request["prompt_id"],
        "prefix_reuse_group": request["prefix_reuse_group"],
        "metric_row_count": safe_int(row["metric_row_count"]),
    }
    for key in row.keys():
        if key == "metric_row_count":
            continue
        result[key] = safe_number(row[key])
    return result


def build_prefix_cache_mode_deltas(request_device_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for row in request_device_rows:
        by_case.setdefault(str(row["case_id"]), {})[str(row["mode"])] = row

    rows = []
    for case_id, mode_rows in sorted(by_case.items()):
        on = mode_rows.get("msprof_prefix_cache_on")
        off = mode_rows.get("msprof_prefix_cache_off")
        if not on or not off:
            continue
        rows.append(
            {
                "case_id": case_id,
                "prompt_id": on["prompt_id"],
                "prefix_reuse_group": on["prefix_reuse_group"],
                "on_task_row_count": on["task_row_count"],
                "off_task_row_count": off["task_row_count"],
                "delta_task_row_count_on_minus_off": int(on["task_row_count"] or 0)
                - int(off["task_row_count"] or 0),
                "on_total_duration_time": on["total_duration_time"],
                "off_total_duration_time": off["total_duration_time"],
                "delta_total_duration_time_on_minus_off": int(on["total_duration_time"] or 0)
                - int(off["total_duration_time"] or 0),
                "on_total_wait_time": on["total_wait_time"],
                "off_total_wait_time": off["total_wait_time"],
                "delta_total_wait_time_on_minus_off": int(on["total_wait_time"] or 0)
                - int(off["total_wait_time"] or 0),
                "policy": "raw_counter_delta_no_performance_or_hit_rate_claim",
            }
        )
    return rows


def build_prefix_pair_deltas(request_device_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in request_device_rows:
        key = (str(row["mode"]), str(row["prefix_reuse_group"]))
        grouped.setdefault(key, []).append(row)

    rows = []
    for (mode, prefix_group), group_rows in sorted(grouped.items()):
        if prefix_group in {"", "none"} or len(group_rows) < 2:
            continue
        ordered = sorted(group_rows, key=lambda row: int(row["arrival_delay_ms"] or 0))
        first, second = ordered[0], ordered[1]
        rows.append(
            {
                "mode": mode,
                "prefix_reuse_group": prefix_group,
                "first_case_id": first["case_id"],
                "second_case_id": second["case_id"],
                "first_prompt_id": first["prompt_id"],
                "second_prompt_id": second["prompt_id"],
                "first_task_row_count": first["task_row_count"],
                "second_task_row_count": second["task_row_count"],
                "delta_task_row_count_second_minus_first": int(second["task_row_count"] or 0)
                - int(first["task_row_count"] or 0),
                "first_total_duration_time": first["total_duration_time"],
                "second_total_duration_time": second["total_duration_time"],
                "delta_total_duration_time_second_minus_first": int(second["total_duration_time"] or 0)
                - int(first["total_duration_time"] or 0),
                "policy": "prefix_pair_candidate_delta_no_prefix_cache_hit_claim",
            }
        )
    return rows


def open_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
    return [str(row[0]) for row in rows]


def list_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({quote_identifier(table)})")]


def safe_number(value: Any) -> int | float | str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return int(number)
    return round(number, 6)


def write_summary(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "## run_context",
        f"run_id={result['run_id']}",
        f"source_artifact_dir={result['source_artifact_dir']}",
        f"artifact_dir={result['artifact_dir']}",
        f"overall_status={result['overall_status']}",
        "",
        "## mode_summaries",
    ]
    for row in result["mode_summaries"]:
        lines.append(
            "\t".join(
                str(row[key])
                for key in (
                    "mode",
                    "result_status",
                    "request_count",
                    "successful_request_count",
                    "msprof_root_exists",
                    "request_device_summary_rows",
                    "top_op_summary_rows",
                    "metric_summary_rows",
                    "aggregate_status",
                )
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
