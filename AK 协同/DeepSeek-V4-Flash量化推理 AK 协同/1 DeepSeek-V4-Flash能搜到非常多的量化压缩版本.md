已整理完成。我按 **2026-07-06 抓取快照**，对 Hugging Face `deepseek-ai/DeepSeek-V4-Flash` 的 Quantizations / Model Tree 逐页枚举，并按仓库 ID 去重整理了 **90 个唯一仓库**。抓取过程中 HF 计数从 89 变化到 90，分页边界也发生漂移；最新出现的 `unsloth/DeepSeek-V4-Flash-GGUF` 已纳入，但其模型页当时返回 401，因([Hugging Face](https://huggingface.co/models?other=deepseek_v4))([Hugging Face](https://huggingface.co/models?other=base_model%3Aquantized%3Adeepseek-ai%2FDeepSeek-V4-Flash)) Excel

[下载《DeepSeek-V4-Flash Hugging Face 量化/压缩版本全量梳理》](sandbox:/mnt/data/DeepSeek-V4-Flash_HF_Quantization_Catalog_2026-07-06.xlsx)

工作簿有 3 张表：

| Sheet            | 内容                                                         |
| ---------------- | ------------------------------------------------------------ |
| **全量仓库清单** | 90 个唯一 HF 仓库逐条整理，共 15 个字段                      |
| **策略族详解**   | 把大量重复/镜像仓库归并成 20 条真正有技术差异的路线          |
| **选型与结论**   | DGX Spark 128GB、Apple Silicon、Blackwell/vLLM、llama.cpp、极限内存等场景的决策矩阵 |

“全量仓库清单”逐仓库包含：**HF 仓库、策略族、派生性质、HF 页面显示大小、真实结构解释、核心量化策略、位宽/codec、MTP/推测解码、格式/runtime、明确磁盘大小、硬件/内存建议、A/B/C 证据等级、风险备注和直接 HF 来源 URL**。

## 梳理后最关键的结论

**第一，DeepSeek-V4-Flash 的“原版”本身已经是量化/混合低精度 checkpoint。** 官方模型是 **284B 总参数、13B 激活、1M context**；官方明确写的是 **MoE expert parameters 使用 FP4，绝大多数其余参数使用 FP8**。所以很多 HF 仓库并非“BF16 原模型 → Q4”，而是在一个已经 FP4+FP8 的源 checkpoint 上继续重封装、换 codec、压专家或裁专家。 ([Hugging Face](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash))

**第二，HF 显示的 `167B / 51B / 22B / 7B / 1B params` 大量不能理解成模型被蒸馏成了这些参数规模。** 例如完整官方模型仍是 284B/13B；而 MTP 仓库实际上只是抽出的 speculative drafter，SSD Flash-MoE 的 `7B` 类显示可能对应 dense 部分/sidecar 统计，4-layer artifact 也只是部分层。独立 MTP 模型卡明确说明它是抽出的 MTP layers，需要与 target 模型共同使用。 ([Hugging Face](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash))线，我归并后大致是：

| 路线                      | 典型代表                     | 核心做法                                                     | 已核明确体积例子     |
| ------------------------- | ---------------------------- | ------------------------------------------------------------ | -------------------- |
| 原生低精度保真重封装      | nsparks / bartowski / anemll | 保留 MXFP4 experts、FP8 dense，尽量不二次量化                | ~146–156GB           |
| GGUF 专家低 bit           | antirez / tarruda            | experts IQ2/Q2/Q3/Q4，attention/shared 保 Q8，控制路径 F16/F32 | ~80.8–153.3GiB       |
| Imatrix GGUF              | jedisct1 / pinklily69        | 对 expert FFN 做 activation-importance calibration           | ~81–114GB            |
| MLX affine                | mlx-community / osmapi       | 3/4/5/6/8-bit affine                                         | 已核版本 ~155–231GB  |
| MLX mixed sensitive quant | Thump604 / Deviad            | experts 2/3/4bit，敏感路径 6/8bit/FP16                       | Q4Q8 173GB           |
| TurboQuant / JANGTQ       | JANGQ / Osaurus / osmapi     | 2/4/8-bit MXTQ lane mix，形成 2.3/3.4/4.5/5.6 effective bits | 79.6–164.25GB        |
| NVFP4                     | NVIDIA                       | MoE transformer linear 权重与激活 NVFP4 PTQ                  | Blackwell 路线       |
| NVFP4 + FP8               | RedHatAI / canada-quant      | experts NVFP4，attention FP8_BLOCK                           | 带 MTP 172GB         |
| GPTQ W4A16 + FP8          | canada-quant                 | experts INT4 GPTQ gs128，attention FP8                       | 143GB / 带 MTP 159GB |
| AutoRound                 | Intel                        | W4A16 gs128 RTN，跳过敏感模块                                | 专用 INT4 路线       |
| 2-bit VQ / MQ2            | iggerask / hipfire           | 只把 routed experts 压到 2-bit VQ/MQ2                        | hipfire 86.184GB     |
| REAP + 量化               | 0xSero / sleepyeldrazi       | 先删专家，再 NVFP4/Q2/Q8                                     | 94–103GB 等          |
| Lite / NE50               | lovedheart / Akicou          | 256 experts → 192 或 206                                     | NE50 ~130.85GB       |
| SSD Flash-MoE             | anemll                       | experts 从 SSD 动态分页，非全量驻内存                        | 完整包 ~156GB        |
| MTP / DSpark              | Inferencer / fraserprice     | speculative decoding 模块                                    | 非“量化小模型”       |
| Abliterated               | Huihui / CyberNeurova        | 行为编辑后再 GGUF/FP8/DSpark                                 | 不是量化算法         |

其中 antirez 的 80.8 GiB DS4 GGUF 是非常典型的“专家激进量化、关键路径保高精度”：expert gate/up 为 IQ2_XXS、down 为 Q2_K，attention/shared/output 为 Q8_0，router/embed/indexer/compressor/HC 为 F16，norm/sink/bias 为 F32。 ([Hugging Face](https://huggingface.co/antirez/deepseek-v4-gguf))-quant 的 W4A16-FP8-MTP 则是另一条非常工程化的路线：routed experts 用 INT4 W4A16、group size 128 的对称 GPTQ；attention 使用 FP8_BLOCK 128×128；MTP block 原样保留 BF16，成品约 159GB。 ([Hugging Face](https://huggingface.co/canada-quant/DeepSeek-V4-Flash-W4A16-FP8-MTP))iggerask/2bit-GB10` 把 routed experts 做成 2-bit VQ，同时 attention/shared/lm_head 保 NVFP4、控制路径 BF16、KV cache FP8；模型卡也很坦率地给出了 perplexity 从 FP4 源的 3.66 增至 4.64，因此我没有把“2-bit”简单标成免费压缩。 ([Hugging Face](https://huggingface.co/iggerask/DeepSeek-V4-Flash-2bit-GB10))uant/JANGTQ 这一族尤其值得单独看。例如 osmapi Q3.4 实际是 **39 组 expert projection 用 2-bit MXTQ、90 组用 4-bit MXTQ，得到 3.3953 effective bits**；Q4.5 则是 113 组 4-bit、16 组 8-bit，得到 4.4961 effective bits。也就是说名字里的“3.4-bit/4.5-bit”不是一种真正的 3.4-bit 标量数据类型，而是 2/4/8-bit lane mix 后的有效平均位宽。 ([Hugging Face](https://huggingface.co/osmapi/DeepSeek-V4-Flash-TQ-Q3.4-MLX))中我专门设置了 **证据等级 A/B/C**：A 是模型卡明确给出 tensor recipe、结构或大小；B 是同族模型卡与仓库命名/metadata 交叉核对；C 是空 README、镜像、具体 quant tag 未统一披露或实时新增仓库。这样可以直接筛选掉那些“仓库名看起来很明确、实际没有技术说明”的版本。





已经按 **Hugging Face 收藏数（Likes）优先、近 30 天下载数次优先**重新排序，并把热度数据标注进原表。

HF 模型详情页将下载指标标为 **“Downlo([Hugging Face](https://huggingface.co/mlx-community/DeepSeek-V4-Flash-3bit-DQ?utm_source=chatgpt.com))它误写成累计下载量。Likes 则按 HF 当前页面的点赞/收藏数记录。([Hugging Face](https://huggingface.co/Deviad/DeepSeek-V4-Flash-MLX-Q4Q8)) 更新后的 Excel

[下载：DeepSeek-V4-Flash 量化版本全量梳理＋HF 热度排行](sandbox:/mnt/data/DeepSeek-V4-Flash_HF_Quantization_Catalog_with_Popularity_2026-07-07.xlsx)

本次热度数据快照时间为 **2026 年 7 月 7 日 00:35，新加坡时间**。HF 的量化 Model Tree 当前显示 90 个模型，但实时分页出现跨页重复卡片；我按原清单的 90 个唯一仓库 ID 一一匹配，并对分页遗漏的 `mlx-community/DeepSeek-V4-Flash-3bit-DQ` 单独核查了模型详情页。([Hugging Face](https://huggingface.co/models?other=base_model%3Aquantized%3Adeepseek-ai%2FDeepSeek-V4-Flash)) 当前收藏数 Top 10

| 排名 | HF 仓库                                                      | Likes   | 近30天下载    |
| ---- | ------------------------------------------------------------ | ------- | ------------- |
| 1    | antirez/deepseek-v4-gguf                                     | **307** | **6,410,000** |
| 2    | huihui-ai/Huihui-DeepSeek-V4-Flash-abliterated-ds4-GGUF      | **92**  | 585,000       |
| 3    | unsloth/DeepSeek-V4-Flash                                    | **69**  | 1,000         |
| 4    | nvidia/DeepSeek-V4-Flash-NVFP4                               | **61**  | 519,000       |
| 5    | cyberneurova/CyberNeurova-DeepSeek-V4-Flash-abliterated-GGUF | **55**  | 23,500        |
| 6    | bartowski/DeepSeek-V4-Flash-GGUF                             | **32**  | 241,000       |
| 7    | 0xSero/DeepSeek-V4-Flash-180B                                | **30**  | 5,330         |
| 8    | teamblobfish/DeepSeek-V4-Flash-GGUF                          | **26**  | 30,700        |
| 9    | Intel/DeepSeek-V4-Flash-W4A16-AutoRound                      | **24**  | 1,680         |
| 10   | 0xSero/DeepSeek-V4-Flash-162B                                | **24**  | 933           |

这些数值来自 HF 当时的模型列表与模型详情页快照，因此会随下载和点赞实时变化。([Hugging Face](https://huggingface.co/models?other=base_model%3Aquantized%3Adeepseek-ai%2FDeepSeek-V4-Flash))el 里我做了两处调整：

**「全量仓库清单」** 已直接重排，新增 `HF收藏数（Likes）`、`HF近30天下载数` 和 `排序规则` 三列，并用数据条突出热度。

**「热度排行」** 是新增 Sheet，90 个仓库按 `Likes ↓ → 近30天下载 ↓` 排序，并附 Top 15 收藏数图表，同时保留策略族、核心量化 recipe、位宽、模型大小、证据等级和 HF 来源。

其中 `unsloth/DeepSeek-V4-Flash-GGUF` 是刚建立的新仓库；核对时详情页显示 **Downloads last month 为 “-”**，所以表中下载数暂按 0 记录，而 Likes 使用详情页快照值。([Hugging Face](https://huggingface.co/unsloth/DeepSeek-V4-Flash-GGUF))