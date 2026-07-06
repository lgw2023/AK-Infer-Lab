# 开发机给服务器的任务说明

## 当前任务：P1.15 long prompt envelope decode matrix

- 任务 ID：`runtime_long_prompt_envelope_decode_2026_0706_p1_015`
- 当前开发机分支：`main`
- 服务器同步方式：只执行 `git pull --ff-only`
- 详细 handoff：`工作记录与进度笔记本/p1_inference_contracts/server_runtime_long_prompt_envelope_handoff.md`
- 核心脚本：`tools/inference_contracts/run_long_prompt_envelope.py`

P1.14 `runtime_long_prompt_trace_matrix_2026_0706_p1_014` 已完成：服务器现有 `Qwen3.5-4B + transformers + torch_npu` 路径在 `npu:6` 上完成了 `P000-P012` 全量 13 条长 prompt 的 4K/8K cap 顺序单请求 trace matrix，`attempted_case_count=13`、`success_case_count=13`、`input_count_mismatch_count=0`、`trace_event_count=91`、`trace_validation_errors=0`。

本轮可以适当扩大步幅：同时测试输入 cap 和 decode 深度的 envelope matrix。仍不运行 vLLM、不安装包、不修环境、不切换 Docker 推理栈、不跑并发、不处理 profiler/CANN pairing、不输出性能或瓶颈归因结论。

## 本轮问题

请服务器回答：

1. 8 个 envelope case 是否能在现有模型路径和 `npu:6` 上完成？
2. 每个 case 的 `input_token_count` 是否等于 `min(full_token_count, cap_tokens)`？
3. 每个 case 是否生成非空 token/text？
4. 是否能生成合法的 `long_prompt_envelope_decode_trace.jsonl` 并通过 P1 validator？
5. 如果失败，失败点是模型加载、tokenizer、NPU/OOM、特定 case 推理、输出为空，还是 trace 校验？

## 本轮 case

| case_id | prompt_id | cap_tokens | max_new_tokens |
| --- | --- | ---: | ---: |
| `P002_cap4096_gen32` | `P002` | 4096 | 32 |
| `P003_cap8192_gen32` | `P003` | 8192 | 32 |
| `P005_cap8192_gen128` | `P005` | 8192 | 128 |
| `P006_cap12288_gen32` | `P006` | 12288 | 32 |
| `P007_cap4096_gen32` | `P007` | 4096 | 32 |
| `P008_cap4096_gen32` | `P008` | 4096 | 32 |
| `P010_cap16384_gen32` | `P010` | 16384 | 32 |
| `P012_cap8192_gen128` | `P012` | 8192 | 128 |

`P007/P008` 只作为普通顺序请求执行，不能声称 prefix cache 命中。`P012` 只作为普通单请求执行，不能声称 continuous batching 行为。

## 严格边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 使用现有 `transformers + torch_npu`
- 默认使用 `npu:6`，可由 `AK_SMALL_MODEL_DEVICE` 覆盖
- 顺序执行上面 8 个单请求 envelope case
- 导出 trace、summary、generated texts、失败日志和邮件附件

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 vLLM engine、serve、benchmark 或 vLLM-Ascend 任务
- 不运行并发、burst、continuous batching 或 prefix cache 结论型测试
- 不运行 full 32K 或 full `P010=43216` tokens
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不启用 profiler 导出；profiler/CANN pairing 另起任务处理
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、瓶颈归因、优化建议或 CANN device timeline pairing 结论

## 建议执行命令

请在服务器项目根目录执行：

```bash
set -euo pipefail

cd /data/node0_disk1/liguowei/AK-Infer-Lab
git pull --ff-only

RUN_ID=runtime_long_prompt_envelope_decode_2026_0706_p1_015
ARTIFACT_DIR="工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}"
MODEL_PATH="${AK_SMALL_MODEL_PATH:-/data/node0_disk1/Public/Qwen3.5-4B}"
DEVICE="${AK_SMALL_MODEL_DEVICE:-npu:6}"

export RUN_ID ARTIFACT_DIR MODEL_PATH DEVICE
export PYTHONUNBUFFERED=1

mkdir -p "${ARTIFACT_DIR}"

set +e
python -m pytest tests/inference_contracts -q > "${ARTIFACT_DIR}/pytest_inference_contracts.log" 2>&1
pytest_exit_code=$?
python tools/inference_contracts/run_long_prompt_envelope.py \
  --run-id "${RUN_ID}" \
  --artifact-dir "${ARTIFACT_DIR}" \
  --model-path "${MODEL_PATH}" \
  --device "${DEVICE}" \
  > "${ARTIFACT_DIR}/long_prompt_envelope_decode.log" 2>&1
envelope_exit_code=$?
set -e

{
  echo "pytest_exit_code=${pytest_exit_code}"
  echo "long_prompt_envelope_decode_exit_code=${envelope_exit_code}"
} >> "${ARTIFACT_DIR}/run_context.txt"

{
  echo "## run_context"
  cat "${ARTIFACT_DIR}/run_context.txt"
  echo
  echo "## conclusion"
  cat "${ARTIFACT_DIR}/long_prompt_envelope_decode_conclusion.txt" 2>/dev/null || true
  echo
  echo "## summary"
  cat "${ARTIFACT_DIR}/long_prompt_envelope_decode_summary.tsv" 2>/dev/null || true
  echo
  echo "## validation"
  cat "${ARTIFACT_DIR}/long_prompt_envelope_decode_validation.txt" 2>/dev/null || true
  echo
  echo "## model_path_precheck"
  cat "${ARTIFACT_DIR}/model_path_precheck.txt" 2>/dev/null || true
} > "${ARTIFACT_DIR}/summary.txt"

python - <<'PY' "${ARTIFACT_DIR}"
import json
import sys
from pathlib import Path

artifact_dir = Path(sys.argv[1])
result_path = artifact_dir / "long_prompt_envelope_decode_result.json"
validation_path = artifact_dir / "long_prompt_envelope_decode_validation_extra.txt"
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
for row in result.get("rows", []):
    if row.get("status") != "success":
        errors.append(f"{row.get('case_id')} status={row.get('status')} error_type={row.get('error_type')}")
    if row.get("input_token_count") != row.get("expected_input_token_count"):
        errors.append(f"{row.get('case_id')} input_count_mismatch")
    if int(row.get("generated_token_count", 0)) <= 0:
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
P1.15 long prompt envelope decode matrix 已完成。

run_id: ${RUN_ID}
commit: $(git rev-parse HEAD)
artifact_dir: ${ARTIFACT_DIR}
pytest_exit_code: ${pytest_exit_code}
long_prompt_envelope_decode_exit_code: ${envelope_exit_code}

请见附件 zip 和 summary.txt。

边界说明：
- 使用现有 Qwen3.5-4B + transformers + torch_npu 路径。
- 未运行 vLLM engine/serve/benchmark。
- 未安装、升级、卸载或修复任何包。
- 未运行并发、burst、continuous batching 或 prefix cache 结论型测试。
- 未运行 full 32K 或 full P010=43216 tokens。
- 未启用 profiler；未声称 CANN device timeline pairing。
- 未输出性能 benchmark、瓶颈归因或优化建议。
EOF

python 通信模块/scripts/send_notify.py \
  -s "[AK服务器] 任务完成：long prompt envelope decode ${RUN_ID}" \
  -b "$(cat "${ARTIFACT_DIR}/mail_body.txt")" \
  -a "工作记录与进度笔记本/runtime_trace_smokes/${RUN_ID}.zip"

if [ "${pytest_exit_code}" -ne 0 ] || [ "${envelope_exit_code}" -ne 0 ]; then
  exit 1
fi
```

## 回传要求

请邮件附件至少包含：

- `runtime_long_prompt_envelope_decode_2026_0706_p1_015.zip`
- `run_context.txt`
- `pytest_inference_contracts.log`
- `package_inventory.tsv`
- `model_path_precheck.txt`
- `long_prompt_envelope_decode.log`
- `long_prompt_envelope_decode_trace.jsonl`
- `long_prompt_envelope_decode_result.json`
- `long_prompt_envelope_decode_summary.tsv`
- `long_prompt_envelope_decode_conclusion.txt`
- `long_prompt_envelope_decode_validation.txt`
- `long_prompt_envelope_decode_validation_extra.txt`
- `generated_texts/*.txt`
- `generated_texts/*_token_ids.json`
- `summary.txt`
- `mail_body.txt`

## 成功口径

- `pytest_exit_code=0`
- `long_prompt_envelope_decode_exit_code=0`
- 8 个 case 均完成单请求 prefill/decode
- 每个 case 有非空 generated token 或文本
- 每个 case 的 `input_token_count == min(full_token_count, cap_tokens)`
- `long_prompt_envelope_decode_trace.jsonl` 校验 `errors=0`

如果失败，请不要在服务器上现场修包或修改代码；直接回传失败 artifact 和错误日志。
