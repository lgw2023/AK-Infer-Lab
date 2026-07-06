# 开发机给服务器的任务说明

## 当前任务：P1.22 vLLM API prefix-cache A/B stats smoke

- 任务 ID：`runtime_vllm_api_prefix_cache_ab_2026_0707_p1_022`
- 当前开发机分支：`main`
- 服务器同步方式：只执行 `git pull --ff-only`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_prefix_cache_ab_handoff.md`
- 核心脚本：`tools/inference_contracts/run_vllm_api_concurrency_smoke.py`

## 先处理通信收件人变更

本次 pull 后，请先同步服务器本地通信配置：

- 当前项目默认收件人已改为只发送到 `yilili1023@gmail.com`。
- 不再发送到 `gwlee1995@gmail.com`。
- 如果服务器项目根目录 `.env` 仍有旧值，请把 `AK_COMM_MAIL_TO` 改为：

```bash
AK_COMM_MAIL_TO=yilili1023@gmail.com
```

请不要在邮件或附件中回传 `.env`、SMTP 授权码或代理凭据。只需要在本次任务完成邮件正文中脱敏报告：

```text
通信收件人配置：AK_COMM_MAIL_TO=yilili1023@gmail.com
已确认不再发送到 gwlee1995@gmail.com
```

可用以下命令在服务器本地脱敏确认，不会发送邮件：

```bash
python3 通信模块/send_notify.py --show-config
```

P1.21 `runtime_vllm_api_continuous16_mixed_retry_2026_0707_p1_021` 已完成并成功：

- `pytest_exit_code=0`
- `vllm_api_continuous16_mixed_retry_exit_code=0`
- `case_plan=continuous16_mixed`
- `max_model_len=9216`
- `request_count=16`
- `success_case_count=16`
- `failed_case_count=0`
- `client_overlap_candidate_count=120`
- `trace_validation_errors=0`
- `server_stats_sample_count=2`
- `server_stats_max_running_reqs=16`
- `server_stats_max_waiting_reqs=1`
- `server_stats_max_kv_cache_usage_pct=8.6`
- `server_stats_max_prefix_cache_hit_rate_pct=52.1`

本轮不再重复单次 smoke，而是使用同一 `continuous16_mixed` 16 请求负载做两轮受控对照：

1. `prefix_cache_on`：启用 `--enable-prefix-caching`。
2. `prefix_cache_off`：显式关闭 prefix cache，不传 `--enable-prefix-caching`。

本轮只收集开关路径、server command、client overlap、P1 trace 校验和 vLLM 自带 server log stats。它不是 benchmark、压测、吞吐比较、调度效率结论、prefix cache 命中验收、瓶颈归因或 CANN device timeline pairing。

## 本轮必须回答

1. 当前环境中 `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 是否可 import？
2. 两轮 `run_context.txt` 是否都记录 `max_model_len=9216`？
3. `prefix_cache_on/vllm_api_server_command.json` 是否包含 `--enable-prefix-caching`？
4. `prefix_cache_off/vllm_api_server_command.json` 是否不包含 `--enable-prefix-caching`？
5. 两轮是否都使用 `--case-plan continuous16_mixed` 并发送相同 16 个 case？
6. 两轮 vLLM OpenAI API server 是否都能 ready？
7. 两轮 16 个 case 是否都返回 HTTP 200，并生成非空输出或正的 `generated_token_count`？
8. 两轮每个 case 的 `submitted_input_token_count` 是否等于 `input_token_count`？
9. 两轮客户端侧请求时间窗是否都有 overlap candidate？
10. 两轮 `vllm_api_concurrency_trace.jsonl` 是否都通过 P1 validator？
11. 两轮是否都导出 `vllm_api_server_stats_summary.tsv`；如果关闭 prefix cache 后日志不再输出 `Prefix cache hit rate` 字段，请原样记录为缺失，不要现场改脚本或改环境。
12. 总结文件 `prefix_cache_ab_summary.tsv` 是否记录两轮 prefix 开关、请求成功数、overlap、Running/Waiting/KV/prefix-cache 自带统计字段？

## 严格边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境已有 `vllm` 和 `vllm_ascend`
- 设置本进程环境变量 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS=ascend`、`VLLM_WORKER_MULTIPROC_METHOD`
- 设置 `AK_VLLM_MAX_MODEL_LEN=9216`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 在 `127.0.0.1` 先后启动两个临时 vLLM OpenAI API server
- 每轮只向本机回环 `/v1/completions` 发送 `continuous16_mixed` 的 16 个请求
- 导出两轮 server command、run context、server log、server log stats summary、trace、summary、result、generated texts、失败日志和总 summary

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不静默降低 `max_model_len`
- 不删减 case、不降低输入 cap、不缩短 output token
- 不运行 benchmark、吞吐测试、压测或长时间服务
- 不运行多 worker 压测客户端
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不切换到 Docker 推理栈；Docker 内 vLLM/torch_npu 另起任务
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不启用 profiler 导出；profiler/CANN pairing 另起任务处理
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、吞吐结论、调度效率结论、prefix cache 命中率结论、瓶颈归因、优化建议或 CANN device timeline pairing 结论

## 建议执行命令

请在服务器项目根目录执行：

```bash
set -euo pipefail

cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

if [ -f .env ]; then
  if grep -q '^AK_COMM_MAIL_TO=.*gwlee1995@gmail.com' .env; then
    python - <<'PY'
from pathlib import Path
path = Path(".env")
lines = path.read_text(encoding="utf-8").splitlines()
updated = []
seen = False
for line in lines:
    if line.startswith("AK_COMM_MAIL_TO="):
        updated.append("AK_COMM_MAIL_TO=yilili1023@gmail.com")
        seen = True
    else:
        updated.append(line)
if not seen:
    updated.append("AK_COMM_MAIL_TO=yilili1023@gmail.com")
path.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY
  elif ! grep -q '^AK_COMM_MAIL_TO=' .env; then
    printf '\nAK_COMM_MAIL_TO=yilili1023@gmail.com\n' >> .env
  fi
else
  printf 'AK_COMM_MAIL_TO=yilili1023@gmail.com\n' > .env
fi

RUN_ID=runtime_vllm_api_prefix_cache_ab_2026_0707_p1_022
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH="${AK_SMALL_MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"

export RUN_ID ARTIFACT_DIR MODEL_PATH
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

python tools/inference_contracts/run_vllm_api_concurrency_smoke.py \
  --run-id "${RUN_ID}_prefix_cache_on" \
  --artifact-dir "${ARTIFACT_DIR}/prefix_cache_on" \
  --model-path "${MODEL_PATH}" \
  --case-plan continuous16_mixed \
  --max-model-len "${AK_VLLM_MAX_MODEL_LEN}" \
  --enable-prefix-caching \
  > "${ARTIFACT_DIR}/prefix_cache_on.log" 2>&1
prefix_cache_on_exit_code=$?

python tools/inference_contracts/run_vllm_api_concurrency_smoke.py \
  --run-id "${RUN_ID}_prefix_cache_off" \
  --artifact-dir "${ARTIFACT_DIR}/prefix_cache_off" \
  --model-path "${MODEL_PATH}" \
  --case-plan continuous16_mixed \
  --max-model-len "${AK_VLLM_MAX_MODEL_LEN}" \
  --no-enable-prefix-caching \
  > "${ARTIFACT_DIR}/prefix_cache_off.log" 2>&1
prefix_cache_off_exit_code=$?
set -e

{
  echo "run_id=${RUN_ID}"
  echo "commit=$(git rev-parse HEAD)"
  echo "timestamp=$(date '+%Y-%m-%dT%H:%M:%S%z')"
  echo "MODEL_PATH=${MODEL_PATH}"
  echo "CASE_PLAN=continuous16_mixed"
  echo "max_model_len=${AK_VLLM_MAX_MODEL_LEN}"
  echo "pytest_exit_code=${pytest_exit_code}"
  echo "prefix_cache_on_exit_code=${prefix_cache_on_exit_code}"
  echo "prefix_cache_off_exit_code=${prefix_cache_off_exit_code}"
} > "${ARTIFACT_DIR}/run_context.txt"

python - "${ARTIFACT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
modes = {
    "prefix_cache_on": 1,
    "prefix_cache_off": 0,
}
errors = []
summary_rows = []

for mode, expected_prefix in modes.items():
    run_dir = artifact_dir / mode
    result_path = run_dir / "vllm_api_concurrency_result.json"
    cmd_path = run_dir / "vllm_api_server_command.json"
    context_path = run_dir / "run_context.txt"
    if not result_path.is_file():
        errors.append(f"{mode}: missing result json")
        continue
    result = json.loads(result_path.read_text(encoding="utf-8"))
    cmd = json.loads(cmd_path.read_text(encoding="utf-8")) if cmd_path.is_file() else []
    context = context_path.read_text(encoding="utf-8") if context_path.is_file() else ""
    has_prefix_flag = "--enable-prefix-caching" in cmd
    if bool(has_prefix_flag) != bool(expected_prefix):
        errors.append(f"{mode}: unexpected enable-prefix-caching flag={has_prefix_flag}")
    if "max_model_len=9216" not in context:
        errors.append(f"{mode}: run_context missing max_model_len=9216")
    if result.get("status") != "success":
        errors.append(f"{mode}: status={result.get('status')}")
    if result.get("case_plan") != "continuous16_mixed":
        errors.append(f"{mode}: case_plan={result.get('case_plan')}")
    if result.get("request_count") != 16:
        errors.append(f"{mode}: request_count={result.get('request_count')}")
    if result.get("success_case_count") != 16:
        errors.append(f"{mode}: success_case_count={result.get('success_case_count')}")
    if result.get("failed_case_count") != 0:
        errors.append(f"{mode}: failed_case_count={result.get('failed_case_count')}")
    if int(result.get("client_overlap_candidate_count") or 0) <= 0:
        errors.append(f"{mode}: client_overlap_candidate_count={result.get('client_overlap_candidate_count')}")
    if result.get("trace_validation_errors") != 0:
        errors.append(f"{mode}: trace_validation_errors={result.get('trace_validation_errors')}")
    if result.get("server_ready") != 1:
        errors.append(f"{mode}: server_ready={result.get('server_ready')}")
    for name, status in result.get("import_probe", {}).items():
        if status != "ok":
            errors.append(f"{mode}: import_failed={name}")
    for row in result.get("rows", []):
        if row.get("status") != "success":
            errors.append(f"{mode}: {row.get('case_id')} status={row.get('status')}")
        if row.get("submitted_input_token_count") != row.get("input_token_count"):
            errors.append(f"{mode}: {row.get('case_id')} submitted_input_count_mismatch")

    summary_rows.append({
        "mode": mode,
        "prefix_cache_requested": result.get("prefix_cache_requested"),
        "status": result.get("status"),
        "request_count": result.get("request_count"),
        "success_case_count": result.get("success_case_count"),
        "client_overlap_candidate_count": result.get("client_overlap_candidate_count"),
        "server_stats_sample_count": result.get("server_stats_sample_count"),
        "server_stats_max_running_reqs": result.get("server_stats_max_running_reqs"),
        "server_stats_max_waiting_reqs": result.get("server_stats_max_waiting_reqs"),
        "server_stats_max_kv_cache_usage_pct": result.get("server_stats_max_kv_cache_usage_pct"),
        "server_stats_max_prefix_cache_hit_rate_pct": result.get("server_stats_max_prefix_cache_hit_rate_pct"),
        "server_command_has_enable_prefix_caching": int(has_prefix_flag),
    })

header = [
    "mode",
    "prefix_cache_requested",
    "status",
    "request_count",
    "success_case_count",
    "client_overlap_candidate_count",
    "server_stats_sample_count",
    "server_stats_max_running_reqs",
    "server_stats_max_waiting_reqs",
    "server_stats_max_kv_cache_usage_pct",
    "server_stats_max_prefix_cache_hit_rate_pct",
    "server_command_has_enable_prefix_caching",
]
lines = ["\t".join(header)]
for row in summary_rows:
    lines.append("\t".join(str(row.get(key, "")) for key in header))
(artifact_dir / "prefix_cache_ab_summary.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
(artifact_dir / "prefix_cache_ab_result.json").write_text(
    json.dumps({"status": "failed" if errors else "success", "errors": errors, "rows": summary_rows}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
(artifact_dir / "vllm_api_prefix_cache_ab_validation.txt").write_text(
    "\n".join(errors) + "\n" if errors else "errors=0\n",
    encoding="utf-8",
)
sys.exit(1 if errors else 0)
PY
prefix_cache_ab_validation_exit_code=$?

echo "prefix_cache_ab_validation_exit_code=${prefix_cache_ab_validation_exit_code}" >> "${ARTIFACT_DIR}/run_context.txt"

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt" 2>/dev/null || true
  echo
  echo "## prefix_cache_ab_summary"
  cat "${ARTIFACT_DIR}/prefix_cache_ab_summary.tsv" 2>/dev/null || true
  echo
  echo "## validation"
  cat "${ARTIFACT_DIR}/vllm_api_prefix_cache_ab_validation.txt" 2>/dev/null || true
  echo
  echo "## prefix_cache_on conclusion"
  cat "${ARTIFACT_DIR}/prefix_cache_on/vllm_api_concurrency_conclusion.txt" 2>/dev/null || true
  echo
  echo "## prefix_cache_on server_command"
  cat "${ARTIFACT_DIR}/prefix_cache_on/vllm_api_server_command.json" 2>/dev/null || true
  echo
  echo "## prefix_cache_on server_stats"
  cat "${ARTIFACT_DIR}/prefix_cache_on/vllm_api_server_stats_summary.tsv" 2>/dev/null || true
  echo
  echo "## prefix_cache_off conclusion"
  cat "${ARTIFACT_DIR}/prefix_cache_off/vllm_api_concurrency_conclusion.txt" 2>/dev/null || true
  echo
  echo "## prefix_cache_off server_command"
  cat "${ARTIFACT_DIR}/prefix_cache_off/vllm_api_server_command.json" 2>/dev/null || true
  echo
  echo "## prefix_cache_off server_stats"
  cat "${ARTIFACT_DIR}/prefix_cache_off/vllm_api_server_stats_summary.tsv" 2>/dev/null || true
} > "${ARTIFACT_DIR}/summary.txt"

zip -qr "${ARTIFACT_DIR}.zip" "${ARTIFACT_DIR}"

python 通信模块/scripts/send_notify.py \
  --subject "[AK服务器] 任务完成：vLLM API prefix-cache A/B stats ${RUN_ID}" \
  --body-file "${ARTIFACT_DIR}/summary.txt" \
  --attach "${ARTIFACT_DIR}.zip" \
  --attach "${ARTIFACT_DIR}/summary.txt"

exit_code=0
if [ "${pytest_exit_code}" -ne 0 ]; then exit_code=1; fi
if [ "${prefix_cache_on_exit_code}" -ne 0 ]; then exit_code=1; fi
if [ "${prefix_cache_off_exit_code}" -ne 0 ]; then exit_code=1; fi
if [ "${prefix_cache_ab_validation_exit_code}" -ne 0 ]; then exit_code=1; fi
exit "${exit_code}"
```

## 回传要求

请邮件正文至少包含：

- `run_id`
- `commit`
- `artifact_dir`
- `pytest_exit_code`
- `prefix_cache_on_exit_code`
- `prefix_cache_off_exit_code`
- `prefix_cache_ab_validation_exit_code`

请附件包含：

- `${ARTIFACT_DIR}.zip`
- `${ARTIFACT_DIR}/summary.txt`

边界说明请明确写入邮件正文：

- 使用当前环境已有 vLLM / vLLM-Ascend。
- 使用 `VLLM_PLUGINS=ascend`，并加载 CANN/ATB 环境。
- 同一 `continuous16_mixed` 16 请求负载连续执行 `prefix_cache_on` 与 `prefix_cache_off` 两轮。
- A/B 只验证 prefix-cache 开关路径和 vLLM 自带 stats 字段是否可对照，不输出性能 benchmark、吞吐比较、调度效率、prefix cache 命中验收、瓶颈归因或优化建议。
- 未安装、升级、卸载或修复任何包。
- 未运行 full 16K/32K 或 full `P010=43216` tokens。
- 未启用 profiler；未声称 CANN device timeline pairing。
