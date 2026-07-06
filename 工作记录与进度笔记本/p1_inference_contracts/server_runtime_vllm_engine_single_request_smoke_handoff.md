# P1.16 vLLM Engine Single-Request Smoke Server Handoff

任务 ID：`runtime_vllm_engine_single_request_smoke_2026_0706_p1_016`

目标：在 P1.15 已证明现有 `Qwen3.5-4B + transformers + torch_npu` 长 prompt 主路径可以覆盖 4K/8K/12K/16K 输入 cap 和 32/128 decode 后，启动独立的 vLLM/vLLM-Ascend engine smoke。本轮只验证当前服务器环境中的 vLLM engine 是否能加载 `Qwen3.5-4B` 并完成 4K/8K 两个顺序单请求生成，同时输出最小 P1 JSONL trace。它不是并发、不是 prefix cache、不是 continuous batching、不是 serve/benchmark，也不处理 profiler/CANN pairing。

## 背景

P1.15 `runtime_long_prompt_envelope_decode_2026_0706_p1_015` 已完成：

- 服务器执行 commit：`2e73e59c551190dfd2133b6385e5e09a89971088`
- 服务器时间：2026-07-06 17:01:40 +08:00
- `pytest_exit_code=0`
- `long_prompt_envelope_decode_exit_code=0`
- `matrix_status=success`
- `attempted_case_count=8`
- `success_case_count=8`
- `failed_case_count=0`
- `input_count_mismatch_count=0`
- `trace_event_count=56`
- `trace_validation_errors=0`
- 成功 case：`P002@4096+32`、`P003@8192+32`、`P005@8192+128`、`P006@12288+32`、`P007@4096+32`、`P008@4096+32`、`P010@16384+32`、`P012@8192+128`

P1.15 结论：`transformers + torch_npu` 主路径已经有足够证据，不需要继续在同一路径上保守扩大。本轮可以启动 vLLM，但必须作为新的独立风险面：engine 初始化、vLLM-Ascend backend、KV cache 管理和调度路径都可能引入新的失败点，因此不能和并发、prefix cache 或性能结论混在一起。

## 本轮 case 策略

本轮只跑两个顺序单请求，每次 `llm.generate()` 只提交一个 prompt：

| case_id | prompt_id | cap_tokens | max_new_tokens | 目的 |
| --- | --- | ---: | ---: | --- |
| `P002_cap4096_gen32` | `P002` | 4096 | 32 | vLLM engine 4K 输入单请求 smoke |
| `P003_cap8192_gen32` | `P003` | 8192 | 32 | vLLM engine 8K 输入单请求 smoke |

提示词输入由脚本先用同一模型 tokenizer 截断到 cap，再 decode 成单条文本交给 vLLM public `LLM.generate()`。脚本会记录 `input_token_count` 和 `submitted_input_token_count`；如二者不一致，本轮应视为输入构造不可靠并回传失败 artifact。

## 本轮必须回答

1. 当前服务器环境中 `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 是否可 import？
2. vLLM/vLLM-Ascend engine 是否能用 `/data/node0_disk1/Public/Qwen3.5-4B` 初始化？
3. `P002_cap4096_gen32` 是否能完成单请求生成？
4. `P003_cap8192_gen32` 是否能完成单请求生成？
5. 每个 case 的 `submitted_input_token_count` 是否等于 `input_token_count`？
6. 是否能生成 `vllm_engine_single_request_trace.jsonl` 并通过 P1 validator？
7. 如果失败，失败阶段是 import、engine_init、tokenizer、input_count_mismatch、NPU/OOM、vLLM generate、输出为空还是 trace 校验？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用当前环境里已有的 `vllm` 和 `vllm_ascend`
- 设置本进程环境变量 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS`、`VLLM_WORKER_MULTIPROC_METHOD`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 使用 vLLM public `LLM` / `SamplingParams` API
- 顺序执行本 handoff 中列出的 2 个单请求 case
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

## 成功口径

最低完成：

- pytest 执行并回传日志。
- `vllm_import_probe.tsv` 明确记录 import 成败。
- `vllm_engine_single_request_result.json` 明确给出 `status`、失败阶段和错误堆栈。

强成功：

- `pytest_exit_code=0`
- `vllm_engine_single_request_exit_code=0`
- `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 均 import 成功
- vLLM engine 初始化成功
- 2 个 case 均完成单请求生成
- 每个 case 有非空 generated token 或文本
- 每个 case 的 `submitted_input_token_count == input_token_count`
- `vllm_engine_single_request_trace.jsonl` 校验 `errors=0`

无论成功或失败，本轮都不能声称 vLLM 并发、prefix cache、continuous batching、性能瓶颈或 CANN device timeline pairing 已经验证。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```

核心运行脚本：

```text
tools/inference_contracts/run_vllm_engine_single_request_smoke.py
```
