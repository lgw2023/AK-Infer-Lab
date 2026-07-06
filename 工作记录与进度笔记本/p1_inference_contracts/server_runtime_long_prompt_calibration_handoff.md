# P1.12 Long Prompt Token Calibration Server Handoff

任务 ID：`runtime_long_prompt_calibration_2026_0706_p1_012`

目标：在 P1.10 + P1.11 已完成短形态 `P000-P012` 小模型 trace 后，对新物化的 `prompts_long/P000-P012.md` 做服务器侧 tokenizer 校准，确认真实 `Qwen3.5-4B` / `Qwen2Tokenizer` 下的 token 档位。该任务只校准长 prompt 文本，不加载模型权重、不运行 NPU 推理、不运行 vLLM。

## 输入

- 短形态 smoke manifest：`工作记录与进度笔记本/p1_inference_contracts/workload_manifest.yaml`
- 长形态 manifest：`工作记录与进度笔记本/p1_inference_contracts/workload_long_manifest.yaml`
- 长形态 prompt：`工作记录与进度笔记本/p1_inference_contracts/prompts_long/P000.md` 到 `P012.md`
- 默认 tokenizer/model 目录：`/data/node0_disk1/Public/Qwen3.5-4B`

## 必须回答

1. `prompts_long/P000-P012.md` 是否都能被服务器现有 tokenizer 成功编码？
2. 每条 prompt 的真实 `Qwen3.5-4B` token 数是多少？
3. 真实 token 数是否落在目标 bucket 附近；如果偏离，只记录偏离，不做自动修复。
4. 哪些 prompt 超过 4096 / 8192 / 16384 / 32768 token 截断阈值？
5. 校准是否暴露 tokenizer 文件、路径、依赖或 manifest 读取问题？

## 执行边界

允许：

- `git pull --ff-only`
- `python -m pytest tests/inference_contracts -q`
- 使用服务器当前 conda 环境
- 从 `/data/node0_disk1/Public/Qwen3.5-4B` 只加载 tokenizer
- 读取 `workload_long_manifest.yaml` 和 `prompts_long/`
- 生成 token calibration TSV、JSON、conclusion 和邮件摘要

禁止：

- 不加载 `AutoModelForCausalLM` 或任何模型权重
- 不使用 NPU，不设置或占用 `npu:6`
- 不运行 prefill/decode/generate
- 不运行 vLLM engine、serve、benchmark、burst、continuous batching 或 prefix cache 测试
- 不安装、升级、卸载或修复任何包
- 不修改服务器 `models/`、`Public/`、CANN、driver、runtime、vLLM 或 vLLM-Ascend 源码
- 不在服务器上修改、提交或 push 项目代码
- 不发送 `.env`、SMTP 授权码、代理凭据、服务器账号、私钥、Cookie 或任何敏感信息

## 成功口径

最低完成：

- pytest 执行并回传日志。
- 13 个长 prompt 均写入 `long_prompt_token_calibration.tsv`，或明确失败阶段。
- `long_prompt_calibration_conclusion.txt` 明确给出 `calibration_status`。

强成功：

- 13 个长 prompt 均 `status=success`。
- 回传每条 prompt 的 char/byte/token 数、bucket status 和各截断阈值计数。
- 邮件正文明确说明本轮未加载模型权重、未使用 NPU、未安装包、未运行 vLLM。

## 执行入口

当前服务器执行命令写在：

```text
通信模块/docs/developer-to-server.md
```
