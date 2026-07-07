from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "工作记录与进度笔记本" / "runtime_trace_smokes"
DEFAULT_SOURCE_RUN_ID = "runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023"
DEFAULT_RUN_ID = "runtime_vllm_api_msprof_sqlite_window_analysis_2026_0707_p1_024"
DEFAULT_MODES = ("msprof_prefix_cache_on", "msprof_prefix_cache_off")
FLAT_SUFFIX = {
    "msprof_prefix_cache_on": "",
    "msprof_prefix_cache_off": "_1",
}
TIME_COLUMN_SETS = (
    ("startNs", "endNs", ""),
    ("start_time", "", "duration"),
    ("start_time", "", "duration_time"),
    ("start", "end", ""),
    ("timestamp", "", "duration"),
)
GROUP_COLUMNS = ("op_type", "device_task_type", "host_task_type", "type")


@dataclass(frozen=True)
class ModePaths:
    mode: str
    result_path: Path | None
    msprof_root: Path | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze msprof SQLite files against vLLM API request windows."
    )
    parser.add_argument("--run-id", default=os.environ.get("RUN_ID", DEFAULT_RUN_ID))
    parser.add_argument(
        "--source-artifact-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT / DEFAULT_SOURCE_RUN_ID,
        help="P1.23 artifact directory containing mode subdirectories.",
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_dir = args.artifact_dir or (DEFAULT_ARTIFACT_ROOT / args.run_id)
    explicit_roots = {
        "msprof_prefix_cache_on": args.msprof_root_on,
        "msprof_prefix_cache_off": args.msprof_root_off,
    }
    modes = tuple(args.mode or DEFAULT_MODES)
    result = analyze_msprof_windows(
        run_id=args.run_id,
        source_artifact_dir=args.source_artifact_dir,
        artifact_dir=artifact_dir,
        modes=modes,
        explicit_roots=explicit_roots,
    )
    return 0 if result["overall_status"] != "failed" else 1


def analyze_msprof_windows(
    *,
    run_id: str,
    source_artifact_dir: Path,
    artifact_dir: Path,
    modes: tuple[str, ...] = DEFAULT_MODES,
    explicit_roots: dict[str, Path | None] | None = None,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    explicit_roots = explicit_roots or {}

    mode_summaries: list[dict[str, Any]] = []
    request_rows: list[dict[str, Any]] = []
    db_rows: list[dict[str, Any]] = []
    time_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    group_rows: list[dict[str, Any]] = []

    for mode in modes:
        paths = discover_mode_paths(source_artifact_dir, mode, explicit_roots.get(mode))
        requests, result_status = load_request_windows(paths.result_path)
        request_rows.extend({"mode": mode, **row} for row in requests)

        db_paths = find_sqlite_files(paths.msprof_root)
        mode_db_rows, mode_time_rows, mode_overlap_rows, mode_group_rows = analyze_sqlite_files(
            mode=mode,
            db_paths=db_paths,
            requests=requests,
        )
        db_rows.extend(mode_db_rows)
        time_rows.extend(mode_time_rows)
        overlap_rows.extend(mode_overlap_rows)
        group_rows.extend(mode_group_rows)

        direct_overlap_candidates = sum(1 for row in mode_time_rows if row["overlapping_request_count"] > 0)
        mode_summaries.append(
            {
                "mode": mode,
                "result_path": str(paths.result_path or ""),
                "result_status": result_status,
                "request_count": len(requests),
                "successful_request_count": sum(1 for row in requests if row["status"] == "success"),
                "msprof_root": str(paths.msprof_root or ""),
                "msprof_root_exists": int(bool(paths.msprof_root and paths.msprof_root.exists())),
                "sqlite_db_count": len(db_paths),
                "sqlite_table_count": len(mode_db_rows),
                "time_candidate_count": len(mode_time_rows),
                "direct_overlap_candidate_count": direct_overlap_candidates,
                "time_alignment_status": (
                    "direct_request_window_overlap"
                    if direct_overlap_candidates
                    else "profiler_tables_available_but_no_direct_window_overlap"
                    if db_paths
                    else "missing_msprof_sqlite"
                ),
            }
        )

    write_tsv(artifact_dir / "request_window_summary.tsv", request_rows)
    write_tsv(artifact_dir / "profiler_sqlite_table_inventory.tsv", db_rows)
    write_tsv(artifact_dir / "profiler_time_range_summary.tsv", time_rows)
    write_tsv(artifact_dir / "request_profiler_overlap_summary.tsv", overlap_rows)
    write_tsv(artifact_dir / "profiler_group_count_summary.tsv", group_rows)

    overall_status = "success" if mode_summaries and all(row["sqlite_db_count"] for row in mode_summaries) else "failed"
    result = {
        "run_id": run_id,
        "source_artifact_dir": str(source_artifact_dir),
        "artifact_dir": str(artifact_dir),
        "overall_status": overall_status,
        "mode_summaries": mode_summaries,
        "policy": "evidence_extraction_only_no_benchmark_or_bottleneck_claim",
    }
    (artifact_dir / "msprof_sqlite_window_analysis_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(artifact_dir / "summary.txt", result)
    return result


def discover_mode_paths(source_artifact_dir: Path, mode: str, explicit_root: Path | None) -> ModePaths:
    suffix = FLAT_SUFFIX[mode]
    result_candidates = [
        source_artifact_dir / mode / "vllm" / "vllm_api_concurrency_result.json",
        source_artifact_dir / mode / "vllm_api_concurrency_result.json",
        source_artifact_dir / f"vllm_api_concurrency_result{suffix}.json",
    ]
    output_file_candidates = [
        source_artifact_dir / mode / "msprof_output_files.txt",
        source_artifact_dir / f"msprof_output_files{suffix}.txt",
    ]
    result_path = next((path for path in result_candidates if path.is_file()), None)
    msprof_root = explicit_root if explicit_root else None
    if msprof_root is None:
        output_file_path = next((path for path in output_file_candidates if path.is_file()), None)
        if output_file_path:
            msprof_root = infer_msprof_root(output_file_path)
    return ModePaths(mode=mode, result_path=result_path, msprof_root=msprof_root)


def infer_msprof_root(output_file_path: Path) -> Path | None:
    paths = [
        line.strip()
        for line in output_file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip().startswith("/")
    ]
    if not paths:
        return None
    common = Path(os.path.commonpath(paths))
    if common.is_file():
        return common.parent
    return common


def load_request_windows(result_path: Path | None) -> tuple[list[dict[str, Any]], str]:
    if not result_path or not result_path.is_file():
        return [], "missing_result_json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    rows = []
    for row in data.get("rows", []):
        start_ns = int(row.get("request_start_ns") or 0)
        end_ns = int(row.get("response_end_ns") or 0)
        if not start_ns or end_ns <= start_ns:
            continue
        rows.append(
            {
                "case_id": row.get("case_id", ""),
                "prompt_id": row.get("prompt_id", ""),
                "prefix_reuse_group": row.get("prefix_reuse_group", ""),
                "arrival_delay_ms": row.get("arrival_delay_ms", ""),
                "cap_tokens": row.get("cap_tokens", ""),
                "max_new_tokens": row.get("max_new_tokens", ""),
                "input_token_count": row.get("input_token_count", ""),
                "generated_token_count": row.get("generated_token_count", ""),
                "request_start_ns": start_ns,
                "response_end_ns": end_ns,
                "client_wall_us": row.get("client_wall_us", ""),
                "status": row.get("status", ""),
            }
        )
    return rows, str(data.get("status", "unknown"))


def find_sqlite_files(root: Path | None) -> list[Path]:
    if not root or not root.exists():
        return []
    return sorted(path for path in root.rglob("*.db") if path.is_file())


def analyze_sqlite_files(
    *,
    mode: str,
    db_paths: list[Path],
    requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    db_rows: list[dict[str, Any]] = []
    time_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    group_rows: list[dict[str, Any]] = []

    for db_path in db_paths:
        with open_sqlite(db_path) as conn:
            for table in list_tables(conn):
                columns = list_columns(conn, table)
                row_count = count_rows(conn, table)
                db_rows.append(
                    {
                        "mode": mode,
                        "db_path": str(db_path),
                        "table": table,
                        "row_count": row_count,
                        "columns": ",".join(columns),
                    }
                )
                time_rows.extend(analyze_time_candidates(conn, mode, db_path, table, columns, row_count, requests))
                group_rows.extend(analyze_group_counts(conn, mode, db_path, table, columns))

    for time_row in time_rows:
        overlap_rows.extend(time_row.pop("_overlaps", []))
    return db_rows, time_rows, overlap_rows, group_rows


def open_sqlite(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()
    return [str(row[0]) for row in rows]


def list_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({quote_identifier(table)})")]


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0])


def analyze_time_candidates(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    table: str,
    columns: list[str],
    row_count: int,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    column_set = set(columns)
    for start_col, end_col, duration_col in TIME_COLUMN_SETS:
        if start_col not in column_set:
            continue
        if end_col and end_col not in column_set:
            continue
        if duration_col and duration_col not in column_set:
            continue
        min_start, max_end = min_max_interval(conn, table, start_col, end_col, duration_col)
        overlaps = overlap_requests(conn, table, start_col, end_col, duration_col, requests)
        rows.append(
            {
                "mode": mode,
                "db_path": str(db_path),
                "table": table,
                "start_column": start_col,
                "end_column": end_col,
                "duration_column": duration_col,
                "row_count": row_count,
                "min_start": min_start,
                "max_end": max_end,
                "overlapping_request_count": sum(1 for row in overlaps if row["overlap_row_count"] > 0),
                "overlap_row_count_total": sum(int(row["overlap_row_count"]) for row in overlaps),
                "_overlaps": [
                    {
                        "mode": mode,
                        "db_path": str(db_path),
                        "table": table,
                        "start_column": start_col,
                        "end_column": end_col,
                        "duration_column": duration_col,
                        **row,
                    }
                    for row in overlaps
                ],
            }
        )
    return rows


def min_max_interval(
    conn: sqlite3.Connection,
    table: str,
    start_col: str,
    end_col: str,
    duration_col: str,
) -> tuple[int | str, int | str]:
    table_q = quote_identifier(table)
    start_q = quote_identifier(start_col)
    if end_col:
        end_expr = f"CAST({quote_identifier(end_col)} AS INTEGER)"
    else:
        end_expr = f"CAST({start_q} AS INTEGER) + CAST({quote_identifier(duration_col)} AS INTEGER)"
    sql = f"SELECT MIN(CAST({start_q} AS INTEGER)), MAX({end_expr}) FROM {table_q}"
    row = conn.execute(sql).fetchone()
    return safe_int(row[0]), safe_int(row[1])


def overlap_requests(
    conn: sqlite3.Connection,
    table: str,
    start_col: str,
    end_col: str,
    duration_col: str,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    table_q = quote_identifier(table)
    start_expr = f"CAST({quote_identifier(start_col)} AS INTEGER)"
    if end_col:
        end_expr = f"CAST({quote_identifier(end_col)} AS INTEGER)"
    else:
        end_expr = f"{start_expr} + CAST({quote_identifier(duration_col)} AS INTEGER)"
    sql = f"SELECT COUNT(*) FROM {table_q} WHERE {start_expr} < ? AND {end_expr} > ?"

    rows = []
    for request in requests:
        count = int(conn.execute(sql, (request["response_end_ns"], request["request_start_ns"])).fetchone()[0])
        rows.append(
            {
                "case_id": request["case_id"],
                "prompt_id": request["prompt_id"],
                "prefix_reuse_group": request["prefix_reuse_group"],
                "request_start_ns": request["request_start_ns"],
                "response_end_ns": request["response_end_ns"],
                "overlap_row_count": count,
            }
        )
    return rows


def analyze_group_counts(
    conn: sqlite3.Connection,
    mode: str,
    db_path: Path,
    table: str,
    columns: list[str],
) -> list[dict[str, Any]]:
    rows = []
    table_q = quote_identifier(table)
    for column in GROUP_COLUMNS:
        if column not in columns:
            continue
        column_q = quote_identifier(column)
        sql = (
            f"SELECT CAST({column_q} AS TEXT) AS value, COUNT(*) AS count "
            f"FROM {table_q} GROUP BY value ORDER BY count DESC LIMIT 30"
        )
        for row in conn.execute(sql):
            rows.append(
                {
                    "mode": mode,
                    "db_path": str(db_path),
                    "table": table,
                    "group_column": column,
                    "group_value": row["value"],
                    "row_count": int(row["count"]),
                }
            )
    return rows


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def safe_int(value: Any) -> int | str:
    try:
        if value is None:
            return ""
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


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
                    "sqlite_db_count",
                    "time_candidate_count",
                    "direct_overlap_candidate_count",
                    "time_alignment_status",
                )
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
