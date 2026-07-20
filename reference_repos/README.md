# Reference repositories

`reference_repos/` contains third-party source used only for P8 code reading,
interface comparison, trace-schema study, and simulator calibration. It is not
the implementation directory of AK-Infer-Lab.

Inventory verified through: **2026-07-20 (Asia/Shanghai)**.

## Refresh result

- The collection now has **25 shallow Git checkouts plus 1 verified source
  archive snapshot**.
- `vllm-moet/` was added on 2026-07-20 at upstream `main@66c65f3` as an
  NVIDIA Blackwell SM120 comparison reference. No submodules or model weights
  were downloaded.
- Of the 23 Git checkouts that already existed, 13 fast-forwarded and 10 were
  already at their configured upstream tips. `unified-cache-management/` was
  added. A temporary `vllm-ascend-v0.18.0/` checkout was subsequently removed;
  version tags now live inside the two rolling vLLM checkouts.
- `servegen/` remains a source archive because its Git shallow clone previously
  disconnected during `index-pack`. Its 864 local blobs match the GitHub tree
  for `main@765b7a2339bbe7658205be8a95a5076f9f389590` exactly.
- Every Git checkout is shallow. `tensorrt-llm/` is also sparse. No submodules
  were initialized and no model weights were downloaded.
- The root `.gitignore` ignores `reference_repos/**`; only this inventory is
  tracked by AK-Infer-Lab.

## P8 implementation and runtime references

| Local path | Upstream / ref | Local state | P8 role |
| --- | --- | --- | --- |
| `vllm-ascend/` | [vllm-project/vllm-ascend](https://github.com/vllm-project/vllm-ascend), `main`; fetched tags through `v0.22.1rc1` | local `main@73998d1`; target tag `5f6faa0` | Rolling discovery plus the exact current P5 source object; `origin/main@dbcbf02` was observed without changing the working tree. |
| `vllm/` | [vllm-project/vllm](https://github.com/vllm-project/vllm), `main`; fetched tags through `v0.22.1` | local `main@e5588e4`; target tag `0decac0` | Rolling scheduler/KV/serving reference plus the exact current P5 vLLM source object; `origin/main@c227aaa` was observed without changing the working tree. |
| `lmcache-ascend/` | [LMCache/LMCache-Ascend](https://github.com/LMCache/LMCache-Ascend), `main` | `79fc599` | Ascend KV connector, NPU transfer, HCCL/HIXL, and adapter patterns. |
| `unified-cache-management/` | [ModelEngine-Group/unified-cache-management](https://github.com/ModelEngine-Group/unified-cache-management), `develop` | `22f0145` | UCM implementation reference for external KV/prefix object management and DRAM-first tiering. |
| `mindie-llm/` | [Ascend/MindIE-LLM](https://github.com/Ascend/MindIE-LLM), `master` | `238c543` | MindIE LLM source reference for prefix/KV, expert-parallel, and Ascend runtime comparison. Source presence does not prove the server runtime is installed. |
| `mindie-motor/` | [Ascend/MindIE-Motor](https://github.com/Ascend/MindIE-Motor), `master` | `a7de90c` | Ascend serving/orchestration comparison path. |
| `mindie-turbo/` | [Ascend/MindIE-Turbo](https://github.com/Ascend/MindIE-Turbo), `master` | `fba896e` | Ascend inference acceleration plugin reference. |
| `mooncake/` | [kvcache-ai/Mooncake](https://github.com/kvcache-ai/Mooncake), `main` | `98ff4e4` | KV Pool, transfer engine, storage tier, and KV-event reference. |
| `lmcache/` | [LMCache/LMCache](https://github.com/LMCache/LMCache), `dev` | `622e146` | KV reuse, CPU/storage tiers, connectors, events, and control-plane reference. |
| `ktransformers/` | [kvcache-ai/ktransformers](https://github.com/kvcache-ai/ktransformers), `main` | `7c021b4` | Heterogeneous CPU/accelerator execution, expert placement, and memory-tiering reference. |
| `finemoe-eurosys26/` | [IntelliSys-Lab/FineMoE-EuroSys26](https://github.com/IntelliSys-Lab/FineMoE-EuroSys26), `master` | `5c58468` | Fine-grained MoE expert trace, offload, prefetch, and cache policy reference. |
| `vllm-moet/` | [kacper-daftcode/vllm-Moet](https://github.com/kacper-daftcode/vllm-Moet), `main` | `66c65f3`; generated vLLM fork source `0fd0e14` | Sign-symmetric routed-expert W2, FP4 delta/confidence recovery, GPU/DRAM/NVMe expert tiering, batched miss restore, graph replay, and cache KPI reference. Apache-2.0; author-reported Blackwell results only, not an Ascend implementation or independently reproduced benchmark. |
| `neo/` | [NEO-MLSys25/NEO](https://github.com/NEO-MLSys25/NEO), `master` | `33e4a0f` | CPU offload for decode attention/KV and heterogeneous pipeline scheduling. |

Each vLLM repository has one working tree on current `main`. The target release
tags are fetched into those same shallow repositories; no parallel version
snapshot directory is maintained. Future AK-owned code should be created on a
first-party branch or worktree outside `reference_repos/`, starting from the tag
commits below rather than editing these third-party reference trees in place.

## Target development stack

| Component | Target version | Local source evidence | Current evidence boundary |
| --- | --- | --- | --- |
| vLLM | `0.22.1` | `reference_repos/vllm`, tag `v0.22.1@0decac0` | Current P5 source object; server environment build pending. |
| vLLM-Ascend | `0.22.1rc1` | `reference_repos/vllm-ascend`, tag `v0.22.1rc1@5f6faa0` | Registers `deepseek_v4_fp8`; server runtime validation pending. |
| CANN | `9.0.0` | Existing project/server evidence | Runtime dependency; no source checkout added here. |
| PyTorch | `2.10.0` | Target stack declaration | Runtime dependency; no source checkout added here. |
| torch-npu | `2.10.0` | Target stack declaration | Runtime dependency; no source checkout added here. |
| triton-ascend | `3.2.1` | Target stack declaration | Runtime dependency; no source checkout added here. |

## Trace, workload, and simulator references

| Local path | Upstream / ref | Local state | P8/P9 role |
| --- | --- | --- | --- |
| `llmservingsim/` | [casys-kaist/LLMServingSim](https://github.com/casys-kaist/LLMServingSim), `main` | `f6848b8` | Event-driven serving simulator, trace, model, and hardware configuration reference. |
| `chakra/` | [mlcommons/chakra](https://github.com/mlcommons/chakra), `main` | `21585d8` | Trace schema and workload representation reference. |
| `ccl-bench/` | [cornell-sysphotonics/ccl-bench](https://github.com/cornell-sysphotonics/ccl-bench), `main` | `1d257f0` | Collective communication benchmark and topology-cost reference. |
| `servegen/` | [alibaba/ServeGen](https://github.com/alibaba/ServeGen), `main` archive | `765b7a2`, 864/864 blobs verified | Realistic serving workload generation and trace-input modeling. |
| `burstgpt/` | [HPMLL/BurstGPT](https://github.com/HPMLL/BurstGPT), `main` | `d895a53` | Bursty request-trace reference for simulator workload distributions. |

## Supplemental comparison references

| Local path | Upstream / ref | Local state | Boundary |
| --- | --- | --- | --- |
| `dynamo/` | [ai-dynamo/dynamo](https://github.com/ai-dynamo/dynamo), `main` | `f553c46` | Disaggregated serving/runtime comparison; NVIDIA-oriented, not an Ascend drop-in. |
| `nixl/` | [ai-dynamo/nixl](https://github.com/ai-dynamo/nixl), `main` | `644facf` | Transport abstraction reference; hardware/backend assumptions require revalidation on Ascend. |
| `tensorrt-llm/` | [NVIDIA/TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM), `main` | sparse `8043934` | Batch manager and disaggregated-serving comparison; NVIDIA-specific implementation. |
| `sglang/` | [sgl-project/sglang](https://github.com/sgl-project/sglang), `main` | `b76dd0b` | Scheduler/cache/API comparison; not an Ascend implementation base here. |
| `llama.cpp/` | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp), `master` | `082b326` | CPU/local-inference and profiling comparison. |
| `mllm/` | [UbiquitousLearning/mllm](https://github.com/UbiquitousLearning/mllm), `main` | `c4fd487` | Mobile/NPU-oriented LLM serving reference. |
| `mindie-sd/` | [Ascend/MindIE-SD](https://github.com/Ascend/MindIE-SD), `master` | `ddd5cc8` | Ascend inference patterns outside the core LLM path. |
| `qwen3/` | [QwenLM/Qwen3](https://github.com/QwenLM/Qwen3), `main` | `7a2f61f` | Model-family documentation/examples only; no weights. |

## Use and license boundaries

- These are read-only third-party references. New AK implementation belongs
  outside `reference_repos/`; copying code requires a separate license and
  dependency review.
- Root license files were present in the refreshed snapshot for all rows except
  `ccl-bench/` and `qwen3/`. Do not copy or redistribute code from those two
  directories until their applicable upstream terms are confirmed.
- Some repositories contain additional third-party notices or component-level
  licenses; the upstream files govern, not this inventory.
- A mechanism implemented for CUDA/GPU hardware is reference evidence only.
  Ascend support remains `documented_unverified` until P8.0 source/runtime probes
  and real Atlas 800T A2 validation close the capability gate.

## Not cloned

The works below still lack a confirmed usable official public implementation in
the project evidence reviewed so far. Do not add look-alike or unofficial repos
without a new provenance audit.

| Work | Current boundary |
| --- | --- |
| FlexInfer | Paper/OpenReview entries found; no confirmed official public implementation. |
| HeteroInfer / HeteroLLM | Related heterogeneous-serving work; no confirmed code repository. |
| HybriMoE | No confirmed official public repository. |
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
