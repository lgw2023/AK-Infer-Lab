# GLM-5.2 架构与推理资源深度研究报告

## Executive Summary

- **GLM-5.2 已有相当可用的公开架构线索，但并非所有底层实现细节都被官方论文式完整披露。** 公开可确认的信息主要来自 Z.ai 官方博客、官方 GitHub / Hugging Face 模型卡与 `config.json`，以及主流推理框架的适配文档；其中最关键的是官方配置文件已经直接暴露了层数、hidden size、MoE expert 数、上下文长度、MTP 相关字段、IndexShare 调度信息等。citeturn12view0turn28search1turn45view2
- **GLM-5.2 不是普通 dense decoder-only，而是带有稀疏注意力与 MoE 的大规模文本模型。** 官方 GitHub/模型卡明确给出 GLM-5.2 为 744B 级别模型，活动参数约 39B–40B，并强调 1M context、IndexShare、改进的 MTP；配置文件显示 `model_type` 为 `glm_moe_dsa`，`n_routed_experts=256`、`num_experts_per_tok=8`、`n_shared_experts=1`、`num_hidden_layers=78`。citeturn12view0turn19view0turn45view2
- **公开配置强烈表明其注意力并非传统 MHA/GQA，而是 DeepSeek-V3.2 风格的 MLA 路线再叠加 DSA/IndexShare。** 直接证据包括 `q_lora_rank=2048`、`kv_lora_rank=512`、`qk_nope_head_dim=192`、`qk_rope_head_dim=64`、`index_topk=2048`、`index_topk_freq=4`；AMD ROCm ATOM 文档与 NVIDIA NeMo 文档也都把 `glm_moe_dsa` 指向 MLA/Indexer 路径。citeturn45view2turn32view1turn29search15
- **就推理内存而言，GLM-5.2 的关键不是“总参数 744B”本身，而是“约 39B 活动参数 + 压缩 KV cache + 稀疏索引复用”。** 标准头维 KV 公式会把 1M context 推到难以承受的显存量；而基于公开配置可反推出 GLM-5.2 的 MLA cache 维度近似为 `kv_lora_rank + qk_rope_head_dim = 576`，远小于传统 `2 * num_kv_heads * head_dim = 24576` 元素/层/Token。citeturn45view2turn32view1
- **官方开源权重目前能明确确认的是 BF16 和 FP8 两套主权重。** 官方 GitHub README 与 Hugging Face 树页列出了 `zai-org/GLM-5.2` 和 `zai-org/GLM-5.2-FP8`；vLLM Recipe 还给出了 NVIDIA 的 `GLM-5.2-NVFP4` 再量化变体，但那属于平台特定再量化，不是 Z.ai 官方主权重。citeturn12view0turn35view1turn19view0
- **主流推理框架方面，最明确的直接支持是 Transformers、vLLM、SGLang，以及 Ascend 侧的 vLLM-Ascend / xLLM / SGLang 路线。** 官方 README 和 Hugging Face 使用说明直接给出 Transformers / vLLM / SGLang 启动方式；vLLM Recipe 要求 `v0.23.0+`，SGLang release note 已写入 “New Model Support: GLM-5.2”。Ascend 侧有官方 README 的支持声明和大批适配/问题工单。citeturn12view0turn11search5turn19view0turn20search7turn38search0turn38search1
- **典型硬件结论很直接：单卡无论 H100/H200/MI300X/4090/5090 都无法“干净地”承载官方 BF16/FP8/INT4 主权重。** 744B 模型原始 BF16 权重约 1.49TB；官方 FP8 检查点目录体积约 756GB；即使按裸 INT4 也约 372GB，实际再量化检查点常落在 395GB–465GB 区间。citeturn12view0turn35view1turn19view0turn31search6
- **官方/半官方最稳妥的生产部署区间，目前是 8 卡级别。** vLLM 官方 Recipe 直接写明：单节点 FP8 的“实用默认”是 8×H200 或 8×H20，想跑满 1M context 需要 8×B200 + FP8 KV cache；ROCm/ATOM 给出了 8×MI355X 的可复现实测基线；Ascend 侧则更多依赖 W8A8 / W4AFP8 等量化权重。citeturn19view0turn32view1turn38search1turn38search8
- **公开信息最大的缺口，不在“有没有模型”，而在“底层 kernel/缓存/IndexShare 的严格数学与实现文档不完整”。** 例如 DSA indexer 的精确 tensor layout、IndexShare 的 kernel 接口、MTP 内部 head 结构、Tokenizer 的底层算法类型，这些信息在当前公开材料里仍主要依靠配置字段、框架适配代码和工程文档反推，而不是官方单一技术报告逐项表述。citeturn45view2turn12view0turn29search15

## Source Map 与版本识别

### 来源可信度表

下表只列本报告最核心、最“承重”的来源。链接列使用可点击引文代替原始 URL。

| 来源 | 类型 | 链接 | 发布日期 | 涉及内容 | 可信度 | 是否直接关于 GLM-5.2 | 备注 |
| -- | -- | -- | -- | -- | -- | -- | -- |
| Z.ai 官方博客《GLM-5.2: Built for Long-Horizon Tasks》 | 官方博客 | citeturn17search4 | 2026-06-16 | 1M context、IndexShare、MTP 改进、能力对比 | A | 是 | 一手发布说明 |
| Z.ai 官方 GitHub `zai-org/GLM-5` README | 官方仓库 | citeturn12view0 | 2026-06 更新 | 744B-A40B、下载链接、框架支持、`reasoning_effort` | A | 是 | 对 GLM-5 / 5.1 / 5.2 的总览 |
| Hugging Face 官方模型卡 `zai-org/GLM-5.2` | 官方模型卡 | citeturn28search1 | 2026-06-17 | 权重公开、模型说明、使用方式 | A | 是 | 与官方博客内容一致 |
| Hugging Face 官方配置 `config.json` | 官方配置文件 | citeturn45view2turn44view0 | 2026-06-16 左右 | 层数、hidden size、MoE/MLA/rope/IndexShare 字段 | A | 是 | 本报告架构参数的核心依据 |
| Hugging Face `chat_template.jinja` | 官方模板文件 | citeturn6view0 | 2026-06-16 左右 | role token、`<think>`、`<tool_call>`、默认思考模式 | A | 是 | 支持 tokenization / 对话模板分析 |
| Z.ai Developer Docs `GLM-5.2` | 官方 API/文档 | citeturn34view0turn34view1 | 2026-06 | API 名称 `glm-5.2`、1M context、调用示例 | A | 是 | 面向 API/产品使用 |
| Hugging Face Transformers 文档 `GlmMoeDsa` | 主流框架文档 | citeturn30view0 | 2026-06 | forward 输入输出、cache 接口、模型类 | B | 间接 | 针对 `glm_moe_dsa` 架构 |
| vLLM Recipes `zai-org/GLM-5.2` | 主流推理框架文档 | citeturn19view0 | 2026-06-27 | vLLM 版本、8×H200/8×B200 建议、NVFP4 | B | 是 | 最强的生产部署参考之一 |
| SGLang release / docs | 主流推理框架文档 | citeturn20search7turn20search0 | 2026-06 | GLM-5.2 已列为新模型支持；SGLang 核心特性 | B | 是 | cookbook 细节更多散落在 PR/issue |
| ROCm ATOM `GLM-5.md` | 主流框架/厂商工程指南 | citeturn32view1 | 2026-06 | `glm_moe_dsa` + MLA、GLM-5.2 IndexShare、8×MI355X 基准 | B | 是 | AMD 侧最关键的实测来源 |
| TensorRT-LLM Supported Models / parser factory | 主流推理框架文档/代码 | citeturn23view0turn21search4 | 2026-06 | `GlmMoeDsaForCausalLM` / `glm_moe_dsa` 支持入口 | B | 间接 | 文档明确写 GLM-5，GLM-5.2 主要靠架构复用与 issue 佐证 |
| LMDeploy supported models | 主流推理框架文档 | citeturn25search5turn25search7 | 2026-06 | 目前列出 GLM-5，未直接列 GLM-5.2 | B | 间接 | 说明“GLM 系列支持”不能自动外推到 5.2 |
| NVIDIA NIM support matrix | 官方平台文档 | citeturn36search0turn36search5 | 2026-06 | NIM 收录 GLM-5 / 5.1，未见 GLM-5.2 | B | 间接 | 用于判断 NIM 公开支持边界 |
| llama.cpp issue / MLX issue / vLLM-Ascend issue | 社区工程线索 | citeturn26search0turn31search0turn38search0 | 2026-06 | 未支持、加载失败、适配中等状态 | D | 是 | 只能辅助，不可当“事实完成态” |

### 模型家族与版本识别

公开材料中，**能够直接确认存在** 的 GLM-5.2 相关版本如下。

| 模型名称 | 权重是否公开 | 参数规模 | 激活参数规模 | 上下文长度 | 是否 MoE | 是否多模态 | 来源 |
| -- | --: | --: | --: | --: | --: | --: | -- |
| `zai-org/GLM-5.2` | 是 | 744B | 40B 级 | 1,048,576 | 是 | 否 | citeturn12view0turn45view2 |
| `zai-org/GLM-5.2-FP8` | 是 | 744B | 40B 级 | 1,048,576 | 是 | 否 | citeturn12view0turn35view1 |
| `nvidia/GLM-5.2-NVFP4` | 否，属 NVIDIA 再量化发布 | 744B 原模再量化 | 未公开单独口径 | 依部署配置 | 是 | 否 | citeturn19view0 |
| `GLM-5.2-W4AFP8` 等社区/平台量化版 | 部分公开 | 原模再量化 | 未统一 | 依部署配置 | 是 | 否 | citeturn38search5turn38search8 |

本次检索**未找到公开确证** 的同代 `Base / Chat / Instruct / Reasoning / Code / Vision-VL` 权重拆分；公开开放权重更像是**单一主模型**，辅以聊天模板、`thinking`/`reasoning_effort`、tool-calling 模板和不同精度检查点来覆盖使用场景。视觉模型则在 Z.ai 文档中以 `GLM-5V-Turbo` 单列，并非 `GLM-5.2-VL`。citeturn34view1turn6view0

## 架构、参数与推理计算路径

### 可确证的架构配置

下表只写**已经被官方配置或官方文档确认** 的字段；拿不到的字段直接写 `unknown`。

| 字段 | 数值 | 来源 | 可信度 | 备注 |
| -- | --: | -- | -- | -- |
| architecture type | `glm_moe_dsa` | citeturn45view2 | A | 配置文件直接给出 |
| parameter count | 744B | citeturn12view0 | A | README 写为 `744B-A40B` |
| active parameter count | 39B–40B | citeturn12view0turn19view0 | A/B | 官方 README 写 40B，vLLM Recipe 写 39B |
| num_hidden_layers | 78 | citeturn45view2 | A | 配置文件直接给出 |
| hidden_size / d_model | 6144 | citeturn44view0 | A | 配置文件直接给出 |
| intermediate_size / d_ff | 12288 | citeturn45view0 | A | dense MLP 用 |
| moe_intermediate_size | 2048 | citeturn45view2 | A | routed/shared expert 路径 |
| num_attention_heads | 64 | citeturn45view2 | A | 配置文件直接给出 |
| num_key_value_heads | 64 | citeturn45view2 | A | 配置文件直接给出 |
| head_dim | 192 | citeturn44view0 | A | value head 维度字段 |
| q_lora_rank | 2048 | citeturn45view2 | A | MLA 线索 |
| kv_lora_rank | 512 | citeturn45view0 | A | MLA/KV 压缩线索 |
| qk_head_dim | 256 | citeturn45view2 | A | `192 + 64` |
| qk_nope_head_dim | 192 | citeturn45view2 | A | 非 RoPE 部分 |
| qk_rope_head_dim | 64 | citeturn45view2 | A | RoPE 部分 |
| attention type | MLA + DSA + IndexShare | citeturn32view1turn29search15turn17search4 | B/A | MLA/IndexShare 为代码与工程文档可证 |
| position embedding | RoPE | citeturn45view2 | A | `rope_parameters` |
| RoPE base / scaling | `rope_theta=8000000` | citeturn45view2 | A | 配置文件直接给出 |
| normalization | RMSNorm | citeturn45view2 | A | `rms_norm_eps` 暗示 RMSNorm 配置族 |
| activation | SiLU | citeturn44view0 | A | 在 gated MLP 上通常对应 SwiGLU 风格实现 |
| vocab_size | 154880 | citeturn3view0 | A | 配置文件直接给出 |
| tokenizer type | unknown | — | — | 本次已抓取公开片段未直接给出 |
| tie_word_embeddings | false | citeturn45view2 | A | 配置文件直接给出 |
| max_position_embeddings | 1048576 | citeturn45view0turn34view1 | A | 1M context |
| quantization config | 官方 BF16 / 官方 FP8 | citeturn12view0turn35view1 | A | 开源主版本 |
| MoE num_experts | 256 routed + 1 shared | citeturn45view2 | A | 配置文件直接给出 |
| MoE top_k | 8 | citeturn45view2 | A | `num_experts_per_tok=8` |
| shared experts | 1 | citeturn45view2 | A | 直接字段 |
| router / gate design | sigmoid + `noaux_tc` | citeturn45view2 | A | `scoring_func` / `topk_method` |
| first_k_dense_replace | 3 | citeturn44view0 | A | 前 3 层 dense |
| mlp layer schedule | 前 3 层 dense，后 75 层 sparse | citeturn45view0turn45view2 | A | 由 `mlp_layer_types` 列表直接可数 |
| sparse index top-k | 2048 | citeturn44view0 | A | `index_topk` |
| index share frequency | 4 | citeturn44view0 | A | `index_topk_freq=4` |

从 `indexer_types` 列表直接计数可得：**78 个注意力层里约有 21 个 `"full"` 层与 57 个 `"shared"` 层**。这与官方博客“**同一个 indexer 在每四个 sparse attention layer 中复用一次**”的表述一致，说明 GLM-5.2 的长上下文优化不是口号，而是被直接编码进了权重配置里。citeturn44view0turn44view2turn17search4

### 从 token input 到 output 的完整推理路径

#### Tokenization 与对话模板

`GLM-5.2` 的 API 名称就是 `glm-5.2`，本地权重则通过 Hugging Face 的 `zai-org/GLM-5.2` / `zai-org/GLM-5.2-FP8` 加载。公开 `chat_template.jinja` 显示它不是裸文本拼接，而是显式注入 `<|begin_of_sentence|>`、`<|User|>`、`<|Assistant|>`、`<think>`、`<tool_call>` 等模板片段，并把“思考模式默认开启、`reasoning_effort` 默认为 `max`，只有显式传 `high` 才切换”为模板级逻辑。citeturn34view1turn6view0turn19view0

| 阶段 | 输入 shape | 输出 shape | 主要数据结构 | 备注 |
| -- | -- | -- | -- | -- |
| 原始文本 / messages | Python list / JSON | 模板化字符串 | chat template | 含 system/user/assistant/tool 角色 |
| 模板化字符串 | `[B]` | `input_ids: [B, S]` | token ids | 词表大小 154,880 |
| padding / mask 构造 | `input_ids` | `attention_mask: [B, S]` | 0/1 mask | HF 接口与 API 都支持 |
| 位置构造 | `input_ids` | `position_ids: [B, S]` | int64 | RoPE 使用位置索引 |
| generation prompt 注入 | messages | 末尾追加 assistant 前缀 | 模板控制 | 可切 `enable_thinking` 与 `reasoning_effort` |

#### Embedding 与残差流

- Token embedding 矩阵大小可直接由 `vocab_size × hidden_size = 154880 × 6144` 反推，参数量约 **951.6M**。这是**配置文件直接可复算** 的工程事实。citeturn44view0turn3view0
- 因为 `tie_word_embeddings=false`，所以输出端 `lm_head` 不能被当作与 embedding 共享权重，推理时仍要再保留一套 `[6144, 154880]` 级别的大矩阵。citeturn45view2turn30view0

| 模块 | Tensor / Matrix | Shape | dtype | 数量 | 内存占用公式 | 是否常驻显存 |
| -- | -- | -- | -- | --: | --: | -- |
| token ids | `input_ids` | `[B, S]` | int64/int32 | 1 | `B*S*bytes` | 否 |
| attention mask | `attention_mask` | `[B, S]` | bool/int | 1 | `B*S*bytes` | 否 |
| position ids | `position_ids` | `[B, S]` | int64 | 1 | `B*S*bytes` | 否 |
| embedding table | `embed_tokens.weight` | `[154880, 6144]` | BF16/FP8/量化 | 1 | `154880*6144*bytes` | 是 |
| hidden states | residual stream | `[B, S, 6144]` | compute dtype | 多层复用 | `B*S*6144*bytes` | 否 |

#### Transformer 层内部结构

这里要特别强调：**GLM-5.2 的公开配置已经表明它不是“普通 Q/K/V 线性层 + 传统 head-wise KV cache”**。更符合公开信息的写法，是把它分成 **MLA query 路径、MLA compressed KV 路径、DSA/IndexShare 稀疏索引路径、再接 dense/MoE MLP**。citeturn45view2turn32view1turn29search15

下面这张表，把“公开能确定的矩阵形状”与“由配置字段直接反推的矩阵形状”放在一起。凡是属于反推，我都在备注中明确标出来。

| 模块 | 输入 shape | 权重矩阵 shape | 输出 shape | 参数量公式 | FLOPs 估算 | memory 访问 | 是否依赖 seq_len |
| -- | -- | -- | -- | -- | -- | -- | -- |
| pre-attn norm | `[B,S,6144]` | `[6144]` | `[B,S,6144]` | `H` | `O(B*S*H)` | 低 | 是 |
| **Q-A 投影** | `[B,S,6144]` | `[6144,2048]` | `[B,S,2048]` | `H*q_lora_rank` | 约 `2*B*S*H*q_r` | 中 | 是 |
| **Q-B 投影** | `[B,S,2048]` | `[2048,64*256]` | `[B,S,64,256]` | `q_r*(n_h*qk_head_dim)` | 约 `2*B*S*q_r*n_h*qk` | 中 | 是 |
| **KV-A 压缩投影** | `[B,S,6144]` | `[6144,512+64]` | `[B,S,576]` | `H*(kv_r+qk_rope)` | 约 `2*B*S*H*(kv_r+rope)` | 中 | 是 |
| **KV-B 展开投影** | `[B,S,512]` | `[512,64*(192+192)]` | `[B,S,64,384]` | `kv_r*n_h*(qk_nope+v_dim)` | 约 `2*B*S*kv_r*n_h*(qk_nope+v)` | 中 | 是 |
| RoPE 应用 | `[B,S,64,64]` 子空间 | 无/缓存表 | 同形状 | — | `O(B*S*n_h*qk_rope)` | 低 | 是 |
| DSA full indexer | `[B,S,6144]` | implementation-specific | index table | unknown | 与 top-k 搜索相关 | 中高 | 是 |
| IndexShare shared 层 | 复用上一个 full 层索引 | 无新增 | index table | 0 | 显著低于 full indexer | 低 | 是 |
| 稀疏 attention logits | `Q×K^T` | — | `[B,64,q_len,topk]` 或 kernel-specific | — | 近似 `O(B*n_h*q_len*topk*d)` | 高 | 是 |
| attention value 聚合 | logits × V | — | `[B,S,64,192]` | — | 近似 `O(B*n_h*q_len*topk*v_dim)` | 高 | 是 |
| O projection | `[B,S,64*192]` | `[12288,6144]` | `[B,S,6144]` | `n_h*v_dim*H` | 约 `2*B*S*12288*6144` | 中 | 是 |
| residual add | `[B,S,6144]` | — | `[B,S,6144]` | — | `O(B*S*H)` | 低 | 是 |
| pre-MLP norm | `[B,S,6144]` | `[6144]` | `[B,S,6144]` | `H` | `O(B*S*H)` | 低 | 是 |
| dense gate/up/down | `[B,S,6144]` | `[6144,12288]`×2 + `[12288,6144]` | `[B,S,6144]` | `3*H*d_ff` | 约 `6*B*S*H*d_ff` | 高 | 是 |
| MoE router | `[B,S,6144]` | `[6144,256]` | `[B,S,256]` | `H*n_exp` | 约 `2*B*S*H*n_exp` | 低中 | 是 |
| routed expert 单 expert | `[tokens,6144]` | `[6144,2048]`×2 + `[2048,6144]` | `[tokens,6144]` | `3*H*d_exp` | 约 `6*tok*H*d_exp` | 高 | 否 |
| shared expert | `[B,S,6144]` | 与 routed expert 同级规模 | `[B,S,6144]` | 近似 `3*H*d_exp` | 同上 | 高 | 是 |
| final norm | `[B,S,6144]` | `[6144]` | `[B,S,6144]` | `H` | `O(B*S*H)` | 低 | 是 |
| lm_head | `[B,S,6144]` 或最后一 token | `[6144,154880]` | `[B,S,154880]` 或 `[B,154880]` | `H*V` | 约 `2*B*S*H*V` | 很高 | 是 |

上表中的 **Q-A / Q-B / KV-A / KV-B** 路径，属于“**配置字段反推**”而不是官方单表给出的矩阵表，但它与 `q_lora_rank / kv_lora_rank / qk_nope_head_dim / qk_rope_head_dim / head_dim` 的组合是完全一致的，也是公开工程文档把 GLM-5.2 归为 `glm_moe_dsa` + MLA 路线的原因。citeturn45view2turn32view1turn29search15

#### Prefill 与 Decode 的区别

GLM-5.2 的 prefill/decode 分化，比普通 dense 模型还更明显，因为它同时叠加了长上下文、DSA sparse attention、IndexShare 和 MTP。官方博客明确说 IndexShare 把 1M context 下的**每 token FLOPs 降低 2.9×**；官方 README 和 vLLM Recipe 明确说 GLM-5.2 的 MTP 已从前代的 3 draft tokens 扩展到 **5 draft tokens**。citeturn17search4turn19view0

| 阶段 | 主要瓶颈 | 计算复杂度 | 显存消耗 | 典型优化 |
| -- | -- | --: | --: | -- |
| Prefill | 计算/Kernel 吞吐 | 稠密投影近似 `O(B*S*H^2)`；attention 近似 `O(B*n_h*S*topk*d)`；full indexer 额外开销 | 高 | chunked prefill、Flash/稀疏 attention、IndexShare |
| Decode | HBM 带宽 / cache 访问 / expert dispatch | 每步新 token 近似线性依赖上下文长度；KV 读取 + 活动权重加载主导 | 中 | 压缩 KV cache、FP8 KV、MTP、prefix cache、continuous batching |

从系统角度看，**prefill 更偏 compute-bound，decode 更偏 memory-bandwidth-bound**。这是因为 prefill 把 prompt 整块推进矩阵乘与稀疏检索，而 decode 每一步只生成极少量 token，算子规模变小，但仍需要频繁读取活动权重、KV cache 和 expert 权重，导致带宽成为核心约束。GLM-5.2 的 IndexShare 与 MLA/压缩 KV，本质上都在缓解 decode 期与长上下文期的带宽压力。citeturn17search4turn19view0turn32view1

#### Logits、采样与 Detokenization

Transformers 文档对 `GlmMoeDsaForCausalLM` 的 forward 接口已经给出标准输出：`logits` 的形状是 `(batch_size, sequence_length, vocab_size)`；用于增量生成时，只输入未处理的新 token，cache 由 `past_key_values` 维护。结合 `chat_template.jinja` 可以确认，输出阶段还要处理 `<think>`、`<tool_call>` 等结构化标记。citeturn30view0turn6view0

`reasoning_effort`、`enable_thinking`、tool-calling parser 已经出现在官方模板与 vLLM/SGLang 命令行中，因此对 GLM-5.2 而言，**“采样”不只是温度/top-p 问题，也包括是否进入思考模式、是否走工具调用解析器**。citeturn6view0turn19view0turn33view0

### 参数量拆解与复算

下面给出一版**可复算**的工程拆解。口径说明：

- **官方事实**：总参数约 744B，活动参数约 39B–40B。citeturn12view0turn19view0
- **配置文件读取**：78 层、hidden 6144、256 experts、top-8、3 dense + 75 sparse。citeturn45view2turn45view0
- **工程反推**：把注意力按 MLA 分解，把 expert 按 `moe_intermediate_size=2048` 计算，并把 embedding/lm_head 单独计入。  
- **结论**：按这个公式，**可以复算到约 741B 级别**，已经非常接近官方的 744B；差额可由 indexer/MTP/额外小模块解释。

| 组件 | 参数量公式 | 单层参数量 | 总参数量 | 激活参数量 | 来源/假设 |
| -- | --: | --: | --: | --: | -- |
| Embedding | `V*H = 154880*6144` | 951.6M | 951.6M | 常驻 | 配置直接读取 |
| LM head | `H*V` | 951.6M | 951.6M | decode 常用最后一 token | `tie_word_embeddings=false` |
| MLA attention | `H*q_r + q_r*(n_h*qk) + H*(kv_r+rope) + kv_r*(n_h*(qk_nope+v)) + (n_h*v)*H` | 137.8M | 10.75B | 全层激活 | 配置反推 |
| Dense MLP | `3*H*d_ff = 3*6144*12288` | 226.5M | 679.5M | 全层激活 | 配置反推 |
| Dense layer total | attention + dense MLP | 364.2M | 1.09B（3层） | 1.09B | 3 个 dense 层 |
| Router | `H*n_exp = 6144*256` | 1.57M | 118M（75层） | 118M | 配置直接读取 |
| Routed expert 单 expert | `3*H*d_exp = 3*6144*2048` | 37.75M | — | — | 配置反推 |
| 256 routed experts 总和 | `256*37.75M` | 9.66B | 724.8B（75层） | — | 配置反推 |
| Routed active experts | `top_k*37.75M = 8*37.75M` | 302.0M | 22.65B（75层） | 22.65B | 配置反推 |
| Shared expert | 近似 `3*H*d_exp` | 37.75M | 2.83B（75层） | 2.83B | **工程假设**，与 39B active 口径匹配 |
| 估算总量 | 上述求和 | — | **约 741.1B** | **约 38.9B** | 工程估算 |
| 官方口径 | — | — | **744B** | **39B–40B** | 官方 README / vLLM Recipe |

这组数字有两个非常重要的含义。

第一，**GLM-5.2 的“39B active”是可以用配置反推到的，不是空洞营销数字。** 只要把 sparse 层按 `top-8 routed experts + 1 shared expert + MLA attention + router` 求和，再加上 3 个 dense 层与输入输出头，数量级就在 39B 左右。citeturn12view0turn19view0turn45view2

第二，**把 744B 总量与 39B 活动量混为一谈，会严重误判推理瓶颈。** 总量决定权重落盘与多卡装载门槛，活动量更接近 decode 时每 token 需要触达的热路径规模；而 KV cache、IndexShare、MTP 进一步决定“同样是 39B active”，最终表现会有多快。citeturn17search4turn19view0turn32view1

## KV Cache、显存模型与硬件适配

### KV cache 公式在 GLM-5.2 上为什么要改写

用户给出的经典公式：

```text
KV_cache_bytes = batch_size * seq_len * num_layers * 2 * num_kv_heads * head_dim * bytes_per_element
```

对**传统 head-wise K/V cache** 是成立的；但对 GLM-5.2 这种 **MLA + 压缩 KV** 路线，需要额外写一个“**GLM-5.2 近似式**”。

公开配置里最关键的两个字段是 `kv_lora_rank=512` 与 `qk_rope_head_dim=64`；结合公开工程文档把 `glm_moe_dsa` 明确归入 MLA 路线，可以近似把**每层每 token 的缓存宽度**写成：

```text
MLA_cache_elems_per_token_per_layer ≈ kv_lora_rank + qk_rope_head_dim = 576
MLA_cache_bytes ≈ B * S * L * 576 * bytes_per_element
```

这与传统公式中的

```text
classic_elems_per_token_per_layer = 2 * num_kv_heads * head_dim
                                  = 2 * 64 * 192
                                  = 24576
```

相比，压缩比约为 **42.7×**。这正是 1M context 在工程上变得“有机会落地”的根本原因之一。citeturn45view2turn32view1turn29search15

### KV cache 显存表

下面给出 **BF16** 下的两张表：第一张是用户熟悉的**传统公式基线**；第二张是更符合 GLM-5.2 公开配置的 **MLA 工程估算**。这两张表一起看，最有价值。

#### 传统 head-wise 公式基线

| batch_size | seq_len | dtype | KV cache 显存 | 备注 |
| ---------: | ------: | -- | ----------: | -- |
| 1 | 4K | BF16 | 14.63 GiB | 经典 `2*64*192` 公式 |
| 1 | 32K | BF16 | 117.00 GiB | 单请求长上下文已非常重 |
| 1 | 128K | BF16 | 468.00 GiB | 几乎无法接受 |
| 8 | 32K | BF16 | 936.00 GiB | 多并发不可行 |
| 32 | 32K | BF16 | 3744.00 GiB | 完全不可行 |
| 128 | 8K | BF16 | 3744.00 GiB | 完全不可行 |

#### 更贴近 GLM-5.2 的 MLA 工程估算

| batch_size | seq_len | dtype | KV cache 显存 | 备注 |
| ---------: | ------: | -- | ----------: | -- |
| 1 | 4K | BF16 | 0.34 GiB | `576` 元素/层/token 估算 |
| 1 | 32K | BF16 | 2.74 GiB | 已显著低于传统公式 |
| 1 | 128K | BF16 | 10.97 GiB | 128K 单请求可行性明显改善 |
| 8 | 32K | BF16 | 21.94 GiB | 多并发长上下文开始进入工程可用区 |
| 32 | 32K | BF16 | 87.75 GiB | 仍重，但远低于传统公式 |
| 128 | 8K | BF16 | 87.75 GiB | 短上下文高并发可规划 |

这张表不是“官方明文表”，而是**基于公开配置与 MLA 架构反推的工程估算**。但它与 vLLM 官方 Recipe 里“**8×B200 + FP8 KV cache 才能把 1M context 真正跑满**”、以及 ROCm/ATOM 文档里“**要给 Index cache 与 KV cache 都留 headroom**”的建议是互相解释得通的。citeturn19view0turn32view1

### 完整推理显存模型

对 GLM-5.2，更实用的显存总模型是：

```text
Total_VRAM
= Weight_Memory
+ KV_Cache_Memory
+ Activation_Memory
+ Runtime_Workspace
+ Fragmentation_Overhead
+ Framework_Overhead
```

其中：

- **Weight_Memory**：  
  - BF16 ≈ `744B * 2 bytes ≈ 1.49 TB`  
  - FP8/INT8 约 `744 GB + scale overhead`；官方 FP8 仓库目录体量约 **756 GB**。citeturn12view0turn35view1
  - INT4 裸算约 `372 GB`，但真实检查点通常会更高；公开生态里可见 `NVFP4` 约 **465GB**，以及 MLX 社区讨论里的 `mxfp4` 约 **395GB**。citeturn19view0turn31search6
- **KV_Cache_Memory**：对 GLM-5.2 不宜直接套传统 head-wise 公式，应按 MLA 压缩 cache 估算。citeturn45view2turn32view1
- **Activation_Memory**：prefill 高、decode 低；但多并发 decode 会把 activation/workspace 顶起来。citeturn19view0turn20search0
- **Runtime_Workspace**：包括 Flash/稀疏 attention workspace、cuBLASLt/TensorRT workspace、CUDA Graph、paged/block table、MTP 草稿路径等。citeturn19view0turn21search6
- **Fragmentation_Overhead**：生产环境一般至少预留 5%–20%。这也是 vLLM/ATOM 都强调 `gpu-memory-utilization` 不要一上来拉满的原因。citeturn19view0turn32view1

按这个模型，最值得记住的不是“某块卡理论上能不能放下参数总量”，而是：

1. **官方 BF16：几乎一定需要多卡，且 8×MI300X 才刚刚接近原始权重容量边界。**  
2. **官方 FP8：8×H200 / 8×H20 / 8×B200 / 8×MI355X / 8×MI300X 才进入现实讨论区间。**  
3. **4-bit：仍然不是单卡模型；它只是在“8×L40S / Apple 大内存 / CPU+SSD offload”这类场景里打开了实验性可能性，而非生产性余量。** citeturn19view0turn32view1turn31search6

### 典型硬件资源表

下表以“**能否单卡加载官方权重**”为核心判断标准；“理论 BF16/FP16 算力”和“带宽”优先使用官方数据源。对于 Apple / Ascend 等未统一披露 BF16 峰值的条目，保持 `unknown` 或仅给内存带宽。  

| 硬件 | 显存/内存 | 理论 FP16/BF16 算力 | 内存带宽 | 可否单卡加载 BF16/FP16 | 可否单卡 INT8/FP8 | 可否单卡 INT4 | 推荐并行方式 | 备注 |
| -- | --: | --: | --: | -- | -- | -- | -- | -- |
| H100 80GB SXM | 80GB | 1979 TFLOPS | 3.35 TB/s | 否 | 否 | 否 | TP8+EP | 官方单卡远小于 756GB FP8 权重 citeturn39search0turn35view1 |
| H200 141GB | 141GB | 官方页强调 HBM/带宽，未在本页片段直接列 BF16；同 Hopper 级 | 4.8 TB/s | 否 | 否 | 否 | TP8+EP | vLLM 推荐 8×H200 跑 FP8 标准部署 citeturn39search1turn19view0 |
| A100 80GB | 80GB | 312/624 TFLOPS（PCIe/SXM） | 1.94–2.04 TB/s | 否 | 否 | 否 | TP8 仅实验 | 8×A100 80GB 总显存 640GB，仍低于官方 FP8 检查点体积 citeturn39search2turn35view1 |
| A800 80GB | 80GB | 近 A100 80GB 级 | ~2.0 TB/s | 否 | 否 | 否 | TP8 仅实验 | 中国市场 A100 衍生 SKU；官方 5.2 公开权重仍不“干净 fit” citeturn40search7turn39search2 |
| L40S | 48GB | 362 TFLOPS BF16 / 733 sparsity | 864 GB/s | 否 | 否 | 否 | 多卡 + 低比特 | 更适合量化实验，不适合官方主权重 citeturn39search3 |
| L4 | 24GB | 242 TFLOPS BF16 | 300 GB/s | 否 | 否 | 否 | 不建议 | 容量与带宽都偏小 citeturn40search0 |
| RTX 4090 | 24GB | 消费卡，官方页未列 BF16 | ~1008 GB/s | 否 | 否 | 否 | 社区 GGUF/offload | 只能做非官方极限量化实验 citeturn40search1turn40search9 |
| RTX 5090 | 32GB | 3352 AI TOPS | 1792 GB/s | 否 | 否 | 否 | 社区 GGUF/offload | 比 4090 更适合极端量化，但仍远不够官方主权重 citeturn40search2 |
| MI300X | 192GB | 官方片段未直列 BF16 峰值 | 5.3 TB/s | 否 | 否 | 否 | TP8+EP | 8×MI300X 有条件装下 BF16/FP8，但官方 ROCm Recipe 仍偏向 FP8 citeturn41search3turn19view0 |
| MI325X | 256GB | 公开片段未直接列 BF16；厂商资料有 FP16/FP8 | 6.0 TB/s | 否 | 否 | 否 | TP8+EP | 适合更宽裕的 FP8 / 低比特部署 citeturn41search1 |
| MI250 | 128GB | 362.1 TFLOPS BF16 | 3.2 TB/s | 否 | 否 | 否 | 多卡实验 | 容量不够官方主权重 citeturn41search2 |
| Ascend 910B | 64GB | 公开资料分歧，常见口径约 320–600 TF16/FP16 | 400 GB/s–1.2 TB/s 口径不一 | 否 | 否 | 否 | W8A8/W4A8 + 多机多卡 | **未找到一致官方规格页**；部署更多依赖量化变体和 Ascend 框架适配 citeturn42search0turn38search1 |
| Apple M2 Ultra | 192GB unified | unknown | 800 GB/s | 否 | 否 | 否 | CPU/GPU 混合、社区极端量化 | 容量不足官方 INT4/FP8，适合极限 GGUF 尝试 citeturn42search1turn42search9 |
| Apple M3 Max | 96/128GB unified | unknown | 300–400 GB/s | 否 | 否 | 否 | 不建议官方权重 | 主要适合小模型/极端低比特 citeturn43search0turn43search2 |
| Apple M4 Max | 128GB unified | unknown | 410–546 GB/s | 否 | 否 | 否 | 不建议官方权重 | 仍不足官方 INT4 体量 citeturn43search1turn43search5 |

结论非常明确：**如果目标是“生产可用 + 官方权重 + 1M context”，GLM-5.2 应优先从 8 卡 FP8 架构规划，而不是从单卡幻想出发。**citeturn19view0turn32view1

## 推理框架支持、部署建议与性能边界

### 主流推理框架支持表

| 框架 | 是否支持 GLM-5.2 | 支持版本 | 后端 | 支持精度 | 支持量化 | 支持 MoE | 支持长上下文 | 需要改代码吗 | 已知限制 | 来源 |
| -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| Hugging Face Transformers | 是 | `transformers` 5.12.0+ | PyTorch | BF16；依生态可接 FP8 | 量化由外部生态提供 | 是 | 是 | 官方模型可直接加载 | 大规模生产性能不如专用 serving 引擎 | citeturn30view0turn45view2 |
| vLLM | 是 | 0.23.0+ | CUDA / ROCm | FP8/BF16 | FP8、NVFP4 等 | 是 | 是 | 否 | tool parser + MTP 同时用时建议 main 分支；1M 需大 HBM | citeturn19view0 |
| SGLang | 是 | 官方 release 已列入；README 要求 0.5.13.post1+ | CUDA / ROCm / Ascend | BF16/FP8 | 部分平台量化 | 是 | 是 | 否 | 仍有若干 GLM-5.2 bug/性能 issue | citeturn12view0turn20search7turn20search6 |
| TensorRT-LLM | **间接支持** | 1.2.x 文档期 | NVIDIA PyTorch backend / TRT engine | BF16/FP8/NVFP4 路线 | NVFP4 等 | 是 | 是 | 多半需要按 GLM-5 路线配置 | 文档明确列 GLM-5，不直接列 5.2；但 `glm_moe_dsa` 路线已存在 | citeturn23view0turn21search4turn21search0 |
| LMDeploy | **未找到 GLM-5.2 明确收录** | 当前支持表列 GLM-5 | TurboMind / PyTorch | 依引擎 | 部分量化 | GLM-5 有 | 未确证 | 可能需要改代码 | 不能把“支持 GLM-5”直接等同于“支持 GLM-5.2” | citeturn25search5turn25search0 |
| llama.cpp / GGUF | **社区适配中** | 未正式完成 | ggml | 社区量化 | GGUF | 部分/不完整 | 社区尝试 | 通常需要转换/补丁 | 官方仓库仅见 feature request / 讨论 | citeturn26search0turn26search3turn26search15 |
| Ollama | Cloud 有迹象；本地公开适配未确证 | unknown | Cloud / 本地待定 | cloud 服务端不透明 | community GGUF | unknown | unknown | 本地大概率要走 GGUF | 不宜把 cloud 提供等同于本地官方支持 | citeturn26search2turn26search8turn28search6 |
| NVIDIA NIM / Dynamo | **公开收录到 GLM-5 / 5.1，未见 5.2** | latest 支持矩阵 | vLLM / TRT-LLM 容器 | 视 profile | 视 profile | 是 | 是 | 需等官方 profile | 目前不能把 NIM 的 GLM-5 支持外推到 5.2 | citeturn36search0turn36search5 |
| AMD ROCm / ATOM | 是 | ATOM 最新 recipe | ROCm + AITER | FP8/BF16 | ROCm 相关量化 | 是 | 是 | 基本否 | 某些 ROCm kernel 仍有数值/精度 issue | citeturn32view1turn20search6 |
| Ascend vLLM-Ascend / xLLM / SGLang | 是，但仍在快速适配 | 2026-06 工程态 | Ascend NPU | W8A8/W4AFP8/BF16 视模型 | 是 | 是 | 是 | 经常需要按官方脚本/镜像 | issue 很多，说明仍在磨合期 | citeturn12view0turn38search1turn38search0turn38search10 |
| MLX / Apple Silicon | **未稳定支持** | 社区 PR/issue 中 | MLX | 社区量化 | 若有则为社区 | 是 | 适配中 | 需要改代码 | 已有明确“fails to load” issue | citeturn31search0turn31search19 |
| TGI / DeepSpeed-MII / FasterTransformer / OpenVINO / IPEX-LLM | **未找到公开确证信息** | unknown | unknown | unknown | unknown | unknown | unknown | 很可能需要自研适配 | 本次检索未发现官方直达适配文档 | — |

对“未找到公开确证信息”的框架，我刻意没有写成“不支持”。更准确的表述是：**截至 2026-07-01 本次检索，未找到足以证明“可直接生产使用 GLM-5.2”的公开材料。** 这与“理论上能接入 `transformers` 权重”是两回事。  

### 典型部署方案

| 机器 | 可部署精度 | 推荐框架 | 推荐并行策略 | 最大上下文估算 | 推荐 max batch | 预期瓶颈 | 适用场景 |
| -- | -- | -- | -- | --: | --: | -- | -- |
| 1× H100 80GB | 无官方主权重可用 | — | — | — | — | 显存绝对不足 | 不建议 |
| 1× H200 141GB | 无官方主权重可用 | — | — | — | — | 显存绝对不足 | 不建议 |
| 1× L40S 48GB | 社区低比特才可能 | llama.cpp/GGUF 社区 | CPU+GPU offload | 取决于量化 | 1 | 显存+带宽 | 研究/试玩 |
| 1× RTX 4090 | 社区极限量化 | GGUF / offload | CPU+GPU offload | 很有限 | 1 | 显存+PCIe+RAM | 研究/试玩 |
| 1× MI300X 192GB | 仍不够官方 FP8 | — | — | — | — | 显存不足 | 不建议 |
| 1× Ascend 910B | 仅量化/切片 | vLLM-Ascend/xLLM | 多机更现实 | 很受限 | 很低 | 显存不足 | 不建议单卡 |
| 4× H100 80GB | 无法装官方 FP8 | — | — | — | — | 总显存不足 | 不建议 |
| 8× H100 80GB | 官方 FP8 仍偏紧 | 若用极端量化再说 | TP8 | <1M，且有风险 | 低 | HBM 容量 | 实验性 |
| 8× H200 | **官方 FP8 标准推荐** | vLLM / SGLang | TP8 + 可选 EP | 中高到 1M 视 KV | 低到中 | KV cache / HBM 余量 | 生产 serving |
| 8× B200 | **最适合 1M 官方 FP8** | vLLM / TRT-LLM / SGLang | TP8 + EP | 1M | 中 | 调度与 kernel 稳定性 | 高吞吐生产 |
| 8× A100 80GB | 官方 FP8 不干净 fit | 仅第三方量化 | TP8 | 取决于量化 | 低 | 总显存 | 过渡方案 |
| 8× L40S | 仅 4-bit / offload 级别 | 社区方案 | TP8 + offload | 取决于量化 | 低 | 带宽 | 成本敏感试验 |
| 8× MI300X | **ROCm 路线可行** | vLLM ROCm / ATOM | TP8 + EP | 先从 524K 起调 | 中 | KV 预算 / runtime 余量 | 生产 serving |
| 8× MI355X | **已见公开实测** | ATOM | TP8 | 取决于配置 | 1–64 并发 | 调度/带宽 | 高吞吐生产 |
| 8× Ascend 910B/A3 | 可行但更依赖量化 | vLLM-Ascend / xLLM / SGLang | TP/DP/多机 | 视 W8A8/W4AFP8 配置 | 中 | 适配成熟度 | 国产化部署 |
| Apple M2 Ultra / M3 Max / M4 Max | 仅社区超低比特 | MLX/GGUF 社区 | CPU+统一内存 | 取决于量化 | 1 | 内存容量 | 个人实验 |

如果只给一句实操建议：**生产环境优先 vLLM / SGLang / ROCm ATOM / Ascend 专用栈；硬件优先 8×H200、8×B200、8×MI300X/MI355X、或量化后的 8×Ascend。** 这基本与官方/半官方文档的建议边界一致。citeturn19view0turn32view1turn38search1

### 推理性能指标与已找到的公开 benchmark

公开、可复现实测里，本次检索最完整的是 **ROCm ATOM 在 8×MI355X** 上的基线。它给出了 output throughput、total throughput、TTFT、TPOT，这在 GLM-5.2 公开资料里已经算非常珍贵。citeturn32view1

| 硬件 | dtype | batch / concurrency | context | estimated / measured prefill tokens/s | estimated / measured decode tokens/s | TTFT | TPOT | 来源/假设 |
| -- | -- | --: | --: | --: | --: | --: | --: | -- |
| 8×MI355X | FP8 weights + BF16 KV | 1 | 1024 in / 1024 out | measured total 158 tok/s | measured output 79 tok/s | 102 ms | 12.5 ms | citeturn32view1 |
| 8×MI355X | FP8 weights + BF16 KV | 16 | 1024 / 1024 | measured total 1690 tok/s | measured output 841 tok/s | 95 ms | 18.5 ms | citeturn32view1 |
| 8×MI355X | FP8 weights + BF16 KV | 64 | 1024 / 1024 | measured total 4148 tok/s | measured output 2074 tok/s | 107 ms | 30.0 ms | citeturn32view1 |
| 8×MI355X | FP8 weights + BF16 KV | 1 | 8192 / 1024 | measured total 669 tok/s | measured output 73 tok/s | 409 ms | 13.2 ms | citeturn32view1 |
| 8×MI355X | FP8 weights + BF16 KV | 16 | 8192 / 1024 | measured total 5818 tok/s | measured output 645 tok/s | 418 ms | 23.3 ms | citeturn32view1 |
| 8×MI355X | FP8 weights + BF16 KV | 64 | 8192 / 1024 | measured total 10853 tok/s | measured output 1210 tok/s | 483 ms | 51.3 ms | citeturn32view1 |
| 8×H200 | FP8 + FP8 KV | 32 seq（示意） | 1M 上限视配置 | **未找到公开实测** | decode 上限可按 HBM 带宽与 active bytes/token 粗估 | unknown | unknown | vLLM 推荐配置，但无公开 benchmark citeturn19view0turn39search1 |
| 8×B200 | FP8 + FP8 KV | 32 seq（示意） | 可到 1M | **未找到公开实测** | 同上 | unknown | unknown | vLLM 推荐用于 full 1M context citeturn19view0 |

关于公式，可以用下面两条做“上限直觉”，但绝不能把它们误当成真实吞吐。

```text
decode_tokens_per_second ≈ memory_bandwidth / bytes_read_per_output_token
prefill_tokens_per_second ≈ effective_FLOPS / FLOPs_per_prompt_token
```

对 GLM-5.2，`bytes_read_per_output_token` 至少包含：

- 活动参数页读取；
- KV cache 读取；
- expert 权重与 router；
- MTP 草稿路径额外开销；
- kernel / scheduler / block allocator 开销。  

而 `FLOPs_per_prompt_token` 则还会吃到 full indexer、稀疏检索与长上下文项。因此，**prefill 受长 prompt 长度影响更大，decode 受 HBM 带宽与 MoE 调度影响更大**。citeturn17search4turn19view0turn32view1

### 框架配置建议

#### vLLM

官方 Recipe 已经足够明确，可以直接提炼成下面这组建议。citeturn19view0

| 参数 | 推荐值 | 作用 | 风险 |
| -- | -- | -- | -- |
| `--tensor-parallel-size` | `8` | 744B 级模型的基础切分 | 少于 8 往往装不下 |
| `--kv-cache-dtype` | `fp8_e4m3` 或 `fp8` | 降低 1M context KV 成本 | 会有数值/兼容性要求 |
| `--speculative-config.method` | `mtp` | 启用 GLM-5.2 原生 MTP | acceptance 低时收益下降 |
| `--speculative-config.num_speculative_tokens` | `5` | 对应 GLM-5.2 的 5-token MTP | 某些 workload 反增延迟 |
| `--max-model-len` | 从 `524288` 起调 | 先保守启动，再逐步冲 1M | 过高易 OOM |
| `--max-num-seqs` | 从 `32` 起调 | 控制并发与 KV 预算 | 太大时上下文会顶爆 HBM |
| `--gpu-memory-utilization` | 0.80 左右起 | 给 runtime 留余量 | 拉太高易在图捕获/OOM 时崩 |
| `--tool-call-parser` | `glm47` | tool call 解析 | 与 reasoning parser 组合要匹配 |
| `--reasoning-parser` | `glm45` | `<think>`/推理块解析 | 解析器版本不匹配会出怪错 |

#### SGLang

SGLang 文档核心特性是 RadixAttention、prefix caching、speculative decoding；而 GLM-5.2 已进入 release note 的“New Model Support”。如果用 KT-Kernel / CPU-GPU heterogeneous inference，公开教程建议 TP8、FP8 KV、限制总 tokens、限制并发请求数。citeturn20search0turn20search7turn33view0

| 参数 | 推荐值 | 作用 | 风险 |
| -- | -- | -- | -- |
| `--tp-size` | `8` | 基础并行切分 | 少于 8 很难稳定装载 |
| `--kv-cache-dtype` | `fp8_e4m3` | 降低 cache 压力 | 某些平台仍有 bug |
| `--tool-call-parser` | `glm47` | 工具调用解析 | parser 不匹配会错 |
| `--reasoning-parser` | `glm45` | 推理块解析 | 同上 |
| `--max-total-tokens` | 先保守如 `4096` | 限制服务端总 token 压力 | 太小限制吞吐 |
| `--max-running-requests` | 先如 `8` | 控制并发 | 太大启动/运行易 OOM |
| `--attention-backend` | 依 cookbook/平台 | 稀疏/高性能 kernel | 平台差异大 |
| `reasoning_effort` | `max` | 复现 benchmark 默认 | `high` 会改变延迟/输出习惯 |

#### TensorRT-LLM

公开文档层面，它更像是“**沿 `glm_moe_dsa` / GLM-5 路线适配 GLM-5.2**”，而不是一句话写清“GLM-5.2 开箱即用”。因此建议：

| 参数 / 策略 | 推荐值 | 作用 | 风险 |
| -- | -- | -- | -- |
| `tp_size` | `8` | 基础切分 | 小于 8 的余量很弱 |
| `ep_size` | `8`（若 NVFP4 / MoE 深优化） | 把 experts 分散 | 网络/调度复杂度上升 |
| `kv_cache_config.enable_block_reuse` | `true` | 重用 KV block | 需要验证稳定性 |
| `backend` | 先从 PyTorch backend 起 | 保证兼容 | engine 化路径更复杂 |
| profile | 优先 H200/B200 | 与文档/issue 更一致 | Hopper/Blackwell 之外证据较少 |

#### LMDeploy / llama.cpp / Apple Silicon

- **LMDeploy**：当前官方 supported models 只明确列到 GLM-5；因此对 GLM-5.2 更稳妥的策略是“视为未正式公开支持”。citeturn25search5
- **llama.cpp / GGUF**：如果目标是个人实验，可走 GGUF/极限量化；如果目标是生产，不建议把它当 GLM-5.2 首选框架。citeturn26search0turn26search15
- **MLX / Apple**：当前公开状态更接近“适配中”；大内存 Apple 机器可以玩社区超低比特，但不宜当官方主权重部署平台。citeturn31search0turn31search6

## 信息缺口与结论

### 已知信息缺口

| 问题 | 为什么重要 | 当前证据 | 缺口 | 建议验证方式 |
| -- | -- | -- | -- | -- |
| GLM-5.2 的完整技术报告是否已单独公开 | 决定能否严格确认各 kernel/训练细节 | 官方博客、README、配置已足够，但没有单一“GLM-5.2 报告表格” | 缺少统一论文式披露 | 持续跟踪 Z.ai / arXiv / HF docs |
| DSA indexer 的精确权重形状与 tensor layout | 决定能否严密复现 FLOPs/显存 | 已知 `index_topk=2048`、IndexShare 调度与 `indexer_types` | kernel 级 layout 未统一公开 | 直接阅读 HF/Transformers/NeMo 源码 |
| Tokenizer 的底层算法类型 | 决定 token 统计与迁移兼容性 | 已获取 vocab/chat template，但未抓到 tokenizer_config 细节 | BPE/SentencePiece 未确证 | 检查 `tokenizer.json` / `tokenizer_config.json` |
| MTP 内部头结构与 acceptance 分布 | 决定 speculative decode 上限 | 官方只说“5-token MTP”与 acceptance 提升 | 缺少系统曲线 | 跑公开 recipe 做 acceptance profile |
| TensorRT-LLM 对 GLM-5.2 的“正式支持等级” | 决定生产可用性 | 已有 `glm_moe_dsa` 架构入口与 issue | 5.2 是否 Day-0/GA 不明 | 关注官方 deployment guide 更新 |
| LMDeploy / TGI / OpenVINO / IPEX-LLM 的 5.2 状态 | 决定多平台选型 | 本次未找到充足公开证据 | 可能仅未文档化，也可能确实未支持 | 直接搜 PR/commit / supported models 页面 |
| Ascend 910B/910C 的统一规格与 5.2 公开 benchmark | 决定国产化部署容量规划 | 有适配与量化权重线索 | 官方硬件规格与实测分散 | 结合华为官方硬件页与 vLLM-Ascend 文档二次核验 |
| H100/H200/B200/L40S/4090/5090 上的 GLM-5.2 公开 benchmark | 决定性能边界判断 | 仅找到部署 recipe / issue，缺少系统 benchmark | 缺少统一实测 | 跟踪 vLLM/SGLang benchmark issue 与厂商博客 |

### 最终结论

本次深度检索的结论可以压缩成一句话：

**GLM-5.2 已经不是“信息全无”的黑盒模型，而是一个可以被系统工程角度较好刻画的 744B 级 `glm_moe_dsa` 稀疏大模型：78 层、6144 hidden、256 routed experts、top-8、1 shared expert、1M context、MLA 风格压缩 KV、DSA sparse attention、每四层复用一次的 IndexShare，以及 5-token MTP。** 这些结论的核心依据不是社区传闻，而是官方 README、官方模型卡与官方 `config.json`。citeturn12view0turn28search1turn45view2

同时也必须说清楚另一半现实：

**GLM-5.2 仍然不是“随便找块大卡就能跑”的模型。** 对官方主权重而言，单卡 H100/H200/MI300X/4090/5090 都不属于合理选择；生产部署的现实分界线基本在 **8 卡 FP8**，最好是 8×H200、8×B200、8×MI300X/MI355X，或者面向国产化的 Ascend 量化多卡方案。citeturn19view0turn32view1turn38search1

如果你的目标是**做系统级推理性能研究**，我认为最有价值的三个抓手不是再问“它是不是 744B”，而是继续往下验证这三件事：

1. **MLA 压缩 KV 在不同框架中的真实 cache layout 与带宽占比。**  
2. **IndexShare 对 prefill / decode 各自带来的 FLOPs 与 latency 改善幅度。**  
3. **5-token MTP 在真实 agent/coding workload 上的 acceptance-rate 曲线。**

这三件事，才真正决定 GLM-5.2 在系统层面的性能边界。