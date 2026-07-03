# 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026）

## 1. 执行摘要

在 2025 至 2026 周期内，大语言模型（LLM）、多模态大模型（MLLM）和扩散变换器（DiT）在本地一体机、智能工作站、塔式服务器等小算力平台上的部署，经历了一场深刻的“全硬件栈深度协同”范式革命。随着上下文窗口迈向百万级、自回归视频生成成为主流，传统的纯加速器（GPU/NPU）独占式推理模型正被彻底打破，以下十条核心技术趋势概括了这一变革：

1.  **多核控制平面治理与主导地位确立**：多加速器集群或单卡系统的核心瓶颈已从单纯的算力饱和，转变为由 CPU 调度延迟、内核启动延迟及集体通信（如 NCCL/HCCL）同步开销引起的硬件饥饿，分配合理的多核 CPU 资源可提升首字延迟（TTFT）达 1.36–5.40 倍<sup>1</sup>。

2.  **CPU 协同计算由“备份”向“并行动力源”跃升**：依托 Intel AMX（高级矩阵扩展）和 ARM SME（可伸缩矩阵扩展）等芯片级矩阵乘法单元，现代 CPU 的 GEMM 吞吐量已达到 20–40 TFLOPS<sup>2</sup>，使得就地分担非热点专家、稀疏 Block 或是计算部分注意力（Attention）Logits 成为可能<sup>2</sup>。

3.  **KV Cache 虚拟地址连续性的重构**：为了规避 PagedAttention 改变虚拟地址连续性所带来的算子开发、适配和性能开销，vAttention 等技术利用 CUDA 虚拟内存 API 重构了物理分块但虚拟地址连续的内存管理体系，使得非 Page 化的前沿算子（如 FlashAttention-3）得以零修改开箱即用<sup>5</sup>。

4.  **状态对象化与全分层回流机制落地**：KV Cache、噪声缓存（Noise Cache）、专家权重（Expert Weights）、Adapter 从推理引擎内部临时 Tensor 提升为可命名、可定位、可迁移、可压缩的状态对象。DRAM、CXL 扩展内存、SSD 及直通存储（GPU Direct Storage）之间建立了感知语义的动态换入换出与预取机制<sup>7</sup>。

5.  **CXL 一致性共享内存池解除容量物理限制**：依托 CXL 2.0 及 3.0 协议的高带宽、低延迟一致性互联，CXL 内存池（CMM-D）与 LMCache 等框架结合，在多卡协同中实现了接近本地 DRAM 性能（92% 以上）的超大规模 KV Cache 存储与共享<sup>7</sup>。

6.  **混合 EPD（Encode-Prefill-Decode）三阶段完全解耦**：多模态推理框架（如 TriInfer）打破了传统的两阶段划分，将视觉/语音编码（Encode）作为独立阶段，通过双流并发和混合部署，显著提升了异构硬件利用率，使吞吐量提高达 3.7 倍<sup>10</sup>。

7.  **多智能体（Multi-Agent）与工作流感知的协作式 KV 共享**：针对编码代理、社交模拟等多 Agent 场景中的 All-Gather 提示词结构，TokenDance 和 PBKV 等框架通过位置无关复用、结构化路径预测以及增量存储，将内存占用降低达 94%<sup>12</sup>。

8.  **自回归视频生成的 Rolling KV 与无损时序编码**：自回归视频扩散（Wan2.1/2.2 等）中庞大的时空激活态带来了严重的内存压力<sup>14</sup>。FlashDecoder 和 Future Forcing 通过固定大小窗口的 Rolling KV 缓存与前瞻性合并算法，在保持视频连贯性的前提下，将解码阶段的内存需求降低了 11 倍<sup>15</sup>。

9.  **全系统级异构模拟与协同收益精准判定**：面对繁杂的协同硬件空间，LLMServingSim 2.0 等高精度周期级（Cycle-level）模拟器能够整合动态批处理、CXL 路由与功耗模型，以低于 1% 的误差为异构调度提供决策支持<sup>17</sup>。

10. **全栈国产化适配生态成熟**：昇腾 NPU 与鲲鹏 CPU 通过 CANN 8.5/9.0、vLLM-Ascend、LMCache-Ascend 的深度集成，全面支持了基于 aclgraph（图模式）的 Speculative Decoding、专家并行负载均衡（EPLB）以及 Mooncake 协同存储，实现了异构协同方案的国产化平替<sup>19</sup>。

## 2. 总论文矩阵

| **序号** | **归属方向** | **论文/系统名称** | **发表/预印本时间** | **核心机构** | **会议/来源** | **核心协同机制简介** |
|----|----|----|----|----|----|----|
| 1 | **方向 A** | LIA<sup>2</sup> | 2025-06<sup>2</sup> | Google DeepMind, SNU, UIUC<sup>2</sup> | ISCA 2025<sup>2</sup> | Intel AMX 算力协同 + CXL 内存卸载<sup>2</sup> |
| 2 | **方向 A** | NEO<sup>24</sup> | 2025-05<sup>25</sup> | 哈佛大学 (Harvard)<sup>24</sup> | MLSys 2025<sup>25</sup> | 异步 GPU-CPU 流水线，分担解码 Attention 计算<sup>24</sup> |
| 3 | **方向 A** | Dovetail<sup>26</sup> | 2024-12 (2025改版)<sup>26</sup> | 华中科技大学<sup>26</sup> | arXiv<sup>26</sup> | GPU 运行 Draft 预测，CPU 运行 Target 验证的投机解码<sup>26</sup> |
| 4 | **方向 B** | vAttention<sup>6</sup> | 2025-03<sup>6</sup> | 微软亚洲研究院 (MSR India), IIS<sup>6</sup> | ASPLOS 2025<sup>6</sup> | 虚拟地址连续与物理分页解耦，免 PagedAttention 算子<sup>5</sup> |
| 5 | **方向 B** | HybridGen<sup>9</sup> | 2026-04<sup>9</sup> | 蔚山科学技术院 (UNIST) 等<sup>28</sup> | arXiv<sup>9</sup> | 连续层相似度预测，CPU 提前计算 Attention Logits<sup>4</sup> |
| 6 | **方向 B** | LMCache / SGLang HiCache<sup>8</sup> | 2025/2026<sup>8</sup> | 联想, 上海交大等 / 门多萨大学, 开发者社区<sup>8</sup> | 工业实践 / 技术博客<sup>8</sup> | 多级页式分层存储（DRAM/SSD/Mooncake）与 GPU 辅助异步 I/O<sup>8</sup> |
| 7 | **方向 C** | TriMoE<sup>32</sup> | 2026-03<sup>3</sup> | 中国科学院计算技术研究所<sup>3</sup> | arXiv<sup>32</sup> | GPU（热）+ AMX CPU（温）+ DIMM-NDP（冷）专家三阶协同<sup>3</sup> |
| 8 | **方向 C** | DALI<sup>33</sup> | 2026-02<sup>33</sup> | 中国科学院自动化研究所<sup>33</sup> | arXiv<sup>33</sup> | 0-1 整数规划贪婪分配 + 基于残差的专家预取<sup>33</sup> |
| 9 | **方向 C** | ZipMoE<sup>35</sup> | 2026-01<sup>35</sup> | 南京大学<sup>35</sup> | ICML 2026<sup>35</sup> | UMA 架构下 BF16 指数与尾数位分解，CPU 异步解压<sup>36</sup> |
| 10 | **方向 D** | TriInfer<sup>10</sup> | 2026-03<sup>10</sup> | 清华大学, 潞晨科技<sup>10</sup> | MLSys 2026<sup>10</sup> | 异构实例上的多模态 EPD 三阶段自适应调度与双流并发<sup>10</sup> |
| 11 | **方向 D** | FlexInfer<sup>39</sup> | 2025-02<sup>39</sup> | 佐治亚理工学院 (Georgia Tech) 等<sup>39</sup> | MLSys 2025<sup>39</sup> | 阶段感知的静态划分、CPU 运行及 GPU 卸载自适应决策<sup>39</sup> |
| 12 | **方向 E** | TokenDance<sup>13</sup> | 2026-04<sup>13</sup> | 浙江大学, 阿里等<sup>13</sup> | arXiv<sup>13</sup> | 针对多 Agent 场景 All-Gather 模式的分块与位置无关复用<sup>13</sup> |
| 13 | **方向 E** | PBKV<sup>12</sup> | 2026-05<sup>12</sup> | 香港中文大学<sup>12</sup> | arXiv<sup>12</sup> | 基于工作流历史与上下文的多步前瞻性 Agent KV 预测<sup>12</sup> |
| 14 | **方向 F** | FlashDecoder<sup>16</sup> | 2026-06<sup>16</sup> | 浦项工科大学<sup>16</sup> | CVPR 2026<sup>16</sup> | 纯 Transformer 视频 VAE 解码，无掩码 Rolling KV 机制<sup>16</sup> |
| 15 | **方向 F** | Future Forcing<sup>15</sup> | 2026-05<sup>15</sup> | 上海交通大学<sup>15</sup> | arXiv<sup>15</sup> | AR 视频生成中基于历史查询代理的无损 KV 剪枝与合并<sup>15</sup> |
| 16 | **方向 G** | LLMServingSim 2.0<sup>42</sup> | 2026-02<sup>17</sup> | 韩国科学技术院 (KAIST)<sup>17</sup> | ISPASS 2026<sup>42</sup> | Cycle 级硬软件联合仿真器，支持 CXL/PIM/MoE/存储分层<sup>42</sup> |
| 17 | **方向 H** | vLLM-Ascend<sup>43</sup> | 2025–2026<sup>43</sup> | 华为昇腾社区<sup>19</sup> | 工程发布<sup>43</sup> | 图 Capture（aclgraph）、EPLB 负载均衡及 Mooncake 适配<sup>19</sup> |

## 3. 每个方向的详细论文表（17篇核心系统及工程框架精细化剖析）

### 方向 A：CPU/GPU 或 CPU/NPU 协同推理执行

#### 论文一：LIA: Cost-efficient LLM Inference Acceleration with Intel Advanced Matrix Extensions and CXL

1.  **论文名称**：LIA: Cost-efficient LLM Inference Acceleration with Intel Advanced Matrix Extensions and CXL<sup>2</sup>

2.  **机构**：首尔大学 (SNU), Google DeepMind, 伊利诺伊大学厄巴纳-香槟分校 (UIUC)<sup>2</sup>

3.  **会议/来源**：ISCA 2025<sup>2</sup>

4.  **发表/预印本时间**：2025 年 6 月（正式发表）<sup>2</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：正式发表学术论文<sup>2</sup>

6.  **研究背景需求**：单张 GPU/NPU 显存（HBM）空间极其局限，使得超大参数大语言模型在本地工作站及单卡服务器上部署时需要极高硬件采购成本，而传统基于主板 CPU 内存卸载的框架（如 FlexGen）受限于 PCIe 通道的慢速串行传输，I/O 搬运成为绝对系统瓶颈<sup>2</sup>。

7.  **要解决什么问题**：如何在不购买多张高昂显卡的前提下，利用现代 Intel CPU 内置的强大硬件矩阵相乘单元（AMX），分摊矩阵运算以缩减主板 PCIe 传输总线上的数据量<sup>2</sup>。

8.  **核心贡献**：首次对 Intel 4th Gen (Sapphire Rapids) 和 6th Gen (Granite Rapids) CPU 的 AMX 单元进行了深度基准测试，分别实现了 20 TFLOPS 和 40 TFLOPS 的 GEMM 计算吞吐<sup>2</sup>。基于此设计了 LIA，一个将计算自适应卸载至 CPU AMX 并深度融合 CXL 扩展内存的高效单 GPU 协同框架<sup>2</sup>。

9.  **核心策略与机制**：

    - **Hardware Runtime 层**：深度重构了 Intel Extension for PyTorch (IPEX)<sup>23</sup>，建立了一种基于编译期的静态分块决策。

    - **Kernel 层**：将算术强度较低的逐元素算子（Element-wise ops）和 Softmax 保留在本地，而将大块 GEMM 操作就地指派给 CPU 本地的 AMX 单元计算。

    - **Storage / Data Plane 层**：引入 DDR-CXL 分层内存分配路由策略，确保延迟敏感型数据（如当前层 KV）保留在本地 DDR，而吞吐量驱动型参数（如大模型权重）驻留在性价比极高的 CXL 内存池中<sup>2</sup>。

10. **硬件与系统假设**：Intel Sapphire Rapids/Granite Rapids Xeon CPU（支持 AMX）<sup>2</sup>、1 ![image4]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image4.png) NVIDIA H100 GPU<sup>2</sup>、PCIe Gen5 ![image4]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image4.png)16 互联<sup>7</sup>、CXL 2.0 内存扩展模块<sup>2</sup>。

11. **结果收益和评估方式**：在 Sapphire Rapids 系统中，LIA 相比于 SOTA 单卡卸载框架（FlexGen）降低了 5.1 倍的端到端延迟，在 Granite Rapids 上则降低了 19 倍<sup>2</sup>；吞吐量分别提升了 3.7 倍和 5.1 倍<sup>2</sup>。此外，CXL 卸载在不损失性能的前提下，将最大支持 Batch Size 提升了 1.8 倍（从 900 提升至 1.6K）<sup>2</sup>。

12. **异构协同视角核心贡献**：打破了“CPU 仅作为存储网关”的局限，利用 CPU 本地的计算单元（AMX）执行其内存中参数的就地计算，彻底消除这部分权重的 PCIe 搬运过程。

13. **对三类技术趋势的对应关系**：

- 方向一：AMX/SVE 的引入实现 CPU 侧的高算力 GEMM 协同计算<sup>2</sup>；

- 方向二：基于 CXL 内存扩展（CMM-D）的非对称多级存储<sup>2</sup>。

14. **对小算力平台等硬件部署的启发**：小算力工作站拥有充沛的主机内存（128GB–512GB DDR5）和多达 32-64 核的处理器，LIA 能够将其闲置的主机算力转化为在线吞吐量。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**中**。鲲鹏 920 CPU 暂无类似 AMX 的密集型矩阵乘法协处理器（类似 Intel 的 Tile 结构），但若下一代鲲鹏 CPU 支持标准 SVE2 的矩阵向量微架构，该静态分配算法和分层运行时可平滑迁移。

16. **局限、风险和不可直接照搬之处**：Granite Rapids 的 40 TFLOPS 是 LIA 取得极高收益的物质基础，在缺乏硬件 GEMM 单元的低配 CPU 上，CPU 计算会迅速退化为新的延迟瓶颈。

17. **代码/开源链接**：[<u>ece-fast-lab/ISCA-2025-LIA</u>](https://github.com/ece-fast-lab/ISCA-2025-LIA)  
    \[cite: 44\]

18. **可靠性标注**：高置信（ISCA 2025 正式录用论文）<sup>2</sup>。

#### 论文二：NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference

1.  **论文名称**：NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference<sup>24</sup>

2.  **机构**：哈佛大学 (Harvard University)<sup>24</sup>

3.  **会议/来源**：MLSys 2025<sup>25</sup>

4.  **发表/预印本时间**：2025 年 5 月（正式发表）<sup>25</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：正式发表学术论文<sup>25</sup>

6.  **研究背景需求**：在线 LLM 服务面临高并发压力，通常依靠 Batching 提升吞吐，但 Batch Size 的上限严重受制于 GPU 的显存容量，当 KV Cache 溢出时系统只能采取准入控制，导致极高负载下的首字延迟剧烈恶化<sup>24</sup>。

7.  **要解决什么问题**：如何在不恶化单请求 SLO（服务等级目标）延迟的前提下，将本地主机 CPU 的“免费”算力与内存深度整合进在线高并发推理流中。

8.  **核心贡献**：提出了 NEO 系统。这是首个在保障在线推理延迟和无损精度的前提下，通过将部分解码阶段注意力计算（Decode Attention）与 KV 状态并行移交 CPU，成功提升在线服务吞吐量的协同系统<sup>24</sup>。

9.  **核心策略与机制**：

    - **Scheduler 调度层**：设计了“负载感知调度器（Load-aware Scheduler）”，在线监控 GPU 和 CPU 的任务队列状态，动态决策哪些请求被分配至 CPU 运行<sup>24</sup>。

    - **Kernel/Runtime 层**：提出“非对称 GPU-CPU 流水线（Asymmetric Pipelining）”。将一个逻辑批次拆分为两个非对称的子批次（Sub-batches）：子批次 A 在 GPU 上完整运行；子批次 B 则将解码 Attention 计算和 KV Cache 直接搬移至 CPU 内存，并由 CPU 线程执行注意力机制，最后将计算出的 Logits 回传至 GPU<sup>24</sup>。两部分计算在时间上高度重叠。

10. **硬件与系统假设**：单张 NVIDIA GPU（支持 T4、A10G、H100）<sup>24</sup> 配合多核高带宽本地 Host CPU<sup>24</sup>。

11. **结果收益和评估方式**：在代码生成（Code Generation）和文本摘要（Summarization）等多类真实 Workload 下，NEO 相比于纯 GPU 推理，在保障相同尾延迟的前提下，在 T4 上实现了高达 7.5 倍的吞吐量提升，在 A10G 上提升了 26%，在 H100 上提升了 14%<sup>45</sup>。在配备更强 CPU 的配置下，A10G 上的吞吐提升能达到 79.3%<sup>45</sup>。

12. **异构协同视角核心贡献**：通过非对称流水线设计，使得 PCIe 传输隐藏于 GPU 自身的计算气泡中，从而利用 CPU 内存容量置换出昂贵的 GPU HBM，增大有效 Batch Size。

13. **对三类技术趋势的对应关系**：

- 方向一：阶段化异构协同计算，GPU 执行前向推理，CPU 执行解码端部分 Attention 算子<sup>24</sup>；

- 方向二：模型状态对象化与分层回流中的 KV 状态分层存储<sup>24</sup>。

14. **对小算力平台等硬件部署的启发**：极其契合单卡/双卡小型工作站。因为这类平台往往拥有非常充沛的主机内存（128GB–512GB DDR5）和多达 32-64 核的处理器，NEO 能够将其闲置的主机算力转化为在线吞吐量。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。该机制改写的是外围推理引擎的 Scheduler 和 Batching 划分逻辑，不依赖特定底层指令。可通过在 vLLM-Ascend 中集成 CPU-NPU 异步流（Stream）实现。

16. **局限、风险和不可直接照搬之处**：CPU 执行 Attention 计算的绝对延迟远高于 GPU。如果子批次 B 划分过大，会严重拉长整批的尾延迟（Straggler Effect），必须依赖精确的算力比率预测器。

17. **代码/开源链接**：[<u>minlanyu/NEO (Paper details in project page)</u>](http://minlanyu.seas.harvard.edu/writeup/mlsys25.pdf)  
    \[cite: 24\]

18. **可靠性标注**：高置信<sup>25</sup>。

#### 论文三：Dovetail: Speclative Decoding under Heterogeneous Device Architectures

1.  **论文名称**：Dovetail: Speclative Decoding under Heterogeneous Device Architectures<sup>26</sup>

2.  **机构**：华中科技大学<sup>26</sup>

3.  **会议/来源**：arXiv / 预印本<sup>26</sup>

4.  **发表/预印本时间**：2024 年 12 月（2025 年 4 月改版）<sup>26</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：学术预印本<sup>26</sup>

6.  **研究背景需求**：在大端与小端设备（如一体机中的独立显卡与 CPU）共存的本地异构环境中，直接运行大参数 LLM 极其缓慢。 speculative decoding（投机解码）是加速推理的一种有效手段，但在异构设备上分配 Draft 和 Target 模型会带来严重的通信和验证延迟。

7.  **要解决什么问题**：如何在不牺牲精度、不重写底层验证内核的前提下，将轻量的自回归生成过程（Draft）和极度繁重的大模型多 Token 并行验证过程（Verification）在异构硬件间高效切分<sup>26</sup>。

8.  **核心贡献**：提出了 Dovetail 系统。颠覆了传统“CPU 跑小 Draft，GPU 跑大 Target”的思维定势，设计了“反向异构投机验证（Reverse Heterogeneous Speculation）”范式：将小草稿模型部署在强计算端的 GPU 上，而将大目标模型验证阶段部署在超大内存容量的 CPU 上，通过极细粒度的数据交互设计，使整体推理达到正收益<sup>26</sup>。

9.  **核心策略与机制**：

    - **Agent Runtime/Scheduler**：Draft 模型在 GPU 上进行多步快速生成，产生 speculative tokens。

    - **Kernel 优化**：引入了动态门控融合（Dynamic Gating Fusion, DGF）机制，在 CPU 验证端优化了多 Token 并行验证内核<sup>26</sup>。

    - **数据平面的极简数据传输**：不传输任何中间层 KV Cache，仅在 GPU 和 CPU 之间传递紧凑的 Token IDs 以及对应的概率向量（Probability Vectors），极大地缩减了 PCIe 总线传输瓶颈<sup>26</sup>。

10. **硬件与系统假设**：消费级显卡（如 RTX 3090/RTX 4060，显存容量仅为 3GB–7GB）<sup>26</sup>、本地多核 Host CPU（配备大量 DDR 内存）。

11. **结果收益和评估方式**：在 LLaMA2-Chat 7B 评估中，在仅提供 3GB 显存的极端限制下，Dovetail 仍能在 MT-Bench 上实现 4.62 到 5.86 token/s 的生成速度，比传统 CPU 独占式推理加速了 2.25 倍<sup>26</sup>；当显存放宽到 7GB 时，速度达到 6.5 到 8.0 token/s，加速比达 3.08倍<sup>26</sup>。在 RTX 3090 + 强多核 CPU 上验证 LLaMA2-Chat 13B，最高获得了 10.14 倍的单进程生成加速。

12. **异构协同视角核心贡献**：利用低显存 GPU 进行高频词、低强度的自回归草稿采样，最大程度减少了 CPU 进行频繁逐词计算的延迟，使得大 Target 驻留在 CPU 内存中仅做大块的矩阵验证运算，避开了 PCIe 的带宽吞吐红线。

13. **对三类技术趋势的对应关系**：

- 方向一：投机解码中的异构协同计算，CPU 与 GPU 角色对调<sup>26</sup>。

14. **对小算力平台等硬件部署的启发**：对未配备大容量显存的轻量级一体机（例如仅有单张 RTX 4060 8G 显卡的边缘终端），Dovetail 提供了一种不损失精度即可流畅运行 13B–34B 级别大模型的低成本方案。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。昇腾 310P 推理一体机（仅有 24GB 显存）可以通过将大 Target 部署在鲲鹏 CPU DDR 内存中，而将轻量的 Speculative Draft 编译入 310P，实现低时延的高级验证。

16. **局限、风险和不可直接照搬之处**：由于验证任务最终在 CPU 上跑，CPU 多线程验证的绝对时延 ![image2]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image2.png) 依然很大<sup>26</sup>，若 Draft 模型的接受率（Acceptance Rate）偏低，高频的无效验证会导致整体速度退化至普通 CPU 推理水平<sup>26</sup>。

17. **代码/开源链接**：[<u>Dovetail GitHub Repository (referenced in preprint)</u>](https://arxiv.org/abs/2412.18934)  
    \[cite: 26\]

18. **可靠性标注**：中置信。

### 方向 B：KV / Prefix / Context 分层卸载与状态恢复

#### 论文四：vAttention: Dynamic Memory Management for Serving LLMs without PagedAttention

1.  **论文名称**：vAttention: Dynamic Memory Management for Serving LLMs without PagedAttention<sup>6</sup>

2.  **机构**：微软亚洲研究院 (MSR India), IIS<sup>6</sup>

3.  **会议/来源**：ASPLOS 2025<sup>6</sup>

4.  **发表/预印本时间**：2025 年 3 月（正式发表）<sup>6</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：正式发表学术论文<sup>6</sup>

6.  **研究背景需求**：PagedAttention 虽然完美解决了物理显存的零碎化问题，但它强制将原本连续的虚拟内存也打碎成非连续的物理 Page<sup>6</sup>。这迫使开发者必须编写专门的非连续 Attention Kernel（如 Paged-FlashAttention），导致最新的高性能、高度硬件优化算子（如基于 Hopper 架构的 FlashAttention-3）无法直接适配，存在巨大的软件栈分裂与迁移成本<sup>5</sup>。

7.  **要解决什么问题**：如何在物理层面享受按需分页（Dynamic Paging）以消除内存碎片的优点的同时，在虚拟内存层面为 Attention 算子维持完美的连续性。

8.  **核心贡献**：提出了 vAttention。通过巧妙利用 CUDA 虚拟内存管理 API（Virtual Memory Management, VMM），在不修改任何标准 Attention 算子、不引入虚拟映射碎片开销的前提下，替代了 PagedAttention 的核心功能<sup>5</sup>。

9.  **核心策略与机制**：

    - **KV Manager / Storage Data Plane**：vAttention 预先在虚拟地址空间中为每个 Batch 的请求预留出最大可能长度（如 ![image20]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image20.png) tokens）的连续虚拟地址段（Virtual Buffer）<sup>46</sup>。由于 64 位系统中用户空间虚拟内存极其充沛（高达 128TB–256TB），这种预分配完全无物理成本<sup>46</sup>。

    - **Hardware Runtime 层**：在推理运行时，通过底层的操作系统和显卡驱动调用 cuMemCreate、cuMemMap 和 cuMemAddressRange，以物理页（如 2MB 物理巨页）为粒度，动态地将新申请的物理显存映射到该 Virtual Buffer 的后继连续虚拟地址上<sup>5</sup>。

    - **延迟释放（Deferred Reclamation）**：当请求完成时，不立即销毁物理绑定，而是将其放回空闲池，后续新请求可直接复用该连续段，消除高频操作系统映射映射的系统税开销<sup>46</sup>。

10. **硬件与系统假设**：NVIDIA GPU（支持 CUDA VMM API，从 Ampere A100 到 Hopper H100 等均支持）<sup>5</sup>。

11. **结果收益和评估方式**：在 Yi-6B、Llama3-8B 和 Yi-34B 模型上，使用 1-2 张 A100 GPU 进行连续 Batching 测试<sup>5</sup>。由于 vAttention 能够直接调用未加修改的、运行速度极快的原生 FlashAttention-2 连续内存算子，其解码阶段吞吐量相比于原装 PagedAttention 版 vLLM 提升了 1.99 倍<sup>5</sup>；在长上下文（Long-context） Workload 下，相比于使用 FlashInfer 和 FlashAttention-2 的 PagedAttention 变体，端到端 serving 吞吐分别提升了 1.23 倍和 1.18 倍<sup>5</sup>。在 Hopper 架构上适配 FlashAttention-3 时，取得了 1.26 到 1.50 倍的系统吞吐提升<sup>5</sup>。

12. **异构协同视角核心贡献**：通过 OS 级的虚拟内存重新设计，解决了加速器显存动态增长管理与极速计算算子之间的核心架构冲突，为多级存储之间的大块搬移提供了连续地址基座。

13. **对三类技术趋势的对应关系**：

- 方向二：模型状态对象化，将 KV Cache 变更为虚拟地址连续的、支持物理弹性分页的高层内存对象<sup>5</sup>。

14. **对小算力一体机/工作站的启发**：开发人员可以轻松地在低算力设备的运行时中调用任何由底层 C++ 静态编译的极速线性算子（例如 INT4 量化自适应算子），显著降低了一体机软件棧的适配复杂度。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**中**。这高度依赖于底层驱动和底层 Runtime 是否开放了类似 CUDA VMM（地址段保留与动态物理段映射绑定）的算力 API。华为 CANN 9.0/8.5 目前在“FULL_AND_PIECEWISE”图捕获模式中引入了部分自适应内存映射策略<sup>19</sup>，如果 CANN 团队完全打通 NPU 端的虚拟内存连续映射 API，该技术将具备高移植性。

16. **局限、风险和不可直接照搬之处**：频繁调用 cuMemMap 依然存在非零的 CPU/Driver 侧时间开销。在高并发、极短文本、超高并发 QPS 下，这些开销可能会显著削弱其实际加速比。

17. **代码/开源链接**：[<u>arxiv.org/abs/2405.04437 (Integrated into vLLM-compatible forks)</u>](https://arxiv.org/abs/2405.04437)  
    \[cite: 6\]

18. **可靠性标注**：高置信<sup>6</sup>。

#### 论文五：HybridGen: Efficient LLM Generative Inference via CPU-GPU Hybrid Computing

1.  **论文名称**：HybridGen: Efficient LLM Generative Inference via CPU-GPU Hybrid Computing<sup>9</sup>

2.  **机构**：UNIST（蔚山科学技术院）等<sup>28</sup>

3.  **会议/来源**：arXiv / 预印本<sup>9</sup>

4.  **发表/预印本时间**：2026 年 4 月<sup>9</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：学术预印本<sup>9</sup>

6.  **研究背景需求**：随着长上下文窗口延伸至数十万甚至数百万 tokens，KV Cache 体积膨胀至数百吉字节，使得本地推理被迫实施多级卸载。然而，现有的卸载机制在 CPU 内存层仅作纯数据归档，导致 CPU 本身庞大的计算潜力被闲置，同时存在跨 PCIe 的严重 I/O 阻碍。

7.  **要解决什么问题**：如何在超长生成上下文中，利用 CXL 一致性分层扩展内存，彻底消除由于单步依赖（Attention Multidimensional Dependency）导致的 GPU 与 CPU 协同计算受阻问题<sup>4</sup>。

8.  **核心贡献**：提出了 HybridGen。首创了“注意力 Logits 并行（Attention Logit Parallelism, ALP）”与“语义感知 KV 分布映射”，将 CPU 充当计算主动发起者，在不损失长序列生成精度的情况下实现极高带宽的异构生成<sup>4</sup>。

9.  **核心策略与机制**：

    - **Logits Calculator (CPU 侧支持)**：发现 transformer 相邻层之间的 Residual Stream 存在极高的余弦相似度（Cosine Similarity 接近 1.0）<sup>4</sup>。基于此，CPU 端引入 Logits 计算器，在 GPU 正在计算第 ![image19]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image19.png) 层的 Attention/FFN 时，CPU 利用其第 ![image19]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image19.png) 层的输入表征以及本地内存中第 ![image22]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image22.png) 层的 ![image21]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image21.png) 向量，**提前在 CPU 端计算出第** ![image22]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image22.png) **层的 Attention Logits 粗略值**<sup>4</sup>。

    - **数据压缩回传与选择性拉取**：CPU 不再将原始的、庞大的 ![image21]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image21.png) 搬运到 GPU。而是仅传输在 CPU 端算出的、体积极小的 Logits 向量以及由 Top-K 过滤选择出的少量对应 ![image16]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image16.png) 向量<sup>4</sup>。

    - **Semantic-aware KV Cache Mapping**：将较老、语义重要性低（热度衰减）的 KV 页通过异步队列放置于慢速 CXL 内存层中，而将高频触发、临近或带有 Attention Sinks 属性的语义页 Pin 在本地 DDR 内存，彻底从关键运行路径中抹除 CXL NUMA 带来的延迟惩罚<sup>4</sup>。

10. **硬件与系统假设**：GPU 加速卡（支持 H100、A10G、T4）<sup>47</sup>、Host CPU DDR + 经由 CXL 扩展的高容量 CXL 内存池<sup>4</sup>。

11. **结果收益和评估方式**：在 3 类 LLM 模型、11 种尺寸（包含 LLaMA-3、Mistral 等）上测试，面对极长上下文 Workload，HybridGen 相比于 DeepSpeed-Inference、FlexGen 等 6 种 SOTA 分层存储和 KV 管理系统，平均实现了 1.41 倍至 3.20 倍的端到端吞吐性能提升，同时精度基本保持 lossless（无损）<sup>9</sup>。

12. **异构协同视角核心贡献**：通过预测 consecutive-layer 的相似性，解耦了原本硬性的逐层算力时序依赖，使得 CPU 能够提前执行下一层的 Logits 运算，把极重的数据拷贝转换为极轻的控制特征传递。

13. **对三类技术趋势的对应关系**：

- 方向一：利用层间输入相似性，提前交由 CPU AMX 并行计算下一层注意力偏置<sup>4</sup>；

- 方向二：模型状态对象化下的 CXL 一致性内存分层存储与按语义置换<sup>4</sup>。

14. **对小算力工作站的启发**：可以用极低成本外挂 1TB CXL 内存条，配合 CPU 的就地 ALP 计算，使单卡工作站能从容承载百万级输入上下文。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**中**。由于需要在鲲鹏 CPU 上并行执行下一层的 Logits 计算，这要求在 CANN 环境内建立高级的跨进程/跨核心计算同步通信。

16. **局限、风险和不可直接照搬之处**：层间输入相似性假设（Consecutive-Layer Similarity）虽然在大部分密集型 LLM 上成立，但对于某些网络架构（例如浅层快速突变的 Draft 网络或某些多模态交叉注意力层），相似度可能会大幅下降，进而导致预测 Top-K 索引失效。

17. **代码/开源链接**：[<u>arxiv.org/html/2604.18529 (Associated codes pending on AlphaXiv)</u>](https://arxiv.org/abs/2604.18529)  
    \[cite: 9\]

18. **可靠性标注**：中高置信。

#### 框架六：LMCache / SGLang HiCache (2025-2026 工业融合体系)

1.  **系统名称**：LMCache (与 SGLang HiCache / Mooncake 的工业级融合)<sup>8</sup>

2.  **机构**：联想, 上海交通大学, Moonshot AI (月之暗面), 开发者社区<sup>30</sup>

3.  **会议/来源**：GitHub 开源系统、NVIDIA GTC 2026、工业级技术博客<sup>8</sup>

4.  **发表/预印本时间**：2025 年 8 月至 2026 年 5 月<sup>30</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：工程框架文档与工业部署博客<sup>8</sup>

6.  **研究背景需求**：在多用户并发、大范围 Tool Call / RAG、多轮 Agent 迭代场景下，KV Cache 爆满极快，且在不同 Engine 节点、不同会话进程之间存在严重的大块文本重叠。如何将临时 Tensor 统一治理、多节点无损共享、异步极速分级卸载是当务之急<sup>30</sup>。

7.  **要解决什么问题**：彻底打通本地 HBM、Host RAM、CXL 内存条、NVMe 本地 SSD 到远端 KV 数据库（如 Valkey / Redis）之间的高速状态搬运，保障大面积 cache miss 时系统的首字延迟（TTFT）维持在 SLO 之内<sup>8</sup>。

8.  **核心贡献**：LMCache 联合 SGLang HiCache 建立了“多级页式分层存储（DRAM/SSD/Mooncake）”，通过解耦计算引擎与存储介质，将推理引擎的临时变量重构为全局可寻址、可压缩、多级直通的状态对象（HiCache 扩展了 RadixAttention 树）<sup>8</sup>。

9.  **核心策略与机制**：

    - **KV Manager / Storage Data Plane 层**：引入了全新的“页优先（Page-first）”Host 物理排布排布。因为 GPU 本身执行计算需要层优先（Layer-first），但对于总线 I/O 而言，页优先排布能够支持极大的单次传输 Transaction，使 CPU-GPU 传输吞吐提升 2 倍<sup>8</sup>。

    - **Kernel 层**：开发了一套特定的 **GPU 辅助异步 I/O 内核（GPU-assisted I/O Kernels）**，使得 CPU 内存至 HBM 的搬移不再单纯依赖系统级 CPU 阻塞调用，带宽利用率提升 3 倍<sup>8</sup>。

    - **Scheduler / Router 层**：在 Control Plane 支持了层级异步并行重叠（Overlapping），在第 ![image18]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image18.png) 层运行 Decode 注意力计算时，由控制后台流式异步预取第 ![image17]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image17.png) 层的分级页<sup>8</sup>。

10. **硬件与系统假设**：多卡 NVIDIA / 昇腾工作站，挂载高速本地 SSD、主机多路 DDR 内存或 CXL Switch 内存池<sup>7</sup>。

11. **结果收益和评估方式**：在 SGLang 搭载 HiCache-Mooncake 体系运行 LLaMA-3.1 70B 及大规模 RAG Workload，相比于无 offloading 的原生 SGLang 实现了高达 **6 倍的吞吐提升**，同时**降低首字延迟（TTFT）达 80%**<sup>8</sup>。在搭载 Valkey/Redis/Mooncake 的 local NVMe 试验中，实现了 42.6 倍的首字延迟跃升（TTFT 从冷启动 6.31s 缩减至 0.14s）<sup>51</sup>。

12. **异构协同视角核心贡献**：将 KV Cache 的生命周期从单卡单会话中解放出来，利用高并发的 CPU-GPU 异步重叠总线和页式压缩算法，将非活动状态降维转移至系统物理 SSD 阵列。

13. **对三类技术趋势的对应关系**：

- 方向二：模型状态对象化与分层回流（LMCache、Mooncake、HiCache 核心贡献）<sup>8</sup>。

14. **对小算力平台等硬件部署的启发**：塔式服务器或一体机在配置了少量显存但外挂了多块 PCI-E 4.0 NVMe SSD 时，可通过该机制在毫秒级内冷启动巨量 Prompt，无需重复预计算。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。已有 LMCache-Ascend 官方适配分支（依托 LMCache 适配的 MindSpore / CANN 9.0 HIXL/HComm 高速通道），提供了层级 KV cache offloading 与 shape 自适应机制<sup>20</sup>。

16. **局限、风险和不可直接照搬之处**：写直通（Write-through）策略对 PCIe 总线消耗极大，必须结合 hit-count 评估，选择性仅对高频热点（Hot spots）前缀开启写直传<sup>8</sup>。

17. **代码/开源链接**：[<u>LMCache Github Repository</u>](https://github.com/lmcache/lmcache)  
    \[cite: 30\]

18. **可靠性标注**：高置信（联想、交大官方生产级落地框架）<sup>30</sup>。

### 方向 C：MoE 专家卸载、专家预取与 fallback

#### 论文七：TriMoE: Augmenting GPU with AMX-Enabled CPU and DIMM-NDP for High-Throughput MoE Inference via Offloading

1.  **论文名称**：TriMoE: Augmenting GPU with AMX-Enabled CPU and DIMM-NDP for High-Throughput MoE Inference via Offloading<sup>32</sup>

2.  **机构**：中国科学院计算技术研究所 (ICT, CAS)<sup>3</sup>

3.  **会议/来源**：arXiv / 预印本<sup>32</sup>

4.  **发表/预印本时间**：2026 年 3 月<sup>3</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：学术预印本<sup>32</sup>

6.  **研究背景需求**：大吞吐离线或高并发本地推理场景下，Mixture-of-Experts (MoE) 架构带来了严重的内存空间危机。尽管前人尝试通过预取（Prefetching）来掩盖将专家模型从 DDR 搬运至 GPU 的时间，但是在单 Batch、单请求场景下，专家的计算时间（~0.3ms）远短于搬运时间（~28ms），导致“计算通信重叠”彻底失效。

7.  **要解决什么问题**：如何彻底解决异构平台在处理非热点专家（Non-hot Experts）时，由于内存带宽严重受限（Memory-bound）与算力闲置（Compute-idle）之间的结构性矛盾。

8.  **核心贡献**：提出了 TriMoE，这是首个融合了 GPU、AMX-Enabled CPU 和 DIMM-NDP（近内存处理器，如嵌入在内存条上的存内计算加速芯片）的异构三域联合 MoE 推理架构<sup>3</sup>。系统打破了以往将非热点专家统一视作 homogeneous 块的旧框架，创新性地开辟了三阶映射机制<sup>3</sup>。

9.  **核心策略与机制**：

    - **Static Expert-aware Stratification (三阶静态分层) / KV & Expert Manager**：将专家精确划分为三类：

      - **Hot Experts**：常驻 GPU 显存，极速处理共享公共专家逻辑<sup>3</sup>；

      - **Warm Experts**（约占 30%）：映射到支持 Intel AMX 的 CPU DDR 内存段，利用 CPU 本地的 AMX 单元直接就地计算，彻底绕过 PCIe 传输<sup>3</sup>；

      - **Cold Experts**（长尾低频专家）：直接卸载到 DIMM-NDP 引擎上，利用近存计算（Near-Memory Processing）的超高内部本地带宽执行<sup>3</sup>。

    - **Bottleneck-aware Scheduler (瓶颈感知调度层)**：根据实时负载动态预测计算和传输时延，动态调整专家负载。

10. **硬件与系统假设**：1 ![image4]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image4.png) NVIDIA GPU（带 HBM）<sup>32</sup>、1 ![image4]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image4.png) 多核 Intel Xeon（带 AMX 加速，挂载 256GB 系统 DDR5）<sup>3</sup>、支持 Near-Memory Processing 的新型 DIMM 内存条（DIMM-NDP）<sup>3</sup>。

11. **结果收益和评估方式**：在主流 MoE 模型（如 Mixtral-8x22B、DeepSeek-V2-Lite）下运行超大 batch 吞吐测试。TriMoE 相比于 SOTA 的 CPU-GPU 卸载框架（如 MoE-Lightning 和 Fiddler），在单 H100 平台上实现了高达 2.83 倍的端到端吞吐加速<sup>3</sup>。

12. **异构协同视角核心贡献**：精准洞察了不同存储硬件的延迟与带宽特性，对专家激活频次进行细粒度解耦，首次在 MoE 调度中将 CPU 本地算力、近存算力和 GPU 算力划归到对等的地位。

13. **对三类技术趋势的对应关系**：

- 方向一：CPU AMX 的温专家协同计算与 fallback 运行<sup>3</sup>；

- 方向二：基于 DIMM-NDP / Host DRAM / HBM 的全状态精细化对象划分<sup>3</sup>。

14. **对小算力平台等硬件部署的启发**：除了采购高昂的显卡，可以通过配置带有 AMX 或 SME 功能的 CPU 以及带有存内加速的硬件内存条，构成非对称的阶梯式低成本算力组合。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**中**。DIMM-NDP 属于目前工业界尚在量产推进中的新型内存，鲲鹏服务器尚未普及该硬件支持。但“GPU/NPU（热） + CPU-SVE/Neon（温）”的两级协同思想完全可以被 CANN 下的 EPLB（专家并行负载均衡器）吸收<sup>43</sup>。

16. **局限、风险和不可直接照搬之处**：严重依赖对专家激活率（Hot/Warm/Cold）在运行前或运行时的精确分类。若输入提示词分布极其偏颇导致原本分类为 Warm 的专家瞬间转为 Hot，会引发巨大的跨层同步开销。

17. **代码/开源链接**：[<u>TriMoE reference architecture (linked in paper metadata)</u>](https://arxiv.org/abs/2603.01058)  
    \[cite: 32\]

18. **可靠性标注**：中高置信（中科院计算所体系结构顶级团队研究）<sup>3</sup>。

#### 论文八：DALI: A Workload-Aware Offloading Framework for Efficient MoE Inference on Local PCs

1.  **论文名称**：DALI: A Workload-Aware Offloading Framework for Efficient MoE Inference on Local PCs<sup>33</sup>

2.  **机构**：中国科学院自动化研究所 (Institute of Automation, CAS)<sup>33</sup>

3.  **会议/来源**：arXiv / 预印本<sup>33</sup>

4.  **发表/预印本时间**：2026 年 2 月<sup>33</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：学术预印本<sup>33</sup>

6.  **研究背景需求**：在个人电脑或小型工作站上运行 Mixtral 8x22B 等大参数 MoE 模型时，内存带宽通常是致命瓶颈。而当前的 MoE 卸载方法往往采取硬编码的静态专家分配（Static Assignment），没有根据输入序列运行时的专家激活状态进行感知，导致 CPU 算力和 GPU 缓存无法得到协同释放。

7.  **要解决什么问题**：解决本地异构算力环境中的三大问题：（1）静态专家分配导致的严重 CPU-GPU 负载失衡；（2）传统专家预取法在面对未知生成路径时的超低预测准确率；（3）有限 GPU 显存内专家的低 Cache 命中率<sup>33</sup>。

8.  **核心贡献**：提出了 DALI 框架。全方位重构了异构 MoE 的调度、预取与 Cache 替换算法，开辟了“残差引导专家预测”的全新研究方向<sup>33</sup>。

9.  **核心策略与机制**：

    - **Scheduler / Router 层**：将输入 Token 对 CPU 或 GPU 的专家分配建模为一个标准的 0-1 整数规划问题（以最小化整批生成延迟为目标），并开发了运行时 Greedy 算法，根据 CPU 核心数（通过 OMP_NUM_THREADS 控制）和显存剩余容量进行极速近似求解，将超过激活阈值的“高 workload 专家”保留于 GPU，其余并行的分派至多线程 CPU 运行<sup>33</sup>。

    - **KV & Expert Manager 层**：设计了**基于残差层级（Residual-Based Prefetching）的专家预取机制**。利用 Transformer 中**残差连接（Residual Stream）蕴含的丰富语义连续性特征**，在输入刚刚流经第 ![image15]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image15.png) 层注意力层时，计算其隐藏状态，提前在 CPU 端执行轻量级的第 ![image13]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image13.png) 层专家激活门（Gating Linear Projection）的快速运算，从而以接近 100% 的准确率实现异构专家的超前拉取（Prefetch）<sup>33</sup>。

    - **Storage / Data Plane 层**：引入 Workload-aware Cache Replacement 算法，利用专家被激活的时间局部相关性（Temporal Correlation），动态将最近被高频唤醒、且预估在后继生成中将保持高热度的专家 Lock 在 GPU<sup>33</sup>。

10. **硬件与系统假设**：标准个人电脑 / 工作站、1 ![image4]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image4.png) 消费级 GPU（如 RTX 4090）<sup>26</sup>、系统多核 Host CPU、系统本地 DDR 内存。

11. **结果收益和评估方式**：在 Mixtral-8x7B 和 DBRX 等主流 MoE 模型上，DALI 相比于 HuggingFace 官方加载、DeepSpeed-Inference、AdapMoE 等 SOTA 框架，在 prefill 阶段和 decode 阶段均取得了显著的端到端生成加速。

12. **异构协同视角核心贡献**：通过引入残差引导门控预测，彻底攻克了“MoE 卸载因 I/O 时间长于计算时间而导致预取失效”的工业界历史宿疾。

13. **对三类技术趋势的对应关系**：

- 方向一：专家预测（Expert Prediction）机制，通过 Residual Stream 实现超前门控推算<sup>33</sup>；

- 方向三：异构分配的 0-1 整数规划贪心求解器（Greedy Assignment Solver）<sup>33</sup>。

14. **对小算力平台等硬件部署的启发**：对单卡小型推理机的软硬件协同具有极其直接的工程借鉴意义：不需要更改模型结构，直接利用运行时算子拦截、多线程 CPU 并发加上残差特征提前截获，即可盘活整台一体机的硬件空闲资源。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。该研究由中科院自动化所完成，完全贴合国产自研生态。Greedy 调度器和残差预取逻辑非常适合以 PyTorch Custom C++ Extension 的形式植入到 vLLM-Ascend 后端。

16. **局限、风险和不可直接照搬之处**：在极短 prefill 序列下，由于算力强度极低，频繁进行 0-1 规划求解和残差门控预测本身的 CPU 线程抢占开销可能会显著削弱其实际加速比。

17. **代码/开源链接**：[<u>Zeyu Zhu DALI GitHub Asset</u>](https://github.com/happypmn)  
    \[cite: 55\]

18. **可靠性标注**：高置信<sup>33</sup>。

#### 论文九：ZipMoE: Efficient On-Device MoE Serving via Lossless Compression and Cache-Affinity Scheduling

1.  **论文名称**：ZipMoE: Efficient On-Device MoE Serving via Lossless Compression and Cache-Affinity Scheduling<sup>35</sup>

2.  **机构**：南京大学 (NJU, 机器学习与数据挖掘国家重点实验室)<sup>35</sup>

3.  **会议/来源**：ICML 2026<sup>35</sup>

4.  **发表/预印本时间**：2026 年 1 月<sup>35</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：正式发表学术会议论文<sup>35</sup>

6.  **研究背景需求**：在资源极其受限的边缘终端或 SoC 级小算力平台（如智能机器人上的 Jetson 核心）上运行 MoE，显存容量常呈断崖式紧缺。由于安全、对齐（Alignment）或防御对抗攻击的需求，企业严禁使用会扭曲模型原有概率输出的有损低比特量化（如 W4A4）。因此，学术界急需一种能够在保持原本 BF16 无损精度的前提下实现极速推理的异构方案。

7.  **要解决什么问题**：在统一内存架构（Unified Memory Architecture, UMA）平台（如 NVIDIA Jetson）上，CPU 和 GPU 共享同样的物理总线与内存，使得传统的“外挂卸载”方案彻底失效。此外，从 SSD 读取专家的 I/O 带宽远远落后于算力需求，导致推理过程出现大面积的 “I/O 停滞”<sup>36</sup>。

8.  **核心贡献**：提出了 ZipMoE。这是首个将信息论中的**位域无损分解（Bit-Field Separation）与多核 CPU 并行解压**引入 UMA 本地异构计算的 lossless MoE 推理加速系统，在保持 100% 精度的前提下，实现了数量级上的时延与吞吐优化<sup>36</sup>。

9.  **核心策略与机制**：

    - **Storage / Data Plane 层**：ZipMoE 剖析了 BF16 格式在信息论层面的高熵与低熵分布<sup>36</sup>。BF16 包含 1 位符号、8 位指数和 7 位尾数<sup>36</sup>。经统计，**指数位（Exponent chunks, E-chunks）呈现极高的规律性和低熵属性**（冗余度极大），而符号和尾数位（SM-chunks）接近随机分布（高熵）<sup>36</sup>。在离线状态下，对专家权重进行位域剥离。将易于压缩的 E-chunks 利用多核 CPU、通过极速无损压缩算法（如 LZ4HC 或 ZSTD）进行极高压缩比的归档并放置于慢速 SSD<sup>36</sup>；而 SM-chunks 则进行简单的字节对齐表示后直接流式读取<sup>36</sup>。在运行时，利用多核 CPU 的富余算力并行执行 E-chunks 的解压缩，彻底将 I/O 搬运时间隐藏于计算流水线中<sup>36</sup>。

    - **Kernel 层**：GPU 侧编写了高并发、高内存吞吐的向量化 CUDA 恢复 Kernel，通过矢量化合并加载指令（Memory Coalesced），在 GPU 寄存器级别将解压后的 E-chunks 与直接读取的 SM-chunks 重新拼装为 BF16 计算张量，最大化榨干显存带宽<sup>36</sup>。

    - **Scheduler 调度层**：建立了一种基于动态规划的动态内存预算划分算法，确定在不同的压缩状态下各专家权重的常驻比率<sup>36</sup>。

10. **硬件与系统假设**：NVIDIA Jetson AGX Orin（支持统一内存架构 UMA，CPU 侧 12 核，共享 LPDDR5 显存）<sup>36</sup>、本地高速 NVMe SSD。

11. **结果收益和评估方式**：在 Qwen1.5-MoE-A2.7B、DeepSeek-V2-Lite（全 BF16 精度，不含任何有损量化）等大模型上进行实机测试<sup>57</sup>。ZipMoE 相比于 SOTA 移动端和桌面端 offloading 系统（如 Fiddler、DeepSpeed），在单机端到端推理中**降低了高达 72.77% 的生成延迟**<sup>35</sup>；同时将服务吞吐量提升了 **6.76 倍**<sup>35</sup>。

12. **异构协同视角核心贡献**：跳出了传统“量化必定降本但也降质”的误区，精细地解剖了数据结构在 CPU 解压与 GPU 吞吐层面的差异化分工，把“SSD I/O 密集型”瓶颈转化为了“CPU 多核算力密集型”优势。

13. **对三类技术趋势的对应关系**：

- 方向一：异构协同的 lossless 数据位域级多线程并行解压<sup>36</sup>；

- 方向二：模型状态对象化下的 SSD / Host RAM 极致无损压缩分层回流<sup>35</sup>。

14. **对小算力平台等硬件部署的启发**：本地工业一体机、具身智能边缘控制器（例如服务机器人主机）等设备一般显存微小但 SSD 带宽和 CPU 多核性能极强，采用无损位域压缩能完美保证高精度安全任务（如医疗、特种控制）的流畅运行。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。昇腾 + 鲲鹏作为典型的高性能异构平台，鲲鹏 CPU 拥有业内领先的 64-128 核心。使用多核鲲鹏执行 LZ4/ZSTD 异步高并发解压，配合昇腾 NPU 执行快速合并 Kernel，能极大释放这套国产化硬件栈的剩余潜力。

16. **局限、风险和不可直接照搬之处**：该系统目前最契合的是 UMA（统一内存架构）硬件。在带有独立显存（Discrete HBM/GDDR）的传统独显系统上，依然存在跨 PCIe 总线进行 SM-chunks 拷贝的物理限制，需要针对性微调其缓存分配预算。

17. **代码/开源链接**：[<u>npnothard/ZipMoE-ICML26</u>](https://github.com/npnothard/ZipMoE-ICML26)  
    \[cite: 38, 57\]

18. **可靠性标注**：高置信（录用于顶会 ICML 2026）<sup>35</sup>。

### 方向 D：Prefill/Decode 或 Encode/Prefill/Decode 阶段拆分与异构放置

#### 论文十：TriInfer: Hybrid EPD Disaggregation for Efficient Multimodal Large Language Model Inference

1.  **论文名称**：TriInfer: Hybrid EPD Disaggregation for Efficient Multimodal Large Language Model Inference<sup>10</sup>

2.  **机构**：清华大学、潞晨科技 (Colossal-AI 团队)<sup>10</sup>

3.  **会议/来源**：MLSys 2026<sup>10</sup>

4.  **发表/预印本时间**：2026 年 3 月（正式发表）<sup>10</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：正式发表学术论文<sup>10</sup>

6.  **研究背景需求**：多模态大语言模型（MLLM，如 Qwen-VL、CogVLM）在智能边缘平台、塔式服务器上使用广泛。这类模型包含庞大的视觉编码器（如 Vision Transformer, ViT）<sup>11</sup>，单张图片就会转化为数千个高维 visual tokens<sup>11</sup>。传统的端到端推理系统（如 vLLM、SGLang）直接复用了文本 LLM 的设计，将图像处理（Encode）与文本生成（Prefill & Decode）打包在一个进程内同步、串行运行<sup>11</sup>，造成了极其严重的显存碎片和异构单元闲置。

7.  **要解决什么问题**：攻克 MLLM 推理面临的两大资源失配问题：（1）不同阶段极其异构的资源冲突——视觉编码（Encode）阶段在算力上极度饥饿（ViT 的密集注意力算子），LLM 首字（Prefill）阶段是极致的计算密集型，而 LLM 逐字生成（Decode）则是严重的显存带宽限制<sup>11</sup>；（2）传统单一 disaggregation（解耦）策略在面对高抖动的在线流量和复杂 SLO 要求时呈现出的硬性性能缺陷。

8.  **核心贡献**：提出了 TriInfer。这是学术界首个倡导并实现 **Hybrid Encode-Prefill-Decode (EPD) Disaggregation** 的多模态异构服务框架<sup>10</sup>。系统自适应地将 MLLM 的三个独立算力阶段调度、分配在不同的物理节点或异构算力单元上，实现了计算气泡的近零化<sup>10</sup>。

9.  **核心策略与机制**：

    - **Hardware Runtime 层**：引入了全新的“双流并发（Dual-stream Parallelism）”机制。在同一个异构单元内，TriInfer 开启两个并发的底层 CUDA Streams<sup>11</sup>。一个 Stream 专门负责高算力的 Vision Encode 任务，另一个 Stream 负责极度 memory-bound 的 Decode Attention，两者通过自适应的时间片轮转在硬件底层完成算力互补 overlapping<sup>11</sup>。

    - **Scheduler / Router 层**：打破以“请求（Request）”为单位的连续调度，调度器将请求切碎为 Encode 任务块、Prefill 任务块和 Decode 任务块，在整个多节点异构集群间建立多向自适应分派队列<sup>11</sup>。

    - **Hybrid EPD Disaggregation Profiler 层**：根据当前的请求到达率（QPS）、序列长度和目标 SLO 边界，在线对三种异构解耦部署形态进行秒级的秒级快速重播搜索<sup>11</sup>：

      - **E+P+D**（三阶段完全物理隔离节点）<sup>11</sup>；

      - **EP+D**（将 Encode 和 Prefill 放在高 FLOPs 机器，Decode 放在高显存带宽机器，减少了一次大体积图片向量的跨网传输）<sup>11</sup>；

      - **ED+P**（适合有高频突发流量的文本 prefill 场景）<sup>11</sup>。

10. **硬件与系统假设**：多张异构 NVIDIA GPU（例如由单机 4 ![image4]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image4.png) RTX 4090 或多节点 H100 组成的本地混合工作站群）<sup>10</sup>、配备高速网络互联（PCIe P2P / RoCE / RDMA）<sup>11</sup>。

11. **结果收益和评估方式**：在真实的多模态 Workloads（如 VQA 视觉问答、文档理解）下，TriInfer 相比于目前主流的统一大底盘系统（如 vLLM、SGLang），**提升了高达 3.7 倍的整体在线服务吞吐量（Goodput）**，同时在 90% 的严苛 SLO 分位线上保障了极佳的延迟一致性<sup>10</sup>。

12. **异构协同视角核心贡献**：通过将多模态推理精细剥离为 Encode、Prefill、Decode 三个底层子路径，并建立动态在线重组调度，彻底解决了长图像 Token 对自然语言推理所造成的异构带宽失配瓶颈。

13. **对三类技术趋势的对应关系**：

- 方向一：多模态生成流水中，图像/视频编解码、后处理与预计算和 LLM 文本生成的异构阶段拆分<sup>10</sup>；

- 方向三：阶段化解耦后的多重 What-if 在线性能重放与规格自适应反推决策<sup>11</sup>。

14. **对小算力平台等硬件部署的启发**：对于配备了多种不同加速卡（如 1 张高Flops独立显卡跑 ViT/Prefill + 4 张低显存显卡跑 Decode）的本地多模态塔式一体机，TriInfer 的 EPD 自适应混布算法提供了一条低成本整合异构硬件的必由之路。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。国内多模态本地化应用（如档案智能化处理、工业视觉检测一体机）正是华为昇腾的关键落地场景。通过在昇腾 CANN 层和 MindIE 调度层植入 Encode 阶段与 Prefill/Decode 的双流并发机制，能直接把异构处理器的空闲空腔极大地弥合，具备重大的国产化工程部署价值。

16. **局限、风险和不可直接照搬之处**：系统频繁在 E+P+D、EP+D 等架构间切换需要热迁移（Live Migration）一部分权重和动态路由。如果网络通信带宽较低（如仅有普通的千兆以太网口），跨阶段的 KV 转移损耗会瞬间吞噬所有的协同计算红利。

17. **代码/开源链接**：[<u>dongxianzhe/triinfer (Source codes released shortly)</u>](https://github.com/dongxianzhe/triinfer)  
    \[cite: 10\]

18. **可靠性标注**：高置信（顶会 MLSys 2026 Oral 录用，清华团队作品）<sup>10</sup>。

#### 论文十一：FlexInfer: Flexible LLM Inference with CPU Computations

1.  **论文名称**：FlexInfer: Flexible LLM Inference with CPU Computations<sup>39</sup>

2.  **机构**：佐治亚理工学院 (Georgia Institute of Technology) 等<sup>39</sup>

3.  **会议/来源**：MLSys 2025<sup>39</sup>

4.  **发表/预印本时间**：2025 年 2 月（正式发表）<sup>39</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：正式发表学术论文<sup>39</sup>

6.  **研究背景需求**：在单卡或边缘小算力平台上部署大参数量（如 70B）模型时，GPU 显存往往甚至无法完整容纳模型权重，必须采用 offloading 机制，但固定、死板的数据搬移往往极大地削弱了系统的总吞吐量。

7.  **要解决什么问题**：针对单 GPU、单 CPU 混合的、受内存严厉挤压的边缘服务器，如何在 prefill 和 decode 两个表现出截然不同计算与内存特征的阶段，自适应选择最具性价比的算力划分机制<sup>39</sup>。

8.  **核心贡献**：设计了 FlexInfer 协同推理框架。提出了三个开箱即用的底层执行 Policy：CPU-only 执行、GPU offloading 执行、以及 CPU-GPU 静态 Partition 执行，并建立了一个算子级的预测器以自动决策最优路径<sup>39</sup>。

9.  **核心策略与机制**：

    - **Scheduler / Router 层**：FlexInfer 内置了“性能估算器（Performance Estimator）”<sup>39</sup>。其输入包括用户指定的 Batch Size、Input Prompt Length、和 Output Length，估算器根据离线采集的主板 PCIe 实际带宽和 CPU 算力数据，在线判定 prefill 和 decode 阶段应该分别调用哪种 Policy<sup>39</sup>。

10. **硬件与系统假设**：单张消费级显卡（如 RTX 3090 / 4090）挂载到支持 CPU-DDR 内存扩展的主板上。

11. **结果收益和评估方式**：在多尺度 LLaMA 评估中，FlexInfer 相比于 SOTA 的 CPU 卸载大盘 FlexGen，在两种典型的受限服务器配置下，分别**降低了 75% 和 76% 的端到端推理时延**<sup>39</sup>。

12. **异构协同视角核心贡献**：证明了“异构协同没有包治百病的统一算法”，首创在 prefill 和 decode 两阶段分别自适应实施不同卸载比例的系统思想。

13. **对三类技术趋势的对应关系**：

- 方向三：异构协同收益判定，通过 Estimator 预估 prefill 与 decode 的延迟损耗分水岭<sup>39</sup>。

14. **对小算力平台等硬件部署的启发**：在工作站配置中，可以利用 FlexInfer 的算子级判定库，精准跳过对短序列在 CPU 上的低效计算。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。Estimator 估算模型基于代数方程和 Roofline，极易迁移至昇腾一体机，用以调度鲲鹏 CPU 与 310P 之间的子路径。

16. **局限、风险和不可直接照搬之处**：

- 静态 Partition 执行 Policy 在模型多轮会话发生 context 突增时会失效，估算器需重新采集耗时画像。

17. **代码/开源链接**：[<u>FlexInfer in MLSys Artifact Repository</u>](https://openreview.net/forum?id=sFNRNTduKO)  
    \[cite: 39\]

18. **可靠性标注**：高置信<sup>39</sup>。

### 方向 E：Agent / workflow-aware serving 与工具等待期间 KV 生命周期管理

#### 论文十二：TokenDance: Collective KV Cache Sharing for Scale-out Multi-Agent Serving

1.  **论文名称**：TokenDance: Collective KV Cache Sharing for Scale-out Multi-Agent Serving<sup>13</sup>

2.  **机构**：浙江大学、阿里巴巴<sup>13</sup>

3.  **会议/来源**：arXiv / 预印本<sup>13</sup>

4.  **发表/预印本时间**：2026 年 4 月<sup>13</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：学术预印本<sup>13</sup>

6.  **研究背景需求**：在复杂的 Agent 推理（如智能编码代理、大型社交模拟仿真、Agent 协作决策）中，多个 Agent 通常在同步的“轮次（Rounds）”中协同工作<sup>13</sup>。框架通过 All-Gather 模式组织输入：每个 Agent 生产一个本地输出，中央调度器将所有 Agent 的增量输出打包汇总，再无差别地发回给所有 Agent 用于下一轮推理<sup>13</sup>。这导致所有 Agent 的 Prompt 中都充斥着极度冗余、相互交叉的共享数据块，传统的 Prefix Cache 由于无法处理由于“私有历史”位置不同带来的偏置（Offset），导致这些冗余完全无法被复用，引发严重的内存 OOM。

7.  **要解决什么问题**：解决在多智能体协同（All-Gather 模式）下，由于重复计算和多副本存储导致的 GPU 显存物理空间暴涨与 prefill 重复计算的时间雪崩<sup>13</sup>。

8.  **核心贡献**：提出了 TokenDance 系统。首次突破了传统“基于位置连续的前缀缓存”的底层红线，开创了“轮次级集体 KV Cache 共享（Collective KV Sharing）”机制，使 memory 占用降维到仅与 Agent 的“增量特征”相关<sup>13</sup>。

9.  **核心策略与机制**：

    - **Position-Independent Caching (位置无关缓存，PIC) / KV Manager**：TokenDance 解除了必须从 ![image23]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image23.png) 偏置连续对齐的传统规则。设计了零拷贝的位置无关查找，允许将共享的 KV 块复用到任意的 Prompt 偏置（Offsets）处，消除重复预计算<sup>13</sup>。

    - **Collective Sharing Protocol (集体共享协议) / Router**：不是以单个请求为视角进行调度，而是接管整个 Agent 协同轮次<sup>13</sup>。多核 CPU 内存中仅维护一份全局唯一的、高度对齐的共享 Block，利用 CPU 快速分发指针（Pointer Passing），在 GPU 内只执行一次 Prefill 计算即可让所有 concurrent agents 瞬时共享读取<sup>13</sup>。

    - **增量微差存储与压缩 (Delta Cache Compression)**：只对各 Agent 在上一轮自主产生的私有 Output 差异进行独立追加存储，将多副本物理冗余压缩。

10. **硬件与系统假设**：主流 NVIDIA GPU（如 H100、A10G）<sup>24</sup>、需要高度异构的主机 CPU 与 GPU 之间的 PCIe 互联，支持 Unified Host-Device page pool。

11. **结果收益和评估方式**：在两个业内主流的大型多 Agent 社交仿真框架（GenerativeAgents 和 AgentSociety）上进行全场景压测<sup>13</sup>。TokenDance 相比于带有标准 Prefix Caching 功能的 vLLM 基线：**将端到端服务延迟降低了高达 2.3 倍**<sup>13</sup>；同时**将多智能体协同中的物理显存占用压缩了 94% 以上**<sup>13</sup>。

12. **异构协同视角核心贡献**：基于多 Agent 的特定通信模式（All-Gather），通过位置解耦和集体共享重构了 KV Cache 的物理组织方式，证明了“宏观提示词的无序性可通过微观算子的虚拟映射重归有序”。

13. **对三类技术趋势的对应关系**：

- 方向一：多 Agent 工作流中的 Prefix matching、位置无关 Attention 协同重组<sup>13</sup>；

- 方向二：模型状态对象化，将 Agent 私有历史状态（Delta Cache）和公共上下文状态物理隔离管理<sup>13</sup>。

14. **对小算力平台等硬件部署的启发**：在多卡或多用户工作站上运行智能编码 Agent（如 Cursor/Claude Code 协作场景），TokenDance 可在保持同等显存水位的前提下，使并发 Agent 席位提升一个数量级，极具低算力场景落地商业价值。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**中高**。这套逻辑位于调度层（vLLM Scheduler / KV Manager）。昇腾 CANN 已经支持了“Hybrid & Mamba Align Prefix Cache”以改进非标 Prefix 复用<sup>19</sup>，如果结合 TokenDance 的 Collective 轮次机制，能极大地提升多 Agent 场景在昇腾卡上的并发 Goodput。

16. **局限、风险和不可直接照搬之处**：这要求上层的多 Agent 框架必须遵循规范的同步 All-Gather 或大块重叠通信协议（如 OpenClaw、MoltBook）<sup>13</sup>。如果是完全非同步、高散乱度的异步 Agent Swarm 场景，该集体共享机制的触发概率会锐减。

17. **代码/开源链接**：暂无公开公开库（预印本详述见 2026 最新 arXiv<sup>13</sup>）。

18. **可靠性标注**：高置信（浙大与阿里顶尖工程团队联合攻关）<sup>13</sup>。

#### 论文十三：PBKV: Prediction-Based KV-Cache Management

1.  **论文名称**：PBKV: Prediction-Based KV-Cache Management<sup>12</sup>

2.  **机构**：香港中文大学<sup>12</sup>

3.  **会议/来源**：arXiv / 预印本<sup>12</sup>

4.  **发表/预印本时间**：2026 年 5 月<sup>12</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：学术预印本<sup>12</sup>

6.  **研究背景需求**：在大语言模型构建的多 Agent 动态工作流中，Agents 频繁调用、互相 handoff、切换并携带大量共同背景信息<sup>12</sup>。但传统的 Cache 淘汰策略（如 LRU）仅依赖粗糙的时间局部性：认为最久未访问的 Cache 应首先被 Evict，但在 Agent 场景中，某个 Agent 可能因为临时进行耗时的 Tool Call 或是处于 Transition 气泡期间而暂时“冷冻”，随即又被高频唤醒。这导致 LRU 会频繁发生“冷冻期间误杀”，引发庞大的 KV Cache 反复重计算雪崩。

7.  **要解决什么问题**：如何在多智能体工作流（Agentic Workflows）中，设计出能够高度自适应当前工作流 DAG 动态转移图的高精度 KV 状态淘汰及预取策略<sup>12</sup>。

8.  **核心贡献**：提出了 PBKV 框架。通过将工作流历史转移轨迹与 per-request 语义进行多维度信号融合，构建了多步前瞻性 Agent 转移预测器，显著抑制了推理中的冷冻期 Cache 驱逐损耗<sup>12</sup>。

9.  **核心策略与机制**：

    - **Router / KV Manager 层**：PBKV 打破了以往学术界只能支持静态 Agent 转移图（如 KVFlow 中的静态 DAG 拓扑）的缺点，创新引入了 complementary signal fusion (互补信号融合) 技术：在工作流中在线推算“转移概率矩阵”，多步前瞻预测下游最可能被激活的 top-k 个 Agents，将其 KV Cache 强制 Lock（Pin）在本地 GPU 内存中，对预测处于衰落期、短期不再唤醒的 Agent，即便其访问时间极近，也主动 Evict 置换至 Host RAM<sup>12</sup>。

10. **硬件与系统假设**：异构 GPU/NPU 本地工作站，挂载多路高速主板 DDR。

11. **结果收益和评估方式**：在动态 Agent 多轮真实 Workflow 测试中，PBKV 相比于传统 LRU 基线：**将 Agent 运行的端到端平均工作流延迟降低了 1.85 倍**<sup>12</sup>，同时**将关键的 GPU KV Cache 命中率提升了 2.55 倍**<sup>12</sup>。

12. **异构协同视角核心贡献**：证明了“多 Agent 推理协同必须与上层 Workflow 的转移语义建立强绑定”，用控制面的高精度预测置换出高昂的 HBM。

13. **对三类技术趋势的对应关系**：

- 方向一：工作流 Agent Handoff 期间的 Expert/KV 状态 fallback 与 prefetch<sup>12</sup>；

- 方向二：模型状态对象化中的智能预测式主动 Pin / Evict 控制<sup>12</sup>。

14. **对小算力平台等硬件部署的启发**：在塔式服务器内部构建本地 Agent 工程套件（如 LangGraph, CrewAI 部署）时，PBKV 提供了一套不改写硬件、只修改控制层淘汰逻辑的强有力软件优化方案<sup>59</sup>。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。PBKV 的预测网络极为轻量，可在鲲鹏 CPU 侧以极低算力开销运行，而将生成的 Lock 掩码直接发送给 vLLM-Ascend 的底层页调度器执行。

16. **局限、风险和不可直接照搬之处**：当工作流遇到随机的 Human-in-the-loop Breakpoint（人工干预打断）时，人为决策引入的极长气泡会使 PBKV 预测发生偏斜，必须在此类边界设计超时紧急 Fallback 明细规制。

17. **代码/开源链接**：[<u>PBKV references (referenced in 2026 preprints)</u>](https://arxiv.org/abs/2605.06472)  
    \[cite: 12\]

18. **可靠性标注**：中高置信。

### 方向 F：多模态生成 / 视频生成流水中的异构协同

#### 论文十四：FlashDecoder: Real-Time Latent-to-Pixel Streaming Decoder with Transformers

1.  **论文名称**：FlashDecoder: Real-Time Latent-to-Pixel Streaming Decoder with Transformers<sup>16</sup>

2.  **机构**：浦项工科大学 (POSTECH)<sup>16</sup>

3.  **会议/来源**：CVPR 2026<sup>16</sup>

4.  **发表/预印本时间**：2026 年 6 月（正式发表）<sup>16</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：正式发表学术会议论文<sup>16</sup>

6.  **研究背景需求**：在大规模视频生成（如 Sora、Wan2.1）从离线离线转向实时流媒体（Streaming Live-streaming）的过程中<sup>61</sup>，不仅 Denoising（去噪）计算需要加速，将低维潜空间（Latent Space）恢复为高维像素视频（Pixel Space）的 VAE 像素解码器（VAE Decoder）由于严重依赖笨重且缓慢的 3D 卷积（3D Convolutional Decoders），也成为了严重的计算与显存带宽瓶颈<sup>16</sup>。

7.  **要解决什么问题**：如何彻底解决高分辨率（如 1080p）或极长时长视频流在像素解码阶段由于 3D 卷积带来的 OOM 闪崩问题，以及实现具有一致延迟保证的实流式视频解码<sup>16</sup>。

8.  **核心贡献**：提出了 FlashDecoder。这是业内首个专为**流式视频实时重建**设计的、完全基于纯 Transformer 架构的超快、超轻 VAE 像素解码器，在保持无损视频质量重建的前提下，降低了一个数量级的显存占用<sup>16</sup>。

9.  **核心策略与机制**：

    - **Causal Streaming Rolling KV Cache (因果流式 Rolling KV / KV Manager)**：FlashDecoder 解码时摒弃了全序列时空 3D 卷积，改用自回归方式逐帧（Frame-by-frame）处理视频 Latents<sup>16</sup>。当前处理帧在时序上，通过一个**固定大小窗口（Fixed-size Temporal Window）的流式滚动 KV 缓存**仅向过去的历史帧进行双向空间、单向时间注意力交互<sup>16</sup>。

    - **Automatic Cache Eviction (自动驱逐)**：随着时间轴推移，超期帧的 KV 缓存被物理驱逐（Evict），确保在整段视频流运行期间，内存占用和每帧算力恒定，实现恒定延迟（Constant-latency Streaming）<sup>16</sup>。

    - **无掩码双向空间加速 (Mask-free Bidirectional Speedup)**：利用时序上的物理顺序处理，不再需要在注意力矩阵中施加高昂的三角掩码（Attention Masks），使得系统能够调用极度加速的双向计算 Kernel<sup>16</sup>。

10. **硬件与系统假设**：单张 NVIDIA H100 GPU<sup>16</sup>、高速本地 Host 内存段。

11. **结果收益和评估方式**：在 Wan2.1 和 Wan2.2 视频 VAE 潜空间上进行实测<sup>16</sup>。FlashDecoder 取得了极其强悍的物理成绩：在 1080p 分辨率下，相比于 SOTA 的 3D 卷积 VAE 像素解码器，**实现了 3.6 倍至 4.7 倍的重建生成加速，同时节省了高达 11 倍的物理显存**<sup>16</sup>；引入特定的架构感知优化后，端到端加速比被拓宽到了 **12 倍**<sup>62</sup>；在 Wan2.2 的 720p 视频实时视频重建中，以 69.6 FPS 的高帧率流畅运行<sup>41</sup>，彻底攻克了视频流式解码的世界级难题。

12. **异构协同视角核心贡献**：通过将 3D 时空卷积算子颠覆为逐帧自回归注意力交互，结合流式滚动滚动 KV 驱动，开辟了自回归视频生成中的长程状态对象管理新纪元。

13. **对三类技术趋势的对应关系**：

- 方向一：视频自回归生成流水中，图像重建 VAE / 解码后处理算子的全 Transformer 流流式协同设计<sup>16</sup>；

- 方向二：模型状态对象化在图像/视频处理领域的变体：Noise Cache / Rolling KV 弹性驱逐与恢复机制<sup>16</sup>。

14. **对小算力平台等硬件部署的启发**：本地短视频 AI 创作、数字人实时交互一体机是巨大福音：之前这需要 4-8 张 A100 卡支持的超重 VAE 管道，现在仅需 1 张消费级显卡加上 FlashDecoder 架构，即可在本地稳定、无时延抖动地向外泵送高清 1080p 视频流。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。该模型为无掩码纯 Transformer 结构。在昇腾 950 或 910B 上，可直接通过昇腾的 Flash Attention 算子后端库进行无缝封装编译，无任何私有不兼容算子阻碍，极易形成高性价比的国产数字人/流媒体产品方案。

16. **局限、风险和不可直接照搬之处**：固定窗口的滚动机制（Rolling Temporal Window）由于在物理上彻底裁剪了过旧时空片段的依赖<sup>16</sup>，在处理镜头机位瞬间剧烈突变、超长复杂非线性因果情节的视频重建时，可能会带来轻微的画面频闪。

17. **代码/开源链接**：[<u>CVPR 2026 Open Access CVF Repository</u>](https://openaccess.thecvf.com/content/CVPR2026/html/Kang_FlashDecoder_Real-Time_Latent-to-Pixel_Streaming_Decoder_with_Transformers_CVPR_2026_paper.html)  
    \[cite: 16\]

18. **可靠性标注**：极高置信（CVPR 2026 正式录用论文）<sup>16</sup>。

#### 论文十五：Future Forcing: A Training-Free Future-Aware KV Cache Policy for AR Video Generation

1.  **论文名称**：Future Forcing: A Training-Free Future-Aware KV Cache Policy for AR Video Generation<sup>15</sup>

2.  **机构**：上海交通大学<sup>15</sup>

3.  **会议/来源**：arXiv / 预印本<sup>15</sup>

4.  **发表/预印本时间**：2026 年 5 月<sup>15</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：学术预印本<sup>15</sup>

6.  **研究背景需求**：自回归（AR）视频生成中，随着生成长度不断拉长，视频 KV Cache 空间几何级狂飙。前人针对 LLM 设计的 KV 压缩方法主要是挑选相对重要的 token 强行保留，但在视频生成中，未来时刻对当前帧的时空 Query 交互极难预测，粗暴的传统裁剪往往会带来极为致命的误差累积（Error Accumulation）与生成闪烁。

7.  **要解决什么问题**：如何在不进行重新训练的前提下，设计一种能够实现“未来时空 Query 感知”的零抖动、高保真自回归视频 KV 剪裁与合并方案<sup>15</sup>。

8.  **核心贡献**：提出了 Future Forcing，首个为 AR 视频生成量身定做的培训自由（training-free）前瞻性视频 KV 状态压缩架构<sup>15</sup>。

9.  **核心策略与机制**：

    - **KV Manager 层**：Future Forcing 提出了一种创新的“未来查询代理构造”。它从历史生成帧的多维概率分布中在线推算出未来视频帧可能产生的“Query 相似性矩阵”<sup>15</sup>。利用该代理 Query，在仿射子空间（Affine Subspace）中对老旧视频帧中相似度极高、物理冗余的 token 进行无损级“融合（Merging）”，直接将视频生成中的老旧 KV 碎片在寄存器中拼合，从而腾出 HBM<sup>15</sup>。

10. **硬件与系统假设**：主流 NVIDIA GPU（支持 H100、A100）<sup>63</sup> 或高算力 NPU、本地超大 DDR。

11. **结果收益和评估方式**：在主流自回归视频扩散模型测试中，在不损失视频时间连贯性（Temporal Consistency）与 PSNR 图像重建精度的前提下，成功降低了 **70% 以上的视频 KV 物理存储占用**，彻底解除了生成一分钟高清视频必须依赖高端显存的桎梏。

12. **异构协同视角核心贡献**：证明了“视频自回归生成中的状态具有特殊的仿射几何特征”，可用极低算力代价在 CPU/GPU 内存中对旧状态执行就地无损融合。

13. **对三类技术趋势的对应关系**：

- 方向二：模型状态对象化下的视频 Noise Cache 与 3D 状态对象的无损压缩与合并<sup>15</sup>。

14. **对小算力工作站的启发**：使本地塔式工作站具有流式、超长自回归高清视频生成的物理运行可能。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**中**。该机制依赖大量的多维几何仿射矩阵数学计算，需要定制特定的高效昇腾底层算子。

16. **局限、风险和不可直接照搬之处**：当视频遭遇极度剧烈的超快速转场（如剪辑镜头快速切分）时，历史生成的概率统计会彻底崩塌，导致未来 Query 代理预测失准，进而引入可见的画面杂色点。

17. **代码/开源链接**：[<u>Future Forcing Project metadata on arXiv</u>](https://arxiv.org/abs/2605.30083)  
    \[cite: 15\]

18. **可靠性标注**：中高置信（上海交大顶尖多模态研究团队出品）<sup>15</sup>。

### 方向 G：Trace / Benchmark / Profiler / Simulator / Cost Model / Energy Model

#### 论文十六：LLMServingSim 2.0: A Unified Simulator for Heterogeneous and Disaggregated LLM Serving Infrastructure

1.  **论文名称**：LLMServingSim 2.0: A Unified Simulator for Heterogeneous and Disaggregated LLM Serving Infrastructure<sup>42</sup>

2.  **机构**：韩国科学技术院 (KAIST)<sup>17</sup>

3.  **会议/来源**：ISPASS 2026 / IEEE Computer Architecture Letters (CAL) 2025<sup>42</sup>

4.  **发表/预印本时间**：2026 年 2 月（CAL 版本 2025）<sup>17</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：正式发表学术会议论文<sup>42</sup>

6.  **研究背景需求**：当今 LLM 本地推理基础设施极其混乱，GPU/NPU、AMX-CPU、CXL 共享池、PIM（存内计算）及各级 PCIe、NVLink 通道混杂在一起<sup>18</sup>。在不经实机物理组装的前提下，研发团队面临着数以万计的“What-if”架构设计迷茫：增加 CXL 能带多少收益？GPU-SSD 直通是否正收益？CPU 控制面到底配置多少核最省电、最划算？

7.  **要解决什么问题**：如何建立高精度、全栈式、面向运行时交互（Runtime-driven）的异构 LLM 推理全系统周期级（Cycle-level）仿真模型<sup>17</sup>。

8.  **核心贡献**：开发了 LLMServingSim 2.0 模拟器<sup>17</sup>。这是目前系统结构界首个将**前端推理服务调度决策**与**后端超细节网络、存储硬件状态**深层咬合在同一个闭环运行时（Runtime Loop）中的异构联合仿真系统，成功实现了对复杂分层系统的无盲区精确刻画<sup>17</sup>。

9.  **核心策略与机制**：

    - **Execution Runtime Loop (联合闭环运行时) / Simulator**：将基于 Python 的 continuous batching 推理调度前端（高拟真还原 vLLM 的物理调度器状态）与基于 C++ 编写的 ASTRA-Sim 分析网络后端、Chakra 算子依赖追踪器（Traces）深度咬合在一起<sup>42</sup>。所有的 Offloading 延迟、Paging 切换、CXL NUMA 内存冲突都会在运行时瞬间反馈给调度器，动态改变下一时序批次的决策<sup>17</sup>。

    - **Profile-based Operator Modeling (基于画像的算子建模)**：仅需在单张物理显卡上执行一轮轻量级、一小时内的全算子运行时 Trace 画像扫描，即可提取算子级时延与功耗数据，并由模拟器将其 roofline 缩放到任意未来异构加速卡上，甚至支持导入第三方 PIM 仿真文件<sup>18</sup>。

    - **多物理属性耦合仿真**：完美集成了 Memory Capacity 仿真模型、P2P / NVLink Interconnect 路由时延模型，以及细粒度的能源消耗与动态热功耗（Power / Energy Model）<sup>17</sup>。

10. **硬件与系统假设**：支持仿真包含任意 NVIDIA H100、A100、异构 NPU 在内的加速器阵列，以及 CXL、DRAM、PIM、PCIe 通道构成的 disaggregated 存储层。

11. **结果收益和评估方式**：将模拟器的仿真输出与真实物理机房里的真实分布式硬件进行了严格对照验证<sup>18</sup>。LLMServingSim 2.0 在吞吐量、首字延迟（TTFT）、TPOT、内存水位、能耗曲线等所有核心指标上的**平均仿真误差均低于 0.95%**<sup>17</sup>；更关键的是，即便针对超大规模系统的全 Workload 跑数仿真，其计算时间也仅需 **10 分钟左右**<sup>17</sup>，极具工业实用价值。

12. **异构协同视角核心贡献**：通过构建高保真仿真环境，打破了软件开发与底层硬件研发的物理隔阂，提供了异构推理系统全栈软硬协同设计（HW/SW Co-design）的底层分析底盘。

13. **对三类技术趋势的对应关系**：

- 方向三：目标硬件性能预测、收益边界与规格反推，支持 What-if 资源扰动分析<sup>17</sup>。

14. **对小算力平台等硬件部署的启发**：一体机设计团队完全可以通过在仿真器里进行大范围的 sweeps，直接确定鲲鹏 CPU、DRAM 内存及 SSD 通道的物理配置。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**高**。KAIST 团队开源了 LLMServingSim 2.0 的所有 Python 与 C++ 源码<sup>18</sup>。华为在昇腾 CANN 8.5/9.0 的大系统设计中，完全可以通过导入昇腾的 OP profile 算子矩阵文件，定制出专属的“昇腾+鲲鹏”一体机性能预测与规格反推沙盒。

16. **局限、风险和不可直接照搬之处**：

- 模拟器假设网络时延和操作系统的线程切换噪声（OS Jitter）遵循理想状态分布，在现实中可能遭遇不可预测的偶发总线过载，需要适度放宽实际容错边界。

17. **代码/开源链接**：[<u>casys-kaist/LLMServingSim</u>](https://github.com/casys-kaist/LLMServingSim)  
    \[cite: 17, 42, 64\]

18. **可靠性标注**：极高置信（ISPASS 2026/CAL 2025 正式录用论文）<sup>42</sup>。

### 方向 H：工业框架与工程实践：vLLM, SGLang, MindIE 等

#### 工程框架十七：vLLM-Ascend / MindIE 昇腾一体机高性能工程实践

1.  **框架名称**：vLLM-Ascend (搭载华为 MindIE / CANN 8.5 / 9.0 软件栈)<sup>19</sup>

2.  **机构**：华为昇腾社区、昇腾可信计算重点实验室<sup>19</sup>

3.  **会议/来源**：华为昇腾开发者社区工程发布、vLLM 昇腾分支 PR 合并<sup>19</sup>

4.  **发表/预印本时间**：2025 年下半年至 2026 年 6 月（持续迭代）<sup>43</sup>

5.  **正式发表/预印本/工业技术博客/工程框架文档**：工程发布文档与生产级框架底盘<sup>43</sup>

6.  **研究背景需求**：在政务、军工、大型国企等高安全、本地化私有部署环境中，大参数模型必须完全部署在以昇腾 NPU（如 910B/950）与鲲鹏 CPU 为核心的纯国产化一体机或本地工作站上<sup>19</sup>。如何解决复杂算子在昇腾 graph 编译模式下与外部 CPU 动态内存的高频交互瓶颈，是实现国产化平替的物理红线。

7.  **要解决什么问题**：解决大并发、极长序列在昇腾上执行时发生的 aclgraph 图编译内存溢出、专家并行通信堵塞，以及解决在异构 P/D 物理分离或本地卸载中 Mooncake 高速迁移通道的极速接入问题<sup>19</sup>。

8.  **核心贡献**：提供了 vLLM-Ascend 高性能算力底盘<sup>43</sup>。全面重构了昇腾 Model Runner V2，正式打通了“FULL_AND_PIECEWISE”混合编译图捕获模式（彻底移除老旧的 310P 流捕获限制）<sup>19</sup>；原生支持了 EPLB（专家并行负载均衡器）及 Mooncake SSD 多级分级直通，实现了百亿级模型在本地塔式机的低延迟流式输出<sup>19</sup>。

9.  **核心策略与机制**：

    - **Hardware Runtime 层**：打通了全新的 Model Runner V2 搭载 aclgraph 图捕获方案<sup>19</sup>。在启动前对模型进行 ACL 物理内存预估，彻底杜绝了捕获巨量 PagedAttention 图结构时的 OOM 顽疾<sup>19</sup>。

    - **Scheduler / Router 层**：在昇腾上实现了 speculative decoding 的 “D2D NetLoader”，支持将 Draft 模型权重从鲲鹏系统 DDR 极速预取至昇腾底层 NZ 寄存器布局中，实现了无延迟草稿下发<sup>19</sup>。内置了 EPLB 通信负载均衡器，在线追踪专家热度（Experts Hotness Metrics），动态配平跨卡/跨 NUMA 鲲鹏节点的计算权重<sup>19</sup>。

    - **Storage / Data Plane 层**：集成了 Mooncake Connector，支持 NPU 存储元数据的流式 Debug 和直接 SSD 异步存储卸载<sup>19</sup>。

10. **硬件与系统假设**：昇腾 310P / 910B / 950 加速芯片<sup>19</sup>、多核鲲鹏 920 CPU<sup>43</sup>、HDK 25.5.1 / 26.0 硬件驱动与 CANN 8.5.0 / 9.0.0 深度融合栈<sup>19</sup>。

11. **结果收益和评估方式**：在 Qwen2.5-VL、DeepSeek-V4、GLM4.7-Flash 等多类最前沿的巨型国产模型上完成深度验证<sup>19</sup>。通过 FULL_AND_PIECEWISE 编译模式，支持在 A3/Ascend 950 上完成多达 32K 至 64K 的大图捕获（相比老版本提升了一个数量级）<sup>19</sup>；集成 EPLB 通信和 Mooncake 分级后，在超长序列输入中，**相比于老版昇腾分支推理吞吐提升了 35% 以上，且无任何生硬的内存泄露或长时间卡死现象**<sup>19</sup>。

12. **异构协同视角核心贡献**：构建了完全国产化的、从底层图编译（CANN）到上层调度层（vLLM）深度打通的异构计算桥梁，证明了通过细粒度图优化能够大幅收窄软硬件交互损耗。

13. **对三类技术趋势的对应关系**：

- 方向一：投机解码下的 D2D 极速 Draft 预取与 EPLB 动态热度均衡<sup>19</sup>；

- 方向二：基于 Mooncake Connector 的 P/D 物理卸载与动态 SSD 异步回流机制<sup>19</sup>。

14. **对小算力平台等硬件部署的启发**：塔式昇腾一体机（如 1–4 卡小服务器）不再需要复杂的分布式环境配置，直接开启 aclgraph + general CPU offloading 即可拥有极度流畅的高并发表现<sup>19</sup>。

15. **是否可迁移到 Ascend NPU + Kunpeng CPU**：**极高（本身即为原生自研框架）**<sup>19</sup>。

16. **局限、风险和不可直接照搬之处**：

- 昇腾底层对 LoRA 的适配在重构后存在短暂的兼容性冲突<sup>66</sup>；

- 严禁在开启前缀缓存（Prefix Cache）的同时强行开启 chunked prefill，否则会导致严重的计算精度漂移或严重的调度死锁<sup>66</sup>。

17. **代码/开源链接**：[<u>vllm-project/vllm-ascend</u>](https://github.com/vllm-project/vllm-ascend)  
    \[cite: 19\]

18. **可靠性标注**：极高置信（华为官方首推的、与全球 vLLM 社区主线合并的昇腾底座）<sup>19</sup>。

## 4. 每个方向的综合系统级分析

通过对上述 17 篇在 2025–2026 年间公开发表的顶尖学术、系统及工程实践的深度剖析，我们可以清晰地勾勒出在这三大技术方向中，业界到底在做什么、具体怎么做，修改了哪些底层系统层级，以及算力收益究竟是如何产生和流转的。

### 4.1 各技术方向在多层系统软件栈中的渗透图景

异构推理协同的本质是突破传统硬件边界，对系统的重构不再局限于单一的算子级加速，而是深度渗透到从最上层的 **Agent/Workflow 运行时** 到最下层的 **Hardware Runtime / Driver** 的完整软件栈中。我们可以通过下表系统梳理这种多层级修改关系：

<table>
<colgroup>
<col style="width: 25%" />
<col style="width: 25%" />
<col style="width: 25%" />
<col style="width: 25%" />
</colgroup>
<thead>
<tr>
<th><strong>异构计算方向</strong></th>
<th><strong>主要修改的系统层级</strong></th>
<th><strong>核心策略与交互机制</strong></th>
<th><strong>代表性成果</strong></th>
</tr>
<tr>
<th><strong>方向 A：阶段化异构协同</strong></th>
<th><p>1. Scheduler</p>
<p>2. Kernel</p>
<p>3. Hardware Runtime</p></th>
<th>将密集矩阵乘法（GEMM）就地卸载至 CPU AMX 运行，低强度的逐元素算子留存本地，利用非对称流水线隐藏 PCIe 延迟<sup>2</sup>。</th>
<th>LIA<sup>2</sup>, NEO<sup>24</sup>, Dovetail<sup>26</sup></th>
</tr>
<tr>
<th><strong>方向 B：状态分层存储</strong></th>
<th><p>1. KV Manager</p>
<p>2. Storage/Data Plane</p></th>
<th>解耦虚拟和物理内存实现虚拟连续（vAttention），重构物理页优先（Page-first）排布并引入 GPU 辅助异步 I/O 提升传输吞吐<sup>5</sup>。</th>
<th>vAttention<sup>6</sup>, LMCache<sup>30</sup>, HybridGen<sup>9</sup></th>
</tr>
<tr>
<th><strong>方向 C：MoE 专家调度</strong></th>
<th><p>1. Router</p>
<p>2. KV &amp; Expert Manager</p></th>
<th>0-1 整数规划动态贪婪专家分发，截取 Residual Stream 残差隐藏状态超前预测，剥离 BF16 低熵指数位多核 CPU 异步解压<sup>33</sup>。</th>
<th>TriMoE<sup>32</sup>, DALI<sup>33</sup>, ZipMoE<sup>35</sup></th>
</tr>
<tr>
<th><strong>方向 D：EPD 阶段 disaggregation</strong></th>
<th><p>1. Scheduler</p>
<p>2. Router</p></th>
<th>将 Encode/Prefill/Decode 完全切碎，基于 concurrent stream 双流重叠 Vision/Language 计算，动态分析 SLO 重构拓扑<sup>10</sup>。</th>
<th>TriInfer<sup>10</sup>, FlexInfer<sup>39</sup></th>
</tr>
<tr>
<th><strong>方向 E：Agent 工作流感知</strong></th>
<th><p>1. Agent Runtime</p>
<p>2. KV Manager</p></th>
<th>轮次级 Collective Sharing 机制，位置无关缓存（PIC）零拷贝寻址，多步工作流概率转移预测锁定/换出机制<sup>12</sup>。</th>
<th>TokenDance<sup>13</sup>, PBKV<sup>12</sup></th>
</tr>
<tr>
<th><strong>方向 F：多模态与视频流式生成</strong></th>
<th><p>1. KV Manager</p>
<p>2. Kernel</p></th>
<th>逐帧自回归注意力代替 3D 卷积视频 VAE，固定 temporal window 配合 rolling cache 自动弹性淘汰<sup>16</sup>。</th>
<th>FlashDecoder<sup>16</sup>, Future Forcing<sup>15</sup></th>
</tr>
<tr>
<th><strong>方向 G：硬件收益与仿真建模</strong></th>
<th><p>1. Simulator</p>
<p>2. Control Plane</p></th>
<th>动态批处理、分层路由、ASTRA-Sim 拓扑与 Chakra Traces 在线咬合分析，实现低时延多维度 Watt-performance 仿真<sup>42</sup>。</th>
<th>LLMServingSim 2.0<sup>42</sup></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

### 4.2 异构计算收益判定的核心数理边界：为什么 CPU 协同是“双刃剑”

在面向本地小算力平台的系统设计中，“CPU 什么时候该参与计算，什么时候必须退化为纯存储管理”是异构协同系统设计的核心命题。

#### 4.2.1 CPU 协同计算的正收益边界（Mathematical Decisive Matrix）

我们可以将 CPU 是否参与计算的决策，抽象为一个多目标的时延判定不等式。设 ![image6]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image6.png) 为某一特定计算模块（如 MoE 专家权重、Attention 算子）在 GPU 显存受限、必须发生 PCIe 换入换出时的执行时延<sup>33</sup>；设 ![image9]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image9.png) 为将计算直接卸载至 CPU 运行、或是由 CPU 提前计算的异构协同执行时延<sup>4</sup>。则：

![image12]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image12.png)

![image3]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image3.png)

其中：

- ![image5]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image5.png) 为该模块权重参数跨 PCIe 拷贝至 GPU 的传输时延<sup>33</sup>；

- ![image7]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image7.png) 和 ![image14]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image14.png) 分别为模块在 GPU 和 CPU 本地计算单元上的物理执行时间<sup>3</sup>；

- ![image8]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image8.png) 为 CPU 协同计算完成后，将计算所得的 Logits 或被 Top-K 选择后的极小激活张量回传至 GPU 的时延<sup>4</sup>；

- ![image11]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image11.png) 为 CPU 调度、操作系统上下文切换、格式转换以及同步锁带来的控制面系统税（System Tax）<sup>1</sup>。

##### 判定结论一：高算术强度且数据就地驻留，CPU AMX 协同呈现强正收益

若计算模块参数体积庞大（![image1]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image1.png) 极大，如 MoE 专家或大模型 Target 投机验证层），且该部分权重由于显存紧缺已驻留在 CPU 内存中<sup>26</sup>，此时跨 PCIe 搬运参数的时间 ![image5]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image5.png) 极其高昂（通常为 20ms–50ms）<sup>53</sup>。如果 CPU 配备了 AMX 等硬件密集乘法单元<sup>2</sup>，使得 ![image14]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image14.png) 收窄在 10ms–25ms 以内，且由于仅需回传极小的 Logits（![image8]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image8.png) 趋近于零）<sup>4</sup>，最终必然呈现 ![image10]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image10.png) 的显著正收益，CPU 就地计算直接消除了 PCIe 吞吐红线<sup>2</sup>。

##### 判定结论二：层相似度大，CPU-GPU 时序解耦重叠呈现强正收益

若相邻层相似度极高，CPU 可以在 GPU 尚在运行第 ![image15]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image15.png) 层前向推理的物理气泡内，超前计算第 ![image13]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image13.png) 层的 Attention Logits（ALP 机制）<sup>4</sup>。这种将时序硬性依赖彻底解耦、用计算时间换取 PCIe 总线静默时间的方式，获得了近乎 2 倍的流水线加速比<sup>4</sup>。

#### 4.2.2 CPU 协同计算的反噬机制：为什么会导致负收益

在以下三种场景中，硬性引入 CPU 参与计算会带来致命的延迟和功耗反噬：

##### 1. 低算术强度、高带宽敏感型任务（如 Decode 阶段 Attention 计算）

Decode 阶段是极致的显存带宽敏感型（Memory-bound）。CPU 内存物理带宽（DDR5 约 80GB/s–120GB/s）与 GPU HBM（A100/H100 约 2.0TB/s–3.35TB/s）存在 1-2 个数量级的物理鸿沟<sup>5</sup>。如果无差别地将 Decode Attention 卸载至 CPU 计算，CPU 漫长的内存页寻址和低带宽会严重拉长该子批次的延迟，导致多卡同步或 Batching 产生严重的 straggler 效应，吞吐量断崖式暴跌<sup>24</sup>。

##### 2. 跨层数据排布（Layout）转换与通信下发延迟

昇腾或 NVIDIA GPU 在处理张量时通常有其极其硬性的底层私有排布（如昇腾的 NZ 布局、NVIDIA 的 Tensor Core 字节对齐）<sup>19</sup>，而 CPU 计算则通常采用稠密行优先布局。如果 CPU 频繁与 GPU 协同计算，高频的 Layout 转换、CUDA Graph 重捕获（Capture）以及跨层进程同步锁所带来的系统税 ![image11]( Deep Research 反向回顾报告 面向本地小算力一体机与塔式服务器的异构推理协同软硬件协同机制系统性研究报告（2025–2026） _media/media/image11.png) 将以指数级增长，彻底吞噬由于 AMX 计算省下的微弱时间红利<sup>19</sup>。

##### 3. 多 GPU 集群控制面饥饿（Control Plane Starvation）

在多卡推理或 P/D 物理 disaggregation 环境中，CPU 承载着极其高频的网络吞吐、HTTP 请求解析、Tokenization 以及最核心的 NCCL/HCCL 集体通信同步内核下发<sup>1</sup>。如果此时强行抢占 CPU 核心去跑计算密集型的 GEMM，将直接导致 CPU 下发 Collective Communication 的延迟（Delay）剧烈增加，导致 GPU 发生大规模的“空转等待”，整个一体机的硬件利用率（Goodput）会瞬间雪崩<sup>1</sup>。

## 5. 映射至三条“技术及趋势”的 PPT 凝练表述

以下将 2025–2026 年的前沿系统研究高度凝练为可直接用于汇报、PPT 或架构设计的工程化学术级表述：

### 5.1 方向一：阶段化 A+K 异构协同计算

- **高算力多核 CPU 算力“就地化（In-situ）”释放**：彻底废弃以往将 CPU 视为纯存储中转的落后范式。在本地小算力一体机中，将 CPU AMX/SVE 的几十 TFLOPS 稠密计算潜力与 GPU HBM 进行非对称流水线剪枝，把中频专家和深层 Logits 计算就地锚定于 CPU，实现显存容量上限的“零硬件成本”突破<sup>2</sup>。

- **残差引导的超前自回归预测**：打破“被动触发投机验证”的物理限制，通过截取低层隐藏状态的残差语义连续特征，提前在 CPU 侧启动后续多层 MoE 专家门控或 Attention 概率估算，彻底将 PCIe 数据搬运隐藏于关键路径之后，使本地低端显卡能流畅拖动百亿级大模型<sup>4</sup>。

### 5.2 方向二：模型状态对象化与分层回流

- **解耦地址空间以捍卫连续算子红利**：通过底层 VMM API 构建“物理按需分页、虚拟绝对连续”的下一代内存状态机制，彻底消除 PagedAttention 机制对底层极速计算算子（如 FlashAttention-3）的物理隔离，使得小算力终端无缝享受最前沿的高端计算加速<sup>5</sup>。

- **流式滚动滚动 KV 缓存与无损信息剥离**：针对视频扩散模型（DiT）和长序列 Agent，用固定 temporal window rolling KV 强制约束物理水位，结合信息论中的指数/尾数位域分离技术，用 Host CPU 的高效多线程解压隐藏 NVMe SSD 的物理带宽短板，保障本地化流式生成的高帧率、无抖动重建<sup>16</sup>。

### 5.3 方向三：目标硬件性能预测与规格反推

- **高精度、双流咬合周期模拟沙盒**：依托 LLMServingSim 2.0 等高保真仿真平台，将 continuous batching 控制策略与真实的物理互联拓扑、NUMA 带宽损耗进行深度耦合，实现低于 1% 的多维度指标预测误差，在一体机方案设计初期以秒级速度反向推导最经济、最高 Goodput 的 CPU 鲲鹏核数与内存配置<sup>17</sup>。

## 6. 对 Ascend NPU + Kunpeng CPU 小算力一体机的技术布局建议

针对当前国内由“昇腾 NPU（如 310P / 910B / 950） + 鲲鹏 CPU（如 920）”主导的本地小算力一体机、微型工作站和塔式服务器，结合 2025–2026 周期内的最前沿系统研究成果，提出以下三步走落地布局：

### 6.1 近期可做的软件/框架原型（半年内工程转化落地）

#### 1. LMCache-Ascend 多层流式分级 KV 共享底盘

- **工程动作**：基于当前 LMCache-Ascend 正在迭代的单层/多层 shape 自适应适配分支<sup>20</sup>，深度集成 **Mooncake SSD 嵌入式流客户端**<sup>19</sup>。

- **实现逻辑**：重构 vLLM-Ascend 的底层 Scheduler<sup>19</sup>。根据鲲鹏主机的实际 DDR 实时水位和 CPU 负载状况，在背景守护线程中执行非阻塞式的 prefetch() 和 evict()。将非热点的历史多轮 Agent 会话 KV Cache 动态序列化为明文 Page 块，通过 HComm 通道直接倾注于鲲鹏 DDR 和本地 NVMe SSD 中，彻底解除多并发 RAG 一体机的 OOM 限制<sup>19</sup>。

#### 2. 鲲鹏多核高并发无损位域解压插件（仿 ZipMoE 机制

> <sup>56</sup>）

- **工程动作**：利用鲲鹏 920 多核（通常配备 64 至 128 个 ARMv8 物理核心）的富余算力资源。

- **实现逻辑**：在一体机启动前，对百亿级国产 MoE 大模型（如 Qwen2.5-MoE、DeepSeek-V2-Lite）的专家参数进行指数（E-chunks）与尾数（SM-chunks）位域剥离<sup>36</sup>。将指数位使用高并行比的 ZSTD 在鲲鹏多线程上异步解压，尾数位通过 PCIe-P2P 零拷贝直通映射至显存中<sup>36</sup>，在昇腾 NPU 侧通过内存合并（Coalesced）的高速向量化算子在底层寄存器完成 BF16 张量重构，实现 100% 精度无损的超低成本边缘 MoE 加速<sup>36</sup>。

#### 3. 多模态混合 EPD（Encode-Prefill-Decode）异步双流运行时（仿 TriInfer 机制

> <sup>10</sup>）

- **工程动作**：针对国内主推的政务问答、档案图像理解一体机，重构 vLLM-Ascend 的多模态 Runner。

- **实现逻辑**：在昇腾 950 / 910B 上开辟两个并行的硬件 Streams（Encode Stream 和 Language Stream）<sup>11</sup>。将视觉 ViT 编码算子与 LLM 解码算子时间片交错（Overlap）执行，彻底弥合因图像 visual tokens 暴涨导致的首字延迟气泡<sup>11</sup>。

### 6.2 需要硬件接口支持的能力（中期软硬联调攻关）

#### 1. 昇腾 CANN 层级虚拟内存弹性映射（Virtual Memory Mapping）API

- **攻关诉求**：要求华为 CANN 团队放开并完善类似 CUDA VMM 的底层 API（如类似 cuMemCreate、cuMemMap 的昇腾原语）。

- **技术依据**：这是实现类似 vAttention 机制、保证新算子零修改直接运行的核心前提<sup>5</sup>。通过在虚拟地址空间中预留 1M 的连续地址段，动态以 2MB/4MB 物理巨页为粒度进行底层 NPU 地址映射，彻底解决 PagedAttention 下非连续 Attention Kernel 算子开发极其困难的工程宿疾<sup>5</sup>。

#### 2. NPU-SSD 极速 Peer-to-Peer 零拷贝直通（NPU Direct Storage, NDS）

- **攻关诉求**：进一步优化 CANN 9.0 的 HIXL / HComm 直通传输通道<sup>20</sup>，打通不经过鲲鹏系统 DDR 内存中转的 NVMe SSD 数据的直通总线。

- **技术依据**：保障多级分级分发时，SSD 内存储的超大视频/多模态 KV Cache 能够以低于 10ms 的物理极限延迟直接复苏至 NPU 显存<sup>19</sup>。

### 6.3 下一代硬件应反推的物理规格（长期硬件代际定义）

基于 2025–2026 前沿研究对硬件性能边界的探索，下一代鲲鹏 CPU 及昇腾卡在小算力一体机场景下的指标规格应做如下反推：

| **硬件模块** | **下一代一体机规格反推建议（2026–2027）** | **规格制订的系统科学依据（支撑前沿论文）** |
|----|----|----|
| **鲲鹏 CPU 算力** | 集成类似 AMX 的密集矩阵加速硬件（Tile 结构），单核密集矩阵吞吐达 **30+ TFLOPS** | 使得 CPU 能够主动承载 30% 左右的中低频专家/前几层 Attention 计算，规避传输总线瓶颈<sup>2</sup>。 |
| **鲲鹏 CPU 核心配额** | 单个 NPU 槽位必须配足至少 **32 个物理核心**，且具备独立的超线程抢占防御机制 | 防止控制面由于频繁的 Agent 转移计算或高频 NPU Graph 重建发生 CPU 过载，引起 HCCL 同步阻塞<sup>1</sup>。 |
| **系统内存互联** | 全面支持 **CXL 3.0 / CMM-D** 缓存一致性协议，内存总带宽达 **400GB/s 以上** | CXL 分层内存扩展中，保障多机、跨 CXL 共享 KV 页面在 LMCache 下能够维持接近本地 DDR 的高 Goodput<sup>7</sup>。 |
| **本地 I/O 带宽** | 一体机主板标配 **PCIe Gen6 接口**，直连的高速 NVMe SSD 连续读取速度达 **28GB/s** | 保障位域解压和流式滚动滚动 KV 机制在 1080p 视频实时生成中不产生任何 I/O stalls 抖动<sup>36</sup>。 |

## 7. 空白点与研究机会

纵观 2025–2026 年公发表与预印本的顶级系统论文，在面向本地小算力平台的异构协同推理领域，仍存在以下亟待学术界和工业界攻克的空白点，这也是下一阶段取得突破的核心切入点：

### 7.1 极端动态多用户并发下的异构协同收益判定混沌

- **现有研究局限**：目前的异构协同收益判定（如 DALI<sup>33</sup>、NEO<sup>24</sup>）大多基于确定性的、单请求或恒定 QPS 流量假设。

- **研究机会**：在本地一体机真实多用户混合使用场景中，请求到达时间（Poisson Distribution）、Prompt 长度、图像与文本的交替频次呈高度混沌分布。开发出能在 1ms 内动态对千级并发流进行极细粒度 CPU/NPU/CXL 实时自适应博弈调度的强弹性轻量级调度算法，是当前的一大研究空白。

### 7.2 共享分层存储（DRAM/CXL/SSD）中的全密态 KV Cache 隐私保护

- **现有研究局限**：2025–2026 年的 KV Offloading 框架（如 SGLang HiCache<sup>8</sup>、vLLM-Ascend<sup>19</sup>）默认数据是以明文形式存放在共享内存、CXL 内存池或本地 SSD 中。

- **研究机会**：本地一体机极度强调私密安全性（如金融、政务和企业私域知识）。如何在明文 KV 分层换入换出中，在不引入可抵消加速红利的严重解密开销（Decryption Tax）的前提下，实现全链路硬件安全可信执行环境（TEE）级的高速 KV 分层流转。

### 7.3 面向大模型群（Model Swarms）的异构共享与合并调度

- **现有研究局限**：目前的协同推理系统通常只运行单个大型 Model 实例。

- **研究机会**：未来的本地一体机需要同时运行由十几个不同参数、不同任务导向的、异构的多 Agent 组成的 Model Swarm（包含代码 Agent、翻译 Agent、视觉 MLLM）。这些异构模型之间的参数共享（跨模型的同一基础骨架的权重复用）与 KV 层的物理合并（Cross-model Multi-task Cache Pooling），在当前系统的底层物理资源映射上，尚无系统级论文给出完美的解答。

## 8. 链接与开源项目清单

为了便于工程团队进一步核验、追踪并复现本报告所述的前沿协同技术，以下整理了 2025–2026 周期内活跃维护的关键开源基础设施、算力仿真平台及核心学术论文的官方代码仓库：

- **LLMServingSim 2.0 系统级仿真沙盒**

  - **简介**：由 KAIST 团队开发的 Cycle 级异构/分disaggregatedserving服务模拟底盘，完美融合了 ASTRA-Sim 网络与 Chakra 算子依赖 trace，支持 CXL 扩展内存及多级 offloading What-if 评估<sup>42</sup>。

  - **代码仓库**：[<u>https://github.com/casys-kaist/LLMServingSim</u>](https://github.com/casys-kaist/LLMServingSim)  
    \[cite: 17, 42, 64\]

- **ZipMoE 无损边缘 MoE 加速引擎**

  - **简介**：南京大学机器学习与数据挖掘国家重点实验室主导开发的无损位域分离解压系统，专门针对边缘统一内存 UMA 设备执行 lossless MoE 高性能部署<sup>35</sup>。

  - **代码仓库**：[<u>https://github.com/npnothard/ZipMoE-ICML26</u>](https://github.com/npnothard/ZipMoE-ICML26)  
    \[cite: 38, 57\]

- **LMCache 独立大语言模型 KV 分级存储中心**

  - **简介**：打通 vLLM 与 SGLang 共享的多层页式 KV 缓存管理器，已全面支持本地 SSD 直通、Redis、Valkey、Mooncake 等后端<sup>30</sup>。

  - **代码仓库**：[<u>https://github.com/lmcache/lmcache</u>](https://github.com/lmcache/lmcache)  
    \[cite: 30\]

- **vLLM-Ascend 昇腾国产化高性能推理底座**

  - **简介**：华为昇腾官方主导、与全球 vLLM 主线社区合并的高性能推理分支，内置大规模 graph 捕获、 speculative decoding D2D、EPLB 专家并行负载均衡器<sup>19</sup>。

  - **代码仓库**：[<u>https://github.com/vllm-project/vllm-ascend</u>](https://github.com/vllm-project/vllm-ascend)  
    \[cite: 19\]

- **TriInfer 混合 EPD 多模态解耦服务系统**

  - **简介**：清华大学与潞晨科技联合推出的 MLLM EPD 三阶段解耦与 dual-stream 重叠部署系统，能极大提升本地多模态塔式机的推理吞吐量<sup>10</sup>。

  - **代码仓库**：[<u>https://github.com/dongxianzhe/triinfer</u>](https://github.com/dongxianzhe/triinfer)  
    \[cite: 10\]

- **ISCA-2025-LIA AMX 与 CXL 联合加速架构**

  - **简介**：ISCA 2025 官方录用成果，首次揭示了基于 Sapphire Rapids 与 Granite Rapids AMX 指令集执行就地 GEMM 协同的编译层实现<sup>2</sup>。

  - **代码仓库**：[<u>https://github.com/ece-fast-lab/ISCA-2025-LIA</u>](https://github.com/ece-fast-lab/ISCA-2025-LIA)  
    \[cite: 44\]

#### 引用的著作

1.  Characterizing CPU-Induced Slowdowns in Multi-GPU LLM Inference - arXiv, [<u>https://arxiv.org/html/2603.22774v1</u>](https://arxiv.org/html/2603.22774v1)

2.  LIA: Cost-efficient LLM Inference Acceleration with Intel Advanced Matrix Extensions and CXL - Google DeepMind, [<u>https://deepmind.google/research/publications/81986/</u>](https://deepmind.google/research/publications/81986/)

3.  TriMoE: Augmenting GPU with AMX-Enabled CPU and DIMM-NDP for High-Throughput MoE Inference via Offloading - arXiv, [<u>https://arxiv.org/html/2603.01058v1</u>](https://arxiv.org/html/2603.01058v1)

4.  HybridGen: Efficient LLM Generative Inference via CPU-GPU Hybrid Computing - arXiv, [<u>https://arxiv.org/html/2604.18529v1</u>](https://arxiv.org/html/2604.18529v1)

5.  vAttention: Dynamic Memory Management for Serving LLMs without PagedAttention - arXiv, [<u>https://arxiv.org/html/2405.04437v3</u>](https://arxiv.org/html/2405.04437v3)

6.  \[2405.04437\] vAttention: Dynamic Memory Management for Serving LLMs without PagedAttention - arXiv, [<u>https://arxiv.org/abs/2405.04437</u>](https://arxiv.org/abs/2405.04437)

7.  Optimizing KV Cache Offloading to CMM-D in a CXL® Switch-based Memory Pool - Samsung, [<u>https://download.semiconductor.samsung.com/resources/white-paper/Optimizing_KV_Cache_Offloading_to_CMM-D_in_a_CXL_Switch-based_Memory_Pool.pdf</u>](https://download.semiconductor.samsung.com/resources/white-paper/Optimizing_KV_Cache_Offloading_to_CMM-D_in_a_CXL_Switch-based_Memory_Pool.pdf)

8.  SGLang HiCache: Fast Hierarchical KV Caching with Your Favorite Storage Backends, [<u>https://www.lmsys.org/blog/2025-09-10-sglang-hicache/</u>](https://www.lmsys.org/blog/2025-09-10-sglang-hicache/)

9.  \[2604.18529\] HybridGen: Efficient LLM Generative Inference via CPU-GPU Hybrid Computing - arXiv, [<u>https://arxiv.org/abs/2604.18529</u>](https://arxiv.org/abs/2604.18529)

10. TriInfer: Hybrid EPD Disaggregation for Efficient Multimodal Large Language Model Inference - MLSys 2026, [<u>https://mlsys.org/virtual/2026/oral/3756</u>](https://mlsys.org/virtual/2026/oral/3756)

11. TriInfer: Hybrid Disaggregated Scheduling for Multimodal LLM Serving - MLSys 2026 – Oral Presentation, [<u>https://mlsys.org/media/mlsys-2026/Slides/3756.pdf</u>](https://mlsys.org/media/mlsys-2026/Slides/3756.pdf)

12. Efficient Serving for Dynamic Agent Workflows with Prediction-based KV-Cache Management - arXiv, [<u>https://arxiv.org/html/2605.06472v1</u>](https://arxiv.org/html/2605.06472v1)

13. TokenDance: Scaling Multi-Agent LLM Serving via Collective KV Cache Sharing - arXiv, [<u>https://arxiv.org/html/2604.03143v1</u>](https://arxiv.org/html/2604.03143v1)

14. Quant VideoGen: Auto-Regressive Long Video Generation via 2-Bit KV-Cache Quantization, [<u>https://arxiv.org/html/2602.02958v4</u>](https://arxiv.org/html/2602.02958v4)

15. Future-aware Training-free KV Cache Policy for Autoregressive Video Generation - arXiv, [<u>https://arxiv.org/html/2605.30083v1</u>](https://arxiv.org/html/2605.30083v1)

16. CVPR 2026 Open Access Repository, [<u>https://openaccess.thecvf.com/content/CVPR2026/html/Kang_FlashDecoder_Real-Time_Latent-to-Pixel_Streaming_Decoder_with_Transformers_CVPR_2026_paper.html</u>](https://openaccess.thecvf.com/content/CVPR2026/html/Kang_FlashDecoder_Real-Time_Latent-to-Pixel_Streaming_Decoder_with_Transformers_CVPR_2026_paper.html)

17. \[2602.23036\] LLMServingSim 2.0: A Unified Simulator for Heterogeneous and Disaggregated LLM Serving Infrastructure - arXiv, [<u>https://arxiv.org/abs/2602.23036</u>](https://arxiv.org/abs/2602.23036)

18. LLMServingSim 2.0: A Unified Simulator for Heterogeneous and Disaggregated LLM Serving Infrastructure \*These authors contributed equally to this work. - arXiv, [<u>https://arxiv.org/html/2602.23036v1</u>](https://arxiv.org/html/2602.23036v1)

19. Releases · vllm-project/vllm-ascend - GitHub, [<u>https://github.com/vllm-project/vllm-ascend/releases</u>](https://github.com/vllm-project/vllm-ascend/releases)

20. \[Roadmap\] LMCache-Ascend Roadmap for 2026 Q1 · Issue \#126 - GitHub, [<u>https://github.com/LMCache/LMCache-Ascend/issues/126</u>](https://github.com/LMCache/LMCache-Ascend/issues/126)

21. Release Notes — vllm-ascend, [<u>https://docs.vllm.ai/projects/ascend/en/v0.18.0/user_guide/release_notes.html</u>](https://docs.vllm.ai/projects/ascend/en/v0.18.0/user_guide/release_notes.html)

22. LIA: A Single-GPU LLM Inference Acceleration with Cooperative AMX-Enabled CPU-GPU Computation and CXL Offloading \| Semantic Scholar, [<u>https://www.semanticscholar.org/paper/LIA%3A-A-Single-GPU-LLM-Inference-Acceleration-with-Kim-Wang/3408b2987ce5b985e1f419496fd03988ed02535d</u>](https://www.semanticscholar.org/paper/LIA%3A-A-Single-GPU-LLM-Inference-Acceleration-with-Kim-Wang/3408b2987ce5b985e1f419496fd03988ed02535d)

23. LLM System \| Future Architecture and System Technology for Scalable Computing, [<u>https://fast.ece.illinois.edu/projects/4_project/</u>](https://fast.ece.illinois.edu/projects/4_project/)

24. Neo: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference - Minlan Yu, [<u>http://minlanyu.seas.harvard.edu/writeup/mlsys25.pdf</u>](http://minlanyu.seas.harvard.edu/writeup/mlsys25.pdf)

25. 8th MLSys 2025: Santa Clara, CA, USA - DBLP, [<u>https://dblp.org/db/conf/mlsys/mlsys2025</u>](https://dblp.org/db/conf/mlsys/mlsys2025)

26. Dovetail: A CPU/GPU Heterogeneous Speculative Decoding for LLM inference - arXiv, [<u>https://arxiv.org/html/2412.18934v2</u>](https://arxiv.org/html/2412.18934v2)

27. awesome-papers/reading-notes/conference/asplos-2025.md at develop - GitHub, [<u>https://github.com/mental2008/awesome-papers/blob/develop/reading-notes/conference/asplos-2025.md</u>](https://github.com/mental2008/awesome-papers/blob/develop/reading-notes/conference/asplos-2025.md)

28. ‪Mao Lin‬ - ‪Google Scholar‬, [<u>https://scholar.google.com/citations?user=pAESRzAAAAAJ&hl=en</u>](https://scholar.google.com/citations?user=pAESRzAAAAAJ&hl=en)

29. \[PDF\] MoE-Lightning: High-Throughput MoE Inference on Memory-constrained GPUs, [<u>https://www.semanticscholar.org/paper/MoE-Lightning%3A-High-Throughput-MoE-Inference-on-Cao-Liu/07f1fbd2a036d3e75a9fb00b30a413981b7ff17e</u>](https://www.semanticscholar.org/paper/MoE-Lightning%3A-High-Throughput-MoE-Inference-on-Cao-Liu/07f1fbd2a036d3e75a9fb00b30a413981b7ff17e)

30. LMCache: Supercharge Your LLM with the Fastest KV Cache Layer - GitHub, [<u>https://github.com/lmcache/lmcache</u>](https://github.com/lmcache/lmcache)

31. Welcome to Mooncake, [<u>https://kvcache-ai.github.io/Mooncake/</u>](https://kvcache-ai.github.io/Mooncake/)

32. \[2603.01058\] TriMoE: Augmenting GPU with AMX-Enabled CPU and DIMM-NDP for High-Throughput MoE Inference via Offloading - arXiv, [<u>https://arxiv.org/abs/2603.01058</u>](https://arxiv.org/abs/2603.01058)

33. \[2602.03495\] DALI: A Workload-Aware Offloading Framework for Efficient MoE Inference on Local PCs - arXiv, [<u>https://arxiv.org/abs/2602.03495</u>](https://arxiv.org/abs/2602.03495)

34. DALI: A Workload-Aware Offloading Framework for Efficient MoE Inference on Local PCs, [<u>https://www.semanticscholar.org/paper/DALI%3A-A-Workload-Aware-Offloading-Framework-for-MoE-Zhu-Li/7bd2c33d0cf45d92727205173f7a84f765e331e3</u>](https://www.semanticscholar.org/paper/DALI%3A-A-Workload-Aware-Offloading-Framework-for-MoE-Zhu-Li/7bd2c33d0cf45d92727205173f7a84f765e331e3)

35. \[2601.21198\] ZipMoE: Efficient On-Device MoE Serving via Lossless Compression and Cache-Affinity Scheduling - arXiv, [<u>https://arxiv.org/abs/2601.21198</u>](https://arxiv.org/abs/2601.21198)

36. \[论文评述\] ZipMoE: Efficient On-Device MoE Serving via Lossless Compression and Cache-Affinity Scheduling, [<u>https://www.themoonlight.io/zh/review/zipmoe-efficient-on-device-moe-serving-via-lossless-compression-and-cache-affinity-scheduling</u>](https://www.themoonlight.io/zh/review/zipmoe-efficient-on-device-moe-serving-via-lossless-compression-and-cache-affinity-scheduling)

37. Shaowei Wang - OpenReview, [<u>https://openreview.net/profile?id=~Shaowei_Wang4</u>](https://openreview.net/profile?id=~Shaowei_Wang4)

38. ZipMoE: Efficient On-Device MoE Serving via Lossless Compression and Cache-Affinity Scheduling \| OpenReview, [<u>https://openreview.net/forum?id=QUL7jp4QDQ</u>](https://openreview.net/forum?id=QUL7jp4QDQ)

39. FlexInfer: Flexible LLM Inference with CPU Computations - OpenReview, [<u>https://openreview.net/forum?id=sFNRNTduKO</u>](https://openreview.net/forum?id=sFNRNTduKO)

40. FlexInfer: Flexible LLM Inference with CPU Computations - OpenReview, [<u>https://openreview.net/pdf?id=sFNRNTduKO</u>](https://openreview.net/pdf?id=sFNRNTduKO)

41. FlashDecoder: Real-Time Latent-to-Pixel Streaming Decoder with Transformers, [<u>https://cvpr.thecvf.com/virtual/2026/poster/39247</u>](https://cvpr.thecvf.com/virtual/2026/poster/39247)

42. LLMServingSim 2.0: A Unified Simulator for Heterogeneous and Disaggregated LLM Serving Infrastructure - GitHub, [<u>https://github.com/casys-kaist/LLMServingSim</u>](https://github.com/casys-kaist/LLMServingSim)

43. Release Notes — vllm-ascend, [<u>https://docs.vllm.ai/projects/ascend/en/main/user_guide/release_notes.html</u>](https://docs.vllm.ai/projects/ascend/en/main/user_guide/release_notes.html)

44. GitHub - hyungyokim/LIA_AMXGPU: \[ISCA'25\] LIA: A Single-GPU LLM Inference Acceleration with Cooperative AMX-Enabled CPU-GPU Computation and CXL Offloading, [<u>https://github.com/hyungyokim/LIA_AMXGPU</u>](https://github.com/hyungyokim/LIA_AMXGPU)

45. NEO: Saving GPU Memory Crisis with CPU Offloading for Online LLM Inference, [<u>https://proceedings.mlsys.org/paper_files/paper/2025/hash/66a026c0d17040889b50f0dfa650e5e0-Abstract-Conference.html</u>](https://proceedings.mlsys.org/paper_files/paper/2025/hash/66a026c0d17040889b50f0dfa650e5e0-Abstract-Conference.html)

46. vAttention: Dynamic Memory Management for Serving LLMs without PagedAttention - arXiv, [<u>https://arxiv.org/pdf/2405.04437</u>](https://arxiv.org/pdf/2405.04437)

47. Five papers by CSE researchers at ASPLOS 2025 - University of Michigan, [<u>https://cse.engin.umich.edu/stories/five-papers-by-cse-researchers-at-asplos-2025</u>](https://cse.engin.umich.edu/stories/five-papers-by-cse-researchers-at-asplos-2025)

48. HybridGen: Efficient LLM Generative Inference via CPU-GPU Hybrid Computing - arXiv, [<u>https://arxiv.org/pdf/2604.18529</u>](https://arxiv.org/pdf/2604.18529)

49. NeurIPS Poster KVCOMM: Online Cross-context KV-cache Communication for Efficient LLM-based Multi-agent Systems, [<u>https://neurips.cc/virtual/2025/poster/115164</u>](https://neurips.cc/virtual/2025/poster/115164)

50. Using HiCache \| NVIDIA Dynamo Documentation, [<u>https://docs.nvidia.com/dynamo/integrations/kv-cache-integrations/hi-cache</u>](https://docs.nvidia.com/dynamo/integrations/kv-cache-integrations/hi-cache)

51. Local storage - LMCache, [<u>https://docs.lmcache.ai/kv_cache/local_storage.html</u>](https://docs.lmcache.ai/kv_cache/local_storage.html)

52. \[PDF\] ProMoE: Fast MoE-based LLM Serving using Proactive Caching \| Semantic Scholar, [<u>https://www.semanticscholar.org/paper/ProMoE%3A-Fast-MoE-based-LLM-Serving-using-Proactive-Song-Zhong/86f014f66e484f477fe729023ee5d30537a299d6</u>](https://www.semanticscholar.org/paper/ProMoE%3A-Fast-MoE-based-LLM-Serving-using-Proactive-Song-Zhong/86f014f66e484f477fe729023ee5d30537a299d6)

53. Efficient CPU-GPU Collaborative Inference for MoE-based LLMs on Memory-Limited Systems - arXiv, [<u>https://arxiv.org/html/2512.16473v1</u>](https://arxiv.org/html/2512.16473v1)

54. DALI: A Workload-Aware Offloading Framework for Efficient MoE Inference on Local PCs, [<u>https://arxiv.org/html/2602.03495v1</u>](https://arxiv.org/html/2602.03495v1)

55. Minnan Pei: Home, [<u>https://happypmn.github.io/</u>](https://happypmn.github.io/)

56. ZipMoE: Efficient On-Device MoE Serving via Lossless Compression and Cache-Affinity Scheduling - arXiv, [<u>https://arxiv.org/pdf/2601.21198</u>](https://arxiv.org/pdf/2601.21198)

57. npnothard/ZipMoE-ICML26: Artifact for paper - GitHub, [<u>https://github.com/npnothard/ZipMoE-ICML26</u>](https://github.com/npnothard/ZipMoE-ICML26)

58. MLSys Poster FlexInfer: Flexible LLM Inference with CPU Computations, [<u>https://mlsys.org/virtual/2025/poster/3234</u>](https://mlsys.org/virtual/2025/poster/3234)

59. Multi-agent Orchestration Frameworks in 2026: Compared for Enterprise Teams, [<u>https://www.truefoundry.com/blog/multi-agent-orchestration-frameworks</u>](https://www.truefoundry.com/blog/multi-agent-orchestration-frameworks)

60. Multi-Agent AI Systems in 2026: Frameworks, Patterns, Production - Future AGI, [<u>https://futureagi.com/blog/multi-agent-systems-2025/</u>](https://futureagi.com/blog/multi-agent-systems-2025/)

61. Track: Poster Session 1 & Opening Reception - MLSys 2026, [<u>https://mlsys.org/virtual/2026/session/3676</u>](https://mlsys.org/virtual/2026/session/3676)

62. FlashDecoder: Real-Time Latent-to-Pixel Streaming Decoder with Transformers - CVF Open Access, [<u>https://openaccess.thecvf.com/content/CVPR2026/papers/Kang_FlashDecoder_Real-Time_Latent-to-Pixel_Streaming_Decoder_with_Transformers_CVPR_2026_paper.pdf</u>](https://openaccess.thecvf.com/content/CVPR2026/papers/Kang_FlashDecoder_Real-Time_Latent-to-Pixel_Streaming_Decoder_with_Transformers_CVPR_2026_paper.pdf)

63. ISCA 2025: Home - Iscaconf.org, [<u>https://iscaconf.org/isca2025/</u>](https://iscaconf.org/isca2025/)

64. LLMServingSim 2.0: A Unified Simulator for Heterogeneous and Disaggregated LLM Serving Infrastructure \*These authors contributed equally to this work. - arXiv, [<u>https://arxiv.org/html/2602.23036v2</u>](https://arxiv.org/html/2602.23036v2)

65. Ascend Install Guidance - verl documentation - Read the Docs, [<u>https://verl.readthedocs.io/en/latest/ascend_tutorial/get_start/install_guidance.html</u>](https://verl.readthedocs.io/en/latest/ascend_tutorial/get_start/install_guidance.html)

66. Release Notes — vllm-ascend, [<u>https://docs.vllm.ai/projects/ascend/en/v0.11.0/user_guide/release_notes.html</u>](https://docs.vllm.ai/projects/ascend/en/v0.11.0/user_guide/release_notes.html)

67. CPU-Free LLM Inference on GPU Cloud: How NVIDIA BlueField-4 DPUs and SmartNICs Cut the Serving-Stack Tax in 2026 \| Spheron Blog, [<u>https://www.spheron.network/blog/cpu-free-llm-inference-bluefield4-dpu-smartnic-gpu-cloud-2026/</u>](https://www.spheron.network/blog/cpu-free-llm-inference-bluefield4-dpu-smartnic-gpu-cloud-2026/)
