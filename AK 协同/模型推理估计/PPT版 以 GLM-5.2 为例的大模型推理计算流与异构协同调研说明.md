## 以 GLM-5.2 为例：大模型推理计算流与异构硬件协同说明稿

### 1. 先把 GLM-5.2 讲成“几件事”

GLM-5.2 可以先不按复杂矩阵拆，而是理解成一个面向长上下文和大规模 MoE 的推理系统。它不是普通 dense 模型，而是 **744B 总参数、约 39B–40B 活动参数、1M 上下文、MoE 专家路由、稀疏注意力和压缩 KV**组合起来的大模型。公开配置显示它有 78 层、256 个 routed experts、每个 token 激活 top-8 experts，并包含 shared expert、IndexShare 和 MLA/DSA 类注意力线索。

对领导汇报时，可以把每一层理解成重复做四件事：

1. **读上下文**：模型看当前 token 和历史上下文，决定当前 token 应该关注哪些历史信息。
2. **查记忆**：从 KV Cache 中读取历史 token 的压缩记忆。
3. **选专家**：MoE router 判断这个 token 应该交给哪些专家处理。
4. **合成答案**：把注意力结果、专家结果合并，继续生成下一个 token。

所以 GLM-5.2 的推理瓶颈不是单纯“算力不够”，而是 **权重、KV、专家、缓存状态放在哪里，以及这些状态如何跨 HBM/DDR/SSD/PCIe/UB 搬运**。大模型推理硬件问题已经从“单卡算力不够”转向“状态对象放在哪里、什么时候搬、由谁搬、搬运是否挡住主链路”。

------

### 2. Prefill 和 Decode 用人话怎么理解

#### Prefill：先把题目读完，并把笔记写好

Prefill 是处理用户输入 prompt 的阶段。比如用户给了一段代码仓库、文档、需求说明，模型要一次性读完整段输入。

这个阶段主要做：

- 把输入文本转成 token；
- 逐层跑 Transformer；
- 生成每一层的 KV Cache；
- 建立后续 decode 要反复查的“上下文记忆”；
- 对 MoE 模型，还要为每个 token 做专家路由。

硬件上，prefill 更像“大批量读题”。输入 token 多、矩阵大、并行度高，所以标准框架通常让 GPU/NPU 主算，吃的是 **Tensor Core / AI Core、HBM/Bailu 带宽和 attention kernel 效率**。

#### Decode：每次写一个字，每写一次都要翻笔记

Decode 是逐 token 生成答案的阶段。每生成一个新 token，都要重新过一遍模型层，但这次不是读完整 prompt，而是：

- 读取当前 token；
- 从 KV Cache 中查历史上下文；
- 做 attention；
- 做 MoE 专家选择；
- 计算 logits；
- 采样出下一个 token。

硬件上，decode 更像“边写边查资料”。每步计算量不大，但要频繁读取历史 KV、专家权重和模型权重，因此更容易从 compute-bound 变成 **memory-bound / scheduler-bound**。也就是说，decode 常常不是卡在算不动，而是卡在 **HBM 放不下、DDR/PCIe 搬不快、专家 miss 后等数据、KV 恢复抖动**。

------

### 3. 标准纯 GPU 推理：所有热数据尽量留在 GPU/HBM

标准纯 GPU 推理框架可以理解成：**CPU 负责接单和调度，GPU 负责真正算模型，HBM 负责放热数据。**

#### 标准链路

```text
CPU:
  tokenizer / request scheduler / sampling / cache metadata

PCIe:
  输入 token、少量控制信息、最终输出结果

GPU + HBM:
  模型权重
  Attention / FFN / MoE 计算
  KV Cache
  Expert weights
  activation / workspace
```

在标准框架里，最理想的情况是：

- 权重常驻 GPU HBM；
- KV Cache 常驻 GPU HBM；
- MoE experts 尽量也常驻 GPU HBM；
- PCIe 只负责请求进入、结果返回、少量调度信息；
- decode 热路径不频繁跨 CPU/PCIe/SSD。

这种方式的好处是链路最短，GPU 算完就能继续下一步。问题是 GLM-5.2 这类大 MoE 模型会让 HBM 同时承受 **权重、KV Cache、MoE experts、activation、workspace** 的压力。HBM 放不下之后，就必须引入 DDR、SSD 或多卡/多机，但只要热路径频繁跨 PCIe/UB，就可能把性能打回去。

可以用一句话概括标准方案：

**标准 GPU 推理是“把算力和热状态都压到 GPU/HBM 里”，性能路径最短，但容量压力最大。**

------

### 4. PCIe / UB 数据搬运在推理里到底扮演什么角色

不能只说 CPU/DRAM 和 GPU/HBM。真正决定 offload 是否成立的是 **PCIe/UB 这条搬运链路**。

推理中常见的数据搬运有五类：

| 搬运对象                      | 搬运方向        | 是否危险 | 说明                                                         |
| ----------------------------- | --------------- | -------- | ------------------------------------------------------------ |
| 输入 token / 输出 token       | CPU ↔ GPU/NPU   | 低       | 数据量小，通常不是瓶颈                                       |
| KV Cache                      | HBM ↔ DDR / SSD | 高       | decode 每步都可能查历史 KV，如果频繁搬整段 KV，会直接拖慢 TPOT |
| MoE expert 权重               | DDR/SSD → HBM   | 很高     | expert 权重大，miss 后临时搬运容易卡住 decode                |
| attention / expert 中间结果   | CPU ↔ GPU/NPU   | 中       | 如果结果较小且能和主计算重叠，可能可接受                     |
| cache metadata / routing 信息 | CPU ↔ GPU/NPU   | 低到中   | 单次小，但高频同步会制造尾延迟                               |

所以 offload 不是“放到 CPU/SSD 就行”，而是要回答三件事：

1. **搬什么**：KV、expert、权重，还是中间结果？
2. **怎么搬**：走 PCIe、UB、DMA、NPU stream、P2P，还是经 CPU bounce buffer？
3. **会不会挡住主链路**：能不能提前搬、批量搬、异步搬，并被 GPU/NPU 主计算覆盖？

硬件地图中也明确指出，PCIe / UB / DMA 层的关键问题是 D2H/H2D 延迟、setup cost、overlap ratio 和同步屏障；如果对象每次访问都在 hot path 上跨 PCIe/网络，通常不赚钱，只有可预测、可预取、可批量、可重叠时才可能赚钱。

------

### 5. NEO：不是简单 KV offload，而是把一部分 decode attention 留在 CPU 侧

NEO 的优化点可以用一句话讲清楚：

**NEO 不是把 KV 放到 CPU 后再每步搬回 GPU，而是把部分请求的 KV 和 decode attention 计算一起留在 CPU/DDR 侧，GPU 继续跑主干计算，两边形成流水。**

标准 GPU 方案中，decode attention 都在 GPU 上做，KV 也在 HBM 中。如果 HBM 不够，把 KV 放到 CPU DDR，再每步通过 PCIe 搬回 GPU，会非常慢。NEO 试图避免这个问题：既然某些 KV 已经在 CPU DDR，那对应的部分 decode attention 也在 CPU 上算，最后只把必要的 attention 输出或中间结果通过 PCIe 送回 GPU。NEO 的精读笔记也强调，它的链路是 GPU/HBM、PCIe、CPU cores、CPU memory 和 load-aware scheduler 协同，而不是普通 KV swap。

#### NEO 对计算流的改动

| 模型组件           | 标准 GPU      | NEO                                          |
| ------------------ | ------------- | -------------------------------------------- |
| Prefill 主计算     | GPU/HBM       | 仍以 GPU/HBM 为主                            |
| 线性层 / FFN       | GPU           | 仍在 GPU                                     |
| GPU-side attention | GPU 读 HBM KV | 部分请求仍在 GPU                             |
| CPU-side attention | 无            | 部分 decode attention 在 CPU 执行            |
| KV Cache           | 主要在 HBM    | 分成 GPU KV 和 CPU KV                        |
| PCIe 搬运          | 尽量少        | 传必要张量，不反复搬整段 KV                  |
| 调度器             | 常规 batching | 决定哪些请求走 GPU，哪些请求走 CPU attention |

NEO 的价值在于扩大有效 batch / 并发，缓解 HBM KV 压力。它的风险也很清楚：CPU attention 太多时，CPU DDR 带宽和 CPU kernel 会成为瓶颈；PCIe 传输如果不能被 GPU 计算覆盖，TPOT/P99 会恶化。

对 GLM-5.2 来说，NEO 更适合借鉴在 **KV / attention warm path** 上，而不是直接解决 MoE expert 权重问题。

------

### 6. KTransformers：重点不是 KV，而是 MoE experts 怎么放、怎么算

KTransformers 的核心不是“KV 放 CPU”，而是面向 MoE 模型解决 expert 权重太大、GPU HBM 放不下的问题。

可以用一句话讲：

**KTransformers 把 attention、shared/hot experts 留在 GPU，把 routed experts 放在 CPU DRAM，并让 CPU 直接计算一部分 experts，避免每次都把大块 expert 权重经 PCIe 搬到 GPU。**

对 GLM-5.2 这种 MoE 模型，这个方向比 NEO 更直接。因为 GLM-5.2 每个 token 要从 256 个 routed experts 中选 top-8，问题不是 router 本身多复杂，而是 **被选中的 expert 权重在哪里、是否命中热缓存、miss 后要不要跨 PCIe/UB 搬运**。GLM-5.2 的系统瓶颈不能只看总参数，还要看 active experts、expert hotness、KV cache 和搬运路径。

#### KTransformers 对计算流的改动

| 模型组件                   | 标准 GPU                 | KTransformers                                |
| -------------------------- | ------------------------ | -------------------------------------------- |
| Attention                  | GPU/HBM                  | 仍主要在 GPU                                 |
| KV Cache                   | GPU/HBM                  | 不是主要改动点                               |
| Router / gate              | GPU                      | GPU 先决定 token 走哪些 experts              |
| Shared expert / hot expert | GPU                      | 继续留在 GPU                                 |
| Routed experts             | GPU HBM                  | 放到 CPU DRAM，由 CPU 直接算                 |
| PCIe 搬运                  | expert miss 时可能搬权重 | 尽量不搬大权重，只传任务、同步和较小结果     |
| CPU 角色                   | host/control             | expert compute + DRAM expert tier + 调度协同 |

这个方案的关键变化是：**从“把 expert 权重搬到 GPU 算”变成“expert 权重留在 CPU，CPU 就地算，再把结果返回 GPU”**。这样能减少大块权重在 PCIe 上来回搬，但会引入 CPU 算力、DDR 带宽、NUMA、CPU-GPU 同步等新瓶颈。精读笔记也特别提醒，KTransformers 不应被简化成“MoE 权重放 CPU”，它实际包含 shared experts/GPU、routed experts/CPU、AMX/AVX/NUMA/CUDA Graph/Expert Deferral 等协同机制。

迁移到 Ascend + Kunpeng 时，不能直接继承 x86 AMX 的结果；Kunpeng 侧必须重新验证 SVE/SME expert kernel、DDR 带宽和 NPU-CPU 异步调度能力。

------

### 7. 三种方案的横向对比

| 维度              | 标准纯 GPU 推理                  | NEO 类方案                              | KTransformers 类方案                          |
| ----------------- | -------------------------------- | --------------------------------------- | --------------------------------------------- |
| 核心思想          | 全部热计算和热状态尽量留 GPU/HBM | 把部分 decode attention + KV 留 CPU/DDR | 把 MoE routed experts 放 CPU/DDR 并直接计算   |
| 主要解决问题      | 链路最短、性能稳定               | HBM KV 容量不够、GPU batch 受限         | MoE expert 权重太大，GPU 放不下               |
| GPU/NPU 负责      | attention、FFN、MoE、KV、lm_head | 主干线性层、GPU-side attention、FFN     | attention、router、shared/hot experts         |
| CPU 负责          | tokenizer、scheduler、sampling   | CPU-side KV 与部分 decode attention     | routed expert compute、expert DRAM tier、调度 |
| HBM/Bailu 放什么  | 权重、热 KV、experts、workspace  | 权重、GPU KV、主计算 workspace          | attention、shared/hot experts、热 KV          |
| DDR 放什么        | 一般不在热路径                   | CPU-request KV                          | routed experts / warm experts                 |
| SSD 放什么        | checkpoint / 冷数据              | 可作为更冷层，但非 NEO 核心             | cold experts / cold KV，可作为扩展            |
| PCIe/UB 压力      | 低，除非 offload                 | 传必要张量，避免整段 KV 往返            | 避免大 expert 权重往返，但有同步和结果回传    |
| 主要风险          | HBM 容量顶不住                   | CPU attention 和 PCIe overlap 不足      | CPU expert kernel、DDR 带宽、同步开销不足     |
| 对 GLM-5.2 的启发 | 基线方案                         | 借鉴 KV / attention warm tier           | 借鉴 MoE expert 分层与 CPU 协同               |

总结成一句话：

**标准方案把热数据都压在 GPU/HBM；NEO 把一部分 KV 和 decode attention 下沉到 CPU/DDR；KTransformers 把 MoE routed experts 下沉到 CPU/DDR，并尽量减少 expert 权重跨 PCIe 来回搬。**

------

### 8. 映射到 A+K 一体机：应该怎么讲

在 Ascend NPU + Kunpeng CPU 的一体机语境下，可以把硬件分成四层：

| 层级   | 对应硬件                     | 适合放什么                                      |
| ------ | ---------------------------- | ----------------------------------------------- |
| 热层   | Ascend NPU + Bailu/HBM       | 主干计算、热 KV、shared/hot experts、workspace  |
| 温层   | Kunpeng CPU + DDR            | warm KV、warm experts、prefix cache、调度元数据 |
| 冷层   | SSD/NVMe                     | cold KV、cold experts、历史会话状态             |
| 搬运层 | PCIe / UB / DMA / NPU stream | HBM↔DDR↔SSD 的数据回流、预取、换出              |

项目材料中的塔式工作站方案也采用类似三级存储组织：L1 为 84GB Bailu 承载热权重与热 KV，L2 为 384GB DDR5 承载冷权重与温 KV，L3 为 512GB×4 SSD 承载冷 KV，并通过 UB、预取、换出和直通路径组织数据流。

因此，A+K 方案不应说成“CPU 加速 NPU”，更准确的说法是：

**NPU 负责高密度主算，Kunpeng 负责状态管理、warm tier、expert/KV 预取、部分可重叠计算和 I/O 聚合；PCIe/UB 决定这些协同是否真正赚钱。**

------

### 9. 建议 PPT 上的主结论

可以放成三句话：

**第一，GLM-5.2 的推理瓶颈不是单纯算力，而是“长上下文 KV + 大规模 MoE experts + 低时延 decode”共同挤压 HBM。**

**第二，标准 GPU 推理路径最短，但容量压力最大；NEO 通过 CPU/DDR 承接部分 KV 与 decode attention，缓解 KV 压力；KTransformers 通过 CPU/DDR 承接 routed experts，缓解 MoE expert 权重压力。**

**第三，A+K 一体机的关键不是简单 offload，而是让热数据留 NPU/Bailu，温数据进 Kunpeng/DDR，冷数据进 SSD，并通过 PCIe/UB 的异步预取、批量搬运和重叠计算，避免数据搬运进入 token 生成主链路。**

------

### 10. 可以直接用于图里的简化计算流

```text
用户请求
  ↓
CPU / Runtime：分词、组 batch、查 prefix、调度
  ↓  小数据经 PCIe/UB 进入加速器
GPU/NPU + HBM/Bailu：Prefill 主计算，生成 KV Cache
  ↓
HBM/Bailu：保存热 KV、热 experts、workspace
DDR：保存温 KV、温 experts、prefix cache
SSD：保存冷 KV、冷 experts、历史状态
  ↓
Decode 循环：
  1. GPU/NPU 读取热 KV 和热 experts
  2. 如命中温层，CPU/DDR 提前预取，经 PCIe/UB 回流
  3. 如走 NEO 类路径，部分 KV 和 attention 留在 CPU 侧计算
  4. 如走 KTransformers 类路径，routed experts 在 CPU/DDR 侧计算
  5. GPU/NPU 汇总结果，输出下一个 token
```

这张图要特别标出两条路径：

- **热路径**：Runtime → GPU/NPU → HBM/Bailu → decode token。
  这条路径要尽量短，不能频繁跨 PCIe/SSD。
- **温/冷路径**：HBM/Bailu ↔ PCIe/UB ↔ DDR ↔ SSD。
  这条路径用于扩容、预取、恢复和换出，但必须异步、批量、可预测、可重叠。