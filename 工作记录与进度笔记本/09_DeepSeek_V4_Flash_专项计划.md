# 09 DeepSeek-V4-Flash 专项计划

日期：2026-07-14

## 1. 当前专项判断

DeepSeek-V4-Flash 专项当前处于 P6 的 official MTP context reference 门。P6.1R retry2
已关闭 MTP `4096+64` 最小请求门，P6.1L-R1 已关闭固定 4096 input 的 512/1024
decode-length 稳定性门；P6.1C 合同已准备，状态为 `prepared_not_dispatched`、
`npu_execution_authorized:false`。official baseline、128K、完整 P6.1、profiler 与 P8
仍未关闭。`0.22.1/0.22.1rc1` mixed-checkpoint 四卡诊断已在当前 SoC 的
`customize_dtype` 能力门收口，W8A8-MTP 保持唯一主对象：

```text
Project primary W8A8-MTP runtime object (70 shards / 279.41 GiB):
/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp

Historical mixed diagnostic and source inventory only:
/data/node0_disk1/Public/DeepSeek-V4-Flash
```

当前待发布服务器合同（尚未授权执行）：

```text
p6_1c_deepseek_v4_flash_w8a8_mtp_official_context_ladder_2026_0714
65536+64 sampling calibration -> fresh 4096/32768/65536/98304/131072 + 64
```

首轮在仅 NPU 6、7 空闲的条件下以 TP2 做启动诊断，所有请求均未进入推理阶段。`vLLM 0.18.0 / vLLM-Ascend 0.18.0` 先后暴露 `mtp` 不受支持，以及 `DeepseekV4Config` 缺少 `kv_lora_rank` 的架构错配；最终最高成功输入为 `0`，不能形成容量、性能或瓶颈结论。

当前固定目标运行时：

```text
vLLM 0.22.1+empty
vLLM-Ascend 0.22.1rc1
CANN 9.0.0
PyTorch 2.10.0
torch-npu 2.10.0
triton-ascend 3.2.1
```

新环境路径为 `/data/node0_disk1/liguowei/AK-Infer-Lab/.conda/envs/ak-infer-lab-vllm-ascend0.22.1rc1`，已由旧环境独立克隆并完成核心构建；旧 `0.20.2rc1` 环境和源码保持不动。W8A8 首轮八卡在 MTP+DSA-CP graph capture 失败；修正 tokenizer cached-wrapper MRO 断言后，no-MTP 路线已完成 8 worker 权重加载、graph server ready 与一个 `4096+64` HTTP 200 请求。P5 当前为 no-MTP YELLOW。

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

- vLLM-Ascend：主路；0.22.1rc1 mixed 诊断已在 SoC 能力门收敛，W8A8 no-MTP `4096+64` 请求已关闭 exact runtime gate；当前验证严格 observe-only adapter，MTP、128K、P6 与 real-move gate 仍关闭。
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

1. 当前只完成 P6.1C workload、handoff、测试和真值面；保持
   `prepared_not_dispatched`、`npu_execution_authorized:false`，不在开发机运行 NPU。
2. 后续若另获执行授权，先在一个 lifecycle 用独立三份 `65536+64` body 完成 HBM
   sampling calibration；任一 calibration hard gate 失败即 cleanup 并停止。
3. calibration green 后才启动 fresh lifecycle，无 warmup 地顺序执行
   `4096/32768/65536/98304/131072 + 64`，全程冻结同一采样周期和 request bodies。
4. calibration 不进入 highest stable context，也不产生 TTFT/TPOT/throughput 或收益结论；
   完整 P6.1、profiler 与 P8 继续分阶段执行。
5. 新产物仍需先列出精确路径、完整清单、bytes、SHA-256、敏感性、可用方法和推荐理由，
   再等待用户为完整范围选择 `email`、`upload-api` 或 `server-local`。
