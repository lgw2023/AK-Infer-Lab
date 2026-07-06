# 服务器 Docker 镜像登记

本页记录昇腾服务器侧已经加载并完成最小冒烟的 Docker 镜像。信息来源为服务器邮件回传，不记录密钥、账号、代理凭据或服务器登录信息。

## 2026-07-06 CANN 9.0.0 基础镜像

邮件信息：
- 主题：`[AK服务器] 任务完成：CANN 9.0.0 Docker 镜像加载与冒烟测试`
- 邮件时间：2026-07-06 15:41:19 CST
- 发件人：`17621223203@163.com`
- 收件人：`gwlee1995@gmail.com,yilili1023@gmail.com`
- 主机：`DevServer-BMS-3d97cc99-0（7.150.8.22）`

服务器结果：
- 已从 `/data/node0_disk1/Public/` 成功 `docker load` 两个 arm64 CANN 镜像 tar 包，邮件报告每个 tar 包约 4.2 GB。
- 单卡容器冒烟测试通过，测试卡为 `/dev/davinci4`，容器内设置 `ASCEND_RT_VISIBLE_DEVICES=0`。
- 冒烟检查覆盖 `set_env.sh`、`npu-smi info` 和 Python 版本。

已加载镜像：

| 镜像 | 镜像 ID | 镜像大小 | Python | 状态 |
| --- | --- | --- | --- | --- |
| `quay.io/ascend/cann:9.0.0-910b-ubuntu22.04-py3.11` | `d24afa915a3e` | 11.3 GB | 3.11.15 | 单卡容器冒烟通过 |
| `quay.io/ascend/cann:9.0.0-910b-ubuntu22.04-py3.12` | `d8b5c3dbfbf4` | 11.3 GB | 3.12.13 | 单卡容器冒烟通过 |

边界与后续使用：
- 这两个镜像是 CANN 9.0.0 基础镜像，邮件确认基础镜像不含 `torch` / `torch_npu`，这属于预期。
- 后续如需在 Docker 内跑推理栈，应另行叠加 `torch_npu` / `vLLM-Ascend`，或直接使用合适的 vLLM-Ascend 镜像。
- 后续单卡 Docker 基线默认优先使用 `py3.12` 镜像，因为它与 `工作记录与进度笔记本/00_原始材料/步骤 1 内容.md` 中的 Docker 单卡环境建议一致。
- 当前 P1.14 `runtime_long_prompt_trace_matrix_2026_0706_p1_014` 仍按已下发任务使用服务器现有 `Qwen3.5-4B + transformers + torch_npu` 路径，不切换到 Docker 容器。
