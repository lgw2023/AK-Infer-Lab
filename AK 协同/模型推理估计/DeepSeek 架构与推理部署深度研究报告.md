# DeepSeek 架构与推理部署深度研究报告

## 摘要

- DeepSeek-V3 与 DeepSeek-R1 的**骨干架构相同**；DeepSeek 官方明确说明 R1 / R1-Zero 基于 DeepSeek-V3-Base 训练，vLLM 官方文档也直接把 V3 与 R1 视为同一架构处理。citeturn34view1turn32view2
- DeepSeek-V3 的公开主配置为：**671B 总参数、37B 激活参数、61 层、hidden size 7168、128 个 attention heads、256 routed experts、每 token 激活 8 个 routed experts + 1 个 shared expert、native FP8 权重**。这些数字可以同时从技术报告与 Hugging Face `config.json` 交叉验证。citeturn28view1turn43view0
- DeepSeek-V2 / Coder-V2-236B 属于同一 **V2 架构族**：公开资料显示其为 **236B 总参数、21B 激活参数**，并采用 MLA + DeepSeekMoE；Coder-V2 官方 README 也明确它是从 DeepSeek-V2 中间 checkpoint 继续预训练得到。citeturn35search5turn34view2turn42view4
- DeepSeek 的推理侧关键创新是 **MLA 多头潜空间注意力**。论文给出的结论是：V2 相比 DeepSeek 67B，**KV cache 减少 93.3%**，且最大生成吞吐提升到 **5.76×**；从 MLA 公式与 V3 配置继续推导，V3 每层每 token 只需缓存 `kv_lora_rank + qk_rope_head_dim = 512 + 64 = 576` 个元素。citeturn35search5turn12view1turn43view0
- 若按 V3 配置估算，**单请求、128K 上下文、BF16 KV cache** 约需 `61 × 128000 × 576 × 2 ≈ 8.99 GB`；若用 FP8 / INT8 KV cache，则约 **4.50 GB**。这说明在 DeepSeek 上，**长上下文的主瓶颈从“是否能缓存”部分转移到了“批量并发下 KV 累积”与“MoE 通信”**。citeturn12view1turn43view0
- V3 的 MoE 层并非全部稀疏：论文与配置都显示 **前 3 层仍是 dense FFN**，后续层换成 MoE。citeturn28view1turn43view0
- V3 的路由与 V2 不同：V2 公开配置/论文对应的是 **softmax + group-limited greedy** 路由；V3 技术报告说明其改为 **sigmoid gating**，并引入 **auxiliary-loss-free** 负载均衡；V3 配置里可见 `scoring_func: "sigmoid"` 与 `topk_method: "noaux_tc"`。citeturn29view1turn42view4turn30view0turn30view2turn43view2
- DeepSeek-R1-Distill 系列**不是 MoE DeepSeek 骨干缩小版**，而是基于 **Qwen2.5 与 Llama 3.x** 的 dense 模型再蒸馏。官方列出的公开版本是 1.5B、7B、8B、14B、32B、70B。citeturn34view1
- 目前对 DeepSeek 大模型支持最成熟的主流推理栈，是 **SGLang、vLLM、TensorRT-LLM**。SGLang 文档直接写明其是官方 DeepSeek 团队日零日推荐的引擎；vLLM 和 TensorRT-LLM 均提供了针对 V3/R1 的专项指南。citeturn37search16turn32view2turn13search18
- **SGLang** 对 DeepSeek 的专项优化最集中，包括：专家并行、DeepEP / DeepGEMM、PD disaggregation、HiCache、Reasoning parser、AMD GPU 支持，以及对预量化的 DeepSeek V3/R1 FP8 模型开箱即用。citeturn14search3turn14search5turn14search12turn14search17turn14search8
- **vLLM** 已提供 DeepSeek-V3/R1 原生使用指南，并支持 EP、DP/TP、自动前缀缓存、推测解码等；文档还给出了 **8×H200 FP8** 和 **4×B200 FP4** 的官方推荐部署路径。citeturn32view2turn15search0turn15search1turn15search2
- **TensorRT-LLM** 已将 DeepSeek-R1/V3 纳入支持矩阵，并明确支持 KV cache reuse、MTP（当前文档写明“仅 DeepSeek 支持”）、以及 DeepSeek-R1 在 H200 / B200 上的专项性能调优。citeturn16search11turn16search2turn16search5turn32view1
- 对 **TGI** 而言，官方支持页已明确列出 **Deepseek V2 / V3**，并支持 continuous batching、tensor parallel、paged attention、prefix caching、FlashInfer/FlashDecoding、AWQ/GPTQ/FP8 等；但官方支持页**没有单独列出 R1**，因此对 R1 应判为“同架构可望支持，但专项验证不如 vLLM / SGLang / TRT-LLM 完整”。citeturn20search0turn20search1turn20search2turn20search3
- 对 **llama.cpp / Ollama / KTransformers** 这类“本地 / 混合式”方案，现阶段更适合 **Distill 模型**、**INT4 / GGUF** 或 **CPU/GPU hybrid**。KTransformers 官方明确宣称已经支持 R1/V3 在 **24GB VRAM + 382GB DRAM** 级别混合部署；Ollama 模型库则公开列出了从 1.5B 到 671B 的 DeepSeek-R1 标签。citeturn18search5turn18search12turn17search5turn39search0
- 硬件上，**8×H200** 与 **8×MI300X** 是当前公开资料里最稳妥的单机 V3/R1 FP8 部署平台；AMD 官方博客明确表示：**671B DeepSeek-R1 FP8 无法装入 8×H100 单机**。citeturn32view0turn21search1turn22search3
- 若只看原始权重容量，V3/R1 **FP8 原始权重约 671 GB**，BF16/FP16 约 **1.342 TB**，INT4 约 **335.5 GB**；因此 “能不能跑” 首先由**总显存容量**决定，而不是先由算力决定。这个结论对 671B 级 MoE 比对 70B dense 更突出。计算依据来自官方参数量与基础显存公式。citeturn28view1turn43view0
- 对在线服务来说，DeepSeek 的瓶颈通常不是单一模块，而是**Prefill 计算、Decode 权重流式读取、MoE all-to-all / expert dispatch、KV cache 增长、跨节点互联**共同决定。SGLang 文档明确将 prefill 描述为 computation-intensive、decode 描述为 memory-intensive；V3 论文则展示了解码阶段的大规模 EP / TP / DP 组合与冗余专家部署。citeturn14search5turn28view2
- 本报告中**最可靠**的信息来自：DeepSeek 论文 / 官方 repo / HF config / 官方框架文档 / GPU 厂商规格页。**最不确定**的信息主要是：V2.5 的精确内部层级参数、部分框架对 R1 的“是否真正原生 MLA 优化”、以及非官方硬件组合上的 tokens/s。citeturn35search3turn43view0turn32view2turn21search0turn22search3

## 资料来源与方法

本报告优先检索并交叉验证了四类资料：DeepSeek 官方论文与 GitHub / Hugging Face 页面；主流推理框架官方文档；NVIDIA / AMD / Apple / Intel / AMD CPU 官方规格页；以及少量用于补足工程语义的官方 issue / benchmark 说明。核心模型侧来源包括 DeepSeek-V2 论文、DeepSeek-V3 论文、DeepSeek-R1 官方仓库、DeepSeek-Coder-V2 官方 README、以及 Hugging Face 上公开的 `config.json` / 模型卡。citeturn10view0turn10view1turn34view1turn34view2turn43view0turn42view4

检索时重点使用了 “DeepSeek V3 technical report architecture / DeepSeek MLA / DeepSeek V3 config.json / DeepSeek R1 vLLM / DeepSeek TensorRT-LLM / DeepSeek SGLang / DeepSeek KV cache MLA / DeepSeek H100 H200 MI300X inference”等中英文关键词，并且尽量要求同一数字至少能由**论文 + 配置文件**或**框架指南 + 硬件规格页**两种来源互相约束。对于无法双重验证的数字，我在正文中会标记为“公开资料未披露”或“只能估算”。citeturn28view1turn43view0turn32view2turn32view1turn21search1turn22search3

处理冲突信息时，本报告遵循三个优先级：**论文 / 官方 config > 官方框架文档 > 社区 issue / benchmark**。例如，V3/R1 的核心架构以论文和官方 `config.json` 为准；而框架是否支持某功能，则以该框架自己的支持矩阵、使用指南或功能文档为准；社区 issue 仅用于说明已知限制与稳定性问题，不作为主结论来源。报告时间基准为 2026-07-01。citeturn10view1turn43view0turn16search11turn37search16turn18search5turn38search0

## DeepSeek 模型架构总览

下表只列出**公开资料足以支撑工程推理分析**的模型。对 V2.5 与 Distill 系列，我保留了“公开资料未单列”的字段，不强行补造。

| Model | 发布时间 | 类型 | 总参数 | 激活参数 | 层数 | Hidden Size | Attention | Experts | 每 token 激活 | Context | Vocab | 公开精度 / 备注 | 主要来源 | 置信度 |
|---|---:|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---|---|
| DeepSeek-V2 | 2024-05 | MoE | 236B | 21B | 公开论文未直接在摘要单列；V2 家族公开 config 对应 60 层 | V2 家族公开 config 对应 5120 | MLA | 2 shared + 160 routed | 6 routed | 128K 级扩展，HF / config 为 163,840 max positions | V2 家族公开 config 对应 102,400 | BF16 发布；推理常见 FP8 / INT4 需后处理 | citeturn35search5turn29view1turn42view4 | 中高 |
| DeepSeek-V2.5 | 2024-09 API 升级 | 合并版通用+代码模型 | 官方未单列；通常视作 V2/Coder-V2 236B 家族 | 官方未单列 | 公开资料未披露 | 公开资料未披露 | 延续 V2 族 MLA + DeepSeekMoE 的概率高，但官方未单列 config 说明 | 公开资料未单列 | 公开资料未单列 | 官方未单列 | 官方未单列 | 是 V2 Chat 与 Coder-V2 的合并升级 | citeturn35search3turn35search12 | 中低 |
| DeepSeek-Coder-V2 | 2024-07 | Code MoE | 236B / 16B | 21B / 2.4B | 236B 版公开 config 为 60 层 | 236B 版公开 config 为 5120 | MLA | 236B：2 shared + 160 routed | 6 routed | 128K | 102,400 | 从 DeepSeek-V2 中间 checkpoint 继续预训练 | citeturn34view2turn42view4turn42view7 | 高 |
| DeepSeek-V3 | 2024-12 | MoE | 671B | 37B | 61 | 7168 | MLA | 1 shared + 256 routed | 8 routed | 163,840 max positions；论文正文按 128K 训练/评测段落描述 | 129,280 | 官方权重为 FP8 block-quantized；`num_nextn_predict_layers=1` | citeturn28view1turn43view0 | 高 |
| DeepSeek-R1 | 2025-01 | Reasoning MoE | 671B | 37B | 与 V3 相同 | 与 V3 相同 | 与 V3 相同 | 与 V3 相同 | 与 V3 相同 | 128K | 与 V3 相同 | 基于 V3-Base 做 RL / SFT / reasoning 流程 | citeturn34view1turn32view2 | 高 |
| DeepSeek-R1-Zero | 2025-01 | Reasoning MoE | 671B | 37B | 与 V3 相同 | 与 V3 相同 | 与 V3 相同 | 与 V3 相同 | 与 V3 相同 | 128K | 与 V3 相同 | 直接 RL，无冷启动 SFT | citeturn34view1 | 高 |
| DeepSeek-R1-Distill-Qwen / Llama 系列 | 2025-01 | Dense Distill | 1.5B / 7B / 8B / 14B / 32B / 70B | 与总参数基本一致 | 跟随各自底模 | 跟随各自底模 | 标准 dense transformer | 无 MoE | 无 | 跟随各自底模；官方仓库仅给出家族信息 | 跟随各自底模 | 基于 Qwen2.5 / Llama 3.x；官方说明“稍改 config 和 tokenizer” | citeturn34view1 | 高 |

### 重点结论

对于工程推理部署，**真正最值得分析的核心对象是两条线**：一条是 **V2 / Coder-V2 236B**，另一条是 **V3 / R1 671B**。原因很直接：这两条线都公开了足够细的论文与配置，而且它们代表了 DeepSeek 在 MLA、DeepSeekMoE、路由、FP8 与 MTP 上的两个主要代际。V2.5 很重要，但从公开资料看，它更像**产品整合版**，不是一套完整单独披露的新架构。citeturn35search5turn34view2turn35search3turn28view1turn43view0

更具体地看，V2 家族的公开 config 显示：`hidden_size=5120`、`intermediate_size=12288`、`kv_lora_rank=512`、`n_routed_experts=160`、`n_shared_experts=2`、`num_experts_per_tok=6`、`num_hidden_layers=60`、`vocab_size=102400`；而 V3 则提升到 `hidden_size=7168`、`intermediate_size=18432`、`n_routed_experts=256`、`n_shared_experts=1`、`num_experts_per_tok=8`、`num_hidden_layers=61`、`vocab_size=129280`，并改用 `scoring_func: "sigmoid"` 与 `topk_method: "noaux_tc"`。citeturn42view4turn42view7turn43view0

## 重点模型深拆

### DeepSeek-V3 与 DeepSeek-R1

V3 的公开骨干由三部分定义：**MLA、DeepSeekMoE、MTP**。技术报告写明：V3 继续沿用 V2 验证过的 MLA 与 DeepSeekMoE，并新增 auxiliary-loss-free load balancing 与 multi-token prediction 目标；配置文件进一步确认 `num_nextn_predict_layers = 1`，说明其多 token 预测深度为 1。R1 则不是新骨干，而是在 V3-Base 上做 reasoning 流程的后训练。citeturn35search8turn28view1turn43view0turn34view1

按公开 config，V3 的关键结构参数如下：`hidden_size=7168`、`num_attention_heads=128`、`q_lora_rank=1536`、`kv_lora_rank=512`、`qk_nope_head_dim=128`、`qk_rope_head_dim=64`、`v_head_dim=128`、`n_routed_experts=256`、`n_shared_experts=1`、`num_experts_per_tok=8`、`first_k_dense_replace=3`、`topk_group=4`、`n_group=8`、`max_position_embeddings=163840`、`vocab_size=129280`。论文正文与 config 在总参数量、激活参数量、前 3 层 dense FFN、专家数、激活专家数上是一致的。citeturn43view0turn28view1

V3 的 MLA 里，KV 路径的核心不是显式缓存完整 K/V，而是先把输入 `h_t ∈ R^7168` 压到 `c_t^KV ∈ R^512`，再配合一个 decoupled RoPE key `k_t^R ∈ R^64` 完成注意力；论文明说，**推理时仅需缓存 `d_c + d_h^R` 个元素**，也就是对 V3 而言每层每 token 只要缓存 `512 + 64 = 576` 个元素。对应地，查询路径还会先压到 `c_t^Q ∈ R^1536`，再恢复成每个头的 `q_nope` 与 `q_rope`。citeturn12view1turn43view0

如果把这些参数写成工程上更直观的矩阵尺寸，V3 单层 MLA 的主要权重大致可表示成：`W_DQ: 7168×1536`，`W_UQ: 1536×(128×(128+64)) = 1536×24576`，`W_DKV: 7168×512`，`W_UK: 512×(128×128) = 512×16384`，`W_KR: 7168×64`，`W_UV: 512×(128×128)=512×16384`，`W_O: (128×128)×7168 = 16384×7168`。这是按论文 MLA 公式与官方 config 直接推出来的近似参数拆解。citeturn12view1turn43view0

MoE 部分，V3 每个 expert 的中间维度是 2048。若按标准无 bias 的 SwiGLU / gated-FFN 近似，单 expert 约有 `3 × 7168 × 2048 ≈ 44.0M` 参数；因此单层 256 个 routed experts 总参数约 `11.27B`，再加 1 个 shared expert 再增约 `44M`。但**每个 token 并不会激活整层全部专家**，而是只激活 8 个 routed experts，再加上 shared expert 路径，因此单层“被激活”的 expert 参数规模约为 `(8+1) × 44.0M ≈ 396M`。这正是 DeepSeek 这类大 MoE “总参数巨大、激活参数可控”的本质。citeturn28view1turn43view0

路由机制方面，V3 技术报告明确写到：V3 相比 V2 改用 **sigmoid** 做 affinity / gating，并引入**无辅助损失的负载均衡**；做法是给每个 expert 一个 bias，只在 top-k 路由判定时加入，而乘到专家输出上的 gate 仍来自原始 affinity。配置文件中的 `scoring_func: "sigmoid"`、`topk_method: "noaux_tc"` 提供了与论文一致的实现侧证据。citeturn30view0turn30view2turn43view2

R1 与 V3 的**推理图几乎一样**。差异主要在后训练目标、采样模板、reasoning token 行为以及框架侧是否单独解析 `<think>` / reasoning 段。SGLang、LMDeploy、Ollama 都已经提供了 reasoning parser / thinking API 语义支持，但这不改变底层注意力、MoE、KV cache 公式。citeturn34view1turn14search8turn17search3turn39search0

### DeepSeek-V2 与 DeepSeek-Coder-V2

V2 论文给出：DeepSeek-V2 是 **236B 总参数、21B 激活参数** 的 MoE 模型，采用 MLA 与 DeepSeekMoE；MoE 侧是 **2 个 shared experts + 160 routed experts**，每 token 激活 **6 个 routed experts**，并且**除第 1 层外其余 FFN 都替换为 MoE**。citeturn35search5turn29view1turn29view3

虽然 DeepSeek-V2 的通用版 `config.json` 在本次检索中没有直接展开，但 DeepSeek-Coder-V2 官方 README 明确写到它是从 DeepSeek-V2 的中间 checkpoint 继续训练而来；而其 236B 版公开 config 显示 `hidden_size=5120`、`intermediate_size=12288`、`kv_lora_rank=512`、`q_lora_rank=1536`、`n_routed_experts=160`、`n_shared_experts=2`、`num_experts_per_tok=6`、`num_hidden_layers=60`、`vocab_size=102400`。因此，把这些数视为 **V2 / Coder-V2 236B 这一骨架族**的公开工程参数，是合理且可复核的。citeturn34view2turn42view4turn42view7

V2 路由与 V3 也有清晰差异。公开 config 显示 V2 家族采用 `scoring_func: "softmax"`、`topk_method: "group_limited_greedy"`、`topk_group: 3`、`n_group: 8`；而论文同时强调 device-limited routing，把每个 token 发往的设备数限制在最多 3 个，以控制 expert parallel 带来的通信成本。citeturn42view4turn42view7turn29view1

从部署角度，这条线的重要性在于：**236B 级 V2/Coder-V2 是目前最现实的“中大型 DeepSeek MoE”生产落点**。它在 4×80GB 或 2×H200 一类机器上就能做 FP8 / INT4 级别部署，而 V3 / R1 671B 则很快把你推到 8×H200 / 8×MI300X 或多节点。citeturn21search1turn25search6turn22search3

## 推理路径拆解

下面以 **DeepSeek-V3 / R1** 为主线，按“单 batch / continuous batching 都成立”的方式拆开从 token input 到 token output 的路径。除非特别说明，张量形状写成 `B=批大小，S=当前序列长度，d=7168`。所有维度都来自论文公式与官方 config。citeturn12view1turn43view0

**文本到 token IDs**：输入文本先经 tokenizer 转成 `input_ids ∈ [B, S]`。V3 config 给出的 `vocab_size=129280`，因此 token id 范围属于 `[0, 129279]`；V2 家族公开 config 则是 `102400`。这一步本身几乎不耗 GPU FLOPs，但在服务端会影响 prefix match、continuous batching 拼批、以及 stop sequence 判定。citeturn43view0turn42view7

**Embedding lookup**：查表得到 `X_0 ∈ R^{B×S×7168}`。若不 tying embedding，则 token embedding 与 LM head 是两套权重；V3 / V2 家族公开 config 都是 `tie_word_embeddings: false`。因此仅 embedding 本身的参数量就分别是 `129280×7168 ≈ 926.7M` 与 `102400×5120 = 524.3M`。这一步偏 memory-bound，因为主要是查表而不是大矩阵乘。citeturn43view0turn42view7

**进入每层 Transformer block**：V3 共有 61 层，每层先做 RMSNorm，再做 MLA，再残差；再做 RMSNorm，接 FFN / MoE，再残差。V2 家族则是 60 层、同样的 pre-norm 风格。Norm 的参数量相对极小，主要是每层一个长度为 hidden size 的缩放向量，因此它几乎不会成为显存主项，但会影响 kernel fusion 与 launch 开销。citeturn43view0turn42view4

**MLA 查询路径**：给定某层输入 `H ∈ R^{B×S×7168}`，先经查询压缩得到 `C^Q ∈ R^{B×S×1536}`，然后再恢复成 `Q_nope ∈ R^{B×S×128×128}` 与 `Q_rope ∈ R^{B×S×128×64}`。因为 V3 的 `num_attention_heads=128`、`qk_nope_head_dim=128`、`qk_rope_head_dim=64`，所以每个 token 的查询总维度是 `128×(128+64)=24576`。这一步主要由两次 GEMM 决定：`7168×1536` 与 `1536×24576`，在 prefill 中通常是 compute-bound。citeturn12view1turn43view0

**MLA KV 路径与 KV cache 写入**：同层里，输入还会先压到 `C^KV ∈ R^{B×S×512}`，再生成一个共享的 RoPE key `K^R ∈ R^{B×S×64}`；论文明确指出，推理时只缓存这两部分，因此每层每 token 的 cache 元素数是 `512+64=576`，不是标准 MHA 的 `2×n_kv_heads×d_head`。对 V3 而言，这意味着单请求 128K 上下文的 BF16 KV cache 约为 `61×128000×576×2 ≈ 8.99GB`；若 batch=8，则直接增长到约 **71.9GB**。citeturn12view1turn43view0

**Prefill 与 Decode 的差异**：Prefill 要处理整个 `[B,S]` 张量，因此 attention score / value aggregation 里会出现 `O(S^2)` 项；Decode 则是每次只生成一个新 token，本层只需要计算 `q_t`，再对历史缓存做 `O(S)` 的读取与打分。SGLang 文档也明确把 prefill 称作 computation-intensive，把 decode 称作 memory-intensive。对 DeepSeek 来说，decode 还叠加了专家选择与跨卡专家调度，因此在小 batch 低延迟场景下尤其容易被 HBM / interconnect 卡住。citeturn14search5turn12view1turn28view2

**MoE router 与 expert selection**：V3 在前 3 层之后进入 MoE 层。输入 `U ∈ R^{B×S×7168}` 先经过 gate / router，得到对 256 个 routed experts 的分数，然后依据 `topk_group=4`、`num_experts_per_tok=8` 等规则选出 routed experts；shared expert 路径始终存在。路由后的 token 需要被分发到本地或远端专家，各专家再做自己的 gated-FFN GEMM。专家分发阶段在单机 NVLink 环境下通常还能控制，但一到多节点就会显著变成 all-to-all / dispatch-combine 瓶颈。citeturn28view1turn30view2turn43view0

**Expert FFN GEMM**：以 V3 为例，单个 expert 大致对应 `W_gate: 7168×2048`、`W_up: 7168×2048`、`W_down: 2048×7168` 三个主矩阵，约 `44.0M` 参数。被激活的 8 个 routed experts 加 1 个 shared expert，等效于本层每 token 触发约 `396M` expert 参数。由于 MoE 是稀疏激活，这部分在 batch 做大以后可以被 grouped GEMM 很好吃满算力；但在低并发推理下，dispatch / combine 与小批量专家 GEMM 反而会拉低效率。citeturn28view1turn43view0

**通信路径**：论文公开了 V3 在线部署的一些关键策略：prefill 阶段会加冗余专家并重叠 attention / MoE 与 dispatch / combine；decode 阶段则把 shared expert 视作 routed expert 来看待，并在一个最小 40 节点、320 GPU 的单元里采用 attention TP4 + DP80、MoE EP320。这说明对 671B DeepSeek 来说，**专家并行通信已经不是次要问题，而是一级性能问题**。citeturn28view2

**LM head、sampling 与 streaming**：最后一层输出经 RMSNorm 后投到 `LM Head ∈ R^{7168×129280}`，得到 logits；再做 greedy / temperature / top-k / top-p 等采样。大多数服务框架都支持 token streaming；TGI、Ollama、vLLM 等都把流式输出作为标准用法。因为 `tie_word_embeddings=false`，LM head 不是和输入 embedding 共用权重，所以它是一个真实的大矩阵乘。citeturn43view0turn20search1turn39search1

## 参数、矩阵与 KV cache 公式

### 参数量公式

对任何 dense decoder-only block，最基础的参数量公式都可以写成：

```text
Embedding params = vocab_size × hidden_size
LM head params   = hidden_size × vocab_size
RMSNorm params   ≈ O(hidden_size)
```

对标准 gated-FFN / SwiGLU，若忽略 bias，单层 FFN 近似参数量可写成：

```text
FFN params ≈ 3 × d × d_ff
```

这个式子可以直接用于 DeepSeek 的 dense FFN，也能用于每个 MoE expert。citeturn43view0turn42view4

对 DeepSeek 的 MLA，按论文公式和公开 config，可复用的近似拆解是：

```text
W_DQ   : d × d_c^Q
W_UQ   : d_c^Q × [n_h × (d_nope + d_rope)]
W_DKV  : d × d_c^KV
W_UK   : d_c^KV × [n_h × d_nope]
W_KR   : d × d_rope
W_UV   : d_c^KV × [n_h × d_v]
W_O    : [n_h × d_v] × d
```

因此：

```text
MLA params
≈ d·d_c^Q
+ d_c^Q·n_h·(d_nope + d_rope)
+ d·d_c^KV
+ d_c^KV·n_h·d_nope
+ d·d_rope
+ d_c^KV·n_h·d_v
+ n_h·d_v·d
```

带入 V3 公布参数后，单层 MLA 主参数量约是 **187M** 量级；带入 V2 家族 236B 配置，则是 **149M** 量级。这两个量级和官方总激活参数量是相容的。citeturn12view1turn43view0turn42view4

对 MoE：

```text
Router params        ≈ d × N_routed
Single expert params ≈ 3 × d × d_expert
Shared expert params ≈ N_shared × 3 × d × d_expert
Routed expert params ≈ N_routed × 3 × d × d_expert
MoE layer total
≈ d×N_routed + (N_shared + N_routed) × 3×d×d_expert

MoE layer activated
≈ d×N_routed + (N_shared + K_active) × 3×d×d_expert
```

用这个公式估算，V3 单 expert 约 **44.0M** 参数，V2 236B 单 expert 约 **23.6M** 参数。citeturn43view0turn42view4

### KV cache 公式

标准注意力的 cache 元素数，一般可以写成：

```text
MHA / GQA / MQA:
KV_elems_per_token_per_layer = 2 × n_kv_heads × d_head
KV_memory = batch × seq × layers × 2 × n_kv_heads × d_head × bytes
```

其中，MHA 是 `n_kv_heads = n_heads`，GQA 是 `n_kv_heads < n_heads`，MQA 则相当于 `n_kv_heads = 1`。citeturn16search6

DeepSeek MLA 的关键区别是：

```text
MLA:
KV_elems_per_token_per_layer = d_c^KV + d_rope
KV_memory = batch × seq × layers × (d_c^KV + d_rope) × bytes
```

论文明确说明推理时缓存的是压缩的 KV latent 与 decoupled RoPE key；因此，对 V3 / R1 和 V2 236B 而言，这个式子都可化成 `(512 + 64)`。citeturn12view1turn29view1turn43view0turn42view4

以 **V3 / R1** 为例：

```text
Per-layer KV elems/token = 512 + 64 = 576
All-layer KV elems/token = 61 × 576 = 35,136
BF16 bytes/token         = 70,272  ≈ 68.6 KiB
FP8  bytes/token         = 35,136  ≈ 34.3 KiB
```

所以单请求 KV cache 约为：

- 16K context：BF16 ≈ **1.12 GB**
- 32K context：BF16 ≈ **2.25 GB**
- 64K context：BF16 ≈ **4.50 GB**
- 128K context：BF16 ≈ **8.99 GB**
- 同条件 FP8 / INT8 减半，INT4 理论上再减半。  

这些都是直接按论文 + config 的数字代入公式得到的。citeturn12view1turn43view0

如果把 V3 的 MLA 与“同样 61 层、128 头、head dim 128 的标准 MHA”做理论对比，那么后者每层每 token 需要 `2×128×128=32768` 个元素；V3 MLA 则是 `576` 个元素。也就是说，**在同维度对比下，每层每 token 的缓存元素数只有标准 MHA 的约 1.76%**。需要注意，论文里“KV cache 减少 93.3%”是相对于其论文对照基线的实证结论；而这里的 1.76% 是对 V3 公开配置做的**同维理论对比**。citeturn35search5turn12view1turn43view0

### 权重显存公式

对于权重，只要不考虑量化 scale、padding、runtime buffer，最基础的公式就是：

```text
weight_memory = total_params × bytes_per_param
```

代入公开总参数量，可得到以下**原始权重规模**：

| Model | BF16 / FP16 | FP8 / INT8 | INT4 |
|---|---:|---:|---:|
| DeepSeek-V3 / R1 671B | 1.342 TB | 671 GB | 335.5 GB |
| DeepSeek-V2 / Coder-V2 236B | 472 GB | 236 GB | 118 GB |
| Distill 70B | 140 GB | 70 GB | 35 GB |
| Distill 32B | 64 GB | 32 GB | 16 GB |
| Distill 14B | 28 GB | 14 GB | 7 GB |

这些只是**原始权重**，没有加上 KV、workspace、MoE routing buffer、CUDA graph buffer、allocator 保留空间、scale tensor、分页 cache 元数据与框架常驻开销。实际部署时，通常还要保留 10%–25% 的余量。citeturn28view1turn35search5turn34view1

### FLOPs 与瓶颈公式

对 decode 单 token，稠密线性层的一个常用近似是：

```text
dense_linear_flops_per_token ≈ 2 × active_params
```

对 DeepSeek 这类 MoE，`active_params` 比 `total_params` 更重要：V3 / R1 是 **37B**，V2 236B 是 **21B**。因此，忽略 attention score/value 的一阶近似下：

```text
V3/R1 decode flops/token ≈ 2 × 37B = 74 GFLOPs
V2-236B decode flops/token ≈ 2 × 21B = 42 GFLOPs
```

如果把注意力对历史长度 `T` 的读写也加进来，decode 还要多出 roughly `O(layers × heads × T × d_att)` 的项；随着 `T` 增长，attention 会从“可忽略”变成“不可忽略”，但小 batch 下仍常常先被**权重流式读取 + KV 读取 + 通信**压住。citeturn28view1turn29view1turn14search5

对 prefill，平均每个 token 还要承受 `O(S^2)` attention 成本，因此更接近 compute-bound；对 decode，则更接近：

```text
decode_tok_s_upper_bound ≈ effective_memory_bandwidth / bytes_streamed_per_token
```

这里的 `bytes_streamed_per_token` 不只是 KV，还包含“当前这一步需要读过的一遍激活权重”。这就是为什么同一台机器上，prefill tokens/s 与 decode tokens/s 经常差一个数量级。citeturn14search5turn32view0

## 推理框架支持矩阵

下表只写**已经在本次检索中找到官方文档或官方仓库证据**的支持项；没有证据的，一律写“未证实”或“部分”。

| 框架 | DeepSeek V3 / R1 | V2 / Coder-V2 | MLA | MoE / EP | FP8 | INT4 / AWQ / GPTQ / GGUF | Prefix Cache / 连续批处理 | 多机 / 多节点 | 硬件侧重点 | 结论 |
|---|---|---|---|---|---|---|---|---|---|---|
| vLLM | 有专项指南；V3/R1 同架构 | 支持 DeepSeek 架构族 | 是 | 是，官方有 EP 文档 | 是，官方 V3/R1 FP8 指南 | 是，官方指南提 FP4；量化生态完善 | 自动前缀缓存、推测解码 | 是 | NVIDIA 为主 | 生产可用，通用性强。citeturn32view2turn15search0turn15search1turn15search2 |
| SGLang | 官方 DeepSeek 专用文档；R1 reasoning parser | 泛 DeepSeek 支持 | 是 | 是，含 DeepEP / expert parallel | 是，文档明确 DeepSeek V3/R1 预量化 FP8 | AWQ 等在 AMD 文档中列出；GGUF 不是主路径 | PD disaggregation、HiCache、连续批处理体系完整 | 是 | NVIDIA + AMD 都强 | 目前对 DeepSeek 最“专项化”的开源栈。citeturn37search16turn14search3turn14search12turn14search17turn14search5 |
| TensorRT-LLM | 支持矩阵已列 Deepseek-R1/V3 | 未见 V2 专项页，但框架对类似模型支持强 | 是，含 MLA / chunked context / KV 系统 | 是 | 是 | 量化体系完整；MTP 仅 DeepSeek 支持 | KV cache reuse、IFB 调度 | 是 | NVIDIA 专属 | 追求 H200 / Blackwell 极致性能的首选。citeturn16search11turn16search2turn16search5turn32view1 |
| Transformers | 已有 DeepSeek-V2 / V3 官方模型文档 | 有 | 模型层面有 | 模型层面有，服务级 EP 不属于其强项 | 可加载官方权重，但不是最佳 serving 栈 | 依赖外部量化生态 | 无服务框架级连续 batching | 可结合 Accelerate / DS | 研究、验证、导出 | 适合研究与单机验证，不是大规模服务首选。citeturn40search1turn40search9turn41view0 |
| TGI | 官方支持页列出 Deepseek V2 / V3；R1 未单列 | V2 / V3 是 | 部分，依赖模型架构后端支持 | Tensor Parallel 有；MoE 服务级优化不如前述三家突出 | 支持 fp8 | 支持 AWQ / GPTQ / Marlin / EXL2 等 | 文档明确 continuous batching、prefix caching、paged attention | 单机多卡强；多机能力相对保守 | NVIDIA / Gaudi 等 | 如果你已经在 HF 服务体系里，TGI 可用；对 R1 专项优化不如 vLLM / SGLang / TRT-LLM。citeturn20search0turn20search1turn20search2turn20search3turn20search6 |
| llama.cpp | 通过 GGUF / 转换链部分支持；新 FP8 tensor 仍有转换问题 | Distill 更稳；全尺寸 V3/R1 变化快 | 不是原生 MLA serving 强项 | 无原生 EP | 否，主要走量化 / GGUF | 是，GGUF 强项；但新 DeepSeek 变体存在兼容议题 | 本地缓存 / server 有；推测解码有 | 否 | CPU / Apple / 本地 GPU | 最适合本地量化与蒸馏模型；不建议把 671B 原始 DeepSeek 当主战场。citeturn17search12turn38search1turn38search0 |
| KTransformers | 官方宣称支持 R1/V3 | 支持 V2/V2.5 | 部分，走 hybrid path | 强调超大 MoE 混合部署 | 有社区需求，但公开资料更多是 GGUF / hybrid | 是，特别强调本地 / mixed | 非传统在线 serving 栈 | 可多 GPU + 大内存 | CPU/GPU hybrid | 很适合“显存不足但内存很多”的本地或实验室场景。citeturn18search5turn18search10turn18search12 |
| LMDeploy | 支持模型页明确列出 V2 / V2.5 / V3 | 是 | 未单列“MLA”字样，但已支持这些模型 | 有张量并行、分布式服务 | 支持 FP8 / INT8 路线 | AWQ / GPTQ / KV quant | Prefix caching、continuous batch | 是 | NVIDIA 为主 | 国内生产化友好；对 DeepSeek 族支持较完整。citeturn17search15turn36search5turn36search10turn36search18 |
| Ollama | 模型库有 deepseek-r1 多标签，含 671b | 以本地模型消费为主 | 不暴露 MLA 优化细节 | 无公开 EP 语义 | 不以原始 FP8 server 为卖点 | 本地模型友好 | thinking / streaming 易用 | 非集群主栈 | Apple / Vulkan / 本地 GPU | 对 Distill 与小中模型最实用；对全尺寸 671B 更多是“能挂上模型标签”，不等于最优部署方式。citeturn17search5turn39search0turn39search2 |
| DeepSpeed Inference / MII | 未检索到 DeepSeek 专项官方 cookbook | 泛 Hugging Face 模型理论可适配 | 未证实 | 有 AutoEP / MoE / pipeline / ZeRO-3 inference | 有混精 / 推理 API | 量化与部署可组合 | 不以 LLM serving 专项见长 | 是 | 训练 / 推理一体 | 理论能力很强，但对 DeepSeek 的“现成可复用性”弱于前三家。citeturn19search11turn19search9turn19search17turn19search16 |
| FlashInfer | 不是完整服务框架 | 作为 kernel 库可服务于 V2/V3/R1 | 是，文档直写 MLA for DeepSeek | 有 fused_moe / comm | 有 DeepSeek 风格 FP8 kernel | 不是 GGUF 路线 | 作为底层 kernel 被集成 | 取决于上层框架 | NVIDIA 为主 | 它更像“加速器库”，不是独立部署终点。citeturn37search0turn37search3turn37search6turn37search15 |

### 框架选择建议

如果目标是**研究 / 验证 / 兼容 Hugging Face 生态**，Transformers 足够；如果目标是**开源生产服务**，优先考虑 **SGLang 或 vLLM**；如果目标是**NVIDIA Hopper / Blackwell 上榨极限性能**，优先考虑 **TensorRT-LLM**；如果目标是**本地量化 / Apple / CPU/GPU hybrid**，优先考虑 **llama.cpp / Ollama / KTransformers**。这个结论与它们各自官方文档的产品定位是一致的。citeturn37search16turn32view2turn13search18turn39search2turn18search12

## 硬件估算与部署建议

### 典型硬件规格

NVIDIA H100 SXM 80GB 提供 **80GB HBM、3.35TB/s 带宽、1,979 TFLOPS BF16/FP16、3,958 TFLOPS FP8**；H100 PCIe 80GB 的带宽则是 **>2TB/s** 级别。H200 提供 **141GB HBM3e、4.8TB/s 带宽**，同样是 **1,979 TFLOPS BF16/FP16、3,958 TFLOPS FP8**。A100 80GB 的带宽是 **1,935 GB/s PCIe / 2,039 GB/s SXM**，BF16/FP16 是 **312 TFLOPS**。L40S 为 **48GB GDDR6、864GB/s、BF16/FP16 362 / 733 TFLOPS、FP8 1.466 PFLOPS（稀疏计法）**。RTX 4090 是 **24GB GDDR6X、约 1 TB/s 带宽**；RTX 6000 Ada 是 **48GB、960 GB/s**。citeturn21search0turn23search3turn25search2turn25search6turn27search0turn22search8turn22search1

AMD 侧，MI300X 是 **192GB HBM3、5.3TB/s 带宽**；MI250 / MI250X 是 **128GB HBM2e、约 3.2–3.277TB/s**。Apple M3 Ultra 最高可配到 **512GB unified memory**、**819GB/s 带宽**；M4 Max 最高 **128GB unified memory、546GB/s 带宽**。服务器 CPU 里，4th Gen Xeon 8490H 支持 **8 通道 DDR5-4800**，AMD EPYC 9754 单 socket 公布的内存带宽是 **460.8 GB/s**。citeturn22search3turn23search1turn23search5turn24search4turn24search0turn24search5turn24search3turn24search9

### 表 A

| Model | Precision | 原始权重显存 | KV 假设 | 运行时开销假设 | 最低聚合显存建议 | 推荐 GPU 数 | 备注 |
|---|---:|---:|---:|---:|---:|---:|---|
| V3 / R1 671B | FP8 | 671 GB | 单请求 32K、BF16 KV ≈ 2.25 GB | +10%~20% buffer / allocator | **740–810 GB** | **8×H200 / 8×MI300X** | 8×H100 80GB 原生 FP8 单机一般不够。citeturn28view1turn12view1turn32view0 |
| V3 / R1 671B | BF16 | 1.342 TB | 同上 | 同上 | **1.48–1.62 TB** | **≥12×H200 或多节点** | 单机 8 卡不现实。citeturn28view1turn21search1 |
| V3 / R1 671B | INT4 | 335.5 GB | 32K KV 取决于 cache dtype | +10%~20% | **370–410 GB** | **8×80GB / 8×48GB + 大量优化** | 更适合离线 / 本地混合式，不是最稳健生产路径。citeturn18search12turn17search5 |
| V2 / Coder-V2 236B | FP8 | 236 GB | 32K BF16 KV ≈ 2.21 GB | +10%~20% | **260–290 GB** | **4×80GB** | 这是中大型 DeepSeek 的甜点位。citeturn35search5turn29view1turn42view4 |
| V2 / Coder-V2 236B | BF16 | 472 GB | 同上 | 同上 | **520–570 GB** | **8×80GB 或 4×H200** | 单机高端训练 / 推理节点可做。citeturn35search5turn21search1turn25search6 |
| Distill 70B | BF16 | 140 GB | 依底模而定 | +10%~20% | **155–170 GB** | **2×80GB 或 1×192GB** | 生产与本地兼顾。citeturn34view1turn22search3 |
| Distill 32B | BF16 | 64 GB | 依底模而定 | +10%~20% | **72–80 GB** | **1×80GB / 2×48GB** | A100 80GB、MI300X 单卡都很轻松。citeturn34view1turn25search6turn22search3 |
| Distill 14B | BF16 | 28 GB | 依底模而定 | +10%~20% | **31–36 GB** | **1×48GB / 1×24GB 需看上下文** | 本地开发很友好。citeturn34view1turn22search1turn22search8 |

### 表 B

| Hardware | VRAM / HBM | 适合精度 | 能否装下 V3/R1 原始 FP8 | 推荐并行 | 典型场景 | 主瓶颈 | 结论 |
|---|---:|---|---|---|---|---|---|
| 8×H200 | 1128 GB aggregate | FP8 / BF16 | 能 | TP+EP 或 DP+EP | 生产主力、低延迟与高吞吐都可 | MoE 通信、调度、KV 增长 | 最稳妥单机选择之一。citeturn21search1turn32view2turn32view1 |
| 8×MI300X | 1536 GB aggregate | FP8 / BF16 | 能 | TP8 / EP8 常见 | 单机生产、AMD 生态 | 软件栈成熟度、A2A | 也是最稳妥单机选择之一。citeturn22search3turn32view0turn14search17 |
| 8×H100 SXM 80GB | 640 GB aggregate | V2 FP8；V3/R1 原始 FP8 不稳 | 一般不够 | 对 V2 可 TP/EP | 中大型 MoE、非 671B 全尺寸 | 容量先爆，再谈算力 | 不推荐做原始 V3/R1 FP8 单机主方案。citeturn21search0turn32view0 |
| 4×A100 80GB | 320 GB aggregate | V2 FP8 / 32B-70B BF16 | 不够 V3/R1 | TP4 / 少量 EP | 成本敏感部署 | 带宽较老，decode 较慢 | 很适合 236B FP8，不适合 671B 原始 FP8。citeturn25search6turn35search5 |
| 4×L40S 48GB | 192 GB aggregate | 32B / 14B / 70B INT4 | 不够 | TP2/4 | 中型模型推理 | PCIe、显存、无 NVLink 级别互联 | 适合 Distill，不适合 V3/R1 全尺寸。citeturn27search0 |
| 2×RTX 6000 Ada | 96 GB aggregate | 32B BF16 / 70B INT4 | 不够 | TP2 | 工作站 | PCIe、软件兼容 | 开发友好，生产不建议跑 671B。citeturn22search1 |
| 4×RTX 4090 | 96 GB aggregate | 14B / 32B 量化 | 不够 | 张量并行或 hybrid | 极客本地 | PCIe、24GB 单卡容量 | 适合 Distill / 量化，不适合 V3/R1 原始部署。citeturn22search8turn18search12 |
| M3 Ultra Mac Studio | 96–512 GB unified | INT4 / GGUF / MLX 路线 | 理论可放很大模型，实际很慢 | 无典型 EP | 本地实验 | 819GB/s 远低于 HBM 集群 | 能“装”不等于能“高性能服务”。citeturn24search4turn24search0 |
| 高端 2P EPYC / Xeon 服务器 | 512GB–2TB RAM | CPU / offload | 只能以极低速或混合式 | NUMA + offload | 离线、验证 | DRAM 带宽与延迟 | 不适合高吞吐在线服务。citeturn24search3turn24search9 |

### 表 C

> 说明：下表分成“**官方观测**”与“**公式估算**”。  
> 其中，官方观测只在我检索到官方 benchmark 数字的组合上填写；其余组合只给**区间估算**，并明确写出是假设结果。  
> 估算前提：V3/R1 优先按原始 FP8；低延迟场景看 batch 小、并发低；高吞吐场景看大并发与 continuous batching。

| Hardware | Framework | Model | Precision | 工作负载假设 | Prefill tokens/s | Decode tokens/s | 延迟 / 吞吐结论 | 来源或公式 | 置信度 |
|---|---|---|---|---|---:|---:|---|---|---|
| 8×H200 | vLLM | R1 / V3 | FP8 | 近似 8K 输入 / 1K 输出、单请求例子 | 由 TTFT 560ms 粗算 prompt processing 约 14k tok/s 量级 | 官方示例输出吞吐 **61 tok/s** | 说明同机可进低延迟区间，但这是示例，不是峰值 | vLLM 官方示例：7902 prompt tokens、TTFT 560ms、TPOT 15.85ms、output 61 tok/s。citeturn33view0 | 中 |
| 8×H200 | TensorRT-LLM | R1 | FP8 | 高并发 throughput benchmark | 未单列 | **11,489 tok/s 总输出吞吐**，**1,436 tok/s/GPU** | 这是高吞吐大并发，不代表单用户聊天速度 | TRT-LLM 官方 benchmark。citeturn32view1 | 高 |
| 8×MI300X | SGLang | R1 / V3 | FP8 | 单节点、并发 1–32 聊天服务 | 公开文中未给绝对 prefill 数；整体 throughput 相比 day0 提升到 **4×** | 文中强调在并发 ≤32 时 TPOT < 50ms | 更偏“可用且竞争力强”的证明，而不是固定 tok/s 发布 | AMD ROCm 官方博客。citeturn32view0 | 中 |
| 8×H100 SXM | 任一 | V3 / R1 | FP8 | 原始权重 | N/A | N/A | 官方与厂商博文都指向**容量不足** | AMD 官方博客 + H100 80GB 规格。citeturn32view0turn21search0 | 高 |
| 4×A100 80GB | vLLM / SGLang | V2 / Coder-V2 236B | FP8 | 公式估算，在线聊天、小并发 | **约 4k–10k tok/s** | **约 30–90 tok/s** | 能跑，decode 带宽较吃紧 | 依据 A100 带宽 1.9–2.0TB/s、V2 激活参数 21B、MLA KV 公式估算。citeturn25search6turn29view1turn42view4 | 中低 |
| 2×RTX 6000 Ada | LMDeploy / vLLM | Distill 32B | BF16 / AWQ | 公式估算，开发 / 小服务 | **约 0.8k–2k tok/s** | **约 15–40 tok/s** | 本地开发实用，生产需谨慎 | 依据 960GB/s 带宽、32B dense 权重规模估算。citeturn22search1turn34view1 | 低 |

### 工程建议

对 **个人本地部署**，最现实的选择不是 V3/R1 原始 671B，而是 **R1-Distill 7B / 8B / 14B / 32B**。使用 Ollama、llama.cpp、LMDeploy 或 vLLM 都可以；如果你有超大内存机器、但 GPU 很少，KTransformers 的 hybrid 路线会比“硬塞原始 V3/R1”更现实。citeturn17search5turn39search0turn18search12turn18search5

对 **单机 4 卡 / 8 卡**，建议分两档：  
一档是 **V2 / Coder-V2 236B**，推荐 4×80GB 以上做 FP8；  
另一档是 **V3 / R1 671B**，推荐直接上 **8×H200 或 8×MI300X**。  
框架优先级上，通用开源生产优先 SGLang / vLLM；若是 NVIDIA 专用高性能栈，优先 TensorRT-LLM。citeturn35search5turn32view2turn32view0turn13search18

对 **多机多卡部署**，你需要把重点从“单卡算力”转移到“互联与调度”。DeepSeek-V3 论文已经说明，它的在线部署会显式受 all-to-all、TP 通信、冗余专家摆放和跨节点拓扑影响；SGLang 的 PD disaggregation、vLLM 的 Wide-EP / 异步调度、TensorRT-LLM 的大规模 EP，都是为此而生。**没有好的 NVLink / NVSwitch / IB / RoCE，就不要指望 671B MoE 在多机下线性扩展。**citeturn28view2turn14search5turn31search9turn16search0

对 **长上下文服务**，MLA 已经大幅缓解了 KV 容量问题，但没有消灭问题。V3 在 128K、BF16 KV 下，单请求也依然接近 9GB KV；批量一大，这部分会迅速顶满显存。因此应优先打开**prefix caching / KV reuse / FP8 KV / Hicache / chunked context**等能力。vLLM、TensorRT-LLM、TGI、LMDeploy、SGLang 都分别有对应特性。citeturn12view1turn15search1turn16search2turn20search3turn36search5turn14search16

对 **低延迟 chat 服务**，vLLM 官方文档已经直接指出：低负载低延迟场景通常更适合 **TP**，高负载更适合 **DP**；同时 DeepSeek 这类 MoE 模型几乎都需要把 **EP** 一起纳入设计。实践上，8×H200 常见做法是 **TP8+EP** 或 **DP8+EP** 两种路线按业务目标择一。citeturn32view2

对 **batch 离线推理 / 高并发 API 服务**，则应该相反：优先选择支持持续拼批、前缀缓存、disaggregated serving 和高效 expert parallel 的引擎。这里 SGLang、vLLM、TensorRT-LLM 都比纯 Transformers / 小型本地栈更合适。citeturn14search5turn15search8turn16search2

## 不确定性与后续验证清单

### 哪些结论最可靠

最可靠的结论包括：V3 / R1 的 **671B / 37B**、V2 的 **236B / 21B**、V3 的 `hidden_size=7168 / layers=61 / 256 routed experts / 8 激活 routed experts / 1 shared expert / kv_lora_rank=512 / qk_rope_head_dim=64`、V2 家族 236B 的 `hidden_size=5120 / layers=60 / 160 routed experts / 2 shared experts / 6 激活 experts`，以及 H100 / H200 / A100 / MI300X / L40S 等硬件规格。这些都直接来自**论文、官方 repo、官方 config 或厂商规格页**。citeturn28view1turn43view0turn29view1turn42view4turn21search0turn21search1turn25search6turn22search3turn27search0

### 哪些结论是估算

本报告中以下内容属于估算：  
V3 / V2 单层 MLA 参数量的细分；单 expert 参数量；不同 seq/batch 条件下的 KV 占用表；以及 A100 / RTX 6000 Ada / 4090 等平台上的 prefill / decode tokens/s 区间。这些是用**公开 config 数字**代入标准参数、显存、FLOPs 与 roofline 公式得出的，不是官方 benchmark 发布值。citeturn43view0turn42view4

### 哪些问题仍待验证

- **DeepSeek-V2.5** 的精确层数、hidden size、专家布局，公开资料没有独立完整披露；就工程上看，它大概率沿 V2 / Coder-V2 主骨架，但这一点不应写成“官方确认”。citeturn35search3turn35search12
- **TGI 对 R1**、**DeepSpeed / MII 对 DeepSeek** 的专项优化程度，公开资料明显少于 vLLM / SGLang / TRT-LLM；结论应保持谨慎。citeturn20search0turn19search16turn19search11
- **llama.cpp / GGUF / Ollama** 对 DeepSeek 最新 FP8 权重和新变体的兼容性变化非常快；公开 issue 已显示某些 DeepSeek V3 风格 FP8 tensor 仍会给 converter 带来问题。citeturn38search0
- **非官方硬件组合的 tok/s**，尤其是 PCIe-only 多卡、Apple 统一内存、大规模 CPU offload，最好都做你自己的实测，而不要把公式估算当作 SLA。citeturn24search0turn24search5turn18search12

### 推荐 benchmark 计划

后续实测建议采用统一变量集：  
**模型**：V2-236B、V3/R1、R1-Distill-32B、R1-Distill-14B；  
**框架**：SGLang、vLLM、TensorRT-LLM、LMDeploy、KTransformers；  
**精度**：BF16 / FP8 / INT4；  
**输入输出长度**：`1k/1k`、`8k/1k`、`1k/8k`、`32k/1k`、`128k/256`；  
**并发**：`1 / 4 / 16 / 32 / 64 / 128`；  
**指标**：TTFT、TPOT、ITL、output tok/s、total tok/s、显存峰值、KV 占用、A2A 流量、GPU 利用率、SM 占用率、HBM 带宽。  
其中，vLLM 与 TensorRT-LLM 已分别公开 `bench serve` / `trtllm-bench` 的官方路径；SGLang 也提供 `sglang.bench_serving` 示例。citeturn32view2turn32view1turn32view0

在真正落地前，可以把最终判断压缩成一句话：**如果你要跑 DeepSeek-V3 / R1 原始 671B，并且希望它像真正的在线服务那样工作，请把默认目标机型设成 8×H200 或 8×MI300X，把默认框架设成 SGLang / vLLM / TensorRT-LLM，把默认精度设成 FP8，并把工程重点放到 EP、KV 管理和通信，而不是只看单卡 TFLOPS。** 这个结论是本次调研里证据最集中、工程可操作性也最高的部分。citeturn32view2turn32view0turn13search18turn21search1turn22search3