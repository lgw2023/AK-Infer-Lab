## 一、核心结论

CPU+NPU / CPU+GPU 异构协同近两年的主线可以压缩成四类：

1. **NPU/GPU 负责高密度主路径**：prefill 大矩阵、decode 热路径、DiT/diffusion 主干、热专家计算。
2. **CPU 不再只是 host**：CPU 开始承担 attention 子计算、KV/专家选择、稀疏/短序列计算、工具执行、检索、调度、压缩、恢复、预取。
3. **异构协同的收益边界由“搬运成本”决定**：细粒度 offload 只有在计算收益大于 PCIe/UB/DRAM/SSD 搬运成本时成立。
4. **小算力场景优先做“任务/阶段级协同”，不要先做“大集群级协同”**：Mini 工作站优先做 CPU 工具链和轻量 offload；塔式工作站优先做大 DRAM/NVMe + MoE/KV 分层；2–8 节点小集群再考虑跨节点专家池和内存池。

------

## 二、代表论文：按方向 + 会议整理

### 方向 A：端侧 / 本地 NPU 协同推理

| 会议 / 时间              | 论文与机构                                                   | 背景需求与问题                                               | 核心策略                                                     | 结果收益与评估                                               | 核心贡献                                                     | 对小算力一体机的启发                                         |
| ------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| ASPLOS 2025 / arXiv 2024 | **Fast On-device LLM Inference with NPUs / llm.npu**；PKU、BUPT 等 | 移动端 LLM 受 prefill 时延限制，NPU 有高吞吐但图编译、动态长度、outlier、算子支持会拖累收益。 | 从 prompt、tensor、block 三层重构：prompt 切固定块；outlier 放 CPU/GPU；Transformer block 按硬件亲和性在 CPU/GPU/NPU 间乱序调度。 | prefill 平均快 22.4×，能耗节省 30.7×，真实应用最高 32.8× 加速；首次在 billion 级模型上实现 >1000 tokens/s prefill。([arXiv](https://arxiv.org/abs/2407.05858?utm_source=chatgpt.com)) | 明确提出“不是整图扔给 NPU，而是按 prompt/tensor/block 分层 offload”。 | A+K 可迁移为：NPU 承担密集块，Kunpeng 处理 outlier、tokenizer、小算子、依赖管理和 fallback；适合 Mini 工作站先做原型。 |
| arXiv 2024               | **PowerInfer-2**；上海交大 IPADS                             | 手机内存不足，传统小模型牺牲能力；大模型超出内存后，粗粒度 offload 导致 I/O 崩溃。 | 把矩阵分成 neuron clusters：高密激活簇走 NPU，稀疏簇走 CPU；存储侧用 segmented neuron cache 和 I/O-compute pipeline。 | 相比 SOTA 框架最高 27.8× 加速；首次在手机上跑 47B LLM，达到 11.68 tokens/s。([arXiv](https://arxiv.org/abs/2406.06282?utm_source=chatgpt.com)) | 把“计算分块”和“存储分块”统一到 neuron cluster 粒度。         | 对 A+K 的直接启发是冷专家、稀疏块、低频权重不必常驻 NPU；可以让 CPU+SSD/SLC 承接冷路径。 |
| arXiv 2026               | **llada.cpp: Efficient On-Device Diffusion LLM Inference with Mobile NPU** | diffusion LLM 在移动端能并行生成多个 token，但重复 denoising 计算重，NPU 可用但地址空间、remap、KV 复用复杂。 | Multi-block speculative decoding、CPU-side progressive revision、swap-optimized memory runtime。 | 在多平台上让 LLaDA-8B 相比 CPU baseline 降低 17×–42× 生成时延，并保持质量。([arXiv](https://arxiv.org/abs/2606.13740?utm_source=chatgpt.com)) | 证明扩散式 LLM 也需要 CPU/NPU 双路径：NPU 保持密集执行，CPU 处理可修订 token 和状态控制。 | 对 AR+DiT / 多模态生成有启发：CPU 做修订、调度、状态整理，NPU 持续跑密集主干。 |

### 方向 B：CPU+GPU 协同 Attention / KV / Offload

| 会议 / 时间             | 论文与机构                                                   | 背景需求与问题                                               | 核心策略                                                     | 结果收益与评估                                               | 核心贡献                                                     | 对小算力一体机的启发                                         |
| ----------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| MLSys 2025 / arXiv 2024 | **NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference**；Xuanlin Jiang、Ion Stoica、Minlan Yu 等 | GPU 显存限制 batch size，导致 GPU 算力空闲；简单把 KV 放 CPU 会增加延迟。 | 将部分 attention compute 和 KV cache state 卸载到 CPU；采用 asymmetric GPU-CPU pipeline 与 load-aware scheduling。 | 在 T4/A10G/H100 上分别最高提升 7.5×、26%、14% 吞吐且保持相同延迟；更强 CPU 下 A10G 最高提升 79.3%。([arXiv](https://arxiv.org/abs/2411.01142?utm_source=chatgpt.com)) | 将 CPU 从“存放 KV 的内存池”提升为“参与 attention 计算的协处理器”。 | 对 A+K 极关键：Kunpeng 可承担部分 KV/attention/短序列计算，换取 NPU 更大 batch 和更少 HBM 压力。 |
| ISCA 2025               | **LIA: Cost-efficient LLM Inference Acceleration with Intel AMX and CXL**；Google DeepMind 等 | 单 GPU 容量不足，频繁 CPU-GPU 传输过慢；新 CPU AMX 使 CPU 矩阵吞吐接近部分 GPU。 | AMX CPU+GPU 协同计算；把 CXL memory 与 DDR 统一作为 offload 层。 | 在单 H100 + Sapphire/Granite Rapids 上，延迟最高降低 5.1×/19×，吞吐最高提升 3.7×/5.1×；CXL 额外提升 1.5× 吞吐并把最大 batch 从 900 提到 1.6K。([Google DeepMind](https://deepmind.google/research/publications/81986/)) | 证明强 CPU 能承接更多矩阵子计算，不只是搬运和控制。          | Kunpeng 没有 AMX 等价能力时不能照搬，但可迁移方法论：先测 CPU 矩阵/向量能力，再决定哪些算子放 CPU。 |
| arXiv 2026              | **HybridGen: Efficient LLM Generative Inference via CPU-GPU Hybrid Computing** | 长上下文 KV 可达数百 GB，单靠 GPU 或 CPU attention 都不充分；CXL/分层内存带来新放置空间。 | CPU-GPU collaborative attention；attention logit parallelism；feedback-driven scheduler；semantic-aware KV mapping。 | 在 3 种 GPU、CXL 扩展内存和多尺寸模型上，相比 6 种 KV 管理方法平均快 1.41×–3.2×。([arXiv](https://arxiv.org/abs/2604.18529?utm_source=chatgpt.com)) | 把长上下文 attention 变成 CPU/GPU 共同执行，而非单纯 KV offload。 | 对塔式工作站最有价值：大 DDR/SLC 承接长上下文，CPU 做部分 attention/KV 选择，NPU/GPU 保留热路径。 |
| MLSys 2026 / arXiv 2026 | **SuperInfer: SLO-Aware Rotary Scheduling and Memory Management for Superchips**；Jiahuan Yu、Minjia Zhang 等 | GH200 类 CPU-GPU superchip 有 NVLink-C2C，但现有 PCIe offload 策略无法满足高请求率下 TTFT/TBT SLO。 | RotaSched 主动轮转请求；DuplexKV 做 CPU-GPU full-duplex KV 传输。 | 在 GH200 上 TTFT SLO 达成率最高提升 74.7%，同时保持相近 TBT 和吞吐。([arXiv](https://arxiv.org/abs/2601.20309?utm_source=chatgpt.com)) | 给出了“CPU-GPU 紧耦合内存 + SLO 调度”的上界样板。            | 对 A+K 是目标形态参考，不是直接照搬；若 UB/PCIe 带宽远低于 NVLink-C2C，应只迁移 SLO-aware rotation 和 KV transfer discipline。 |
| arXiv 2025              | **APEX: Parallel CPU-GPU Execution for LLM Inference on Constrained GPUs** | 受限 GPU decode 阶段带宽受限，已有 CPU offload 调度不能充分和 GPU 执行重叠。 | profiling-informed scheduler，预测 CPU/GPU 子任务时间，最大化 overlap。 | T4 上吞吐提升 84%–96%，A10 上提升 11%–89%；相比已有 hybrid scheduler，长输出场景最高再提升 49%/37%。([arXiv](https://arxiv.org/abs/2506.03296?utm_source=chatgpt.com)) | 把“CPU-GPU overlap”做成可预测调度问题。                      | A+K 应建立算子/阶段 profiler，用预测模型决定 CPU/NPU 分工，而不是静态规则。 |
| arXiv 2025              | **CLO: CPU-Light KVCache Offloading**                        | 传统 KV offload 把细粒度 cache 管理和 gather 放在 CPU，CPU 自身变成瓶颈。 | GPU-centric synchronization、zero-copy transfer、coarse-grained head-wise on-GPU caching。 | 在两个 LLM 上保持精度，同时 decode 吞吐提升 9.3%–66.6%。([arXiv](https://arxiv.org/abs/2511.14510?utm_source=chatgpt.com)) | 提醒 CPU offload 不是越多越好，CPU 侧细粒度动态管理会反噬。  | 对 A+K 是重要边界条件：Kunpeng 应做“粗粒度元数据 + 批量搬运 + 聚合”，避免被碎片 KV 管理拖垮。 |

### 方向 C：MoE / 专家权重的 CPU-GPU 协同卸载

| 会议 / 时间              | 论文与机构                                    | 背景需求与问题                                               | 核心策略                                                     | 结果收益与评估                                               | 核心贡献                                                   | 对小算力一体机的启发                                         |
| ------------------------ | --------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ---------------------------------------------------------- | ------------------------------------------------------------ |
| ASPLOS 2025 / arXiv 2024 | **MoE-Lightning**；UC Berkeley、Stanford 等   | MoE 总参数大，低成本 GPU 放不下；传统 offload CPU/GPU/I/O 利用率低。 | CGOPipe：CPU-GPU-I/O 流水；paged weights；Hierarchical Roofline Model 寻优。 | 在单 T4 16GB 上 Mixtral 8×7B 比 SOTA offloading 系统最高 10.3× 吞吐；支持 Mixtral 8×22B、DBRX 在 2–4 张低成本 GPU 上 batch inference。([arXiv](https://arxiv.org/abs/2411.11217?utm_source=chatgpt.com)) | 把 MoE 权重加载、CPU 内存、GPU 计算、I/O 统一流水化。      | 直接对应 GLM5.2/DSv4 Flash：热专家常驻，温专家预取，冷专家落 DDR/SSD/SLC。 |
| arXiv 2025               | **fMoE: Fine-Grained Expert Offloading**      | 粗粒度 expert offload 要么延迟高，要么内存占用高。           | 提取 expert selection pattern 和 prompt semantic hints，指导 expert prefetch/cache/offload。 | 在 6-GPU testbed 上推理延迟降低 47%，expert hit rate 提升 36%。([arXiv](https://arxiv.org/abs/2502.05370?utm_source=chatgpt.com)) | 把语义 hint 与专家预取关联起来。                           | Coding/办公 Agent 的 session/task 类型可作为专家热度预测输入；适合塔式工作站原型。 |
| arXiv 2025               | **MoE-SpeQ**                                  | 专家选择数据依赖强，miss expert 走 PCIe 拉取会卡关键路径。   | 小 draft model 预测未来 token 所需专家，提前从 host memory prefetch；amortization roofline 动态调 speculation。 | 在资源受限设备上，Phi-MoE 最高比 SOTA offloading 快 2.34×。([arXiv](https://arxiv.org/abs/2511.14102?utm_source=chatgpt.com)) | 用“便宜的预测计算”隐藏“昂贵的专家搬运”。                   | A+K 可用小模型/历史路由预测专家，CPU 提前准备冷专家，NPU 不等 I/O。 |
| arXiv 2026               | **CoX-MoE: AMX-enabled CPU-GPU Co-Execution** | MoE expert 微批导致 operational intensity 低，CPU offload 又受 PCIe 限制。 | coalesced expert execution；static expert-aware stratification；频繁专家上 GPU，CPU/GPU 协同执行。 | 相比 FlexGen 和 MoE-Lightning，最高分别 7.1× 和 2.4× 吞吐提升。([arXiv](https://arxiv.org/abs/2605.17889?utm_source=chatgpt.com)) | 强调专家执行不能过度微批，要把专家合并成更适合硬件的粒度。 | Kunpeng 侧适合做“专家分层 + 冷专家合批 + 索引/预取”，不要让 NPU 被碎专家 miss 打断。 |
| arXiv 2025               | **MoE-Gen**                                   | 单 GPU 上连续 batching 会让 MoE attention/expert 模块 batch 太小，吞吐低。 | module-based batching：在 host memory 累积 token，对 attention/expert 分模块启动大 batch。 | 相比 FlexGen、MoE-Lightning、DeepSpeed 等 model-based batching，吞吐提升 8×–31×；代码公开。([arXiv](https://arxiv.org/abs/2503.09716?utm_source=chatgpt.com)) | 将 MoE 调度粒度从 request/model 提升到 module。            | 对一体机离线批处理、后台代码索引、企业知识批量生成有价值；交互场景需控制排队延迟。 |
| arXiv 2025               | **MoE-Lens**                                  | 资源受限环境下 CPU/GPU 混合 MoE 推理缺少能预测硬件上限的模型。 | holistic performance model，分析 CPU memory、GPU compute、workload 与系统执行机制。 | 平均比 SOTA 快 4.6×，最高 25.5×；模型预测准确率平均 94%。([arXiv](https://arxiv.org/abs/2504.09345?utm_source=chatgpt.com)) | 给出 MoE 系统瓶颈建模方法，而非只给一个调度策略。          | A+K 需要类似模型反推“专家常驻数量、DDR 带宽、SSD IOPS、CPU 参与度”的甜点。 |

### 方向 D：边缘 / 一体机异构系统的能效、适配器、多租与测量

| 会议 / 时间                   | 论文与机构                                                   | 背景需求与问题                                               | 核心策略                                                     | 结果收益与评估                                               | 核心贡献                                               | 对小算力一体机的启发                                         |
| ----------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------ | ------------------------------------------------------------ |
| ATC/Edge 方向，arXiv 2025     | **CLONE: Customizing LLMs for Latency-Aware Edge Inference** | 边缘设备受存储、重量、功耗限制，必须同时平衡延迟、能耗和精度。 | 算法-硬件协同，在模型级和系统级做实时能耗优化，并设计 28nm 可扩展加速器。 | 在两类边缘平台上，推理最高加速 11.92×，能耗最高降低 7.36×。([arXiv](https://arxiv.org/abs/2506.02847?utm_source=chatgpt.com)) | 证明边缘部署不能只做模型压缩，要做算法-系统-硬件联合。 | A+K 小算力应把能耗、功耗封顶、温度、任务质量纳入同一调度目标。 |
| MobiSys/Edge 方向，arXiv 2025 | **EdgeLoRA**                                                 | 企业/部门本地 Agent 常需多 LoRA，多租边缘设备频繁 adapter swap 会增加内存和延迟。 | adaptive adapter selection、heterogeneous memory management、adapter caching/pooling、batch LoRA inference。 | Llama3.1-8B 上吞吐最高 4×，可同时服务数量级更多 adapters。([arXiv](https://arxiv.org/abs/2507.01438?utm_source=chatgpt.com)) | 把 LoRA 也作为异构内存管理对象。                       | 办公/企业 Agent 一体机需要 CPU DRAM 管理 adapter 池，NPU 只常驻热点 adapter。 |
| SEC/Edge 方向，arXiv 2025     | **lm-Meter**                                                 | 端侧 LLM 缺少 phase/kernel 级可见性，无法判断瓶颈在 embedding、prefill、decode、softmax 还是 sampling。 | 轻量在线 latency profiler，采集 phase 与 kernel 级时延。     | 在商用移动平台上 profiling overhead 很低；prefill 吞吐下降 2.58%，decode 下降 0.99%。([arXiv](https://arxiv.org/abs/2510.06126?utm_source=chatgpt.com)) | 给出端侧异构运行时的测量底座。                         | A+K 原型必须先做 phase-level profiler，再谈 CPU/NPU placement。 |
| arXiv 2025                    | **FUSE: Unified Energy-Aware Governor for Mobile LLM Inference** | 移动端 CPU/GPU/Memory DVFS governor 独立工作，导致 LLM prefill/decode 延迟和能耗错配。 | 统一 CPU/GPU/Memory 频率调度，根据 prefill/decode 长度选择 governor。 | 在相同 energy/token 下，TTFT 降低 7.0%–16.9%，TPOT 降低 25.4%–36.8%。([arXiv](https://arxiv.org/abs/2507.02135?utm_source=chatgpt.com)) | 将“异构协同”扩展到功耗/频率控制。                      | 一体机持续运行时，CPU/NPU/DRAM/SSD 也需要统一功耗调度，不应只看短时峰值。 |
| HPCA/Sim 方向，arXiv 2026     | **LLMServingSim 2.0**；KAIST 等                              | 异构 serving 需要同时建模硬件、调度、offload、cache、路由和功耗，现有模拟器割裂。 | runtime-driven simulator，统一 batching、routing、offloading、memory、power 建模。 | 对真实部署的性能、内存、功耗指标平均误差 0.97%，复杂配置模拟约 10 分钟。([arXiv](https://arxiv.org/abs/2602.23036?utm_source=chatgpt.com)) | 把异构硬件/服务系统 co-design 变成可扫描问题。         | A+K 必须建设仿真器：先扫 CPU 核数、UB/PCIe 带宽、DDR/NVMe、NPU 算力配比，再定规格。 |

------

## 三、按方向综合分析：挑战 → 研究现状 → 趋势 → 技术布局

### 方向 A：CPU+NPU 端侧 / 本地协同

**主要挑战：**
小算力一体机里的 NPU 适合高密度矩阵，但对动态长度、outlier、控制流、小算子、数据依赖和频繁 remap 不友好；

CPU 灵活但算力/带宽有限，细粒度 offload 一旦切得过细，UB/PCIe 搬运和同步开销会吞掉 NPU 的收益。

**当前研究路线：**
一条路线是 **NPU 主算 + CPU/GPU 处理 outlier / fallback**；

一条路线是 **按稀疏激活或 neuron cluster 分配 CPU/NPU**；

新兴路线是 **NPU 保持密集执行，CPU 处理修订、状态和调度**。

**未来趋势：**
2026–2027 年会从手工规则走向 profile-driven placement；

2027–2029 年需要统一异构 runtime，把 prompt、block、tensor 的 placement 策略标准化；

2029–2031 年可能进入 NPU 可见地址空间、统一内存、NPU 直连存储和更低开销图编译阶段。

**技术布局：**
挑战/趋势 → 构建 **A+K phase/block placement profiler** → 形成“prefill 大块上 NPU、outlier/小矩阵/索引上 CPU、状态管理在 CPU”的策略。
挑战/趋势 → 探索 **CPU SVE/OMP + NPU AICore 协同内核集** → 达到 KV 相似度、短序列矩阵、prefix 匹配、向量检索的 CPU 侧卸载。
挑战/趋势 → 构建 **NPU-visible memory / staging runtime** → 降低 remap、copy、同步对端到端时延的影响。

### 方向 B：CPU+GPU/NPU Attention、KV 与长上下文协同

**主要挑战。**
长上下文下 KV 容量和带宽同时爆炸。CPU/DRAM 可以扩容量，但 CPU 细粒度管理和 PCIe gather 很容易成为新瓶颈；CPU-heavy KV offload 会引入 cache 管理、PCIe 利用率和同步气泡问题。

**当前研究路线。**
NEO 把部分 attention compute 和 KV state 下放 CPU；LIA 用强 CPU AMX + CXL memory 扩展单 GPU；HybridGen 把 CPU-GPU attention 变成协同计算；SuperInfer 则展示紧耦合 superchip 上 SLO-aware KV rotation 的上界。([arXiv](https://arxiv.org/abs/2411.01142?utm_source=chatgpt.com))

**未来趋势。**
CPU 会从“KV parking lot”变成“long-context attention 协处理器”；但是否值得做取决于 CPU 算力、链路带宽、NUMA、DDR/CXL 带宽和 NPU/GPU 内核可插拔性。紧耦合 CPU-GPU/NPU 架构会显著优于传统 PCIe 松耦合，但 Mini 工作站短期不应假设具备 GH200 级别链路。

**技术布局。**
挑战/趋势 → 构建 **CPU-light KV offload** → 形成“粗粒度元数据、批量搬运、GPU/NPU-centric sync”的策略。
挑战/趋势 → 探索 **Hybrid Attention on A+K** → CPU 只处理长尾/冷 KV/低优先级 attention，NPU 处理热路径。
挑战/趋势 → 建立 **link-aware cost model** → 若 CPU↔NPU 搬运成本高于重算成本，策略自动回退为重算或压缩。

### 方向 C：MoE 专家权重与 CPU-GPU/NPU 协同

**主要挑战。**
MoE 的核心问题不是 FLOPs，而是专家权重容量、miss expert 拉取、PCIe/UB 带宽、expert hit rate、负载不均衡。对 200B–700B+ 稀疏模型，单纯量化仍不够，需要专家级热温冷分层。

**当前研究路线。**
MoE-Lightning 做 CPU-GPU-I/O 流水和 paged weights；fMoE 用语义 hint 做专家预取；MoE-SpeQ 用 draft model 预测未来专家；CoX-MoE 和 MoE-Lens 强调 CPU/GPU 协同必须通过性能模型和 expert stratification 寻优。([arXiv](https://arxiv.org/abs/2411.11217?utm_source=chatgpt.com))

**未来趋势。**
MoE serving 会从“专家均衡”转向“专家生命周期管理”：热专家常驻，温专家预取，冷专家低精度/延迟加载，CPU 管索引和 fallback，小模型预测专家轨迹。

**技术布局。**
挑战/趋势 → 构建 **A+K expert object layer** → 每个 expert 具备 hotness、last_used、session_affinity、precision、resident_tier。
挑战/趋势 → 探索 **layer-wise expert prefetch + CPU-side index** → 降低 miss expert 对 TPOT 的冲击。
挑战/趋势 → 建立 **MoE roofline + trace replay** → 反推 HBM/Bailu 容量、DDR 带宽、SSD IOPS、CPU 核数和 NPU batch 甜点。

### 方向 D：边缘 / 一体机的能效、适配器、多租和测量

**主要挑战。**
本地一体机和云服务不同：并发少但链路长，工具和检索多，功耗/噪声/热限制强，CPU/DRAM/NVMe 可能比 NPU 更早成为端到端瓶颈。CLONE、lm-Meter、FUSE 和 EdgeLoRA 都证明，端侧系统不能只看模型 tokens/s。([arXiv](https://arxiv.org/abs/2506.02847?utm_source=chatgpt.com))

**当前研究路线。**
CLONE 走算法-硬件协同；EdgeLoRA 走 adapter 缓存和异构内存；lm-Meter 走 phase/kernel 级 profiling；FUSE 走 CPU/GPU/Memory 统一 DVFS；LLMServingSim 2.0 走异构仿真与 co-design。([arXiv](https://arxiv.org/abs/2602.23036?utm_source=chatgpt.com))

**未来趋势。**
一体机研发会从“买硬件 + 跑模型”转向“trace → profiler → simulator → placement → prototype”的闭环。没有这个闭环，A+K 协同很容易变成经验调参。

**技术布局。**
挑战/趋势 → 构建 **A+K phase-level profiler** → 输出 embedding/prefill/decode/tool/KV/I/O 的阶段时延和资源归因。
挑战/趋势 → 构建 **A+K serving simulator** → 支持 CPU 核数、DDR 带宽、SSD IOPS、NPU 近端容量、UB/PCIe 带宽的 what-if 扫描。
挑战/趋势 → 建立 **energy-aware runtime** → 用 Tasks/J、P95 JCT、TPOT、温度和质量损失共同评价，而不是只看 tokens/s。

------

## 四、面向 A+K 的建议优先级

**P0：近期必须做。**
第一，复现 NEO / APEX / CLO 这类 CPU+GPU 协同思想到 A+K：先做 CPU/NPU 阶段 profiler，再决定哪些 attention/KV/短矩阵可以下沉 CPU。第二，复现 MoE-Lightning / fMoE 的专家分层：做热专家常驻、温专家预取、冷专家 DDR/SSD/SLC 延迟加载。第三，把 llm.npu 的 prompt/tensor/block 三层拆分思想迁移到 Ascend：不要整图 offload，按动态长度、outlier、硬件亲和性拆。

**P1：中期形成平台能力。**
构建 A+K 异构运行时：统一对象包括 KV、prefix、expert、adapter、embedding index、tool result；统一动作包括 place、prefetch、evict、compress、recover、pin、migrate。构建 link-aware cost model：如果 UB/PCIe/DDR/SSD 搬运超过收益，自动选择重算、压缩或降低精度。

**P2：长期芯片/整机诉求。**
下一代一体机真正要争取的不是单点 TOPS，而是 **近端容量 × 有效带宽 × 可编程搬运语义 × 可观测运行时**。Mini 工作站重在低成本、低噪声、开箱即用；塔式工作站重在大 DRAM/NVMe、MoE/KV 分层、CPU 工具链；2–8 节点小集群重在跨节点内存池、专家池和会话局部性。