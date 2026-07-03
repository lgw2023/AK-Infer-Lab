下面这版按“**GLM-5.2 单个 Transformer layer 的组件拆解** → **prefill / decode 计算流** → **标准纯 GPU 推理硬件映射** → **NEO / KTransformers 改动对照**”展开。先说明口径：GLM-5.2 的底层 kernel、DSA indexer 的完整数学形式没有官方论文式逐项公开；下面把**官方配置可确认的信息**和**系统工程反推**分开写。

## 1. GLM-5.2 的模型层级结构

GLM-5.2 公开配置显示：模型类型是 `glm_moe_dsa`，`hidden_size=6144`，`num_hidden_layers=78`，上下文长度 `max_position_embeddings=1048576`；Attention 侧包含 `q_lora_rank=2048`、`kv_lora_rank=512`、`qk_nope_head_dim=192`、`qk_rope_head_dim=64`、`qk_head_dim=256`，MoE 侧包含 `n_routed_experts=256`、`num_experts_per_tok=8`、`n_shared_experts=1`，并且前 3 层是 dense MLP，后续层是 sparse / MoE MLP。([Hugging Face](https://huggingface.co/zai-org/GLM-5.2/blob/main/config.json)) 官方模型卡还说明 GLM-5.2 支持 1M context，并通过 IndexShare 在每四个 sparse attention layer 复用同一个 indexer，在 1M context 下将 per-token FLOPs 降低 2.9×；MTP speculative decoding 的 acceptance length 也有提升。([Hugging Face](https://huggingface.co/zai-org/GLM-5.2))

可以把 78 层拆成两类：

| 层范围     | Attention                   | MLP / FFN                                                 | 主要状态对象                                                 |
| ---------- | --------------------------- | --------------------------------------------------------- | ------------------------------------------------------------ |
| Layer 0–2  | MLA / DSA / IndexShare 路线 | Dense SwiGLU 类 MLP，`intermediate_size=12288`            | 权重、压缩 KV、activation、workspace                         |
| Layer 3–77 | 同上                        | MoE：256 routed experts，top-8 激活，另有 1 shared expert | routed expert、shared expert、router logits、专家缓存、压缩 KV |

单层的主结构可以写成：

```text
hidden_states
  → RMSNorm
  → MLA / DSA Attention
      → Q low-rank projection
      → compressed KV projection
      → RoPE
      → DSA indexer / IndexShare
      → sparse attention gather
      → output projection
  → residual add
  → RMSNorm
  → Dense MLP 或 MoE MLP
      → router / gate
      → top-8 routed experts
      → shared expert
      → expert output combine
  → residual add
```

这里最关键的是：GLM-5.2 不是传统 “Q/K/V 全量展开并缓存完整 K/V head” 的结构。更合理的系统视角是把 Attention 侧拆成 **Q low-rank 路径、compressed KV 路径、RoPE 位置路径、DSA/IndexShare 稀疏索引路径**。KV cache 也不应直接按传统公式 `2 * num_kv_heads * head_dim` 估算，而应近似理解为保存 `kv_lora_rank + qk_rope_head_dim = 512 + 64 = 576` 这一类压缩状态；这是 GLM-5.2 能谈 1M context 的核心原因之一。

## 2. 单层组件的计算与状态拆解

### 2.1 Embedding 与输入侧

输入端先由 CPU / Runtime 做 chat template、tokenization、position ids、attention mask；之后 token ids 进入 GPU，查 embedding table 得到 `[B, S, 6144]` 的 residual stream。Embedding 和 `lm_head` 都是大矩阵；配置里 `tie_word_embeddings=false`，所以输出头不能与输入 embedding 简单共享。([Hugging Face](https://huggingface.co/zai-org/GLM-5.2/blob/main/config.json))

| 组件                         | 输入              | 输出         | 纯 GPU 下硬件位置                         |
| ---------------------------- | ----------------- | ------------ | ----------------------------------------- |
| Chat template / tokenizer    | messages / prompt | token ids    | CPU host / runtime                        |
| Embedding lookup             | `[B,S]`           | `[B,S,6144]` | GPU HBM 读 embedding；SM 做 gather / load |
| Position ids / RoPE metadata | `[B,S]`           | 位置索引     | CPU 构造，GPU kernel 使用                 |

### 2.2 Attention：MLA / DSA / IndexShare

GLM-5.2 的 Attention 侧建议拆成四段：

第一段是 **Q 路径**：从 hidden states 投影到 `q_lora_rank=2048`，再展开到 `64 heads × qk_head_dim 256`。第二段是 **compressed KV 路径**：从 hidden states 投影到压缩 KV latent 和 RoPE 位置部分，核心字段是 `kv_lora_rank=512` 与 `qk_rope_head_dim=64`。第三段是 **DSA indexer / IndexShare**：full indexer 层计算稀疏索引，shared 层复用索引。第四段是 **稀疏 attention 聚合**：只对被 indexer 选中的 top-k / 局部块执行 QK、softmax、V 聚合。

| Attention 子组件         | Prefill 行为                    | Decode 行为                                      | 纯 GPU 硬件位置                      |
| ------------------------ | ------------------------------- | ------------------------------------------------ | ------------------------------------ |
| RMSNorm                  | 对 `[B,S,H]` 全 prompt 做归一化 | 对 `[B,1,H]` 新 token 做归一化                   | GPU SM / HBM                         |
| Q low-rank projection    | 大矩阵，整段 prompt 并行        | 小 batch 单 token GEMM，利用率较低               | Tensor Core / HBM                    |
| compressed KV projection | 生成整段 prompt 的压缩 KV       | 只生成当前 token 的压缩 KV                       | Tensor Core / HBM                    |
| RoPE                     | 对 Q / K 位置子空间加旋转       | 对当前 token 加 RoPE，并读取历史位置             | GPU elementwise kernel               |
| DSA full indexer         | full 层计算稀疏索引             | 为新 token 或当前步计算索引                      | GPU kernel；可能占用 HBM / L2        |
| IndexShare shared 层     | 复用前面 full indexer 的索引    | 复用索引，减少 per-token FLOPs                   | GPU HBM 存 index metadata            |
| Sparse attention         | 对 prompt 内候选块做 attention  | 读取历史 compressed KV，计算当前 token attention | GPU SM / Tensor Core / shared memory |
| KV cache 写入            | 写入所有 prompt token 的 KV     | 每层写入当前 token KV                            | GPU HBM / paged KV block             |

### 2.3 MLP：前 3 层 dense，后 75 层 MoE

前 3 层是 dense MLP，基本是标准 SwiGLU 类路径：gate projection、up projection、激活、down projection。后 75 层是 MoE：router 从 hidden states 产生 256 个 expert 的 score，每个 token 选择 top-8 routed experts，再叠加 shared expert。配置字段 `scoring_func=sigmoid`、`topk_method=noaux_tc`、`num_experts_per_tok=8` 支持这一判断。([Hugging Face](https://huggingface.co/zai-org/GLM-5.2/blob/main/config.json))

| MLP 子组件      | Prefill 行为                            | Decode 行为                    | 纯 GPU 硬件位置                               |
| --------------- | --------------------------------------- | ------------------------------ | --------------------------------------------- |
| Dense MLP       | `[B,S,6144] → [B,S,12288] → [B,S,6144]` | `[B,1,6144]` 小 GEMM           | GPU Tensor Core                               |
| Router / gate   | 每个 token 计算 256 expert score        | 每个新 token 计算 expert score | GPU Tensor Core / SM                          |
| Expert dispatch | 将 tokens 按 expert 分组                | token 数少，分组粒度小         | GPU HBM gather/scatter                        |
| Routed experts  | top-8 expert FFN                        | top-8 expert FFN               | 标准纯 GPU 下在 GPU；多卡时可能 EP/all-to-all |
| Shared expert   | 每个 token 固定走 shared expert         | 同上                           | GPU                                           |
| Combine         | expert 输出加权合并                     | 当前 token expert 输出合并     | GPU SM / HBM                                  |

对 GLM-5.2 这种 744B / A40B 级 MoE，系统瓶颈常常不是 router 计算本身，而是 expert weight 的驻留、搬运、热度预测和 miss penalty。项目文档也把 MoE expert 管理归为核心方向：expert 总量大、激活稀疏，并与 KV cache 共同争抢 HBM。

## 3. Prefill 过程：从 prompt 到 KV cache 初始化

Prefill 的输入是整段 prompt，输出是最后一个位置的 hidden state / logits，以及每层所有 prompt token 的 KV cache。对于 GLM-5.2，prefill 还要生成或复用 DSA/IndexShare 的索引。

标准纯 GPU prefill 流程：

```text
CPU runtime:
  request parse / tokenizer / template / batch scheduler

GPU:
  input_ids → embedding
  for layer in 0..77:
      RMSNorm
      Q / compressed-KV projection
      RoPE
      DSA indexer 或 IndexShare
      sparse attention
      写入 paged KV cache
      attention output projection
      residual
      RMSNorm
      Dense MLP 或 MoE router + experts
      residual
  final norm
  lm_head for last token
CPU/GPU:
  sampling / structured output parsing
```

硬件层面，prefill 是**大矩阵、长序列并行、较高 GPU 利用率**。它吃 Tensor Core / AI Core、HBM 带宽、attention kernel 和 workspace；activation 与临时 attention workspace 也更大。项目硬件地图中也明确区分：prefill 更像算力密集阶段，decode 更容易变成 memory / scheduler bound 阶段。

纯 GPU prefill 的关键路径是：

| 阶段                    | 主要硬件                       | 主要瓶颈                                       |
| ----------------------- | ------------------------------ | ---------------------------------------------- |
| Tokenization / batching | CPU                            | 调度开销通常不是主瓶颈                         |
| Embedding / projection  | GPU Tensor Core + HBM          | HBM 读权重、GEMM 吞吐                          |
| DSA indexer             | GPU SM / Tensor Core           | sparse index 计算与 metadata                   |
| Sparse attention        | GPU SM / shared memory / HBM   | top-k KV gather、softmax、workspace            |
| KV 写入                 | GPU HBM / paged KV allocator   | block 分配、写带宽、fragmentation              |
| MoE expert              | GPU Tensor Core / HBM / NVLink | expert weight 驻留、token dispatch、all-to-all |
| Logits                  | GPU Tensor Core                | `H × vocab` 大矩阵，通常只算最后 token         |

## 4. Decode 过程：每 token 迭代

Decode 每次只输入上一步生成的新 token，但每一层都要读取历史 KV，并重新经过 attention、MoE 和 lm_head。这个阶段的计算粒度小，batch 也往往较小，因此 GPU Tensor Core 可能不饱和；同时每 token 都要访问活动权重、KV cache、expert weight 和 block metadata，带宽与调度成为核心瓶颈。

标准纯 GPU decode 流程：

```text
while not finished:
  CPU/GPU scheduler forms decode batch
  GPU:
    embedding current token
    for layer in 0..77:
        RMSNorm
        Q projection for current token
        compressed KV projection for current token
        RoPE
        DSA / IndexShare index selection
        read historical compressed KV from HBM
        sparse attention over selected history
        append current token KV to paged cache
        output projection + residual
        RMSNorm
        router
        top-8 routed experts + shared expert
        combine + residual
    final norm
    lm_head
    optional MTP draft / verify path
  sampler:
    sample / accept draft tokens / stop check
```

Decode 的核心状态对象：

| 状态对象                         | 位置：标准纯 GPU                | Decode 中的作用               |
| -------------------------------- | ------------------------------- | ----------------------------- |
| 权重                             | GPU HBM，或多卡分片             | 每 token 反复读取             |
| compressed KV                    | GPU HBM paged cache             | 每层 attention 读取历史上下文 |
| IndexShare metadata              | GPU HBM / runtime metadata      | 减少稀疏 indexer 重算         |
| MoE expert weights               | GPU HBM，或多卡 expert parallel | top-8 experts 被激活          |
| activation / workspace           | GPU HBM / SRAM / L2             | 当前 token 临时张量           |
| block table / scheduler metadata | CPU + GPU metadata              | 管理 cache block 与 batch     |

这也是为什么 GLM-5.2 的系统分析不应只看 “744B 总参数”。总参数决定装载门槛；decode 的真实性能由**活动参数、compressed KV 布局、IndexShare、MTP、expert hit rate 和 HBM 带宽**共同决定。

## 5. 标准纯 GPU 推理框架下的硬件分工

这里的“纯 GPU”指 vLLM / SGLang / TensorRT-LLM 这类标准 serving 框架中，模型主计算、KV、expert 和 cache 均保留在 GPU 侧；CPU 只做控制面和外围处理。GLM-5.2 官方模型卡列出 Transformers、vLLM、SGLang、KTransformers、Ascend 侧 vLLM-Ascend / xLLM / SGLang 等部署入口。([Hugging Face](https://huggingface.co/zai-org/GLM-5.2))

| 模型组件                  | 标准纯 GPU 放置             | Prefill                               | Decode                         |
| ------------------------- | --------------------------- | ------------------------------------- | ------------------------------ |
| Tokenizer / chat template | CPU                         | 构造 prompt ids                       | 处理增量输出 / stop            |
| Scheduler / batcher       | CPU runtime + GPU metadata  | continuous batching / chunked prefill | decode batch merge / split     |
| Embedding                 | GPU HBM + SM                | 全 prompt lookup                      | 当前 token lookup              |
| Q / KV projections        | GPU Tensor Core             | 大 GEMM，高利用率                     | 小 GEMM，易低利用              |
| RoPE / norm / activation  | GPU SM                      | elementwise                           | elementwise                    |
| DSA indexer / IndexShare  | GPU                         | full indexer 或 shared reuse          | 当前 token 选择 / 复用         |
| Attention                 | GPU SM / Tensor Core / SRAM | 长序列 sparse attention               | 读历史 KV，memory-bound        |
| KV cache                  | GPU HBM                     | 写入整段 prompt KV                    | 每步读取历史 KV，并追加新 KV   |
| Dense MLP                 | GPU Tensor Core             | 大 GEMM                               | 小 GEMM                        |
| MoE router                | GPU                         | 计算所有 prompt token 的 top-8        | 计算当前 token top-8           |
| Routed experts            | GPU HBM / 多卡 EP           | token 分组后专家计算                  | 小 token 数，dispatch 开销显著 |
| Shared expert             | GPU                         | 常规 FFN                              | 常规 FFN                       |
| lm_head                   | GPU                         | 末 token logits                       | 每步 logits                    |
| Sampling                  | CPU 或 GPU                  | 选首 token                            | 每步采样 / MTP 接受            |

纯 GPU 路径的优点是同步简单，热路径短；缺点是 HBM 被**权重、KV、expert、activation、workspace**共同挤压。一旦 GLM-5.2 这种 MoE 模型进入长上下文和多轮 agent workload，容量与带宽问题会先于峰值算力暴露。项目材料的总体判断也类似：大模型推理问题已经从“单卡算力不够”转向“状态对象放在哪里、什么时候搬、由谁搬、搬运是否挡住主链路”。

## 6. NEO 对标准路径的改动

NEO 的关键不是“把 KV 放 CPU 再搬回 GPU”，而是把一部分 request 的 **decode attention 计算和对应 KV cache 留在 CPU / CPU memory 侧**，GPU 继续跑 prefill、线性层、GPU-side attention 和主计算。NEO 通过 asymmetric GPU-CPU pipelining 和 load-aware scheduling 平衡 CPU/GPU 负载；论文摘要报告在 T4、A10G、H100 上分别达到最高 7.5×、26%、14% 的吞吐提升，同时维持相同延迟。([arXiv](https://arxiv.org/abs/2411.01142?utm_source=chatgpt.com)) 项目精读也强调：NEO 只证明特定 decode attention 子路径在容量受限且可重叠时有价值，不证明 CPU 能普遍加速推理。

把 NEO 映射到 GLM-5.2：

| GLM-5.2 组件     | 标准纯 GPU               | NEO 式改动                                      | 对 GLM-5.2 的适配难点                                        |
| ---------------- | ------------------------ | ----------------------------------------------- | ------------------------------------------------------------ |
| Prefill          | GPU 执行                 | 基本仍在 GPU                                    | GLM-5.2 prefill 含 DSA indexer / IndexShare，CPU 不适合直接接管 |
| Q / projection   | GPU                      | GPU 仍跑线性主路径                              | 需要把 CPU attention 所需 Q / metadata 传到 CPU              |
| KV cache         | 全部在 GPU HBM           | 一部分 request 的 KV 留 CPU DRAM                | GLM-5.2 是 compressed KV / MLA cache，CPU 侧需要同格式 kernel |
| Decode attention | GPU 读 HBM KV            | 部分 request 的 decode attention 在 CPU 执行    | CPU attention 必须能处理 DSA/IndexShare / compressed KV      |
| Dense / MoE MLP  | GPU                      | NEO 通常不改 FFN / MoE 主路径                   | GLM-5.2 的大瓶颈还有 MoE expert，NEO 不直接解决              |
| Scheduler        | 标准 continuous batching | load-aware scheduling：决定哪些 request offload | 需要记录 CPU queue、GPU queue、KV size、attention latency    |
| PCIe / DMA       | 主路径不跨 CPU           | 传必要张量和 attention output，不反复搬整段 KV  | 链路必须可被 GPU 主计算覆盖                                  |

所以，NEO 对 GLM-5.2 的价值主要在 **decode attention / KV warm tier**，不是 MoE expert 分层。它适合作为 A+K 的“CPU 只吃一部分可重叠 decode 子路径”的参考，而不适合作为“Kunpeng 主算化”的依据。

## 7. KTransformers 对标准路径的改动

KTransformers 面向大 MoE 本地部署，核心做法是：**attention、shared / hot experts 留 GPU；routed experts 放 CPU DRAM，并用 AMX / AVX、NUMA-aware placement、异步 CPU-GPU 调度和 Expert Deferral 提高 overlap**。论文摘要给出 4.62–19.74× prefill speedup、1.25–4.09× decode speedup，并指出 Expert Deferral 可把 CPU 利用率从通常低于 75% 提升到接近 100%，带来最高 1.45× 额外吞吐收益，精度损失平均不超过 0.5%。([MADSys](https://madsys.cs.tsinghua.edu.cn/publication/ktransformers-unleashing-the-full-potential-of-cpu/gpu-hybrid-inference-for-moe-models/SOSP25-chen.pdf))

把 KTransformers 映射到 GLM-5.2：

| GLM-5.2 组件          | 标准纯 GPU        | KTransformers 式改动                                    | 对 GLM-5.2 的价值                                         |
| --------------------- | ----------------- | ------------------------------------------------------- | --------------------------------------------------------- |
| Attention / MLA / DSA | GPU               | 基本仍在 GPU                                            | 保持高带宽 attention 热路径                               |
| KV cache              | GPU HBM           | 不作为主要改动对象                                      | 可与 LMCache / UCM 另行叠加                               |
| Router / gate         | GPU               | GPU gate 后把 routed expert task 分发给 CPU             | router 仍需导出 expert id / workload                      |
| Shared expert         | GPU               | shared / hot experts 留 GPU                             | 保持高频 expert 低延迟                                    |
| Routed experts        | GPU HBM 或多卡 EP | routed experts 常驻 CPU DRAM，CPU 执行                  | 直接缓解 GLM-5.2 744B expert weight 容量压力              |
| Expert weights        | GPU HBM           | CPU DRAM / NUMA socket local memory                     | 减少 expert weight 经 PCIe 反复搬运                       |
| CPU compute           | 很少参与          | AMX / AVX 专家 kernel                                   | Kunpeng 需重测 SVE/SME，不能直接继承 AMX 结果             |
| Synchronization       | GPU 内部          | 异步 task queue、CUDA Graph / callback、Expert Deferral | 目标是让 CPU expert 与 GPU attention / shared expert 重叠 |

KTransformers 对 GLM-5.2 更直接，因为 GLM-5.2 后 75 层是 MoE。它解决的是 **expert weight 放不下和 expert miss 搬运慢**，而不是 attention KV cache 本身。项目精读也提醒：KTransformers 不能被简化成“MoE 权重放 CPU”，它的实际链路是 GPU shared experts + CPU routed experts + AMX/AVX/NUMA/CUDA Graph/Expert Deferral；迁移到 Kunpeng + Ascend 时，必须重新证明 SVE/SME expert kernel 与 CANN stream/callback 能力。

## 8. 横向对比：标准 GPU、NEO、KTransformers

| 模型组件 / 计算阶段      | 标准纯 GPU 推理                        | NEO                                                   | KTransformers                                          |
| ------------------------ | -------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------ |
| Tokenization / template  | CPU                                    | CPU                                                   | CPU                                                    |
| Scheduler                | CPU runtime，负责 batching             | CPU runtime 增加 load-aware offload decision          | CPU runtime 增加 expert task queue / overlap 调度      |
| Embedding                | GPU                                    | GPU                                                   | GPU                                                    |
| RMSNorm / RoPE           | GPU                                    | GPU                                                   | GPU                                                    |
| Q projection             | GPU                                    | GPU                                                   | GPU                                                    |
| compressed KV projection | GPU                                    | GPU；部分 KV 状态可转 CPU 侧                          | GPU                                                    |
| DSA indexer / IndexShare | GPU                                    | 原则上仍 GPU；CPU 适配难度高                          | GPU                                                    |
| Prefill attention        | GPU                                    | GPU 为主                                              | GPU                                                    |
| Decode attention         | GPU 读 HBM KV                          | 部分 request 在 CPU 上用 CPU-resident KV 做 attention | GPU                                                    |
| KV cache                 | GPU HBM                                | GPU-cache + CPU-cache 分裂                            | 主要仍 GPU HBM；可另接外部 KV 系统                     |
| Dense MLP                | GPU                                    | GPU                                                   | GPU                                                    |
| MoE router               | GPU                                    | GPU                                                   | GPU gate 后分发 expert task                            |
| Shared expert            | GPU                                    | GPU                                                   | GPU / hot path                                         |
| Routed expert            | GPU / 多卡 EP                          | 通常仍 GPU                                            | CPU DRAM 常驻 + CPU AMX/AVX 执行；hot experts 可在 GPU |
| Expert weight            | GPU HBM                                | 不重点处理                                            | CPU DRAM / NUMA + GPU hot expert cache                 |
| PCIe / DMA               | 单卡热路径基本不跨；多卡走 NVLink/PCIe | 传 Q / attention output 等小张量，避免整段 KV 来回搬  | CPU expert 输出 / 控制同步跨 PCIe                      |
| 主要收益                 | 简单、热路径短                         | 扩大有效 batch，降低 GPU HBM KV 压力                  | 大 MoE 本地化，减少 expert weight 搬运                 |
| 主要风险                 | HBM 容量不够，decode 带宽瓶颈          | CPU attention 带宽 / kernel 变瓶颈，overlap 不足      | CPU expert kernel 弱、NUMA/同步开销、精度变化          |

一句话概括：**标准 GPU 路径把所有热状态压在 HBM；NEO 把“部分 decode attention + KV”移到 CPU/DDR；KTransformers 把“routed experts”移到 CPU/DDR 并让 CPU 直接执行 expert。** 这两个方向正好对应 GLM-5.2 的两个关键压力面：NEO 对 KV / attention 压力有参考价值，KTransformers 对 MoE expert 权重压力更直接。

## 9. 对 A+K / 小算力一体机的落点

对 Ascend NPU + Kunpeng CPU，不建议直接照搬“GPU+CPU”的具体实现，而应抽象成三条工程路径。

第一，**标准主路径仍然应由 Ascend NPU 承担**：embedding、MLA/DSA attention、dense projection、router、hot experts、lm_head 都应优先在 NPU/HBM 内完成。热路径上引入 CPU 同步、DDR 访问或 SSD 小 I/O，会直接抬高 TPOT/P95/P99。

第二，**NEO 方向适合做 KV warm tier 和少量 decode attention 子路径实验**：Kunpeng DDR 放 inactive / CPU-request KV，CPU 只处理可重叠、低频、可批处理的 attention 子任务；是否成立必须以 `D2H/H2D bytes/token`、CPU attention latency、overlap ratio、TPOT/P99 为准。

第三，**KTransformers 方向适合做 MoE expert 分层**：NPU HBM 放 shared experts、non-expert 主干、hot routed experts、active KV 和 workspace；Kunpeng DDR 放 warm routed experts；SSD 放 cold experts。只有当 Kunpeng SVE/SME microbenchmark 证明某些 expert shape 有正收益时，才把 CPU expert execution 写成强路径。项目 GLM5.2 单卡优化材料也建议优先做 MoE expert hit rate、KV/Prefix 恢复与可观测闭环，而不是先主打完整 P/D 分离或 NPU-SSD 直通。

一个可执行的分析框架是：

```text
GLM-5.2 单层 trace schema:
  layer_id
  layer_type: dense / sparse_moe
  indexer_type: full / shared
  q_proj_latency
  kv_proj_latency
  indexer_latency
  attention_latency
  kv_read_bytes
  kv_write_bytes
  router_latency
  topk_expert_ids
  expert_hit_or_miss
  expert_load_bytes
  expert_compute_latency
  residual_norm_latency
  hbm_occupancy
  ddr_traffic
  dma_bytes
  stall_reason
```

用这套 schema 去跑标准 GPU、NEO-like、KTransformers-like 三种路径，才能回答真正的硬件问题：**GLM-5.2 每一层到底是被 attention/KV 卡住，还是被 expert weight / expert miss 卡住，还是被 runtime 调度和搬运卡住。**