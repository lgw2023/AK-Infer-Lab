# P1.6 Runtime Profiler Bridge Server Handoff

任务 ID：`runtime_profiler_bridge_2026_0706_p1_005`

目标：在不加载模型、不访问服务器 `models/`、不安装或修复推理框架的前提下，验证服务器现有 `torch` / `torch_npu` / PyTorch profiler 是否能导出同一份 trace，其中同时包含自定义 `record_function` marker 和 NPU/device 事件。它是 P1.5 `msprof` marker 不可见后的替代 pairing 路径诊断。

## 背景

P1.5 `runtime_marker_pairing_2026_0705_p1_004` 已完成：

- `tests/inference_contracts`：`11 passed in 0.19s`
- `msprof --msproftx=on` 使用 ASCII `/tmp` 输出目录稳定退出 `0`
- 无模型 NPU tensor 运算正常，生成 78 个 profiler 文件
- `marker_pairing_trace.jsonl`：`errors=0`，`events=4`
- `grep -aR` 全树搜索未命中 `ak_p1_msprof_marker_prefill` / `matmul` / `decode`
- sqlite 全列 `LIKE` 搜索未命中 marker 名称
- 存在 `CANN_API.startNs/endNs`、`TASK.startNs/endNs`、`SESSION_TIME_INFO.startTimeNs`、`host/sqlite/time.db` 等时间字段候选
- 但没有可验证的 host marker 名称到 CANN device timeline 的 pairing 证据

因此后续不能声称 `msprof` 路径已经完成 CANN timeline pairing。下一步先尝试 `torch.profiler` / `torch_npu` trace 作为替代桥；仍然不进入小模型、不碰服务器模型目录、不安装包。

## 本轮必须回答

1. 当前服务器环境中 `torch.profiler.ProfilerActivity` 是否包含 `NPU` 或等价 device activity？
2. 极小 NPU tensor smoke 能否在 `torch.profiler.profile(...)` 下完成并导出 Chrome trace？
3. 导出的 trace 中能否检索到自定义 marker 名称？
4. 同一 trace 中能否检索到 NPU/device/op/copy 事件候选？
5. marker 和 device event 是否共享同一种 trace 时间字段，例如 Chrome trace 的 `ts` / `dur`？
6. 如果能共享同一 trace 时间字段，后续小模型阶段能否把它作为候选 pairing 路径？
7. 如果仍不能，明确后续小模型只能做 host-side runtime trace，不能声称 device timeline 已对齐。

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `torch` / `torch_npu` 执行极小 NPU tensor smoke
- 使用 `torch.profiler.profile`、`torch.profiler.record_function`、`prof.export_chrome_trace`
- 只读分析 profiler JSON 产物

禁止：

- 不运行真实模型推理、小模型 smoke、vLLM engine serve/generate 或 P000-P012 workload
- 不访问、加载、复制或枚举服务器 `models/` 目录下的模型
- 不安装、升级、卸载或修复 `vllm`、`vllm_ascend`、`mindie`、`mindspore` 或其他推理框架包
- 不修改 driver、CANN、apt、dpkg、NPU runtime 或 vLLM/vLLM-Ascend 源码
- 不自动修复或重装 `ascend910b-driver`
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息

## 成功口径

最低成功：

- pytest 通过
- profiler API 盘点完成
- 无模型 NPU tensor smoke 完成或给出明确失败码和 traceback
- 输出 trace 文件是否存在、marker 搜索、device event 搜索和结论文件

强成功：

- Chrome trace 中同时出现自定义 marker 和 NPU/device event 候选
- 两类事件都有 `ts` / `dur` 等同一 trace 时间字段
- 结论明确后续小模型阶段可以尝试 `torch_profiler_trace` 作为候选 pairing 证据，但仍不能提前声称真实模型已完成归因

如果 marker 或 device event 任一侧缺失，本轮仍算完成诊断，但结论必须写明：后续小模型阶段只能按 host-side runtime trace 验收，device timeline pairing 仍未确认。
