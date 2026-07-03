# 以 GLM-5.2 为例的大模型推理计算流与异构协同调研说明

## 1. 说明定位

本说明不做算子级实现拆解，也不逐项展开矩阵形状、kernel 调度和 cache block 布局，而是从方案调研角度说明：以 GLM-5.2 这类大规模 MoE 长上下文模型为例，模型推理在标准 GPU/NPU 框架下如何流转，prefill 与 decode 两个阶段对硬件资源的压力有何不同，以及 NEO、KTransformers 等代表性工作如何改变 CPU 与 GPU/NPU 的分工。

GLM-5.2 适合作为分析样例，原因是它不是普通 dense decoder-only 模型，而是同时具备大 MoE、稀疏注意力、长上下文、压缩 KV 和 IndexShare 等特征。公开资料显示，GLM-5.2 是 744B 级模型，活动参数约 39B–40B，配置中包含 `glm_moe_dsa`、78 层、256 个 routed experts、top-8 expert 激活、1 个 shared expert，以及 1M context 等架构线索。

因此，用 GLM-5.2 做方案分析时，不应只看“总参数能不能放进显存”，而应重点看三类资源压力：一是 MoE 专家权重如何放置与预取，二是 KV / Prefix / Context 状态如何分层和恢复，三是 prefill 与 decode 阶段如何分别占用算力、带宽和内存。

## 2. GLM-5.2 的模型架构可简化为三条主链路

从调研视角看，GLM-5.2 的推理链路可以简化为三部分。

第一是主干计算链路。输入 token 经过 embedding 后进入 78 层 Transformer block，每层包括归一化、注意力、残差、MLP 或 MoE。模型的 dense 投影、attention 主计算、shared expert、hot expert 和输出头仍然是高密度计算，应优先放在 GPU/NPU 的近端高带宽内存中执行。

第二是长上下文状态链路。GLM-5.2 采用 MLA / 压缩 KV 路线，并叠加 DSA / IndexShare，因此 KV cache 不再适合简单按传统 full K/V head 公式估算。公开配置可反推出 GLM-5.2 的 MLA cache 宽度远小于传统 K/V cache，这也是其支持长上下文的重要基础。 但即使 KV 被压缩，长上下文、多轮会话和多 Agent 场景仍会持续放大 KV、Prefix、Context 和索引状态的管理压力。

第三是 MoE 专家链路。GLM-5.2 后续大部分层是 MoE 结构，每个 token 只激活部分 routed experts，但总专家权重规模巨大。这里的核心矛盾不是 router 计算本身，而是哪些专家常驻近端内存、哪些专家放在 DDR/SSD 温冷层、专家 miss 时如何预取或回取，以及 expert hit rate 如何影响 decode 阶段的 TPOT 和尾延迟。

## 3. 标准 GPU/NPU 推理框架下的计算流

在标准 vLLM / SGLang / TensorRT-LLM / MindIE 类推理框架下，可以先把 GLM-5.2 的计算流理解为一条“GPU/NPU 主算 + HBM 近端状态 + CPU 控制面”的基线。

请求进入系统后，CPU 侧 runtime 负责 tokenizer、chat template、请求排队、batch 组织、采样控制和 cache metadata 管理；GPU/NPU 侧负责 embedding、attention、MoE、lm_head 等模型主计算；HBM/NPU memory 中保存热权重、活动 KV、activation、workspace 和部分专家权重；CPU DDR 和 SSD 在标准纯 GPU/NPU 路径中一般只作为模型加载、host staging 或外部缓存补充，不直接进入每 token 的热路径。

prefill 阶段主要处理完整 prompt。这个阶段的特点是输入序列长、矩阵规模大、并行度较高，更接近 compute-bound，主要消耗 GPU/NPU 的矩阵计算能力、HBM 带宽和 attention kernel 能力。硬件层面对照地图也明确区分了 prefill 与 decode：prefill 是大矩阵和长序列并行，主要吃加速器计算核心、HBM 带宽和 attention 算法。

decode 阶段则是逐 token 迭代。每生成一个新 token，都要读取历史 KV、访问活动权重、执行 attention、经过 MoE router 和被激活的 experts，再输出 logits。这个阶段单步计算粒度小，但状态访问频繁，因此容易从 compute-bound 转成 memory-bound 或 scheduler-bound。硬件地图中也指出，decode 是单 token 迭代、小 batch、频繁读 KV，容易变成内存和调度瓶颈。

## 4. 标准基线的主要瓶颈

标准纯 GPU/NPU 推理路径的优势是链路短、同步少、实现成熟，但在 GLM-5.2 这类模型上会遇到三个主要瓶颈。

第一，近端内存被多类状态共同挤压。HBM 中不仅要放权重，还要放 KV cache、activation、workspace、MoE expert cache 和 prefix metadata。硬件地图明确指出，HBM 里真正争空间的不是单一对象，而是 KV、expert、weight、activation/workspace、prefix metadata 等一组状态。

第二，MoE expert 与 KV cache 会互相争近端容量。GLM-5.2 这种大 MoE 模型的专家总量很大，但每个 token 只激活部分 experts，因此专家更适合按热度分层：热专家靠近 GPU/NPU，温专家放 CPU DDR，冷专家放 SSD 或远端存储。硬件地图也把 MoE expert 的典型硬件动作概括为 hot experts 常驻、warm experts 放 CPU/DRAM、cold experts 放 SSD/remote。

第三，跨层搬运可能反噬性能。只要热路径上出现频繁 CPU 同步、PCIe/UB 往返、DDR 回取或 SSD 小 I/O，decode 的 TPOT 和 P95/P99 都会放大。因此，任何 offload 机制都必须回答三个问题：offload 的对象是什么、跨了哪条硬件链路、搬运是否能被主计算流水线隐藏。

## 5. NEO 路线：把部分 decode attention 与 KV 留在 CPU 侧

NEO 的核心启发不是“CPU 全面加速推理”，而是：在显存受限、decode 较长、CPU attention 可与 GPU 主计算重叠的情况下，可以把一部分请求的 KV 和 decode attention 留在 CPU/DDR 侧处理，从而减少 GPU HBM 压力并扩大有效 batch。硬件地图中对 NEO 的概括是：GPU 保留线性层和主算，CPU 放部分 decode attention 与 KV 状态，通过 asymmetric GPU-CPU pipeline 和 load-aware scheduling 平衡 CPU/GPU。

放到 GLM-5.2 场景里，NEO 路线主要对应 KV / attention 方向。标准框架中，decode attention 每步都在 GPU/NPU 上读取历史 KV；NEO 式路径则将部分请求的 KV 保存在 CPU DDR，并让 CPU 承接对应的 decode attention 子路径。GPU/NPU 继续执行主干 projection、MoE、lm_head 和其他高密度计算。

这条路线适合回答一个方案问题：当 HBM 不足以同时容纳足够多的活动 KV 和 expert cache 时，能否让 Kunpeng DDR 作为 KV warm tier，并让 CPU 承接一小部分可重叠的 attention 子计算？

但这条路线的边界也很明确。CPU 不能被写成主算替代；它只适合承接可重叠、低频、内存带宽型或状态相关的子路径。Deep Research 也明确指出，CPU 参与推理的有效角色更窄但更清晰，包括 metadata manager、I/O aggregator、KV warm tier、expert warm tier、小矩阵/稀疏/异常路径和 profiler/simulator host；CPU 直接接管主干 attention/FFN 通常不成立。

## 6. KTransformers 路线：把 MoE 专家作为分层状态管理对象

KTransformers 的启发更直接面向 GLM-5.2 的 MoE 部分。它不是简单“把专家权重放到 CPU”，而是把 shared/hot experts 保留在 GPU，routed experts 放到 CPU DRAM，并通过 CPU expert kernel、异步调度和 overlap 机制减少专家搬运造成的停顿。硬件地图也将 KTransformers 概括为 GPU VRAM + CPU DDR + CPU SIMD/AMX + NUMA + 异步调度的 MoE hybrid 路线。

对 GLM-5.2 这类 744B 级 MoE 模型来说，KTransformers 的价值在于把专家权重从“必须全部近端常驻”的压力中解放出来。标准 GPU/NPU 路径中，若尽量把所有专家权重放在 HBM，会很快触顶；如果每次 expert miss 都从 CPU/SSD 拉取，又会被链路带宽和同步成本卡住。因此，调研阶段应把 MoE expert 看成一类独立状态对象，研究其热度、命中率、预取窗口、miss penalty 和可降精度空间。

这条路线在 A+K 上的合理表达是：Ascend NPU 保留 non-expert 主干、shared expert、hot routed experts 和当前 token 的热路径计算；Kunpeng DDR 承接 warm routed experts、expert index、routing trace 和预取计划；SSD/SLC 承接 cold experts。CPU 是否直接执行部分低频 expert，需要等 Kunpeng SVE/SME microbenchmark 证明收益，不能直接继承 x86 AMX 论文结论。硬件地图也明确提醒，KTransformers 强依赖 CPU ISA 和内存带宽，Kunpeng SVE 需要独立验证。

## 7. 三类路径的横向对比

| 方案路径             | 主算位置                                                     | 状态放置                                                     | CPU 角色                                                     | 适合解决的问题                                | 主要风险                                                     |
| -------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | --------------------------------------------- | ------------------------------------------------------------ |
| 标准 GPU/NPU 推理    | GPU/NPU 承担 attention、MLP/MoE、lm_head                     | 权重、KV、activation、workspace、hot experts 尽量放 HBM/NPU memory | tokenizer、scheduler、sampler、metadata                      | 基线性能、实现简单、热路径短                  | HBM 被权重、KV、experts 共同挤压                             |
| NEO 类路径           | GPU/NPU 保持主干计算，CPU 承接部分 decode attention          | 部分 KV 下沉 CPU DDR                                         | KV warm tier、部分 attention compute、load-aware scheduler   | 降低 KV 对 HBM 的压力，扩大 batch/concurrency | CPU attention 或 CPU-DDR 带宽成为瓶颈；overlap 不足会恶化 TPOT |
| KTransformers 类路径 | GPU/NPU 保留 attention、shared/hot experts，CPU 处理部分 routed expert 路径 | routed experts 分层放 HBM/DDR/SSD                            | expert warm tier、专家索引、专家预取、可能的低频 expert compute | 大 MoE expert 放不下、expert miss 影响 decode | CPU expert kernel 能力不确定，专家预取错误会挤占 HBM         |

从调研结论看，GLM-5.2 的优先方向不是“把模型拆到 CPU 上跑”，而是先做两类状态分层：**MoE expert 分层**和**KV/Prefix/Context 分层**。前者决定大模型是否放得下、expert miss 是否拖慢 TPOT；后者决定长上下文和多轮会话下 TTFT、恢复时延和 HBM 占用。Deep Research 也将 MoE expert 管理、KV/Prefix/State 分层、统一 state object runtime、推理仿真与 profiling 列为核心研究问题。

## 8. 面向 A+K 小算力一体机的方案表达

面向 A+K 一体机，可以把技术路线表述为“主算保持在 Ascend，状态和冷路径交给 Kunpeng 与分级内存”。

在 prefill 阶段，Ascend NPU 负责大矩阵、attention、MoE 主干和 IndexShare 相关计算；Kunpeng CPU 负责 tokenizer、prefix 命中判断、cache metadata、请求调度和后续预取计划。此阶段重点是降低 TTFT，避免重复 prefill，提升 prefix/cache 命中率。

在 decode 阶段，Ascend NPU 负责每 token 的主路径计算，包括 attention 热路径、router、hot expert 和输出；Kunpeng CPU 负责 KV warm tier、expert warm tier、cache 管理、冷专家预取、低频 fallback 和链路调度。此阶段重点是稳定 TPOT 和 P95/P99，避免 expert miss、KV restore、DDR/SSD 回取进入不可隐藏的热路径。

在状态管理层，KV、Prefix、Context、Expert、Weight、Activation 和多模态 latent/noise cache 都应被抽象为 state object，记录大小、热度、所在层级、下一次访问概率、加载成本、驱逐成本和重算成本。大模型推理硬件地图也建议将 KV、expert、prefix、weight、latent 等统一成 state object，而不是分别写死在 KV 或 expert 模块中。

## 9. 调研阶段建议保留的结论

本阶段不建议深入到每层矩阵和每个 kernel，而应形成下面几条方案判断。

第一，GLM-5.2 的推理瓶颈不是单纯 FLOPs，而是权重、KV、Prefix、Expert、activation 和 workspace 在近端内存中的竞争关系。

第二，prefill 和 decode 需要分开分析。prefill 更偏计算密集，decode 更偏状态访问、内存带宽和调度稳定性。不能只用平均 tokens/s 判断方案好坏。

第三，NEO 代表的是“CPU 参与部分 decode attention / KV warm tier”的思路，适合缓解 KV 与 batch/concurrency 压力，但不能泛化为 CPU 主算。

第四，KTransformers 代表的是“MoE expert 分层与 CPU/GPU 协同”的思路，对 GLM-5.2 这种大 MoE 模型更直接，但迁移到 Kunpeng 需要重新验证 CPU 向量化 expert kernel 能力。

第五，A+K 的落地优先级应是：先做可观测、KV warm tier、UCM/external KV 和 expert hotness trace；再做 MoE expert 分层、prefix 复用和 Mooncake/KV Pool；最后再讨论 SSD cold tier、NPU-native SSD direct path 或完整 P/D 分离。Deep Research 也建议 P0 先做 profiler/simulator、KV Cache CPU Offload 和 UCM/prefix cache，P1 再做 Mooncake/KV Pool 与 expert hotness，P2/P3 才推进 SSD cold tier 与 NPU-native direct path。

## 10. 一句话总结

以 GLM-5.2 为例，标准推理框架把模型主计算和热状态尽量放在 GPU/NPU 近端内存中；NEO 说明部分 decode attention 与 KV 可以下沉到 CPU/DDR 并与主计算重叠；KTransformers 说明大 MoE expert 可以按冷热分层并让 CPU 承接部分专家路径。对 A+K 小算力一体机而言，最合理的调研结论不是“CPU 替代 NPU”，而是“Ascend 保持高密度主算，Kunpeng 承接状态管理、warm tier、预取、低频子路径和可观测闭环”，通过 MoE expert 分层与 KV/Prefix 状态分层来解决 GLM-5.2 的容量、带宽和尾延迟问题。