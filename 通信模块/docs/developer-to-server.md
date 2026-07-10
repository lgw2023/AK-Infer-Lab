# Developer to Server

## 当前状态：等待八卡设备范围确认（当前无新增服务器任务）

状态 ID：

```text
no_new_server_task_waiting_8card_scope_for_p5_retry_2026_0710
```

本文件当前不授权新的服务器执行。请不要重跑旧 P5 Smoke，不要继续安装或修改运行时，也不要占用 NPU 0-5。下一轮 P5 需要同一时段完整 8 卡；只有用户明确确认可使用的 8 卡范围后，开发机才会再次清空本文件，并写入唯一可执行任务和精确命令。

拟用设备范围是：

```text
ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
```

该范围当前只是待确认计划，不是执行授权。

## 已验证的新隔离运行时

服务器已完成独立环境构建：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1
```

已回传版本：

```text
Python           3.11.15
CANN             9.0.0
vLLM             0.20.2+empty
vLLM-Ascend      0.20.2rc1
PyTorch          2.10.0+cpu
torch-npu        2.10.0
triton-ascend    3.2.1
transformers     5.5.3
```

新环境与原 `.conda/envs/ak-infer-lab` 0.18.0 环境隔离，共享 `/data/node0_disk1/vllm @ v0.18.0` 未改动；新 vLLM 源码位于 `/data/node0_disk1/vllm-0.20.2 @ v0.20.2`。

服务器已在 NPU 6 上用 `Qwen2.5-3B-Instruct` 完成 `VLLM_PLUGINS=ascend`、bf16、eager 模式端到端推理，证明新环境的 Ascend plugin、V1 engine、模型加载、生成与释放链路可用。

## 仍未验证的范围

- Qwen2.5 是纯注意力小模型；该结果不证明 DeepSeek-V4 的 DSA、MoE、TP8、EP、MTP、W8A8 或 128K 路径可用。
- Qwen3.5-4B 的 Mamba/GDN prefill 在 triton GDN 内核失败，属于另一架构代码路径；既不能否定 DeepSeek，也提醒后续必须以真实模型首个失败点为准。
- 当前默认设备范围仍只有 NPU 6、7。双卡容量不足以承载约 `279.41 GiB` 的 W8A8 canonical 权重，不能替代八卡 P5。
- P6 controlled baseline、msprof、性能 A/B、瓶颈归因和 P8 real-move 任务继续关闭。

## 八卡范围确认后的唯一下一任务

拟定任务 ID：

```text
p5_deepseek_v4_flash_8card_128k_smoke_retry_v0202_2026_0710
```

任务目标保持为 P5，不升级为 P6：

1. 固定使用上述新隔离环境，并 source CANN 与 ATB `set_env.sh`，设置 `VLLM_PLUGINS=ascend`。
2. 先确认 8 卡全部健康、空闲且与用户批准的 `ASCEND_RT_VISIBLE_DEVICES` 完全一致；任一卡不满足即返回 `blocked_resource_scope`，不启动模型。
3. 记录 DeepSeek-V4 architecture、tokenizer/tool/reasoning parser、MTP、DSA/FlashComm1 配置入口的可识别性。
4. 使用 `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp`，保持 TP8、EP、`quantization=ascend`、MTP 和 fixed 64-token 控制，复跑 `4096 -> 32768 -> 65536 -> 98304 -> 131072` context ladder。
5. 为与首轮形成可比的运行时升级对照，除 0.20.2rc1 必需的配置迁移外，不同时改动 workload；FlashComm1 改用 `additional_config.enable_flashcomm1`，并显式记录 `additional_config.enable_dsa_cp`。
6. 仍按 `max_num_seqs 16 -> 4 -> 1 -> disable MTP` 记录降级；任何降级都只能标记 `yellow/degraded_smoke`。
7. 不运行 msprof，不做并发性能矩阵，不输出容量、性能、瓶颈或优化收益结论。

验收保持不变：

| 状态 | 条件 | 后续 |
| --- | --- | --- |
| green | MTP 开启且 `131072+64` 成功 | 才进入 P6.0 baseline freeze |
| yellow | 八卡有成功请求，但降级或未达 131072 | 只进入 P6 stabilization |
| red | 八卡不 ready 或无成功请求 | 留在 P5，按第一失败点定向修复 |

## 回传边界

raw log、大模型输出、环境目录、模型文件和其他大产物留在服务器。后续任务下发后，邮件正文和每个附件仍不得超过 70KB；只回传小型版本表、设备摘要、最终命令、逐档状态、第一失败点、分级结果和服务器 artifact path。
