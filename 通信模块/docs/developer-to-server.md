# Developer to Server

## 当前状态：等待运行时升级反馈（当前无新增服务器任务）

状态 ID：

```text
no_new_server_task_waiting_vllm_0202_upgrade_feedback_2026_0710
```

本文件当前不授权新的服务器执行。服务器端已经在独立进行运行时升级；请不要重跑旧 P5 Smoke，也不要依据本文件重复安装、升级或启动双卡/八卡服务。待升级反馈返回开发机后，再清空本文件并写入下一轮唯一任务。

## 已完成任务与结论

最近完成任务：

```text
p5_deepseek_v4_flash_8card_128k_smoke_2026_0710
```

邮件最终评级为 `RED`：

- `git pull` 与 `tests/inference_contracts` 通过，两个模型路径及 canonical 分片完整。
- 8 张 NPU 均健康，但当时只有 NPU 6、7 空闲；服务器以 TP2 做了启动诊断，没有形成八卡实跑。
- 含 MTP 的首次启动在 vLLM 0.18.0 报 `Unsupported speculative method: 'mtp'`。
- 关闭 MTP 后，vLLM-Ascend 0.18.0 在 `model_runner_v1.py` 读取 DeepSeek-V3/MLA 字段 `kv_lora_rank`，而 `DeepseekV4Config` 不含该字段。
- server 未 ready，请求成功数 `0`，最高成功输入 `0`；不得输出容量、性能、瓶颈或优化收益结论。

服务器 artifact 仍保留在：

```text
/data/node0_disk1/liguowei/AK-Infer-Lab/工作记录与进度笔记本/runtime_trace_smokes/p5_deepseek_v4_flash_8card_128k_smoke_2026_0710
```

## 服务器正在独立执行的升级（仅记录，不重复下发）

```text
vLLM             0.20.2
vLLM-Ascend      0.20.2rc1
CANN              9.0.0
PyTorch           2.10.0
torch-npu         2.10.0
triton-ascend     3.2.1
```

本地官方参考快照的 `v0.20.2rc1` 发布记录把 DeepSeek-V4 模型架构、DSA attention、KV cache、tool-call parser、MTP 和 910B custom operator 支持列入该版本线，并给出与上述版本一致的依赖组合。该记录只说明目标版本具备官方实现，不等于本服务器已经升级成功；真实状态以后续服务器回传为准。

## 等待反馈时的判读边界

- 原八卡 P5 计划保持不变；升级不会把 TP8/EP、128K ladder 或 fixed 64-token 验收降级成双卡计划。
- 本地 W8A8 canonical 权重约 `279.41 GiB`，双卡原始 HBM 约 `128 GiB`；官方 A2 部署前提为 `8×64GB`。双卡只能形成运行时兼容性或容量边界证据，不能称 full-model deployment。
- 升级后参数入口已经发生迁移风险，例如 v0.20.2rc1 发布记录说明 FlashComm1 从环境变量迁移到 `additional_config.enable_flashcomm1`；不得直接照抄 0.18.0 旧命令重跑。
- P6 controlled baseline、msprof、性能 A/B、瓶颈归因仍保持关闭。
- raw log、大模型输出、环境目录和其他大产物继续留在服务器；邮件正文和每个附件仍不得超过 70KB。

## 开发机收到下一封反馈后优先核对

1. 精确的 Python、vLLM、vLLM-Ascend、PyTorch、torch-npu、triton-ascend、CANN 版本和安装来源。
2. 旧 0.18.0 环境是否保留，新环境是否隔离，以及实际使用的 Python/vLLM 路径。
3. DeepSeek-V4 原生 architecture、tokenizer/tool/reasoning parser 和 MTP 配置入口是否能被新运行时识别。
4. 若服务器已自行执行探针，记录所用 NPU、完整 command、第一失败点、exit code 和服务器 artifact path；不要把双卡容量失败上升为八卡结论。
5. 只有新运行时证据闭环且 8 卡可用后，才决定是否重新下发原八卡 P5 Smoke。
