我按一个比较严格的标准重新查了：**必须能找到“精确 checkpoint / 精确量化版本在 Ascend NPU 上成功启动或完成推理验证”的公开一手证据**，不能因为“DeepSeek-V4-Flash 架构支持 Ascend”就推导所有量化版都支持。

## 结论

**你刚才 Top 10 的 10 个 Hugging Face 版本里，截至 2026 年 7 月 7 日，我没有找到任何一个“精确仓库版本已被公开验证在 Ascend NPU 上成功运行”的直接证据。**

但是，**DeepSeek-V4-Flash 本身已经被 vLLM-Ascend 正式验证运行；经过 Ascend 专用 W8A8-MTP 量化的版本也是明确跑通的。** vLLM-Ascend 官方教程直接指定 `DeepSeek-V4-Flash-w8a8-mtp`，给出了 Atlas 800 A2/A3 单机部署命令，并使用 `--quantization ascend`。A2 配置是 64GB×8，A3 是 128GB×8。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/tutorials/models/DeepSeek-V4-Flash.html))

MindSpeed-LLM 的官方支持矩阵也已经把 `DeepSeek-V4-Flash 284B` 列入 Ascend 支持列表，认证状态为 `Test`，测试集群规模记录为 `8×16`。([GitHub](https://github.com/Ascend/MindSpeed-LLM/blob/master/docs/zh/pytorch/models/supported_models.md))

### 你 Top 10 的逐项判断

| 热度排名 | HF 版本                                   | Ascend 精确版本已验证？                  | 我的判断                                       |
| -------- | ----------------------------------------- | ---------------------------------------- | ---------------------------------------------- |
| 1        | `antirez/deepseek-v4-gguf`                | ❌ 未找到                                 | **不建议直接认定支持**                         |
| 2        | `huihui-ai/...abliterated-ds4-GGUF`       | ❌ 未找到                                 | **明确没有 Ascend 测试**                       |
| 3        | `unsloth/DeepSeek-V4-Flash`               | ⚠️ 基础架构已验证，精确 checkpoint 未验证 | **最接近可适配候选**                           |
| 4        | `nvidia/DeepSeek-V4-Flash-NVFP4`          | ❌ 未找到                                 | **不适合直接搬到 Ascend**                      |
| 5        | `cyberneurova/...abliterated-GGUF`        | ❌ 未找到                                 | **GGUF 路线，未验证**                          |
| 6        | `bartowski/DeepSeek-V4-Flash-GGUF`        | ❌ 未找到                                 | **理论有 CANN 路线，但无实测证据**             |
| 7        | `0xSero/DeepSeek-V4-Flash-180B`           | ❌ 未找到                                 | **高度 NVIDIA/DGX Spark 特化**                 |
| 8        | `teamblobfish/DeepSeek-V4-Flash-GGUF`     | ❌ 未找到                                 | **GGUF/CANN 理论路线，未验证**                 |
| 9        | `Intel/DeepSeek-V4-Flash-W4A16-AutoRound` | ❌ 未找到                                 | **值得做 Ascend 转换验证，但不可直接称已跑通** |
| 10       | `0xSero/DeepSeek-V4-Flash-162B`           | ❌ 未找到                                 | **高度 NVIDIA/DGX Spark 特化**                 |

------

## 1. antirez GGUF：有 CANN backend，不代表这个 DS4 quant 跑通过 Ascend

这是最容易产生误判的一个。

`antirez/llama.cpp-deepseek-v4-flash` 是一个 DS4 专用 llama.cpp fork。它继承的 llama.cpp README backend 表中确实列出了 **CANN → Ascend NPU**。([GitHub](https://github.com/antirez/llama.cpp-deepseek-v4-flash))

但 antirez 对自己的 DeepSeek V4 Flash 实现写得很明确：

> 代码实际运行验证的是 CPU 和 Metal。

其 README 明确说 DS4 实现 “runs both with CPU and Metal backends”；没有说 CANN/Ascend 跑通。([GitHub](https://github.com/antirez/llama.cpp-deepseek-v4-flash))

所以：

**`antirez/deepseek-v4-gguf` = ❌ 不能标记为 Ascend 已验证。**

我的判断是，它存在一条技术上的实验路径：

```
GGUF → upstream llama.cpp DeepSeek V4 support → CANN backend
```

因为当前 llama.cpp 本身同时列出了 DeepSeek V4 支持和 CANN Ascend backend。([GitHub](https://github.com/ggml-org/llama.cpp?ref=codersera.com&utm_source=chatgpt.com))

但**我没有找到 DeepSeek-V4-Flash + 这个 80.8GiB IQ2_XXS/Q2_K checkpoint + Ascend 910B/950 的成功日志**。

因此严格讲只能标：

> **理论可尝试，未验证**

------

## 2. Huihui DS4 GGUF：模型卡甚至明确写“只测了 RTX 6000 Pro”

这个版本可以明确排除“Ascend 已验证”。

Huihui 模型卡明确表示，它的 quants 是为 `DS4(antirez/ds4)` 和 llama.cpp 制作的；测试环境是 Windows/WSL2/Ubuntu 24.04、RTX 6000 Pro、CUDA 13.0。模型卡随后明确写：

> Only the RTX 6000 Pro has been tested; other hardware has not been tested.

支持硬件部分列的是 Metal 和 NVIDIA CUDA，没有 Ascend。([Hugging Face](https://huggingface.co/huihui-ai/Huihui-DeepSeek-V4-Flash-abliterated-ds4-GGUF))

因此：

**`huihui-ai/Huihui-DeepSeek-V4-Flash-abliterated-ds4-GGUF` = ❌ 明确未验证 Ascend。**

而且它是 abliterated 权重，再叠加 DS4 专用 GGUF codec。即使将 DS4 图执行移植到 CANN，仍要单独验证 IQ2_XXS、Q2_K、Q8_0 混合 tensor 的 CANN kernel/offload。

------

## 3. Unsloth：Top 10 中我认为“最接近 Ascend 可适配”的一个

`unsloth/DeepSeek-V4-Flash` 本身是 Safetensors/Transformers `deepseek_v4` checkpoint，模型卡提供标准 Transformers、vLLM 和 SGLang 加载方式。([Hugging Face](https://huggingface.co/unsloth/DeepSeek-V4-Flash))

这和 GGUF/DS4 有很大区别。

因为 **vLLM-Ascend 已经完成 DeepSeek-V4 架构的端到端支持**，当前 release notes 明确列出了：

- DeepSeek V4 model architecture
- DSA attention backend
- KV cache management
- distributed inference
- MTP
- DeepSeek V4 on Ascend 950 end-to-end support

([GitHub](https://github.com/vllm-project/vllm-ascend/releases?utm_source=chatgpt.com))

所以从**模型结构**角度：

> `unsloth/DeepSeek-V4-Flash` 和 Ascend 已支持的 `deepseek_v4` 架构是同一路。

但是问题在于**权重精度格式**。

Unsloth 这个 repo 的模型页面标记为 FP8/8-bit，并引用官方 DeepSeek V4 Flash FP4+FP8 Mixed checkpoint。([Hugging Face](https://huggingface.co/unsloth/DeepSeek-V4-Flash))

而 vLLM-Ascend 官方验证 recipe 用的是：

> ```
> DeepSeek-V4-Flash-w8a8-mtp
> ```

并通过：

```bash
--quantization ascend
```

加载 Ascend 专用量化格式。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/tutorials/models/DeepSeek-V4-Flash.html))

因此：

**`unsloth/DeepSeek-V4-Flash` 不能直接标“已跑通 Ascend”。**

但 Top 10 中，**这是我认为最值得拿来做 `msmodelslim → Ascend W8A8` 转换的候选之一**。

我的评级：

> 🟡 **架构已验证；精确 checkpoint 未验证；适合转换成 Ascend 专用 W8A8。**

------

## 4. NVIDIA NVFP4：不要直接拿去 Ascend

`nvidia/DeepSeek-V4-Flash-NVFP4` 的模型卡明确说明，它使用 NVIDIA Model Optimizer 做 NVFP4 PTQ。([Hugging Face](https://huggingface.co/nvidia/DeepSeek-V4-Flash-NVFP4?utm_source=chatgpt.com))

而 vLLM-Ascend 当前发布说明写的是：

- Ascend 950 增加 **W4A8 MXFP4**
- MXFP8 FlashCommV3
- W4A8 MoE compressed tensors

([vLLM](https://docs.vllm.ai/projects/ascend/en/main/user_guide/release_notes.html?utm_source=chatgpt.com))

注意这里是 **MXFP4/W4A8**，不是 NVIDIA ModelOpt 的 **NVFP4 checkpoint**。

我搜索 vLLM-Ascend 官方仓库，也没有找到：

```text
nvidia/DeepSeek-V4-Flash-NVFP4
```

的实际验证记录。

因此：

**`nvidia/DeepSeek-V4-Flash-NVFP4` = ❌ 不建议直接在 Ascend 上尝试。**

它的问题不是 DeepSeek V4 架构，而是：

> **checkpoint quant metadata、scale representation、packed weight layout 和 kernel contract 都属于 NVIDIA ModelOpt/NVFP4 路线。**

Ascend 950 的 MXFP4 kernel 支持**不能自动推出 NVFP4 checkpoint 可直接加载**。

------

## 5. CyberNeurova GGUF：未验证

这是 abliterated GGUF。

我没有找到这个精确 repository ID 在：

- vLLM-Ascend
- Ascend 官方支持列表
- llama.cpp Ascend/CANN issues

中的成功运行记录。

所以：

> ❌ **未验证**

技术上仍然只能走 llama.cpp CANN 的实验路线。

------

## 6. Bartowski MXFP4 GGUF：非常值得实验，但不能说已验证

Bartowski 的模型卡是标准 llama.cpp/GGUF 路线，模型为 MXFP4 GGUF。([Hugging Face](https://huggingface.co/bartowski/DeepSeek-V4-Flash-GGUF?utm_source=chatgpt.com))

当前 upstream llama.cpp：

- 已列 DeepSeek V4 支持
- 已有 CANN Ascend NPU backend

([GitHub](https://github.com/ggml-org/llama.cpp?ref=codersera.com&utm_source=chatgpt.com))

这使它成为一个**有趣的 Ascend 实验候选**。

尤其 vLLM-Ascend 最新版本已经开始支持 Ascend 950 的 **W4A8 MXFP4 quantization**。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/user_guide/release_notes.html?utm_source=chatgpt.com))

但仍然要强调：

> llama.cpp CANN 的 MXFP4 op 支持 ≠ Bartowski DeepSeek V4 MXFP4 GGUF 已经跑通。

我没有找到精确成功日志。

因此我的评级是：

> 🟡 **理论兼容性较高 / 值得 PoC，但未验证。**

在 Top 10 里，如果你的目标是研究 **GGUF + CANN**，我会优先测 Bartowski，而不是 Huihui abliterated。

------

## 7 和 10. 0xSero 180B / 162B：不建议作为 Ascend 首测对象

这两个版本虽然很吸引人，因为 REAP 之后只有 180B/162B，但它们的 runtime 是**高度 NVIDIA DGX Spark 特化的**。

180B 模型卡明确写：

- NVFP4/MXFP4 expert weights
- FP8 KV cache
- hardware target：DGX Spark / GB10 / SM121
- 需要修改 vLLM router 来支持非标准 160 experts
- MXFP4 memory layout patch
- FlashInfer CUDA IPC fix
- CUTLASS 4.5.1 workaround

([Hugging Face](https://huggingface.co/0xSero/DeepSeek-V4-Flash-180B))

甚至它的验证硬件明确是：

> single DGX Spark / GB10 / SM121

模型卡提供了精确 CUDA/vLLM Docker image 和 SHA。([Hugging Face](https://huggingface.co/0xSero/DeepSeek-V4-Flash-180B))

所以它不是简单的：

```text
Safetensors + standard DeepSeek V4
```

而是：

```text
REAP
→ 非标准 expert count
→ router remapping
→ MXFP4/NVFP4 packed experts
→ NVIDIA-specific patched vLLM runtime
```

Ascend 虽然支持 DeepSeek V4，但**不意味着支持 K160/K144 的非标准专家数和这套 packed expert 权重**。

因此 180B 和 162B：

> 🔴 **没有 Ascend 验证，且移植工作量明显较高。**

不过长期看，我觉得 **REAP + Ascend W8A8/W4A8** 是非常值得做的路线。

正确方法不是直接加载 0xSero checkpoint，而更可能是：

```text
DeepSeek-V4-Flash
        ↓
REAP K160/K144 expert pruning
        ↓
修 Ascend MoE router / expert count
        ↓
msmodelslim W8A8 或 Ascend 950 W4A8 MXFP4
        ↓
vLLM-Ascend
```

------

## 8. TeamBlobFish GGUF：和 Bartowski 类似，未验证

TeamBlobFish 模型卡给的是标准 llama.cpp/GGUF 启动方法。([Hugging Face](https://huggingface.co/teamblobfish/DeepSeek-V4-Flash-GGUF?utm_source=chatgpt.com))

没有 Ascend/CANN 测试记录。

所以：

> 🟡 **存在 llama.cpp CANN 实验路线，但没有公开验证。**

我会把它排在 Bartowski 后面，因为 Bartowski 的 MXFP4 路线和 Ascend 950 当前增加的 MXFP4 能力在“codec 方向”上更接近；不过这只是**技术路线相似性的推断，不是兼容性证明**。vLLM-Ascend 最新 release notes 明确新增的是 W4A8 MXFP4。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/user_guide/release_notes.html?utm_source=chatgpt.com))

------

## 9. Intel W4A16 AutoRound：我认为是第二值得做 Ascend 转换验证的版本

Intel 模型明确是：

```text
W4A16
group_size = 128
RTN
AutoRound
```

并跳过 compressor、indexer.weights_proj 等层。([Hugging Face](https://huggingface.co/Intel/DeepSeek-V4-Flash-W4A16-AutoRound))

vLLM-Ascend 历史 roadmap/issue 明确推进过 W4A16/W4A8 MoE quantization support；相关官方 issue 也提到 W4A16 Ascend quantization 适配。([GitHub](https://github.com/vllm-project/vllm-ascend/issues/4378?utm_source=chatgpt.com))

但我对精确名称做了搜索：

```text
Intel/DeepSeek-V4-Flash-W4A16-AutoRound
```

在 vLLM-Ascend 官方仓库中**没有找到实际成功运行记录**。

所以：

> 🟡 **量化方向接近 Ascend 可支持路线，但 exact checkpoint 未验证。**

而且还有一个额外风险：Intel 这个 artifact 使用 AutoRound 自己的 quantization representation；Ascend 的量化 loader 通常期待 Ascend/msmodelslim 格式。

因此不能直接认为：

```bash
vllm serve Intel/DeepSeek-V4-Flash-W4A16-AutoRound
--quantization ascend
```

就能运行。

**大概率需要权重转换或重新从源 checkpoint 量化。**

------

# 我的最终排序：Ascend 候选优先级

不是 HF 热度，而是按 **“Ascend 落地可能性”** 排：

| Ascend PoC 优先级 | Top 10 版本                               | 原因                                                      |
| ----------------- | ----------------------------------------- | --------------------------------------------------------- |
| **1**             | `unsloth/DeepSeek-V4-Flash`               | 标准 Safetensors/deepseek_v4 架构；适合重新做 Ascend W8A8 |
| **2**             | `Intel/DeepSeek-V4-Flash-W4A16-AutoRound` | W4A16方向有价值；建议转换/重新量化                        |
| **3**             | `bartowski/DeepSeek-V4-Flash-GGUF`        | DeepSeek V4 + llama.cpp CANN + MXFP4，有实验价值          |
| **4**             | `teamblobfish/DeepSeek-V4-Flash-GGUF`     | llama.cpp CANN 理论路线                                   |
| **5**             | `antirez/deepseek-v4-gguf`                | DS4 极致压缩，但 DS4 只明确验证 CPU/Metal                 |
| **6**             | `0xSero/DeepSeek-V4-Flash-162B`           | REAP 很有价值，但需改 Ascend router/量化                  |
| **7**             | `0xSero/DeepSeek-V4-Flash-180B`           | 同上，K160 非标准 experts                                 |
| **8**             | `CyberNeurova abliterated GGUF`           | 无直接 Ascend 价值增益                                    |
| **9**             | `Huihui abliterated DS4 GGUF`             | 模型卡明确只测试 RTX 6000 Pro                             |
| **10**            | `NVIDIA NVFP4`                            | NVIDIA ModelOpt/NVFP4 特化，不适合直接搬 Ascend           |

## 我给你的直接建议

**如果目标是“找一个 DeepSeek-V4-Flash 量化版，现在就在昇腾上部署”，不要从 Top 10 选。**

直接使用 vLLM-Ascend 官方验证的：

> **`DeepSeek-V4-Flash-w8a8-mtp`**

官方教程已经给出单机验证配置：

```text
Atlas 800 A3: 128GB × 8
或
Atlas 800 A2: 64GB × 8
```

并明确使用：

```bash
--quantization ascend
--tensor-parallel-size 8
--enable-expert-parallel
--tokenizer-mode deepseek_v4
--speculative-config '{"num_speculative_tokens": 1,"method": "mtp","enforce_eager": true}'
```

这是目前我查到的**证据最扎实的 Ascend DeepSeek-V4-Flash 量化部署路线**。([vLLM](https://docs.vllm.ai/projects/ascend/en/main/tutorials/models/DeepSeek-V4-Flash.html))

**如果你的真实目标是“找 128GB/256GB 级别、比官方 W8A8 更小的 DeepSeek-V4-Flash，在昇腾 910B/910C/950 上跑”——那结论会完全不同。** 我建议下一步直接专门梳理 **Ascend 910B / A2、A3、Ascend 950 分硬件的可行量化路线，并重点研究 REAP-162B + Ascend W8A8/W4A8 和 Bartowski MXFP4+CANN 两条路线**。