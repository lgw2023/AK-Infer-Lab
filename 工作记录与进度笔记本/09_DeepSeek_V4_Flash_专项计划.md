# 09 DeepSeek-V4-Flash 专项计划

日期：2026-07-15

## 1. 当前专项判断

DeepSeek-V4-Flash 专项已越过 P6 的 official MTP context reference 门。P6.1C-R1 已由开发机
接受为 `green_mtp_official_context_ladder`，`highest_stable_context=131072`；P6.1 MTP
unprofiled baseline 随后以 18/18 cells、90/90 measured requests 首次成功收口为
`green_mtp_unprofiled_baseline`，性能 reference 已成立。P6.2 的三个代表 cell 也已由开发机
接受为 `green_mtp_profiled_evidence`，operator/memory/transfer/request-device 证据链可用。
P6.3A matched MTP on/off 已接受为 `green_p6_3a_mtp_matched_ab`；P6.3B purpose-built
Prefix Cache on/off 已完成为 `yellow_p6_3b_prefix_cache_matched_ab_partial`：Prefix-on measured
query 正增但 24/24 hit 为 0。P6.3B-R1 因 eager `sitecustomize` 早于 Ascend spec 替换，在 ready
前以 `AscendMLAAttentionSpec` manager `KeyError` 收口为
`red_p6_3b_r1_hybrid_kv_repair_no_success`，0/12 request。当前 P6.3B-R2 deferred-install repair
已授权，在 Ascend MLA/SWA spec 替换后加载 frozen vLLM `#44082` 写入侧与 vLLM-Ascend `#11107`
manager 传播 backport，P8 仍在
后续独立任务。`0.22.1/0.22.1rc1` mixed-checkpoint 四卡诊断已在当前 SoC 的 `customize_dtype`
能力门收口，W8A8-MTP 保持唯一主对象：

```text
Project primary W8A8-MTP runtime object (70 shards / 279.41 GiB):
/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp

Historical mixed diagnostic and source inventory only:
/data/node0_disk1/Public/DeepSeek-V4-Flash
```

最近完成的服务器合同：

```text
p6_2_deepseek_v4_flash_w8a8_mtp_profiled_evidence_2026_0714
short_prefill=4096+64 / long_prefill=131072+64 / decode_heavy=4096+256
fresh lifecycle per cell -> msprof + phase memory + request-device aggregate
```

当前 handoff 为
`p6_3b_r2_deepseek_v4_flash_w8a8_mtp_prefix_cache_hybrid_kv_deferred_install_repair_2026_0715`，双授权均为 true；
一个 fresh lifecycle 执行 `32768/65536/131072 × 90%`、3 prime + 9 measured，9/9 positive hit
是 candidate green 硬门。该任务不形成 Prefix Cache performance A/B。

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

- vLLM-Ascend：主路；W8A8-MTP official 131072 context、unprofiled performance 与三个代表性 profiled evidence 已关闭。observe-only adapter 的旧 no-MTP 前置已被超越，但 P8 server validation 与 real move 仍需新 baseline contract 和独立授权。
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

1. P6.1C-R1 已收口为 `green_mtp_official_context_ladder`，不重跑。
2. P6.1 unprofiled 已验收为 `green_mtp_unprofiled_baseline`，不重跑。
3. P6.2 已验收为 `green_mtp_profiled_evidence`，不把 profiled latency 当性能基线。
4. P6.3A 已验收为 `green_p6_3a_mtp_matched_ab`；P6.3B 已完成为 `yellow_p6_3b_prefix_cache_matched_ab_partial`，P6.3B-R1 保留 ready 前 red。当前 P6.3B-R2 已授权：deferred task-local hybrid-KV repair、一个 fresh lifecycle、3 prime/9 measured/12 request，9/9 positive hit 为硬门。
5. NPU/vLLM 消耗授权保持允许，但完整 P6.3B matched A/B、P6.3C 与 P8 不自动进入；任何新产物仍需先列出精确路径、完整清单、bytes、SHA-256、敏感性、可用方法和推荐理由，
   再等待用户为完整范围选择 `email`、`upload-api` 或 `server-local`。
