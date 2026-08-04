# DeepSeek-V4-Flash Benchmark Cards

This directory holds local planning artifacts for P5-P9. It does not contain model payloads.

Current objects:

| model_object_id | source | server path | role |
| --- | --- | --- | --- |
| `deepseek_v4_flash_w8a8_mtp_modelscope` | ModelScope `DeepSeek-V4-Flash-w8a8-mtp` | `/data/node0_disk1/Public/DeepSeek-V4-Flash-w8a8-mtp` | project primary runtime object; P6 official/unprofiled/profiled/P6.3A/P6.3B-R4-R1 green |
| `deepseek_v4_flash_official_hf` | Hugging Face `deepseek-ai/DeepSeek-V4-Flash` | `/data/node0_disk1/Public/DeepSeek-V4-Flash` | historical mixed-checkpoint diagnostic and source inventory only |

Boundaries:

- Downloaded model files do not prove Ascend runtime compatibility.
- The official source checkpoint is mixed FP8 plus FP4 experts, not pure FP8 and not a `--quantization ascend` object.
- The v0.22.1/v0.22.1rc1 four-card diagnostic fixed plugin, allocator and ACL path issues, loaded all 46 shards, then failed at FP4 expert post-processing because `customize_dtype` is unsupported by the current SoC.
- The project will not build an adapter for that mixed route. W8A8-MTP is the only current P5/P6 runtime object.
- The 279.41 GiB W8A8 checkpoint exceeds four-card aggregate HBM. The first eight-card run loaded all 70 shards but failed before server-ready in the MTP drafter DSA-CP graph-capture path.
- The no-MTP isolation reached graph-ready; after replacing the incompatible client path and correcting the cached-wrapper MRO assertion, the exact no-MTP graph cell completed one `4096+64` HTTP 200 request.
- That success remains a degraded historical runtime baseline. Later P6.1C-R1 validated MTP through 131072, P6.1 established the unprofiled performance reference, and P6.2 established the profiled evidence reference.
- P5 is a startup and long-context smoke, not a benchmark or bottleneck attribution run.
- Server tasks use a self-contained handoff under `通信模块/docs/`; concurrent workstreams must keep dedicated files such as `developer-to-server.P6.md` so one session does not overwrite another. Returned bounded packages remain within the 70KB communication limit.

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
- `workloads/p6_1r_bounded_mtp_reference_repair.yaml`: completed bounded MTP repair lineage; retry2 closed the minimum `4096+64` MTP request gate.
- `workloads/p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml`: completed official context reference through `131072+64`.
- `workloads/p6_1_mtp_unprofiled_baseline.yaml`: completed 18-cell unprofiled performance reference.
- `workloads/p6_2_mtp_profiled_evidence.yaml`: completed three-cell profiled evidence reference.
- `workloads/p6_3a_mtp_matched_ab.yaml`: completed matched MTP on/off task; developer grade `green_p6_3a_mtp_matched_ab`.
- `workloads/p6_3b_prefix_cache_matched_ab.yaml` through `workloads/p6_3b_r4_r1_explicit_prefix_cache_matched_ab.yaml`: completed Prefix Cache lineage; R4-R1 developer grade is `green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab` with explicit off hit=0 and on primary 9/9 positive hits under the same R2 repair.
- `p6_3c_chunked_prefill_feasibility_audit.yaml`: completed exact-commit CLI/config audit; `4096 < 135168` makes Chunked Prefill off fail before resolved runtime config, so the original `135168/4096/1` reference remains `blocked_p6_3c_not_strict_single_variable` and has no executable workload. This does not prohibit independently named, jointly frozen scheduler-pressure experiments.
- `workloads/p6_3c_r1_chunked_prefill_scheduler_pressure_matched_ab.yaml`: completed first independent scheduler-pressure attempt; `mechanism_01` stopped during KV-cache initialization with 8.27 GiB available versus 36.66 GiB required, so the accepted result is startup-only `red_p6_3c_r1_scheduler_pressure_no_success` with zero requests and zero scheduler steps.
- `workloads/p6_3c_r2_chunked_prefill_capacity_calibrated_matched_ab.yaml`: preserved R2 science contract and run01 audit. Run01 stopped before vLLM startup because the task-local overlay did not materialize the real mixed editable/site-packages installation; it produced 0 request and 0 scheduler evidence while global resource recovery was clean.
- `workloads/p6_3c_r2_f1_runtime_layout_portable_matched_ab.yaml`: preserved runner-repair attempt. Real package resolution, the 1644-file materialized overlay and vLLM startup succeeded, but inherited proxy routing made the local health loop return 504 while an explicit direct loopback probe returned 200; it produced zero requests and no scheduler evidence.
- `workloads/p6_3c_r2_f2_loopback_proxy_safe_matched_ab.yaml`: completed transport-repair attempt. All six lifecycles and 90/90 requests ran with direct-loopback and clean recovery, but each internal pair reached adjacent scheduler steps, so it did not create same-round token-budget pressure and cannot support a Chunked Prefill mechanism or performance conclusion.
- `workloads/p6_3c_r2_f3_atomic_pair_admission_matched_ab.yaml` through `workloads/p6_3c_r2_f4_a1_adaptive_acceptance.yaml`: completed controlled co-arrival lineage. F4/A1 accepts mechanism evidence under `12288/12288/2`, Prefix Cache off and atomic co-arrival: Off has no partial prefill, while On has partial prefill in both over-budget cells. The fixed sample did not show a short-request TTFT or throughput benefit.
- `workloads/p6_3c_r3a_decode_resident_admission_cliff_matched_ab.yaml`: completed decode-resident matched A/B. With eight resident requests and `D=16`, the 12281-token cliff waited on Off but was partially admitted with 12272 tokens on On. Median injected TTFT fell 77.7%, while resident interference P99 TBT rose about 684% and aggregate output TPS fell 8.5%; the accepted outcome is `mechanism_confirmed_tradeoff_only`.
- `workloads/p6_3c_r3b_chunk_budget_pareto.yaml`: current P6 task. It retains a contemporaneous legal Off `B=12288` baseline and scans On `B∈{2048,4096,6144,8192,12288}` under the same decode-resident admission cliff. Five observer lifecycles calibrate actual chunks before 12 mirrored observer-free performance lifecycles estimate the TTFT–TBT–throughput Pareto frontier. This is a policy comparison, not a strict single-variable A/B.
- `p6/`: materialized P6 closeout package containing the baseline contract, unprofiled report, profiled report, single-variable A/B report and hash-verifiable artifact manifest.
- `patches/vllm_ascend_v0221rc1_mtp_positions_cpu_overlay.patch`: one-line diagnostic backport of the `positions_cpu` proposer metadata field from upstream PR 11062; it is not a full upstream backport.
- `p8/p8_baseline_contract.yaml` and `workloads/p8_1_vllm_ascend_observe_only_adapter_smoke.yaml`: preserved historical no-MTP `frozen_degraded` provenance; not the current P8.1 execution target.
- `p8/p8_official_mtp_baseline_contract.yaml` and `workloads/p8_1_vllm_ascend_official_mtp_observe_only_adapter_smoke.yaml`: preserved official-MTP single-request tracer provenance; published but superseded before server execution.
- `p8/p8_official_mtp_observe_matrix_contract.yaml` and `workloads/p8_1_vllm_ascend_official_mtp_observe_only_matrix.yaml`: completed P8.1 parent, developer-reviewed `yellow_p8_1_matrix_trace_invalid`; all six requests and trace/replay/join gates passed, but the 64K follower hit was zero instead of 49152.
- `workloads/p8_1_r1_vllm_ascend_official_mtp_observe_only_matrix.yaml`: completed P8.1-R1 target; developer grade `green_p8_1_r1_official_mtp_observe_only_matrix`. It closed the shared-prefix trace gate with the accepted R2 task-local repair, but remains observe-only rather than a performance comparison.
- `workloads/p8_2_k0_order_balanced_prefix_cache_baseline.yaml`: completed order-balanced Prefix Cache baseline; offline R1 refinalization corrected the request-evidence field aliases and the developer accepted `green_p8_2_k0_order_balanced_prefix_cache_baseline`, not a performance reference or offload result.
- `p8_2_k1_kv_cache_cpu_offload_feasibility_audit.yaml`: completed legacy K1 frozen-source audit; import/API and hybrid multi-group incompatibility keep this path blocked.
- `p8_2_k1a_r1_allocator_feasibility_audit.yaml` through `p8_2_k1a_r3_r2_r2_r1_r1_source_binding_provenance_audit.yaml`: preserved K1A geometry, accepted-capacity, formal-lifecycle and forensic lineage. R2 accepts exactly `430604288 bytes/rank / 3444834304 total`; R3-R2-R1 is runtime partial yellow; R3-R2-R2, R3-R2-R2-R1 and R3-R2-R2-R1-R1 remain blocked provenance.
- `p8_2_k1a_r3_r2_r2_r1_r1_r1_causal_exception_replay_audit.yaml` and its workload: completed runtime parent. Its six requests passed transport/token/MTP/health/queue gates and its D2H store path completed, but no CPU hit/load/H2D appeared; the original red grade is preserved and the developer accepts only store-only yellow.
- `p8_2_k1a_r4_store_only_refinalization_audit.yaml` and its workload: completed read-only parent. Store-only refinalization and raw trace attribution passed, but the source audit falsely rejected frozen `popleft_n`; its blocked grade remains provenance.
- `p8_2_k1a_r4_r1_source_semantics_replay_audit.yaml` and `workloads/p8_2_k1a_r4_r1_store_only_source_semantics_replay.yaml`: current zero-NPU task. It validates the old R4 package, recognizes only the exact `popleft`/`popleft_n` dequeue calls, reruns the same bounded/raw evidence, and transfers the 9 payloads together with their manifest control file.
- `p8_2_k2_r0_ucm_dram_external_prefix_path_audit.yaml` and `workloads/p8_2_k2_r0_ucm_dram_external_prefix_path.yaml`: current P8.2-K2-R0 run04 implementation. Run03 attribution proved that FAWA split the old 32 GiB POSIX setting to 16/16 GiB and default 4096 directory shards made the scheduler FA GC recycle count truncate to zero. Run04 preserves the validated dependency/NFS/16 GiB CacheStore path, sets total POSIX capacity to 64 GiB and `data_dir_shard_bytes=2`, yielding FA/WA 32/32 GiB across 256 shards. Before NPU touch it validates the attribution package, observed FA/WA block sizes, both Cache/GC integer geometries, DRAM headroom, and storage free space; then one TP8+EP+MTP lifecycle exercises `UCM save → DRAM external hit → Cache load/H2D → follower completion`. Latency is descriptive and its sign is not a path-implementation gate.
- `workloads/fixed_output_smoke.yaml`: older P6 fixed-output smoke template retained for continuity.

Planning references:

- `docs/EXPERIMENT_PLAN.md`: canonical P5-P9 stage graph, evidence gates and experiment contracts.
- `docs/DEEPSEEK_V4_FLASH_ASCEND_PLAN.md`: DeepSeek-specific runtime, model-object and boundary plan.
- `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`: P8 runtime capability matrix, StateObject control plane, KV/Prefix and MoE prototype details.

Next artifact boundary:

- P6.3A changed only the MTP speculative server argument and is complete; its accepted mechanism effect remains fixed-order descriptive evidence, not a randomized or statistically significant claim.
- P6.3B-R4-R1 changed only explicit `--no-enable-prefix-caching` versus `--enable-prefix-caching`; both modes retained MTP and reused the same block-aligned repeated-prefix bodies. The fifteen boundary followers still had zero hits, so the accepted mechanism scope is not a universal performance claim.
- P6.3C strict-single-variable feasibility is closed as `blocked_p6_3c_not_strict_single_variable`: explicit CLI on/off exists, but the frozen off configuration is rejected because `4096 < 135168`. That statement applies only to the original reference. F4 is accepted controlled mechanism evidence, R3A is complete trade-off evidence, and R3B is the independently named budget-policy calibration.
- P8.1-R1 and P8.2-K0 are closed in their narrow boundaries. K1A-F1 is now closed by R17 full-trace replay with D2H/H2D 8-worker completion. The generic handoff owns the active K2 stream; the dedicated P6 handoff owns R3B. Because both require NPU 0–7, server-side coordination must confirm global exclusivity before either starts. R3C, K2 follow-ups, K3 and P8.3-I1 remain unauthorized.
- MindIE cards are conditional on a separately confirmed server runtime; current server evidence does not show MindIE as available.
