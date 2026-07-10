# DeepSeek-V4-Flash Benchmark Cards

This directory holds local planning artifacts for P5-P9. It does not contain model payloads.

Current objects:

| model_object_id | source | server path | role |
| --- | --- | --- | --- |
| `deepseek_v4_flash_official_hf` | Hugging Face `deepseek-ai/DeepSeek-V4-Flash` | `/data/node0_disk1/Public/DeepSeek-V4-Flash` | project primary runtime object; mixed FP8 plus FP4 experts |
| `deepseek_v4_flash_w8a8_mtp_modelscope` | ModelScope `DeepSeek-V4-Flash-w8a8-mtp` | `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp` | retired inventory only; do not start or convert |

Boundaries:

- Downloaded model files do not prove Ascend runtime compatibility.
- The official checkpoint is mixed FP8 plus FP4 experts, not pure FP8 and not a `--quantization ascend` object.
- The completed v0.20.2/v0.20.2rc1 probe failed at the NPU quantization gate before weight load. The current four-card task builds an isolated v0.22.1/v0.22.1rc1 stack, which registers `deepseek_v4_fp8`, then reruns the same checkpoint without an explicit `--quantization`.
- W8A8 is retired from future project execution; its inventory remains historical evidence only.
- P5 is a startup and long-context smoke, not a benchmark or bottleneck attribution run.
- Any server task must be written by clearing and rewriting `通信模块/docs/developer-to-server.md`, with body and returned attachments kept within the 70KB communication limit.

P5 deliverables:

- `deepseek_v4_flash_model_objects.yaml`: model object registry and boundaries.
- `p5_readiness_card.yaml`: current official-checkpoint runtime gate and future eight-card boundary.
- `workloads/p5_4card_startup_probe.yaml`: completed v0.20.2/v0.20.2rc1 probe with `diagnostic_red_quant_format` result.
- `workloads/p5_4card_fp8_stack_upgrade_probe.yaml`: current NPU 4-7 isolated-stack build and TP4 startup/request probe.
- `workloads/p5_8card_context_ladder.yaml`: future fixed-output context ladder, blocked until the four-card gate succeeds and eight-card scope is separately authorized.
- `workloads/fixed_output_smoke.yaml`: older P6 fixed-output smoke template retained for continuity.

Planning references:

- `docs/EXPERIMENT_PLAN.md`: canonical P5-P9 stage graph, evidence gates and experiment contracts.
- `docs/DEEPSEEK_V4_FLASH_ASCEND_PLAN.md`: DeepSeek-specific runtime, model-object and boundary plan.
- `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`: P8 runtime capability matrix, StateObject control plane, KV/Prefix and MoE prototype details.

Next artifact boundary:

- Do not create P6 benchmark cards until the P5 server result is graded green/yellow/red and the final successful command is archived.
- Do not create P8 real-move cards before P8.0 capability probe and P8.1 observe-only trace pass.
- MindIE cards are conditional on a separately confirmed server runtime; current server evidence does not show MindIE as available.
