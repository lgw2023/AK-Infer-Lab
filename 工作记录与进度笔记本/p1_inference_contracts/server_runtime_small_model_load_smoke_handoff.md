# P1.9 Small Model Load Smoke Server Handoff

任务 ID：`runtime_small_model_load_smoke_2026_0706_p1_008`

目标：在独立任务中实际加载服务器候选小模型 `Qwen3.5-4B`，执行一次最短 tokenizer / prefill / decode smoke，并导出 P1 最小统一事件 trace 与 `torch_profiler_trace` 候选桥证据。本轮允许加载模型权重、实例化 tokenizer、执行极短推理；但不安装包、不修环境、不运行 vLLM 服务、不跑完整 P000-P012 workload、不输出性能或瓶颈结论。

## 背景

P1.8 `runtime_model_symlink_readiness_2026_0706_p1_007` 已完成：

- 服务器执行 commit：`b5cad00`
- 最新邮件时间：2026-07-06 09:39:20 CST
- `tests/inference_contracts`：执行通过
- `models/` 下 9 个模型入口均为 symlink，并全部解析到 `/data/node0_disk1/Public/<name>`
- 跟随 symlink 后读取到 50 个 metadata 文件
- `Qwen3.5-4B` 排名第一，真实路径为 `/data/node0_disk1/Public/Qwen3.5-4B`
- `Qwen3.5-4B` 具备 `config.json`、`tokenizer_config.json`、`model.safetensors.index.json`、tokenizer metadata 和约 9.32 GB 权重文件 stat
- 自动规则因 `architectures=Qwen3_5ForConditionalGeneration` 未命中 `ForCausalLM` 字符串，所以给出 `readiness_status=blocked_no_causal_lm_candidate`
- 人工判断该 blocker 是分类规则偏窄，不是模型路径或 metadata 缺失；`Qwen3.5-4B` 仍是下一轮最合适的小模型加载 smoke 候选

P1.6 的 profiler 结论仍然成立：`torch_profiler_trace` 可作为候选 marker/op bridge，但不是 CANN device timeline pairing 证据。

## 本轮必须回答

1. 当前服务器 conda 环境能否从本地路径加载 `Qwen3.5-4B` 的 config 与 tokenizer？
2. `AutoModelForCausalLM.from_pretrained(..., local_files_only=True, trust_remote_code=True)` 能否加载该模型权重？
3. 模型能否移动到指定 NPU 设备并完成一次极短 prefill 与 decode？
4. 最短推理能否产生非空 token / 文本输出？
5. 能否导出同一份 `torch_profiler_trace.json`，其中包含 `ak_p1_small_model_*` marker 与 NPU/op 事件候选？
6. 能否生成并通过校验 `small_model_trace.jsonl`，至少覆盖 request runtime、operator timeline、state object、transfer overlap 四类 resource scope？
7. 如果失败，失败点是 tokenizer/config、模型架构支持、权重加载、NPU 可用性、OOM、推理执行、profiler 导出，还是 trace 校验？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `Qwen3.5-4B` 本地模型路径：`/data/node0_disk1/Public/Qwen3.5-4B`
- 实例化 tokenizer
- 加载模型权重
- 将模型移动到一个 NPU 设备，默认 `npu:6`
- 对 `P000` 做截断后的极短 tokenizer / prefill / decode smoke
- 使用 `torch.profiler.record_function` 与 `torch.profiler.profile`
- 导出 `small_model_trace.jsonl`、`torch_profiler_trace.json`、结果摘要和失败日志

禁止：

- 不安装、升级、卸载或修复 `transformers`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他包
- 不创建新 conda 环境
- 不运行 vLLM engine、serve、benchmark 或完整 P000-P012 workload
- 不复制、移动、删除或改名 `models/` 或 `/data/node0_disk1/Public/` 下任何文件
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不自动修复或重装 `ascend910b-driver`
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息

## 成功口径

最低完成：

- pytest 执行并回传日志
- config/tokenizer/model load smoke 至少执行到失败点并写出 `small_model_smoke_result.json` 或 `small_model_smoke_error.txt`
- 邮件正文明确说明 `small_model_smoke_status`

强成功：

- config/tokenizer/model 均加载成功
- NPU 上完成极短 prefill 与至少 1 个 decode token
- `generated_text.txt` 非空或 `generated_token_ids` 非空
- `small_model_trace.jsonl` 通过 P1 validator
- `torch_profiler_trace.json` 存在，且 marker 与 NPU/op 候选事件可检索

无论成功或失败，本轮都不能声称 CANN device timeline pairing 已完成，也不能输出模型性能或瓶颈归因结论。
