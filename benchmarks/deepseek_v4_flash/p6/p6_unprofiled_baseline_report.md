# P6 Unprofiled Baseline Report

Date: 2026-07-16

Accepted grade: `green_mtp_unprofiled_baseline`

Claim boundary: P6 用户侧 streaming 性能 reference；不是 profiler 归因、并发扩展性证明或普遍优化收益。

## Frozen runtime

- Model: DeepSeek-V4-Flash W8A8-MTP, `quantization=ascend`.
- Runtime: vLLM `0.22.1+empty@0decac0d...` and vLLM-Ascend `0.22.1rc1@5f6faa0c...`.
- Topology: TP8 + EP, `num_speculative_tokens=1`.
- Scheduler/graph: Chunked Prefill on, Prefix Cache on, `FULL_DECODE_ONLY`, `max_model_len=135168`, `max_num_batched_tokens=4096`, `max_num_seqs=1`.
- Request protocol: streaming, `temperature=0`, fixed output, exact prompt/output/SSE checks, no profiler or HBM sampler.

## Accepted result

- Official context prerequisite: `green_mtp_official_context_ladder`, with `4096/32768/65536/98304/131072 + 64` all first-attempt successful and `highest_stable_context=131072`.
- P6.1 matrix: 18/18 cells, 24/24 measured batches and 90/90 measured requests succeeded with zero retry.
- All token, finish, health, queue, MTP-counter continuity and cleanup gates passed.
- The canonical request bodies were frozen and unique within the plan; generated text and token IDs were not retained or transferred.

## Metric meaning

The accepted report uses the frozen P6.1 definitions for TTFT, E2EL, TPOT, client-observed ITL and request/batch throughput. Concurrent E2EL includes queue time because `max_num_seqs=1`. Tokens sharing one SSE chunk share the same arrival timestamp, so zero-gap ITL samples are transport observations, not zero NPU decode latency.

## Evidence source

- `benchmarks/deepseek_v4_flash/workloads/p6_1c_r1_mtp_official_context_ladder_sampling_repair.yaml`
- `benchmarks/deepseek_v4_flash/workloads/p6_1_mtp_unprofiled_baseline.yaml`

No new server or NPU execution was performed to materialize this report.
