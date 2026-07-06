# P1.18 vLLM API Concurrency Smoke Server Handoff

任务 ID：`runtime_vllm_api_concurrency_smoke_2026_0706_p1_018`

目标：在 P1.17 已证明 vLLM public `LLM.generate()` 可一次提交两条 4K repeated-prefix prompt 后，进入最小 OpenAI API server 并发入口冒烟。本轮只启动本机回环 `vLLM OpenAI API server`，发送 3 个错开 100ms 的 `/v1/completions` 请求，验证 API server、多客户端入口和候选调度 trace 能否闭环。它不是压测，不是 throughput benchmark，不是真实 continuous batching 验收，不声称 prefix cache 命中率、调度效率、瓶颈归因或 CANN device timeline pairing。

## 背景

P1.17 `runtime_vllm_batched_prefix_smoke_2026_0706_p1_017` 已成功：

- 服务器执行 commit：`3e6d266a3b7a36f29e630cfa46e0be080e9be8f1`
- 服务器时间：2026-07-06 19:36:05 +08:00
- `pytest_exit_code=0`
- `vllm_batched_prefix_exit_code=0`
- `status=success`
- `batch_count=1`
- `batch_size=2`
- `prefix_cache_requested=1`
- `attempted_case_count=2`
- `success_case_count=2`
- `input_count_mismatch_count=0`
- `submitted_count_mismatch_count=0`
- `trace_event_count=17`
- `trace_validation_errors=0`
- 成功 case：`P007_prefix_a_first_cap4096_gen32`、`P008_prefix_a_second_cap4096_gen32`

P1.17 仍只是 public `LLM.generate()` batch，不是 OpenAI API server，不是多客户端并发，也不证明 continuous batching。P1.18 因此只推进一个最小 API server + 3 个重叠请求的入口验证。

## 本轮 case 策略

本轮启动一个 vLLM OpenAI API server，并向 `/v1/completions` 发送 3 个错开的 4K prompt 请求：

| case_id | prompt_id | cap_tokens | max_new_tokens | delay | 目的 |
| --- | --- | ---: | ---: | ---: | --- |
| `P007_api_prefix_first_cap4096_gen32` | `P007` | 4096 | 32 | 0ms | repeated-prefix pair 第一条 |
| `P008_api_prefix_second_cap4096_gen32` | `P008` | 4096 | 32 | 100ms | repeated-prefix pair 第二条 |
| `P012_api_continuous_candidate_cap4096_gen32` | `P012` | 4096 | 32 | 200ms | continuous-batching 形态候选 |

`P012` 的 manifest 形态是 `W7_continuous_batching`，但本轮只取 1 条 4K 截断请求，不按 manifest 的 16 请求规模执行。

## 本轮必须回答

1. 当前环境中 `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 是否可 import？
2. 使用 `VLLM_PLUGINS=ascend` 和 CANN/ATB 环境后，vLLM OpenAI API server 是否能启动并通过 `/health`？
3. `/v1/completions` 是否能接受 `Qwen3.5-4B` 的 3 个错开请求？
4. 3 个 case 是否都返回非空输出？
5. 每个 case 的 `submitted_input_token_count` 是否等于 `input_token_count`？
6. 客户端侧请求时间窗是否至少出现 1 个 overlap candidate？
7. 是否能生成合法的 `vllm_api_concurrency_trace.jsonl` 并通过 P1 validator？
8. 如果失败，失败点是 import、api_server_start、health_probe、CLI 参数、tokenizer、input_count_mismatch、HTTP request、输出为空、NPU/OOM，还是 trace 校验？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- source `/usr/local/Ascend/cann-9.0.0/set_env.sh`
- source `/usr/local/Ascend/nnal/atb/set_env.sh`
- 使用当前环境已有 `vllm` 和 `vllm_ascend`
- 设置本进程环境变量 `ASCEND_RT_VISIBLE_DEVICES`、`VLLM_USE_V1`、`VLLM_PLUGINS=ascend`、`VLLM_WORKER_MULTIPROC_METHOD`
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 在 `127.0.0.1` 启动一个临时 vLLM OpenAI API server
- 只向本机回环 `/v1/completions` 发送本 handoff 列出的 3 个请求
- 导出 server log、trace、summary、generated texts、失败日志和邮件附件

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 benchmark、吞吐测试、压测或长时间服务
- 不运行多 worker 压测客户端，不运行 8 请求 burst，不运行 16 请求 continuous batching workload
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不切换到 Docker 推理栈；Docker 内 vLLM/torch_npu 另起任务
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不启用 profiler 导出；profiler/CANN pairing 另起任务处理
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、吞吐结论、调度效率结论、瓶颈归因、优化建议、prefix cache 命中结论或 CANN device timeline pairing 结论

## 成功口径

最低完成：

- pytest 执行并回传日志。
- `vllm_import_probe.tsv` 明确记录 import 成败。
- `vllm_api_server.log` 明确记录 API server 启动或失败信息。
- `vllm_api_concurrency_result.json` 明确给出 `status`、失败阶段和错误堆栈。

强成功：

- `pytest_exit_code=0`
- `vllm_api_concurrency_exit_code=0`
- `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 均 import 成功
- vLLM OpenAI API server `/health` ready
- `/v1/completions` 3 个请求均返回 2xx
- 3 个 case 均有非空 generated token 或文本
- 每个 case 的 `submitted_input_token_count == input_token_count`
- `client_overlap_candidate_count > 0`
- `vllm_api_concurrency_trace.jsonl` 校验 `errors=0`

无论成功或失败，本轮都不能声称 vLLM continuous batching、prefix cache hit rate、吞吐性能、调度瓶颈或 CANN device timeline pairing 已经验证。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```

核心运行脚本：

```text
tools/inference_contracts/run_vllm_api_concurrency_smoke.py
```
