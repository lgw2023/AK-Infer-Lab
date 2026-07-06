# P1.14 Long Prompt Trace Matrix Server Handoff

任务 ID：`runtime_long_prompt_trace_matrix_2026_0706_p1_014`

目标：在 P1.13 已证明 `Qwen3.5-4B + transformers + torch_npu` 能完成少量 4K/8K 截断长 prompt 单请求 trace 后，扩大到 `prompts_long/P000-P012.md` 的完整 13 条清单覆盖。本轮仍只做顺序单请求 trace matrix，最大输入 cap 为 8192 tokens；不运行 vLLM、不安装包、不修环境、不做并发、性能 benchmark、瓶颈归因或 CANN device timeline pairing 结论。

## 背景

P1.13 `runtime_long_prompt_trace_smoke_2026_0706_p1_013` 已完成：

- 服务器执行 commit：`77ddb78291e5e8c1dab8c064d7e6dcd3ded1200c`
- 服务器时间：2026-07-06 15:40:04 +08:00
- `pytest_exit_code=0`
- `matrix_status=success`
- `attempted_case_count=4`
- `success_case_count=4`
- `failed_case_count=0`
- `trace_event_count=28`
- `trace_validation_errors=0`
- 成功 case：`P002@4096`、`P003@8192`、`P007@4096`、`P008@4096`
- `torch_profiler_trace_exists=0`
- profiler 导出错误：`AttributeError: 'NoneType' object has no attribute 'save'`

P1.13 的结论是：长 prompt 的 4K/8K 截断模型推理主路径可跑通，P1 JSONL trace 可自校验；但 `torch_profiler_trace` 不可作为本轮成功证据。P1.14 因此默认不要求 profiler 导出成功，仍把 profiler 标为 `candidate_only_optional`。

## 本轮 case 策略

P1.14 覆盖全部 `P000-P012`，但只使用 4K/8K cap：

| case_id | prompt_id | cap_tokens | 预期 input token 口径 |
| --- | --- | ---: | --- |
| `P000_cap4096` | `P000` | 4096 | full 1184，不截断 |
| `P001_cap4096` | `P001` | 4096 | full 1764，不截断 |
| `P002_cap4096` | `P002` | 4096 | 截断到 4096 |
| `P003_cap8192` | `P003` | 8192 | 截断到 8192 |
| `P004_cap8192` | `P004` | 8192 | 截断到 8192 |
| `P005_cap8192` | `P005` | 8192 | 截断到 8192 |
| `P006_cap8192` | `P006` | 8192 | 截断到 8192 |
| `P007_cap4096` | `P007` | 4096 | 截断到 4096 |
| `P008_cap4096` | `P008` | 4096 | 截断到 4096 |
| `P009_cap8192` | `P009` | 8192 | 截断到 8192 |
| `P010_cap8192` | `P010` | 8192 | 截断到 8192 |
| `P011_cap4096` | `P011` | 4096 | 截断到 4096 |
| `P012_cap8192` | `P012` | 8192 | 截断到 8192 |

## 本轮必须回答

1. 13 条长 prompt 在上述 cap 策略下是否均能完成顺序单请求 prefill/decode？
2. 每个 case 是否有非空 generated token 或文本？
3. 每个 case 的 `input_token_count` 是否等于 `min(full_token_count, cap_tokens)`？
4. 是否能生成合并的 `long_prompt_trace_matrix_full.jsonl` 并通过 P1 validator？
5. 如果失败，失败阶段是模型加载、tokenizer、NPU/OOM、某个长 prompt 推理、trace 校验，还是可选 profiler 导出？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 使用现有 `transformers + torch_npu`
- 默认使用 `npu:6`，可由 `AK_SMALL_MODEL_DEVICE` 覆盖
- 实例化 tokenizer 与模型
- 顺序执行 `P000-P012` 的 13 个单请求 trace
- 默认跳过 profiler 导出；如显式设置 `AK_LONG_PROMPT_MATRIX_ENABLE_PROFILER=1`，可尝试导出并记录成功或失败
- 导出 trace、summary、generated texts、失败日志和邮件附件

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 vLLM engine、serve、benchmark 或 vLLM-Ascend 任务
- 不运行 16K/32K full prompt，不运行 full P010 43216 tokens
- 不运行并发、burst、continuous batching 或 prefix cache 结论型测试
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、瓶颈归因、优化建议或 CANN device timeline pairing 结论

## 成功口径

最低完成：

- pytest 执行并回传日志。
- `long_prompt_trace_matrix_full_result.json` 明确给出 `matrix_status` 或失败阶段。
- `long_prompt_trace_matrix_full_summary.tsv` 至少记录每个已尝试 case 的状态、token 数和失败信息。

强成功：

- 13 个 case 均完成单请求 prefill/decode。
- 每个 case 有非空 generated token 或文本。
- `long_prompt_trace_matrix_full.jsonl` 校验 `errors=0`。
- profiler 未启用或导出失败时，必须在 result/summary 中明确记录；该项不影响 P1.14 主成功口径。

无论成功或失败，本轮都不能声称 CANN device timeline pairing 已完成，也不能输出性能、瓶颈归因或优化建议。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```
