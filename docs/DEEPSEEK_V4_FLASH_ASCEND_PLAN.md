# DeepSeek-V4-Flash on Ascend：P5-P9 专项计划

日期：2026-07-17

## 1. 专项目标

围绕 DeepSeek-V4-Flash 建立三层证据链：

1. 在 Atlas 800T A2 8×64GB 上形成 W8A8-MTP checkpoint 的八卡可复现基线。
2. 在单卡/双卡和等效压力组件上定位容量、格式、kernel、通信和状态恢复边界。
3. 用 KV/Prefix、MoE expert 与统一状态对象 trace 驱动 simulator，并以成功 smoke 或实测负结论关闭“Expert Offload / Expert Cache 能否支持 TP4 full-model capacity”问题，再反推下一代硬件优先级。

完整阶段契约见 `docs/EXPERIMENT_PLAN.md`，P8 工程详案见 `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`。

## 2. 模型对象与当前路径

DeepSeek-V4-Flash 的模型规格和量化事实以 `docs/SOURCES_AND_BOUNDARIES.md` 登记的官方 model card 为准。本项目必须始终区分来源 checkpoint 与 Ascend runtime object：

| object_id | 本地镜像 | 服务器路径 | 当前角色 | 边界 |
| --- | --- | --- | --- | --- |
| `deepseek_v4_flash_w8a8_mtp_modelscope` | `/Volumes/Elements/DeepSeek-V4-Flash-w8a8-mtp` | `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp` | 项目主 runtime、P5/P6 候选；70 分片 / 279.41GiB | 当前标准 runtime 必须八卡授权并显式使用 `--quantization ascend`；TP4 只能在 P8.5B expert-residency 路径中验证，不能直接改 TP 参数 |
| `deepseek_v4_flash_official_hf` | `/Volumes/Elements/DeepSeek-V4-Flash` | `/data/node0_disk1/Public/DeepSeek-V4-Flash` | 历史诊断与来源 inventory | mixed FP8+FP4 experts；当前 910B1 在 MXFP4 format cast 失败；不做 adapter、转换或 fallback |

本地目录存在和结构相同只用于准备实验卡，不代替服务器路径、inode、分片完整性和 runtime load 验证。

## 3. 当前运行底座

### 3.1 主路：vLLM-Ascend

当前服务器已有证据：

```text
Python 3.11.15
CANN 9.0.0
torch 2.10.0+cpu
torch_npu 2.10.0
vLLM 0.22.1+empty
vLLM-Ascend 0.22.1rc1
triton-ascend 3.2.1
transformers 5.5.4
new isolated host conda environment built; W8A8-MTP official context ladder green through 131072+64
```

P8.1 parent 继续保留 `yellow_p8_1_matrix_trace_invalid`，P8.1-R1 已接受为
`green_p8_1_r1_official_mtp_observe_only_matrix`；二者均不被后续 K0 覆盖。

旧 `0.20.2/0.20.2rc1` 隔离环境通过 Qwen2.5 smoke，但 mixed checkpoint 在 `ModelConfig` 量化平台门失败。完全独立的 `0.22.1/0.22.1rc1` 环境已建成；W8A8-MTP 已完成 P6 official context/performance/profiled/matched controls，P8.1-R1 也已接受 green。P8.2-K0 已接受 `green_p8_2_k0_order_balanced_prefix_cache_baseline`，仍不是 performance reference 或 offload evidence。K1 旧 `OffloadingConnector + NPUOffloadingSpec` 冻结路径的本地审计与服务器只读复核已关闭为 `blocked_p8_2_k1_frozen_stack_import_incompatible`。K1A source/import/registration 通过，但冻结 32 GiB/rank 容量点在任何请求前因 `aclrtMallocHostWithCfg / 207001` 收口为 `red_p8_2_k1a_simple_cpu_offload_no_success`。当前唯一任务将 K1A-R1 exact KV block geometry/八 rank pinned envelope 与 P8.3-I0 只读 checkpoint inventory 分 section 执行，正式模型 lifecycle/request 为 0。

### 3.2 对照路：MindIE

MindIE 是 P6/P8 的候选对照底座，不是当前前置条件。现有服务器体检把 `mindie_version` 记为 unknown，package inventory 记录 `mindie=missing`。只有用户另行确认可用环境、版本和模型支持后，才创建 MindIE 对照实验；不得在 P5/P6 vLLM 基线任务中顺带安装。

## 4. P5：八卡拉起与 128K Context Ladder

NPU 0-7 曾获用户对已完成任务的明确授权。首轮 context-ladder 任务在 MTP graph capture 失败，后续 P6.1R、P6.1L-R1 和 P6.1C-R1 已依次关闭修复、长输出与 official context 门。以下是已经关闭的 P6 profiled reference 历史任务，不是当前 handoff：

```text
p6_2_deepseek_v4_flash_w8a8_mtp_profiled_evidence_2026_0714
ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
TP=8, EP=enabled, MTP=enabled, msprof per representative cell
```

mixed checkpoint 的最终诊断为 `diagnostic_yellow_acl_path_fixed`：ACL 门通过，Ascend model route 正确，46/46 分片加载完成，随后四个 worker 在 `process_weights_after_loading` 同样命中当前 SoC 不支持 `customize_dtype`。因此不再继续 mixed 兼容性工作。W8A8 权重为 279.41GiB；首轮八卡在 MTP proposer DSA-CP graph capture 因 `positions_cpu=None` 失败。no-MTP 路线随后完成权重加载、graph capture、server-ready 与一个 `4096+64` 请求，最终评级为 `yellow_no_mtp_graph_request_success`。

已完成的 official context 任务：

```text
p6_1c_r1_deepseek_v4_flash_w8a8_mtp_official_context_ladder_sampling_repair_2026_0714
```

server-local Git 管理最终验收已完成。P6.1C-R1 正式五档均首次成功，P6.1 unprofiled 18-cell matrix、P6.2 三个 profiled cell、P6.3A matched MTP on/off 与 P6.3B-R4-R1 explicit Prefix Cache control 均已由开发机接受为 green；P8.1 parent yellow、P8.1-R1 green 与 P8.2-K0 green 均已关闭。K1 旧路径为 blocked，K1A 32 GiB/rank 容量点为 red。当前唯一服务器 handoff 是 `p8_dual_track_k1a_r1_allocator_and_p8_3_i0_inventory_2026_0717`：只允许一个 geometry-only lifecycle、零模型请求、最多四个 pinned allocator wave 与零 NPU checkpoint inventory；K2/P8.3-I1 均未授权。

参考配置：

```text
tensor_parallel_size=8
expert_parallel=enabled
quantization=ascend
max_model_len=135168
max_num_seqs=1
prefix_cache=enabled
chunked_prefill=enabled
MTP={"method":"mtp","num_speculative_tokens":1}
```

已完成的 unprofiled 验证：

```text
1 fresh lifecycle; 1 explicit warmup; 24 measured batches; 90 measured requests
context=4096/65536/131072; output=64/256; concurrency=1/4/8
zero retry; no HBM sampler; no profiler
```

P6.1C-R1 已回答 MTP 与最高稳定上下文；P6.1 unprofiled 已建立性能 reference；P6.2 已建立 profiled evidence reference；P6.3A 已关闭 matched MTP mechanism gate；P6.3B-R4-R1 已关闭 primary scope 的 explicit Prefix Cache mechanism gate。P6.3C 因 frozen `4096 < 135168` 配置在 off 侧触发 vLLM validation，已记录为 `blocked_p6_3c_not_strict_single_variable`。后续 P8.1-R1/P8.2-K0/K1A 均固定 Chunked Prefill-on，不重开 P6.3C，也不把该选择写成性能比较。

状态门：

- `green`：MTP 保持开启并完成 `131072+64`。
- `yellow`：有成功请求，但降低 `max_num_seqs`、关闭 MTP 或未达到 131072。
- `red`：八卡不 ready 或没有成功请求。

## 5. P6：八卡 Reference Baseline

八卡基准的目的不是立即优化，而是给 P7/P8/P9 一个可信的 W8A8 reference point。P6.1 unprofiled、P6.2 profiled evidence、P6.3A 与 P6.3B-R4-R1 已完成；P6.3C 条件项的严格单变量可行性已 blocked，未创建可执行 workload。

### 5.1 Baseline freeze

- 复用 P5 最终成功 command，不从目录名反推参数。
- P5 yellow 先稳定 degraded profile，修复前不升级为 official baseline。
- 固定 server lifecycle、rank mapping、workload、输出、采样和 warmup。

### 5.2 Unprofiled 性能

`4K+64+c1`、1 warmup + 3 measured 的 no-MTP 最小对照与 official MTP 18-cell matrix 均已完成。

P6.1 已记录 TTFT、TPOT、ITL、E2EL、throughput、server stats 和 token control；MTP 允许同一 SSE chunk 最多交付 2 token，同 chunk token 共享 client arrival timestamp，不把 client-observed ITL 解释为 NPU decode-step latency。

### 5.3 Profiled evidence

从 unprofiled 矩阵选出的三个代表 cell 已完成 msprof、request-device aggregate 与 phase-memory 读数，开发机接受为 `green_mtp_profiled_evidence`。Profiled latency 不回填为用户性能。

### 5.4 单变量对照

顺序改为 matched MTP、purpose-built Prefix Cache、条件式 Chunked Prefill；`max_num_seqs` 是可选 scheduler/capacity sweep，`max_model_len` 后移到 P7 capacity boundary。P6.3C 已实证 `4096 < 135168` 使严格单布尔对照不可执行，因而以 `blocked_p6_3c_not_strict_single_variable` 停止，不另建调参后的伪 A/B。

P6.3A 已完成的 matched 集覆盖 `4096/65536/131072` context、`64/256` output 和
c1/c4/c8 代表并发，共 8 cell；`mtp_off` 与 `mtp_on` 各执行 3 个 batch/cell，合计
48 batch / 108 request。请求 body bytes/hash 跨 mode 相同，只有 speculative config 改变；
固定 `mtp_off -> mtp_on` 顺序是已知限制，candidate green 不预设收益方向。

P6.3B-R4-R1 已完成 `4096/32768/65536/131072 × 50%/90% shared prefix` 八个 group；
每 group 每 mode 1 prime + 3 measured follower。两边都保持 MTP 和 same R2 repair，只改变显式
`--no-enable-prefix-caching` / `--enable-prefix-caching`。64/64 request 成功，off hit=0，on primary
9/9 positive 且逐请求符合 16K hybrid LCM floor；其余 15 条 boundary 仍零命中，因此不形成普遍命中或性能收益结论。

### 5.5 MindIE 对照

只有 runtime availability gate 关闭后才执行；先统一模型对象、请求与指标语义，再比较，不把不同 runtime 的原生字段直接视为同一测量。

## 6. P7：单卡/双卡极致硬件边界

P7 不套用八卡 full-model 部署承诺。测试对象按证明目的拆分：

| 对象 | 证明目的 | 有效输出 |
| --- | --- | --- |
| 小模型 | KV/Prefix、adapter、trace、transfer 链路 | 工具链与状态路径可运行 |
| 中型 MoE | expert hotness、placement、miss/reuse | P8 expert 校准数据 |
| DeepSeek 子图/partial shard | weight format、scale、kernel、KV shape | 兼容性和失败边界 |
| 模拟 expert pool | HBM/DRAM/SSD 预算与策略 | replay/simulator 输入 |
| simulator-only full model | 全模型 what-if | 误差区间，不是实机部署 |

必须分类记录第一失败点：capacity、format/scale、kernel、runtime、collective、state restore 或 feature combination。

## 7. P8：AK 分层工程原型

### 7.1 不是“直接接一个完整框架”

P8 的底座和自研边界是：

```text
vLLM-Ascend / MindIE:
  模型执行、scheduler、已有 Prefix/KV/EP/EPLB 能力

AK State Runtime:
  capability matrix、事件规范化、StateObject metadata、policy、replay、simulator handoff

不自研：
  通用推理引擎、完整生产级 object store、NPU-SSD 直通、跨节点一致性系统
```

### 7.2 KV/Prefix 主线

```text
P6 Prefix baseline
  -> vLLM-Ascend KV Cache CPU Offload
  -> UCM / External KV Cache DRAM-first
  -> cold persistence only after warm-tier evidence
  -> MindIE Prefix/KV Pool comparison when available
```

### 7.3 MoE 主线

```text
expert tensor/role bytes + TP4 rank mapping
  -> expert aggregated hotness
  -> expert map / static placement / replication
  -> request/session-aware trace when needed
  -> Expert Tier V0 + TP4 capacity simulation
  -> gated expert payload mover / DRAM-to-HBM warm prefetch V1
  -> CPU-first loader + TP4 4096+64,c1 full-model capacity smoke
  -> MTP/Prefix Cache/larger context only after capacity path
```

当前 TP8 no-MTP/MTP 权重加载日志为 `38.1255/39.2795 GB per worker`，P6.1C whole-device HBM 峰值为 `61436–61447 MB / 65536 MB`。这些数字足以说明直接 TP4 没有容量前提，但不能相减后固化为应卸载多少 GB；P8 必须以逐 tensor/expert materialized bytes、TP4 owner mapping 和 runtime reserve 重算。EPLB 和冗余专家部署只作为 hotness/placement 支点，不包装成 expert offload。SSD cold expert 第一阶段只做 checkpoint、离线 preload 和 simulator cost，不进入 decode step。

### 7.4 StateObject 主线

统一对象只包含：

```text
KV block
Prefix block
Expert weight
Weight shard
Session
```

Trace 是事件，不是对象。对象 registry 只保存 metadata 和 opaque runtime reference，不持有模型 payload。

完整对象字段、runtime adapter、P8.0-P8.6 门槛与交付物见 P8 详案。

## 8. P9：硬件参数联合分析

P9 合并：

```text
P0/P3 microbench
P6 eight-card baseline
P7 one/two-card boundary
P8 KV/expert/state trace and policy outcomes
```

优先扫描：HBM capacity/bandwidth、DRAM capacity/bandwidth、NPU-CPU link、HCCL collective、SSD I/O、CPU cores/vector、HMM/PIM modeled parameters。

每条 hardware ask 必须给出：触发实验、测量机制、受影响指标、模型误差、软件前提、workload 范围和置信度。

## 9. DeepSeek 实验卡最小字段

```yaml
experiment_id:
date:
git_commit:
claim_level: readiness | smoke | controlled_benchmark | profile_readout | calibrated_simulation

model_object_id:
server_model_path:
runtime:
runtime_version:
server_id:
npu_count:
hbm_per_npu_gb:

parallelism:
  tp:
  ep:
  dp:
  pp:

features:
  prefix_cache:
  chunked_prefill:
  mtp:
  kv_cpu_offload:
  ucm:
  eplb:
  expert_tier_policy:

workload:
  manifest:
  prompt_tokens:
  output_tokens:
  concurrency:
  warmup:
  repeats:

artifacts:
  server_command:
  request_summary:
  server_stats:
  profiler_summary:
  state_trace:

boundaries:
  scope:
  not_claim:
  known_confounds:
```

## 10. 当前下一步

1. P6.1C-R1 official、P6.1 unprofiled performance、P6.2 profiled evidence、P6.3A matched MTP 与 P6.3B-R4-R1 explicit Prefix Cache control 已完成并验收。
2. P6 五份汇总交付物、P8.1-R1 observe-only 与 P8.2-K0 已闭合。K1 旧路径保持 blocked；K1A 32 GiB/rank 点保持 red。当前 handoff 只授权 K1A-R1 geometry-only lifecycle + 八 rank pinned envelope 和 P8.3-I0 只读 inventory，`formal_model_lifecycle_count_exact:0`、`model_request_count_exact:0`、`next_task_authorized:false`、`result_transfer_authorized:false`。
3. P6.3C Chunked Prefill on/off 已完成冻结源码审计：显式双布尔 CLI 存在，但 `4096 < 135168` 使 off 侧在 resolved config 前失败，结论为 `blocked_p6_3c_not_strict_single_variable`。
4. P8.3-I0 deterministic index/header parser、Parquet schema 与 TP4 planning-budget 合同已实现，当前 handoff 授权其零 NPU 真实 checkpoint 物化；P8.3-I1 hotness/runtime trace、P7 与 P9 均需新授权。
