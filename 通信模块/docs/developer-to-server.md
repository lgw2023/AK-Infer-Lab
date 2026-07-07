# 开发机给服务器的任务说明

## 当前任务：P1.23 vLLM API msprof stats pairing

- 任务 ID：`runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023`
- 当前开发机分支：`main`
- 服务器同步方式：只执行 `git pull --ff-only`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_msprof_stats_pairing_handoff.md`
- 核心脚本：`tools/inference_contracts/run_vllm_api_concurrency_smoke.py`

P1.22 `runtime_vllm_api_prefix_cache_ab_2026_0707_p1_022` 已成功：

- `pytest_exit_code=0`
- `prefix_cache_on_exit_code=0`
- `prefix_cache_off_exit_code=0`
- `prefix_cache_ab_validation_exit_code=0`
- 两轮均为 `case_plan=continuous16_mixed`
- 两轮均 `request_count=16`、`success_case_count=16`、`failed_case_count=0`
- 两轮均 `client_overlap_candidate_count=120`
- 两轮均 `trace_validation_errors=0`
- `prefix_cache_on` 命令包含 `--enable-prefix-caching`，vLLM stats 记录 `max_running=15`、`max_waiting=1`、`max_kv_cache_usage_pct=7.9`、`max_prefix_cache_hit_rate_pct=49.2`
- `prefix_cache_off` 命令不包含 `--enable-prefix-caching`，vLLM stats 记录 `max_running=9`、`max_waiting=5`、`max_kv_cache_usage_pct=6.3`、`max_prefix_cache_hit_rate_pct=0.0`

因此本轮不再做更小的 smoke，直接进入第一轮真实 vLLM API workload profiler 证据采集：对同一 `continuous16_mixed` 16 请求负载分别运行 `msprof_prefix_cache_on` 和 `msprof_prefix_cache_off`，用 `msprof --msproftx=on` 包住现有脚本，收集 vLLM server stats、客户端 P1 trace、msprof host/device/sqlite/timebase 候选和 selected profiler 产物。

本轮仍不是 benchmark、压测、吞吐比较、prefix cache 命中验收、调度效率结论、瓶颈归因或优化建议。

## 本轮必须回答

1. `msprof --msproftx=on` 能否包住现有 vLLM API concurrency 脚本并正常退出？
2. `msprof_prefix_cache_on` 与 `msprof_prefix_cache_off` 是否仍然各自完成 16/16 请求、client overlap 和 P1 trace validator？
3. 两个子任务的 server command 是否保持 prefix-cache 开关分离？
4. 两个子任务是否都生成 vLLM `vllm_api_server_stats_summary.tsv`？
5. msprof 输出目录是否包含 `host`、`device_<id>`、`sqlite`、`time.db` 或其他时间字段候选？
6. 是否生成 `msprof_pairing_inventory.tsv`，汇总每个 mode 的请求成功数、P1 trace 校验、vLLM stats、msprof 文件数、sqlite 数、timebase 候选数？
7. 如果 profiler 原始 raw data 过大，是否只回传 selected profiler 产物、文件列表和大小清单，而不是塞满邮件附件？

## 严格边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境已有 `vllm`、`vllm_ascend`、`msprof`
- 设置 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS=ascend`、`VLLM_WORKER_MULTIPROC_METHOD`
- 设置 `AK_VLLM_MAX_MODEL_LEN=9216`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 用 ASCII `/tmp/<run_id>_<mode>_msprof` 作为 `msprof --output`
- 对 `prefix_cache_on` 与 `prefix_cache_off` 各运行一次 profiled `continuous16_mixed` 负载
- 只读枚举和解析 msprof 产物，复制 selected profiler 产物到项目 artifact

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不静默降低 `max_model_len`
- 不删减 case、不降低输入 cap、不缩短 output token
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不运行多 worker 压测、benchmark、长时间服务或吞吐压测
- 不切换 Docker 推理栈
- 不复制、移动、删除或改名 `/data/node0_disk1/Public/` 下任何模型文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime、vLLM 或 vLLM-Ascend 源码
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、吞吐优劣、调度效率、prefix cache 命中率验收、瓶颈归因或优化建议

## 建议执行命令

请在服务器项目根目录执行：

```bash
set -euo pipefail

cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

RUN_ID=runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH="${AK_SMALL_MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"
PYTHON_BIN="$(command -v python)"

export RUN_ID ARTIFACT_DIR MODEL_PATH PYTHON_BIN
export PYTHONUNBUFFERED=1
export AK_COMM_MAIL_TO="${AK_COMM_MAIL_TO:-yilili1023@gmail.com}"
export ASCEND_RT_VISIBLE_DEVICES="${AK_VLLM_ASCEND_VISIBLE_DEVICES:-6}"
export AK_VLLM_DEVICE_LABEL="${AK_VLLM_DEVICE_LABEL:-npu:${ASCEND_RT_VISIBLE_DEVICES}}"
export VLLM_USE_V1="${VLLM_USE_V1:-1}"
export VLLM_PLUGINS="${VLLM_PLUGINS:-ascend}"
export VLLM_WORKER_MULTIPROC_METHOD="${VLLM_WORKER_MULTIPROC_METHOD:-spawn}"
export AK_VLLM_MAX_MODEL_LEN="${AK_VLLM_MAX_MODEL_LEN:-9216}"
export AK_VLLM_GPU_MEMORY_UTILIZATION="${AK_VLLM_GPU_MEMORY_UTILIZATION:-0.85}"
export AK_VLLM_TP_SIZE="${AK_VLLM_TP_SIZE:-1}"
export AK_VLLM_DTYPE="${AK_VLLM_DTYPE:-auto}"
export AK_VLLM_ENFORCE_EAGER="${AK_VLLM_ENFORCE_EAGER:-1}"
export AK_VLLM_API_HOST="${AK_VLLM_API_HOST:-127.0.0.1}"
export AK_VLLM_API_PORT="${AK_VLLM_API_PORT:-0}"
export AK_VLLM_SERVED_MODEL_NAME="${AK_VLLM_SERVED_MODEL_NAME:-Qwen3.5-4B}"
export AK_VLLM_API_READY_TIMEOUT_SEC="${AK_VLLM_API_READY_TIMEOUT_SEC:-900}"
export AK_VLLM_API_REQUEST_TIMEOUT_SEC="${AK_VLLM_API_REQUEST_TIMEOUT_SEC:-900}"
export AK_VLLM_API_CASE_PLAN=continuous16_mixed

set +u
if [ -f /usr/local/Ascend/cann-9.0.0/set_env.sh ]; then
  source /usr/local/Ascend/cann-9.0.0/set_env.sh
fi
if [ -f /usr/local/Ascend/nnal/atb/set_env.sh ]; then
  source /usr/local/Ascend/nnal/atb/set_env.sh
fi
set -u

mkdir -p "${ARTIFACT_DIR}"

set +e
python -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
pytest_exit_code=$?
set -e

run_profiled_mode() {
  local mode="$1"
  local prefix_arg="$2"
  local mode_dir="${ARTIFACT_DIR}/${mode}"
  local msprof_out="/tmp/${RUN_ID}_${mode}_msprof"

  rm -rf "${msprof_out}"
  mkdir -p "${mode_dir}" "${msprof_out}"

  {
    echo "run_id=${RUN_ID}_${mode}"
    echo "mode=${mode}"
    echo "commit=$(git rev-parse HEAD)"
    echo "timestamp=$(date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "MODEL_PATH=${MODEL_PATH}"
    echo "CASE_PLAN=continuous16_mixed"
    echo "max_model_len=${AK_VLLM_MAX_MODEL_LEN}"
    echo "MSPROF_OUT=${msprof_out}"
    echo "prefix_arg=${prefix_arg}"
  } > "${mode_dir}/profiled_run_context.txt"

  set +e
  msprof \
    --output "${msprof_out}" \
    --msproftx=on \
    --storage-limit=4096 \
    "${PYTHON_BIN}" tools/inference_contracts/run_vllm_api_concurrency_smoke.py \
      --run-id "${RUN_ID}_${mode}" \
      --artifact-dir "${mode_dir}/vllm" \
      --model-path "${MODEL_PATH}" \
      --case-plan continuous16_mixed \
      --max-model-len "${AK_VLLM_MAX_MODEL_LEN}" \
      "${prefix_arg}" \
      > "${mode_dir}/msprof_vllm_api.log" 2>&1
  local exit_code=$?
  set -e

  echo "${exit_code}" > "${mode_dir}/msprof_exit_code.txt"
  find "${msprof_out}" -type f -print 2>/dev/null | sort > "${mode_dir}/msprof_output_files.txt" || true
  du -ah "${msprof_out}" 2>/dev/null | sort -h > "${mode_dir}/msprof_du.txt" || true

  mkdir -p "${mode_dir}/msprof_selected"
  while IFS= read -r file_path; do
    rel_path="${file_path#${msprof_out}/}"
    case "${rel_path}" in
      */sqlite/*|*.json|*.csv|*.tsv|*.txt|*.log|*start_info*|*end_info*)
        mkdir -p "${mode_dir}/msprof_selected/$(dirname "${rel_path}")"
        cp -p "${file_path}" "${mode_dir}/msprof_selected/${rel_path}" 2>/dev/null || true
        ;;
    esac
  done < "${mode_dir}/msprof_output_files.txt"

  python - "${mode_dir}" "${msprof_out}" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path

mode_dir = Path(sys.argv[1])
msprof_out = Path(sys.argv[2])
files = [p for p in msprof_out.rglob("*") if p.is_file()] if msprof_out.exists() else []

schema_rows = ["db_path\ttable\tcolumn\ttype"]
time_rows = ["db_path\ttable\tcolumn\trow_count_hint"]
for db_path in sorted([p for p in files if p.suffix == ".db"]):
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        tables = [r[0] for r in conn.execute("select name from sqlite_master where type='table' order by name")]
        for table in tables:
            cols = conn.execute(f"pragma table_info({table!r})").fetchall()
            row_count = ""
            try:
                row_count = str(conn.execute(f"select count(*) from {table!r}").fetchone()[0])
            except Exception:
                row_count = "unknown"
            for col in cols:
                name = str(col[1])
                typ = str(col[2])
                schema_rows.append(f"{db_path}\t{table}\t{name}\t{typ}")
                lowered = name.lower()
                if any(token in lowered for token in ("time", "start", "end", "duration", "timestamp", "ts", "dur")):
                    time_rows.append(f"{db_path}\t{table}\t{name}\t{row_count}")
        conn.close()
    except Exception as exc:
        schema_rows.append(f"{db_path}\tERROR\t{type(exc).__name__}\t{exc}")

(mode_dir / "msprof_sqlite_schema.tsv").write_text("\n".join(schema_rows) + "\n", encoding="utf-8")
(mode_dir / "msprof_timebase_candidates.tsv").write_text("\n".join(time_rows) + "\n", encoding="utf-8")

inventory = {
    "file_count": len(files),
    "sqlite_count": sum(1 for p in files if p.suffix == ".db"),
    "json_count": sum(1 for p in files if p.suffix == ".json"),
    "host_dir_count": sum(1 for p in msprof_out.rglob("host") if p.is_dir()) if msprof_out.exists() else 0,
    "device_dir_count": sum(1 for p in msprof_out.rglob("device_*") if p.is_dir()) if msprof_out.exists() else 0,
    "timebase_candidate_count": max(0, len(time_rows) - 1),
}
(mode_dir / "msprof_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

run_profiled_mode "msprof_prefix_cache_on" "--enable-prefix-caching"
msprof_prefix_cache_on_exit_code="$(cat "${ARTIFACT_DIR}/msprof_prefix_cache_on/msprof_exit_code.txt")"

run_profiled_mode "msprof_prefix_cache_off" "--no-enable-prefix-caching"
msprof_prefix_cache_off_exit_code="$(cat "${ARTIFACT_DIR}/msprof_prefix_cache_off/msprof_exit_code.txt")"

python - "${ARTIFACT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
modes = ["msprof_prefix_cache_on", "msprof_prefix_cache_off"]
rows = []
for mode in modes:
    mode_dir = artifact_dir / mode
    result_path = mode_dir / "vllm" / "vllm_api_concurrency_result.json"
    inv_path = mode_dir / "msprof_inventory.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
    inv = json.loads(inv_path.read_text(encoding="utf-8")) if inv_path.is_file() else {}
    rows.append({
        "mode": mode,
        "msprof_exit_code": (mode_dir / "msprof_exit_code.txt").read_text(encoding="utf-8").strip() if (mode_dir / "msprof_exit_code.txt").is_file() else "missing",
        "vllm_status": result.get("status", "missing"),
        "request_count": result.get("request_count", ""),
        "success_case_count": result.get("success_case_count", ""),
        "failed_case_count": result.get("failed_case_count", ""),
        "client_overlap_candidate_count": result.get("client_overlap_candidate_count", ""),
        "trace_validation_errors": result.get("trace_validation_errors", ""),
        "server_stats_sample_count": result.get("server_stats_sample_count", ""),
        "server_stats_max_running_reqs": result.get("server_stats_max_running_reqs", ""),
        "server_stats_max_waiting_reqs": result.get("server_stats_max_waiting_reqs", ""),
        "server_stats_max_kv_cache_usage_pct": result.get("server_stats_max_kv_cache_usage_pct", ""),
        "server_stats_max_prefix_cache_hit_rate_pct": result.get("server_stats_max_prefix_cache_hit_rate_pct", ""),
        "msprof_file_count": inv.get("file_count", ""),
        "msprof_sqlite_count": inv.get("sqlite_count", ""),
        "msprof_json_count": inv.get("json_count", ""),
        "msprof_host_dir_count": inv.get("host_dir_count", ""),
        "msprof_device_dir_count": inv.get("device_dir_count", ""),
        "msprof_timebase_candidate_count": inv.get("timebase_candidate_count", ""),
    })

headers = list(rows[0].keys()) if rows else []
(artifact_dir / "msprof_pairing_inventory.tsv").write_text(
    "\t".join(headers) + "\n" + "\n".join("\t".join(str(row.get(h, "")) for h in headers) for row in rows) + "\n",
    encoding="utf-8",
)
(artifact_dir / "msprof_pairing_result.json").write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date '+%Y-%m-%dT%H:%M:%S%z')"
  echo "MODEL_PATH=${MODEL_PATH}"
  echo "CASE_PLAN=continuous16_mixed"
  echo "max_model_len=${AK_VLLM_MAX_MODEL_LEN}"
  echo "pytest_exit_code=${pytest_exit_code}"
  echo "msprof_prefix_cache_on_exit_code=${msprof_prefix_cache_on_exit_code}"
  echo "msprof_prefix_cache_off_exit_code=${msprof_prefix_cache_off_exit_code}"
} > "${ARTIFACT_DIR}/run_context.txt"

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo
  echo "## msprof_pairing_inventory"
  cat "${ARTIFACT_DIR}/msprof_pairing_inventory.tsv"
} > "${ARTIFACT_DIR}/summary.txt"

cd 工作记录与进度笔记本/runtime_trace_smokes
rm -f "${RUN_ID}.zip"
zip -r -q "${RUN_ID}.zip" "${RUN_ID}"
```

## 回传要求

请邮件正文直接列出：

```text
P1.23 vLLM API msprof stats pairing 已完成/失败。

run_id: runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023
commit: <git rev-parse HEAD>
artifact_dir: 工作记录与进度笔记本/runtime_trace_smokes/runtime_vllm_api_msprof_stats_pairing_2026_0707_p1_023
pytest_exit_code: <...>
msprof_prefix_cache_on_exit_code: <...>
msprof_prefix_cache_off_exit_code: <...>

请见附件 zip、summary.txt、msprof_pairing_inventory.tsv。
```

附件至少包含：

- `${RUN_ID}.zip`
- `${RUN_ID}/summary.txt`
- `${RUN_ID}/run_context.txt`
- `${RUN_ID}/msprof_pairing_inventory.tsv`
- 两个子任务的 `msprof_vllm_api.log`
- 两个子任务的 `msprof_output_files.txt`
- 两个子任务的 `msprof_du.txt`
- 两个子任务的 `msprof_sqlite_schema.tsv`
- 两个子任务的 `msprof_timebase_candidates.tsv`
- 两个子任务的 `vllm/vllm_api_concurrency_result.json`
- 两个子任务的 `vllm/vllm_api_server_stats_summary.tsv`
- 两个子任务的 `vllm/vllm_api_server_command.json`

如果 zip 过大，不要强行邮件发送完整 raw profiler data；保留 selected profiler 产物、文件列表和大小清单，并在正文说明 raw profiler 数据仍在服务器 `/tmp/<run_id>_<mode>_msprof`。

边界说明必须写清楚：本轮启用了 profiler，但只采集 profiler 覆盖与 pairing 证据，不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中验收、瓶颈归因或优化建议。
