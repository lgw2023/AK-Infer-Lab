from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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


DEFAULT_RUN_ID = "runtime_vllm_api_msprof_request_device_aggregate_fast_2026_0707_p1_025b"
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
    parser.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("P1_25B_SQLITE_WORKERS", "2")),
        help="Number of independent msprof modes to aggregate in parallel.",
    )
    parser.add_argument(
        "--skip-heavy-joins",
        action="store_true",
        help="Skip ge_summary and ai_core_metrics joins; still emit request and task-type summaries.",
    )
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
        workers=args.workers,
        skip_heavy_joins=args.skip_heavy_joins,
    )
    return 0 if result["overall_status"] != "failed" else 1


@dataclass
class ModeAggregate:
    mode_summary: dict[str, Any]
    request_device_rows: list[dict[str, Any]]
    task_type_rows: list[dict[str, Any]]
    top_op_rows: list[dict[str, Any]]
    metric_rows: list[dict[str, Any]]


def analyze_request_device_aggregate(
    *,
    run_id: str,
    source_artifact_dir: Path,
    artifact_dir: Path,
    modes: tuple[str, ...] = DEFAULT_MODES,
    explicit_roots: dict[str, Path | None] | None = None,
    top_n_op_types: int = DEFAULT_TOP_N_OP_TYPES,
    workers: int = 1,
    skip_heavy_joins: bool = False,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    explicit_roots = explicit_roots or {}

    mode_summaries: list[dict[str, Any]] = []
    request_device_rows: list[dict[str, Any]] = []
    task_type_rows: list[dict[str, Any]] = []
    top_op_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []

    mode_results = run_mode_aggregates(
        source_artifact_dir=source_artifact_dir,
        modes=modes,
        explicit_roots=explicit_roots,
        top_n_op_types=top_n_op_types,
        workers=workers,
        skip_heavy_joins=skip_heavy_joins,
    )
    for mode_result in mode_results:
        mode_summaries.append(mode_result.mode_summary)
        request_device_rows.extend(mode_result.request_device_rows)
        task_type_rows.extend(mode_result.task_type_rows)
        top_op_rows.extend(mode_result.top_op_rows)
        metric_rows.extend(mode_result.metric_rows)

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
        "aggregation_strategy": "bulk_temp_window_join_parallel_modes",
        "workers": max(1, workers),
        "heavy_joins_skipped": skip_heavy_joins,
        "policy": "evidence_extraction_only_no_benchmark_or_bottleneck_claim",
    }
    (artifact_dir / "msprof_request_device_aggregate_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(artifact_dir / "summary.txt", result)
    return result


def run_mode_aggregates(
    *,
    source_artifact_dir: Path,
    modes: tuple[str, ...],
    explicit_roots: dict[str, Path | None],
    top_n_op_types: int,
    workers: int,
    skip_heavy_joins: bool,
) -> list[ModeAggregate]:
    if workers > 1 and len(modes) > 1:
        results_by_mode: dict[str, ModeAggregate] = {}
        with ThreadPoolExecutor(max_workers=min(max(1, workers), len(modes))) as executor:
            futures = {
                executor.submit(
                    aggregate_mode,
                    source_artifact_dir=source_artifact_dir,
                    mode=mode,
                    explicit_root=explicit_roots.get(mode),
                    top_n_op_types=top_n_op_types,
                    skip_heavy_joins=skip_heavy_joins,
                ): mode
                for mode in modes
            }
            for future, mode in futures.items():
                results_by_mode[mode] = future.result()
        return [results_by_mode[mode] for mode in modes]
    return [
        aggregate_mode(
            source_artifact_dir=source_artifact_dir,
            mode=mode,
            explicit_root=explicit_roots.get(mode),
            top_n_op_types=top_n_op_types,
            skip_heavy_joins=skip_heavy_joins,
        )
        for mode in modes
    ]


def aggregate_mode(
    *,
    source_artifact_dir: Path,
    mode: str,
    explicit_root: Path | None,
    top_n_op_types: int,
    skip_heavy_joins: bool,
) -> ModeAggregate:
    started = time.monotonic()
    paths = discover_mode_paths(source_artifact_dir, mode, explicit_root)
    requests, result_status = load_request_windows(paths.result_path)
    db_paths = discover_device_databases(paths.msprof_root)

    request_device_rows: list[dict[str, Any]] = []
    task_type_rows: list[dict[str, Any]] = []
    top_op_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []

    if db_paths["ai_core_op_summary"]:
        aggregate_ai_core_database(
            mode=mode,
            db_path=db_paths["ai_core_op_summary"],
            requests=requests,
            top_n_op_types=top_n_op_types,
            skip_heavy_joins=skip_heavy_joins,
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

    mode_summary = {
        "mode": mode,
        "result_path": str(paths.result_path or ""),
        "result_status": result_status,
        "request_count": len(requests),
        "successful_request_count": sum(1 for row in requests if row["status"] == "success"),
        "msprof_root": str(paths.msprof_root or ""),
        "msprof_root_exists": int(bool(paths.msprof_root and paths.msprof_root.exists())),
        "ai_core_op_summary_db": str(db_paths["ai_core_op_summary"] or ""),
        "ascend_task_db": str(db_paths["ascend_task"] or ""),
        "request_device_summary_rows": len(request_device_rows),
        "top_op_summary_rows": len(top_op_rows),
        "metric_summary_rows": len(metric_rows),
        "aggregate_status": (
            "request_device_aggregate_available"
            if request_device_rows
            else "missing_direct_overlap_device_tables"
        ),
        "aggregation_strategy": "bulk_temp_window_join",
        "heavy_joins_skipped": int(skip_heavy_joins),
        "elapsed_sec": round(time.monotonic() - started, 3),
    }
    return ModeAggregate(
        mode_summary=mode_summary,
        request_device_rows=request_device_rows,
        task_type_rows=task_type_rows,
        top_op_rows=top_op_rows,
        metric_rows=metric_rows,
    )


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
    skip_heavy_joins: bool,
    request_device_rows: list[dict[str, Any]],
    task_type_rows: list[dict[str, Any]],
    top_op_rows: list[dict[str, Any]],
    metric_rows: list[dict[str, Any]],
) -> None:
    with open_readonly(db_path) as conn:
        configure_sqlite_for_bulk_temp(conn)
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

        prepare_request_window_table(conn, requests)
        prepare_overlap_task_time_table(conn, task_columns)

        request_device_rows.extend(query_task_time_summaries(conn, mode, db_path))
        if "task_type" in task_columns:
            task_type_rows.extend(query_task_type_summaries(conn, mode, db_path))
        if skip_heavy_joins:
            return
        if has_ge and can_join_top_ops(task_columns, ge_columns):
            prepare_ge_summary_join_table(conn)
            top_op_rows.extend(query_top_op_types(conn, mode, db_path, top_n_op_types))
        if has_metrics and can_join_metrics(task_columns, metric_columns):
            prepare_ai_core_metrics_join_table(conn, metric_columns)
            metric_rows.extend(query_metric_summaries(conn, mode, db_path, metric_columns))


def aggregate_ascend_task_database(
    *,
    mode: str,
    db_path: Path,
    requests: list[dict[str, Any]],
    task_type_rows: list[dict[str, Any]],
) -> None:
    with open_readonly(db_path) as conn:
        configure_sqlite_for_bulk_temp(conn)
        if "AscendTask" not in set(list_tables(conn)):
            return
        columns = set(list_columns(conn, "AscendTask"))
        if not {"start_time", "duration"}.issubset(columns):
            return
        prepare_request_window_table(conn, requests)
        prepare_overlap_ascend_task_table(conn, columns)
        for column in ("device_task_type", "host_task_type"):
            if column not in columns:
                continue
            task_type_rows.extend(query_ascend_task_type_summaries(conn, mode, db_path, column))


def configure_sqlite_for_bulk_temp(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA automatic_index = ON")
    conn.execute("PRAGMA temp_store = MEMORY")


def prepare_request_window_table(conn: sqlite3.Connection, requests: list[dict[str, Any]]) -> None:
    conn.execute("DROP TABLE IF EXISTS temp.request_windows")
    conn.execute(
        """
        CREATE TEMP TABLE request_windows(
          request_index INTEGER PRIMARY KEY,
          case_id TEXT,
          prompt_id TEXT,
          prefix_reuse_group TEXT,
          arrival_delay_ms TEXT,
          cap_tokens TEXT,
          max_new_tokens TEXT,
          input_token_count TEXT,
          generated_token_count TEXT,
          request_start_ns INTEGER,
          response_end_ns INTEGER,
          client_wall_us TEXT,
          status TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO request_windows(
          request_index, case_id, prompt_id, prefix_reuse_group, arrival_delay_ms,
          cap_tokens, max_new_tokens, input_token_count, generated_token_count,
          request_start_ns, response_end_ns, client_wall_us, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                index,
                request["case_id"],
                request["prompt_id"],
                request["prefix_reuse_group"],
                request["arrival_delay_ms"],
                request["cap_tokens"],
                request["max_new_tokens"],
                request["input_token_count"],
                request["generated_token_count"],
                request["request_start_ns"],
                request["response_end_ns"],
                request["client_wall_us"],
                request["status"],
            )
            for index, request in enumerate(requests)
        ],
    )


def prepare_overlap_task_time_table(conn: sqlite3.Connection, task_columns: set[str]) -> None:
    fields = [
        "r.request_index",
        "CAST(t.start_time AS INTEGER) AS start_time_i",
        "CAST(t.duration_time AS INTEGER) AS duration_time_i",
        cast_column_or_null("t", "wait_time", "wait_time_i", task_columns, "INTEGER"),
        cast_column_or_null("t", "task_type", "task_type_t", task_columns, "TEXT"),
        cast_column_or_null("t", "stream_id", "stream_id_t", task_columns, "TEXT"),
        cast_column_or_null("t", "task_id", "task_id_t", task_columns, "TEXT"),
        cast_column_or_null("t", "model_id", "model_id_t", task_columns, "TEXT"),
        cast_column_or_null("t", "batch_id", "batch_id_t", task_columns, "TEXT"),
        cast_column_or_null("t", "index_id", "index_id_t", task_columns, "TEXT"),
        cast_column_or_null("t", "subtask_id", "subtask_id_t", task_columns, "TEXT"),
    ]
    conn.execute("DROP TABLE IF EXISTS temp.overlap_task_time")
    conn.execute(
        f"""
        CREATE TEMP TABLE overlap_task_time AS
        SELECT {", ".join(fields)}
        FROM request_windows AS r
        JOIN task_time AS t
          ON CAST(t.start_time AS INTEGER) < r.response_end_ns
         AND CAST(t.start_time AS INTEGER) + CAST(t.duration_time AS INTEGER) > r.request_start_ns
        """
    )
    conn.execute("CREATE INDEX temp.idx_overlap_task_request ON overlap_task_time(request_index)")
    conn.execute(
        "CREATE INDEX temp.idx_overlap_task_ge ON overlap_task_time("
        "model_id_t, task_id_t, stream_id_t, batch_id_t, index_id_t)"
    )
    conn.execute(
        "CREATE INDEX temp.idx_overlap_task_metric ON overlap_task_time("
        "task_id_t, stream_id_t, batch_id_t, subtask_id_t)"
    )


def prepare_overlap_ascend_task_table(conn: sqlite3.Connection, columns: set[str]) -> None:
    fields = [
        "r.request_index",
        "CAST(a.duration AS INTEGER) AS duration_i",
        cast_column_or_null("a", "device_task_type", "device_task_type_t", columns, "TEXT"),
        cast_column_or_null("a", "host_task_type", "host_task_type_t", columns, "TEXT"),
    ]
    conn.execute("DROP TABLE IF EXISTS temp.overlap_ascend_task")
    conn.execute(
        f"""
        CREATE TEMP TABLE overlap_ascend_task AS
        SELECT {", ".join(fields)}
        FROM request_windows AS r
        JOIN AscendTask AS a
          ON CAST(a.start_time AS INTEGER) < r.response_end_ns
         AND CAST(a.start_time AS INTEGER) + CAST(a.duration AS INTEGER) > r.request_start_ns
        """
    )
    conn.execute("CREATE INDEX temp.idx_overlap_ascend_request ON overlap_ascend_task(request_index)")


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
          COALESCE(CAST(op_type AS TEXT), '') AS op_type
        FROM ge_summary
        """
    )
    conn.execute(
        "CREATE INDEX temp.idx_ge_summary_join ON ge_summary_join("
        "model_id_t, task_id_t, stream_id_t, batch_id_t, index_id_t)"
    )


def prepare_ai_core_metrics_join_table(
    conn: sqlite3.Connection,
    metric_columns: set[str],
) -> None:
    metric_fields = [
        f"CAST({quote_identifier(column)} AS REAL) AS {quote_identifier(column)}"
        for column in (*SUMMARY_METRIC_COLUMNS, *AVG_METRIC_COLUMNS)
        if column in metric_columns
    ]
    fields = [
        "CAST(task_id AS TEXT) AS task_id_t",
        "CAST(stream_id AS TEXT) AS stream_id_t",
        "CAST(batch_id AS TEXT) AS batch_id_t",
        "CAST(subtask_id AS TEXT) AS subtask_id_t",
        *metric_fields,
    ]
    conn.execute("DROP TABLE IF EXISTS temp.ai_core_metrics_join")
    conn.execute(
        f"""
        CREATE TEMP TABLE ai_core_metrics_join AS
        SELECT {", ".join(fields)}
        FROM ai_core_metrics
        """
    )
    conn.execute(
        "CREATE INDEX temp.idx_ai_core_metrics_join ON ai_core_metrics_join("
        "task_id_t, stream_id_t, batch_id_t, subtask_id_t)"
    )


def cast_column_or_null(
    table_alias: str,
    source_column: str,
    output_column: str,
    available_columns: set[str],
    sqlite_type: str,
) -> str:
    if source_column in available_columns:
        return (
            f"CAST({table_alias}.{quote_identifier(source_column)} AS {sqlite_type}) "
            f"AS {quote_identifier(output_column)}"
        )
    return f"NULL AS {quote_identifier(output_column)}"


def can_join_top_ops(task_columns: set[str], ge_columns: set[str]) -> bool:
    task_required = {"model_id", "task_id", "stream_id", "batch_id", "index_id"}
    ge_required = {"model_id", "task_id", "stream_id", "batch_id", "index_id", "op_type"}
    return task_required.issubset(task_columns) and ge_required.issubset(ge_columns)


def can_join_metrics(task_columns: set[str], metric_columns: set[str]) -> bool:
    required = {"task_id", "stream_id", "batch_id", "subtask_id"}
    return required.issubset(task_columns) and required.issubset(metric_columns)


def request_metadata_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "case_id": row["case_id"],
        "prompt_id": row["prompt_id"],
        "prefix_reuse_group": row["prefix_reuse_group"],
        "arrival_delay_ms": row["arrival_delay_ms"],
        "cap_tokens": row["cap_tokens"],
        "max_new_tokens": row["max_new_tokens"],
        "input_token_count": row["input_token_count"],
        "generated_token_count": row["generated_token_count"],
        "request_start_ns": row["request_start_ns"],
        "response_end_ns": row["response_end_ns"],
        "client_wall_us": row["client_wall_us"],
        "status": row["status"],
    }


def query_task_time_summaries(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
          r.*,
          COUNT(o.start_time_i) AS task_row_count,
          MIN(o.start_time_i) AS min_start_time,
          MAX(o.start_time_i + o.duration_time_i) AS max_end_time,
          SUM(o.duration_time_i) AS total_duration_time,
          SUM(o.wait_time_i) AS total_wait_time,
          COUNT(DISTINCT o.stream_id_t) AS distinct_stream_count,
          COUNT(DISTINCT o.task_id_t) AS distinct_task_id_count
        FROM request_windows AS r
        LEFT JOIN overlap_task_time AS o
          ON r.request_index = o.request_index
        GROUP BY r.request_index
        ORDER BY r.request_index
    """
    return [
        {
            "mode": mode,
            "db_path": str(db_path),
            **request_metadata_from_row(row),
            "task_row_count": safe_int(row["task_row_count"]),
            "min_start_time": safe_int(row["min_start_time"]),
            "max_end_time": safe_int(row["max_end_time"]),
            "total_duration_time": safe_int(row["total_duration_time"]),
            "total_wait_time": safe_int(row["total_wait_time"]),
            "distinct_stream_count": safe_int(row["distinct_stream_count"]),
            "distinct_task_id_count": safe_int(row["distinct_task_id_count"]),
        }
        for row in conn.execute(sql)
    ]


def query_task_type_summaries(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
) -> list[dict[str, Any]]:
    sql = """
        SELECT r.case_id, r.prompt_id, r.prefix_reuse_group,
               o.task_type_t AS value,
               COUNT(*) AS task_row_count,
               SUM(o.duration_time_i) AS total_duration_time
        FROM overlap_task_time AS o
        JOIN request_windows AS r
          ON r.request_index = o.request_index
        GROUP BY r.request_index, value
        ORDER BY r.request_index, task_row_count DESC
    """
    return [
        {
            "mode": mode,
            "db_path": str(db_path),
            "table": "task_time",
            "group_column": "task_type",
            "group_value": row["value"],
            "case_id": row["case_id"],
            "prompt_id": row["prompt_id"],
            "prefix_reuse_group": row["prefix_reuse_group"],
            "task_row_count": safe_int(row["task_row_count"]),
            "total_duration_time": safe_int(row["total_duration_time"]),
        }
        for row in conn.execute(sql)
    ]


def query_ascend_task_type_summaries(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    column: str,
) -> list[dict[str, Any]]:
    temp_column = f"{column}_t"
    sql = f"""
        SELECT r.case_id, r.prompt_id, r.prefix_reuse_group,
               {quote_identifier(temp_column)} AS value,
               COUNT(*) AS task_row_count,
               SUM(duration_i) AS total_duration_time
        FROM overlap_ascend_task AS a
        JOIN request_windows AS r
          ON r.request_index = a.request_index
        GROUP BY r.request_index, value
        ORDER BY r.request_index, task_row_count DESC
    """
    return [
        {
            "mode": mode,
            "db_path": str(db_path),
            "table": "AscendTask",
            "group_column": column,
            "group_value": row["value"],
            "case_id": row["case_id"],
            "prompt_id": row["prompt_id"],
            "prefix_reuse_group": row["prefix_reuse_group"],
            "task_row_count": safe_int(row["task_row_count"]),
            "total_duration_time": safe_int(row["total_duration_time"]),
        }
        for row in conn.execute(sql)
    ]


def query_top_op_types(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    top_n_op_types: int,
) -> list[dict[str, Any]]:
    sql = """
        SELECT r.request_index, r.case_id, r.prompt_id, r.prefix_reuse_group,
               COALESCE(g.op_type, '') AS op_type,
               COUNT(*) AS task_row_count,
               SUM(o.duration_time_i) AS total_duration_time,
               SUM(o.wait_time_i) AS total_wait_time
        FROM overlap_task_time AS o
        JOIN request_windows AS r
          ON r.request_index = o.request_index
        LEFT JOIN ge_summary_join AS g
          ON o.model_id_t = g.model_id_t
         AND o.task_id_t = g.task_id_t
         AND o.stream_id_t = g.stream_id_t
         AND o.batch_id_t = g.batch_id_t
         AND o.index_id_t = g.index_id_t
        GROUP BY r.request_index, op_type
        ORDER BY r.request_index, total_duration_time DESC, task_row_count DESC
    """
    rows = []
    rank_by_request: dict[int, int] = {}
    for row in conn.execute(sql):
        request_index = int(row["request_index"])
        rank = rank_by_request.get(request_index, 0) + 1
        rank_by_request[request_index] = rank
        if rank > top_n_op_types:
            continue
        rows.append(
            {
                "mode": mode,
                "db_path": str(db_path),
                "case_id": row["case_id"],
                "prompt_id": row["prompt_id"],
                "prefix_reuse_group": row["prefix_reuse_group"],
                "rank": rank,
                "op_type": row["op_type"],
                "task_row_count": safe_int(row["task_row_count"]),
                "total_duration_time": safe_int(row["total_duration_time"]),
                "total_wait_time": safe_int(row["total_wait_time"]),
            }
        )
    return rows


def query_metric_summaries(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    metric_columns: set[str],
) -> list[dict[str, Any]]:
    sum_exprs = [
        f"SUM(m.{quote_identifier(column)}) AS {quote_identifier(column + '_sum')}"
        for column in SUMMARY_METRIC_COLUMNS
        if column in metric_columns
    ]
    avg_exprs = [
        f"AVG(m.{quote_identifier(column)}) AS {quote_identifier(column + '_avg')}"
        for column in AVG_METRIC_COLUMNS
        if column in metric_columns
    ]
    select_exprs = ["r.*", "COUNT(m.task_id_t) AS metric_row_count", *sum_exprs, *avg_exprs]
    sql = f"""
        SELECT {", ".join(select_exprs)}
        FROM request_windows AS r
        LEFT JOIN overlap_task_time AS o
          ON r.request_index = o.request_index
        LEFT JOIN ai_core_metrics_join AS m
          ON o.task_id_t = m.task_id_t
         AND o.stream_id_t = m.stream_id_t
         AND o.batch_id_t = m.batch_id_t
         AND o.subtask_id_t = m.subtask_id_t
        GROUP BY r.request_index
        ORDER BY r.request_index
    """
    rows = []
    for row in conn.execute(sql):
        result: dict[str, Any] = {
            "mode": mode,
            "db_path": str(db_path),
            "case_id": row["case_id"],
            "prompt_id": row["prompt_id"],
            "prefix_reuse_group": row["prefix_reuse_group"],
            "metric_row_count": safe_int(row["metric_row_count"]),
        }
        for key in row.keys():
            if key in {"request_index", *request_metadata_from_row(row).keys(), "metric_row_count"}:
                continue
            result[key] = safe_number(row[key])
        rows.append(result)
    return rows


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
        f"aggregation_strategy={result['aggregation_strategy']}",
        f"workers={result['workers']}",
        f"heavy_joins_skipped={int(result['heavy_joins_skipped'])}",
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
                    "heavy_joins_skipped",
                    "elapsed_sec",
                    "aggregate_status",
                )
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
