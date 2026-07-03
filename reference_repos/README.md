# Reference repositories

These public repositories were selected from `../步骤 1 内容.md` and cloned on
2026-07-03 as code-reading references for the AK single-card MoE inference work.

Clone policy:

- Repositories are shallow clones (`--depth 1`) to keep the project light.
- Model weights were not downloaded.
- Treat these directories as upstream references. Put project code outside these
  cloned repositories unless intentionally patching a fork later.

| Local path | Upstream | Current commit | Why it is here |
| --- | --- | --- | --- |
| `vllm/` | https://github.com/vllm-project/vllm | `4c3c64f` | Core LLM serving engine; reference for KV cache, scheduler, MoE execution, and planned vLLM trace patches. |
| `vllm-ascend/` | https://github.com/vllm-project/vllm-ascend | `c3ac524` | Ascend hardware plugin for vLLM; reference for CANN/NPU integration, Docker/runtime setup, and Ascend tests. |
| `ktransformers/` | https://github.com/kvcache-ai/ktransformers | `8e46e58` | Heterogeneous CPU/GPU LLM inference framework; reference for CPU-side expert execution, memory tiering, and async scheduling patterns. |
| `neo/` | https://github.com/NEO-MLSys25/NEO | `33e4a0f` | MLSys 2025 NEO code; reference for CPU offload of decode attention and KV cache plus GPU/CPU pipeline scheduling. |
| `finemoe-eurosys26/` | https://github.com/IntelliSys-Lab/FineMoE-EuroSys26 | `5c58468` | FineMoE demo implementation; reference for fine-grained expert offloading, prefetching, and caching. |
| `qwen3/` | https://github.com/QwenLM/Qwen3 | `7a2f61f` | Lightweight model-family docs/examples for Qwen3 and Qwen3 MoE usage. This is not a model-weight download. |

## Mentioned but not cloned

| Item | Reason |
| --- | --- |
| DALI | Found paper/preprint entries, but no confirmed official public implementation during this pass. |
| FluxMoE | Found paper/preprint entries, but no confirmed official public implementation during this pass. An unrelated tiny `FluxMoE` repo was not cloned. |
| MoE-APEX | Found ACM/author-page entries, but no confirmed public code repository during this pass. |
| MindIE | Mentioned as a runtime option, but no public source repository was found. |
| Hugging Face model repos | The plan names Qwen3/Mixtral/DeepSeek model weights as experiment inputs; weights were intentionally not downloaded here. |

If the scope expands beyond the exact source document, `EfficientMoE/MoE-Infinity`
is a nearby public baseline for MoE expert offloading and may be worth adding.
