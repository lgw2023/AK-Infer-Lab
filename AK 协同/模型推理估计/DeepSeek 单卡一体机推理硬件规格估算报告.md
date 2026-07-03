# DeepSeek 单卡一体机推理硬件规格估算报告

核验日期：2026-07-01  
项目语境：A+K / Ascend NPU + Kunpeng CPU 小算力一体机。刘力维（ACS Lab）为本项目语境联系人，本报告不重新指定任何组织 owner 或 lead。  
输出位置：`AK 协同/模型推理估计/DeepSeek 单卡一体机推理硬件规格估算报告.md`

## 1. 任务情况与结论摘要

本报告的任务是：以 DeepSeek-V3 / DeepSeek-R1 671B 为主线，参考项目中已有 DeepSeek 架构报告、A+K 原文硬件拓扑精读笔记、第三轮反向回顾报告和相关原文 PDF，估计如果要在“单卡一体机”形态下利用量化、MLA/KV cache、Prefix/KV 复用、MoE expert 分层、CPU/DRAM warm tier、SSD cold tier、推理框架调度等技术实现模型推理，需要什么样的 GPU/NPU/HBM 或 Bailu、CPU、DRAM、SSD/NVMe、PCIe/UB/Fabric、功耗散热与可观测能力。

结论先说清楚：

1. **如果要求完整 DeepSeek-V3/R1 671B 官方 FP8 权重全部常驻热层，单卡一体机需要约 770-840 GB 级高带宽热内存。**  
   DeepSeek-V3/R1 原始 FP8 权重约 671 GB；加 15%-25% 的 scale、workspace、allocator、MoE routing、runtime buffer 余量后，最低热层预算约 772-839 GB。现有 84 GB Bailu 或 128/192/288 GB 级单卡 HBM 都不能“干净放下”官方 FP8 主权重。这个结论来自 DeepSeek 报告中的 671B 总参数、FP8 权重公式，以及官方/厂商 H200、MI300X、MI355X、DGX Station 等规格对照。

2. **DeepSeek 的 MLA 大幅降低 KV cache 压力，但没有消灭容量问题。**  
   对 V3/R1，MLA 每层每 token 只缓存 `kv_lora_rank + qk_rope_head_dim = 512 + 64 = 576` 个元素。低并发交互场景下，按 `32K = 32,000 tokens`、`128K = 128,000 tokens` 的十进制 GB 口径估算，32K 上下文、并发 1/2/4 的 BF16 KV 约为 2.25 / 4.50 / 8.99 GB；128K 上下文、并发 1/2/4 的 BF16 KV 约为 8.99 / 17.99 / 35.98 GB。KV 本身相对权重不是最大项，但它直接挤占热 expert、workspace 和 runtime buffer。

3. **现有 84 GB Bailu + 384 GB DDR5 + 2 TB SSD 的 950PR Lite 锚点适合验证分层推理机制，不应写成已满足 DeepSeek 671B 的最终配置。**  
   该锚点的价值是验证 KV/Prefix/Expert 热温冷对象层、NPU-SSD 直通、CPU/NPU 联合准入和 A+K cost model；它无法热层常驻 671B FP8 或 INT4 全权重。对 DeepSeek 671B，它只能作为“极低比特 + expert 分页/预取 + DRAM/SSD offload + 强约束低并发”的研发验证平台。

4. **面向单卡低并发交互，最现实的短期规格目标不是“单卡完整常驻 671B”，而是三档路线。**  
   第一档是最低可验证配置：84-128 GB 热层、384-512 GB DRAM、2-4 TB NVMe，用于验证 offload 和对象层。第二档是平衡研发配置：192-288 GB 热层、768 GB-1 TB DRAM、4-8 TB NVMe、>=200-400 GB/s NPU-CPU/host 链路，用于 4-bit/2-bit 分层 MoE 原型。第三档是下一代目标配置：400-800 GB 级 HMM/HBM coherent memory、>=800 GB/s Fabric、PIM/near-memory KV 工作集、>=1 TB DRAM 和 8-16 TB SSD，才进入“单卡/单节点接近完整大 MoE 交互服务”的讨论区间。

5. **性能判断不能只看 TOPS。**  
   Decode 的粗略激活算力只有 `2 × 37B ≈ 74 GFLOPs/token`，单用户 35 ms TPOT 只对应约 2.1 TFLOP/s 活动算力；真正容易卡住的是每 token 活动权重读取、expert miss、KV restore、DDR/SSD 回温、UB/PCIe 往返和 runtime 同步。也就是说，单卡一体机规格必须按“容量 + 带宽 + 可重叠窗口 + P95/P99”反推。

## 2. 参考资料与证据口径

### 2.1 本地项目资料

| 资料 | 本报告使用方式 |
|---|---|
| `AK 协同/模型推理估计/DeepSeek 架构与推理部署深度研究报告.md` | DeepSeek-V3/R1 架构、MLA/KV 公式、权重容量、框架支持、8×H200/MI300X 对照。 |
| `AK 协同/代表工作原文硬件拓扑映射精读笔记.md` | NEO、Tutti、Mooncake、LMCache、KTransformers、FineMoE、DALI、FluxMoE、CacheSlide、ServeGen、LLMServingSim2.0 等机制边界。 |
| `AK 协同/Deep Research 反向回顾报告 第三轮可核验版 小算力大模型推理落地与推理仿真系统构建.md` | A+K 迁移路线、vLLM-Ascend/UCM/Mooncake 工程支点、CPU/KV/SSD/P/D 的收益边界。 |
| `A_K协同技术挑战与趋势凝练_20260630_补充硬件规格需求.md` | Mini/DV100 Lite、950PR Lite、1920/HMM/PIM 的项目规格锚点和参数反推口径。 |
| `硬件规格材料_images/硬件规格材料_完整图文整理.md` | 84GB Bailu、384GB DDR5、512GB×4 SSD、UB 200GB/s、CPU-DDR5 228GB/s、CPU-SSD 40GB/s 等内部材料锚点。 |
| `一体机汇报_0616_2127_images/一体机汇报_0616_2127_图文识别.md` | 120B/200B/744B 项目包络、Mini/塔式工作站定位、TPOT 35 ms 等内部目标口径。 |

### 2.2 原文论文与系统

本报告引用的机制来自以下本地原文或官方文档路线，文件路径均在 `AK 协同/references/` 下：

| 方向 | 代表资料 | 借鉴点 | 不可误用边界 |
|---|---|---|---|
| CPU attention / warm tier | `papers/NEO__arxiv-2411.01142.pdf` | CPU 参与部分 decode attention 与 KV warm tier，靠异步 pipeline 隐藏 CPU 时间。 | 不等于 CPU 接管 dense Transformer 主干。 |
| SSD-backed KV | `papers/Tutti__arxiv-2605.03375.pdf` | SSD 冷层要做 object layout、batch I/O、GPU/NPU-native 或低 bounce path。 | 不等于普通 SSD offload；tiny random I/O 和 CPU-centric control path 会反噬。 |
| KV disaggregation | `papers/Mooncake__arxiv-2407.00079.pdf` | KVCache-centric scheduling、CPU DRAM KV pool、P/D 分离与 connector。 | 单机低并发不应照搬完整集群 P/D。 |
| KV object layer | `papers/LMCache__arxiv-2510.09665.pdf` | KV store/retrieve/lookup、GPU/CPU/SSD/remote backend、多级搬运接口。 | LMCache 是 cache layer/API，不是固定硬件拓扑。 |
| CPU/GPU MoE | `papers/KTransformers.pdf` | shared/hot experts 在 GPU，routed experts 在 CPU，AMX/NUMA/Expert Deferral/异步调度。 | AMX/AVX 结论不能直接外推到 Kunpeng SVE/SME。 |
| Expert hotness | `papers/fMoE-FineMoE__arxiv-2502.05370.pdf`、`papers/DALI__arxiv-2602.03495.pdf` | expert map、semantic hints、workload-aware assignment、prefetch/cache replacement。 | routing 可预测性不足时会 miss；CPU expert kernel 弱时收益变负。 |
| Expert paging | `papers/FluxMoE__arxiv-2604.02715v2.pdf` | expert paging、PagedTensor、KV 优先的 residency planner。 | 依赖 GPU memory mapping/event 能力；Ascend 需重测 CANN 支持。 |
| Agent prefix reuse | `papers/CacheSlide.pdf` | 相对顺序稳定但绝对位置漂移的 prompt segment 复用。 | 依赖 prompt template 和位置编码适配，不是通用 SSD direct I/O。 |
| Workload / 仿真 | `papers/ServeGen-NSDI26.pdf`、`papers/BurstGPT__arxiv-2401.17644.pdf`、`papers/LLMServingSim-2.0__arxiv-2511.07229.pdf`、`papers/ProfInfer__arxiv-2601.20755.pdf` | 真实 workload、operator profile、memory/power/system simulator、trace replay。 | 这些是证据层，不是具体 offload 策略。 |

### 2.3 外部官方资料复核

硬件与框架规格需要防止沿用旧资料，本报告以 2026-07-01 可访问的官方资料做外部对照：

| 类别 | 官方资料 | 本报告使用方式 |
|---|---|---|
| NVIDIA H200 | [NVIDIA H200](https://www.nvidia.com/en-us/data-center/h200/) | 141 GB HBM3e、4.8 TB/s 带宽，用作当前高端单卡热层上限对照。 |
| NVIDIA DGX Spark | [DGX Spark User Guide](https://docs.nvidia.com/dgx/dgx-spark/hardware.html)、[NVIDIA DGX Spark](https://www.nvidia.com/en-us/products/workstations/dgx-spark/) | 128 GB unified memory、273 GB/s、1 PFLOP FP4、个人/小团队工作站对照。 |
| NVIDIA DGX Station | [NVIDIA DGX Station](https://www.nvidia.com/en-us/products/workstations/dgx-station/) | 748 GB coherent memory、20 PFLOPS FP4、1T 参数模型口径，用作下一代单机/塔式竞品对照。 |
| AMD MI300X | [AMD MI300X](https://www.amd.com/en/products/accelerators/instinct/mi300/mi300x.html)、[AMD MI300 Series](https://www.amd.com/en/products/accelerators/instinct/mi300.html) | 192 GB HBM3、5.3 TB/s 级别对照。 |
| AMD MI325X | [AMD MI325X](https://www.amd.com/en/products/accelerators/instinct/mi300/mi325x.html) | 256 GB HBM3E、6 TB/s 级别对照。 |
| AMD MI355X | [AMD MI355X](https://www.amd.com/en/products/accelerators/instinct/mi350/mi355x.html) | 288 GB HBM3E、8 TB/s 级别对照。 |
| vLLM DeepSeek | [vLLM DeepSeek-V3/R1 Usage Guide](https://docs.vllm.ai/projects/recipes/en/latest/DeepSeek/DeepSeek-V3.html) | DeepSeek-V3/R1 同架构、FP8/FP4、服务框架对照。 |
| SGLang DeepSeek | [SGLang DeepSeek V3/V3.1/R1 Usage](https://github.com/sgl-project/sglang/blob/main/docs/basic_usage/deepseek_v3.md) | DeepSeek 专项优化、官方推荐引擎线索。 |
| TensorRT-LLM DeepSeek | [TensorRT-LLM DeepSeek-R1 on B200](https://nvidia.github.io/TensorRT-LLM/blogs/tech_blog/blog1_Pushing_Latency_Boundaries_Optimizing_DeepSeek-R1_Performance_on_NVIDIA_B200_GPUs.html) | B200 低延迟 DeepSeek-R1 性能上限对照。 |
| vLLM-Ascend UCM/KV Pool | [UCM Store Deployment](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/ucm_deployment.html)、[KV Cache Pool](https://docs.vllm.ai/projects/ascend/en/main/user_guide/feature_guide/kv_pool.html) | Ascend 上 external KV、KV pool、Mooncake backend 的工程支点。 |
| Mooncake | [Mooncake project](https://kvcache-ai.github.io/Mooncake/) | vLLM Ascend / Mooncake Store / KV connector 路线对照。 |

## 3. 借鉴的方法如何映射到单卡一体机

本报告不把所有推理技巧混成一个“魔法加速器”。不同方法解决的是不同瓶颈，硬件规格也由不同瓶颈反推。

| 方法 | 解决的瓶颈 | 对单卡一体机的硬件含义 | 关键验收指标 |
|---|---|---|---|
| 低比特量化 FP8/INT4/2-bit | 权重热层容量不足、decode 权重读取带宽过高 | 热层容量从 TB 级降到数百 GB；但需要量化 kernel、scale buffer、精度评估和 dequant 带宽 | 质量损失、TPOT、有效 HBM/Bailu 带宽 |
| MLA / 压缩 KV | 长上下文 KV 线性增长 | KV 从主容量瓶颈变为并发和恢复瓶颈；仍需 DRAM/SSD 分层 | KV GB、KV restore ms、P95/P99 |
| Prefix/KV reuse | 多轮 Agent 反复 prefill | 需要 KV object layer、prefix metadata、content hash、DRAM/SSD warm/cold tier | prefix hit ratio、TTFT、resume latency |
| MoE expert 热温冷分层 | 671B 总参数无法常驻热层，但每 token 只激活少量 expert | 热层放 dense/shared/hot experts，DRAM 放温 expert，SSD 放冷 expert；需要 expert trace 和 prefetch | expert hit rate、miss penalty、TPOT |
| CPU warm tier | 热层不足、decode 小 batch、工具/检索/metadata 需要 CPU | CPU 不是主算芯片，而是 metadata manager、I/O aggregator、DRAM KV/expert tier、工具池和 profiler host | CPU Core·s、DDR BW、同步 stall |
| SSD cold tier / NPU-SSD direct | DRAM 容量仍不足，冷 KV/expert/Prefix 需要落盘 | SSD 要看有效 I/O 粒度、队列深度、读写放大、是否绕过 CPU bounce | SSD IOPS、GB/s、tiny I/O 比例、stall |
| P/D 或 E/P/D 拆分 | Prefill 与 decode 资源画像不同 | 单机低并发不默认收益；只有长上下文、高复用、transfer 可重叠时才有价值 | transfer overlap、TTFT、TPOT、queue delay |
| Trace / what-if simulator | 规格靠拍脑袋，无法解释尾延迟 | 硬件必须暴露 NPU/CPU/DDR/SSD/UB/Fabric/功耗 counters | 仿真误差、瓶颈归因、Tasks/J |

## 4. DeepSeek-V3/R1 模型推理计算参数

### 4.1 模型结构参数

主线模型按 DeepSeek-V3/R1 671B 口径：

| 参数 | 数值 | 来源口径 |
|---|---:|---|
| 总参数 | 671B | DeepSeek 架构报告，论文/config 交叉验证。 |
| 激活参数 | 37B | DeepSeek 架构报告。 |
| 层数 | 61 | DeepSeek 架构报告。 |
| hidden size | 7168 | DeepSeek 架构报告。 |
| attention heads | 128 | DeepSeek 架构报告。 |
| MLA KV latent | `kv_lora_rank = 512` | DeepSeek 架构报告。 |
| RoPE key dim | `qk_rope_head_dim = 64` | DeepSeek 架构报告。 |
| routed experts | 256 | DeepSeek 架构报告。 |
| 每 token 激活 routed experts | 8 | DeepSeek 架构报告。 |
| shared expert | 1 | DeepSeek 架构报告。 |
| MoE 前 dense 层 | 前 3 层 dense FFN | DeepSeek 架构报告。 |

### 4.2 权重容量公式

基础公式：

```text
weight_memory = total_params × bytes_per_param × overhead_factor
```

其中 `overhead_factor` 用 1.15-1.25 表示 scale、zero point、padding、workspace、allocator、MoE routing buffer、runtime 常驻开销和安全余量。下表用十进制 GB/TB 估算，作为硬件 sizing 的初筛值。

| 模型包络 | 精度 | 原始权重 | 加 15% 余量 | 加 25% 余量 | 单卡热层判断 |
|---|---:|---:|---:|---:|---|
| 120B | FP16/BF16 | 240 GB | 276 GB | 300 GB | 84/128 GB 不可；288 GB 级接近但 KV/workspace 紧。 |
| 120B | INT4/FP4 | 60 GB | 69 GB | 75 GB | 84 GB 可验证，128 GB 更稳。 |
| 200B | FP8/INT8 | 200 GB | 230 GB | 250 GB | 192 GB 不稳，256/288 GB 级可讨论。 |
| 200B | INT4/FP4 | 100 GB | 115 GB | 125 GB | 128 GB 勉强，需控制 KV/workspace；192 GB 更稳。 |
| DeepSeek-V2 / Coder-V2 236B | FP8/INT8 | 236 GB | 271 GB | 295 GB | 288 GB 级接近，单卡仍需压 runtime/KV。 |
| DeepSeek-V2 / Coder-V2 236B | INT4/FP4 | 118 GB | 136 GB | 148 GB | 192 GB 级更合理。 |
| DeepSeek-V3/R1 671B | FP8/INT8 | 671 GB | 772 GB | 839 GB | 单卡需 800 GB 级热/一致内存才干净。 |
| DeepSeek-V3/R1 671B | INT4/FP4 | 335.5 GB | 385.8 GB | 419.4 GB | 400 GB 级热/一致内存才干净；288 GB 不够。 |
| DeepSeek-V3/R1 671B | INT2/2-bit | 167.8 GB | 192.9 GB | 209.7 GB | 192-288 GB 可研发验证，但质量和 kernel 风险高。 |
| GLM-5.2 744B 对照 | FP8/INT8 | 744 GB | 855.6 GB | 930 GB | 与 DeepSeek 671B 同级或更高。 |
| GLM-5.2 744B 对照 | INT4/FP4 | 372 GB | 427.8 GB | 465 GB | 400 GB 级仍偏紧。 |

关键含义：

- **84 GB Bailu 只能覆盖 120B INT4 级热权重验证，不能覆盖 DeepSeek 671B 全权重。**
- **192/256/288 GB 单卡 HBM/HMM 仍不能干净常驻 DeepSeek 671B INT4 全权重。**
- **400 GB 级热/一致内存是 DeepSeek 671B INT4 的下限讨论区。**
- **800 GB 级热/一致内存才是 DeepSeek 671B FP8 的下限讨论区。**

### 4.3 MLA KV cache 公式

DeepSeek-V3/R1 的 MLA KV 公式：

```text
MLA_KV = batch × seq × layers × (kv_lora_rank + qk_rope_head_dim) × bytes
       = batch × seq × 61 × (512 + 64) × bytes
```

每 token KV：

```text
BF16 KV bytes/token = 61 × 576 × 2 = 70,272 bytes ≈ 68.6 KiB
FP8  KV bytes/token = 61 × 576 × 1 = 35,136 bytes ≈ 34.3 KiB
```

低并发交互下的 KV 容量。下表按 `32K = 32,000 tokens`、`128K = 128,000 tokens` 的十进制 GB 口径计算：

| 上下文 | 并发 | BF16 KV (GB) | FP8/INT8 KV (GB) | INT4 理论 KV (GB) |
|---:|---:|---:|---:|---:|
| 32K | 1 | 2.25 GB | 1.12 GB | 0.56 GB |
| 32K | 2 | 4.50 GB | 2.25 GB | 1.12 GB |
| 32K | 4 | 8.99 GB | 4.50 GB | 2.25 GB |
| 128K | 1 | 8.99 GB | 4.50 GB | 2.25 GB |
| 128K | 2 | 17.99 GB | 8.99 GB | 4.50 GB |
| 128K | 4 | 35.98 GB | 17.99 GB | 8.99 GB |

这个表说明：在 DeepSeek 上，MLA 已把 128K KV 从不可承受量级降到可管理量级，但在热层只有 84 GB 时，4 并发 128K 的 BF16 KV 仍会吃掉约 36 GB，明显挤压热权重、hot experts、workspace 和 runtime buffer。

### 4.4 MoE expert 参数与热层压力

V3/R1 单个 routed expert 按 gated FFN 估算：

```text
single_expert_params ≈ 3 × hidden_size × expert_intermediate_size
                     = 3 × 7168 × 2048
                     ≈ 44.0M params
```

单层激活 expert 参数：

```text
active_expert_params/layer ≈ (8 routed + 1 shared) × 44.0M
                           ≈ 396M params
```

单层全部 routed experts：

```text
all_routed_experts/layer ≈ 256 × 44.0M
                         ≈ 11.27B params
```

这解释了为什么 DeepSeek 671B 的单卡问题不是“每 token 算不动”，而是“总 expert 权重无法常驻热层”。单卡一体机必须把 expert 变成状态对象：热 experts 常驻 Bailu/HBM/HMM，温 experts 在 DRAM，冷 experts 在 SSD，runtime 根据 routing trace、semantic hint、workflow stage 和 next-use probability 预取。

### 4.5 Decode 计算与带宽预算

粗略活动 FLOPs：

```text
decode_flops/token ≈ 2 × active_params + attention_history_term
                   ≈ 2 × 37B
                   ≈ 74 GFLOPs/token
```

按目标 TPOT 折算：

| TPOT | 单用户 tok/s | 活动算力下界 | FP8 活动权重读取压力粗估 | INT4 活动权重读取压力粗估 |
|---:|---:|---:|---:|---:|
| 20 ms | 50.0 | 3.70 TFLOP/s | 1850 GB/s | 925 GB/s |
| 35 ms | 28.6 | 2.11 TFLOP/s | 1057 GB/s | 529 GB/s |
| 50 ms | 20.0 | 1.48 TFLOP/s | 740 GB/s | 370 GB/s |
| 63 ms | 15.9 | 1.17 TFLOP/s | 587 GB/s | 294 GB/s |

表中活动权重读取压力是保守粗估：把每 token 需要触达的 37B 激活参数近似视为一次权重流式读取。真实框架会通过 batching、expert grouping、kernel fusion、cache locality 和量化 kernel 改善有效带宽，但这个估算足够说明一点：**35 ms TPOT 这类目标更多是 HBM/Bailu/HMM 带宽、expert hit、KV/expert restore 和调度问题，不是 TOPS 问题。**

### 4.6 热层总预算公式

单卡一体机热层预算应写成：

```text
hot_memory_budget =
  resident_weights
+ hot_KV
+ workspace
+ hot_expert_cache
+ activation_buffer
+ runtime_buffer
+ allocator_reserved
```

建议用以下工程下界：

| 项 | DeepSeek 671B 单卡分层时的含义 |
|---|---|
| resident_weights | 不可能是全部 FP8/INT4 权重；应是 dense 层、attention、shared experts、hot routed experts、LM head、embedding 和当前/下一层 expert working set。 |
| hot_KV | 低并发 32K 可按 2-9 GB 估；128K 可按 9-36 GB 估。 |
| workspace | MoE dispatch/combine、MLA、dequant、FlashMLA/FlashAttention、continuous batching 需要留出。 |
| hot_expert_cache | 取决于 expert hotness 和 prefetch 策略；应作为显式预算，不应挤占 KV。 |
| runtime_buffer | vLLM/SGLang/TRT-LLM/MindIE/vLLM-Ascend allocator、graph/capture、metadata 常驻开销。 |
| allocator_reserved | 建议 15%-25% 全局余量，不要用 100% 标称容量做设计。 |

## 5. 单卡一体机硬件规格反推

### 5.1 GPU/NPU/HBM 或 Bailu 热层

| 目标 | 最低可验证规格 | 推荐规格 | 推导依据 | 欠配风险 |
|---|---|---|---|---|
| 120B INT4/FP4 低并发交互 | 84 GB Bailu/HBM | 128 GB 级热层 | 120B INT4 + 15%-25% 约 69-75 GB，剩余空间给 KV/workspace。 | 84 GB 下 128K、多并发、workspace 会挤爆。 |
| 200B INT4/FP4 | 128 GB 级热层 | 192 GB 级热层 | 200B INT4 + 15%-25% 约 115-125 GB。 | 128 GB 基本没有 KV/workspace 余量。 |
| DeepSeek 671B INT4 全常驻 | 400 GB 级热/一致内存 | 512 GB 级热/一致内存 | 671B INT4 + 15%-25% 约 386-419 GB。 | 288 GB 不足，需要 expert 分层/offload。 |
| DeepSeek 671B FP8 全常驻 | 800 GB 级热/一致内存 | 900 GB+ 热/一致内存 | 671B FP8 + 15%-25% 约 772-839 GB。 | 任何 192/288/400 GB 单卡都不能干净 fit。 |
| DeepSeek 671B 分层研发 | 192-288 GB 热层 | 288-400 GB 热/一致内存 | 只常驻 dense/shared/hot experts/current experts，DRAM/SSD 承接温冷 expert。 | expert miss 和回温带宽决定 TPOT/P99。 |

与外部硬件对照：

- H200 单卡 141 GB HBM3e / 4.8 TB/s，不足以常驻 DeepSeek 671B INT4/FP8，但可作为 120B-200B 低比特或分层机制对照。
- MI300X 单卡 192 GB HBM3 / 5.3 TB/s、MI325X 256 GB HBM3E / 6 TB/s、MI355X 288 GB HBM3E / 8 TB/s，仍不足以常驻 DeepSeek 671B INT4 全权重，但适合做更强单卡分层 MoE 原型。
- DGX Station 748 GB coherent memory、20 PFLOPS FP4 是竞品塔式单机方向；它接近 DeepSeek 671B FP8 容量下限，但还要看高带宽部分与 LPDDR 部分的有效访问路径。

### 5.2 CPU

CPU 在本报告中不是 dense 主算设备，而是五类角色：

1. host / scheduler / admission control；
2. metadata manager / state object ledger；
3. I/O aggregator / DRAM-SSD warm/cold tier 管理；
4. KV warm tier / expert warm tier / prefetch planner；
5. 工具、检索、文档解析、编译测试、sandbox、media pipeline。

规格建议：

| 形态 | CPU 建议 | 理由 | 验证指标 |
|---|---|---|---|
| 最低可验证配置 | 32-64 cores，明确隔离主控、推理 runtime、工具/sandbox core pool；要求 SVE/向量能力可测 | 对标 950PR Lite 64 核 CPU 口径，支持 16 核主控 + 48 核沙箱一类隔离。 | CPU runnable queue、tool_queue_time、CPU Core·s、runtime overhead。 |
| 平衡研发配置 | 64-96 cores，高内存带宽 NUMA，SVE/SME 或等价向量矩阵能力，支持 pinned memory/异步 DMA 管理 | MoE expert prefetch、KV restore、工具链和 profiler 同时运行。 | DDR BW、expert fallback latency、sync stall、P95 JCT。 |
| 下一代目标配置 | CPU 与 NPU/HMM/Fabric 有硬件级低延迟队列、可观测 counters 和可控 QoS | CPU 控制面要进入硬件规格，而不是仅靠 OS 调度。 | admission accuracy、queueing delay、Tasks/J。 |

边界：KTransformers 证明 CPU/GPU hybrid MoE 有价值，但其原文强依赖 Intel AMX/AVX-512、NUMA-aware placement、CUDA Graph/FlashInfer 等条件。Kunpeng + Ascend 需要重新测 SVE/SME expert kernel、CANN stream/callback、NPU-CPU 异步同步，不能直接继承 AMX 结论。

### 5.3 DRAM warm tier

DRAM 的角色是温 KV、温 experts、冷权重 staging、Prefix/KV metadata、object ledger、工具/检索/沙箱工作集。

| 目标 | 最低可验证规格 | 推荐规格 | 推导依据 |
|---|---:|---:|---|
| 120B/200B 原型 | 64-384 GB DDR5 | 384-512 GB DDR5 | Mini 64 GB DDR 可做小原型；950PR Lite 384 GB 是更合理的温层锚点。 |
| DeepSeek 671B 分层研发 | 384 GB DDR5 | 768 GB-1 TB DDR5 | INT4 总权重约 335.5 GB；如果热层只有 192-288 GB，DRAM 需承接大部分温专家和 staging。 |
| DeepSeek/GLM 744B 包络 | 768 GB DDR5 | 1-2 TB DDR5 | 744B INT4 原始约 372 GB，且 1M 上下文和工具/沙箱会增加温层压力。 |

带宽建议：

| 规格项 | 下限 | 推荐 | 说明 |
|---|---:|---:|---|
| CPU-DDR5 读写带宽 | 228 GB/s 锚点 | 300-500 GB/s+ | 950PR Lite 已有 228 GB/s 口径；DeepSeek 分层 expert 回温会更吃带宽。 |
| DDR 到 NPU/Bailu 回温 | 200 GB/s UB 锚点 | 400 GB/s+ 或 direct/Fabric path | 如果每次 expert miss 需要数 GB 级回温，200 GB/s 只能承受少量 miss。 |
| pinned / page-locked memory | 必须支持 | 必须支持并可观测 | KV/expert offload 需要稳定 DMA buffer。 |

### 5.4 SSD/NVMe cold tier

SSD 的角色是冷 KV、冷 experts、Prefix object、checkpoint、工具中间文件和多模态临时对象。

| 目标 | 最低可验证规格 | 推荐规格 | 说明 |
|---|---:|---:|---|
| 机制验证 | 2 TB NVMe，顺序聚合带宽 10-40 GB/s | 4 TB NVMe，聚合带宽 40 GB/s | 对应 Mini 1 TB / 10 GB/s 和 950PR Lite 2 TB / 40 GB/s 锚点。 |
| DeepSeek 分层研发 | 4-8 TB NVMe/SLC，聚合 40-80 GB/s | 8 TB+，支持 high queue depth、低尾延迟、QoS | 冷 expert、冷 KV、checkpoint 和工具 I/O 会共用。 |
| 下一代目标 | 8-16 TB，NPU-SSD direct 或低 bounce object path | 16 TB+，支持对象化 KV/expert layout、读写分离、耐久分层 | Tutti 说明账面带宽不够，关键是 I/O 粒度和控制路径。 |

设计约束：

```text
link_budget ≥ restore_bytes / hidden_latency_window
```

如果一次 cold expert miss 需要恢复 1 GB，而可隐藏窗口只有 20 ms，则所需有效带宽是 50 GB/s。若 SSD 实际因 tiny random I/O 只能给几 GB/s，TPOT/P99 会直接恶化。Tutti 的经验说明，应优先把冷 KV/expert 组织成对象化、批量化、可预取的数据块，避免 CPU bounce buffer 和每次 I/O 的 CPU control path。

### 5.5 PCIe / UB / Fabric / NPU-SSD direct

| 链路 | 现有锚点 | DeepSeek 分层需求 | 欠配风险 |
|---|---:|---:|---|
| NPU/Bailu 内部带宽 | 1 TB/s | 35 ms TPOT 下 INT4 活动读取粗估约 529 GB/s；FP8 粗估约 1057 GB/s | 1 TB/s 对 FP8 decode 很紧，对 INT4 更现实。 |
| NPU-CPU UB | 200 GB/s | 建议 200 GB/s 为验证下限，400 GB/s+ 更适合 DeepSeek 分层 expert/KV 回温 | expert miss、KV restore 和 metadata 同步会进入关键路径。 |
| CPU-DDR | 228 GB/s | 建议 300-500 GB/s+ | 温 expert 和 KV 回温与工具/沙箱抢带宽。 |
| CPU-SSD | 40 GB/s | 40 GB/s 为验证下限；NPU direct 或 80 GB/s+ 更稳 | 冷层恢复被 SSD/CPU bounce 限制。 |
| Fabric/HMM | >800 GB/s 方向 | 下一代建议 >=800 GB/s，一致内存/对象语义要明确 | 只增容量不增有效带宽会变成慢速大内存。 |

### 5.6 功耗、散热与形态

功耗不应只按峰值 TOPS 反推。单卡一体机低并发交互要看：

- NPU/GPU 常驻功耗；
- CPU 工具池和沙箱峰值；
- DRAM/SSD 持续读写功耗；
- NPU-SSD direct 或 Fabric 传输功耗；
- 长时间 agent workflow 的 idle/pinned state 功耗；
- 温控降频后 P95/P99 是否恶化。

三档建议：

| 档位 | 功耗/散热口径 | 适用目标 |
|---|---|---|
| Mini 原型 | 200-300 W 级 | 120B INT4、200B 低比特、工具链和 A+K placement 验证；对标 DGX Spark 形态。 |
| 塔式研发 | 1-2 kW 级 | DeepSeek/GLM 大 MoE 分层验证、低并发长上下文、CPU 工具池和 SSD cold tier；对标 DGX Station 形态。 |
| 下一代 SoC/一体机 | 1.5-3 kW 级，需液冷或强风冷 | 400-800 GB HMM/HBM、PIM/near-memory、低尾延迟大 MoE。 |

### 5.7 可观测计数器

如果目标是“硬件参数可由 trace 反推”，以下 counters 应进入平台规格，而不是事后工具：

| 组件 | 必要 counters |
|---|---|
| NPU/GPU | compute util、HBM/Bailu occupancy、HBM bandwidth、copy engine、stream wait、kernel timeline、MoE dispatch/combine bytes。 |
| CPU | per-pool CPU util、runnable queue、context switch、SVE/SME kernel latency、tool_queue_time、sandbox occupancy。 |
| DRAM | bandwidth、page fault、pinned pool、NUMA locality、KV/expert bytes in/out。 |
| SSD/NVMe | queue depth、IOPS、read/write size distribution、tail latency、read/write amplification、thermal throttle。 |
| UB/PCIe/Fabric | bytes by object type、latency, retry/error、DMA setup cost、overlap ratio。 |
| Runtime | TTFT、TPOT/ITL、JCT、prefix hit、KV restore ms、expert hit/miss、eviction reason、recompute reason。 |
| Power | NPU/CPU/DRAM/SSD/Fabric power、temperature、throttling event、energy/token、Tasks/J。 |

## 6. 推荐配置表

### 6.1 三档配置建议

| 档位 | 组件 | 规格建议 | 能做什么 | 不能承诺什么 |
|---|---|---|---|---|
| 最低可验证配置 | NPU/GPU 热层 | 84-128 GB Bailu/HBM，>=1 TB/s 热层带宽 | 验证 120B INT4、DeepSeek 分层机制切片、KV/Prefix object、低并发 trace。 | 不能完整常驻 DeepSeek 671B INT4/FP8。 |
| 最低可验证配置 | CPU | 32-64 cores，主控/沙箱/推理 runtime 隔离，SVE/向量能力可测 | 工具链、metadata、KV/expert warm tier 管理。 | 不能证明 CPU expert fallback 必然正收益。 |
| 最低可验证配置 | DRAM | 384-512 GB DDR5，>=228 GB/s | 温 KV、温 expert、staging、工具/沙箱。 | 不能覆盖 671B 大量 expert 长时间温驻留。 |
| 最低可验证配置 | SSD | 2-4 TB NVMe，10-40 GB/s 聚合读写 | 冷 KV、冷 prefix、checkpoint、I/O 粒度实验。 | 不能只靠账面带宽保证 P99。 |
| 最低可验证配置 | 链路 | UB/PCIe >=200 GB/s，支持 pinned memory 和异步 copy | 验证 CPU/NPU offload 成本模型。 | 不适合高频 expert miss。 |
| 平衡研发配置 | NPU/GPU 热层 | 192-288 GB HBM/HMM/Bailu，5-8 TB/s 级更优 | DeepSeek 671B 2-bit/4-bit 分层 MoE 原型，120B/200B 较稳。 | 仍不能完整常驻 DeepSeek 671B INT4。 |
| 平衡研发配置 | CPU | 64-96 cores，高内存带宽，强 SVE/SME/向量，硬隔离工具池 | expert prefetch、工具链、KV restore、A+K runtime。 | 如果 expert fallback kernel 弱，仍只能做 metadata/prefetch。 |
| 平衡研发配置 | DRAM | 768 GB-1 TB DDR5，300-500 GB/s+ | 大量温 expert、KV pool、UCM/Mooncake/LMCache 后端。 | DRAM 带宽仍远低于 HBM，不可当热层。 |
| 平衡研发配置 | SSD | 4-8 TB NVMe/SLC，40-80 GB/s，有 QoS 和高 QD | 冷 expert/KV、checkpoint、长 agent workflow。 | 没有 object layout/direct path 时会被 tiny I/O 反噬。 |
| 平衡研发配置 | 链路 | UB/Fabric 400 GB/s+，NPU-SSD direct 原型 | 降低 DDR/SSD 回温尾延迟。 | direct path 也必须有对象布局和调度。 |
| 下一代目标配置 | 高带宽一致内存 | 400-800 GB HMM/HBM/coherent memory，>=800 GB/s Fabric，热区多 TB/s | DeepSeek 671B INT4 到 FP8 的单节点完整性讨论。 | 若高容量部分带宽低，只能当温层。 |
| 下一代目标配置 | PIM/near-memory | 30 GB+ KV/activation/expert working set，>8 TB/s 近存访问 | 稀疏 gather/reduce、KV/activation 高频访问、低时延恢复。 | 需要编译器、数据布局、一致性语义。 |
| 下一代目标配置 | DRAM/SSD | 1-2 TB DRAM，8-16 TB SSD/SLC，direct/object path | 长上下文、多 agent、冷 expert/Prefix、checkpoint。 | 仍需 trace 决定是否收益为正。 |

### 6.2 硬件需求字段版

| component | minimum_spec | recommended_spec | reasoning_formula | borrowed_method | risk_if_underprovisioned | validation_metric |
|---|---|---|---|---|---|---|
| 热层 HBM/Bailu/HMM | 84-128 GB for 120B/机制验证 | 400 GB for INT4 671B；800 GB for FP8 671B | `resident_weights + hot_KV + workspace + expert_cache + runtime` | FluxMoE residency、KTransformers hot/shared experts | OOM、频繁 expert miss、TPOT 抖动 | HBM occupancy、expert hit、TPOT P95 |
| 热层带宽 | 1 TB/s | 5-8 TB/s；下一代多 TB/s hot region | `active_weight_bytes / TPOT` | MLA/FlashMLA、grouped MoE | decode memory-bound、SM/AIV 空转 | effective bandwidth、stall |
| CPU | 32-64 cores | 64-96 cores + strong SVE/SME + isolated pools | `tool_core_s + runtime_core_s + prefetch_core_s` | NEO scheduler、KTransformers CPU expert | runtime overhead、工具反压、fallback 负收益 | CPU Core·s、queue time |
| DRAM | 384 GB / 228 GB/s | 768 GB-1 TB / 300-500 GB/s+ | `warm_KV + warm_expert + staging + tools` | LMCache/UCM warm tier | 温层不足、host OOM、restore 慢 | DDR BW、host OOM、restore ms |
| SSD/NVMe | 2 TB / 40 GB/s | 4-8 TB / 40-80 GB/s + QoS + high QD | `cold_state / retention_window` and `restore_bytes / hidden_window` | Tutti、SolidAttention、Bidaw | tiny I/O、P99、写放大、热降频 | IOPS、tail latency、read size |
| UB/PCIe/Fabric | 200 GB/s | 400-800 GB/s+ | `restore_bytes / overlap_window` | Mooncake connector、NIXL、vLLM-Ascend | KV/expert transfer 进入关键路径 | bytes/token、overlap ratio |
| NPU-SSD direct | 原型可选 | 对象化 direct path + batch I/O | `cold_object_restore_ms < slack_window` | Tutti GPU-centric object I/O | CPU bounce 和 control path 反噬 | CPU bypass rate、stall |
| 可观测性 | 软件 profiler | 硬件 timestamp + counters + run card | `simulation_error = measured - predicted` | ProfInfer、LLMServingSim2.0、ServeGen | 不能反推规格，只能拍脑袋 | 仿真误差、bottleneck attribution |

## 7. 风险边界

1. **CPU 不接管 dense 主干。**  
   CPU 的有效角色是 host/scheduler、metadata manager、I/O aggregator、KV/expert warm tier、fallback expert、工具/检索/media 和 profiler host。除非有明确的 SVE/SME/AMX 类算力、可批处理 shape 和可重叠窗口，否则 CPU 接管主干 attention/FFN 通常会拖慢。

2. **SSD offload 不等于收益。**  
   SSD-backed KV/expert 只有在 object layout、I/O 粒度、队列深度、direct path、slack-aware scheduling 和低 CPU control overhead 同时成立时才可能收益为正。Tutti 的关键教训是：tiny random I/O、CPU-centric control path、DRAM-HBM bounce copy 会让 SSD 账面带宽失效。

3. **P/D 拆分不默认收益。**  
   低并发、短上下文、低 prefix reuse、KV transfer 不可重叠时，P/D 拆分会带来纯额外开销。单卡一体机应先做 P/D-colocated、prefix/KV object 和 transfer overlap 观测，再决定是否拆分。

4. **KTransformers 的 AMX 经验不能直接外推 Kunpeng。**  
   A+K 必须实测 Kunpeng SVE/SME expert kernel、CANN event/stream、NPU-CPU sync 和 DDR 带宽。否则 CPU expert fallback 可能只是把 miss penalty 从“搬运慢”换成“host compute 慢”。

5. **DGX Spark / DGX Station 是竞品形态对照，不是 A+K 规格自动答案。**  
   Spark 的 128 GB unified memory 更适合 70B/120B/200B 低比特开发；Station 的 748 GB coherent memory 接近大模型单机方向，但仍要区分 HBM 与 LPDDR 的有效带宽、软件栈、功耗和价格。

6. **内部 744B/1M/TPOT 35 ms 目标不能直接套到 DeepSeek 671B。**  
   GLM-5.2 和 DeepSeek 都是大 MoE，但模型结构、KV 结构、上下文目标、量化格式、Index/KV cache 和框架成熟度不同。本报告只把 744B/1M 作为项目包络对照。

## 8. 验证计划

### 8.1 算术校验

必须固定一份小脚本或表格，复算：

- 权重：120B / 200B / 236B / 671B / 744B 在 BF16、FP8、INT4、INT2 下的 raw + 15%-25% 余量。
- KV：DeepSeek 32K / 128K、并发 1/2/4、BF16/FP8/INT4。
- 带宽：TPOT 20/35/50/63 ms 下的活动权重读取压力和活动算力。
- 热层预算：resident weights、hot KV、workspace、expert cache、runtime buffer 分项。

### 8.2 微基准

| 微基准 | 目的 | 输出 |
|---|---|---|
| NPU/GPU matmul by shape | prefill/decode/MLA/MoE operator latency | shape-latency table |
| Kunpeng SVE/SME expert kernel | 判断 CPU fallback 是否可能正收益 | expert latency、tokens/s、energy |
| NPU-CPU copy / UB | 计算 KV/expert restore 是否可重叠 | H2D/D2H latency、GB/s、overlap |
| DDR streaming / random | 温 expert/KV 的实际可用带宽 | GB/s、P95 latency |
| SSD object I/O | 识别 tiny I/O 与 queue depth 边界 | IOPS、GB/s、tail latency |
| NPU-SSD direct path | 验证是否减少 CPU bounce 和 stall | CPU bypass rate、stall ratio |

### 8.3 端到端场景

| 场景 | 配置 | 指标 |
|---|---|---|
| DeepSeek 671B 模拟包络 | 低比特分层权重、32K/128K、并发 1/2/4 | TTFT、TPOT、P95/P99、expert hit、KV restore |
| 120B 办公助手 | 120B INT4、RAG/文档工具、多轮 | resume latency、prefix hit、CPU Core·s、Tasks/J |
| 200B 本地模型 | 200B 低比特、权重预取 | prefetch hit、DDR bytes/token、TPOT |
| 744B GLM 对照 | 1M context 只做包络仿真 | KV GB·s、restore ms、容量缺口 |
| 多模态流水 | 14B/27B + VAE/codec/postprocess | 首帧时延、media CPU、SSD bytes |

### 8.4 扰动实验

每个结论必须绑定扰动，而不是只看利用率：

- 限算力：降低 NPU/GPU clock 或并发，看 TPOT 变化。
- 限热层容量：缩小 KV/expert cache，看 hit/miss 和 P99。
- 限 UB/PCIe：人为限速，测 restore 对 TPOT 的贡献。
- 限 DDR：限带宽或改变 NUMA，测 warm tier 敏感度。
- 限 SSD：改变 queue depth、I/O 粒度、并发读写，测 tiny I/O 反噬。
- 限 CPU：缩小工具池/metadata 线程，测 runtime overhead。
- 限功耗：设置 power cap，测 Tasks/J 与 P95/P99。

## 9. 最终规格建议

### 9.1 当前 950PR Lite 锚点的定位

现有锚点：

```text
L1: 84GB Bailu, 1TB/s
L2: 384GB DDR5, CPU-DDR5 228GB/s
L3: 512GB × 4 SSD, CPU-SSD 40GB/s
NPU-CPU: UB 200GB/s
```

判断：

- 对 120B INT4 和 200B 低比特预取验证，有现实意义。
- 对 DeepSeek 671B，不能全权重常驻；只能验证分层 expert/KV/Prefix、offload、NPU-SSD direct、A+K profiler 与 what-if simulator。
- 如果要写成 DeepSeek 671B 单卡方案，必须显式加前提：极低比特、非全权重热驻留、热 expert 预测、温/冷层回温可重叠、低并发、可接受质量损失，并且需要实测验证。

### 9.2 面向 DeepSeek 671B 的单卡一体机推荐目标

| 部件 | 研发可行目标 | 更稳妥目标 | 理由 |
|---|---:|---:|---|
| 热层 HBM/Bailu/HMM | 288-400 GB，5-8 TB/s | 512-800 GB，>8 TB/s 等效热区 | INT4 常驻需要约 386-419 GB；FP8 需要约 772-839 GB。 |
| DRAM warm tier | 768 GB-1 TB，300-500 GB/s | 1-2 TB，500 GB/s+ | 温 experts、KV、staging、工具池同时存在。 |
| SSD cold tier | 4-8 TB，40-80 GB/s，QoS | 8-16 TB，object/direct path | 冷 expert/KV/Prefix/checkpoint 需要低尾延迟。 |
| NPU-CPU/Fabric | 400 GB/s+ | 800 GB/s+，支持低 bounce direct | 200 GB/s 是验证下限，不是大 MoE 分层舒适区。 |
| CPU | 64-96 cores，强 SVE/SME，可隔离 | 96 cores+，硬件队列/QoS/counters | CPU 是控制面、I/O 聚合、工具池和 warm tier manager。 |
| PIM/near-memory | 可选 30 GB KV/activation 工作集 | 30-100 GB，>8 TB/s 有效带宽 | 面向长上下文和 sparse gather/reduce。 |
| 功耗散热 | 1-2 kW 塔式 | 1.5-3 kW，液冷/强风冷 | 大热层 + DRAM/SSD + CPU 工具池需要持续功耗余量。 |

### 9.3 一句话判断

如果目标是“在单卡一体机上研究 DeepSeek 671B 低并发推理”，最低路径是 **84/128 GB 热层 + 384 GB DRAM + SSD 的 A+K 分层原型**；如果目标是“真正让 DeepSeek 671B 成为可用的单卡/单节点交互服务”，硬件方向应上升到 **400 GB 级 INT4 热/一致内存或 800 GB 级 FP8 热/一致内存，加 1 TB 级 DRAM、对象化 SSD cold tier、400-800 GB/s 级 Fabric/UB 和完整可观测性**。现阶段不能把 84 GB Bailu 方案写成 DeepSeek 671B 的最终承载方案。

## 10. AI 辅助披露

本报告使用 AI 辅助完成资料整理、公式复算和写作。核心数字来自本地已核验报告、原文 PDF 精读笔记、项目硬件规格材料和 2026-07-01 外部官方资料复核。所有容量、带宽和性能数值除特别注明官方观测外，均为工程估算，需通过实际 hardware profile、runtime trace 和扰动实验确认。
