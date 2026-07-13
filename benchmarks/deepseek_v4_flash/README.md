# DeepSeek-V4-Flash Benchmark Cards

This directory holds local planning artifacts for P5-P9. It does not contain model payloads.

Current objects:

| model_object_id | source | server path | role |
| --- | --- | --- | --- |
| `deepseek_v4_flash_w8a8_mtp_modelscope` | ModelScope `DeepSeek-V4-Flash-w8a8-mtp` | `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp` | project primary runtime object; eight-card P5 authorized |
| `deepseek_v4_flash_official_hf` | Hugging Face `deepseek-ai/DeepSeek-V4-Flash` | `/data/node0_disk1/Public/DeepSeek-V4-Flash` | historical mixed-checkpoint diagnostic and source inventory only |

Boundaries:

- Downloaded model files do not prove Ascend runtime compatibility.
- The official source checkpoint is mixed FP8 plus FP4 experts, not pure FP8 and not a `--quantization ascend` object.
- The v0.22.1/v0.22.1rc1 four-card diagnostic fixed plugin, allocator and ACL path issues, loaded all 46 shards, then failed at FP4 expert post-processing because `customize_dtype` is unsupported by the current SoC.
- The project will not build an adapter for that mixed route. W8A8-MTP is the only future P5/P6 runtime object.
- The 279.41 GiB W8A8 checkpoint exceeds four-card aggregate HBM. The first eight-card run loaded all 70 shards but failed before server-ready in the MTP drafter DSA-CP graph-capture path.
- The no-MTP isolation reached graph-ready; after replacing the incompatible client path and correcting the cached-wrapper MRO assertion, the exact no-MTP graph cell completed one `4096+64` HTTP 200 request.
- That success is frozen as a degraded P8 runtime baseline only. MTP and the 128K ladder remain unvalidated, and the smoke timing is not a P6 performance result.
- P5 is a startup and long-context smoke, not a benchmark or bottleneck attribution run.
- Any server task must be written by clearing and rewriting `通信模块/docs/developer-to-server.md`, with body and returned attachments kept within the 70KB communication limit.

P5 deliverables:

- `deepseek_v4_flash_model_objects.yaml`: model object registry and boundaries.
- `p5_readiness_card.yaml`: W8A8 route decision, mixed-checkpoint final result and active eight-card P5 boundary.
- `workloads/p5_4card_startup_probe.yaml`: completed v0.20.2/v0.20.2rc1 probe with `diagnostic_red_quant_format` result.
- `workloads/p5_4card_fp8_stack_upgrade_probe.yaml`: completed isolated-stack build attempt; core stack passed, but runtime was not attempted because of an overbroad full-environment `pip check` gate.
- `workloads/p5_4card_fp8_runtime_resume_probe.yaml`: completed NPU 4-7 retry; it reached worker initialization but failed before weight loading at the generic accelerator allocator assertion.
- `workloads/p5_4card_fp8_allocator_patch_delivery_probe.yaml`: completed diagnostic; the session overlay removed the allocator error and exposed the later upstream NVIDIA model-route failure.
- `workloads/p5_4card_fp8_plugin_activation_probe.yaml` and `workloads/p5_4card_fp8_acl_path_probe.yaml`: completed historical diagnostics for the retired mixed route.
- `workloads/p5_8card_context_ladder.yaml`: completed first-attempt contract; the run reached weight load but failed in MTP graph capture before the ladder.
- `workloads/p5_8card_no_mtp_isolation.yaml`: completed W8A8 no-MTP graph/eager isolation contract; graph server reached ready but the client failed before request dispatch.
- `workloads/p5_8card_no_mtp_tokenizer_retry.yaml`: completed native-tokenizer retry; token generation passed, but an over-strict cached-wrapper class assertion stopped execution.
- `workloads/p5_8card_no_mtp_tokenizer_mro_retry.yaml`: completed MRO-validated retry with one successful no-MTP `4096+64` request.
- `workloads/p6_0_no_mtp_degraded_stabilization.yaml`: completed P6.0 contract; two new identical fresh lifecycles extended the prior P5 success to three consecutive no-MTP `4096+64` successes.
- `workloads/p6_1_no_mtp_minimal_unprofiled_control.yaml`: completed bounded P6.1 control; warmup plus three measured `4096+64+c1` requests passed with grade `yellow_degraded_minimal_unprofiled_control_measured`.
- `workloads/p6_1r_bounded_mtp_reference_repair.yaml`: active bounded MTP repair retry2; retry1 proved the one-line overlay crosses the original graph-capture failure and reaches server-ready, then exposed a completion-payload/chat-endpoint HTTP 400 contract mismatch. Retry2 preserves the patch/runtime/payload and one-lifecycle/one-request budget while correcting only the request/evidence/overlay gates.
- `patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch`: one-line diagnostic backport of the `positions_cpu` proposer metadata field from upstream PR 11062; it is not a full upstream backport.
- `workloads/p8_1_vllm_ascend_observe_only_adapter_smoke.yaml`: prepared bounded-observation server validation for the strictly observe-only adapter; not executed and still deferred during the minimal control and MTP decision sequence.
- `workloads/fixed_output_smoke.yaml`: older P6 fixed-output smoke template retained for continuity.

Planning references:

- `docs/EXPERIMENT_PLAN.md`: canonical P5-P9 stage graph, evidence gates and experiment contracts.
- `docs/DEEPSEEK_V4_FLASH_ASCEND_PLAN.md`: DeepSeek-specific runtime, model-object and boundary plan.
- `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`: P8 runtime capability matrix, StateObject control plane, KV/Prefix and MoE prototype details.

Next artifact boundary:

- P6.0 is `yellow_degraded_baseline_stabilized`, and the repair-before control is `yellow_degraded_minimal_unprofiled_control_measured`.
- The current P6.1R retry2 handoff uses `/v1/completions`, captures at most 8192 bytes of an HTTPError body, prioritizes request-error evidence, and validates the overlay through package root plus patched/base hashes without importing the circular proposer module. It still allows only the existing one-line patch in one task-local overlay, one lifecycle and one MTP `4096+64+c1` request.
- P8.1 remains a deferred preflight. When separately reauthorized, it may validate only the observe-only adapter on the frozen cell; its Prefix metrics remain proxies and cannot be promoted to object bytes or performance conclusions.
- Do not create P8 real-move cards before P8.0 capability probe and P8.1 observe-only trace pass.
- MindIE cards are conditional on a separately confirmed server runtime; current server evidence does not show MindIE as available.
