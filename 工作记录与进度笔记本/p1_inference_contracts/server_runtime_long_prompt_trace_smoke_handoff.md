# P1.13 Long Prompt Trace Smoke Server Handoff

任务 ID：`runtime_long_prompt_trace_smoke_2026_0706_p1_013`

目标：在 P1.12 已确认 `prompts_long/P000-P012.md` 均可被服务器现有 `Qwen3.5-4B` tokenizer 成功编码后，使用已验证过的 `Qwen3.5-4B + transformers + torch_npu` 路径，执行少量受限长 prompt 单请求 trace smoke。本轮只验证 4K/8K 截断输入能否完成 prefill/decode 和 P1 trace 校验，不做性能 benchmark、瓶颈归因、并发、prefix cache 结论或 vLLM engine 测试。

## 背景

P1.12 `runtime_long_prompt_calibration_2026_0706_p1_012` 已完成：

- 服务器执行 commit：`0074466`
- `pytest_exit_code=0`
- `long_prompt_token_calibration_exit_code=0`
- `calibration_status=success`
- `tokenizer_class=Qwen2Tokenizer`
- `prompt_count=13`
- `success_prompt_count=13`
- `failed_prompt_count=0`
- `bucket_miss_count=13`
- `max_full_token_count=43216`
- 真实 token 分布：`P000=1184`、`P001=1764`、`P002=5556`、`P003=11144`、`P004=11656`、`P005=21569`、`P006=22490`、`P007=5972`、`P008=5975`、`P009=11094`、`P010=43216`、`P011=5972`、`P012=11128`

所有 prompt 均高于原 bucket 估计，因此 P1.13 不直接跑 full 16K/32K，更不跑完整 P000-P012 workload。本轮只选 4 个受控截断 case：

| case_id | prompt_id | cap_tokens | 目的 |
| --- | --- | ---: | --- |
| `P002_4k` | `P002` | 4096 | 4K 代码分析类长 prompt smoke |
| `P003_8k` | `P003` | 8192 | 8K 长系统 prompt smoke |
| `P007_4k` | `P007` | 4096 | 重复 prefix 第一条，仍只做顺序单请求 |
| `P008_4k` | `P008` | 4096 | 重复 prefix 第二条，仍不声称 prefix cache 结论 |

## 本轮必须回答

1. 服务器现有 `Qwen3.5-4B + transformers + torch_npu` 路径是否能加载模型并在 `npu:6` 上完成上述 4 个截断长 prompt 的顺序单请求 prefill/decode？
2. 每个 case 是否有非空 generated token 或文本？
3. 每个 case 的 `input_token_count` 是否等于预期 cap 或低于 cap 的真实 token 数？
4. 是否能生成合并的 `long_prompt_trace_matrix.jsonl` 并通过 P1 validator？
5. 是否能导出 `torch_profiler_trace.json`，或在过大时回传 `.omitted.txt` 与 marker/NPU 候选事件计数？
6. 如果失败，失败点是模型加载、tokenizer、NPU/OOM、长 prompt 推理、profiler 导出，还是 trace 校验？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 使用现有 `transformers + torch_npu`
- 默认使用 `npu:6`，可由 `AK_SMALL_MODEL_DEVICE` 覆盖
- 实例化 tokenizer 与模型
- 对 `P002@4096`、`P003@8192`、`P007@4096`、`P008@4096` 顺序执行单请求 trace
- 使用 `torch.profiler.record_function` 与 `torch.profiler.profile`
- 导出 trace、profiler、summary、失败日志和邮件摘要

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 vLLM engine、serve、benchmark 或 vLLM-Ascend 任务
- 不运行 16K/32K full prompt，不运行完整 P000-P012 workload
- 不运行并发、burst、continuous batching 或 prefix cache 结论型测试
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息

## 成功口径

最低完成：

- pytest 执行并回传日志。
- `long_prompt_trace_matrix_result.json` 明确给出 `matrix_status` 或失败阶段。
- `long_prompt_trace_matrix_summary.tsv` 至少记录每个已尝试 case 的状态、token 数和失败信息。

强成功：

- 4 个 case 均完成单请求 prefill/decode。
- 每个 case 有非空 generated token 或文本。
- `long_prompt_trace_matrix.jsonl` 校验 `errors=0`。
- profiler 产物存在，且 marker 与 NPU/op 候选事件可检索。

无论成功或失败，本轮都不能声称 CANN device timeline pairing 已完成，也不能输出性能、瓶颈归因或优化建议。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```
