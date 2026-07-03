# GLM-5.2 单卡一体机推理硬件规格反推报告

日期：2026-07-01  
项目语境：A+K / Ascend NPU + Kunpeng CPU 小算力一体机技术路线研究。刘力维（ACS Lab）为本项目语境联系人；本文不重新指定任何组织 owner 或 lead。

## 0. 结论先行

本报告要回答的问题不是“GLM-5.2 官方生产部署需要什么机器”，这个问题已有比较明确的答案：官方和半官方工程材料都把现实生产边界放在 8 卡 FP8 节点，例如 8xH200/H20，满 1M context 更偏向 8xB200。这里要回答的是另一个更窄的问题：**在现有或更低规格小算力硬件上，综合低比特量化、MoE 专家冷热分层、KV/Prefix/Context 分级缓存、CPU/SSD offload、预取和 profile 闭环，GLM-5.2 的最低加载与低速生成边界在哪里，哪些指标不能承诺。**

最终判断如下：

1. **官方 BF16 / FP8 主权重不能被现实单卡 HBM 干净承载。** GLM-5.2 是 744B-A40B 级 MoE 模型。BF16 权重约 1.49 TB，FP8 约 744 GB，加上 scale、KV、runtime workspace 和碎片余量后，单卡 HBM 需要接近 0.9-1.0 TB 才能讨论 FP8 官方权重的干净加载。H100/H200/MI300X/MI325X/当前常见 Ascend 64 GB 级卡都不满足。
2. **单卡小算力可行边界来自低比特权重 + HBM/DRAM/SSD 分层。** INT4 裸权重约 372 GB，真实工程检查点可落到约 395-465 GB。它仍然大于 64-96 GB HBM，因此必须把 HBM 留给 non-expert 核心、少量 hot experts、active KV、workspace 和预取窗口，把 warm/cold 权重、prefix/KV、checkpoint 和 trace 分别下沉到 DRAM/SSD。
3. **本文主目标是向下压榨硬件。** L0 以 `84GB Bailu + 384GB DDR5 + 2TB SSD` 为现有样机锚点，验证极限分层、权重切片、runtime hook、少量 token 生成和 profile；L1a/L1b 分别验证 SSD-offload 极限加载和 DRAM-warm 保守加载；L2 只作为 32K 单用户低速可交互尝试上界。
4. **档位体系统一为 L0 -> L1a -> L1b -> L2。** L0 是容量压榨验证锚点，L1a 是 SSD-offload 极限加载，L1b 是 DRAM-warm 保守加载，L2 是单用户低速可交互尝试；多卡生产只作为边界说明。
5. **1M 长上下文验证和高配单卡上探不再作为本文目标。** 32K 可作为 L2 压力验证上限，128K/1M 仅用于说明容量、状态恢复和 profile 风险边界，不作为主承诺或验收目标。若目标转为 1M 长上下文验证、4TB DRAM、16-32TB NVMe 或 256-512GB 级 HBM，应另立高配单卡或多卡方案报告。
6. **A+K 单卡一体机的合理角色分工是：Ascend NPU 做热计算和热状态，Kunpeng CPU 做调度、metadata、KV/expert warm tier、I/O aggregation 和 profiling/simulation host。** 不应把 Kunpeng 写成主干 FFN/attention 的泛化替代。CPU 做主算只有在低频、稀疏、可批处理、可重叠或有明确 SVE/SME kernel 证据时才可进入实验项。

## 1. 任务定义与默认口径

### 1.1 本次任务

需要产出一份自洽的技术报告，说明：

- GLM-5.2 的模型结构、参数规模、KV cache 和推理热路径如何影响硬件需求。
- 如何借鉴近两年推理系统工作中的 CPU/GPU/NPU 协同、MoE expert offload、KV cache 分层、SSD-backed KV、仿真与 workload 建模方法。
- 在“单卡一体机”约束下，GPU/NPU HBM、CPU、DRAM、SSD、PCIe/CXL/UB/HCCS、功耗散热等硬件组件该如何反推规格。
- 哪些目标可以承诺，哪些目标不能承诺。

### 1.2 工作负载和向下压榨口径

本文采用“向下压榨硬件”的工作负载口径：L0 以 `84GB Bailu + 384GB DDR5 + 2TB SSD` 为现有样机锚点，验证 4K-16K 的加载和少量生成；L1a/L1b 分别验证 SSD-offload 极限加载和 DRAM-warm 保守加载；L2 作为 32K 单用户低速可交互尝试上界。128K/1M 只作为容量和风险边界，不作为本文主承诺。

| 项目 | 默认值 | 说明 |
|---|---:|---|
| 平台优先级 | A+K 国产优先 | Ascend NPU + Kunpeng CPU 为主，NVIDIA/AMD 作参照 |
| 服务目标 | 最低加载与低速生成验证 | 不是对外服务，不承诺高并发 |
| 默认上下文 | L0/L1a 以 4K-8K smoke 为主，L1b 到 16K，L2 尝试 32K | 128K/1M 仅作风险边界 |
| 权重精度 | INT4/NVFP4/W4A8 级实验口径 | 官方 BF16/FP8 只作容量边界 |
| KV 精度 | BF16/FP8 KV 都作为容量和质量验证项 | KV 数值风险需框架验证 |
| 速度目标 | 能加载、能出少量 token、能复现实验路径 | TPOT、32K 体验和长上下文均需 profile 证明 |

### 1.3 单卡的含义

本文里的“单卡”指一体机中只有一张主加速卡或一个主加速模块。不排除该卡内部有多 die、多 HBM stack、片上互联或 vendor-specific fabric，但不使用多张独立加速卡做 tensor parallel / expert parallel。  

这一定义很重要：如果允许 8 张卡，那么问题会变成标准 8 卡 FP8 serving；如果坚持单卡，必须把大部分权重和冷状态移出 HBM。

## 2. 资料与证据表

### 2.1 模型和框架一手来源

| 编号 | 来源 | 本文使用的信息 | 可信度 |
|---|---|---|---|
| R1 | [Z.ai GLM-5 GitHub](https://github.com/zai-org/GLM-5) | GLM-5.2 是 744B-A40B，支持 BF16/FP8 权重，1M context，IndexShare，MTP，Transformers/vLLM/SGLang/KTransformers/Ascend 路线 | A |
| R2 | [Hugging Face GLM-5.2 config.json](https://huggingface.co/zai-org/GLM-5.2/blob/main/config.json) | `glm_moe_dsa`、78 层、6144 hidden、256 routed experts、top-8、1 shared expert、`kv_lora_rank=512`、`qk_rope_head_dim=64`、1M context | A |
| R3 | [vLLM GLM-5.2 recipe](https://recipes.vllm.ai/zai-org/GLM-5.2) | FP8 practical default，8xH200/H20，满 1M context 建议 8xB200，5-token MTP，FP8 KV cache；Blackwell NVFP4 变体约 465 GB checkpoint | A |

### 2.2 本地综述和精读材料

| 编号 | 本地资料 | 作用 |
|---|---|---|
| L1 | `AK 协同/模型推理估计/GLM-5.2 架构与推理资源深度研究报告.md` | GLM-5.2 架构、参数、KV、框架、硬件边界的主输入 |
| L2 | `AK 协同/代表工作原文硬件拓扑映射精读笔记.md` | 代表工作在 GPU/HBM、CPU/DRAM、SSD、PCIe/RDMA、scheduler 上的真实硬件链路 |
| L3 | `AK 协同/Deep Research 反向回顾报告 第三轮可核验版 小算力大模型推理落地与推理仿真系统构建.md` | A+K 路线、状态对象化、KV/expert 分层、仿真输入输出指标 |
| L4 | `AK 协同/同事提供的外部参考文档/GLM推理硬件需求推导_普通FP4_FP8混合量化.docx` | FP4/FP8 混合量化、35% hot expert、8x reuse、1000 tok/s 吞吐型硬件反推口径 |
| L5 | `AK 协同/同事提供的外部参考文档/GLM推理硬件需求推导_极致4_2bit量化.docx` | 4/2bit 极致量化、冷专家 2.6bit、CPU/CXL 冷层、卸载带宽和 HBM 预算 |

### 2.3 原文论文和系统材料

| 方向 | 原文文件或网页 | 借鉴点 |
|---|---|---|
| CPU attention / KV offload | `references/papers/NEO__arxiv-2411.01142.pdf` | CPU 只承接部分 decode attention 与 KV，GPU 仍跑 prefill/linear/hot attention；收益依赖 overlap |
| CPU/GPU hybrid MoE | `references/papers/KTransformers.pdf` | shared/hot experts 在 GPU，routed experts 在 CPU，AMX/AVX/NUMA/异步调度/Expert Deferral |
| 阶段级 CPU/GPU 策略 | `references/papers/FlexInfer.pdf` | prefill/decode 分阶段选择 CPU-only、GPU offload 或 SplitGen，不固定单一路径 |
| MoE hotness / prefetch | `references/papers/DALI__arxiv-2602.03495.pdf` | workload-aware expert assignment、residual prefetch、GPU expert cache |
| MoE expert paging | `references/papers/FluxMoE__arxiv-2604.02715v2.pdf` | expert 不必常驻 HBM，可分页 materialize，HBM 优先给 KV/activation |
| KV disaggregation | `references/papers/Mooncake__arxiv-2407.00079.pdf` | CPU/DRAM/SSD/RDMA 组成 KVCache pool，scheduler 以 KV 分布与 SLO 做决策 |
| KV object API | `references/papers/LMCache__arxiv-2510.09665.pdf` | KV store/retrieve/lookup，多级后端，chunk 化搬运，connector API |
| SSD-backed KV | `references/papers/Tutti__arxiv-2605.03375.pdf` | 不能天真用 SSD；关键是 object I/O、减少 tiny I/O、让 CPU 退出 critical path |
| sparse + SSD KV | `references/papers/SolidAttention-FAST26.pdf` | sparse attention 选中 KV blocks，SSD-aware scheduler 与 prefetch |
| interactive KV tier | `references/papers/Bidaw-FAST26.pdf` | host memory + SSD two-tier KV，ready/preparing queue 和 eviction |
| prefix position reuse | `references/papers/CacheSlide.pdf` | agent prompt 相对顺序保持但绝对位置漂移时的 KV reuse |
| workload / trace | `references/papers/ServeGen-NSDI26.pdf`、`references/papers/BurstGPT__arxiv-2401.17644.pdf` | 负载生成、arrival、prompt/output、conversation reuse |
| 仿真器 | `references/papers/LLMServingSim-2.0__arxiv-2602.23036.pdf`、`references/papers/LLMServingSim-2.0__arxiv-2511.07229.pdf` | heterogeneous devices、multi-tier memory、MoE、prefix、P/D、power 的统一仿真 loop |
| Ascend 工程接口 | `references/web/vLLM-Ascend-KV-CPU-offload-live.html`、`references/web/vLLM-Ascend-UCM-deployment-live.html`、`references/web/vLLM-Ascend-KV-pool-live.html` | CPU KV offload、UCM、Mooncake KV Pool、SSD offload 的 A+K 工程支点 |

注意：FluxMoE 引用应使用 `FluxMoE__arxiv-2604.02715v2.pdf`。旧 `FluxMoE__arxiv-2601.07343.pdf` / arXiv `2601.07343` 在本地精读中已标注为无关论文，不能作为 FluxMoE 证据。

### 2.4 证据如何进入估算

为避免“列了文献但没有说明如何参与计算”，本文采用三层证据口径：

| 估算对象 | 直接计算来源 | 文献是否直接给本文数值 | 文献在本文中的作用 | 本文没有采用的外推 |
|---|---|---|---|---|
| 总参数、active 参数、权重容量 | Z.ai/HF config/vLLM recipe 与 GLM-5.2 结构复算 | 否 | 不参与这些裸容量公式 | 不用任何 offload 论文的模型规模替代 GLM-5.2 |
| KV cache 容量 | GLM-5.2 `kv_lora_rank + qk_rope_head_dim = 576` | 否 | Mooncake/LMCache/Tutti/Bidaw/SolidAttention/CacheSlide 只影响 KV 放置、搬运粒度、复用和 SSD 风险 | 不用 sparse attention 或 prefix reuse 论文直接缩小默认 KV 容量 |
| HBM hot working set | GLM-5.2 non-expert、shared expert、hot routed expert、KV、workspace 拆分 | 部分影响分层策略 | KTransformers/DALI/FluxMoE 支持“HBM 放热专家/共享专家/当前工作集，不放全量专家”的预算方式 | 不直接套用论文 speedup 或 CUDA/AMX 数值到 Ascend/Kunpeng |
| DRAM 容量 | 低比特全量权重 395-465 GB + staging/page cache/runtime 余量 | 否 | KTransformers/DALI/FluxMoE/LMCache/Mooncake/Bidaw 支持 DRAM 作为 expert/KV warm tier | 不把 DRAM 写成逐 token 主算的无限带宽层 |
| SSD 容量与 I/O | checkpoint、cold expert、cold KV、trace 的容量需求 | 否 | Tutti/SolidAttention/Bidaw/CacheSlide 约束 SSD 只能作为 cold tier，且必须 chunk/object/prefetch | 不把 SSD 顺序读峰值当作逐 token active expert 供给能力 |
| CPU 规格 | scheduler、metadata、I/O、warm tier、profile 负载 | 否 | NEO/FlexInfer/KTransformers/DALI 给出 CPU 参与的边界和必须 profile 的指标 | 不声称 Kunpeng 可直接继承 Intel AMX 或 x86 AVX 论文结论 |
| 场景和验证指标 | 4K-16K 加载与生成、32K L2 尝试、128K/1M 风险边界 | 否 | ServeGen/BurstGPT/LLMServingSim2.0 影响 workload 字段、profile 字段和仿真 loop | 不用 trace/仿真论文直接证明硬件已可服务化 |

因此，本文所有 GB/GiB 级容量数字都必须能从 GLM-5.2 的参数、上下文长度或硬件链路带宽反推回来；文献主要决定“这些字节应该放在哪里、何时搬、哪些搬运不能进入关键路径、应该记录哪些瓶颈”。

### 2.5 反向回顾报告技术方向覆盖复核

前文提到的“MoE expert 放置、KV/SSD 分层、负载/仿真指标”只是本次抽样深读时优先检查的三类证据，并不是 `Deep Research 反向回顾报告 第三轮可核验版` 的全部技术方向。按该报告的研究问题地图，至少应覆盖以下主线：

| 技术方向 | 代表工作/系统 | 是否进入本报告硬件估算 | 对 GLM-5.2 单卡反推的影响 | 本报告处理状态 |
|---|---|---|---|---|
| CPU 可卸载计算与异构协同 | NEO、FlexInfer、llm.npu、HeteroInfer | 部分进入 | 影响 CPU 角色、DDR 带宽、PCIe/UB profile、CPU fallback 是否可用 | 已覆盖 NEO/FlexInfer；补充 llm.npu/HeteroInfer 为迁移参考，不直接改 BOM |
| MoE expert 管理 | KTransformers、FineMoE、HybriMoE、DALI、FluxMoE、MoE-APEX | 直接进入 | 决定 HBM hot expert cache、DRAM warm expert、SSD cold expert、expert miss 下界 | 已覆盖 KTransformers/DALI/FluxMoE；补充 FineMoE/MoE-APEX 作为 hotness/adaptive precision 拓展 |
| KV/Prefix/State 分层内存 | Mooncake、LMCache、Bidaw、CacheSlide、SolidAttention、Tutti、ECHO | 直接进入 | 决定 active KV 放 HBM、inactive/prefix KV 放 DRAM、cold KV 放 SSD 的边界 | 已覆盖主要 FAST/LMCache/Mooncake/Tutti；ECHO 作为 sparse KV restore 拓展 |
| 统一 state object runtime | LMCache、FluxMoE、UCM、vLLM connectors、Tutti | 间接进入 | 把 KV/expert/weight/activation 统一为带位置、热度、生命周期和迁移代价的对象 | 原报告已有分散描述；本节明确为独立拓展方向 |
| 硬件流水线与 P/D/E/P/D 拆分 | Mooncake、TensorRT-LLM DS、vLLM NixlConnector、NVIDIA Dynamo/NIXL | 部分进入 | 单卡默认不采用 P/D，但影响多卡生产边界、KV transfer、RDMA/NIXL/UB 建模 | 已在多卡生产边界和验证项体现；补充说明低并发单卡不默认获益 |
| 推理仿真、trace、profiling | ServeGen、BurstGPT、ProfInfer、Chakra、CCL-Bench、LLMServingSim2.0 | 间接进入 | 影响验证指标、trace schema、瓶颈归因、硬件规格敏感性分析 | 已覆盖 ServeGen/BurstGPT/LLMServingSim；补充 ProfInfer/Chakra/CCL-Bench 为 evidence layer |
| Ascend/Kunpeng 迁移路线 | vLLM-Ascend、MindIE、Mooncake、UCM、LMCache-Ascend | 直接进入 A+K 口径 | 决定 P0/P1 工程接口、NPU stream、CPU KV offload、UCM/KV Pool、CANN counter | 已覆盖 vLLM-Ascend/UCM/KV Pool；补充 MindIE/LMCache-Ascend 为工程候选 |
| CXL/remote/tiered memory | ITME、CXL memory、remote KV/remote store | 不进入 L0-L2 默认 BOM，只作未来拓展 | 可作为 warm/capacity tier，但延迟和随机访问风险高 | 已在 PCIe/CXL 节提到；明确为 P2/P3，不作为 HBM 替代 |
| 低比特量化与自适应精度 | NVFP4/INT4/W4A8、MoE-APEX、KV FP8 | 直接进入容量估算 | 决定权重从 744 GB FP8 降到约 395-465 GB 工程低比特口径 | 已进入权重表；质量和 kernel 风险单列 |
| speculative decoding / MTP | GLM-5.2 5-token MTP、speculative decode runtime | 不降低容量下限 | 可能改善吞吐，但会增加 workspace，取决于 acceptance rate | 只作为 workspace/验证项，不用来降低硬件规格 |
| model loading / PPC / checkpoint I/O | FAST 2026 model loading PPC、runtime loader | 间接进入 | 影响冷启动、mmap、page cache、SSD 顺序读和加载峰值 DRAM | 已在 L1a/L1b DRAM/SSD 预算体现，未作为独立速度承诺 |
| 多模态 latent/noise/adapters 分层 | 反向回顾报告的创新机会 | 不进入 GLM-5.2 文本模型默认估算 | 对 VLM/video/agent 扩展有意义 | 不纳入本次 GLM-5.2 BOM，只作为未来 state object 扩展 |

结论：本报告的硬件容量推导仍以 GLM-5.2 权重、active 参数、KV、expert 字节为主；但技术方向不应被压缩成三类。更准确的说法是：**容量数字来自模型结构，规格余量来自低比特量化、expert/KV/state 分层、CPU/NPU 协同、P/D 数据面、CXL/SSD 冷层、profiling/simulation evidence layer 和 Ascend/Kunpeng 工程接口的联合约束。**

## 3. GLM-5.2 模型参数复算

### 3.1 官方和配置字段

从 R1/R2/R3 可确认：

| 字段 | 数值 | 硬件意义 |
|---|---:|---|
| 总参数 | 744B | 决定落盘、DRAM、HBM 总容量门槛 |
| 官方 active 参数 | 约 39B-40B | 决定 decode 单 token 热路径带宽压力 |
| 模型类型 | `glm_moe_dsa` | MoE + DSA/IndexShare，不是普通 dense decoder |
| 层数 | 78 | KV cache 与 layer-wise transfer 成本线性相关 |
| hidden size | 6144 | activation、projection、expert shape 的主维度 |
| attention heads | 64 | 注意力并行和 cache layout 的基础 |
| routed experts | 256/layer | 总权重巨大的根源 |
| experts per token | 8 | active expert 热路径 |
| shared experts | 1 | 每个 token 都要走的 expert 路径 |
| dense 前缀层 | 3 | 前 3 层不是 MoE sparse layer |
| sparse MoE 层 | 75 | expert offload / hotness 管理主要发生处 |
| max context | 1,048,576 tokens | 极限上下文容量目标 |
| `kv_lora_rank` | 512 | MLA cache 主体 |
| `qk_rope_head_dim` | 64 | 每 token cache 中 RoPE 部分 |
| MLA cache 宽度 | 约 576 elems/layer/token | KV cache 反推主公式 |
| MTP | 5 draft tokens | speculative decode 可能提升吞吐，但取决于 acceptance |

### 3.2 总参数复算

当前 Hugging Face `config.json` 同时给出 `head_dim=192`、`qk_head_dim=256` 和 `v_head_dim=256`。本文按更贴近当前配置的 `v_head_dim=256` 复算参数量：

| 组件 | 公式 | 估算参数 |
|---|---:|---:|
| Embedding | `154880 * 6144` | 0.952B |
| LM head | `6144 * 154880`，且 `tie_word_embeddings=false` | 0.952B |
| MLA attention / layer | `H*q_r + q_r*(heads*qk) + H*(kv_r+rope) + kv_r*(heads*(qk_nope+v)) + (heads*v)*H` | 0.165B |
| 78 层 attention | `78 * 0.165B` | 12.87B |
| Dense MLP / layer | `3 * 6144 * 12288` | 0.226B |
| 前 3 层 dense MLP | `3 * 0.226B` | 0.679B |
| Router / sparse layer | `6144 * 256` | 1.57M |
| 75 层 router | `75 * 1.57M` | 0.118B |
| 单个 expert | `3 * 6144 * 2048` | 37.75M |
| 75 层全部 routed experts | `75 * 256 * 37.75M` | 724.78B |
| 75 层 shared expert | `75 * 37.75M` | 2.83B |
| 估算总量 | 上述合计 | 约 743.2B |
| 官方口径 | Z.ai / vLLM | 744B |

这个复算说明 744B 不是抽象宣传数字，而是由“每层 256 个专家 x 75 个 sparse 层”推出来的容量事实。

### 3.3 Active 参数口径

每 token 激活的主要路径为：

```text
active_core
= all_attention
+ first_3_dense_mlp
+ all_routers
+ 75_layers * 8_routed_experts_per_token * single_expert
+ 75_layers * 1_shared_expert * single_expert
```

代入上表数值：

```text
active_core
= 12.87B
+ 0.68B
+ 0.12B
+ 75 * 8 * 37.75M
+ 75 * 1 * 37.75M
= 39.15B
```

如果把 embedding 与 LM head 也完整计入，会变成约 41.05B。但工程上谈 decode 热路径带宽时，通常采用官方的 39B-40B active 口径，因为词表头和 embedding 的访问形态不同于每层 MoE/attention 的循环热路径。

这对硬件规格有直接影响：

- **容量规划看 744B 总权重。**
- **decode 带宽规划看约 39B active 权重，加上 KV、expert miss、workspace。**
- **prefill 规划看 FLOPs、workspace、长序列 attention/indexer 开销。**

## 4. KV cache 与显存公式

### 4.1 不能直接使用传统 KV 公式

传统 head-wise KV cache 公式为：

```text
KV_cache_bytes = B * S * L * 2 * num_kv_heads * head_dim * bytes
```

对 GLM-5.2，如果按传统 head-wise KV 展开估算，会严重放大 KV 显存。沿用本地初版报告中的旧 `head_dim=192` 对比口径，传统 cache 为 `2 * 64 * 192 = 24576` elems/layer/token；如果按当前配置里的 `qk_head_dim=256` 与 `v_head_dim=256` 展开，则可写成 `64 * (256 + 256) = 32768` elems/layer/token。无论采用哪种传统对比口径，都不应作为 GLM-5.2 的主容量公式。公开配置显示 GLM-5.2 更适合使用 MLA 压缩 cache 近似：

```text
MLA_cache_elems_per_token_per_layer
≈ kv_lora_rank + qk_rope_head_dim
= 512 + 64
= 576

GLM52_KV_cache_bytes
≈ B * S * L * 576 * bytes
```

相对于 MLA 口径，传统展开会放大约：

```text
24576 / 576 = 42.7x
32768 / 576 = 56.9x
```

这也是 1M context 从“完全不可讨论”变成“多卡大 HBM 下可讨论”的核心原因。

### 4.2 单请求 KV 容量表

| 场景 | BF16 KV | FP8 KV | 说明 |
|---|---:|---:|---|
| 32K x 1 | 2.74 GiB | 1.37 GiB | 单卡演示默认档 |
| 128K x 1 | 10.97 GiB | 5.48 GiB | 长上下文压力档 |
| 1M x 1 | 87.75 GiB | 43.88 GiB | 极限档，不建议单卡承诺 |

注意这里还没有计入：

- IndexShare / sparse attention index cache。
- paged KV block table。
- prefix/APC metadata。
- runtime workspace。
- speculative decoding / MTP workspace。
- HBM allocator 碎片。
- framework graph capture buffer。

所以硬件规格不能只看这张 KV 表。实践上即使 32K KV 只有几 GiB，单卡仍会被权重与 expert working set 卡住。

## 5. 权重内存与分层预算

### 5.1 权重容量

| 精度 | 裸容量 GB | 裸容量 GiB | 工程口径 | 单卡 HBM 结论 |
|---|---:|---:|---|---|
| BF16 | 1488 GB | 1385.8 GiB | 加 workspace 后接近 1.6-1.8 TB | 现实单卡不可行 |
| FP8/INT8 | 744 GB | 692.9 GiB | 官方 FP8 仓库约 756 GB，运行需 0.85-1.0 TB 级 HBM | 现实单卡不可行 |
| INT4 裸算 | 372 GB | 346.5 GiB | 真实 NVFP4/INT4 可能约 395-465 GB | 不能全放 HBM，但可放 DRAM |

### 5.2 单 token 热路径带宽直觉

以 39B active 参数估算：

| active 权重精度 | 每 token active 权重字节 | 若全从 HBM 读 | 若全从 PCIe Gen5 x16 读 | 若全从 SSD 读 |
|---|---:|---|---|---|
| BF16 | 78 GB | HBM 可承受但容量放不下 | 不可接受 | 不可接受 |
| FP8 | 39 GB | HBM 带宽主导 | PCIe 约 64 GB/s，理论也只有 1-2 tok/s 且未计同步 | 不可接受 |
| INT4 | 19.5 GB | 最有希望 | PCIe 仍是强瓶颈 | 不可作为逐 token 供给路径 |

结论：**SSD 不能处在每 token active 权重读取路径上；PCIe 也不能承接大比例逐 token expert miss。** 低速交互尝试必须让高频 expert 和所有非 expert 核心尽量在 HBM，DRAM/SSD 只服务于 warm/cold 状态，且通过预取窗口隐藏 miss。

### 5.3 HBM 分层预算

以 INT4/W4A8 低比特权重、4K-32K 单用户低速验证为例：

| HBM 项目 | 64 GB HBM | 84 GB Bailu | 96 GB HBM | 192 GB HBM | 256 GB HBM |
|---|---:|---:|---:|---:|---:|
| non-expert 核心、attention、router、shared expert、词表头热部件 | 很紧 | 可勉强规划 | 可勉强规划 | 可放 | 可放 |
| 4K-16K BF16/FP8 KV + metadata | 可放 | 可放 | 可放 | 可放 | 可放 |
| 32K BF16/FP8 KV + metadata | 可放但挤压热层 | 可放但挤压热层 | 可放但挤压热层 | 可放 | 可放 |
| runtime workspace / graph / MTP / fragmentation | 很紧 | 很紧 | 很紧 | 较稳 | 稳 |
| hot routed expert cache | 极少 | 极少 | 很少 | 可做热集 | 可做较大热集 |
| 定位 | L1a/L1b 下沿 | L0 样机锚点 | L1a/L1b 上沿 | L2 起步 | L2 更稳 |

更具体地说，单个 expert 约 37.75M 参数。若按 FP8 存，一个 expert 约 37.75 MB；按 INT4 存，一个 expert 约 18.9 MB。GLM-5.2 共有 `75 * 256 = 19200` 个 routed expert 实例。即使 192 GB HBM 能拿出 80-120 GB 给 hot expert cache，也只能缓存全部 expert 的一小部分。可行性完全依赖 routing locality、hotness 预测、prefetch lead time 和 miss penalty。

为了把“向下压榨”的容量口径算得更清楚，下面给出一个粗略 HBM 预算。假设 non-expert + shared expert 的热部件按 FP8/低比特混合约 18-24 GiB，runtime/workspace/MTP/graph capture 取 16-32 GiB，prefetch buffer 取 8-16 GiB，allocator/碎片保留约 10% HBM。表中剩余空间才是可给 hot routed expert cache 的预算。

| HBM 容量 | 16K FP8 KV 后 hot expert cache | 32K FP8 KV 后 hot expert cache | 128K FP8 KV 后 hot expert cache | 含义 |
|---:|---:|---:|---:|---|
| 64 GB | 约 0-8 GiB | 约 0-6 GiB | 不建议 | L1a/L1b 下沿，只适合加载和少量 token |
| 84 GB | 约 10-20 GiB | 约 8-18 GiB | 不建议 | L0 样机锚点，必须采用 10/30/60 极限分层 |
| 96 GB | 约 20-30 GiB | 约 18-28 GiB | 不建议 | L1a/L1b 上沿，仍不是演示机 |
| 192 GB | 约 100-105 GiB | 约 100-105 GiB | 约 95-101 GiB | L2 起步，可尝试 32K 单用户低速交互 |
| 256 GB | 约 155-165 GiB | 约 155-165 GiB | 约 150-160 GiB | L2 更稳，128K 仅作风险压测 |

hot expert cache 也可以换算成“每层平均能缓存多少个 INT4 expert”。单个 INT4 expert 约 18.9 MB，因此：

| hot expert cache | 可缓存 expert 总数 | 折算每层平均 expert 数 | 折算全 expert layer window |
|---:|---:|---:|---:|
| 64 GiB | 约 3,640 | 约 49/layer | 约 14 层 |
| 96 GiB | 约 5,460 | 约 73/layer | 约 21 层 |
| 120 GiB | 约 6,830 | 约 91/layer | 约 27 层 |
| 160 GiB | 约 9,100 | 约 121/layer | 约 36 层 |
| 302 GiB | 约 17,180 | 约 229/layer | 约 67 层 |

这张表改变了本文的硬件口径：L0/L1a/L1b 的核心任务不是“证明单卡高配能跑长上下文”，而是证明 64-96GB 甚至 84GB HBM 在极限分层下能否加载、生成少量 token 并输出可解释 profile。192-256GB HBM 只作为 L2 向上对照，用来尝试 32K 单用户低速交互。若目标转为 1M 长上下文验证或长上下文演示，则需要另行上探到高配单卡或多卡方案，不属于本文主线。

### 5.4 L0/L1a/L1b 的 DRAM / SSD 边界复核

L1b 写成 `DRAM = 1 TB`，这不是因为 active KV 很大，而是因为它默认采用较保守的加载口径：**全量低比特权重至少能在 DRAM 中 mmap / resident / warm-staging，不把 SSD 放进逐 token 热路径。**

按上面的模型参数复算：

| 项目 | 估算 |
|---|---:|
| 全量 INT4 裸权重 | 372 GB / 346.5 GiB |
| 真实低比特工程检查点 | 约 395-465 GB |
| 全部 routed expert 的 INT4 裸容量 | 约 362.4 GB |
| 非 routed 部分加 shared expert，INT4 裸容量 | 约 9.2 GB |
| 非 routed 部分加 shared expert，FP8 裸容量 | 约 18.4 GB |
| 16K BF16 active KV | 1.37 GiB |
| 32K BF16 active KV | 2.74 GiB |

所以 L1b 的 DRAM 高压来自权重与 staging，而不是 KV：

| DRAM 消耗项 | 保守估计 | 说明 |
|---|---:|---|
| 低比特权重 resident / mmap warm set | 395-465 GB | 避免每 token expert miss 直接打到 SSD |
| quant scale、expert index、loader metadata、runtime 对象 | 50-120 GB | 取决于量化格式和框架实现 |
| HBM 预取 / pinned buffer / copy staging | 50-150 GB | 支撑 DRAM -> HBM 异步搬运 |
| OS page cache、SSD readahead、checkpoint 读写余量 | 100-250 GB | 避免频繁 page fault 和冷启动抖动 |
| inactive KV / prefix / trace / 系统余量 | 20-100 GB | L1 口径下 KV 本身很小，但仍要预留 |
| 合计工程底线 | 约 615-1085 GB | 因此规格表取 1 TB 作为保守最低值 |

也可以定义一个更激进的 **L1a SSD-offload 极限加载口径**：

| 子档 | DRAM | expert 权重 | KV | 结论 |
|---|---:|---|---|---|
| L1a：SSD-offload 极限加载 | 512-768 GB | cold routed experts 允许在 SSD，DRAM 只保留 warm set / page cache | active KV 仍放 HBM，inactive/cold KV 可下 SSD | 可能打通加载和少量 token，但速度和稳定性不可承诺 |
| L1b：DRAM-warm 保守加载 | 1 TB | 低比特全量权重尽量 resident / warm，SSD 主要做冷层和 checkpoint | 4K-16K active KV 放 HBM，历史 KV 可下 SSD | 更适合作为最低加载验证的稳妥口径 |

如果需要解释当前 `84 GB Bailu + 384 GB DDR5 + 2 TB SSD` 还能把容量压到什么程度，可以定义 **L0 现有样机极限分层验证档**。这里统一按 **热 / 温 / 冷 = HBM 10% / DRAM 30% / SSD 60%** 来算。注意：这个比例只针对 `全部 routed experts INT4 裸容量约 362.4 GB`，不是逐 token 的 expert miss 比例。

| 层级 | L0 比例 | routed expert INT4 裸容量 | 还必须叠加的工程项 | 对 950PR Lite 的含义 |
|---|---:|---:|---|---|
| HBM / Bailu 热层 | 10% | 约 36.2 GB | non-routed + shared 约 9.2 GB、32K active KV 1.37-2.74 GiB、workspace / prefetch buffer 约 15-30 GB | 总热层约 63-78 GB，84 GB Bailu 勉强覆盖，但不适合 1M 或大 prefetch buffer |
| DRAM 温层 | 30% | 约 108.7 GB | metadata / expert index 30-60 GB、staging 40-80 GB、page cache 50-120 GB、系统 / KV 余量 20-50 GB | 总温层约 249-419 GB；384 GB 可以作为极限验证，但要求 runtime 开销受控，不能保留全量低比特权重 resident |
| SSD 冷层 | 60% | 约 217.4 GB | 低比特 checkpoint、cold expert、cold KV / prefix、trace / profile、失败恢复余量 | 2 TB 容量够做单量化版本与基础 trace，但不够多版本 checkpoint 和长时间 profile；关键风险是随机 I/O 与 P95/P99 tail latency |

这个 L0 口径可以把 L1b 的 DRAM 需求从 `615-1085 GB，取 1 TB` 压到约 `249-419 GB`，因此能解释 384 GB DDR5 为什么可作为“极限分层验证锚点”。但它比 L1a 还激进：SSD 冷专家一旦频繁进入 token critical path，性能会退回到极慢低速生成，不能称为 L1b “保守加载”。

因此，L0/L1a/L1b **已经考虑 SSD 上的 cold expert / cold KV**，但不应该把 SSD 写成 active expert 或 active KV 的逐 token 供应源。KV 容量本身很小，真正需要 SSD-offload 的主要是冷 expert、冷权重版本、历史 prefix/KV 和 checkpoint。

若目标另行转为 1M 长上下文验证或长上下文演示，DRAM、HBM 和 NVMe 都需要进入高配上探口径；这不属于本文 L0-L2 的主线。

### 5.5 Expert 分层的逐 token 计算边界

MoE offload 文献影响的是 expert 放置策略，但下面的字节数来自 GLM-5.2 自身结构：

```text
single_expert_params
= 3 * hidden_size * moe_intermediate_size
= 3 * 6144 * 2048
= 37.75M params

routed_experts_total
= 75 sparse_layers * 256 experts/layer * 37.75M
= 724.78B params

routed_experts_active_per_token
= 75 sparse_layers * 8 experts/token * 37.75M
= 22.65B params
```

| 项目 | INT4/NVFP4 裸字节 | FP8/INT8 裸字节 | 估算意义 |
|---|---:|---:|---|
| 单个 expert | 18.9 MB | 37.7 MB | expert cache 的最小颗粒 |
| 每层全部 routed experts | 4.83 GB | 9.66 GB | FluxMoE 式 layer window 的上界颗粒 |
| 两层全部 routed experts window | 9.66 GB | 19.33 GB | FluxMoE two-layer sliding residency 的 GLM-5.2 量级 |
| 每层 top-8 active routed experts | 151 MB | 302 MB | 只搬已选 expert 时的单层下界 |
| 75 层 top-8 active routed experts / token | 11.32 GB | 22.65 GB | 每 token routed expert 热路径总量 |
| 75 层 shared expert / token | 1.42 GB | 2.83 GB | 每 token 必走 shared expert |

这解释了为什么 KTransformers/DALI/FluxMoE 可以支撑“expert 不全常驻 HBM”的方向，但不能支撑“SSD 每 token 供给 active expert”的结论。若以 INT4 routed active expert 的 `11.32 GB/token` 为基准，miss 传输下界为：

```text
transfer_time_ms = expert_miss_bytes / effective_bandwidth * 1000
```

| INT4 routed expert miss 比例 | 需要搬运 | PCIe Gen5 x16 有效 40 GB/s 下界 | SSD 冷层 14 GB/s 理想下界 | 结论 |
|---:|---:|---:|---:|---|
| 5% | 0.57 GB/token | 14 ms/token | 40 ms/token | 只有充分预取时可接受 |
| 10% | 1.13 GB/token | 28 ms/token | 81 ms/token | PCIe 已明显吃掉 TPOT 余量 |
| 25% | 2.83 GB/token | 71 ms/token | 202 ms/token | 单用户演示会明显卡顿 |
| 100% | 11.32 GB/token | 283 ms/token | 809 ms/token | 不应作为逐 token 路径 |

上表还没有计入 DMA setup、随机 I/O、量化解包、kernel 同步、CPU control path 和 NPU/GPU compute。因此硬件表中的 192-256 GB HBM，不是为了装下全量 744B 权重，而是为了提高 hot routed expert 命中率，并容纳 non-expert 核心、shared expert、KV、workspace、prefetch buffer 与 runtime 碎片。64-96 GB HBM 的 L1a/L1b 只能验证加载和少量 token，是因为 hot expert cache 太小，而不是 KV cache 算错。

向下压榨硬件还需要反过来设定 miss budget。假设每 token 只允许把一部分时间花在 DRAM/PCIe/SSD 搬运上，则可接受 miss 比例如下：

| 传输预算 | PCIe/DRAM 有效 40 GB/s 可搬运 | 折算 routed expert miss | SSD 冷层 14 GB/s 可搬运 | 折算 routed expert miss | 解释 |
|---:|---:|---:|---:|---:|---|
| 10 ms/token | 0.40 GB | 3.5% | 0.14 GB | 1.2% | 追求明显可交互时，miss 必须非常低 |
| 25 ms/token | 1.00 GB | 8.8% | 0.35 GB | 3.1% | 只适合充分预取后的少量 miss |
| 100 ms/token | 4.00 GB | 35.3% | 1.40 GB | 12.4% | 已接近极低速生成；SSD 仍不能随机触发 |
| 500 ms/token | 20.00 GB | 176.7% | 7.00 GB | 61.8% | 只对应极低速边界，不应写成可交互 |

因此 L0-L2 的关键指标不是“SSD 有多少 GB/s”，而是 **expert miss 中有多少已经被提前搬入 HBM 或至少 DRAM pinned buffer**。如果 miss 到达 token 级 critical path，再高的 SSD 标称顺序读也救不了 TPOT。

## 6. 借鉴方法如何落到硬件组件

本章不是独立的论文综述，而是第 7 章硬件规格和第 8 章 BOM 档位的“建模接口”。本文采用以下规则把文献方法转成硬件估算：

1. **模型裸容量只由 GLM-5.2 参数决定**：权重、active 参数、KV bytes/token、expert bytes/token 不从文献外推。
2. **文献方法改变的是放置、搬运、命中率风险和验证项**：例如 expert 可以分 HBM/DRAM/SSD 三层，但单个 expert 的字节数仍按 GLM-5.2 `hidden_size=6144, moe_intermediate_size=2048` 计算。
3. **只有能移出逐 token 关键路径的方法，才允许降低默认硬件承诺**：SSD cold tier、CPU fallback、sparse KV restore、P/D split 都不能被写成默认性能收益，除非对应 runtime 已经有 profile 证据。
4. **第 8 章每个档位都必须说明其方法假设**：L0 是“现有样机极限分层验证”，L1a 是“SSD-offload 极限加载”，L1b 是“DRAM-warm 保守加载”，L2 是“单用户低速可交互尝试”，多卡生产只作为边界说明。

从第 6 章到第 7/8 章的对应关系如下：

| 文献方法群 | 可参考性级别 | 转成本文估算旋钮 | 落到第 7 章硬件组件 | 落到第 8 章 BOM 档位 |
|---|---|---|---|---|
| 低比特量化、adaptive precision、MoE-APEX | 直接进入容量下界，但不继承质量结论 | BF16/FP8/INT4 权重字节、scale/metadata 工程余量、低比特 kernel 可用性 | HBM 精度支持、DRAM 权重 resident、SSD 多版本 checkpoint | L0-L2 的前提条件；没有低比特 kernel 时最低加载验证不成立 |
| KTransformers、DALI、FluxMoE、FineMoE、HybriMoE | 直接进入 MoE 放置策略，不直接继承 speedup | hot expert cache、DRAM warm expert、SSD cold expert、expert miss budget | HBM 容量、DRAM 带宽、PCIe/DMA、SSD 冷层 | L0/L1a 允许大量 cold expert 在 SSD；L1b/L2 要求 DRAM warm/resident；全部都必须可观测 miss budget |
| Mooncake、LMCache、Bidaw、CacheSlide、SolidAttention、Tutti、ECHO | 直接进入 KV/state 分层策略，不直接缩小默认 KV 公式 | active KV 留 HBM，warm/prefix/history KV 入 DRAM，cold KV 入 SSD，chunk/object 粒度 | HBM KV 预算、DRAM warm tier、SSD IOPS/队列、CPU metadata | L0/L1a/L1b 只承诺小上下文 active KV；L2 默认尝试 32K，128K/1M 只作风险边界 |
| NEO、FlexInfer、llm.npu、HeteroInfer | 进入 CPU/NPU 角色划分和 profile 口径 | CPU 是否只做调度/I/O，还是允许 fallback expert；CPU/DRAM/PCIe overlap | CPU 核数、DDR 带宽、NUMA、PCIe root、profiling 字段 | L0-L1b CPU 只做控制和搬运；L2 可实验低频 fallback，但必须 microbenchmark |
| Tutti、SolidAttention、Bidaw 的 SSD/KV 路线 | 作为风险约束和下一代 direct path 诉求 | SSD 只能做冷层；tiny random I/O、CPU bounce copy、stall 必须度量 | SSD 带宽/IOPS、P2P/direct、queue depth、温控 QoS | L0-L2 都不把 SSD 写成 active expert/KV 供应源；direct path 只作为优化或研究项 |
| Mooncake、TensorRT-LLM DS、vLLM NixlConnector、Dynamo/NIXL | 单卡默认不采用 P/D serving，但 direct/object transfer 思路可作为边界参考 | P/D/KV transfer bytes、RDMA/NIXL/UB、phase-aware routing | PCIe/UB/HCCS/RDMA、CXL/remote tier | 多卡生产方向；不用于证明单卡 L0-L2 可服务化 |
| ServeGen、BurstGPT、ProfInfer、Chakra、CCL-Bench、LLMServingSim2.0 | 不给容量数字，给验证闭环 | trace 字段、arrival/prompt/output、TTFT/TPOT/P99、stall attribution | 所有组件的可观测指标和压测项 | L0-L1b 是否能从“能加载”升级到“低速生成”、L2 是否能从“可承载”升级到“低速可交互”，取决于这些验证结果 |

### 6.1 CPU / NPU / GPU 协同

NEO 的关键启发是：CPU 不是主算替代品，而是在 GPU/HBM 受限时承接一部分 decode attention 和 KV cache，并用 asymmetric pipeline 让 GPU 工作覆盖 CPU 子路径。对 A+K 来说，这映射为：

- NPU 保持 prefill、dense projection、hot attention、hot expert 的主路径。
- Kunpeng CPU 承接 scheduler、metadata、KV warm tier、prefetch planner、trace collector。
- 只有在 microbenchmark 证明 Kunpeng SVE/SME 对某些 expert shape 有足够吞吐时，才让 CPU 跑低频 expert 或 fallback expert。

硬件含义：

- CPU 不只看核数，还要看 DDR 带宽、NUMA、本地 PCIe 拓扑、pinned memory 和异步 copy 能力。
- PCIe/UB/HCCS 的延迟和 DMA setup 要建模，不可只看峰值 GB/s。
- CPU 参与主循环时，必须记录同步栅栏和 host overhead。

### 6.2 MoE expert offload 和 hotness 管理

KTransformers、DALI、FluxMoE 给出三类互补思路：

- KTransformers：shared/hot experts 放 GPU，routed experts 放 CPU 直接计算，依赖 AMX/AVX/NUMA 和异步调度。
- DALI：按 workload 动态分配 CPU/GPU expert，并用 residual 信息预取高负载 experts。
- FluxMoE：expert 不再长期常驻 HBM，而是以 paged/transient resource 的形式在执行前 materialize，HBM 优先留给 KV 和 activation。

对 GLM-5.2 单卡一体机，建议采用组合策略：

1. HBM 常驻 non-expert 核心和 shared expert。
2. HBM 保留 hot routed expert cache。
3. DRAM 在 L1b/L2 口径下保存全量低比特 routed expert；在 L0/L1a 极限口径下只保存 warm expert set 和 page cache。
4. SSD 保存权重文件、cold routed expert、历史 checkpoint、cold KV 和 page cache，但只作为冷层。
5. runtime 持续记录 expert ID、per-layer hit/miss、miss load time、prefetch 命中率。

硬件含义：

- HBM 容量越大，hot expert miss 越少。
- L1b/L2 的 DRAM 应能放下全量低比特权重；L0/L1a 可把 cold expert 留在 SSD，但只能用于极限分层或加载验证。
- DRAM 带宽要足够支撑 warm expert materialization。
- PCIe Gen5 x16 是下限，且需要稳定的 DMA/stream overlap。
- SSD 只能作为冷层，不应承接逐 token expert miss。

### 6.3 KV / Prefix / State 分层

Mooncake、LMCache、Bidaw、SolidAttention、Tutti、CacheSlide 的共同趋势是：KV 不再是普通显存数组，而是带有对象 ID、位置、热度、生命周期、后端位置、传输代价的 state object。

对单卡 GLM-5.2：

- HBM：当前请求 active KV、APC/prefix hot KV、block table、attention workspace。
- DRAM：inactive KV、prefix warm tier、UCM/Mooncake/LMCache-style external KV。
- SSD：历史会话 KV、长 agent workflow 的 cold KV、可重建/可恢复状态。
- CPU：metadata、hash、eviction、prefetch、ready/preparing queue。

Tutti 的反例尤其关键：SSD-backed KV 的瓶颈常常不是账面 SSD 顺序带宽，而是 tiny random I/O、CPU-centric control path、DRAM-HBM bounce copy 和同步导致的加速器 stall。因此单卡一体机即使配置多块 Gen5 SSD，也必须配套：

- KV chunk/object 大粒度搬运。
- SSD queue depth 管理。
- 异步预取和 slack-aware scheduling。
- 尽量减少 CPU bounce copy。
- 监测 HBM stall attribution。

### 6.4 仿真和验证口径

LLMServingSim2.0 和 ServeGen 提醒我们：规格反推不能只算 FLOPs 和容量。报告建议一体机设计阶段必须记录以下指标：

- workload：arrival、prompt length、output length、conversation reuse、agent segment reuse。
- 模型：active experts、expert hotness、KV bytes/token、prefix hit rate。
- 硬件：NPU/GPU kernel timeline、HBM occupancy、DDR traffic、PCIe/UB utilization、SSD IOPS、copy engine utilization。
- 结果：TTFT、TPOT、P50/P95/P99、tokens/s、energy/token、stall attribution。

没有这些 profile，只能给保守规格，不能声称系统已达到可生产部署。

### 6.5 文献方法与硬件表的对应关系

逐篇复核后，本文对文献方法的采用边界如下：

| 文献/系统 | 原文方法要点 | 本文是否用于数值估算 | 落到本文哪一项 | 采用边界 |
|---|---|---|---|---|
| NEO | CPU 承接部分 decode attention 与 CPU-cache，GPU 仍跑 prefill/linear/hot attention，通过 asymmetric pipeline 和 load-aware scheduling 重叠 | 不给容量数值，给角色边界 | CPU 规格、PCIe profile、KV warm tier、验证指标 | 不把 CPU 写成主干 FFN/attention 的普适替代 |
| FlexInfer | prefill/decode 分阶段在 CPU-only、GPU offload、SplitGen 间选择，依据 CPU/GPU throughput、内存带宽和互联 profile | 不直接给硬件档位数值 | 场景复核、L0-L2 必须 profile TTFT/TPOT | 不固定某个策略为 A+K 最优 |
| llm.npu / HeteroInfer | 端侧 NPU/CPU/GPU 异构放置、outlier/fallback path、OOO subgraph | 不直接给服务器 BOM 数值 | A+K 迁移时的 NPU 主算、CPU 特殊路径、动态图/静态图风险 | 移动 SoC/UMA 结论不能直接外推到 Ascend PCIe/UB/HCCS 服务器 |
| KTransformers | shared/hot experts 在 GPU，routed experts 在 CPU DRAM 计算，依赖 AMX/AVX、NUMA、异步调度和 Expert Deferral | 只用于 expert 分层方向，不继承性能倍数 | HBM hot expert cache、DRAM 全量低比特 expert、CPU microbench | Intel AMX/CUDA Graph 结果不能直接迁移 Kunpeng/Ascend |
| FineMoE / HybriMoE | expert map、semantic hints、intra-layer scheduling、score/cache hotness | 用于 hotness trace 需求，不给固定命中率 | expert trace schema、prefetch lead time、next-use probability | 未拿到 GLM-5.2 routing trace 前不降低 HBM 需求 |
| DALI | activated experts 按 workload 动态分给 CPU/GPU，残差预取与 workload-aware cache replacement 提高 GPU expert cache 命中 | 用于 hotness/prefetch 假设，不给固定 hit rate | hot expert cache、expert trace、PCIe miss 风险 | 不假定 GLM-5.2 routing locality 一定足够好 |
| FluxMoE | expert paging、PagedTensor、compressed GPU backend + host DRAM backend，HBM 优先给 KV/activation | 用于 HBM/DRAM 分层结构，字节数仍由 GLM-5.2 expert size 计算 | 5.5 的 two-layer window、HBM expert cache、DRAM warm expert tier | 不假设 Ascend 已有等价 PagedTensor/虚拟地址能力 |
| MoE-APEX / adaptive precision | 按 expert 或层做自适应精度/带宽优化 | 作为低比特拓展，不改变当前保守低比特容量 | INT4/NVFP4/W4A8 质量回归、scale/metadata 余量 | 不能把精度降低当作免费容量收益 |
| Mooncake | P/D 分离和 CPU/DRAM/SSD/RDMA KVCache pool，Conductor 按 KV 分布与 SLO 调度 | 不改变单卡容量公式 | KV object 化、host KV pool、TTFT/TBT 口径 | 单机只借鉴 KV pool/connector，不照搬集群 P/D |
| LMCache | KV store/retrieve/lookup，chunk 化搬运，多后端，layer-wise pipeline，connector API | 不改变 KV bytes/token，只影响搬运粒度 | UCM/external KV、DRAM/SSD warm/cold tier、chunked transfer | 不把 LMCache 等同于 SSD direct fast path |
| Tutti | GPU-centric HBM-SSD KV object I/O，减少 tiny random I/O 和 CPU critical path | 用于 SSD 风险和 direct path 需求，不用于 A+K 默认性能估算 | SSD 不能进逐 token active path、P2P/direct 作为推荐项 | 不默认 Ascend 具备 NPU-native SSD submission |
| SolidAttention | dynamic sparse attention + SSD KV block consolidation/prefetch/scheduler | 不用于缩小 GLM-5.2 默认 KV 表 | 128K/1M 长上下文研究项、SSD-aware scheduler | 未验证 GLM-5.2/IndexShare 下 sparse recall 前不降容量 |
| ECHO / sparse KV restore | sparse LLM/KV restore 的 lossless prefetch 路线 | 不改变默认 KV 容量 | sparse attention/IndexShare 的研究项与 restore-vs-recompute 评估 | 没有 GLM-5.2 sparse/index 兼容证据前只作拓展 |
| Bidaw | host memory + SSD two-tier KV，ready/preparing queue，previous-answer-based eviction | 不改变单请求 active KV，影响历史 KV warm/cold 放置 | DRAM/SSD 容量余量、interactive agent 历史会话 | 只对多轮交互历史 KV 有效，不证明单轮 prefill 加速 |
| CacheSlide | agent prompt 相对顺序保持但绝对位置漂移时复用 KV，并做 spill-aware KV 管理 | 不用于默认容量压缩 | agent/coding 场景的 prefix reuse 与 SSD spill 风险 | 不作为通用 prefix cache 或通用 SSD 加速 |
| TensorRT-LLM DS / vLLM NixlConnector / NVIDIA Dynamo | P/D disaggregation、NIXL/KVBM/LMCache/FlexKV、CPU/disk tiers | 不改变单卡 L0-L2 容量，影响多卡生产边界和 direct/object transfer 研究项 | KV transfer bytes、RDMA/NIXL/UB、phase-aware routing | 低并发单卡不默认收益；多卡/小集群才进入 serving 主路径 |
| ServeGen | 生产 workload 的 arrival、input/output、client、reasoning/multimodal 分布生成 | 不给硬件容量，给 workload 字段 | 验证清单、仿真输入 | 不证明 offload 路径有效 |
| BurstGPT | 真实请求 trace、burstiness、conversation、response length、failure 行为 | 不给硬件容量，给 trace replay 口径 | P50/P95/P99、failure、burst 压测 | 云端 GPT trace 不等于本地 A+K agent 负载 |
| ProfInfer / Chakra / CCL-Bench | operator timeline、hardware counter、execution trace、collective benchmark | 不给容量，给 evidence layer | 瓶颈归因、trace schema、PCIe/UB/RDMA/collective microbench | profiler 不是 offload 策略，需要和 CANN/NPU counter 对齐 |
| LLMServingSim2.0 | hetero devices、multi-tier memory、MoE/offload、prefix、P/D、power 的 runtime-driven 仿真 | 用于规格复核流程，不直接给 BOM 数值 | profile/simulation 字段、电源/能耗、瓶颈归因 | 没有 A+K profile 前不能直接输出可信性能 |
| ITME / CXL tier | CXL-hybrid memory、TB-scale tiered capacity | 不进入 L0-L2 默认，只作为 P2/P3 warm tier 研究项 | CXL memory 可选项、latency/bandwidth sensitivity | CXL/remote memory 不能当 HBM 热层 |
| vLLM-Ascend / MindIE / UCM / KV Pool | Ascend CPU KV offload、external KV、Mooncake backend、Page Attention/continuous batching | 进入 A+K 工程接口，不直接改变模型容量 | P0/P1 落地路线、NPU stream、CANN counter、host OOM/copy stall | 官方接口可用不等于 GLM-5.2 单卡速度可承诺 |

结论是：**本文硬件容量表是 GLM-5.2 参数驱动，文献方法驱动的是分层策略、约束条件和验证流程。** 这比直接套用论文里的吞吐提升更保守，但更适合 A+K 单卡一体机这种硬件栈尚需实测的场景。

## 7. 单卡一体机硬件规格反推

### 7.1 GPU / NPU / HBM

#### L0/L1a/L1b：最低加载验证档

| 项目 | 建议规格 | 借鉴与估计说明 |
|---|---|---|
| HBM 容量 | L0 锚点为 84 GB Bailu；L1a/L1b 为 64-96 GB | 不是为了装全量权重，而是只放 non-expert 核心、shared expert、active KV、workspace 和极小 hot expert cache；这一口径借鉴 FluxMoE/KTransformers 的 expert 分层思想，但由于 HBM 只能容纳很少 hot experts，DALI/FineMoE 类 hotness 方法尚不足以保证命中率 |
| HBM 带宽 | >= 1.2 TB/s，越高越好 | expert miss 下界由 5.5 节计算；只要 miss 进入 PCIe/DRAM 热路径，TPOT 就会被搬运时间主导；NEO/FlexInfer 只支持 overlap 思路，不证明低带宽可用 |
| 计算精度 | INT4/W4A8/FP8 kernel 必须可用 | L0-L2 成立依赖低比特权重；MoE-APEX/adaptive precision 只作为进一步降带宽的研究项，不能替代 INT4/W4A8 kernel |
| 定位 | 容量验证、低速加载和少量生成验证 | 对应第 8 章 L0/L1a/L1b，不对应低速交互体验 |
| 风险 | hot expert cache 太小，PCIe/DRAM miss 频繁，TPOT 很差 | KTransformers/DALI/FluxMoE 说明可以分层，但没有 GLM-5.2 routing trace 前，不能把分层写成稳定速度收益 |

此档不建议作为 GLM-5.2 演示机。它只能验证模型切片、权重格式、runtime hook、少量 token 生成是否打通。

#### L2：单用户低速可交互尝试档

| 项目 | 建议规格 | 借鉴与估计说明 |
|---|---|---|
| HBM 容量 | 192 GB 起步，256 GB 推荐 | 由 GLM-5.2 hot working set 反推：non-expert/shared、32K active KV、workspace、prefetch buffer 后，仍要留出数十到上百 GB 给 hot routed experts；这个要求来自 KTransformers/DALI/FluxMoE 的 hot expert cache/warm expert 设计，而不是官方推荐规格 |
| HBM 带宽 | >= 3.2 TB/s，推荐 >= 5 TB/s | 参考 expert miss 表，L2 目标是把大多数 routed expert 命中挡在 HBM 内；带宽越高，copy/compute overlap 越有机会吸收小比例 miss |
| 低比特支持 | INT4/NVFP4/W4A8 权重，FP8/BF16 compute，FP8 KV 可选 | 低比特把全量权重从 FP8 约 744 GB 降到工程 INT4 约 395-465 GB，使 DRAM warm/resident 成为可能；KV FP8 只降低 KV 层容量，不改变权重下界 |
| 稀疏/MoE 支持 | MoE fused kernel、expert cache、异步 copy stream、prefetch hook | 直接对应 DALI/FineMoE/HybriMoE 的 hotness trace、FluxMoE 的 paged/transient expert、KTransformers 的异步 expert 调度 |
| 上下文目标 | 32K x 1 低速可交互尝试，128K x 1 只作风险压测 | KV 容量按 GLM-5.2 MLA 公式计算；Mooncake/LMCache/Bidaw/CacheSlide 只支持 warm/cold KV 分层和复用，不直接把 128K/1M KV 容量抹掉 |
| 定位 | 向上对照的单用户 agent/coding 长任务尝试 | 需要第 13 章 profile 通过后才能从“硬件可承载”升级为“低速可交互尝试” |

192-256 GB HBM 的核心价值不是装下全量模型，而是给 hot working set 足够空间：non-expert 核心、shared expert、hot routed experts、KV、workspace、MTP 和预取窗口。

#### 高配上探边界

本文不设置单卡高配上探档。若目标需要 1M 长上下文验证、4TB DRAM、16-32TB NVMe 或 512GB 级 HBM，则已经偏离“向下压榨硬件”的目标，应另立高配上探报告或直接进入多卡方案评估。

#### 多卡生产边界说明

| 项目 | 建议规格 | 借鉴与估计说明 |
|---|---|---|
| NVIDIA | 8xH200/H20 FP8；满 1M context 更偏 8xB200 | FP8 权重约 744 GB 裸容量，工程 HBM 接近 0.85-1.0 TB；这是官方/vLLM 生产口径，Mooncake/Dynamo/NIXL 类 P/D/KV transfer 更适合在此档发挥 |
| AMD | 8xMI300X/MI355X FP8，按 vLLM/ROCm/ATOM recipe 调 `max_model_len` 与 `max_num_seqs` | 同样以全量 FP8/低比特权重常驻 HBM 为主，offload 只作为容量和长上下文补充 |
| Ascend | 量化权重 + vLLM-Ascend/xLLM/SGLang，多卡 TP/DP/EP | A+K 工程接口可借鉴 vLLM-Ascend/UCM/KV Pool；但稳定服务需要多卡并行，而不是单卡 SSD offload |
| 定位 | 多并发服务、1M context、稳定 SLO | ServeGen/BurstGPT/LLMServingSim2.0 的负载和仿真口径主要服务这一边界 |

如果用户目标变为多用户服务，这一档才是应该采购和评估的方向。

### 7.2 CPU

对 A+K 一体机，CPU 建议规格：

| 项目 | L0/L1a/L1b 下限 | L2 向上对照 | 借鉴与估计说明 |
|---|---:|---:|---|
| 核数 | 32-48 cores | 64-96 cores | NEO/FlexInfer/KTransformers 都把 CPU 放在调度、KV/expert warm tier、异步搬运和部分 fallback 上；L2 需要更多线程承接 profile、I/O aggregation 和恢复队列 |
| 内存通道 | 8 通道 DDR5 | 12 通道 DDR5 或更高 | expert materialization、KV warm tier 和 SSD page cache 都走 DRAM；DALI/FluxMoE/LMCache 类方法要求 warm tier 有足够并行内存通道 |
| DRAM 带宽 | >= 300 GB/s | >= 500-800 GB/s | 5.5 节已经显示 routed expert miss 传输量很大；若 DRAM 带宽不足，hot expert cache miss 会直接变成 TPOT 瓶颈 |
| 指令能力 | NEON/SVE 基线 | SVE/SME 或厂商矩阵扩展可用，必须做 GLM expert shape microbenchmark | 只有在 microbenchmark 证明有效时，才参考 KTransformers 式 CPU expert compute；不能继承 Intel AMX 论文速度 |
| PCIe root | CPU 直连加速卡和 NVMe | 加速卡 x16 + NVMe 分组直连，避免跨 NUMA | Tutti/Bidaw 提醒 SSD/DRAM/HBM bounce copy 会造成 stall；拓扑必须支持稳定 DMA 和 overlap |
| 角色 | metadata、调度、I/O、warm tier | 加上低频 expert fallback、profiling host | 对应第 8 章 L0-L1b“控制与搬运”、L2“可实验 fallback，但需 profile” |

CPU 不应被规格书写成“替代 NPU/GPU 算 FFN”。正确写法是：CPU 为容量、状态、调度和观测提供支撑；是否参与 expert compute 需要以 shape-specific microbenchmark 决定。

### 7.3 DRAM

DRAM 需要承担低比特全量权重或其 warm set、warm expert tier、inactive KV、page cache、runtime metadata 和系统缓冲。这里要区分“能 mmap 加载”和“能稳定 warm-staging”：前者可以用更小 DRAM 加 SSD 分页硬撑，后者才是报告推荐的最低加载口径。

| 目标 | DRAM 容量 | 理由 | 借鉴与估计说明 |
|---|---:|---|---|
| L0 现有样机极限分层验证 | 约 249-419 GB，锚点为 384 GB | 按 routed experts 热 / 温 / 冷 = 10% / 30% / 60%，DRAM 只保留 30% 温专家、metadata、staging、page cache 和系统余量 | 这是比 L1a 更激进的验证口径，可解释 384 GB DDR5 的锚点意义；要求 SSD 冷层和预取命中，不能写成最低能稳定加载 |
| L1a SSD-offload 极限加载 | 512-768 GB | 依赖 SSD cold expert / cold KV / mmap paging，只验证加载和少量 token，不承诺速度 | 借鉴 FluxMoE/KTransformers 的分层放置，但只保留 warm set，不要求全量 routed expert resident；Tutti/Bidaw 的约束要求 SSD page fault 不得成为常态热路径 |
| L1b DRAM-warm 保守加载 | 1 TB | 可容纳 395-465 GB 低比特权重、runtime、pinned staging 和基本 page cache | 395-465 GB 来自 GLM-5.2 INT4 工程权重；额外 500 GB 左右来自 LMCache/Mooncake/KTransformers 类 warm tier、staging、page cache 和系统余量 |
| L2 单用户低速可交互尝试 | 1.5-2 TB | 给 395-465 GB 低比特权重、热/温 expert、KV warm tier、SSD page cache 留足余量 | L2 参考 DALI/FluxMoE 的 hot/warm expert cache 和 Mooncake/LMCache 的 host KV pool；2 TB 是为了减少 SSD page fault，而不是 KV 公式本身需要这么大 |
| 128K 风险压测 | 2 TB 左右更稳 | 支持更多 prefix/KV、历史会话、SSD 缓冲和 trace | Bidaw/CacheSlide/LMCache 的多轮历史 KV、prefix reuse 和 spill-aware 管理会增加 DRAM warm/cold 缓冲需求；不作为主承诺 |
| 官方 FP8 全量 DRAM staging | >= 2 TB | 756 GB FP8 权重 + 量化/scale + 多副本/缓存/工作区 | 如果不采用低比特常驻，则 DRAM 下限由 FP8 权重和工程副本推高；文献 offload 方法不能消除这一冷启动/转换容量 |

DRAM 带宽同样重要。如果 DRAM 只有容量但带宽低，expert materialization 会变成 PCIe/HBM 等待；如果 NUMA 拓扑混乱，CPU worker 会被 remote memory access 拖慢。

### 7.4 SSD / NVMe

SSD 的角色有三类：

1. 存放权重文件和多种量化版本。
2. 作为 cold expert / cold KV / prefix cache 的容量层。
3. 支撑实验过程中的 trace、profile、checkpoint 和缓存。

建议：

| 项目 | L0/L1a/L1b | L2 向上对照 | 借鉴与估计说明 |
|---|---:|---:|---|
| 总容量 | L0 为 2 TB；L1a/L1b 4 TB 起步 | 8-16 TB | 容量来自低比特/FP8 checkpoint、cold expert、cold KV、trace/profile；L2 需要更多 trace 和量化版本余量 |
| 盘数 | 1-2x PCIe Gen4/5 NVMe | 4x PCIe Gen5 NVMe 更稳 | 多盘用于提高冷启动、prefetch 和 trace 写入余量；Tutti/SolidAttention/Bidaw 都显示 SSD 路径必须考虑并发队列和 I/O 粒度 |
| 聚合顺序读 | >= 14 GB/s 为 L1 起步参考，L0 按实测记录 | >= 40-56 GB/s | L1a 可接受较低顺序读用于加载验证；L2 需要把 cold restore/prefetch 尽量挡在 token critical path 外 |
| 随机读 IOPS | >= 1M，重点看 P95/P99 | >= 2-4M，重点看 tail latency | tiny random I/O 是 Tutti 特别指出的风险；仅有顺序带宽不能证明 KV/expert restore 有效 |
| 企业特性 | 可选但应记录 SMART/温控 | PLP、稳定 QoS、温控、可观测 SMART | 长任务和 trace/profile 会放大 SSD tail latency；报告关注稳定 QoS，而不是消费级峰值 |
| 数据路径 | CPU-mediated 可接受，但必须测 bounce copy | 尽量支持 P2P/direct/fabric memory，至少要能异步预取 | direct path 参考 Tutti/NIXL 类方向；没有 direct path 时必须把低速生成边界写清楚 |

关键限制：SSD 不能成为逐 token active expert 的供应源。SSD 可做冷层，但必须通过 chunk/object、prefetch 和 queue 管理把 I/O 挡在关键路径之外。

### 7.5 PCIe / CXL / UB / HCCS

| 链路 | 建议规格 | 作用 | 借鉴与估计说明 |
|---|---|---|---|
| 加速卡链路 | PCIe Gen5 x16 起步，或厂商等效 UB/HCCS/fabric | HBM 与 DRAM 之间的 expert/KV transfer | 5.5 节把 expert miss 转成 PCIe 时间下界；L0-L2 都应把有效带宽、双向 copy 和 overlap 写入验收项 |
| NVMe 链路 | L1a/L1b 至少 2 组 x4；L2 建议 4 组 x4，避免与加速卡抢同一低带宽 uplink | SSD cold tier | Tutti/Bidaw/SolidAttention 要求 cold KV/expert 能异步恢复；NVMe 不应与加速卡共享狭窄上行链路 |
| P2P / DMA | L1 可选，L2 推荐 | 减少 CPU bounce copy | 对应 Tutti、Dynamo/NIXL、TensorRT-LLM KV exchange 的 direct/object transfer 思路；没有 direct path 时必须把低速生成边界写清楚 |
| CXL memory | 可选，不作为 v1 必需 | 可作为 future warm tier，但延迟/带宽需实测 | ITME/CXL 只作为 P2/P3 容量扩展，不替代 HBM hot tier 或 DRAM resident 权重 |
| NUMA 拓扑 | 加速卡、NVMe、主 DRAM 尽量本地 | 降低 remote access 和 DMA 走远路 | KTransformers/NEO 类 CPU 协同对 NUMA 敏感；拓扑不清会让文献中的异步重叠失效 |

理论峰值不等于有效带宽。规格书应要求给出：

- H2D/D2H 单向与双向带宽。
- 小块与大块 DMA 延迟。
- pinned memory 分配和回收成本。
- copy stream 与 compute stream overlap。
- SSD read 到 HBM 的实际路径和 stall。

### 7.6 电源、散热与整机形态

单卡一体机虽然叫“小算力”，但如果目标是 GLM-5.2，整机功耗不会小。

| 档位 | 加速卡 | CPU+DRAM | SSD/主板 | 推荐电源 | 散热 |
|---|---:|---:|---:|---:|---|
| L0 现有样机极限分层验证 | 现有 84GB Bailu 配置 | 现有 384GB DDR5 配置 | 2TB SSD | 按现有样机实测 | 必须记录降频、SSD 温控和长时间 profile 稳定性 |
| L1a/L1b 最低加载验证 | 300-600 W | 250-500 W | 50-100 W | 1200-1600 W | 高风量塔式/4U |
| L2 单用户低速可交互尝试 | 600-1000 W | 400-700 W | 80-150 W | 1800-2800 W | 4U/塔式服务器，独立风道 |
| 多卡生产边界 | 多卡 4-8 kW | 1 kW+ | 200 W+ | 机柜级 | 液冷或高规格风冷 |

报告建议不要把 GLM-5.2 单卡机包装成普通桌面工作站。它更接近“单加速卡高内存服务器”。

## 8. 推荐 BOM 档位

本章按“向下压榨硬件”的主线组织 BOM：L0 先解释现有样机能验证什么，L1a/L1b 再给最低加载的两种口径，L2 只作为 32K 单用户低速可交互尝试的向上对照。本文不设置高配单卡上探档。

| 档位 | 新名称 | 硬件定位 | 验收口径 |
|---|---|---|---|
| L0 | 现有样机极限分层验证档 | 84GB Bailu + 384GB DDR5 + 2TB SSD | 权重分层、runtime hook、少量 token、profile，不能承诺速度 |
| L1a | SSD-offload 极限加载档 | 64-96GB HBM + 512-768GB DRAM + 4TB NVMe 起步 | 大量 cold experts/cold KV 留在 SSD，验证加载和少量 decode |
| L1b | DRAM-warm 保守加载档 | 64-96GB HBM + 1TB DRAM + 4TB NVMe 起步 | 低比特全量权重尽量 resident/warm，更稳地验证 4K-16K smoke/profile |
| L2 | 单用户低速可交互尝试档 | 192-256GB HBM + 1.5-2TB DRAM + 8-16TB NVMe | 32K x 1 低速可交互尝试，128K 仅作风险压测 |

### 8.1 L0：现有样机极限分层验证档

用途：解释 `84GB Bailu + 384GB DDR5 + 2TB SSD` 这类现有/低配样机，如何通过极限冷热分层勉强验证 GLM-5.2 的加载、分层和少量生成路径。

| 项目 | 建议口径 | 说明 |
|---|---|---|
| 硬件锚点 | 84GB Bailu + 384GB DDR5 + 2TB SSD | 这是容量压榨验证锚点，不是性能档 |
| 分层比例 | routed experts 按 HBM/DRAM/SSD = 10%/30%/60% 拆分 | 该比例只用于容量试算，不等同于逐 token miss 比例 |
| HBM 热层 | hot routed experts + non-routed/shared + active KV + workspace，总热层约 63-78GB | 84GB 勉强覆盖，但 workspace、碎片和预取窗口都很紧 |
| DRAM 温层 | warm routed experts + metadata + staging + page cache，总温层约 249-419GB | 384GB 可以作为极限验证，但不能保留全量低比特权重 resident |
| SSD 冷层 | cold routed experts + cold KV/prefix + checkpoint + trace | 2TB 容量够做单量化版本与基础 trace，关键风险是随机 I/O 和 tail latency |
| 可承诺 | 容量验证、权重切片、runtime hook、少量 token 生成、profile 采集 | 重点是证明链路和归因能力 |
| 不承诺 | 稳定 TPOT、可交互速度、L1b 最低加载、1M 长上下文验证 | 失败必须能归因到 HBM/DRAM/PCIe/SSD/CPU/NPU/调度 |

### 8.2 L1a：SSD-offload 极限加载档

用途：在比 L0 更稳一点、但仍高度依赖 SSD cold tier 的配置下，验证 GLM-5.2 能否加载并产生少量 token。

| 组件 | 规格 | 借鉴与估计说明 |
|---|---|---|
| HBM | 64-96GB | 放 non-expert、shared、active KV、workspace 和极少 hot experts |
| CPU | 32-48 cores，8 通道 DDR5 | 主要做调度、I/O、metadata、mmap/page cache，不承诺 CPU expert compute |
| DRAM | 512-768GB | 保存 warm set、page cache、metadata、staging，不要求全量 routed expert resident |
| SSD | 4TB NVMe 起步 | 大量 cold routed experts、cold KV/prefix、checkpoint 和 trace 留在 SSD |
| 互联 | PCIe Gen4/5 x16，NVMe 尽量本地 | 需要测 H2D/D2H、小块/大块、copy/compute overlap |
| 默认上下文 | 4K-8K smoke，16K 仅在 profile 可解释时尝试 | KV 不是主瓶颈，expert miss 和 SSD stall 才是主风险 |
| 可承诺 | 加载、prefill/少量 decode 打通 | decode 可能只有 `0.05-0.5 tok/s` 常见区间，局部 warm 后可到 `0.5-1.5 tok/s` |
| 不承诺 | 稳定 TPOT、32K 长输出、SSD 不抖动、可交互体验 | SSD cold miss 进入 token critical path 时会出现秒级 stall |

### 8.3 L1b：DRAM-warm 保守加载档

用途：在 1TB DRAM 下，让低比特全量权重尽量 resident/warm，减少 SSD page fault，相比 L1a 更适合作为“最低加载验证”的稳妥口径。

| 组件 | 规格 | 借鉴与估计说明 |
|---|---|---|
| HBM | 64-96GB | 放 non-expert、shared、active KV、workspace、少量 hot experts |
| CPU | 32-48 cores，8 通道 DDR5 | 做调度、warm tier、profile host 和异步搬运 |
| DRAM | 1TB | 覆盖 395-465GB 低比特权重、metadata、pinned staging、page cache 和系统余量 |
| SSD | 4TB NVMe 起步 | 主要做冷层、checkpoint、trace 和失败恢复余量 |
| 默认上下文 | 4K-16K smoke/profile | 比 L1a 更适合验证 runtime hook、低比特加载和基本生成 |
| 可承诺 | 更稳定地验证最低加载、低比特权重 resident/warm、少量生成 | decode 估算可按 `0.5-2 tok/s` 较现实、`2-5 tok/s` 为优化目标处理 |
| 不承诺 | 单用户可交互速度、稳定 32K 长输出、多并发 | L1b 仍然不是演示机档位，不能包装成低速交互整机 |

### 8.4 L2：单用户低速可交互尝试档

用途：作为向上对照，不作为本文主目标。用于说明如果硬件放宽到 192-256GB HBM、1.5-2TB DRAM，可以尝试 32K 单用户低速可交互。

| 组件 | 规格 | 借鉴与估计说明 |
|---|---|---|
| HBM | 192GB 起步，256GB 更稳 | 给 hot expert cache、workspace、active KV 和 prefetch buffer 留空间 |
| CPU | 64-96 cores，8-12 通道 DDR5，强 NUMA 控制 | 可实验低频 expert fallback，但必须以 Kunpeng shape microbenchmark 证明 |
| DRAM | 1.5-2TB | 给全量低比特权重、warm expert、warm KV、page cache、pinned staging、trace 留余量 |
| SSD | 8-16TB NVMe | 存 checkpoint、多量化版本、cold expert、cold KV、trace 和恢复数据 |
| 互联 | PCIe Gen5 x16 到加速卡，NVMe 直连 CPU root，支持异步 DMA/P2P 更佳 | expert miss 表显示 5%-10% miss 已有明显传输成本 |
| 软件 | 低比特 runtime + expert/KV 分层 + prefetch + stall attribution | 没有这些软件层，硬件规格不能自动转成低速可交互体验 |
| 默认目标 | 32K x 1 低速可交互尝试 | 需记录 TTFT、TPOT、HBM occupancy、expert miss、SSD tail latency |
| 压测目标 | 128K x 1 可压测，但不作为主承诺 | 主要用于暴露 KV、workspace、expert cache 和 SSD 恢复风险 |
| 不承诺 | 1M 长上下文验证、多并发、生产 SLO | 若目标转为长上下文或服务化，应另行进入多卡方案 |

### 8.5 多卡生产边界说明

当目标变成多用户、高上下文或生产 SLO 时，问题已经不是“单卡向下压榨硬件”，而是标准多卡推理系统设计。

| 项目 | 边界说明 |
|---|---|
| NVIDIA/AMD | 参考 8xH200/H20、8xB200 或 MI300X/MI355X 级 FP8/低比特节点 |
| Ascend | 转向多卡量化部署，采用 vLLM-Ascend/xLLM/SGLang、TP/DP/EP、UCM/KV Pool 等工程路线 |
| DRAM/SSD | 主要服务 KV warm tier、prefix/history cache、checkpoint、trace、日志和恢复 |
| 网络/互联 | 需要建模 P/D、EP/TP/DP、KV transfer 和 collective；可参考 LLMServingSim2.0/Chakra/CCL-Bench |
| 结论 | 多卡生产边界只用于划清承诺范围，不用于包装 L0-L2 单卡方案 |

### 8.6 BOM 档位的计算依据复核

本节把第 6 章的方法假设重新压回 BOM 档位。阅读顺序应是：第 3-5 章给出 GLM-5.2 的字节级下限，第 6 章说明哪些文献方法可以改变放置和搬运，第 7 章把这些方法落到单个硬件组件，本章再组合成整机档位。

| 档位 | 关键计算过程 | 参考文献方法是否进入估算 | 不应承诺 |
|---|---|---|---|
| L0 现有样机极限分层验证 | routed experts INT4 裸容量 362.4GB，按 HBM/DRAM/SSD = 10%/30%/60% 拆分为 36.2/108.7/217.4GB；叠加公共层、KV、workspace 后 HBM 约 63-78GB，DRAM 约 249-419GB | 采用 FluxMoE/DALI/KTransformers 的 hot expert cache、workload-aware replacement 和预取思想，但该比例只是容量压缩试算，必须用 trace 校验 | 不承诺 L1b 保守加载，不承诺稳定 TPOT，不承诺 SSD cold expert 可进入逐 token 热路径 |
| L1a SSD-offload 极限加载 | INT4 工程权重约 395-465GB，DRAM 512-768GB 只能保存 warm set/page cache；64-96GB HBM 只放 non-expert、少量 hot experts、active KV 与 workspace | 采用 FluxMoE/KTransformers/DALI 的 expert 冷热分层思路，采用 LMCache/Bidaw/Tutti 的 cold KV/cold expert 不能阻塞热路径约束 | 不承诺稳定 TPOT，不承诺 32K 长输出，不承诺 SSD active expert |
| L1b DRAM-warm 保守加载 | 1TB DRAM 覆盖 395-465GB 权重 + 50-120GB metadata + 50-150GB staging + 100-250GB page cache + 20-100GB 系统/KV 余量 | 同 L1a，但要求全量低比特权重尽量 resident/warm，减少 SSD page fault | 不承诺低速交互体验 |
| L2 单用户低速可交互尝试 | 192-256GB HBM 覆盖 non-expert/shared、32K KV、workspace、hot routed experts、prefetch buffer；1.5-2TB DRAM 覆盖低比特全量权重、warm expert、KV warm tier 和 page cache | 明确采用 KTransformers/DALI/FluxMoE 的 hot expert cache + DRAM warm tier，采用 Mooncake/LMCache/Bidaw 的 KV object/warm tier，采用 Tutti/SolidAttention 的 SSD 风险约束 | 不承诺 1M 长上下文验证，不承诺多并发生产 SLO |
| 多卡生产边界 | FP8 权重约 744GB，工程 HBM 需求接近 0.85-1.0TB，单卡不满足，因此转向多卡 FP8/低比特节点 | 参考 vLLM/官方 recipe 和 serving 系统文献的生产化口径 | 不再满足“单卡一体机向下压榨”约束 |

这张复核表也说明：L0-L2 的 DRAM 和 SSD 并不是来自某篇文献的固定规格，而是由 GLM-5.2 权重规模先给出容量下限，再用文献方法约束这些容量层的用途。SSD 可以参与 cold expert/cold KV/checkpoint/mmap page cache，但不能作为逐 token active expert 的供应源；任何 direct/object I/O 优化都必须通过 stall profile 验证。

## 9. 场景复核

场景复核按“验证什么、不承诺什么”组织，不再把 128K/1M 写成主挑战目标。

| 场景 | 新定位 | 推荐档位 | 验收/观察重点 |
|---|---|---|---|
| 4K | 最小 smoke test | L0/L1a/L1b | 能否完成加载、prefill 和少量 decode；记录冷启动、HBM occupancy、expert miss |
| 8K | 基本 smoke test | L0/L1a/L1b | 比 4K 更容易触发 expert warm/cold 切换；重点看 SSD tail latency 和预取命中 |
| 16K | 主验证目标 | L1b | 验证 DRAM-warm 全量低比特权重、runtime hook、KV offload 和 profile 闭环 |
| 32K | 单用户低速可交互尝试上界 | L2 | 记录 TTFT、TPOT、OOM、stall、HBM hot expert cache 是否被挤压 |
| 128K | 风险压测，不作为主承诺 | L2 可选 | 用于暴露 KV、workspace、expert cache、SSD 恢复和调度风险；失败也要保留 trace |
| 1M | 不在本文范围 | 另立高配单卡或多卡方案 | 仅作为容量和状态恢复风险边界；不作为本文验收项 |

### 9.1 4K-8K smoke test

| 项目 | 估算 |
|---|---:|
| 4K BF16 KV | 0.34 GiB |
| 4K FP8 KV | 0.17 GiB |
| 8K BF16 KV | 0.69 GiB |
| 8K FP8 KV | 0.34 GiB |
| 主要压力 | 低比特权重加载、expert 分层、runtime hook、SSD cold miss |

结论：4K-8K 是 L0/L1a 的基本 smoke test。它不证明可交互，只证明最低加载、少量 token 和 profile 链路能打通。

### 9.2 16K 主验证目标

| 项目 | 估算 |
|---|---:|
| BF16 KV | 1.37 GiB |
| FP8 KV | 0.69 GiB |
| HBM 主要压力 | hot expert cache + workspace |
| DRAM 主要压力 | 全量低比特权重 resident/warm、staging、page cache |
| SSD 主要压力 | cold expert、checkpoint、trace、失败恢复 |

结论：16K 是 L1b 更合理的主验证目标。若 16K 无法输出可解释的 TTFT/TPOT、expert hit/miss、KV 层级和 SSD tail latency，32K 体验不应被对外承诺。

### 9.3 32K 单用户低速可交互尝试

| 项目 | 估算 |
|---|---:|
| BF16 KV | 2.74 GiB |
| FP8 KV | 1.37 GiB |
| 低比特全量权重 | 约 395-465 GB 工程口径 |
| HBM 主要压力 | hot expert cache + workspace |
| DRAM 主要压力 | 全量权重 + warm expert + page cache |
| SSD 主要压力 | 冷启动、cold expert、历史 KV、trace |
| 推荐硬件 | L2：192-256GB HBM + 1.5-2TB DRAM + 8-16TB NVMe |

结论：32K 是 L2 的单用户低速可交互尝试上界，不是 L0/L1a/L1b 的默认验收项。

### 9.4 128K/1M 风险边界

128K/1M 主要用于说明容量和状态恢复风险。本文的主目标是向下压榨硬件，不以 128K/1M 作为验收目标。

| 场景 | KV 容量 | 边界说明 |
|---|---:|---|
| 128K BF16 / FP8 | 10.97 GiB / 5.48 GiB | KV 容量本身可算，但 workspace、Index/cache metadata、expert prefetch 和 SSD 恢复风险会显著放大 |
| 1M BF16 / FP8 | 87.75 GiB / 43.88 GiB | 已经偏离 L0-L2 的验证目标；若需要演示，应另立高配上探或多卡方案 |

## 10. A+K 落地建议

### 10.1 P0 必做

- vLLM-Ascend / xLLM / SGLang 路线先打通 GLM-5.2 或同构 GLM MoE 的低比特加载。
- 接入 KV CPU offload：CPU DRAM 作为 warm tier，记录 H2D/D2H、copy stream、host OOM、LRU 命中。
- 接入 UCM / external KV：把 prefix/KV 从 HBM 中对象化，支持 lookup/load/store。
- 建 profiler：记录 HBM occupancy、DRAM traffic、PCIe/UB、SSD I/O、NPU kernel、CPU host overhead。

### 10.2 P1 应做

- expert hotness trace：记录每层 top-k expert ID、命中率、miss penalty。
- hot expert cache：先静态，再动态；先 HBM/DRAM 两层，再考虑 SSD cold。
- Mooncake KV Pool / PD 原型：在单机里只提取 KV object + host pool + connector，不照搬集群 P/D。
- 128K context 压测：看 KV、workspace、expert cache 互相挤压的拐点。

### 10.3 P2/P3 研究项

- SSD-backed KV/expert cold tier：必须验证 tiny I/O、CPU control path、DRAM-HBM bounce copy；L0-L2 都应作为 profile 项。
- NPU-native SSD/direct path：目前公开证据不足；如果目标转为 1M 长上下文验证，应作为高配上探报告的优先验证项。
- Kunpeng expert kernel：需要 SVE/SME microbenchmark，不能直接继承 KTransformers 的 Intel AMX 结论。
- CXL memory：可作为 future warm tier；当前 L0-L2 不列为默认 BOM，需要实测延迟和带宽后再进入上探方案。

## 11. 风险与不应承诺项

| 风险 | 为什么重要 | 处理方式 |
|---|---|---|
| 单卡 HBM 放不下官方权重 | FP8 也约 744 GB 裸权重 | 明确只做低比特 + offload 演示 |
| 量化质量下降 | INT4/NVFP4/W4A8 可能影响 reasoning/coding | 单独做质量回归，不把量化当免费 |
| expert routing 不稳定 | hot expert cache 可能 miss | 必须采集 expert trace |
| PCIe 成为逐 token 瓶颈 | active expert miss 不能每 token 大量传 | 只允许小比例 miss，并预取 |
| SSD tiny I/O | 账面带宽无法转化为有效 KV/expert restore | chunk/object、queue、prefetch |
| CPU 同步开销 | host overhead 会放大 TPOT/P99 | async stream、减少同步、profile |
| Ascend/Kunpeng 公开证据不足 | CUDA/AMX 论文不能直接迁移 | 做 A+K microbenchmark |
| 1M context 误承诺 | 单卡 HBM/workspace/hot expert 被挤爆 | 只写风险边界，不写主承诺或验收目标 |

## 12. 最终硬件建议：按向下压榨目标组织

最终建议不再按高配单卡采购/设计，而是按 L0-L2 的验证问题组织。

| 档位 | 建议硬件 | 验收目标 |
|---|---|---|
| L0 | 84GB Bailu + 384GB DDR5 + 2TB SSD | 权重分层、少量 token、profile，不能承诺速度 |
| L1a | 64-96GB HBM + 512-768GB DRAM + 4TB NVMe | SSD-offload 极限加载，能出 token |
| L1b | 64-96GB HBM + 1TB DRAM + 4TB NVMe | 更稳的最低加载，4K-16K smoke/profile |
| L2 | 192-256GB HBM + 1.5-2TB DRAM + 8-16TB NVMe | 32K 单用户低速可交互尝试 |

本文不再推荐高配单卡采购。256-512GB HBM、4TB DRAM、16-32TB NVMe 属于高配单卡上探方案，不符合当前“向下压榨硬件”的目标；若目标转为 1M 长上下文验证或服务化，应另立报告。

## 13. 可执行验证清单

交付硬件前应做以下验证，而不是只看规格表。验证清单按 L0-L2 降级，不把 1M 长上下文验证作为必做项。

1. **权重加载验证**：低比特权重能从 SSD -> DRAM -> HBM 分层加载，记录冷启动时间、峰值内存、mmap/page fault 和失败恢复路径。
2. **4K smoke test**：能完成 prefill 和少量 decode，记录 TTFT、TPOT、HBM occupancy、expert miss。
3. **8K/16K 加载与生成验证**：记录 TTFT、TPOT、HBM occupancy、expert hit/miss、prefetch lead time、DRAM traffic。
4. **32K 压力验证**：仅 L2 执行，记录 OOM、stall、SSD tail latency、workspace 峰值、hot expert cache 被挤压情况。
5. **expert trace**：记录每层 top-k expert、hot set size、hit/miss、miss load latency、miss 发生时所在层级。
6. **KV offload trace**：记录 KV block 所在层级、load/store 时间、prefix hit/miss、HBM/DRAM/SSD 迁移粒度。
7. **PCIe/UB copy microbench**：测大块、小块、双向、compute overlap、pinned memory 分配和回收成本。
8. **SSD microbench**：测真实 chunk size 下的随机/顺序混合读取、P50/P95/P99 tail latency、温控降速和长时间 trace 写入。
9. **CPU kernel microbench**：如需 Kunpeng expert fallback，必须测 GLM expert shape，不能继承 Intel AMX 或 CUDA 论文速度。
10. **质量回归**：低比特方案在 coding/reasoning/agent workflow 上做小样本验证，不能把量化当免费容量收益。
11. **瓶颈归因**：失败必须能归因到 HBM、DRAM、PCIe/UB、SSD、CPU host、NPU kernel 或调度。

只有这些验证通过后，才能把相应 L0/L1a/L1b/L2 结论写进项目材料；其中 128K/1M 仍只作为风险边界，不作为本文验收目标。

## 14. 与同事外部参考文档的差异说明

`同事提供的外部参考文档` 下两份 Word 文档给出的数字看起来比本文某些结论“低”或“乐观”，主要原因不是公式互相矛盾，而是 **档位口径不同**。同事文档实际采用的是“热专家大比例常驻 HBM + 批次内复用 + 高带宽冷专家预取”的吞吐型规划，而不是本文 L0/L1a/L1b 的“最低加载与低速生成”口径。

### 14.1 同事文档的关键假设

| 项目 | 普通 FP4/FP8 混合量化文档 | 极致 4-2bit 混合量化文档 | 对本文的影响 |
|---|---:|---:|---|
| GLM-5.2 压缩权重总量 | 约 428 GB | 约 316 GB | 极致 2-bit 会显著降低 cold expert 容量，但精度和 kernel 风险更高 |
| 公共/非路由参数 | 约 19.2B，8.4 bit，约 20.2 GB | 同左 | 与本文非 routed / shared 热部件量级接近 |
| 热专家比例 | 35% | 35% | 这是最大差异之一：35% routed experts 常驻 HBM 本身就需要约 142.7 GB expert 权重 |
| GLM-5.2 热专家常驻权重 | 约 142.7 GB | 约 142.7 GB | 仅热专家 + 公共层就约 163 GB，已经超过 L1a/L1b 的 64-96 GB HBM |
| GLM-5.2 冷专家存储 | 约 265 GB，4.5 bit | 约 153 GB，2.6 bit | 2-bit 文档降低的是 cold expert 存储/传输体积，不等于原生 2-bit 计算 |
| 冷热分层 HBM 预算 | 300-423 GB | 300-423 GB | 这对应高配上探或多卡边界，不对应 L0/L1a/L1b 最低加载 |
| 冷专家推荐卸载带宽 | 223 GB/s | 129 GB/s | 显著高于 L1a/L1b 的 4TB NVMe 起步口径，也高于单 PCIe x16 的保守有效带宽 |
| 复用假设 | reuse = 8x，目标 8x-16x | 同左 | 这是吞吐型/batch 口径，不是 batch=1 单用户 decode 口径 |
| 吞吐假设 | 1000 tok/s | 1000 tok/s | 更像系统聚合吞吐或白板容量规划目标，不是 L0-L2 单请求实测 token/s |
| 部署建议 | GLM-5.2 4xH100 需冷热分层，4xH200 全驻留可用，8xH100/H200 稳定生产 | GLM-5.2 2xH200 必须冷专家卸载，4xH200 全驻留可用，8xH100/H200 稳定生产 | 同事文档默认已经越过“单卡 64-96GB HBM 最低加载” |

### 14.2 为什么本文 L0-L1b 性能估计低得多

本文 L0-L1b 估算低，主要因为它故意采用最苛刻的单卡最低加载口径：

1. **L1a/L1b HBM 只有 64-96 GB，而同事文档冷热分层 HBM 预算是 300-423 GB。**  同事文档里 GLM-5.2 仅“公共层 + 35% 热专家”就约 163 GB，还没算 KV、workspace、prefetch buffer 和碎片。因此这个方案天然不是 L1a/L1b，而更接近高配上探或多卡边界的热专家规划。
2. **同事文档假设 `reuse=8x`，本文 L0-L2 按单用户 batch=1 decode 估算。**  reuse=8x 会把冷专家卸载带宽和 HBM 有效读带宽摊薄 8 倍；如果没有连续 batching 或多请求共享 expert hot set，这个复用不能直接用于单用户 token/s。
3. **同事文档的冷专家带宽需求远高于 L1a/L1b 硬件。**  普通 FP4 文档给 GLM-5.2 冷专家推荐卸载带宽约 223 GB/s，极致 2-bit 文档约 129 GB/s。L1a/L1b 只有 4TB NVMe 起步、单 PCIe x16 有效传输也只有几十 GB/s 量级。因此如果照同事的 miss/reuse 假设运行，需要的不是本文 L1a/L1b 的 SSD cold tier，而是 CXL/UB/HCCS/NVLink/RDMA/direct I/O 级别的数据面。
4. **同事文档更偏“容量白板推导”，本文 L0-L2 更偏“token critical path”。**  同事文档的公式重点是 `压缩权重总量`、`HBM预算`、`1000 tok/s 下的冷专家带宽`。本文则直接问每个 token 如果 miss 到 PCIe/SSD，会增加多少 ms/token，因此会更悲观，尤其对 P95/P99 和秒级 stall 更敏感。
5. **2-bit cold expert 只降低存储/传输，不自动降低计算时间。**  同事极致文档也写明：2-bit 是存储/传输压缩，不等于 GPU 原生 2-bit 计算。如果运行时需要解码到 FP8/INT8/FP16 再计算，token critical path 仍要付出解码、搬运、kernel 同步和调度成本。

### 14.3 如何把两套估算对齐

如果按同事文档口径，应把本文档位重新映射如下：

| 同事文档口径 | 更接近本文哪个位置 | 原因 |
|---|---|---|
| GLM-5.2 冷热分层 HBM 300-423 GB | 高配上探 / 多卡生产边界 | 需要远超 L1a/L1b 的 HBM，且冷专家带宽要到 129-223 GB/s |
| GLM-5.2 2xH200 必须冷专家卸载 | 多卡技术验证，不是 L0-L2 主线 | 2xH200 已有 282 GB HBM，仍低于同事冷热分层 300-423 GB 下沿 |
| GLM-5.2 4xH200 全驻留可用 | 多卡生产前验证 | HBM 约 564 GB，接近同事全权重驻留 433-536 GB 预算 |
| `1000 tok/s @ reuse=8x` | 吞吐型系统目标 | 不能等同于单用户 decode token/s |
| `hot_ratio=35%, miss_rate=10%` | 需要真实 routing trace 验证 | 本文不在 L0-L2 默认采用这个命中率 |

因此，本文不应该简单把同事文档的 300-423 GB HBM 或 1000 tok/s 塞进 L0-L2。更合理的合并方式是：

- **保留 L0/L1a/L1b**：定义为现有样机极限分层、SSD-offload 极限加载和 DRAM-warm 保守加载，性能按 L1a `0.05-0.5 tok/s 常见 / 0.5-1.5 tok/s warm`、L1b `0.5-2 tok/s 较现实 / 2-5 tok/s 优化目标` 估。
- **把同事文档作为高配上探/多卡边界参考**：`35% hot experts`、`reuse=8x`、`miss_rate=10%`、`129-223 GB/s cold expert bandwidth` 可以作为未来仿真输入或多卡规划输入，不是本文主线。
- **补充一个“同事乐观口径”情景**：如果未来硬件能提供 300-423 GB HBM、>=129 GB/s 冷专家带宽、稳定 8x expert reuse，并且 2-bit/FP4 质量可接受，则 GLM-5.2 单卡/单模块的硬件压力会显著下降；但这已经不是当前向下压榨硬件的目标。

一句话总结：**同事的数字不是真正的 L0/L1a/L1b 最低加载数字，而是把 hot expert 常驻、batch 复用和高带宽冷层都先假设成立后的吞吐型规划数字；本文按单用户、低 HBM、低冷层带宽、token critical path 口径算，因此结论更保守。**

## 15. 参考资料

- Z.ai GLM-5 GitHub: https://github.com/zai-org/GLM-5
- Hugging Face GLM-5.2 config.json: https://huggingface.co/zai-org/GLM-5.2/blob/main/config.json
- vLLM GLM-5.2 recipe: https://recipes.vllm.ai/zai-org/GLM-5.2
- 本地报告：`AK 协同/模型推理估计/GLM-5.2 架构与推理资源深度研究报告.md`
- 本地精读：`AK 协同/代表工作原文硬件拓扑映射精读笔记.md`
- 本地反向回顾：`AK 协同/Deep Research 反向回顾报告 第三轮可核验版 小算力大模型推理落地与推理仿真系统构建.md`
- 同事外部参考：`AK 协同/同事提供的外部参考文档/GLM推理硬件需求推导_普通FP4_FP8混合量化.docx`
- 同事外部参考：`AK 协同/同事提供的外部参考文档/GLM推理硬件需求推导_极致4_2bit量化.docx`
- NEO: `AK 协同/references/papers/NEO__arxiv-2411.01142.pdf`
- KTransformers: `AK 协同/references/papers/KTransformers.pdf`
- FlexInfer: `AK 协同/references/papers/FlexInfer.pdf`
- DALI: `AK 协同/references/papers/DALI__arxiv-2602.03495.pdf`
- FluxMoE: `AK 协同/references/papers/FluxMoE__arxiv-2604.02715v2.pdf`
- Mooncake: `AK 协同/references/papers/Mooncake__arxiv-2407.00079.pdf`
- LMCache: `AK 协同/references/papers/LMCache__arxiv-2510.09665.pdf`
- Tutti: `AK 协同/references/papers/Tutti__arxiv-2605.03375.pdf`
- SolidAttention: `AK 协同/references/papers/SolidAttention-FAST26.pdf`
- Bidaw: `AK 协同/references/papers/Bidaw-FAST26.pdf`
- CacheSlide: `AK 协同/references/papers/CacheSlide.pdf`
- ServeGen: `AK 协同/references/papers/ServeGen-NSDI26.pdf`
- LLMServingSim2.0: `AK 协同/references/papers/LLMServingSim-2.0__arxiv-2602.23036.pdf` 和 `AK 协同/references/papers/LLMServingSim-2.0__arxiv-2511.07229.pdf`
- vLLM-Ascend KV Cache CPU Offload 快照：`AK 协同/references/web/vLLM-Ascend-KV-CPU-offload-live.html`
- vLLM-Ascend UCM 快照：`AK 协同/references/web/vLLM-Ascend-UCM-deployment-live.html`
- vLLM-Ascend KV Pool 快照：`AK 协同/references/web/vLLM-Ascend-KV-pool-live.html`

扩展方向来源，用于补齐反向回顾报告中的非三类主线：

- llm.npu: `AK 协同/references/papers/llm.npu__arxiv-2407.05858.pdf`
- HeteroInfer: `AK 协同/references/papers/HeteroInfer__arxiv-2501.14794.pdf`、`AK 协同/references/papers/HeteroInfer-SOSP-PDF.pdf`
- FineMoE: `AK 协同/references/papers/fMoE-FineMoE__arxiv-2502.05370.pdf`
- HybriMoE: `AK 协同/references/papers/HybriMoE__arxiv-2501.04595.pdf`
- MoE-APEX: `AK 协同/references/papers/MoE-APEX.pdf`
- KVCache in the Wild: `AK 协同/references/papers/KVCache-in-the-Wild__arxiv-2503.01526.pdf`
- ITME / CXL tier: `AK 协同/references/papers/ITME__arxiv-2606.12556.pdf`
- Chakra: `AK 协同/references/papers/Chakra-MLSys2026__arxiv-2605.11333.pdf`、`AK 协同/references/papers/Chakra-original__arxiv-2305.14516.pdf`
- CCL-Bench: `AK 协同/references/papers/CCL-Bench__arxiv-2605.06544.pdf`
- ECHO: `AK 协同/references/web/ECHO-OSDI26-page.html`
- TensorRT-LLM Disaggregated Serving / KV exchange: `AK 协同/references/web/TensorRT-LLM-disaggregated-docs.html`、`AK 协同/references/web/TensorRT-LLM-KV-exchange.html`
- NVIDIA Dynamo / NIXL: `AK 协同/references/web/NVIDIA-Dynamo-KV-offloading-live.html`、`AK 协同/references/web/NVIDIA-Dynamo-introduction-live.html`、`AK 协同/references/web/NIXL-GitHub.html`
- MindIE / Ascend serving docs: `AK 协同/references/web/MindIE-docs.html`、`AK 协同/references/web/Ascend-MindIE.html`
