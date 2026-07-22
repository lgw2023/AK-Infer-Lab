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
- 当前 P1.15 `runtime_long_prompt_envelope_decode_2026_0706_p1_015` 仍按已下发任务使用服务器现有 `Qwen3.5-4B + transformers + torch_npu` 路径，不切换到 Docker 容器。

## 2026-07-22 节点 0 本地镜像库快照

以下条目来自节点 0（`7.150.8.22`）的 `docker images` 输出。除上一节两套 CANN 基础镜像已有单卡冒烟证据外，其余镜像只确认存在，不代表已通过当前服务器、模型或多卡/多节点验收。

| Repository | Tag | Image ID | Created | Size | 状态 |
| --- | --- | --- | --- | ---: | --- |
| `quay.io/ascend/cann` | `9.0.0-910b-ubuntu22.04-py3.12` | `d8b5c3dbfbf4` | 2 months ago | 11.3GB | 单卡基础容器冒烟通过 |
| `quay.io/ascend/cann` | `9.0.0-910b-ubuntu22.04-py3.11` | `d24afa915a3e` | 2 months ago | 11.3GB | 单卡基础容器冒烟通过 |
| `swr.cn-southwest-2.myhuaweicloud.com/mep-dev-ga/vllm_ascend` | `910B_0.13.0rc0.20260417141425` | `5b4c8865b5f9` | 3 months ago | 30.8GB | 只确认存在 |
| `swr.cn-southwest-2.myhuaweicloud.com/huaweiccs-hivoice-product-ga/mep-vllm-ascend` | `1.0.0.20260320165527` | `98824e745c5c` | 4 months ago | 13.1GB | 只确认存在 |
| `quay.io/ascend/vllm-ascend` | `v0.11.0` | `bd312fe62114` | 7 months ago | 17.7GB | 只确认存在 |
| `swr.cn-southwest-2.myhuaweicloud.com/mep-dev-ga/mep-vllm-ascend` | `11.3.10.300.2` | `1a8dd22f222b` | 8 months ago | 9.92GB | 只确认存在 |
| `swr.cn-southwest-2.myhuaweicloud.com/huaweiccs-hivoice-product-ga/vllm-ascend-0.10.2-910b-cann8.2.rc1-torch2.7.1rc1` | `1.2.9.300` | `dd2d5c1b80c8` | 9 months ago | 20.7GB | 只确认存在 |
| `quay.io/ascend/vllm-ascend` | `v0.10.0rc1` | `ed946500e4cd` | 11 months ago | 15.6GB | 只确认存在 |
| `quay.io/ascend/vllm-ascend` | `v0.9.2rc1` | `e0eb8dc337c1` | 12 months ago | 14.4GB | 只确认存在 |

节点 0 根分区与 Docker overlay 在同日磁盘快照中均为 90% 使用率。拉取、加载或构建大镜像前必须先确认 Docker 数据目录、回收边界和磁盘余量。双节点与完整磁盘/模型清单见 [`internal-ascend-cluster-inventory.md`](internal-ascend-cluster-inventory.md)。
