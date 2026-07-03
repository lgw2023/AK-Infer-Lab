# Reference repositories

This directory collects public code references mentioned by, or directly useful
for following up on, these two local AK notes:

- `/Volumes/SSD1/小算力项目/AK 协同/代表工作原文硬件拓扑映射精读笔记.md`
- `/Volumes/SSD1/小算力项目/AK 协同/Deep Research 反向回顾报告 第三轮可核验版 小算力大模型推理落地与推理仿真系统构建.md`

Deduplication policy:

- If an upstream repository was already present, keep the existing directory and
  update or verify it in place.
- Do not create parallel copies with alternate names.
- Treat these directories as third-party references. Put project code outside
  these repositories unless intentionally creating a fork later.
- Model weights were not downloaded.

Most git repositories here are shallow clones. `tensorrt-llm/` is also a sparse
checkout because the full repository is large. `servegen/` is a GitHub source
archive snapshot because repeated git shallow clones disconnected during
`index-pack`.

## Selected references

| Local path | Upstream | Local state | Why it is here |
| --- | --- | --- | --- |
| `neo/` | https://github.com/NEO-MLSys25/NEO | existing, git `33e4a0f` | NEO; CPU offload for decode attention and KV cache, plus CPU/GPU pipeline scheduling. |
| `ktransformers/` | https://github.com/kvcache-ai/ktransformers | existing, git `8e46e58` | KTransformers; heterogeneous CPU/GPU inference, CPU-side expert execution, and memory-tiering patterns. |
| `finemoe-eurosys26/` | https://github.com/IntelliSys-Lab/FineMoE-EuroSys26 | existing, git `5c58468` | FineMoE; fine-grained MoE expert offload, prefetch, and caching reference. |
| `vllm/` | https://github.com/vllm-project/vllm | existing, git `4c3c64f` | vLLM baseline for scheduler, paged KV cache, disaggregated prefill/decode connectors, and serving integration. |
| `vllm-ascend/` | https://github.com/vllm-project/vllm-ascend | existing, git `c3ac524` | Ascend plugin for vLLM; CANN/NPU integration and Ascend runtime adaptation. |
| `mooncake/` | https://github.com/kvcache-ai/Mooncake | added, git `a325291` | Mooncake / KV Pool line; KV cache-centric serving and transfer architecture. |
| `lmcache/` | https://github.com/LMCache/LMCache | added, git `979719d` | LMCache; KV cache reuse, storage tiers, and serving integration. |
| `lmcache-ascend/` | https://github.com/LMCache/LMCache-Ascend | added, git `dbd6545` | LMCache Ascend adaptation; useful for NPU-side KV cache integration patterns. |
| `mllm/` | https://github.com/UbiquitousLearning/mllm | added, git `c4fd487` | llm.npu codebase; mobile/NPU-oriented LLM serving reference. |
| `servegen/` | https://github.com/alibaba/ServeGen | added, source archive of main at `765b7a2` | ServeGen; realistic LLM serving workload generation and trace/simulator input modeling. |
| `llmservingsim/` | https://github.com/casys-kaist/LLMServingSim | added, git `f6848b8` | LLMServingSim; event-driven serving simulation baseline. |
| `burstgpt/` | https://github.com/HPMLL/BurstGPT | added, git `d895a53` | BurstGPT trace/workload reference for bursty LLM serving demand. |
| `dynamo/` | https://github.com/ai-dynamo/dynamo | added, git `867d9ab` | NVIDIA Dynamo; disaggregated serving/runtime reference. |
| `nixl/` | https://github.com/ai-dynamo/nixl | added, git `fec498f` | NIXL transport layer used by disaggregated serving stacks. |
| `tensorrt-llm/` | https://github.com/NVIDIA/TensorRT-LLM | added, sparse git `a6e0a5d` | TensorRT-LLM disaggregated serving and batch manager reference. |
| `sglang/` | https://github.com/sgl-project/sglang | added, git `05bc3f2` | SGLang runtime and serving reference for scheduler/cache/API comparisons. |
| `llama.cpp/` | https://github.com/ggml-org/llama.cpp | added, git `fdb1db8` | Local inference baseline; relevant to ProfInfer-style profiling references and CPU-oriented execution. |
| `chakra/` | https://github.com/mlcommons/chakra | added, git `21585d8` | MLCommons Chakra; trace schema / workload representation reference. |
| `ccl-bench/` | https://github.com/cornell-sysphotonics/ccl-bench | added, git `1d257f0` | Collective communication benchmark reference for topology and communication-cost modeling. |

## Already present, not duplicated

These directories existed before this pass and were left in place.

| Local path | Upstream | Local state | Note |
| --- | --- | --- | --- |
| `mindie-llm/` | https://github.com/Ascend/MindIE-LLM | git `0695772` | Ascend LLM inference engine reference. |
| `mindie-motor/` | https://github.com/Ascend/MindIE-Motor | git `a7de90c` | Ascend serving framework reference. |
| `mindie-turbo/` | https://github.com/Ascend/MindIE-Turbo | git `fba896e` | Ascend inference acceleration plugin reference. |
| `mindie-sd/` | https://github.com/Ascend/MindIE-SD | git `3c29c51` | Ascend inference patterns outside the core LLM scope. |
| `qwen3/` | https://github.com/QwenLM/Qwen3 | git `7a2f61f` | Model-family docs/examples only; no weights downloaded. |

## Not cloned in this pass

The notes mention the works below, but this pass did not find a confirmed
official public code repository, or found only paper/author pages without a
usable repository link. They should not be added until a public upstream is
confirmed.

| Work | Reason |
| --- | --- |
| FlexInfer | Paper/OpenReview entries found; no confirmed official public implementation. |
| HeteroInfer / HeteroLLM | Mentioned as related heterogeneous serving work; no confirmed code repository. |
| HybriMoE | No confirmed official public repository found in this pass. |
| DALI | Paper/preprint found; no confirmed official implementation. |
| FluxMoE | Paper/preprint found; no confirmed official implementation. |
| MoE-APEX | Paper/author entries found; no confirmed public implementation. |
| Bidaw | Paper/USENIX entries found; no confirmed public implementation. |
| SolidAttention | Paper/USENIX entries found; no confirmed public implementation. |
| CacheSlide | Author page indicated a code slot, but no usable public repository link was available. |
| Tutti | Paper claims open-source intent, but no confirmed public repository link was found. |
| ProfInfer | Paper entries found; no confirmed implementation repository. |
| KVCache in the Wild | Paper entries found; no confirmed implementation repository. |
| ECHO | Paper entries found; no confirmed implementation repository. |
| ITME | Paper entries found; no confirmed implementation repository. |
