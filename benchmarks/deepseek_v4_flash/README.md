# DeepSeek-V4-Flash Benchmark Cards

This directory holds local planning artifacts for P5-P9. It does not contain model payloads and does not define a server task by itself.

Current objects:

| model_object_id | source | local path | role |
| --- | --- | --- | --- |
| `deepseek_v4_flash_w8a8_mtp_modelscope` | ModelScope `DeepSeek-V4-Flash-w8a8-mtp` | `/Volumes/Elements/DeepSeek-V4-Flash-w8a8-mtp` | P6 eight-card baseline first candidate |
| `deepseek_v4_flash_official_hf` | Hugging Face `deepseek-ai/DeepSeek-V4-Flash` | `/Volumes/Elements/DeepSeek-V4-Flash` | source checkpoint, conversion/readiness and boundary candidate |

Boundaries:

- Local paths are not server paths.
- Downloaded model files do not prove Ascend runtime compatibility.
- The official HF checkpoint must not be treated as the vLLM-Ascend W8A8-MTP `--quantization ascend` runtime object before validation.
- The user will copy model directories to the server. Server paths are filled only after that copy is complete.
- Any server task must be written by clearing and rewriting `通信模块/docs/developer-to-server.md`, with body and returned attachments kept within the 70KB communication limit.

P5 deliverables:

- `deepseek_v4_flash_model_objects.yaml`: model object registry and boundaries.
- `p5_readiness_card.yaml`: readiness checklist before server handoff.
- `workloads/fixed_output_smoke.yaml`: fixed-output smoke workload template for later P6 handoff.
