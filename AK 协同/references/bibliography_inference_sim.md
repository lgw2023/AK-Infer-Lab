# 推理落地与推理仿真系统 Deep Research 文献索引

来源文档（2 份）：

- `Deep Research 反向回顾报告 第一轮 小算力大模型推理落地与推理仿真系统构建的 Deep Research 报告.md`
- `Deep Research 反向回顾报告 第二轮 小算力大模型推理落地与推理仿真系统构建的 Deep Research 报告.md`

> 这两份 MD **不含直接 URL**，文献从正文表格、强相关论文总表、参考文献清单与精读清单中提取。完整映射见 `references/inference_sim_urls.json`。

## 统计

| 类别 | 数量 |
|---|---|
| 识别唯一文献/系统 | 62 |
| 本地 PDF（全库累计） | 130 |
| 本地网页快照（全库累计） | 104 |
| 本轮新下载 PDF | 25 |
| 本轮新下载/补抓网页快照 | 29 |

## 学术论文 PDF（按方向）

### CPU / NPU / 异构协同

| 名称 | 会议/来源 | 本地文件 |
|---|---|---|
| NEO | MLSys 2025 | `NEO-MLSys25-writeup.pdf`, `NEO__arxiv-2411.01142.pdf` |
| FlexInfer | MLSys 2025 | `FlexInfer.pdf`, `FlexInfer-OpenReview.pdf` |
| llm.npu | ASPLOS 2025 | `llm.npu__arxiv-2407.05858.pdf` |
| HeteroInfer / HeteroLLM | SOSP 2025 | `HeteroInfer__arxiv-2501.14794.pdf`, `HeteroInfer-SOSP-PDF.pdf` |
| APEX | arXiv 2025 | `APEX__arxiv-2506.03296.pdf` |
| shadowNPU | MobiSys 2026 | `shadowNPU__arxiv-2508.16703.pdf` |
| ScoutAttention | arXiv 2026 | `ScoutAttention__arxiv-2603.27138.pdf` |
| Select-N | arXiv 2025 | `Select-N__arxiv-2502.08182.pdf` |
| Toppings | USENIX ATC 2025 | `Toppings-ATC25.pdf` |
| Weaver | USENIX ATC 2025 | `Weaver-ATC25.pdf` |

### MoE 专家管理

| 名称 | 会议/来源 | 本地文件 |
|---|---|---|
| KTransformers | SOSP 2025 | `KTransformers.pdf` |
| FineMoE | EuroSys 2026 | `fMoE-FineMoE__arxiv-2502.05370.pdf` |
| HybriMoE | arXiv 2025 | `HybriMoE__arxiv-2501.04595.pdf` |
| DAOP | arXiv 2025 | `DAOP__arxiv-2501.10375.pdf` |
| DALI | arXiv 2026 | `DALI__arxiv-2602.03495.pdf` |
| FluxMoE | arXiv 2026 | `FluxMoE__arxiv-2604.02715v2.pdf`；旧 `FluxMoE__arxiv-2601.07343.pdf` / arXiv `2601.07343` 为无关油基泥浆成像论文，不能作为 FluxMoE 证据 |
| MoE-APEX | ASPLOS 2026 | `MoE-APEX.pdf` |
| FlashMoE | arXiv 2026 | `FlashMoE-SSD__arxiv-2601.17063.pdf` |

### KV / Prefix / 分层内存

| 名称 | 会议/来源 | 本地文件 |
|---|---|---|
| Mooncake | FAST 2025 | `Mooncake__arxiv-2407.00079.pdf` |
| LMCache | tech report 2025 | `LMCache__arxiv-2510.09665.pdf` |
| KVCache Cache in the Wild | USENIX ATC 2025 | `KVCache-in-the-Wild__arxiv-2503.01526.pdf` |
| IMPRESS | FAST 2025 | `IMPRESS-FAST25.pdf` |
| Bidaw | FAST 2026 | `Bidaw-FAST26.pdf` |
| CacheSlide | FAST 2026 | `CacheSlide.pdf` |
| SolidAttention | FAST 2026 | `SolidAttention-FAST26.pdf` |
| Tutti | arXiv 2026 | `Tutti__arxiv-2605.03375.pdf`；旧缓存 `Tutti__arxiv-2602.04182.pdf` 内容不符，不能作为 Tutti 证据 |
| ITME | arXiv 2026 | `ITME__arxiv-2606.12556.pdf` |
| SpeCache | ICML 2025 | `SpeCache__arxiv-2503.16163.pdf` |
| Strata | arXiv 2025 | `Strata__arxiv-2508.18572.pdf` |
| SwiftCache | arXiv 2026 | `SwiftCache__arxiv-2606.16135.pdf` |
| TableCache | arXiv 2026 | `TableCache__arxiv-2601.08743.pdf` |
| Marconi | MLSys 2025 | `Marconi__arxiv-2411.19379.pdf`, `Marconi-MLSys25.pdf` |

### Prefill/Decode 拆分与调度

| 名称 | 会议/来源 | 本地文件 |
|---|---|---|
| Context Parallelism | MLSys 2025 | `Context-Parallelism__arxiv-2411.01783.pdf` |
| TaiChi | arXiv 2025 | `TaiChi__arxiv-2508.01989.pdf` |
| TokenFlow | EuroSys 2026 | `TokenFlow__arxiv-2510.02758.pdf` |
| Resource Multiplexing (LLMStation) | USENIX ATC 2025 | `Resource-Multiplexing-ATC25.pdf` |

### 仿真 / Trace / Benchmark

| 名称 | 会议/来源 | 本地文件 |
|---|---|---|
| ServeGen | NSDI 2026 | `ServeGen__arxiv-2505.09999.pdf`, `ServeGen-NSDI26.pdf` |
| BurstGPT | dataset / arXiv | `BurstGPT__arxiv-2401.17644.pdf` |
| ProfInfer | arXiv 2026 | `ProfInfer__arxiv-2601.20755.pdf` |
| CCL-Bench | arXiv 2026 | `CCL-Bench__arxiv-2605.06544.pdf` |
| Chakra | MLCommons / arXiv | `Chakra-MLSys2026__arxiv-2605.11333.pdf` |
| LLM Energy-Performance Tradeoffs | arXiv 2025 | `LLM-Energy-Performance-Tradeoffs__arxiv-2505.04671.pdf` |
| LLMServingSim2.0 | arXiv 2025/2026 版本线索 | `LLMServingSim-2.0__arxiv-2511.07229.pdf`, `LLMServingSim-2.0__arxiv-2602.23036.pdf` |

## 工业框架 / 官方文档快照

| 名称 | 本地文件 |
|---|---|
| SGLang HiCache | `web/SGLang-HiCache.html`, `web/SGLang-HiCache-docs.html` |
| vLLM APC / KV connector | `web/vLLM-APC-docs.html`, `web/vLLM-KV-connector-docs.html` |
| vLLM KV offloading | `web/vLLM-KV-offloading-docs.html`, `web/LMCache-docs.html` |
| TensorRT-LLM disaggregated | `web/TensorRT-LLM-disaggregated-docs.html`, `web/TensorRT-LLM-KV-exchange.html` |
| NVIDIA Dynamo / NIXL | `web/NVIDIA-Dynamo-GitHub.html`, `web/NVIDIA-Dynamo-docs.html`, `web/NIXL-GitHub.html` |
| NVIDIA Dynamo / KV offloading 增量快照 | `web/NVIDIA-Dynamo-KV-offloading-live.html`, `web/NVIDIA-Dynamo-introduction-live.html` |
| vLLM-Ascend | `web/vLLM-Ascend.html`, `web/vLLM-Ascend-docs.html`, `web/vLLM-Ascend-release-notes-live.html`, `web/vLLM-Ascend-UCM-deployment-live.html`, `web/vLLM-Ascend-KV-pool-live.html`, `web/vLLM-Ascend-KV-CPU-offload-live.html` |
| Mooncake 增量快照 | `web/Mooncake-home-live.html`, `web/vLLM-Mooncake-Store-blog-2026-05-06.html` |
| MindIE-LLM | `web/Ascend-MindIE.html`, `web/MindIE-docs.html` |
| ServeGen 开源仓库 | `web/ServeGen-GitHub.html` |

## 无法直接获取正式 PDF（已保存替代快照）

| 名称 | 说明 | 替代来源 |
|---|---|---|
| ECHO | OSDI 2026 正式 PDF 截至 2026-07-01 尚未公开 | `web/ECHO-OSDI26-page.html` |
| AdaGen | EuroSys 2026 无公开 arXiv | `web/AdaGen-EuroSys26-page.html` |
| TurboInfer | 未找到同名正式论文（ASPLOS 2026 program 中无此条目） | `web/TurboInfer-ASPLOS26-program.html` |

## 本轮新下载清单（25 PDF + 29 网页）

**PDF：** ServeGen, ScoutAttention, Select-N, SpeCache, Strata, FlashMoE-SSD, TaiChi, Marconi, Context-Parallelism, shadowNPU, TokenFlow, SwiftCache, TableCache, ServeGen-NSDI26, IMPRESS-FAST25, Toppings-ATC25, Weaver-ATC25, Bidaw-FAST26, SolidAttention-FAST26, Resource-Multiplexing-ATC25, Marconi-MLSys25, Context-Parallelism-MLSys25, SpeCache-OpenReview, Tutti 正确 arXiv 版本, LLMServingSim2.0 2511.07229 版本

**网页：** NVIDIA-Dynamo/NIXL GitHub, MindIE, ServeGen GitHub, AdaGen/ECHO/Strata 页面, TensorRT-LLM/vLLM 文档补抓，FAST/NSDI 2026 官方 technical sessions，vLLM-Ascend release/UCM/KV offload/KV pool，NVIDIA Dynamo KV offloading，Mooncake 主页与 vLLM Mooncake Store 博客等

下载日志：`references/inference_sim_download_results.json`
增量核验日志：`references/inference_sim_incremental_search_2026-07-01.json`
