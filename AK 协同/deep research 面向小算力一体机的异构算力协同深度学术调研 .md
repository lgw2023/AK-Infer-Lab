# 面向小算力一体机的异构算力协同深度学术调研

## 执行摘要

这次调研的结论很明确：近两年学术界确实已经开始把 CPU 从“纯 host”提升为推理系统中的一等协同资源，但这种提升并不是“一步到位地把 CPU 变成 dense Transformer 主算力”，而是沿着三条更现实的路径展开：第一，CPU 成为 **KV/Prefix/Context 的分层存储与恢复平面**；第二，CPU 成为 **MoE/offload/agent workflow 的控制与辅助计算平面**；第三，在 **MoE 专家、短矩阵、NPU/GPU 不擅长的尾部算子、工具执行与 I/O** 上，CPU 开始以数据面角色直接参与端到端推理。NEO、FlexInfer、KVPR、KTransformers、CoX-MoE、MORI、MARS 等论文都沿着这一趋势推进，只是关注点分别落在在线 serving、KV 分层、MoE、Agent 工作负载和异构调度上。citeturn9view4turn10view0turn6search5turn12view0turn18view0turn16view3turn23view0turn23view3

如果把目标限定为“小算力一体机 / 本地 Agent 工作站 / 1–4 卡小服务器”，最先能落地、而且论文与工程都同时支持的路径，并不是“把大部分 attention 或 GEMM 下放给 CPU”，而是五条更稳的路线：**KV/Prefix/Context 的 GPU→CPU DRAM→SSD 分层与预取**、**MoE 冷热专家的 CPU/DRAM 驻留与 GPU 热专家保活**、**工具调用空窗期的 KV 保活/换出策略**、**embedding/rerank/vector search 等短算子在 CPU/NPU 上并行执行**、以及 **Prefill/Decode 或 Encode/Prefill/Decode 的选择性分离**。这些路径同时贴合小算力设备最真实的四个约束：显存不够、PCIe/内存带宽不够、功耗受限、以及交互型 agent 的 workflow 不稳定。citeturn12view1turn18view0turn16view0turn23view0turn21view0turn36view0

从“学术结果能否迁移到小算力一体机”的角度看，最需要警惕的是三类论文。第一类是 **依赖 GH200/GB200/MI300A 这类统一内存或超高带宽 CPU-GPU 互联** 的系统，例如 Pie、SuperInfer、部分统一内存/CXL 方案；它们证明了“强耦合 CPU-GPU”非常有价值，但其 900 GB/s NVLink-C2C 或统一 HBM 的假设在普通 PCIe 工作站上并不成立。第二类是 **默认高带宽集群互联与多 GPU 资源池** 的全量 P/D 或 E/P/D disaggregation 方案；这些机制可以迁移，但必须从“跨节点分离”退化为“单机进程内 / 单机多卡 / 低频分离”的轻量变体。第三类是 **追求数据中心 goodput 峰值** 的工作，往往弱化了工具等待、会话驻留、JCT 与功耗约束，而这些正是小算力 agent 机最重要的指标。citeturn18view1turn13view0turn8search2turn38view0turn36view0turn25view2turn23view5

如果只回答一个最核心的问题：**CPU 是否已成为本地 LLM/Agent/多模态系统中的一等协同资源？** 我的判断是：**在“状态管理、缓存分层、工作流感知调度和稀疏子任务计算”上，答案已经是“是”；在“dense 主路径与 GPU/NPU 对等计算”上，答案仍然是“部分成立，且主要限于 MoE、NPU 异构和统一内存平台”。** 也就是说，CPU 在小算力一体机里最先成熟的价值，并不是替代 GPU/NPU，而是把整个系统从“显存内的单轮推理”扩展成“跨显存、DRAM、SSD、工具链和会话状态的完整 agent runtime”。citeturn10view0turn12view1turn18view0turn28view1turn23view0turn23view6

## 调研范围与方法

本次检索以 **2024-06-30 至 2026-06-30** 为近两年核心窗口，优先覆盖 MLSys、OSDI、ASPLOS、SOSP、USENIX FAST、ACL Findings、ICLR/ICML/NeurIPS 的 systems 或 efficient inference 相关论文，同时补充系统论文引用频繁、但略早于窗口的背景论文。像 Mooncake 由于发表于 2024-06-24，严格来说略早于 24 个月窗口，因此我将其标记为“背景/奠基论文”，不与 2025–2026 核心进展混排。citeturn8search11turn8search7turn38view0

检索和筛选时，我没有把 “heterogeneous computing” 这类泛关键词作为主轴，而是围绕更贴近你关心主题的机制词来收集论文：如 **CPU-GPU collaborative inference、KV cache offload / tiering / restore、prefill-decode disaggregation、MoE expert offloading / prefetch、agentic workflow KV management、unified memory / CXL memory / direct storage、edge/on-device LLM with NPU/GPU/CPU** 等。最终纳入的文献中，正式发表论文优先，其次是大会官方论文页、会议 Proceedings、论文作者项目页，再其次才是 arXiv preprint；如果某一方向只发现 preprint，我会显式标注“仅发现 preprint”。citeturn9view4turn12view1turn18view0turn16view3turn25view2

需要单独说明的是：在你限定的主题下，**“NPU/GPU + CPU 异构协同”在服务器级正式论文里仍以 GPU+CPU 为主，NPU+CPU 的正式学术论文更多集中在 mobile / AI PC / Apple silicon 一侧**。因此本报告对 NPU 部分采取“双轨证据”：正式学术论文优先使用 llm.npu、HeteroInfer 这类端侧系统论文；工程落地与生态趋势则以 OpenVINO、MLX、Ascend、Ryzen AI Max 等官方资料作工程映射，而不拿厂商博客替代论文结论。citeturn28view1turn28view0turn30search2turn30search3turn31search1turn31search2

## 方向与会议论文矩阵

下表按“方向 + 会议/状态”组织，只保留与“小算力一体机中 NPU/GPU + CPU 协同增强”最相关的论文。为了便于技术研讨，重点字段压缩为：核心机制、适用硬件、主要收益、以及对小算力一体机的迁移判断。

| 方向 | 论文 | 会议/状态 | 机构 | 核心机制 | 硬件/部署假设 | 主要收益 | 对小算力一体机的迁移判断 | 来源 |
|---|---|---|---|---|---|---|---|---|
| Runtime 与调度 | **NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference** | MLSys 2025 正式论文 | Peking University, UC Berkeley, UC Davis, Harvard | 非对称 GPU-CPU pipeline + load-aware scheduling；把一部分 decode attention 与 KV 下放 CPU | 单 GPU + 本机 CPU，T4/A10G/H100 | T4 上吞吐最高 7.5×；A10G 26%；H100 14%，保持相同延迟 | **可直接迁移**；特别适合单机 1–4 卡、显存受限且 decode 较长的场景 | citeturn9view4turn10view0 |
| Runtime 与调度 | **FlexInfer: Flexible LLM Inference with CPU Computations** | MLSys 2025 正式论文 | Georgia Tech, Meta, UC San Diego, Intel Labs | 预填/解码阶段分开建模，动态选择 CPU-only / GPU-offload / CPU-GPU partition | 单机 offloading，强调 CPU AMX 与执行计划 | 平均端到端延迟下降 75%–76% | **可直接迁移**；适合 AI PC / 工作站做“按阶段选策略” | citeturn11view2turn7search14turn7search15 |
| Runtime 与调度 | **SuperInfer: SLO-Aware Rotary Scheduling and Memory Management for LLM Inference on Superchips** | MLSys 2026 会议论文/公开稿 | 公开稿作者页可得；论文针对 GH200 Superchip | RotaSched 主动轮转 + DuplexKV 全双工 KV 旋转 | GH200，NVLink-C2C 900 GB/s | TTFT SLO 达成率最高提升 74.7% | **需要改造**；思路可迁移，性能假设不可直接迁移到 PCIe 工作站 | citeturn7search2turn13view0turn29search0 |
| 分层内存/KV | **KVPR: Efficient LLM Inference with I/O-Aware KV Cache Partial Recomputation** | Findings of ACL 2025 正式论文 | University of Southern California | “激活先传 + GPU 局部重算 + 其余 KV 并传” 以重算遮蔽 PCIe 瓶颈 | 单 GPU / 数据并行多 GPU，CPU DRAM ↔ GPU HBM 通过 PCIe | decode 延迟最高降低 35.8%，吞吐最高提升 46.2% | **可直接迁移**；非常适合 PCIe 限制下的小机 | citeturn12view1turn12view0 |
| 分层内存/KV | **Pie: Pooling CPU Memory for LLM Inference** | arXiv 2024 preprint | UC Berkeley | performance-transparent swapping + adaptive expansion | GH200 统一高带宽 CPU-GPU 内存 | 吞吐最高 1.9×、延迟最高 2× 优于 vLLM | **需强改造**；适合抽象出“透明扩容”理念，不适合直接抄到 PCIe | citeturn18view1 |
| 分层内存/KV | **Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving** | FAST 2025 正式论文；但属背景/奠基 | Moonshot AI, Tsinghua University | 以 KV 为中心的调度；利用集群闲置 CPU/DRAM/SSD 做分布式 KV | 多节点/分离式资源池 | 模拟场景吞吐最高 525%，真实负载多处理 75% 请求 | **可部分迁移**；思想可缩成单机 L3 cache / SSD back-end | citeturn8search11turn9view3 |
| 分层内存/KV / 互联 | **ITME: Inference Tiered Memory Expansion with Disaggregated CXL-Hybrid Memories** | arXiv 2026 preprint | SK hynix 等团队 | CXL 混合内存做 TB 级远端字节寻址扩容，主动跨层数据管理 | CXL memory + NVMe + FPGA prototype | 吞吐最高提升 35.7% | **中长期**；适合 2–8 节点小集群，不适合近期单机产品化 | citeturn8search2 |
| MoE | **Fiddler: CPU-GPU Orchestration for Fast Inference of Mixture-of-Experts Models** | ICLR 2025 正式论文 | 作者页/ICLR 摘要公开；机构信息公开摘要页不完整 | 用 CPU 计算能力减少 CPU-GPU 间权重搬运 | 单 GPU 24GB + CPU | 单张 24GB GPU 上可跑无压缩 Mixtral-8x7B，生成速率超 3 tok/s | **可直接迁移**；非常贴合本地 MoE | citeturn15search3turn15search10turn15search6 |
| MoE | **MoE-Lightning: High-Throughput MoE Inference on Memory-constrained GPUs** | ASPLOS 2025 正式论文 | UC Berkeley / Stanford 相关团队 | CPU-GPU-I/O pipeline（CGOPipe）+ paged weights + HRM 性能模型 | 单 T4/多 T4，离线批处理为主 | 单 T4 跑 Mixtral 8x7B 吞吐最高 10.3× | **部分迁移**；适合离线/后台 agent，不直接适合强交互 | citeturn18view2turn17search5 |
| MoE | **DAOP: Data-Aware Offloading and Predictive Pre-Calculation for Efficient MoE Inference** | DATE 2025 正式论文 | National University of Singapore | 基于序列激活模式动态分配 expert 到 CPU/GPU，并在 CPU 预计算预测专家 | on-device / resource-constrained | 相比传统 expert cache/prefetch 最多 8.2×，比 offloading 最多 1.35× | **可直接迁移**；极适合“本地大 MoE + 小显存” | citeturn15search0turn15search11turn16view0 |
| MoE | **KTransformers: Unleashing the Full Potential of CPU/GPU Hybrid Inference for MoE Models** | SOSP 2025 正式论文 | Tsinghua University 等 | AMX 特化 CPU kernel + 异步 CPU-GPU 任务调度 + Expert Deferral | 低并发本地部署；超大 MoE | 预填 4.62–19.74×，解码 1.25–4.09×；Deferral 额外带来最高 1.45× 吞吐 | **高度可迁移**；本报告认为是“本地 MoE 一体机”代表论文 | citeturn18view0turn19view4 |
| MoE | **DALI: A Workload-Aware Offloading Framework for Efficient MoE Inference on Local PCs** | arXiv 2026 preprint | arXiv 公开作者页 | 动态 expert 分配 + Residual-based prefetch + workload-aware cache replacement | Local PCs | prefill/decode 均显著优于现有 offloading 框架 | **可直接迁移**；尤其贴合 PC/工作站 | citeturn15search2 |
| MoE | **CoX-MoE: Coalesced Expert Execution for High-Throughput MoE Inference with AMX-Enabled CPU-GPU Co-Execution** | DAC 2026 正式论文 | KAIST | AMX-enabled CPU-GPU co-execution + coalesced expert execution + stratification | 单 GPU + AMX CPU + 主机内存/SSD | 相比 FlexGen 最高 7.1×，相比 MoE-Lightning 最高 2.4×；平均约 2× | **可直接迁移**；适合 Intel/AMX 路线小型服务器 | citeturn16view3 |
| P/D 与多轮会话 | **DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving** | OSDI 2024 正式论文 | Peking University, StepFun, UC San Diego | Prefill / decode 分离 + 按 TTFT/TPOT 共同优化资源与并行策略 | GPU 集群，需考虑 NVLink/带宽 placement | goodput 可提升到 7.4× 更多请求或 12.6× 更紧 SLO | **选择性迁移**；单机更适合“轻分离/阶段隔离”，不适合照搬集群版 | citeturn38view0 |
| P/D 与多轮会话 | **EcoServe: Enabling Cost-effective LLM Serving with Proactive Intra- and Inter-Instance Orchestration** | arXiv 2025 preprint | Sun Yat-sen University 等 | commodity interconnect 上的 partial disaggregation + rolling activation | 32× L20 + 以太网 | 相比代表系统 goodput 平均提升 82%–127% | **部分迁移**；思路适合 2–8 节点小集群 | citeturn20search2 |
| P/D 与多轮会话 | **AMPD: Efficient Multi-round LLM Inference over Disaggregated Serving** | arXiv 2026 preprint | arXiv HTML 公开稿 | 面向 multi-round / agentic workflow 的 adaptive routing + prefill reordering | PD disaggregation 集群 | 强调 SLO 导向地决定 append-prefill 在哪里执行 | **可迁移**；尤其适合本地 Agent 长会话 | citeturn21view1 |
| P/D 与多轮会话 | **PPD: Not All Prefills Are Equal** | arXiv 2026 preprint | ETH Zürich 等作者信息见公开页 | 把 Turn 2+ 的 append-prefill 尽量留在 decode 节点，本地复用 KV | 多轮对话 / agent 工作负载 | Turn 2+ TTFT 降低约 48%–73%，文中代表结果 68% | **高度可迁移**；单机可做“会话内本地 append-prefill” | citeturn21view0 |
| 边缘/端侧/NPU | **llm.npu: Fast On-device LLM Inference with NPUs** | ASPLOS 2025 正式论文 | Peking University, BUPT | prompt chunking + tensor outlier 分离到 CPU/GPU + block-level NPU/CPU/GPU 调度 | 手机/端侧 SoC；NPU+CPU+GPU | 平均 prefill 快 22.4×，能耗降低 30.7×；端到端最高 32.8× | **机制可迁移**；平台假设偏手机，适合 AI PC 的 NPU 路线参考 | citeturn28view1 |
| 边缘/端侧/NPU | **HeteroInfer: Characterizing Mobile SoC for Accelerating Heterogeneous LLM Inference** | SOSP 2025 正式论文 | Shanghai Jiao Tong University, Tsinghua University, SenseTime Research | GPU-NPU 异构执行；按序列长度/图形形状与算子特性选设备 | 手机/SoC/UMA | 对 MLC/MNN 最多 9.99× / 4.36×；预填 1.34×–6.02×，解码 1.50×–2.53× | **机制可迁移**；最适合 AI PC / UMA，而非离散 PCIe 服务器 | citeturn27search4turn28view0 |
| 边缘/端侧/GPU+CPU | **APEX: Parallel CPU-GPU Execution for LLM Inference on Constrained GPUs** | arXiv 2025 preprint | arXiv 公开稿 | profiling-informed scheduling，细粒度 CPU-GPU overlap，无需 batch splitting | T4 / A10 这类 constrained GPU | 对 vLLM 吞吐提升 84%–96%（T4）、11%–89%（A10） | **可直接迁移**；很适合低成本单卡机 | citeturn28view2 |
| 多模态流水线 | **EPD Disaggregation for LMMs** | arXiv 2025 preprint | Huawei Technologies Canada, Simon Fraser University, Huawei Cloud | Encode-Prefill-Decode 三阶段分离 + MM token cache + IPR + role switching | 多 GPU | TTFT 最高降低 71%，内存利用最多 15× 更低 | **需要收缩版迁移**；单机适合“轻量 E/P/D”而非完整池化 | citeturn36view0 |
| 多模态流水线 | **vLLM-Omni: Fully Disaggregated Serving for Any-to-Any Multimodal Models** | arXiv 2026 preprint | HKUST / vLLM 相关团队 | stage graph abstraction + per-stage batching + unified connectors | 多阶段任意模态图 | JCT 最多下降 91.4% | **部分迁移**；更适合作为 pipeline runtime 原型蓝图 | citeturn35search1turn37search0 |
| 多模态流水线 | **LiveServe: Interaction-Aware Serving for Real-Time Omni-Modal LLMs** | arXiv 2026 preprint | HKUST / 合作团队 | 把音频播放进度、打断、下轮复用显式接入调度与 KV 管理 | 实时语音/全模态会话 | P90 first-audio 下降 1.55×，完成吞吐提升 1.15× | **可迁移**；适合语音 Agent 一体机 | citeturn35search0turn37search1 |
| 多模态流水线 | **CodecSight** | arXiv 2026 preprint | 公开作者页 | 直接利用 codec metadata 跨“视频解码 → ViT → LLM prefill”协同优化 | 视频/流式 VLM | 吞吐最高 3×，GPU 计算最高减少 87% | **可迁移**；非常适合视频 Agent / 多模态盒子 | citeturn36view3turn37search10 |
| Agent 工具协同 | **Autellix: An Efficient Serving Engine for LLM Agents as General Programs** | arXiv 2025 preprint | 公开稿 | 把 agent 当“程序”调度，兼顾数据局部性与 KV-cache recomputation | 多引擎 agent serving | 显著提升吞吐，并强调 stateful API | **可迁移**；对本地 coding/office agent 很实用 | citeturn23view6 |
| Agent 工具协同 | **Efficient LLM Serving for Agentic Workflows** | arXiv 2026 preprint | 公开稿 | 跨调用冗余消除，关注 workflow 级而非单请求级优化 | agent workflow | 指出传统 vLLM 类系统忽视 cross-call 依赖 | **可迁移**；非常适合 Deep Research / Coding Agent | citeturn23view1 |
| Agent 工具协同 | **MORI: Idleness is Relative** | arXiv 2026 preprint | 公开稿 | 利用 tool-call idle windows 做程序级 KV 保活/换出决策 | coding-agent traces | 证明 tool gap 跨毫秒到分钟，必须程序级管理 KV | **高度可迁移**；本地 agent 必做 | citeturn23view0 |
| Agent 工具协同 | **MARS** | arXiv 2026 preprint | 公开稿 | 联合 GPU、KV、host CPU 的异构协同调度 | multi-turn agent systems | 直接指出 agent workloads 给 host CPU 带来耦合压力 | **可迁移**；适合作为 admission control/routing 参考 | citeturn23view3 |
| Benchmark/Trace | **Agentic AI Workload Characteristics** | arXiv 2026 preprint | 公开稿 | 端到端 tracing，把 agent 轨迹与 serving trace 关联 | agent benchmarks + vLLM | 给出 tool/runtime/LLM 共同特征 | **可直接迁移**；适合制定一体机 trace schema | citeturn23view2turn24search8 |
| Benchmark/Trace | **ProfInfer** | arXiv 2026 preprint | Huawei Hilbert Research Center, TUM 等 | eBPF 非侵入 profiling，输出 operator/DAG/timeline/hardware counters | llama.cpp / edge/mobile | 运行时开销低于 4% | **可直接迁移**；很适合本地机瓶颈归因 | citeturn25view1turn25view0 |
| Benchmark/Trace | **Frontier** | arXiv 2026 preprint | CUHK, Anuttacon, StepFun | 现代 serving 的离散事件仿真器，支持 PDD/AFD/stateful workloads | 最多 1K GPU 仿真 | 吞吐误差低于 4%，端到端延迟误差显著低于既有模拟器 | **可迁移为规格反推工具**；尤其适合小集群规划 | citeturn25view2 |
| Benchmark/Trace | **CCL-Bench 1.0** | arXiv 2026 preprint | 公开稿 | trace-based benchmark + simulator replay + what-if analysis | 多框架/多硬件 | 已收集 100+ 工作负载 | **可迁移**；适合建立 Tasks/J 与资源效用指标库 | citeturn25view3 |
| 互联/统一内存 | **GH200 / Grace Hopper / NVLink-C2C 官方材料** | 厂商原始资料 | NVIDIA | CPU-GPU 一致性高带宽互联，900 GB/s；大统一内存池 | GH200 / DGX Spark / Grace Blackwell | 为 offload、rotation、direct KV handoff 提供硬件基础 | **仅硬件趋势可迁移**；小机可期待 AI PC / superchip 化 | citeturn29search0turn29search8turn34search14 |
| 互联/统一内存 | **MI300A / Ryzen AI Max / UMA 官方材料** | 厂商原始资料 | AMD | CPU+GPU unified memory / shared address space | MI300A、Ryzen AI Max / Halo | 支持更大本地模型与更少数据搬运 | **对一体机高度相关**；但要等待软件栈成熟 | citeturn31search0turn31search4turn31search13 |

从这个矩阵看，近两年真正最有“产品可迁移性”的论文并不是那些最宏大的大集群论文，而是 **NEO、KVPR、DAOP、KTransformers、CoX-MoE、APEX、MORI、ProfInfer** 这一组。它们共同特征是：把 CPU 视为廉价、可编程、状态感知、可持续驻留的本地协同资源，而不是只把它当作启动 GPU 的控制器。citeturn10view0turn12view1turn16view0turn18view0turn16view3turn28view2turn23view0turn25view1

## 代表论文深度解读

下面只展开最能支撑技术规划的代表论文。每篇都按照你要求的字段压缩成“能直接进入研讨会”的格式，而不是摘要复述。

**NEO**

论文名称：**NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference**。作者与机构：Xuanlin Jiang, Yang Zhou, Shiyi Cao, Ion Stoica, Minlan Yu；机构为 Peking University、UC Berkeley、UC Davis、Harvard。会议：MLSys 2025。发表时间：2025。方向归类：A / B。citeturn9view4turn10view0

研究背景需求在于：在线 LLM serving 的瓶颈并不是纯算力，而是 **KV cache 挤占 GPU 显存，导致 batch size 上不去，GPU 计算单元空转**。要解决的核心问题，是在不牺牲在线延迟的前提下，让本机 CPU 参与 decode attention 与 KV 驻留，从而扩大有效 batch。系统假设非常“接地气”：单 GPU 加本机 CPU，不依赖远端 CPU 集群，不依赖超高端互联；论文还明确批评了一些方案需要“8 台 32-core EPYC 才服务 1 张 A10G”的不经济性。citeturn10view0

核心策略有两层。第一层是 **asymmetric GPU-CPU pipelining**：把 requests 切成两个不同的子批次，一个主要在 GPU 上执行，另一个把 decode attention 与对应 KV 留到 CPU 上执行，形成异步重叠；第二层是 **load-aware scheduling**：每一轮根据 GPU/CPU 负载与动态输入输出长度决定哪些请求 offload，避免静态策略在真实 workload 下失效。CPU 的角色因此不再只是 host，而变成了 **解码 attention 的协同计算资源 + KV 存储层 + per-iteration scheduler 所在控制面**；GPU 继续承担 linear ops、prefill attention 和主体 dense GEMM。数据路径则是 GPU 内保留权重与热点状态，部分 decode attention 所需 KV 驻留在 CPU DRAM，经 PCIe 与 GPU 同步协作。citeturn10view0

结果收益非常扎实：在代码生成和文本摘要 workload、7B/8B/70B 模型、T4/A10G/H100 平台上，NEO 在同等延迟下分别达到 **最高 7.5×、26%、14% 的吞吐提升**；更强 CPU 配置还能进一步提高收益。它的局限也很清楚：假设“dense 主路径仍全部在 GPU 上”，因此当 workload 的 decode 不够长、或者 GPU 自身显存已经足够大时，收益会退化。对小算力一体机的启发在于：**CPU 最现实的第一步不是替代稠密层，而是吃掉 decode attention + KV 驻留 + 调度决策这一段。** 这几乎可以直接变成你的产品 prototype。citeturn9view4turn10view0

**KVPR**

论文名称：**KVPR: Efficient LLM Inference with I/O-Aware KV Cache Partial Recomputation**。作者与机构：Chaoyi Jiang, Lei Gao, Hossein Entezari Zarch, Murali Annavarm；University of Southern California。会议：Findings of ACL 2025。发表时间：2025。方向归类：B。citeturn12view1turn12view0

这篇论文的价值在于，它没有像很多 offload 方案那样默认“KV 只要搬回来就行”，而是首先承认对 PCIe 系统而言，**整块 KV 回传常常已经比解码算力更慢**。它要解决的是：显存不够时，把 KV 放在 CPU DRAM 没问题，但回传路径本身会让 GPU 大量 idle，怎么办？论文的答案是非常适合小机的：**不要先把整个 KV 传回来再算，而是先传一部分较小的激活，让 GPU 立刻重算这一段 KV；重算发生时，CPU 再并行传输剩余 KV**。citeturn12view1turn12view0

因此，CPU 在 KVPR 中的角色主要是 **I/O 与内存管理者**，而不是重算主体；GPU 则承担部分 KV 的快速重建与注意力计算。调度层面，KVPR 还引入 profiler 与线性规划/整数规划式的 split-point 选择，使“传多少、算多少”不是拍脑袋，而是由输入特征与硬件参数共同决定。这个设计特别符合“小算力 PCIe 机器”的现实，因为你通常拿不到 GH200 那样的统一内存与 C2C 带宽，但你又经常需要做长上下文与会话恢复。citeturn12view1turn12view0

实验里，KVPR 在 decode 阶段对比现有方法实现 **最高 35.8% 延迟降低和 46.2% 吞吐提升**。局限是它目前主要针对单 GPU 和数据并行多 GPU，尚未扩展到更复杂的远端存储或大规模多节点条件。对小算力一体机的核心启发是：**长上下文下最值得做的事情，不一定是“更激进的 offload”，而是“更聪明的传输-重算分工”。** 这也是比纯粹 SSD/Paging 更适合本地盒子的路线。citeturn12view1

**KTransformers**

论文名称：**KTransformers: Unleashing the Full Potential of CPU/GPU Hybrid Inference for MoE Models**。作者与机构：Hongtao Chen 等；Tsinghua University 等。会议：SOSP 2025。方向归类：C。citeturn18view0turn19view0

这是本次调研里最值得认真看的论文之一，因为它直接瞄准了“**低并发、本地部署、超大 MoE 模型**”这一你关心的场景。研究背景是：像 DeepSeek-V3/R1 这类超大 MoE 模型非常适合本地 CPU/GPU 混合推理——因为并非所有专家都会同时激活，CPU DRAM 的大容量与 GPU VRAM 的高带宽天然互补——但现有 hybrid 方案被 **CPU 计算瓶颈与 CPU-GPU 同步开销** 严重限制。citeturn18view0

KTransformers 的核心策略不是简单“把冷专家放 CPU”，而是做了三层事情。第一，针对 CPU 端实现 **AMX-specialized kernels**，尽量把 CPU 真正变成高效 expert 计算资源。第二，构造 **asynchronous CPU-GPU task scheduling**，降低专家执行与 attention 等路径的同步开销。第三，提出 **Expert Deferral**：把一部分专家的输出延迟到后续层消费，从而增强 CPU 与 GPU 之间的可重叠性，显著提高 CPU 利用率。论文中直接报告 CPU 利用率可从通常低于 75% 拉高到接近 100%，并在既有优化之上再带来最高 1.45× 的额外吞吐提升，而且平均精度损失不超过 0.5%。citeturn18view0turn19view3turn19view4

从“CPU 角色”看，这篇论文几乎是最明确的一篇：CPU 不只是控制面或内存层，而是 **MoE 专家执行的正式计算平面**；GPU 则承担 attention、共享专家与高带宽主路径。数据路径上，GPU 保留热点权重与主干状态，CPU/DRAM 则持有被 offload 的专家，必要时通过异步计划与小粒度同步配合完成执行。收益非常可观：**预填 4.62–19.74×、解码 1.25–4.09×**，还可通过 Expert Deferral 继续放大。对小算力一体机的启发几乎是直接的：**如果你的目标模型是 MoE，本地机的 CPU 不应该只是“权重搬运器”，而应该是“专家执行器”。** 这也意味着软件栈要优先建设 CPU 专家 kernel、expert-aware scheduler 和延迟容忍机制，而不是只盯着显存 offload。citeturn18view0turn19view4

**CoX-MoE**

论文名称：**CoX-MoE: Coalesced Expert Execution for High-Throughput MoE Inference with AMX-Enabled CPU-GPU Co-Execution**。作者与机构：Muyoung Son 等；KAIST。会议：DAC 2026。方向归类：C。citeturn16view3

CoX-MoE 的研究问题与 KTransformers 相近，但落点更偏“**如何在单 GPU + AMX CPU 上稳定做高吞吐 MoE**”。它指出 MoE 的 micro-batching 往往让 expert execution 变成 memory-bound，同时 CPU offloading 又受 PCIe 与负载失衡限制，因此必须联动设计批处理方式、expert 分层和 attention offload。对应的核心策略是两点：**coalescing-aware orchestration policy** 和 **expert-aware stratification**。前者把原本碎片化的专家微批合并成更大的 coalesced batch，再配合 CPU-GPU 共执行；后者把高频激活的专家预先分层部署到 GPU，降低 PCIe 搬运并平衡 CPU/GPU 负载。citeturn16view3

这篇论文特别适合 Intel/AMX 路线的小机：它不是在讨论理想化的统一内存，而是把 **AMX + GPU + host memory/SSD** 作为可实现的混合平台。实验显示，相比 FlexGen 最高可到 **7.1× 吞吐提升**，相比 MoE-Lightning 最高 **2.4×**，平均约 **2×**，而且论文明确说明它面向的是 **resource-constrained single-GPU systems**。对小算力技术布局的启发是：如果你准备押注本地 MoE，一定要同步建设 **expert hot/cold 分层、AMX/短矩阵 kernel 和 coalesced expert batching**，否则 CPU 只会变成同步障碍，而不是协同资源。citeturn16view3

**llm.npu**

论文名称：**Fast On-device LLM Inference with NPUs**。作者与机构：Daliang Xu 等；Peking University、北京邮电大学。会议：ASPLOS 2025。方向归类：E。citeturn28view1

这篇论文的重要性在于，它展示了 **NPU/CPU/GPU 三方异构协同** 在生成式模型上的一条非常清晰的技术路线。它观察到：移动/端侧 LLM 的 prefill 往往是主要瓶颈，而 NPU 擅长整数 GEMM，却不擅长 outlier、浮点尾算子和复杂动态 shape。因此 llm.npu 并没有把整个模型都丢给 NPU，而是做了三层重构：**prompt level chunking**、**tensor-level outlier 提取到 CPU/GPU 并行处理**、以及 **block-level 按硬件亲和度把 Transformer block 划给 NPU 与 CPU/GPU**。citeturn28view1

这意味着 CPU 在 llm.npu 中明确承担了 **难以量化的 outlier 部分、动态控制，以及 GPU/NPU 难协同部分的补足角色**。论文报告平均 prefill 提升 **22.4×**、能耗降低 **30.7%**，端到端真实应用最高 **32.8×**，并首次在 COTS 移动设备上把十亿级模型 prefill 做到每秒 1000+ token。局限当然也明显：它针对的是移动 SoC 与 on-device NPU，而不是工作站级离散 GPU/NPU。citeturn28view1

但对“小算力一体机”的启发并不小。它告诉我们，**NPU 在本地 Agent 设备里最先落地的角色，很可能不是整个 decode 主路径，而是 prefill 中的规则化大矩阵部分；CPU 再承接 outlier、控制逻辑和 residual/hard fallback。** 这和 Intel OpenVINO、Apple MLX/Core ML、Ascend MindIE 等工程栈的演进方向高度一致。citeturn28view1turn30search2turn32search9turn33search3

**HeteroInfer**

论文名称：**Characterizing Mobile SoC for Accelerating Heterogeneous LLM Inference**，文中系统名为 **HeteroInfer**。作者与机构：Le Chen 等；Shanghai Jiao Tong University、Tsinghua University、SenseTime Research。会议：SOSP 2025。方向归类：E。citeturn27search4turn27search10

HeteroInfer 的核心贡献，不是只给出一个新 engine，而是系统性地说明：在 **CPU/GPU/NPU 共享 UMA 的异构 SoC** 上，LLM 的 prefill 与 decode 具有不同的设备偏好，因此应同时支持 **layer-level** 与 **tensor-level** 的异构执行。论文展示，在不对齐 NPU graph shape 时，传统 padding 方法代价很高；而更细的设备映射可以显著降低这一损失。最终，HeteroInfer 对现有移动侧 LLM 引擎取得了 **1.34×–6.02× 的端到端提升**，并在解码阶段取得 **1.50×–2.53×** 的加速，同时还能把与游戏等 GPU-heavy 任务的干扰压到较低水平。citeturn27search4turn28view0

对于本地 Agent 工作站，这篇论文最值得吸收的不是具体 mobile kernel，而是两条原则：**第一，prefill 与 decode 在异构平台上不应该共享同一种设备策略；第二，NPU/GPU/CPU 协同时，资源旁路和低干扰比峰值 tokens/s 更关键。** 也就是说，小算力一体机若走 AI PC 路线，异构 runtime 不能只做静态 operator placement，而要做 **phase-aware placement + interference-aware scheduling**。citeturn28view0

**EPD Disaggregation**

论文名称：**Efficiently Serving Large Multimodal Models Using EPD Disaggregation**。作者与机构：Huawei Technologies Canada、Simon Fraser University、Huawei Cloud。状态：2025 arXiv preprint。方向归类：D / F。citeturn36view0

这篇论文很好地回答了你非常关心的一点：**多模态推理不该只讨论 LLM 的 P/D 分离，还要把 encode 独立出来。** 它指出，LMM 相比纯 LLM 新增了 multimodal encoding 阶段，这个阶段既吃算力也吃显存，而且会产生大量 multimodal token，使 prefill 进一步膨胀。因此传统“编码和 prefill 绑定在一起”的系统，会在 TTFT、batch size、可处理图片数上同时吃亏。citeturn36view0

EPD 的核心策略包括：把 **Encode、Prefill、Decode** 三段放到专用资源上；用 **MMBlockManager / MM cache** 管理 multimodal tokens；在 encode 阶段做 **intra-request parallelization**；并通过优化器寻找不同阶段的资源配比。此外，论文还支持动态 role switching，说明作者意识到现实 workload 会不断漂移。结果方面，它报告 **TTFT 最多减少 71%**，端到端 throughput 明显改善，同时能实现更低的内存占用、更大的 batch 和更多图片/请求处理能力。citeturn36view0

这篇论文对小算力一体机的真正启发不在于“照搬三池化资源池”，而在于：**多模态本地盒子需要把视频解码/视觉编码/LLM prefill/LLM decode/VAE 或后处理视作不同阶段来分析，而不是把它们都压进同一块 GPU。** 在单机上，最实际的做法通常是“轻量 E/P/D”：例如媒体引擎和 CPU 先做视频解码与部分预处理，视觉编码和 prefill 优先抢 GPU 窗口，decode 则用更稳定的小 batch 长驻。citeturn36view0

**vLLM-Omni 与 LiveServe**

论文名称分别是 **vLLM-Omni: Fully Disaggregated Serving for Any-to-Any Multimodal Models** 和 **LiveServe: Interaction-Aware Serving for Real-Time Omni-Modal LLMs**。两篇都属于 2026 arXiv preprint。方向归类：F。citeturn35search1turn35search0

vLLM-Omni 的核心价值在于，它把复杂多模态模型抽象成 **stage graph**，每个 stage 可以独立批处理、独立分配 GPU、通过统一 connector 路由数据，因此把“多模型流水线”从 ad-hoc 工程改造成了可管理 runtime。它对 baseline 的 **JCT 最高下降 91.4%**，这对本地多模态 agent 意味着：后续如果你同时做视觉编码、LLM planning、语音 TTS、图像生成或视频生成，最好从一开始就把系统建成 graph runtime，而不是堆脚本。citeturn35search1turn37search0

LiveServe 则更进一步，把 **用户是否在播放音频、是否正在说话、是否会打断** 这些交互事件变成调度输入，避免系统在用户还没听到的音频上过度生成，同时把下一轮最可能复用的 KV 在用户说话期间预加载。它把 P90 first-audio 延迟平均改善 **1.55×**，并提高 completed-request throughput。对小算力设备的意义非常直接：**未来语音 agent 的调度器不能只看 tokens/s，要看“播放前沿”和“下一轮复用概率”。** CPU 在这里天然是最合适的控制面。citeturn35search0turn37search1

**MORI 与 MARS**

论文名称：**Idleness is Relative: Exploiting Tool-Call Idle Windows for Offloading in Agentic Systems with MORI**；**MARS: Efficient, Adaptive Co-Scheduling for Heterogeneous Agentic Systems**。状态：2026 arXiv preprint。方向归类：G。citeturn23view0turn23view3

MORI 抓住了一个对 coding/deep-research/office agent 极其关键、但传统 serving 论文没有正面处理的问题：**tool-call gap 到底该不该把 KV 换出？** 它通过 coding-agent trace 证明，工具调用时长从毫秒到分钟跨越三个数量级，同一种工具内部方差都很大；如果每次工具调用都机械地 offload/reload，短 gap 会适得其反；但如果一直 pin 在 HBM，长 gap 又会浪费显存。论文因此提出，必须把“程序”而非单个请求作为内存管理单位，并把 idleness 视为连续谱，而不是简单的 idle/busy 二值状态。citeturn23view0

MARS 更进一步，把 agentic workloads 定义为 **GPU 计算、KV cache 容量、host CPUs** 三种资源的耦合系统挑战，强调 tool-interleaved workflow 需要协同调度而非单一 LLM scheduler。这两篇论文的核心共识非常适合小算力一体机：**CPU 一定要管工具、I/O、KV 生命周期、以及 admission control；否则哪怕 GPU 推理很快，整机任务完成时间也不会好。** 这是本报告最想强调给技术规划的点之一。citeturn23view0turn23view3

**ProfInfer 与 Frontier**

论文名称：**ProfInfer: An eBPF-based Fine-Grained LLM Inference Profiler**；**Frontier: Towards Comprehensive and Accurate LLM Inference Simulation**。状态：2026 arXiv preprint。方向归类：H。citeturn25view1turn25view2

ProfInfer 的意义在于补足“可观测性墙”。它利用 eBPF 挂载/uprobes 的方式，在不改 runtime 源码的前提下生成 operator、DAG、timeline 和硬件计数器视图，运行时开销低于 **4%**。论文甚至专门讨论了 MoE expert ID、存储加载导致的算子延时变化等问题。对一体机规划而言，这意味着你可以非常具体地回答：**当前瓶颈到底是 HBM、DRAM、PCIe、SSD、还是某个 expert miss 导致的 stalls？** citeturn25view1turn25view0

Frontier 则解决“规格反推”和“what-if 分析”的痛点。它把现代 serving 抽象成 admission–batching–execution–completion 的控制流，支持 colocated、PDD、AFD、stateful requests 等配置，在 16× H800 testbed 上吞吐误差低于 **4%**，并能扩展到 1K GPU 级仿真。对小算力一体机来说，你不需要 1K GPU 仿真，但你非常需要把它的思想收缩成“**单机/4 卡/8 节点的小系统设计空间探索器**”。没有这个层次的工具，后续很多硬件规格、KV 分层策略、功耗-SLO 联调都只能靠经验。citeturn25view2

## 小算力一体机挑战与迁移判断

围绕你关心的“小算力一体机 / 本地 Agent 工作站 / 小型服务器”，我建议把方向级挑战总结成八堵“墙”，而且要把它们和论文证据一一对应起来。

**容量墙** 并不只是模型权重太大，更关键的是 **KV、Prefix、MoE experts、MM tokens、视频中间状态** 会一起争抢显存。NEO、KVPR、Pie、Mooncake、ITME 共同说明：哪怕模型参数已经勉强放下，长上下文或多轮 agent 仍会让 KV 成为第一瓶颈；MoE 场景下则是专家权重与中间激活共同挤压 VRAM。对小算力设备最直接的结论是，**“只想办法放下模型本体”远远不够，分层管理状态才是正题。** citeturn10view0turn12view1turn18view1turn9view3turn8search2turn18view2turn18view0

**带宽墙** 是第二现实约束。普通工作站通常只有 PCIe，而论文里真正效果最好的 offload/rotation 又经常发生在 NVLink-C2C、统一 HBM 或高带宽 NVLink 环境里。SuperInfer、Pie、GH200 官方资料显示，900 GB/s 级 C2C 会显著改变设计空间；而 KVPR、NEO、CoX-MoE、KTransformers 则告诉我们，在 PCIe 条件下必须尽量通过 **重算、异步、批内合并、热点分层和 expert-aware placement** 来缓解带宽不匹配。换句话说，小算力设备里“带宽优化”的优先级不低于“计算优化”。citeturn13view0turn18view1turn29search0turn12view1turn10view0turn16view3turn18view0

**时延墙** 在 agent 场景尤为突出。MORI、MARS、Autellix、PPD、AMPD 都说明：工具等待、append-prefill、KV reload miss、以及多轮会话的资源切换，常常比单次请求的 token latency 更决定用户体验。对本地 Agent 盒子而言，如果你只优化 TTFT/TPOT 而不优化 **JCT、completed workflow throughput、task success rate**，最后很可能得到一个“跑 benchmark 很快、做任务很慢”的系统。citeturn23view0turn23view3turn23view6turn21view0turn21view1

**调度墙** 在小算力设备上甚至比云上更难。原因是云上可以靠大并发和资源池摊薄，而本地设备经常是 **低并发、强交互、多任务、前后台并行、还要跑浏览器/编译/数据库**。FlexInfer、APEX、SuperInfer 展示了 phase-aware/perf-model-aware 调度的必要性；MORI、MARS、SAGA 则把这一点推进到 workflow-aware 层面。你的 runtime 如果继续把每次推理都当作独立 request，很难处理 agent 程序。citeturn11view2turn28view2turn13view0turn23view0turn23view3turn23view5

**能耗墙** 与 **热约束墙** 在 NPU/edge/AI PC 场景下尤其明显。llm.npu 与 HeteroInfer 都显示，把 prefill 的规则化部分迁给 NPU，或在 GPU/NPU/CPU 间做 phase-aware mapping，不但能提高速度，还能把能耗与对其他前台任务的干扰压低。对小算力一体机来说，未来关键指标不该只是 tokens/s，而是 **Tasks/J、持续运行温升、前台业务干扰度**。citeturn28view1turn28view0

**软件生态墙** 同样不能低估。OpenVINO 明确支持 CPU/GPU/NPU 与 AUTO device，MLX 强调 unified memory，Ascend 的 MindIE / vLLM-Ascend / SGLang-on-Ascend 在推进自己的高性能推理栈；但 CUDA、ROCm、OpenVINO、Metal/MLX、CANN 之间的内存对象、KV 对象、通信库与调度接口差异仍然很大。也就是说，你如果今天要做产品，**必须从一开始就把 runtime 内核设计成可插拔后端**，否则后续迁移成本会非常高。citeturn30search18turn31search3turn30search3turn30search7turn33search3turn33search7

**可观测性墙** 则是很多团队最容易低估的一堵墙。ProfInfer、Agentic AI Workload Characteristics、CCL-Bench、Frontier 都在强调：没有端到端 trace、没有 what-if、没有 resource perturbation、没有 task-level 指标，就无法判断该加 DRAM、加 SSD、加 NPU、还是改调度。对一体机规格寻优来说，观测体系本身就是产品能力，而不是辅助工具。citeturn25view1turn23view2turn25view3turn25view2

综合迁移判断，我建议把近两年文献分成三档。**可直接迁移**：NEO、KVPR、DAOP、KTransformers、CoX-MoE、APEX、MORI、ProfInfer。**需要改造**：DistServe、AMPD、PPD、EPD、vLLM-Omni、LiveServe。**不适合直接迁移，只适合作为方向启示**：Pie、SuperInfer、ITME、以及过度依赖统一内存/超高带宽 fabric 的体系结构论文。citeturn10view0turn12view1turn16view0turn18view0turn16view3turn28view2turn23view0turn25view1turn38view0turn21view1turn21view0turn36view0turn35search1turn35search0turn18view1turn13view0turn8search2

## 业界系统映射与工程验证

工业与开源系统并没有替代学术论文，但它们非常清楚地验证了学术趋势正在落地。NVIDIA 这条线最完整：Grace Hopper / Grace Blackwell 通过 **NVLink-C2C 与统一高带宽内存池** 提供强耦合 CPU-GPU 基座；Dynamo 已把 **Disaggregated Serving、KV Cache-Aware Routing、KV Cache Offloading** 和 **NIXL** 组合成产品化方向；TensorRT-LLM 则直接支持 **KV cache reuse、host memory offloading、chunked context**。从论文视角看，这几乎是把 DistServe / SuperInfer / KV-tiering / cache reuse 这一整套研究方向工程化了。对小算力一体机而言，最重要的不是照搬 Dynamo 的分布式规模，而是学习它的 **KV Block Manager、memory-tier offload 和 data-plane/control-plane 分离**。citeturn29search0turn34search7turn34search1turn34search5turn34search15turn34search17

AMD 路线的重点在 **统一内存 APU / AI PC**。MI300A 官方资料明确给出 **24 个 Zen 4 CPU 核 + 228 个 CDNA3 GPU CU + 128GB unified HBM3 + shared address space**；Ryzen AI Max / Halo 则把统一内存与本地大模型推理拉到工作站/笔记本级别。对你的主题来说，这意味着 AMD 平台可能是“小算力一体机”里最接近学术论文中“CPU 与 GPU 真正共享大内存池”的商业化路线之一。它非常适合落地 **KV 热温层驻留、专家冷热分层、embedding/rerank/vector CPU/GPU 并行** 等策略。citeturn31search4turn31search0turn31search13turn31search1

Intel 的 OpenVINO 路线则更偏 **多设备编排与低功耗 NPU 落地**。OpenVINO 官方文档已经把 CPU、GPU、NPU 列为一等推理设备，并支持 AUTO device 选择；其 AI PC 页面更直接强调 Windows 设备上的 CPU/GPU/NPU 加速协同。这和学术论文中的 llm.npu / HeteroInfer 可以形成很自然的映射：**NPU 跑规则化块，CPU 兜底动态/短算子，GPU 负责吞吐和兼容性。** 对 AI PC 和低功耗本地 agent 盒子尤其重要。citeturn30search18turn31search3turn30search2turn30search6

Apple 的 MLX / Core ML / Core AI 路线，本质上是在统一内存架构上构建本地大模型 runtime。MLX 明确强调 **arrays live in shared memory**，无需 CPU↔GPU 显式数据传输；Apple 的开发者资料也反复强调 Apple silicon 的 unified memory、CPU/GPU/Neural Engine 协同，以及本地 agentic AI 支持。这条路线对你最重要的启示是：**统一地址空间 + 高层 runtime 抽象，会让“小算力一体机”的异构协同难度显著下降。** 从技术布局角度，未来你应优先把 runtime 的 memory object / KV object API 做干净，以便适配这类平台。citeturn30search3turn30search7turn32search12turn32search15turn32search17

华为 Ascend / Kunpeng 这条线更强调 **推理软件栈一体化**。Ascend 社区已把 CANN、MindIE、vLLM-Ascend、SGLang-on-Ascend、HCCL/HIXL 等能力组织成了完整推理方案；MindIE 明确支持 Continuous Batching、PageAttention 与 P/D disaggregation；HIXL 文档甚至直接把 **PD disaggregation、parameter caching** 作为其应用场景。工程上，这说明“**面向 NPU 的异构推理生态**”正在从单一算子支持，走向完整 memory/communication/runtime 栈。这对本地 NPU 一体机和 2–8 节点小集群都很有意义。citeturn31search2turn33search3turn33search6turn33search7turn33search1

开源框架层面，vLLM、SGLang、LMCache、Mooncake 正在把学术论文里的关键机制公开化。vLLM 文档已经给出 **disaggregated prefill** 和 **LMCache integration**；SGLang 的 HiCache 文档则明确采用 **GPU memory + host memory + external storage backend 的三级层次 KV cache**；LMCache 进一步把 KV 从“进程内临时状态”提升为可持久化、可跨引擎复用、带观测能力的对象；Mooncake 则把分布式 KV storage 与高带宽 transfer engine 结合起来。对小算力产品来说，最关键的不是全部引入，而是尽快形成 **统一的 KV object 层**，否则所有 cache/offload/prefix reuse 都会变成框架特例。citeturn29search10turn29search6turn29search3turn29search19turn30search12turn30search20turn30search1turn30search21

## 未来趋势与技术布局

如果按照时间轴看，我认为 **2026–2027、2027–2029、2029–2031** 会分别对应“可验证原型 → 系统化能力 → 体系结构级能力”三个阶段，而你要做的技术布局也应按这三个层次推进。

在 **2026–2027**，最值得做的是一批“能在单机/小集群上快速验证”的原型。第一，是 **CPU/DRAM/NVMe 参与的 KV/Prefix/Context 分层原型**，核心不在于存得多，而在于恢复路径够快、trace 够清楚、与 tool-gap 联动。第二，是 **MoE expert 冷热预测与二层预取**，优先验证 KTransformers / DAOP / CoX-MoE 这类机制在本地机上的收益边界。第三，是 **Agent tool-gap 感知 KV 保活/换出**，这几乎可以直接从 MORI 的问题设定出发。第四，是 **embedding/rerank/vector search 的 CPU/NPU 协同**，让 GPU 把窗口留给 prefill/decode 主路径。第五，是 **多模态 E/P/D pipeline profiling**，先把视频/视觉/LLM/VAE 的时间和内存剖开再谈优化。第六，是 **一体机 trace + bottleneck dashboard**，把 TTFT、ITL、JCT、cache hit、HBM/DRAM/NVMe bytes、CPU core·s、Tasks/J 全部串起来。citeturn23view0turn18view0turn16view0turn16view3turn25view1turn23view2turn36view0

进入 **2027–2029**，真正的竞争点会从“单点技巧”转向“runtime 系统化能力”。届时最有价值的是：**session/workflow-aware runtime**、**可插拔异构调度器**、**统一 KV object API**、**CPU/GPU/NPU 混合执行计划**、**小集群 remote KV / unified memory 扩展**、以及 **功耗-SLO 联合控制**。这一步的本质是把当前分散在 NEO、FlexInfer、MORI、LMCache、EPD、vLLM-Omni 里的思路，收敛成一个完整 runtime。到这个阶段，产品差异化不再是“一条优化技巧”，而是“这台机器是否真正理解 agent workflow，以及是否能基于 workflow 调动异构资源”。citeturn10view0turn11view2turn23view0turn30search12turn36view0turn35search1

到了 **2029–2031**，体系结构级能力会开始决定上限。届时值得期待的方向包括：**CPU/NPU/GPU 对等异构计算平面**、**统一地址空间 + 分层内存硬件支持**、**near-data KV / expert / vector 加速**、**面向 agent workload 的自适应模型-缓存-工具联合调度**、以及 **面向 Agent 的硬件规格仿真器**。从今天的论文看，SuperInfer、Pie、ITME、MI300A、MLX、Ryzen AI Max 这些工作虽然暂时不一定能直接搬到你的产品里，但它们都在指向同一个终局：**下一代小算力一体机不会把 CPU/GPU/NPU 看成“三个不同设备”，而会把它们看成“同一个工作流的三个资源层”。** citeturn13view0turn18view1turn8search2turn31search4turn30search3turn31search13

基于上述判断，我给出的技术布局建议如下。

| 优先级 | 建议布局 | 为什么现在就该做 | 关键验证指标 |
|---|---|---|---|
| P0 | Agent workload trace schema | 没有 workflow 级 trace，就无法讨论 tool gap、KV 生命周期与任务级 goodput | request→session→workflow 关联率、JCT、Tasks/J、cache 恢复时延 |
| P0 | CPU/GPU/NPU 阶段级 profiling | 先分清 prefill/decode/encode/tool 哪段在卡 | TTFT、ITL、CPU core·s、PCIe bytes、HBM/DRAM/NVMe bytes |
| P0 | KV/Prefix/Context 分层与恢复 | 是小显存机器最通用也最必要的能力 | reload miss rate、prefix hit rate、恢复时延、TTFT P95 |
| P0 | CPU 侧工具执行与推理 admission control | Agent 机不是纯推理盒子，CPU 冲突会直接毁掉任务时延 | JCT、tool wait overlap、任务成功率 |
| P0 | MoE expert 冷热预测与预取 | 如果押注 DeepSeek/Qwen-MoE，本项收益最大 | expert hit rate、PCIe bytes、tok/s、准确率变化 |
| P0 | 多模态端到端 pipeline profiling | 不先拆阶段，就谈不上 E/P/D 或媒体引擎协同 | encode/prefill/decode/VAE/video codec 分段时延 |
| P1 | heterogeneous runtime / router | 从“单优化”升级为系统竞争力 | workflow goodput、SLO attainment |
| P1 | 选择性 Prefill/Decode/Encode 分离 | 单机不适合全量池化，但适合轻量阶段隔离 | TTFT、ITL、JCT、GPU 利用率 |
| P1 | CPU 侧 vector / sparse index / short matrix 库 | 是 CPU 真正有性价比的协同算力位置 | embedding/rerank 吞吐、GPU 抢占减少量 |
| P1 | direct SSD / bypass CPU 数据路径 | 长上下文与 agentic KV 迟早碰到 I/O 墙 | NVMe bytes、读放大、恢复时延 |
| P1 | 统一 memory object / KV object 管理 | 没有对象层，跨后端协同无法产品化 | 跨引擎复用率、故障恢复、后端切换成本 |
| P2 | coherent memory / UMA / CXL / unified address space | 长期硬件上限所在 | 迁移开销、拷贝次数、能耗 |
| P2 | near-data KV / expert cache | I/O 墙的最终解决方向 | bytes/J、恢复时延、容量扩展性 |
| P2 | 自动生成 CPU/NPU/GPU 混合执行计划 | 让平台适配从手调走向自动化 | 计划生成开销、性能逼近最优比 |
| P2 | Agent hardware spec simulator | 为后续整机 SKU 反推提供依据 | 仿真误差、规格-收益敏感度 |

上述布局基本上把学术论文里的“分散创新点”重新组织成了适合技术规划的能力栈。citeturn10view0turn18view0turn23view0turn25view2turn30search12turn34search15

## 结论与可执行清单

最后把本次调研压缩成最重要的结论。第一，**CPU 已经不是单纯 host，而是小算力一体机里最重要的状态管理与 workflow 协同资源。** 第二，**GPU/NPU 仍然是 dense 主路径的核心，但 CPU 在 KV、MoE、工具链、短算子、调度与功耗控制上的价值正在快速上升。** 第三，**最先落地的不是全面 heterogeneous execution，而是状态分层与 workflow-aware runtime。** 第四，**NPU 路线最适合承担 prefill 中规则化、高重复的块；CPU 负责 outlier、tool、I/O 与控制平面。** 第五，**MoE 是 CPU 真正有机会升级为计算平面的突破口。** 第六，**多模态系统的核心不是再造一个 LLM 引擎，而是管理 encode/prefill/decode/VAE/codec 的 stage graph。** 第七，**agent 场景必须用 JCT、completed tasks、Tasks/J 来替代纯 tokens/s。** 第八，**统一 KV object、trace schema 与 profiling/what-if 能力，应该被当作平台基础设施而不是辅助工具。** 第九，**GH200/MI300A/UMA/CXL 代表的是未来方向，但你近期产品应以 PCIe/DRAM/NVMe 现实约束来反推方案。** 第十，**如果你的目标是“小算力一体机的增强”，最值得押注的不是更大的模型，而是更聪明的异构 runtime。** citeturn10view0turn18view0turn28view1turn36view0turn23view5turn25view1turn13view0turn31search4

我建议优先做以下五个原型。

| 原型 | 输入 | 输出 | baseline | 指标 | 预期收益 | 核心风险 |
|---|---|---|---|---|---|---|
| Tool-gap aware KV lifecycle | agent trace、tool duration、KV footprint | per-session keep/offload/evict policy | 固定 TTL 或 LRU | JCT、TTFT P95、reload miss、GPU 利用率 | coding/deep research agent 的尾延迟显著下降 | 工具时长预测不稳，可能误判 |
| PCIe-aware KV partial recompute | 模型层信息、PCIe 带宽、KV 大小 | 传输-重算切分点 | 全量 KV 回传 | decode latency、throughput、PCIe bytes | 单机长上下文显著增益 | 工程实现复杂，需改 runtime |
| MoE hot/cold expert CPU-GPU scheduler | expert activation trace、CPU AMX/GPU profile | expert placement + prefetch plan | 静态 GPU cache / 简单 offload | expert hit rate、tok/s、accuracy、PCIe bytes | 本地 DeepSeek/Qwen-MoE 体验提升最大 | workload 漂移时 cache 失效 |
| 一体机 stage profiler | engine trace、CPU/GPU/NPU/NVMe 计数器 | encode/prefill/decode/tool 分段 dashboard | 仅 GPU profiler | bottleneck attribution 准确性、overhead、可复现性 | 为后续所有优化提供依据 | 指标体系过粗则无法指导决策 |
| 轻量 E/P/D runtime | multimodal request DAG、设备拓扑 | 单机/多卡阶段调度与缓存管理 | encode+prefill 聚合执行 | TTFT、JCT、GPU occupancy、media engine utilization | 多模态与视频 Agent 体验提升 | 单机分离过度可能被 PCIe 反噬 |

从后续跟踪角度，最值得持续关注的会议和关键词是：**MLSys、OSDI、SOSP、ASPLOS、FAST、ICLR/ICML/NeurIPS systems、MobiSys/edge AI workshops**；关键词则建议持续盯住 **agentic workload serving、tool-aware KV cache、workflow-aware scheduling、MoE expert offloading、coherent memory inference、CXL tiered memory、EPD/PPD disaggregation、NPU+CPU LLM inference、direct storage for inference、KV object layer**。就论文名单而言，建议持续跟踪 **SuperInfer、AMPD、PPD、MARS、MORI、LiveServe、Frontier、ITME、M\*** 以及 vLLM / SGLang / LMCache / Mooncake / Dynamo / TensorRT-LLM 的官方更新。citeturn13view0turn21view1turn21view0turn23view3turn23view0turn35search0turn25view2turn8search2turn37search9turn29search10turn29search19turn30search12turn34search7