# 开发机给服务器的任务说明

## 当前任务：P1.21 vLLM API continuous16 mixed retry

- 任务 ID：`runtime_vllm_api_continuous16_mixed_retry_2026_0707_p1_021`
- 当前开发机分支：`main`
- 服务器同步方式：只执行 `git pull --ff-only`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_api_continuous16_mixed_retry_handoff.md`
- 核心脚本：`tools/inference_contracts/run_vllm_api_concurrency_smoke.py`

P1.20 `runtime_vllm_api_continuous16_mixed_2026_0706_p1_020` 已完成但部分失败：

- `pytest_exit_code=0`
- `vllm_api_continuous16_mixed_exit_code=1`
- `server_ready=1`
- `request_count=16`
- `success_case_count=6`
- `failed_case_count=10`
- `client_overlap_candidate_count=75`
- `trace_validation_errors=0`
- `server_stats_sample_count=1`
- 失败原因明确：API server 实际以 `--max-model-len 6144` 启动，10 个 8K cap case 因 `6081 input + 64 output = 6145` 被 vLLM HTTP 400 拒绝。

本轮目标不是换新负载，而是纠正 P1.20 的配置边界：同一 `continuous16_mixed` 16 请求负载必须以 `--max-model-len 9216` 启动并复跑。它仍不是 benchmark、压测、性能归因、prefix cache 命中验收或 CANN device timeline pairing。

## 本轮必须回答

1. 当前环境中 `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 是否可 import？
2. `vllm_api_server_command.json` 是否明确记录 `--max-model-len 9216`？
3. `run_context.txt` 是否明确记录 `max_model_len=9216`？
4. 使用 `VLLM_PLUGINS=ascend` 并 source CANN/ATB 环境后，vLLM OpenAI API server 是否能启动？
5. `/health` 是否 ready？
6. `/v1/completions` 是否能接受 16 个错开请求？
7. 16 个 case 是否全部返回 HTTP 200？
8. 16 个 case 是否全部生成非空输出或正的 `generated_token_count`？
9. 每个 case 的 `submitted_input_token_count` 是否等于 `input_token_count`？
10. 客户端侧请求时间窗是否出现 overlap candidate？
11. 是否能生成合法的 `vllm_api_concurrency_trace.jsonl` 并通过 P1 validator？
12. 是否能生成 `vllm_api_server_stats_summary.tsv`，并从 server log 中抽取 Running/Waiting/KV/prefix-cache 统计？
13. 如果失败，失败点是 max-model-len 未生效、api_server_start、health_probe、HTTP 400、输出为空、input_count_mismatch、NPU/OOM、trace 校验，还是 server log stats 缺失？

## 本轮 case

本轮仍使用脚本参数：

```bash
--case-plan continuous16_mixed
```

保持 P1.20 相同 16 个 case，不删减、不降低 cap、不缩短 decode：

| case_id | prompt_id | cap_tokens | max_new_tokens | delay | 目的 |
| --- | --- | ---: | ---: | ---: | --- |
| `P007_api_continuous16_prefix_first_cap8192_gen64` | `P007` | 8192 | 64 | 0ms | repeated-prefix pair 第一条 |
| `P008_api_continuous16_prefix_second_cap8192_gen64` | `P008` | 8192 | 64 | 100ms | repeated-prefix pair 第二条 |
| `P011_api_continuous16_burst_001_cap4096_gen64` | `P011` | 4096 | 64 | 200ms | burst queue 候选 |
| `P011_api_continuous16_burst_002_cap4096_gen64` | `P011` | 4096 | 64 | 300ms | burst queue 候选 |
| `P011_api_continuous16_burst_003_cap4096_gen64` | `P011` | 4096 | 64 | 400ms | burst queue 候选 |
| `P011_api_continuous16_burst_004_cap4096_gen64` | `P011` | 4096 | 64 | 500ms | burst queue 候选 |
| `P012_api_continuous16_001_cap8192_gen64` | `P012` | 8192 | 64 | 600ms | continuous-arrival 候选 |
| `P012_api_continuous16_002_cap8192_gen64` | `P012` | 8192 | 64 | 800ms | continuous-arrival 候选 |
| `P012_api_continuous16_003_cap8192_gen64` | `P012` | 8192 | 64 | 1000ms | continuous-arrival 候选 |
| `P012_api_continuous16_004_cap8192_gen64` | `P012` | 8192 | 64 | 1200ms | continuous-arrival 候选 |
| `P012_api_continuous16_005_cap8192_gen64` | `P012` | 8192 | 64 | 1400ms | continuous-arrival 候选 |
| `P012_api_continuous16_006_cap8192_gen64` | `P012` | 8192 | 64 | 1600ms | continuous-arrival 候选 |
| `P003_api_continuous16_system_001_cap8192_gen64` | `P003` | 8192 | 64 | 1800ms | long-system 候选 |
| `P003_api_continuous16_system_002_cap8192_gen64` | `P003` | 8192 | 64 | 2000ms | long-system 候选 |
| `P009_api_continuous16_moe_001_cap8192_gen64` | `P009` | 8192 | 64 | 2200ms | mixed-reasoning 候选 |
| `P009_api_continuous16_moe_002_cap8192_gen64` | `P009` | 8192 | 64 | 2400ms | mixed-reasoning 候选 |

## 严格边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境里已有的 `vllm` 和 `vllm_ascend`
- 设置本进程环境变量 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS=ascend`、`VLLM_WORKER_MULTIPROC_METHOD`
- 设置 `AK_VLLM_MAX_MODEL_LEN=9216`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 在 `127.0.0.1` 启动一个临时 vLLM OpenAI API server
- 只向本机回环 `/v1/completions` 发送本 handoff 列出的 16 个请求
- 导出 server command、server log、server log stats summary、trace、summary、generated texts、失败日志和邮件附件

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
- 不输出性能 benchmark、吞吐结论、调度效率结论、瓶颈归因、优化建议或 CANN device timeline pairing 结论
- 不把 `Prefix cache hit rate` 日志字段单独解释成严格 prefix cache 命中验收

## 建议执行命令

请在服务器项目根目录执行：

```bash
set -euo pipefail

cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

RUN_ID=runtime_vllm_api_continuous16_mixed_retry_2026_0707_p1_021
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH="${AK_SMALL_MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"

export RUN_ID ARTIFACT_DIR MODEL_PATH
export PYTHONUNBUFFERED=1
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
export AK_VLLM_ENABLE_PREFIX_CACHING="${AK_VLLM_ENABLE_PREFIX_CACHING:-1}"
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
  --run-id "${RUN_ID}" \
  --artifact-dir "${ARTIFACT_DIR}" \
  --model-path "${MODEL_PATH}" \
  --case-plan continuous16_mixed \
  --max-model-len "${AK_VLLM_MAX_MODEL_LEN}" \
  > "${ARTIFACT_DIR}/vllm_api_continuous16_mixed_retry.log" 2>&1
vllm_exit_code=$?
set -e

{
  echo "pytest_exit_code=${pytest_exit_code}"
  echo "vllm_api_continuous16_mixed_retry_exit_code=${vllm_exit_code}"
} >> "${ARTIFACT_DIR}/run_context.txt"

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt" 2>/dev/null || true
  echo
  echo "## server_command"
  cat "${ARTIFACT_DIR}/vllm_api_server_command.json" 2>/dev/null || true
  echo
  echo "## import_probe"
  cat "${ARTIFACT_DIR}/vllm_import_probe.tsv" 2>/dev/null || true
  echo
  echo "## conclusion"
  cat "${ARTIFACT_DIR}/vllm_api_concurrency_conclusion.txt" 2>/dev/null || true
  echo
  echo "## summary"
  cat "${ARTIFACT_DIR}/vllm_api_concurrency_summary.tsv" 2>/dev/null || true
  echo
  echo "## server_stats"
  cat "${ARTIFACT_DIR}/vllm_api_server_stats_summary.tsv" 2>/dev/null || true
  echo
  echo "## validation"
  cat "${ARTIFACT_DIR}/vllm_api_concurrency_validation.txt" 2>/dev/null || true
  echo
  echo "## model_path_precheck"
  cat "${ARTIFACT_DIR}/model_path_precheck.txt" 2>/dev/null || true
} > "${ARTIFACT_DIR}/summary.txt"

python - <<'PY' "${ARTIFACT_DIR}"
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
result_path = artifact_dir / "vllm_api_concurrency_result.json"
server_cmd_path = artifact_dir / "vllm_api_server_command.json"
run_context_path = artifact_dir / "run_context.txt"
validation_path = artifact_dir / "vllm_api_continuous16_mixed_retry_validation_extra.txt"

errors = []
if not result_path.is_file():
    errors.append("missing result json")
else:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != "success":
        errors.append(f"status={result.get('status')}")
    if result.get("server_ready") != 1:
        errors.append(f"server_ready={result.get('server_ready')}")
    if result.get("case_plan") != "continuous16_mixed":
        errors.append(f"case_plan={result.get('case_plan')}")
    if result.get("request_count") != 16:
        errors.append(f"request_count={result.get('request_count')}")
    if result.get("success_case_count") != 16:
        errors.append(f"success_case_count={result.get('success_case_count')}")
    if int(result.get("client_overlap_candidate_count") or 0) <= 0:
        errors.append(f"client_overlap_candidate_count={result.get('client_overlap_candidate_count')}")
    if result.get("trace_validation_errors") != 0:
        errors.append(f"trace_validation_errors={result.get('trace_validation_errors')}")
    if int(result.get("server_stats_sample_count") or 0) <= 0:
        errors.append(f"server_stats_sample_count={result.get('server_stats_sample_count')}")
    for name, status in result.get("import_probe", {}).items():
        if status != "ok":
            errors.append(f"import_failed={name}")
    for row in result.get("rows", []):
        if row.get("status") != "success":
            errors.append(f"{row.get('case_id')} status={row.get('status')} error_type={row.get('error_type')}")
        if row.get("submitted_input_token_count") != row.get("input_token_count"):
            errors.append(f"{row.get('case_id')} submitted_input_count_mismatch")
        if int(row.get("generated_token_count", 0)) <= 0 and not row.get("generated_text_nonempty"):
            errors.append(f"{row.get('case_id')} empty_generation")

if server_cmd_path.is_file():
    cmd = json.loads(server_cmd_path.read_text(encoding="utf-8"))
    try:
        max_model_len = cmd[cmd.index("--max-model-len") + 1]
    except (ValueError, IndexError):
        max_model_len = ""
    if str(max_model_len) != "9216":
        errors.append(f"server_command_max_model_len={max_model_len or 'missing'}")
else:
    errors.append("missing server command json")

if run_context_path.is_file():
    run_context = run_context_path.read_text(encoding="utf-8")
    if "max_model_len=9216" not in run_context:
        errors.append("run_context_max_model_len_not_9216")
else:
    errors.append("missing run_context")

validation_path.write_text("errors=0\n" if not errors else "\n".join(errors) + "\n", encoding="utf-8")
print("errors=0" if not errors else "\n".join(errors))
PY

(
  cd "工作记录与进度笔记本/runtime_trace_smokes"
  rm -f "${RUN_ID}.zip"
  zip -r "${RUN_ID}.zip" "${RUN_ID}"
)

cat > "${ARTIFACT_DIR}/mail_body.txt" <<EOF
P1.21 vLLM API continuous16 mixed retry 已完成。

run_id: ${RUN_ID}
commit: $(git rev-parse HEAD)
artifact_dir: ${ARTIFACT_DIR}
pytest_exit_code: ${pytest_exit_code}
vllm_api_continuous16_mixed_retry_exit_code: ${vllm_exit_code}

请见附件 zip 和 summary.txt。

边界说明：
- 使用当前环境已有 vLLM / vLLM-Ascend。
- 使用 VLLM_PLUGINS=ascend，并加载 CANN/ATB 环境。
- 启动本机回环 vLLM OpenAI API server，发送与 P1.20 相同的 16 个错开请求。
- 本轮必须以 --max-model-len 9216 启动，并回传 vllm_api_server_command.json 与 run_context.txt 作为生效证据。
- vLLM server log 中 Running/Waiting/KV/prefix-cache 统计只作为候选观测数据，不作为性能 benchmark 或 prefix cache 命中验收。
- 未安装、升级、卸载或修复任何包。
- 未运行 benchmark、压测、多 worker 并发、full 16K/32K 或 full P010=43216 tokens。
- 未启用 profiler；未声称 CANN device timeline pairing。
- 未输出性能 benchmark、吞吐结论、调度效率结论、瓶颈归因或优化建议。
EOF

python 通信模块/send_notify.py \
  -s "[AK服务器] 任务完成：vLLM API continuous16 mixed retry ${RUN_ID}" \
  -b "$(cat "${ARTIFACT_DIR}/mail_body.txt")" \
  -a "工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}.zip" \
  -a "${ARTIFACT_DIR}/summary.txt"

exit "${vllm_exit_code}"
```

## 回传要求

邮件正文至少包含：

- `run_id`
- 当前 commit
- artifact 目录
- `pytest_exit_code`
- `vllm_api_continuous16_mixed_retry_exit_code`
- `status`
- `server_ready`
- `request_count`
- `success_case_count`
- `failed_case_count`
- `client_overlap_candidate_count`
- `trace_validation_errors`
- `server_stats_sample_count`
- `server_command_max_model_len`
- `run_context_max_model_len`
- 如失败，直接给出失败阶段和第一条关键错误。

附件至少包含：

- `runtime_vllm_api_continuous16_mixed_retry_2026_0707_p1_021.zip`
- `summary.txt`
- `vllm_api_server_command.json`
- `run_context.txt`
- `vllm_import_probe.tsv`
- `vllm_api_server.log`
- `vllm_api_server_stats_summary.tsv`
- `vllm_api_concurrency_result.json`
- `vllm_api_concurrency_summary.tsv`
- `vllm_api_concurrency_trace.jsonl`
- `vllm_api_concurrency_validation.txt`
- `vllm_api_continuous16_mixed_retry_validation_extra.txt`
- `generated_texts/`
