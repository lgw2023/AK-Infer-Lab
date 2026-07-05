# P1.5 Runtime Marker Pairing Server Handoff

任务 ID：`runtime_marker_pairing_2026_0705_p1_004`

目标：在不加载模型、不访问服务器 `models/`、不安装或修复推理框架的前提下，确认 `msprof --msproftx=on` 产物中是否能找到 host marker 名称，以及是否存在可用于后续 host/runtime trace 与 CANN device timeline 对齐的时间字段候选。

## 背景

P1.4 `runtime_hook_proto_2026_0705_p1_003` 已完成：

- `tests/inference_contracts`：`11 passed in 0.19s`
- `runtime_hook_proto_trace.jsonl`：`errors=0`，`events=4`
- P1.3 候选 hook 可 import、可 inspect、可临时 wrapper patch 并恢复
- 未访问 `models/`，未加载模型，未安装或修复推理框架

P1.4 的剩余缺口：

- `msprof --output` 指向含中文路径的项目 artifact 目录时退出 `255`
- 使用 `/tmp/msprof_marker_p1_003` 后 `msprof --msproftx=on` 退出 `0`，并生成 host/device/sqlite/sample.json 等产物
- `ak_p1_msprof_marker_prefill` / `ak_p1_msprof_marker_matmul` 未在可检索产物中命中
- CANN timeline pairing 仍未确认

## 本轮必须回答

1. 使用 ASCII `/tmp` 目录作为 `msprof --output` 后，marker smoke 是否稳定退出 `0`？
2. profiler 目录下实际生成了哪些 host/device/sqlite/json/raw 文件？
3. 二进制 grep 是否能在任何产物中命中 marker 名称？
4. sqlite 表结构中是否存在 marker、range、event、api、op、time、timestamp、start、end、duration 等字段？
5. sqlite 文本列搜索是否能命中 marker 名称？
6. json 产物中是否存在可解释的 marker 或时间字段？
7. 是否能给出 host marker 与 device timeline 的可验证 pairing 证据？如果不能，明确 blocker 和证据文件。

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 使用 `torch` / `torch_npu` 执行极小 NPU tensor smoke
- 使用 `msprof --msproftx=on`
- 在 Python 脚本中用 `sqlite3`、`json`、`grep` 等只读分析 profiler 产物

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
- `msprof --msproftx=on` 使用 `/tmp` 输出目录稳定完成
- 产出完整文件枚举、grep 搜索结果、sqlite schema、sqlite marker 搜索、json key 盘点和 pairing 结论

强成功：

- marker 名称在 msprof 可检索产物中命中
- 同时找到可解释的 host/device 时间字段候选
- 能给出后续小模型 trace smoke 的 pairing 证据路径

如果 marker 仍不可见，本轮仍算完成诊断，但结论必须写明：小模型阶段不能声称 CANN device timeline 已对齐。
