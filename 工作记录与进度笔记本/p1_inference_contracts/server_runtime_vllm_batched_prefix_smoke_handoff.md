# P1.17 vLLM Batched Prefix Smoke Server Handoff

任务 ID：`runtime_vllm_batched_prefix_smoke_2026_0706_p1_017`

目标：在 P1.16 已证明当前服务器环境中的 vLLM/vLLM-Ascend engine 可加载 `Qwen3.5-4B` 并完成 4K/8K 顺序单请求后，进入最小 batched repeated-prefix smoke。本轮只验证 vLLM public `LLM.generate()` 一次提交两条 4K repeated-prefix prompt 时能否完成生成，并输出合法 P1 JSONL trace。它不是压测、不是吞吐 benchmark、不是真实 continuous batching 验收，也不声称 prefix cache 命中率或瓶颈归因。

## 背景

P1.16 `runtime_vllm_engine_single_request_smoke_2026_0706_p1_016` 有两次服务器回传：

- 17:35 失败回传：`VLLM_PLUGINS=vllm_ascend` 时 import 均成功，但 vLLM engine 初始化失败，错误为 `RuntimeError: Device string must not be empty`，未进入任何 case。
- 17:56 重跑成功：改为 `VLLM_PLUGINS=ascend`，并 source `/usr/local/Ascend/cann-9.0.0/set_env.sh` 与 `/usr/local/Ascend/nnal/atb/set_env.sh` 后，vLLM engine 初始化成功。

P1.16 最终成功结果：

- 服务器执行 commit：`85e8783c230b0ea0980b40a68ca14b449a66db80`
- `pytest_exit_code=0`
- `vllm_engine_single_request_exit_code=0`
- `status=success`
- `attempted_case_count=2`
- `success_case_count=2`
- `input_count_mismatch_count=0`
- `submitted_count_mismatch_count=0`
- `trace_event_count=14`
- `trace_validation_errors=0`
- 成功 case：`P002_cap4096_gen32`、`P003_cap8192_gen32`

P1.16 结论：vLLM engine 单请求路径已打通；下一步可以启动最小 batched repeated-prefix smoke，但必须保持小规模、可回退、无性能结论。

## 本轮 case 策略

本轮只跑一个 batch，batch 内包含两条 repeated-prefix 4K prompt：

| case_id | prompt_id | cap_tokens | max_new_tokens | prefix_reuse_group | 目的 |
| --- | --- | ---: | ---: | --- | --- |
| `P007_prefix_a_first_cap4096_gen32` | `P007` | 4096 | 32 | `prefix_group_a` | repeated-prefix pair 第一条 |
| `P008_prefix_a_second_cap4096_gen32` | `P008` | 4096 | 32 | `prefix_group_a` | repeated-prefix pair 第二条 |

脚本会先用同一 tokenizer 把每条 prompt 截断到 4096 tokens，再 decode 成文本，一次性调用：

```python
llm.generate([text_for_P007, text_for_P008], SamplingParams(max_tokens=32, temperature=0.0))
```

本轮设置 `enable_prefix_caching=True` 作为候选路径请求；但 vLLM public API 不一定回传命中明细，所以本轮只记录 `kv_prefix_profile` 的 `candidate_only_no_runtime_hit_signal` 事件，不声称 prefix cache hit/miss 或命中率。

## 本轮必须回答

1. 当前环境中 `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 是否可 import？
2. 使用 `VLLM_PLUGINS=ascend` 和 CANN/ATB 环境后，vLLM engine 是否能初始化？
3. `enable_prefix_caching=True` 是否被当前 vLLM engine 接受？
4. batch size 为 2 的 `LLM.generate()` 是否能完成？
5. `P007` / `P008` 两个输出是否非空？
6. 每个 case 的 `submitted_input_token_count` 是否等于 `input_token_count`？
7. 是否能生成合法的 `vllm_batched_prefix_trace.jsonl` 并通过 P1 validator？
8. 如果失败，失败点是 import、engine_init、prefix_cache_arg、tokenizer、input_count_mismatch、NPU/OOM、batched generate、输出为空，还是 trace 校验？

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
- 使用 vLLM public `LLM` / `SamplingParams` API
- 一次提交本 handoff 中列出的 2 个 prompt
- 导出 trace、summary、generated texts、失败日志和邮件附件

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 `vllm serve`、OpenAI API server、benchmark、压测或吞吐测试
- 不运行多 worker 并发客户端、burst 压测或连续到达流量
- 不运行 full 16K/32K 或 full `P010=43216` tokens
- 不切换到 Docker 推理栈；Docker 内 vLLM/torch_npu 另起任务
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不启用 profiler 导出；profiler/CANN pairing 另起任务处理
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息
- 不输出性能 benchmark、吞吐结论、瓶颈归因、优化建议、prefix cache 命中结论或 CANN device timeline pairing 结论

## 成功口径

最低完成：

- pytest 执行并回传日志。
- `vllm_import_probe.tsv` 明确记录 import 成败。
- `vllm_batched_prefix_result.json` 明确给出 `status`、失败阶段和错误堆栈。

强成功：

- `pytest_exit_code=0`
- `vllm_batched_prefix_exit_code=0`
- `torch`、`torch_npu`、`transformers`、`vllm`、`vllm_ascend` 均 import 成功
- vLLM engine 初始化成功
- `batch_count=1`
- `batch_size=2`
- `prefix_cache_requested=1`
- 2 个 case 均完成生成
- 每个 case 有非空 generated token 或文本
- 每个 case 的 `submitted_input_token_count == input_token_count`
- `vllm_batched_prefix_trace.jsonl` 校验 `errors=0`

无论成功或失败，本轮都不能声称 vLLM continuous batching、prefix cache hit rate、性能瓶颈或 CANN device timeline pairing 已经验证。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```

核心运行脚本：

```text
tools/inference_contracts/run_vllm_batched_prefix_smoke.py
```
