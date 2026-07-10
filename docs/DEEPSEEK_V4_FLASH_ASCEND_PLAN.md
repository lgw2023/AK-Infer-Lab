# DeepSeek-V4-Flash on Ascend：P5-P9 专项计划

日期：2026-07-10

## 1. 专项目标

围绕 DeepSeek-V4-Flash 建立三层证据链：

1. 在 Atlas 800T A2 8×64GB 上形成官方 FP8 + FP4 experts mixed checkpoint 的八卡可复现基线。
2. 在单卡/双卡和等效压力组件上定位容量、格式、kernel、通信和状态恢复边界。
3. 用 KV/Prefix、MoE expert 与统一状态对象 trace 驱动 simulator，反推下一代硬件优先级。

完整阶段契约见 `docs/EXPERIMENT_PLAN.md`，P8 工程详案见 `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`。

## 2. 模型对象与当前路径

DeepSeek-V4-Flash 的模型规格和量化事实以 `docs/SOURCES_AND_BOUNDARIES.md` 登记的官方 model card 为准。本项目必须始终区分来源 checkpoint 与 Ascend runtime object：

| object_id | 本地镜像 | 服务器路径 | 当前角色 | 边界 |
| --- | --- | --- | --- | --- |
| `deepseek_v4_flash_official_hf` | `/Volumes/Elements/DeepSeek-V4-Flash` | `/data/node0_disk1/Public/DeepSeek-V4-Flash` | 项目主 runtime 对象；46 分片 / 148.66GiB；当前四卡新栈探针 | mixed FP8+FP4 experts；不得显式传 `--quantization ascend`；新 tag 仍需服务器验证 |
| `deepseek_v4_flash_w8a8_mtp_modelscope` | `/Volumes/Elements/DeepSeek-V4-Flash-w8a8-mtp` | `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp` | 历史 inventory only | 项目已停止使用；禁止启动、转换或作为 fallback |

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
new isolated host conda environment pending server build
```

旧 `0.20.2/0.20.2rc1` 隔离环境通过 Qwen2.5 smoke，但官方 checkpoint 在 `ModelConfig` 量化平台门失败。当前任务新建完全独立的 `0.22.1/0.22.1rc1` 环境；旧环境和源码保持不动。真实 DeepSeek DSA/MoE/MTP/EP/weight-load 路径仍未验证。

### 3.2 对照路：MindIE

MindIE 是 P6/P8 的候选对照底座，不是当前前置条件。现有服务器体检把 `mindie_version` 记为 unknown，package inventory 记录 `mindie=missing`。只有用户另行确认可用环境、版本和模型支持后，才创建 MindIE 对照实验；不得在 P5/P6 vLLM 基线任务中顺带安装。

## 4. P5：八卡拉起与 128K Context Ladder

当前先执行的前置诊断为：

```text
p5_deepseek_v4_flash_4card_fp8_stack_upgrade_probe_v0221rc1_2026_0710
ASCEND_RT_VISIBLE_DEVICES=4,5,6,7
TP=4, EP=enabled, max_model_len=8192, max_num_seqs=1
```

上一轮 `0.20.2rc1` 已得到 `diagnostic_red_quant_format`，且失败早于权重加载。当前诊断先构建 `0.22.1/0.22.1rc1` 独立栈，按 `base_no_mtp -> mtp_on after base success` 顺序运行；不显式传 `--quantization`，不使用 offload，不跑 128K ladder。W8A8 已退出项目执行。

当前任务：

```text
p5_deepseek_v4_flash_official_fp8_8card_128k_smoke_after_authorization
```

参考配置：

```text
tensor_parallel_size=8
expert_parallel=enabled
quantization=auto_from_checkpoint_config
max_model_len=135168
max_num_seqs=16 first
prefix_cache=enabled
chunked_prefill=enabled
MTP=enabled first
```

请求阶梯：

```text
4096 -> 32768 -> 65536 -> 98304 -> 131072
fixed output = 64 tokens
```

P5 只回答：是否 ready、最高成功上下文、是否保持固定输出、发生了何种降级。P5 不跑 msprof，不做性能基准或瓶颈归因。

状态门：

- `green`：MTP 保持开启并完成 `131072+64`。
- `yellow`：有成功请求，但降低 `max_num_seqs`、关闭 MTP 或未达到 131072。
- `red`：八卡不 ready 或没有成功请求。

## 5. P6：八卡 Reference Baseline

八卡基准的目的不是立即优化，而是给 P7/P8/P9 一个可信的官方 checkpoint reference point；它必须等待当前四卡新栈 gate 成功和独立八卡授权。

### 5.1 Baseline freeze

- 复用 P5 最终成功 command，不从目录名反推参数。
- P5 yellow 先稳定 degraded profile，修复前不升级为 official baseline。
- 固定 server lifecycle、rank mapping、workload、输出、采样和 warmup。

### 5.2 Unprofiled 性能

先跑 `4K+64+c1`、`中档+64+c4`、`最高稳定档+64+c1` 三个 tracer-bullet cell，每个重复 3 次；稳定后再扩展 4K/中档/最高稳定档、64/256 输出和 1/4/8 并发。记录 TTFT、TPOT、ITL、E2EL、throughput、P95/P99、server stats 和 token control。

### 5.3 Profiled evidence

从 unprofiled 矩阵选代表 cell，单独运行 msprof、request-device aggregate、memory/transfer 读数。Profiled latency 不回填为用户性能。

### 5.4 单变量对照

顺序为 Prefix Cache、MTP、Chunked Prefill、`max_num_seqs`、`max_model_len`。每次只改变一项，任何组合约束或被迫降级都另建实验卡。

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
expert aggregated hotness
  -> expert map / static placement / replication
  -> request/session-aware trace when needed
  -> Expert Tier V0 simulation
  -> gated DRAM-to-HBM warm prefetch V1
```

EPLB 和冗余专家部署只作为 hotness/placement 支点，不包装成 expert offload。SSD cold expert 第一阶段只做 checkpoint、离线 preload 和 simulator cost，不进入 decode step。

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

1. 等待 P5 服务器真实回传并判定 green/yellow/red。
2. 不因本轮文档刷新改写当前 `developer-to-server.md`。
3. P5 回传后先生成 P6 baseline contract，不直接下发大矩阵。
4. P8 本地第一实现任务将是 capability matrix + observe-only schema/fixture，不是 expert payload move。
