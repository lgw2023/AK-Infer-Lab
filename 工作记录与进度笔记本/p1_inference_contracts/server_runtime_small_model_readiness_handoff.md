# P1.7 Small Model Readiness Server Handoff

任务 ID：`runtime_small_model_readiness_2026_0706_p1_006`

目标：在不加载模型、不运行推理、不安装或修复任何推理框架包的前提下，只读盘点服务器项目 `models/` 目录和当前 conda 环境，判断是否具备另起独立 P4 小模型加载 smoke 的候选模型与现成框架入口。

## 背景

P1.6 `runtime_profiler_bridge_2026_0706_p1_005` 已完成：

- `tests/inference_contracts`：`11 passed in 0.19s`
- `runtime_profiler_bridge_trace.jsonl`：`errors=0`，`events=4`
- `torch.profiler.ProfilerActivity` 不包含 `NPU`，本轮实际启用 `activities=CPU`
- `torch_npu.profiler.ProfilerActivity` 中存在 `CPU` / `NPU`
- `torch_profiler_trace.json` 已生成，`trace_event_count=71`
- 同一 Chrome trace 中 3 个自定义 `record_function` marker 与 7 个 NPU 相关 op 候选均可见，且均带 `ts` / `dur`

P1.6 的结论是：`torch_profiler_trace` 可作为后续小模型阶段的候选 marker/op bridge，但仍不是 CANN device timeline pairing 证据。进入小模型 trace smoke 之前，需要先确认服务器上是否已有可用小模型、metadata 是否完整、当前环境是否已有可用加载入口。

## 本轮必须回答

1. 服务器项目根目录下 `models/` 是否存在，是否有可读的模型候选目录？
2. 候选模型是否包含 `config.json`、`tokenizer_config.json`、`generation_config.json`、`*.safetensors.index.json` 等可解析 metadata？
3. 根据 metadata 和目录名，是否存在适合 P4 小模型 smoke 的小尺寸候选？
4. 当前 conda 环境中 `torch`、`torch_npu`、`transformers`、`tokenizers`、`sentencepiece`、`accelerate`、`safetensors`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 是否可见？
5. 是否可以不修环境、不装包、不搬模型，另起独立小模型加载 smoke？
6. 如果不能，阻塞原因是缺模型、缺 tokenizer、缺框架、环境需修复，还是需要人工选择模型？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 对 `models/` 做只读目录和小型 metadata 文件扫描
- 使用 `importlib.util.find_spec` 和 `importlib.metadata.version` 探测包是否可见
- 生成候选模型清单、包清单和 readiness 结论

禁止：

- 不加载模型权重，不实例化模型，不实例化 tokenizer
- 不运行 `generate`、`serve`、benchmark、小模型 smoke 或 P000-P012 workload
- 不读取权重文件内容，不复制、移动、删除或改名 `models/` 里的任何文件
- 不安装、升级、卸载或修复 `transformers`、`vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他推理框架包
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息

## 成功口径

最低成功：

- pytest 通过或给出明确失败日志
- `models/` 存在性、候选数量、metadata 数量和包可见性均有结构化输出
- 输出 `readiness_conclusion.txt`，明确是否建议进入独立小模型加载 smoke

强成功：

- 找到至少一个小模型候选目录，且包含 `config.json` 与 tokenizer 相关 metadata
- 当前环境已有至少一种合理加载入口候选，例如 `transformers` 或 `vllm` / `vllm_ascend`
- 结论明确下一轮小模型 smoke 应使用的候选模型路径和加载方式，但本轮不实际加载

如果缺模型、metadata 不完整或框架入口不可用，本轮仍算完成 readiness 诊断；后续应单独讨论模型选择、模型同步或环境/装包任务。
