# DeepSeek-V4-Flash on Ascend：八卡基准与极限硬件专项计划

## 1. 模型事实

DeepSeek-V4-Flash 是 DeepSeek-V4 系列中的 MoE Flash 版本，官方口径为 284B total parameters、13B activated parameters、1M context。开源主权重采用 FP4 + FP8 Mixed：MoE expert parameters 使用 FP4，绝大多数其他参数使用 FP8。这个事实决定了两件事：第一，模型并不是 BF16 dense 模型；第二，容量压力主要来自全量专家权重和状态对象，而不是单 token 激活参数。

来源锁定：
- DeepSeek 模型事实以 `deepseek-ai/DeepSeek-V4-Flash` Hugging Face model card 为准。
- Ascend 部署事实以 vLLM-Ascend `DeepSeek-V4-Flash` 教程为准。
- 本文档按 2026-07-08 校验；后续实际执行前必须重新核对权重、镜像、vLLM-Ascend 版本和服务器硬件。

## 2. Ascend 官方可运行基线

当前应采用官方 vLLM-Ascend 路线作为八卡基准：

```text
Model: DeepSeek-V4-Flash-w8a8-mtp
Hardware: official reference 1 × Atlas 800 A2, 64GB × 8; project target Atlas 800T A2 requires server-side compatibility proof
Parallelism: tensor_parallel_size=8, expert_parallel=enabled
Quantization: ascend
Runtime: vLLM-Ascend
Key runtime features: chunked prefill, prefix caching, async scheduling, MTP speculative decode
```

当前登记两个后续测试对象：

| 对象 | 本地状态 | 角色 | 边界 |
| --- | --- | --- | --- |
| `DeepSeek-V4-Flash-w8a8-mtp` | `/Volumes/Elements/DeepSeek-V4-Flash-w8a8-mtp`，ModelScope 版本已下载完成 | P6 八卡 baseline 首选 | 本地路径不是服务器路径；Atlas 800T A2 兼容性必须实测 |
| `deepseek-ai/DeepSeek-V4-Flash` | `/Volumes/Elements/DeepSeek-V4-Flash`，仍在下载 | 官方来源、转换/兼容性和 P7/P8 边界研究对象 | 未验证前不能写成 vLLM-Ascend `--quantization ascend` 可直接加载的 W8A8-MTP 形态 |

用户会自行把模型目录拷贝到服务器。实验卡片只能先写 server path 占位，不得推断服务器路径。

八卡基准的目的不是直接优化，而是建立可信的 reference point。所有 P7 单卡/双卡、P8 KV Offload/UCM/Mooncake/专家分层和 P9 硬件敏感性实验都必须能回到这个 reference point 进行对比。

如果服务器侧只能先用更低 `max_model_len`、更小 `max_num_seqs` 或关闭某个官方开关完成 smoke，文档必须标记为 `degraded_smoke`，不得归入正式八卡基准。

## 3. 八卡实验矩阵

### 3.1 B0：官方基线

| 变量 | 默认值 | 记录 |
| --- | --- | --- |
| TP | 8 | rank 映射、HCCL/HCCS 状态 |
| EP | enabled | expert parallel 状态 |
| quantization | ascend | 权重路径、scale 元数据 |
| max_model_len | 先 32K/128K，再扩展 | 不直接首跑 1M |
| max_num_seqs | 1/4/8/16 | 连续 batching 行为 |
| max_num_batched_tokens | 4096 起 | chunked prefill 行为 |
| prefix cache | on | server stats + trace |
| MTP | on/off A/B | acceptance、TPOT、tail |

输出：`benchmark_card.yaml`、`server_config.sh`、`request_trace.jsonl`、`vllm_stats.jsonl`、`msprof_summary/`、`request_device_summary.tsv`、`hardware_snapshot.yaml`。

### 3.2 B1：功能开关 A/B

优先做四组受控对照：

1. prefix-cache on/off。
2. chunked-prefill on/off。
3. MTP on/off。
4. max_model_len 32K / 128K / 384K 梯度。

每组只改变一个变量。所有请求必须固定 `min_tokens`、`ignore_eos` 或等价策略，避免生成长度混杂导致 raw delta 不能解释。

单变量对照必须记录完整 server command。特别是 MTP、prefix cache、chunked prefill 和 hybrid KV cache manager 之间可能存在组合约束，不能只用结果目录名反推配置。

### 3.3 B2：AK 状态分层候选

在官方基线稳定后，再引入：

1. KV Cache CPU Offload：inactive KV HBM→CPU DRAM。
2. UCM：HBM→DRAM→Storage Backend 的 external KV/prefix cache。
3. Mooncake KV Pool：KV pool / SSD offload / PD 相关验证。

B2 的第一目标是“路径可运行、trace 可采集、tail 风险可见”，不是立刻证明吞吐提升。

B2 进入条件：
- B0 至少完成 4K/8K/32K 的固定输出 smoke。
- B1 至少完成 prefix-cache on/off 和 MTP on/off 的受控读数。
- `request_id`、时间窗、rank、KV/prefix 对象或 proxy 字段至少有一种稳定 join 路径。

## 4. 单卡/双卡极限实验矩阵

单卡/双卡不能套用官方 W8A8-MTP full model。该场景用于边界研究：

| 实验 | 模型对象 | 成功标准 | 失败也要记录 |
| --- | --- | --- | --- |
| E0 | 小模型/中型 MoE | trace pipeline 完整 | 无 |
| E1 | DeepSeek-V4-Flash 子图 / partial shard | 能加载模块、跑局部算子 | 具体哪类权重/算子/内存不足 |
| E2 | 低比特或裁剪变体 | 低上下文少量 token | kernel/格式/scale 不兼容 |
| E3 | 模拟 expert pool | expert hot/warm/cold 策略可复现 | miss penalty 和 wrong prefetch |
| E4 | simulator-only full model | what-if 能解释硬件差距 | 仿真误差和缺失字段 |

单卡/双卡实验的文档必须明确：这是硬件极限探索，不是官方模型部署说明。

## 5. AK 技术优先级

### 5.1 第一优先级：KV / Prefix 管理

- vLLM prefix cache：作为当前最成熟的入口。
- vLLM-Ascend KV Cache CPU Offload：作为 DRAM warm tier 的第一候选。
- UCM：作为 external KV/prefix object 层。
- Mooncake：作为 P8 后半段的 P/D、KV Pool、SSD offload 候选。

### 5.2 第二优先级：专家热温冷分层

在 DeepSeek-V4-Flash 之前，先在中型 MoE 上建立 expert trace：

```text
request_id
layer_id
token_id
topk_expert_ids
expert_scores
expert_tier
expert_hit
expert_load_latency_ms
expert_load_bytes
prefetch_lead_time_ms
wrong_prefetch_bytes
stall_reason
```

然后迁移到 DeepSeek-V4-Flash：shared expert、non-expert main path 和高频 routed experts 放 HBM；warm experts 放 DRAM/DUMA；cold experts 放 SSD 或仅在 simulator 中建模。

### 5.3 第三优先级：CPU/NPU 阶段级协同

CPU 优先承担：tokenizer、sampling、request scheduling、prefix hash、KV metadata、expert hotness prediction、prefetch planner、I/O aggregation、offline readout、simulator。只有在 microbench 与 trace 证明收益为正时，才允许进入 partial attention、fallback expert 或小矩阵计算。

## 6. 关键实验卡片模板

每个 DeepSeek-V4-Flash 实验必须生成：

```yaml
experiment_id:
date:
git_commit:
server_id:
model:
model_variant:
model_source:
local_source_path:
server_model_path:
model_role:
quantization:
runtime:
scenario:
container_or_conda:
cann_version:
torch_npu_version:
vllm_ascend_version:
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
  mooncake:
workload:
  prompt_set:
  request_count:
  prompt_tokens:
  generated_tokens:
  concurrency_plan:
metrics:
  ttft_ms:
  tpot_ms:
  p95_tpot_ms:
  throughput_tok_s:
  hbm_peak_gb_by_rank:
  kv_cache_usage_pct:
  prefix_cache_hit_rate_pct:
  cpu_dram_peak_gb:
  d2h_bytes:
  h2d_bytes:
  ai_core_top_ops:
  stall_top_reasons:
boundaries:
  is_benchmark:
  is_smoke:
  can_compare_performance:
  known_confounds:
```
