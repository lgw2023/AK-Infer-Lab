# P1.10 Small Model Trace Matrix Server Handoff

任务 ID：`runtime_small_model_trace_matrix_2026_0706_p1_009`

目标：在 P1.9 已经证明 `Qwen3.5-4B` 可加载、可在 `npu:6` 完成极短 prefill/decode 的基础上，执行一个受限的小模型单请求 trace 矩阵。默认只对 `P000,P001,P002` 执行推理 trace，同时对 `P000-P012` 做真实 tokenizer token 数校准。本轮仍使用现有 `transformers + torch_npu` 手动推理路径，不启动 vLLM，不安装包，不修环境，不输出性能 benchmark、瓶颈归因或 CANN device timeline pairing 结论。

## 背景

P1.9 `runtime_small_model_load_smoke_2026_0706_p1_008` 已完成：

- 服务器执行 commit：`09a6118`
- 最新邮件时间：2026-07-06 10:23:55 CST
- `tests/inference_contracts`：执行通过
- `Qwen3.5-4B` 路径：`/data/node0_disk1/Public/Qwen3.5-4B`
- `config_class=Qwen3_5Config`
- `tokenizer_class=Qwen2Tokenizer`
- `model_class=Qwen3_5ForCausalLM`
- `device=npu:6`
- `input_token_count=51`
- `generated_token_count=4`
- `generated_text_nonempty=1`
- `small_model_trace_validation_errors=0`
- `torch_profiler_trace_exists=1`
- `torch_profiler_marker_event_count=4`
- `torch_profiler_npu_event_candidate_count=89871`

P1.9 只证明单个短 prompt 的最小链路成立。P1.10 的目标是确认该链路在少量代表 prompt 上是否稳定，并补齐 workload manifest 的真实 tokenizer token 计数，为后续 P4 小模型 trace smoke 做准备。

## 本轮必须回答

1. `Qwen3.5-4B` 的 tokenizer 对 `P000-P012` 的真实 token 数是多少？
2. 默认 `P000,P001,P002` 三个 prompt 在同一模型加载会话中是否都能完成单请求 prefill/decode？
3. 每个请求是否都能生成非空 token 或文本输出？
4. 是否能生成一份合并的 `small_model_trace_matrix.jsonl` 并通过 P1 validator？
5. 是否能导出一份合并的 `torch_profiler_trace.json`，其中包含 `ak_p1_trace_matrix_*` marker 和 NPU/op 候选事件？
6. 如果失败，失败点是 prompt/tokenizer、模型推理、NPU/OOM、profiler 导出，还是 trace 校验？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `/data/node0_disk1/Public/Qwen3.5-4B`
- 实例化 tokenizer 与模型
- 在默认 `npu:6` 上顺序执行 `P000,P001,P002` 单请求 trace
- 对 `P000-P012` 做 tokenizer token 计数
- 使用 `torch.profiler.record_function` 与 `torch.profiler.profile`
- 导出 trace、profiler、token calibration、matrix summary、失败日志和邮件摘要

禁止：

- 不安装、升级、卸载或修复任何包
- 不创建新 conda 环境
- 不运行 vLLM engine、serve、benchmark 或完整 P000-P012 推理 workload
- 不运行并发、burst、continuous batching 或 prefix cache 结论型测试
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

- `P000,P001,P002` 均完成单请求 prefill/decode
- 每个请求有非空 generated token 或文本
- `small_model_trace_matrix.jsonl` 校验 `errors=0`
- `torch_profiler_trace.json` 存在，且 marker 与 NPU/op 候选事件可检索

无论成功或失败，本轮都不能声称 CANN device timeline pairing 已完成，也不能输出性能、瓶颈归因或优化建议。
