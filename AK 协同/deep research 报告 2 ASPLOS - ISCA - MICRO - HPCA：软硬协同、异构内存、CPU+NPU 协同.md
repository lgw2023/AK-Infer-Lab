# 面向小算力一体机与小型服务器的本地 Agent 计算体系结构深度调研

## 核心判断

把本地 Agent 跑在 Mini 工作站、塔式工作站、一体机，甚至 2–8 节点小集群上，核心矛盾已经不是“峰值 TOPS / TFLOPS 够不够”，而是**每个推理阶段对近端内存容量、有效带宽、KV 容量、状态搬运路径和软件运行时的需求完全不同**。Splitwise、DistServe、WindServe 与 SuperInfer 的共同结论是：Prefill 与 Decode 的性能主导项不同，强行共址往往会导致 TTFT 与 TPOT 相互干扰；而 Mooncake、LMCache、SGLang HiCache/HiSparse、Dynamo/NIXL 则说明，现代推理系统越来越像“分层存储操作系统”，在管理 KV、前缀、专家和状态，而不只是调一个 GEMM 内核。citeturn2search4turn18search0turn21search3turn2search2turn2search13turn3search8turn3search5turn8search13turn27search10turn16search2

对“小算力一体机/塔式工作站/小型服务器”来说，最值得借鉴的大机思路并不是简单堆更多 GPU，而是三件事：**阶段分治、状态分层、异构协同**。阶段分治指把 Prefill、Decode、Embedding/Rerank、检索/工具、KV 管理拆成不同资源池；状态分层指把权重、KV、MoE 专家、Adapter、向量索引、工具结果按热度放到 SRAM/HBM/LPDDR/DDR/NVMe；异构协同则是让 CPU 负责调度、检索、I/O、压缩、分页、故障恢复和工具执行，让 GPU/NPU 只承担最适合它们的稠密矩阵计算与热点注意力。LIA、llm.npu、Hybe、Apple 的 MLX/ANE 工作，以及华为 MindIE/vLLM-Ascend 的公开资料，几乎都沿着这条路线在推进。citeturn20search0turn21search1turn21search2turn24search2turn24search9turn4search2turn4search5turn3search6turn4search14

从硬件趋势看，**统一内存/一致性内存不是“替代 HBM”的魔法，而是“降低搬运与编程复杂度”的结构性能力**。NVIDIA GH200/Grace-Blackwell 通过 NVLink-C2C 暴露统一地址空间与高带宽一致性内存；AMD Ryzen AI Max 和 MI300A 用 UMA/统一 HBM 把“本地大模型能否放得下”从显存问题变成整机共享内存问题；Apple MLX 则把统一内存做成了软件默认抽象。它们共同降低了“模型 fit 不下、状态来回拷”的门槛，但并没有消掉 decode 阶段对**热点权重/KV 高带宽驻留**的刚性需求。DAK、CXL/远端内存研究与 NVIDIA 的 CPU-GPU memory sharing 资料都说明：只要热路径落到更慢一层，decode 仍会明显掉速；因此一致性内存更像**温层**或**过渡层**，而不是热层。citeturn5search0turn5search8turn27search0turn5search15turn5search6turn5search2turn26search4turn26search7turn24search2turn1search5turn19search6turn19search9turn19search2

对 Ascend NPU + Kunpeng CPU 的 A+K 协同，我的判断是：**体系结构思想高度可迁移，真正的难点在软件接口与运行时成熟度，而不是理念不兼容**。华为官方已经把推理开发入口分成 MindIE、vLLM、SGLang 三类，并公开强调 MindIE 的调度、服务化、量化、多机弹性推理、MoE 动态调度、序列并行与低时延通信；vLLM-Ascend 官方文档也明确说明它是社区维护的硬件插件。也就是说，A+K 协同最现实的路线不是“照搬 CUDA 生态”，而是把上述通用思想翻译为 CANN/HCCL/MindIE/vLLM-Ascend 语义下的**分页 KV、分层缓存、异构 P/D、MoE 放置与可观测性**。citeturn4search2turn4search5turn4search12turn4search14turn3search6turn3search10turn25search16turn25search18

## 负载阶段与资源需求矩阵

下表是对本地 Agent 常见阶段的资源画像综合归纳，依据了 Splitwise/DistServe 对 Prefill/Decode 差异的刻画，LMCache/Mooncake/HiCache/HiSparse 对 KV 状态分层的实现，llm.npu/LIA/Hybe/NPUMoE 对 CPU-GPU-NPU 异构执行的拆分，以及华为 TEI/MindIE 对 Embedding、Rerank 和服务化场景的公开说明。citeturn2search4turn18search0turn3search8turn2search13turn3search5turn8search13turn21search1turn20search0turn21search2turn24search1turn4search13turn4search2

| 负载阶段 | 主要算子与行为 | 首要资源 | 次要资源 | 更适合的执行硬件 | 更适合的状态驻留 |
|---|---|---|---|---|---|
| Prefill | 大 batch / 长序列 GEMM + 注意力，追求 TTFT | 稠密算力、近端带宽、注意力 kernel 效率 | Prompt 前缀复用、编排开销 | GPU/NPU 优先；CPU 负责分词、编排、前缀命中 | 权重与热点激活放 HBM/GDDR/统一内存热区；可复用前缀放 DDR/NVMe |
| Decode | 小步长、反复读取权重与 KV，追求 TPOT/TBT | **有效内存带宽、KV 热点驻留、低抖动调度** | 小量算力、跨阶段状态传递 | GPU/NPU 主算；CPU 负责调度、草稿模型、异常路径 | 活跃层权重与热点 KV 放近端内存；冷 KV 进 DDR/CXL/NVMe |
| Embedding / Rerank | 编码器类全序列计算，可批处理 | 中高算力、适中带宽 | 低延迟服务化、批处理调度 | CPU、GPU、NPU 都可；取决于 QPS 和模型大小 | 小模型可常驻 CPU/DDR；高 QPS 时驻留 GPU/NPU |
| 工具执行 | Python/JS/数据库/API/文件系统等不规则工作负载 | 单核性能、系统调用、I/O 并发 | 序列化/反序列化、缓存命中 | **CPU 明显更合适** | DRAM + NVMe；结果对象可做短期缓存 |
| 检索 / 数据库 | 向量检索、BM25、KV/文档读写、随机 I/O | DRAM 容量、SSD 带宽/IOPS、索引局部性 | SIMD/多线程、网络 | CPU 主导；大批量 rerank 可转 GPU/NPU | 索引热段放 DRAM，冷段放 NVMe；结果摘要可回写 KV 缓存 |
| KV 状态存取 | 前缀命中、页表、压缩/解压、迁移、恢复 | 内存层级带宽、页管理、DMA/拷贝路径 | 持久化与可观测性 | CPU + Runtime 是主角；必要时借助 GPU/NIXL/GDS | HBM 热页、DDR 温页、NVMe 冷页，必要时远端共享 |
| 多模态编码 / 解码 | 视觉/音频编码器 + 文本主干 + 媒体解码 | 近端内存、编码器吞吐、跨模态张量共享 | 媒体 I/O、前缀复用 | 图像/视频编码器多在 GPU/NPU；媒体前处理多在 CPU | 视觉特征缓存放近端或 DRAM；重复图像/视频片段适合前缀缓存 |

如果只记住一条经验，那就是：**Prefill 更像“高并行、高吞吐、可批处理”的密集计算问题，Decode 更像“低算强度、强带宽依赖、强状态局部性”的内存系统问题**。这也是为什么 Splitwise 与 DistServe 都主张按阶段切开资源；为什么 FlashAttention-4 继续围绕共享内存流量和 softmax 非 matmul 开销优化；以及为什么 SuperInfer、HiSparse、FlexiCache、Kitty、NVFP4 KV 这类工作都在围着 decode 的“热状态/热页/热通道”做文章。citeturn2search4turn18search4turn15search2turn2search2turn8search13turn7search13turn9search3turn27search14

对于本地 Agent，真正拖慢端到端体验的往往不是单独某个 LLM token，而是**多阶段串联后的尾延迟**：RAG 检索、Rerank、工具调用、文件/数据库 I/O、视觉编码、KV 恢复、模型热切换都会叠到 p95/p99 上。多阶段推理建模工作已经开始把“硬件簇 + KV 存储 + 推理阶段”看成统一优化对象，这对小型本地系统尤其重要，因为你没有云端那样可以靠超额冗余去掩盖抖动。citeturn22search10turn22search20turn4search13turn25search10

## 技术机制与硬件层级矩阵

用户给出的“SRAM、HBM/GDDR、LPDDR/DDR、NVMe、PCIe/C2C、节点网络、软件 Runtime”七层划分非常正确；补充一点：**CXL 在这张表里最好理解为“通过 PCIe/CXL 链路暴露出来的字节寻址扩展内存层”**，因此它同时影响“LPDDR/DDR 侧的远端扩展能力”和“PCIe/C2C 侧的传输语义”。下表把主流机制映射到这七层。支撑证据主要来自 FlashAttention-4、Mooncake/LMCache/HiCache、Kitty/FlexiCache/OPKV、Splitwise/DistServe/SuperInfer、CRAFT/MoE Tax/FarSkip-Collective，以及 NVIDIA/AMD/Intel/CXL Consortium/华为的官方资料。citeturn15search2turn2search13turn3search8turn3search5turn9search3turn7search13turn9search2turn2search4turn18search0turn2search2turn10search3turn10search2turn16search3turn5search0turn5search8turn26search4turn6search12turn6search13turn4search2

| 技术机制 | SRAM | HBM / GDDR | LPDDR / DDR | NVMe | PCIe / C2C | 节点网络 | 软件 Runtime |
|---|---|---|---|---|---|---|---|
| FlashAttention / kernel fusion | 依赖 tile 复用、共享内存、寄存器压缩中间态 | 减少显存往返与非必要读写 | 基本不直接受益 | 无 | 无 | 无 | 需要自动调参与 kernel 选择 |
| KV 量化与稀疏化 | 存放临时 dequant / top-k 元数据 | 热页与高精度通道优先保留 | 冷页/稳定头页可下放 | 可做冷快照 | 页迁移与批量搬运关键 | 可用于远端共享 | 需要分页、量化、命中预测协同 |
| Prefix / 外置 KV Cache | 元数据与索引表 | 作为 L1 热缓存 | 作为温层缓存与跨请求复用池 | 作为 L3 持久层 | 决定本地搬运成本 | 决定远端命中收益 | 核心在 cache API、pin/lookup/cleanup/move |
| Prefill / Decode 分离 | 无特殊需求 | 两阶段各自维护热集 | CPU 侧做 staging / overflow | 可承接冷数据 | 单机内切依赖 C2C/PCIe 低抖动 | 多机切分高度依赖网络 | 调度器必须理解 TTFT 与 TPOT 双目标 |
| MoE 专家预取 / 复制 / 负载均衡 | Router 元数据与小型表项 | 热专家常驻、热门层复制 | 冷专家或 CPU fallback | 超冷专家/检查点 | 预取与专家装载路径 | all-to-all / P2P 成本决定上限 | 需要热度模型、预测器与复制预算器 |
| 统一内存 / 一致性内存 | 让热工作集更容易在片上保留 | 仍是最热层 | 成为“可访问但更慢”的温层 | 冷数据更易映射进入地址空间 | **C2C/UMA 是关键启发** | 单机内收益大于多机 | 运行时必须做 residency 控制，防止 page thrash |
| Direct Storage / GDS / NIXL | 可减少中间拷贝 staging | 数据直接落到加速器侧 | 绕开部分 host bounce buffer | 成为主动流式数据源 | 链路拓扑决定真实收益 | NVMe-oF / 对象存储可扩展 | 需要统一的数据搬运抽象 |
| CPU-GPU/NPU 协同执行 | NPU/CPU scratchpad 与小缓存 | 只放最适合 GPU/NPU 的稠密热点 | 工具、检索、冷状态、异常路径主要在此层 | 冷状态与恢复层 | 离散 NPU/GPU 时尤受链路影响 | 小集群通常只在同步与共享时需要 | 调度器要理解算子亲和性与图编译约束 |

把这张矩阵翻译成面向一体机/塔式工作站的工程原则，就是：**SRAM 解决的是“每次算子如何少搬一次”，HBM/GDDR 解决的是“热状态能否待在近端”，LPDDR/DDR 解决的是“整机能否放得下”，NVMe 解决的是“长期状态能否养得起”，PCIe/C2C/网络决定的是“切分之后值不值得”，而 Runtime 决定的是“这些层能否被真正用起来”**。NVIDIA 的 NIXL、Dynamo 与 CPU-GPU memory sharing，Mooncake/LMCache 的缓存控制 API，SGLang HiCache/HiSparse 的层级缓存，Intel Xeon 6 的 CXL/DSA/QAT，以及华为 MindIE 的调度/服务化/量化，实际上都在把 Runtime 变成“存储层级控制面”。citeturn16search2turn27search10turn27search0turn2search13turn3search8turn3search5turn8search13turn6search12turn4search5turn25search16

对小算力系统最重要的启发是：**不要把 DDR/NVMe/CXL 当“失败时的过载兜底”，而要当“设计时就存在的温层/冷层”**。这样才能把权重、KV、专家、前缀、索引和工具结果做成有策略的热温冷放置，而不是一旦溢出就整体崩速。DAK 和 ITME 等工作也在推动“直接访问远端层、避免先拉回本地 HBM 再计算”的思路，这对未来小型一体机很关键，因为它们最稀缺的往往不是计算，而是**高带宽近端容量**。citeturn19search6turn19search2turn19search9turn19search15

## 代表工作与 Ascend+Kunpeng 迁移判断

下面按“代表工作/代表工作类”整理其瓶颈、硬件假设、小算力适配性和迁移到 Ascend+Kunpeng 的主要难点。表中“适合度”不是论文原话，而是结合设备形态、链路条件和栈成熟度后的工程判断。citeturn2search4turn18search0turn2search13turn3search8turn15search2turn9search3turn10search3turn20search0turn21search1turn24search2turn4search2turn3search6

| 代表工作 / 类别 | 解决什么瓶颈 | 依赖什么硬件假设 | 是否适合小算力一体机 | 迁移到 Ascend + Kunpeng 的难点 |
|---|---|---|---|---|
| **Splitwise / DistServe / WindServe / SuperInfer** citeturn2search4turn18search0turn21search3turn2search2 | Prefill/Decode 干扰、双 SLO 冲突、状态转移抖动 | 至少需要较快的本地 backplane、PCIe、C2C 或多机网络 | **高**。单机可做“逻辑分离”，2–8 节点更有价值 | 需要把 KV 传输、阶段调度、异构资源绑定改写到 CANN/HCCL/MindIE/vLLM-Ascend 语义；但华为已公开多机低时延通信、序列并行、LayerwiseDisaggregated 等方向，说明思路可落地。citeturn4search12turn4search7turn4search2 |
| **Mooncake / LMCache / SGLang HiCache / HiSparse** citeturn2search13turn3search8turn3search5turn8search13 | KV 复用、跨请求前缀共享、长上下文状态分层 | 需要足够 DRAM/SSD，最好还能利用网络做远端共享 | **很高**。这是长记忆 Agent 最可迁移的能力 | Ascend 侧需要统一 KV 页面格式、cache connector、压缩/搬运 API 和 observability；华为公开资料更偏“推理引擎+工具链”，缓存生态仍弱于 NVIDIA/vLLM 主线。citeturn4search2turn4search5turn14search12 |
| **FlashAttention-4 / TokenWeave / NanoFlow** citeturn15search2turn7search0turn18search2 | 注意力与通信/算力重叠、单卡资源利用率、长上下文吞吐 | 强依赖 CUDA、Hopper/Blackwell 指令特性、Triton/CuTe、Multimem 或类似机制 | **中**。思想重要，直接复用实现难 | Ascend 迁移难点在 CUDA/CuTe 风格 kernel、通信-计算 overlap 与图编译机制不兼容，需要重新做算子融合与 HCCL 并发控制。citeturn14search12turn14search7 |
| **Kitty / FlexiCache / OPKV / NVFP4 KV** citeturn9search3turn7search13turn9search2turn27search14 | KV 体积过大、页命中低、精度与吞吐折中 | 依赖 paged KV、量化友好 kernel、head/page 级统计 | **很高**。本地长上下文最直接受益 | Ascend 需要重做低比特 KV pack/depack、页布局与高性能 dequant kernel；并要验证长上下文精度在 CANN kernel 上是否稳定。citeturn14search12turn14search14 |
| **MoE Tax / CRAFT / Layered Prefill / 专家预测 / FarSkip-Collective** citeturn10search3turn10search2turn9search0turn2search11turn16search3 | MoE 的专家不均衡、过度复制、载入流量、阻塞式通信 | 需要多 GPU/NPU、较强 NIC/RDMA、显式专家路由 | **中**。2–8 节点 MoE 或大一体机有意义；小模型不一定值 | Ascend 难点在专家调度与点对点传输栈成熟度、HCCL/P2P 灵活性、以及模型结构修改带来的工程复杂度；但华为已公开“大规模专家并行解决方案”和 MoE 动态调度。citeturn25search2turn4search12 |
| **LIA / llm.npu / Hybe / LLM-NPU / NPUMoE** citeturn20search0turn21search1turn21search2turn20search1turn24search1 | 把 CPU/NPU 从“闲置外设”变成推理协作者，尤其是 prefill 与长上下文 | 假设 CPU 有 AMX/强 SIMD，或 NPU/ANE 有可编译静态图 | **高**。特别适合 UMA SoC、一体机和 A+K | Ascend 的机会很大，因为其本来就是 CPU+NPU 系统；难点是动态图/不规则算子、混合精度和分块调度要与 CANN 图编译友好。citeturn4search5turn4search2turn25search0 |
| **NVIDIA Grace-Hopper / Grace-Blackwell / Dynamo / NIXL / GDS** citeturn5search0turn5search8turn27search10turn16search2turn5search1 | 一致性内存、分层 KV、数据搬运抽象、直通存储 | 假设 NVLink-C2C/NVLink、CUDA unified memory、GDS/NIXL 可用 | **高启发、低可直接复用** | 不能直接移植，但“统一地址空间 + 明确的 KV/API + point-to-point 数据面”的思想非常值得 A+K 仿照。华为已在硬件/软件开放栈上朝这个方向走。citeturn25search16turn25search17 |
| **AMD Ryzen AI Max / MI300A / ROCm** citeturn5search2turn5search6turn26search4turn26search7 | 本地大模型 fit 与 CPU/GPU 共享内存协同 | 依赖 UMA/统一 HBM/Infinity Fabric 与 ROCm 栈 | **很高**。这是“小算力一体机”最现实的现成范式之一 | 迁移到 Ascend 时实现栈不同，但架构理念相近：共享地址空间、CPU 做控制与冷层、加速器做热点稠密算。citeturn25search0turn4search5 |
| **Apple unified memory / MLX / vLLM-MLX / AFM 稀疏化** citeturn24search2turn1search5turn24search0turn24search10 | 用统一内存承接本地 LLM/MLLM，减少复制与栈复杂度 | 假设 Apple UMA、MLX/Metal/ANE 软硬一体 | **很高**。是“一体机范式”的成熟样本 | 不能直接迁移实现，但对 A+K 的启发很明确：统一内存默认化、运行时懒执行、前缀/多模态共享缓存，比单纯追求峰值算力更重要。citeturn24search9turn24search14 |
| **Ascend MindIE / vLLM-Ascend / TEI / MoE EP 方案** citeturn4search2turn3search6turn4search13turn4search1 | 在 Ascend 上把文本生成、Embedding/Rerank、服务化、MoE 并行都接起来 | 依赖 CANN、MindIE、HCCL、Kunpeng+Ascend 服务器/模组 | **高**。这是 A+K 的主路径 | 难点不是“能不能做”，而是跟进 vLLM/SGLang 主线创新的速度、低比特 KV 与前沿 kernel 的及时适配，以及多组件版本组合复杂度。citeturn3search10turn4search14turn25search16 |

一个非常重要的额外观察是：**适合小算力一体机的工作，往往不是最“炫”的大规模分布式论文，而是那些把状态做成一等公民、把 CPU/NPU 纳入主路径、把链路和存储看成可调度资源的工作**。从这个角度看，Mooncake/LMCache/HiCache、Kitty/FlexiCache、LIA/llm.npu、Ryzen AI Max/MLX、以及 MindIE/vLLM-Ascend，可能比纯粹追求 72-GPU 峰值的系统更值得优先落地。citeturn2search13turn3search8turn3search5turn9search3turn7search13turn20search0turn21search1turn5search2turn24search2turn4search2turn3search6

## 对下一代芯片模组与整机的参数启发

下面给出的不是“市场现成 SKU 清单”，而是基于 2024–2026 年公开论文与官方规格，对未来本地 Agent 一体机/塔式工作站/小型集群的**建议区间**。推导依据包括：GH200/GB200 的一致性内存与 C2C 路径、AMD Ryzen AI Max 与 MI300A 的统一内存实践、Apple M4 Max/MLX 的 UMA 范式、Intel Gaudi 3/Xeon 6 的 HBM+CXL+DSA 组合，以及华为 A+K 服务器形态与推理栈。citeturn5search0turn5search8turn5search16turn5search2turn5search6turn26search4turn26search7turn6search7turn24search2turn5search3turn6search12turn25search0turn25search7

| 参数项 | 一体机 / SoC 型本地 Agent 机 | 塔式工作站 / 小型服务器 | 2–8 节点小集群 |
|---|---|---|---|
| 近端内存容量 | **建议 96–192 GB**；128 GB 应成为高端默认甜点位 | 单加速器 **48–96 GB** 起步，双加速器聚合 **96–192 GB** 更稳妥 | 每节点 **64–192 GB**；集群总近端容量 **0.5–1.5 TB** |
| 近端内存带宽 | **建议 ≥ 400 GB/s，可用；≥ 800 GB/s 更理想** | 每加速器 **≥ 0.8 TB/s 优先，>1.5 TB/s 理想** | 每节点同左；同时要求网络/状态搬运足够快，别让近端带宽被远端等待抵消 |
| CPU 核数与单核性能 | **12–24 个高性能核**即可明显改善调度/检索/工具执行 | **24–64 核**更适合混合负载；单核性能仍然关键 | 每节点 **16–64 核**，重点看检索、工具与缓存管理是否共置 |
| DDR / LPDDR 容量与通道 | UMA 机型本身就是主内存；若离散加速器，主机侧建议 **128–256 GB** | 建议 **256–512 GB DDR5**；多通道优先，用于缓存池、索引和冷层权重 | 每节点 **256 GB–1 TB**；对长记忆 Agent 与 MoE 更重要 |
| SSD 带宽 / IOPS | 建议 **7–14 GB/s 顺序读**、**>1M 随机读 IOPS** 级别 | 建议 **10–20 GB/s 聚合带宽**，最好多盘并行 | 每节点 **10–20 GB/s**，并支持分布式对象/块存储 |
| 互联带宽 / 时延 | 芯内 / 封装内最好有 **C2C/UMA 级一致性链路**；否则 PCIe Gen5 x16 是底线 | 机内至少要让 GPU↔CPU、GPU↔SSD 拓扑最短；P/D 分离受机内链路影响极大 | **100 GbE/RDMA 是底线，200–400 GbE 更稳**；目标是让 KV/专家传输尽量隐藏在一次 decode 步内 |
| 持续功耗 | **120–250 W** 适合“常开型本地 Agent” | **350–900 W** 适合多模型/多代理并行 | 每节点 **300–1200 W**，整簇 **1–6 kW** 仍是较现实上限 |
| 软件栈要求 | 必须有统一的 KV / prefix / offload 控制面与 observability | 必须支持 paged KV、cache 分层、异步 I/O、模型热切换 | 还必须额外支持 P/D 拆分、P2P 传输、故障恢复与多节点 cache 一致性 |

如果把这些建议浓缩成一句更“芯片设计”导向的话，那就是：**下一代本地 Agent 芯片/模组，最值得追求的主指标不是纯算力，而是“近端容量 × 有效带宽 × 可编程的一致性/搬运语义”**。NVIDIA GH200 用 900 GB/s NVLink-C2C 和最高 624 GB 的组合快存证明了一致性内存对推理的重要性；AMD Ryzen AI Max 证明了 128 GB UMA 能显著抬高本地模型上限；Apple M4 Max 证明了 128 GB / 546 GB/s 的 UMA 已足以承接相当多的本地生成与编码任务；Gaudi 3 和 MI350 进一步说明，只要模型进入高并发或长上下文，**带宽仍会重新成为硬约束**。citeturn5search0turn5search12turn5search8turn5search2turn5search6turn6search7turn6search15turn5search3turn26search10

对 A+K 下一代模组/整机尤其值得强调两点。第一，**Kunpeng 不是“喂卡 CPU”，而应被设计成检索、前缀管理、KV 冷热迁移、工具执行、健康监测和故障恢复的控制/数据平面**；第二，**昇腾近端内存之外，一定要有足够厚的 DDR/NVMe 温冷层**，否则长上下文、多代理、RAG 和多模态会同时争同一块 NPU 近端容量，系统很快从“可用”跌到“抖动”。华为公开资料已经在 MindIE、MindX DL、MoE 动态调度、序列并行、监测与自动恢复上强调了这一方向。citeturn25search16turn4search12turn4search5

## 趋势推演与可执行技术点

基于 2024–2026 年的公开信号，2027–2031 年最值得谨慎推演的方向有四条：其一，**Prefill/Decode 硬件异构化会更明确**，因为华为已经公开给出了 950PR 与 950DT 这样的阶段专用变体；其二，**内存带宽和近端容量会继续成为推理主线**，NVIDIA Rubin 已公开表示几乎把带宽相对 Blackwell 提升到近 3 倍，AMD 也已把 HBM4E/MI500 与更大 scale-up 域摆上 2027 路线；其三，**本地端模型会更稀疏、更多模态、更像 Agent 系统而不是纯聊天模型**，Apple 的 AFM 3 Core Advanced 已公开采用稀疏架构，20B 总参数只激活 1–4B；其四，**运行时会比单一芯片更重要**，因为 NIXL、Dynamo、LMCache、Mooncake、MindIE、vLLM-Ascend、MLX 都在把推理系统往“以状态与数据流为中心”的方向推。下面的 8 条技术点，可以直接当作下一代本地 Agent 一体机/小集群的研发纲要。citeturn14search0turn27search7turn26search13turn24search10turn16search2turn27search10turn3search8turn2search13turn4search5turn3search6turn24search2

- **长上下文不是单一容量问题** → **构建 HBM/近端热 KV + DDR 温 KV + NVMe 冷 KV 的三层状态体系** → **形成基于前缀命中、页热度、head 稳定性与 TTL 的分层缓存/卸载/恢复策略** → **把可服务上下文做大 3–6 倍，同时把 TTFT 增幅控制在 15–25% 内，把 TPOT 劣化控制在 10–20% 内，作为研发目标**。citeturn3search8turn2search13turn3search5turn8search13turn7search13turn9search3turn27search14

- **Prefill 与 Decode 的资源画像继续分化** → **构建阶段特化的异构执行域，哪怕在单机里也要做逻辑分池** → **形成按 TTFT/TPOT 双目标联合优化的调度、批处理和状态移交流程** → **在长提示、多会话场景争取 1.5–4 倍拥有更好 SLO 的 goodput；对 2–8 节点场景，争取把“同预算下能服务的请求数”至少提升一倍以上**。citeturn2search4turn18search4turn21search3turn2search2

- **CPU 不应只是管理面，而应成为数据面的一部分** → **构建 CPU 主导的检索、工具、序列化、压缩、KV 索引、异常路径与草稿/小模型执行能力** → **形成“CPU 管状态、GPU/NPU 管热点稠密算”的协同执行策略** → **预期把端到端 p95 明显压低，并减少 GPU/NPU 因杂务而被打断的时间；对本地 Agent，目标是把工具/检索带来的附加尾延迟压缩 20–40%**。citeturn20search0turn21search1turn24search2turn4search13turn25search16

- **MoE 的主要税不在“激活参数少”，而在“专家状态与通信复杂”** → **构建基于热度统计、层内收益估计与下一步预测的专家复制/预取/CPU fallback 能力** → **形成专家放置、复制预算、通信隐藏与负载均衡联合策略** → **目标是在 2–8 节点 MoE 服务中获得 10–25% 的稳定吞吐提升，并降低长尾超时与拥塞抖动**。citeturn10search3turn10search2turn9search0turn2search11turn16search3

- **统一内存/一致性内存会普及，但不会自动给你高效 decode** → **构建显式 residency 控制与热页 pin 策略，把 UMA/C2C 视为“温层可访问池”而非“免费 HBM”** → **形成按层、按页、按头、按专家的驻留与抢占策略** → **预期把单机可容纳模型规模扩到纯显存方案的 1.5–3 倍，同时尽量把 decode 性能损失控制在 20–30% 以内**。citeturn27search0turn5search0turn5search8turn5search2turn24search2turn19search6

- **存储会从“加载介质”变成“主动推理层”** → **构建 GPU/NPU 友好的 direct-storage 或近似 direct-storage 路径，以及对象化的权重/KV/Adapter/索引仓** → **形成冷权重、冷专家、向量分片、工具缓存的预取/恢复/清理策略** → **预期把模型/状态恢复时间从分钟级压到秒级到十秒级，并减少高峰期因重复装载导致的抖动**。citeturn5search1turn16search2turn17search0turn2search13turn3search8

- **小集群的关键不只是 all-reduce，而是灵活 point-to-point 数据平面** → **构建面向 KV 传输、专家派发、状态转移的 P2P/RDMA/零拷贝接口抽象** → **形成 KV 块合并、路由感知的 chunking、点对点隐藏延迟和回压控制策略** → **对 2–8 节点系统，目标是把有效传输带宽尽量逼近 100–400 Gbps 链路上限，并让多数状态转移隐藏在一次 decode 步或一层专家计算时间内**。citeturn17search0turn16search2turn7search0turn18search14

- **A+K 的胜负手在“运行时兼容层”而不只在单芯片参数** → **构建以 MindIE/vLLM-Ascend/SGLang/TEI 为核心的统一服务入口，并补齐分页 KV、分层缓存、Embedding/Rerank、量化与可观测性插件** → **形成面向文本生成、检索、工具、多模态的统一调度/缓存/卸载/评测策略** → **预期把模型上新和场景迁移周期压到周级，稳定服务能力优先于追逐单点 benchmark 峰值**。citeturn4search2turn4search13turn3search6turn3search10turn25search16turn25search18

总体上，2027–2031 年本地 Agent 计算系统大概率会越来越像“**小型、异构、分层、状态中心化的推理操作系统**”：芯片负责提供足够的近端容量、带宽和一致性语义，真正决定体验上限的则是运行时是否能把 Prefill、Decode、KV、专家、检索、工具和多模态状态组织成一个稳定的热温冷分层系统。这一点，已经被 2024–2026 年的论文趋势与 NVIDIA / AMD / Apple / 华为的公开资料共同验证。citeturn11search6turn23search1turn27search10turn26search8turn24search14turn25search16