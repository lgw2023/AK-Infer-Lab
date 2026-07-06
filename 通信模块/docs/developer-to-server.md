# 开发机给服务器的任务说明

## 当前任务：P1.16 vLLM engine single-request smoke

- 任务 ID：`runtime_vllm_engine_single_request_smoke_2026_0706_p1_016`
- 当前开发机分支：`main`
- 服务器同步方式：只执行 `git pull --ff-only`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_vllm_engine_single_request_smoke_handoff.md`
- 核心脚本：`tools/inference_contracts/run_vllm_engine_single_request_smoke.py`

P1.15 `runtime_long_prompt_envelope_decode_2026_0706_p1_015` 已完成：服务器现有 `Qwen3.5-4B + transformers + torch_npu` 路径在 `npu:6` 上完成 8 个 envelope case，覆盖 4K/8K/12K/16K 输入 cap 和 32/128 new tokens decode，`attempted_case_count=8`、`success_case_count=8`、`input_count_mismatch_count=0`、`trace_event_count=56`、`trace_validation_errors=0`。

现在可以启动 vLLM，但必须作为独立新风险面。本轮只验证当前环境中的 vLLM/vLLM-Ascend engine 能否加载 `Qwen3.5-4B` 并完成 4K/8K 两个顺序单请求生成。仍不运行 serve、benchmark、并发、prefix cache、continuous batching、profiler 或性能归因。

## 本轮问题

请服务器回答：

1. 当前环境中 `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 是否可 import？
2. vLLM/vLLM-Ascend engine 是否能用 `/data/node0_disk1/Public/Qwen3.5-4B` 初始化？
3. `P002_cap4096_gen32` 是否能完成 vLLM 单请求生成？
4. `P003_cap8192_gen32` 是否能完成 vLLM 单请求生成？
5. 每个 case 的 `submitted_input_token_count` 是否等于 `input_token_count`？
6. 是否能生成合法的 `vllm_engine_single_request_trace.jsonl` 并通过 P1 validator？
7. 如果失败，失败点是 import、engine_init、tokenizer、input_count_mismatch、NPU/OOM、vLLM generate、输出为空，还是 trace 校验？

## 本轮 case

| case_id | prompt_id | cap_tokens | max_new_tokens |
| --- | --- | ---: | ---: |
| `P002_cap4096_gen32` | `P002` | 4096 | 32 |
| `P003_cap8192_gen32` | `P003` | 8192 | 32 |

本轮每次 `llm.generate()` 只提交一个 prompt，两个 case 顺序执行，不构成并发、batch、prefix cache 或 continuous batching 结论。

## 严格边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用当前环境里已有的 `vllm` 和 `vllm_ascend`
- 设置本进程环境变量 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS`、`VLLM_WORKER_MULTIPROC_METHOD`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 使用 vLLM public `LLM` / `SamplingParams` API
- 顺序执行上面 2 个单请求 case
- 导出 trace、summary、generated texts、失败日志和邮件附件

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 `vllm serve`、OpenAI API server、benchmark、压测或吞吐测试
- 不运行并发、burst、continuous batching 或 prefix cache 结论型测试
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不切换到 Docker 推理栈；Docker 内 vLLM/torch_npu 另起任务
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不启用 profiler 导出；profiler/CANN pairing 另起任务处理
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、瓶颈归因、优化建议、prefix cache 命中结论或 CANN device timeline pairing 结论

## 建议执行命令

请在服务器项目根目录执行：

```bash
set -euo pipefail

cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

RUN_ID=runtime_vllm_engine_single_request_smoke_2026_0706_p1_016
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH="${AK_SMALL_MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"

export RUN_ID ARTIFACT_DIR MODEL_PATH
export PYTHONUNBUFFERED=1
export ASCEND_RT_VISIBLE_DEVICES="${AK_VLLM_ASCEND_VISIBLE_DEVICES:-6}"
export AK_VLLM_DEVICE_LABEL="${AK_VLLM_DEVICE_LABEL:-npu:${ASCEND_RT_VISIBLE_DEVICES}}"
export VLLM_USE_V1="${VLLM_USE_V1:-1}"
export VLLM_PLUGINS="${VLLM_PLUGINS:-vllm_ascend}"
export VLLM_WORKER_MULTIPROC_METHOD="${VLLM_WORKER_MULTIPROC_METHOD:-spawn}"
export AK_VLLM_MAX_MODEL_LEN="${AK_VLLM_MAX_MODEL_LEN:-9216}"
export AK_VLLM_GPU_MEMORY_UTILIZATION="${AK_VLLM_GPU_MEMORY_UTILIZATION:-0.85}"
export AK_VLLM_TP_SIZE="${AK_VLLM_TP_SIZE:-1}"
export AK_VLLM_DTYPE="${AK_VLLM_DTYPE:-auto}"
export AK_VLLM_ENFORCE_EAGER="${AK_VLLM_ENFORCE_EAGER:-1}"

mkdir -p "${ARTIFACT_DIR}"

set +e
python -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
pytest_exit_code=$?
python tools/inference_contracts/run_vllm_engine_single_request_smoke.py \
  --run-id "${RUN_ID}" \
  --artifact-dir "${ARTIFACT_DIR}" \
  --model-path "${MODEL_PATH}" \
  > "${ARTIFACT_DIR}/vllm_engine_single_request.log" 2>&1
vllm_exit_code=$?
set -e

{
  echo "pytest_exit_code=${pytest_exit_code}"
  echo "vllm_engine_single_request_exit_code=${vllm_exit_code}"
} >> "${ARTIFACT_DIR}/run_context.txt"

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt" 2>/dev/null || true
  echo
  echo "## import_probe"
  cat "${ARTIFACT_DIR}/vllm_import_probe.tsv" 2>/dev/null || true
  echo
  echo "## conclusion"
  cat "${ARTIFACT_DIR}/vllm_engine_single_request_conclusion.txt" 2>/dev/null || true
  echo
  echo "## summary"
  cat "${ARTIFACT_DIR}/vllm_engine_single_request_summary.tsv" 2>/dev/null || true
  echo
  echo "## validation"
  cat "${ARTIFACT_DIR}/vllm_engine_single_request_validation.txt" 2>/dev/null || true
  echo
  echo "## model_path_precheck"
  cat "${ARTIFACT_DIR}/model_path_precheck.txt" 2>/dev/null || true
} > "${ARTIFACT_DIR}/summary.txt"

python - <<'PY' "${ARTIFACT_DIR}"
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
result_path = artifact_dir / "vllm_engine_single_request_result.json"
validation_path = artifact_dir / "vllm_engine_single_request_validation_extra.txt"
if not result_path.is_file():
    validation_path.write_text("missing result json\n", encoding="utf-8")
    print("missing result json")
    raise SystemExit(0)
result = json.loads(result_path.read_text(encoding="utf-8"))
errors = []
if result.get("status") != "success":
    errors.append(f"status={result.get('status')}")
if result.get("trace_validation_errors") != 0:
    errors.append(f"trace_validation_errors={result.get('trace_validation_errors')}")
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
validation_path.write_text("errors=0\n" if not errors else "\n".join(errors) + "\n", encoding="utf-8")
print("errors=0" if not errors else "\n".join(errors))
PY

(
  cd "工作记录与进度笔记本/runtime_trace_smokes"
  rm -f "${RUN_ID}.zip"
  zip -r "${RUN_ID}.zip" "${RUN_ID}"
)

cat > "${ARTIFACT_DIR}/mail_body.txt" <<EOF
P1.16 vLLM engine single-request smoke 已完成。

run_id: ${RUN_ID}
commit: $(git rev-parse HEAD)
artifact_dir: ${ARTIFACT_DIR}
pytest_exit_code: ${pytest_exit_code}
vllm_engine_single_request_exit_code: ${vllm_exit_code}

请见附件 zip 和 summary.txt。

边界说明：
- 使用当前环境已有 vLLM / vLLM-Ascend。
- 使用 Qwen3.5-4B，顺序执行 4K/8K 两个单请求 smoke。
- 未运行 vLLM serve/API server/benchmark。
- 未安装、升级、卸载或修复任何包。
- 未运行并发、burst、continuous batching 或 prefix cache 结论型测试。
- 未运行 full 16K/32K 或 full P010=43216 tokens。
- 未启用 profiler；未声称 CANN device timeline pairing。
- 未输出性能 benchmark、瓶颈归因或优化建议。
EOF

python 通信模块/scripts/send_notify.py \
  -s "[AK服务器] 任务完成：vLLM engine single-request smoke ${RUN_ID}" \
  -b "$(cat "${ARTIFACT_DIR}/mail_body.txt")" \
  -a "工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}.zip"

if [ "${pytest_exit_code}" -ne 0 ] || [ "${vllm_exit_code}" -ne 0 ]; then
  exit 1
fi
```

## 回传要求

请邮件附件至少包含：

- `runtime_vllm_engine_single_request_smoke_2026_0706_p1_016.zip`
- `run_context.txt`
- `pytest_inference_contracts.log`
- `package_inventory.tsv`
- `model_path_precheck.txt`
- `vllm_import_probe.tsv`
- `vllm_engine_single_request.log`
- `vllm_engine_init.json`
- `vllm_engine_single_request_trace.jsonl`
- `vllm_engine_single_request_result.json`
- `vllm_engine_single_request_summary.tsv`
- `vllm_engine_single_request_conclusion.txt`
- `vllm_engine_single_request_validation.txt`
- `vllm_engine_single_request_validation_extra.txt`
- `generated_texts/*.txt`
- `generated_texts/*_token_ids.json`
- `summary.txt`
- `mail_body.txt`

## 成功口径

- `pytest_exit_code=0`
- `vllm_engine_single_request_exit_code=0`
- `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 均 import 成功
- vLLM engine 初始化成功
- 2 个 case 均完成单请求生成
- 每个 case 有非空 generated token 或文本
- 每个 case 的 `submitted_input_token_count == input_token_count`
- `vllm_engine_single_request_trace.jsonl` 校验 `errors=0`

如果失败，请不要在服务器上现场修包或修改代码；直接回传失败 artifact 和错误日志。
