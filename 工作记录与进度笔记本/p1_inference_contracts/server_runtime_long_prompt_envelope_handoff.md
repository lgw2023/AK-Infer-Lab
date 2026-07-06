# P1.15 Long Prompt Envelope Decode Server Handoff

任务 ID：`runtime_long_prompt_envelope_decode_2026_0706_p1_015`

目标：在 P1.14 已证明 `P000-P012` 全量 13 条长 prompt 的 4K/8K cap 顺序单请求 trace matrix 成功后，把输入和输出压力同时扩大一档。本轮仍使用服务器现有 `Qwen3.5-4B + transformers + torch_npu` 路径，覆盖 4K/8K/12K/16K 输入 cap 和 32/128 新 token decode 深度。它不是 vLLM、不是并发、不是性能 benchmark，也不处理 profiler/CANN pairing。

## 背景

P1.14 `runtime_long_prompt_trace_matrix_2026_0706_p1_014` 已完成：

- 服务器执行 commit：`9123fc506cd365ac486f0f88176e2cf02a21b3b5`
- 服务器时间：2026-07-06 16:37:25 +08:00
- `pytest_exit_code=0`
- `matrix_status=success`
- `attempted_case_count=13`
- `success_case_count=13`
- `failed_case_count=0`
- `input_count_mismatch_count=0`
- `trace_event_count=91`
- `trace_validation_errors=0`
- `long_prompt_trace_matrix_full.jsonl` 覆盖 13 个 request 和 4 类 resource scope
- `torch_profiler_trace_exists=0`，profiler 本轮按 `candidate_only_optional_disabled_by_default` 处理

结论：现有 `Qwen3.5-4B + transformers + torch_npu` 路径已经能稳定完成全量长 prompt 的 4K/8K cap 主路径。下一步可以扩大输入 cap 和 decode 深度，但仍不能把结果解释成 vLLM 队列、prefix cache、continuous batching、性能结论或 CANN device timeline pairing。

## 本轮 case 策略

P1.15 不再只跑 `max_new_tokens=4`。本轮选 8 个代表 case：

| case_id | prompt_id | cap_tokens | max_new_tokens | 目的 |
| --- | --- | ---: | ---: | --- |
| `P002_cap4096_gen32` | `P002` | 4096 | 32 | 4K 长 prompt 基线，扩大 decode 到 32 |
| `P003_cap8192_gen32` | `P003` | 8192 | 32 | 8K 长 prompt 基线，扩大 decode 到 32 |
| `P005_cap8192_gen128` | `P005` | 8192 | 128 | 8K 输入下较深 decode 样例 |
| `P006_cap12288_gen32` | `P006` | 12288 | 32 | 12K cap 输入压力样例 |
| `P007_cap4096_gen32` | `P007` | 4096 | 32 | repeated-prefix 形态的第一条普通请求 |
| `P008_cap4096_gen32` | `P008` | 4096 | 32 | repeated-prefix 形态的第二条普通请求 |
| `P010_cap16384_gen32` | `P010` | 16384 | 32 | 最大 16K cap 输入压力样例，仍不跑 full 43216 |
| `P012_cap8192_gen128` | `P012` | 8192 | 128 | multi-turn / continuous-batching 形态文本的深 decode 样例 |

注意：`P007/P008` 只作为普通顺序请求执行，记录其 repeated-prefix 形态；不能声称 prefix cache 命中。`P012` 只作为普通单请求执行，不能声称 continuous batching 行为。

## 本轮必须回答

1. 8 个 envelope case 是否能在现有模型路径和 `npu:6` 上完成？
2. 每个 case 的 `input_token_count` 是否等于 `min(full_token_count, cap_tokens)`？
3. 每个 case 是否生成非空 token/text，并达到对应 `max_new_tokens` 目标或明确记录停止原因？
4. 是否能生成 `long_prompt_envelope_decode_trace.jsonl` 并通过 P1 validator？
5. 如果失败，失败阶段是模型加载、tokenizer、NPU/OOM、特定 case 推理、输出为空还是 trace 校验？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 使用现有 `transformers + torch_npu`
- 默认使用 `npu:6`，可由 `AK_SMALL_MODEL_DEVICE` 覆盖
- 实例化 tokenizer 与模型
- 顺序执行本 handoff 中列出的 8 个单请求 envelope case
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

## 成功口径

最低完成：

- pytest 执行并回传日志。
- `long_prompt_envelope_decode_result.json` 明确给出 `matrix_status` 或失败阶段。
- `long_prompt_envelope_decode_summary.tsv` 至少记录每个已尝试 case 的状态、token 数和失败信息。

强成功：

- 8 个 case 均完成单请求 prefill/decode。
- 每个 case 有非空 generated token 或文本。
- 每个 case 的 `input_token_count == min(full_token_count, cap_tokens)`。
- `long_prompt_envelope_decode_trace.jsonl` 校验 `errors=0`。

无论成功或失败，本轮都不能声称 CANN device timeline pairing 已完成，也不能输出性能、瓶颈归因或优化建议。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```

核心运行脚本：

```text
tools/inference_contracts/run_long_prompt_envelope.py
```
