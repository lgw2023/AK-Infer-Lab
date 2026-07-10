# 09 DeepSeek-V4-Flash 专项计划

日期：2026-07-10

## 1. 当前专项判断

DeepSeek-V4-Flash 专项已经从“对象登记/readiness”进入 P5 八卡 W8A8-MTP 拉起与 128K context ladder smoke。首轮任务已于 2026-07-10 回传 `RED`；服务器随后完成新隔离运行时构建和 Qwen2.5 纯注意力端到端 smoke。升级门已经关闭，用户现授权 NPU `4,5,6,7` 先做四卡 TP4/EP 最小拉起诊断；完整八卡 P5 门仍未授权：

```text
Canonical W8A8-MTP eight-card runtime object (70 shards / 279.41 GiB):
/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp

Authorized four-card FP8/FP4 format probe (46 shards / 148.66 GiB):
/data/node0_disk1/Public/DeepSeek-V4-Flash
```

最近完成的服务器任务：

```text
p5_deepseek_v4_flash_8card_128k_smoke_2026_0710
```

首轮在仅 NPU 6、7 空闲的条件下以 TP2 做启动诊断，所有请求均未进入推理阶段。`vLLM 0.18.0 / vLLM-Ascend 0.18.0` 先后暴露 `mtp` 不受支持，以及 `DeepseekV4Config` 缺少 `kv_lora_rank` 的架构错配；最终最高成功输入为 `0`，不能形成容量、性能或瓶颈结论。

服务器已验证以下隔离运行时：

```text
vLLM 0.20.2
vLLM-Ascend 0.20.2rc1
CANN 9.0.0
PyTorch 2.10.0
torch-npu 2.10.0
triton-ascend 3.2.1
```

隔离环境位于 `/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.20.2rc1`，原 0.18.0 环境和共享 vLLM 源码未改动。Qwen2.5-3B-Instruct 已证明 Ascend plugin、V1 engine、模型加载、生成和释放链路可用；但该模型不经过 DeepSeek-V4 的 DSA/MoE/MTP/TP8/EP/W8A8 路径，因此 P5 仍未通过。Qwen3.5-4B 的 Mamba/GDN prefill 失败属于不同架构内核路径，不否定 DeepSeek，也不能被忽略为通用环境成功。

本页只维护专项现状和阶段关系。稳定实验契约见 `docs/EXPERIMENT_PLAN.md`；P8 详案见 `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`。

## 2. 专项目标

1. 在 Atlas 800T A2 8×64GB 上建立 DeepSeek-V4-Flash W8A8-MTP 可复现 reference baseline。
2. 在单卡/双卡和等效组件上定位容量、格式、kernel、通信和状态恢复边界。
3. 以 KV/Prefix 和 MoE expert 为主线，形成可观测、可模拟、分阶段可执行的状态分层原型。
4. 用真实 trace 与 microbench 校准 simulator，输出下一代硬件优先级。

## 3. P5 当前验收

请求阶梯：

```text
4096 -> 32768 -> 65536 -> 98304 -> 131072
fixed output = 64 tokens
```

状态：

- green：MTP 保持开启且 `131072+64` 成功。
- yellow：八卡至少一个请求成功，但发生降级或未到 131072。
- red：八卡不 ready 或无成功请求。

P5 不跑 msprof，不输出 benchmark、瓶颈或优化收益。

## 4. P6-P9 专项路线

| 阶段 | DeepSeek 专项目标 | 核心产物 |
| --- | --- | --- |
| P6 | 八卡 unprofiled baseline、profiled evidence、单变量 A/B | baseline contract、性能表、profile report |
| P7 | 1/2 卡边界与中型 MoE/子图/模拟 expert pool 校准 | boundary/compatibility/calibration |
| P8 | KV/Prefix real path + expert trace/static placement/tier simulation | capability matrix、StateObject trace、P8 reports |
| P9 | 模型性能与硬件参数联合分析 | sensitivity、hardware ask、归因报告 |

## 5. P8 在 DeepSeek 专项中的落点

### 5.1 运行底座

- vLLM-Ascend：主路；服务器已证实 0.18.0 与 DeepSeek-V4 不兼容，并已完成 0.20.2rc1 隔离环境与 Qwen 纯注意力 smoke；DeepSeek-V4 真实路径仍待八卡 P5 复跑。
- MindIE：官方能力对照候选；当前服务器证据为 unknown/missing，需单独关闭 availability gate。

最新官方文档出现某项能力，不代表升级环境已经可用。P8.0 必须先做 capability probe。

### 5.2 KV/Prefix

```text
P6 Prefix baseline
  -> KV Cache CPU Offload
  -> UCM / External KV Cache DRAM-first
  -> cold persistence
```

先回答真实 path、hit/miss、bytes、restore/recompute、HBM/DRAM 与 tail cost，再谈收益。SSD 不进入逐 token decode 热路径。

### 5.3 MoE Expert

```text
expert hotness
  -> expert map / static placement
  -> holdout-based tier simulation
  -> gated DRAM-to-HBM warm prefetch
```

EPLB/static map 是 placement 支点，不是 offload。没有 expert identity、bytes、load latency 和 miss penalty 时，不启动真实 warm/cold move。

### 5.4 StateObject

项目统一管理 KV block、Prefix block、Expert weight、Weight shard 和 Session 的 metadata、tier、hotness、成本和策略。Trace 单独作为事件流；registry 不持有 tensor payload。

## 6. 单卡/双卡边界口径

允许：

- 小模型 KV/Prefix/adapter smoke。
- 中型 MoE expert trace 与 placement。
- DeepSeek 子图、partial shard、source metadata、局部算子和格式验证。
- 模拟 expert pool 与 full-model simulator。

禁止：

- 把 8×64GB 聚合 HBM 写成单卡 512GB。
- 把子图/裁剪/模拟结果写成 official full-model deployment。
- 把 SSD 顺序读带宽写成逐 token cold expert restore 能力。
- 把 CPU 写成主干 attention/FFN 的默认替代算力。

## 7. 当前下一步

1. 执行 `p5_deepseek_v4_flash_4card_small_checkpoint_probe_v0202_2026_0710`：服务器完整同步 `main` 后，只用 NPU `4,5,6,7`，固定 TP4/EP、8K 配置上限、`max_num_seqs=1`、eager mode；若 server ready 只发一个 `4096+64` 请求。
2. 选中 46 分片 / `148.66 GiB` 的 FP8/FP4 checkpoint，不显式传 `--quantization`，用于验证格式/运行时首错；70 分片 / `279.41 GiB` W8A8 目录静态超过四卡 HBM，本轮不启动。
3. 量化格式或容量失败立即停止，不启用 CPU/NVMe/KV offload。只有明确 MTP/speculative 失败且不是格式、容量或更早错误时，才补一次 MTP off 诊断。
4. 四卡成功也只是 diagnostic，不解锁 P6；四卡失败不外推为 canonical 八卡 W8A8 不可行。八卡 P5 继续等待独立资源授权。
5. 准备 P7 中型 MoE expert trace 候选与 P8 capability matrix 字段；P8 第一实现片仍为 observe-only trace。
