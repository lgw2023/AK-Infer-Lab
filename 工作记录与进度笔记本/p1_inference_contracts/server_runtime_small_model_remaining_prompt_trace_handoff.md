# P1.11 Small Model Remaining Prompt Trace Server Handoff

任务 ID：`runtime_small_model_remaining_prompt_trace_2026_0706_p1_010`

目标：在 P1.10 已完成 `P000,P001,P002` 顺序单请求 trace 和 `P000-P012` tokenizer 校准的基础上，补齐当前短形态样例中的 `P003-P012` 顺序单请求 trace。P1.10 + P1.11 合并后，形成当前 `P000-P012` shape fixture 的完整小模型 trace 覆盖。

## 背景

P1.10 `runtime_small_model_trace_matrix_2026_0706_p1_009` 已完成：

- 服务器执行 commit：`42fa210`
- 最新邮件时间：2026-07-06 10:50:21 CST
- `pytest_exit_code=0`
- `small_model_trace_matrix_exit_code=0`
- `matrix_status=success`
- `token_calibration_prompt_count=13`
- `matrix_prompt_ids=P000,P001,P002`
- `matrix_success_prompt_count=3`
- `trace_event_count=18`
- `trace_validation_errors=0`
- `torch_profiler_marker_event_count=24`
- `torch_profiler_npu_event_candidate_count=407700`

P1.10 同时暴露一个 workload 设计缺口：当前 `P000-P012` prompt 文件在 `Qwen3.5-4B` tokenizer 下只有 51-185 tokens。它们可以继续作为 shape fixture 和链路 smoke 输入，但不能代表 manifest 中 4K/8K/16K/32K 的真实长上下文压力。

## 本轮必须回答

1. `P003-P012` 十个当前短形态 prompt 是否都能在同一模型加载会话中完成顺序单请求 prefill/decode？
2. 每个 `P003-P012` 请求是否都能生成非空 token 或文本？
3. 是否能生成合并的 `small_model_trace_matrix.jsonl` 并通过 P1 validator？
4. 是否能导出 `torch_profiler_trace.json`，其中包含 `ak_p1_trace_matrix_P003` 到 `P012` 的 marker 与 NPU/op 候选事件？
5. 复核 `P000-P012` token 校准是否仍与 P1.10 一致。
6. 如果失败，失败点是 prompt/tokenizer、模型推理、NPU/OOM、profiler 导出，还是 trace 校验？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 实例化 tokenizer 与模型
- 在默认 `npu:6` 上顺序执行 `P003-P012` 单请求 trace
- 对 `P000-P012` 复核 tokenizer token 数
- 使用 `torch.profiler.record_function` 与 `torch.profiler.profile`
- 导出 trace、profiler、token calibration、matrix summary、失败日志和邮件摘要

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 vLLM engine、serve 或 benchmark
- 不运行真实长上下文、并发、burst、continuous batching 或 prefix cache 结论型 workload
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息

## 成功口径

最低完成：

- pytest 执行并回传日志
- `token_calibration.tsv` 写出 `P000-P012` 的真实 token 数或明确失败阶段
- `small_model_trace_matrix_conclusion.txt` 明确给出 `matrix_status`

强成功：

- `P003-P012` 均完成单请求 prefill/decode
- 每个请求有非空 generated token 或文本
- `small_model_trace_matrix.jsonl` 校验 `errors=0`
- `torch_profiler_trace.json` 存在，且 marker 与 NPU/op 候选事件可检索

无论成功或失败，本轮都不能声称 CANN device timeline pairing 已完成，也不能输出性能、瓶颈归因或优化建议。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```
