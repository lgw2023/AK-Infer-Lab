# P6 Single-variable A/B Report

Date: 2026-07-16

Stage disposition: P6.3A and P6.3B accepted; conditional P6.3C closed as infeasible under the strict frozen profile.

## P6.3A — MTP matched A/B

Accepted grade: `green_p6_3a_mtp_matched_ab`.

- Two fresh unprofiled lifecycles used fixed `mtp_off -> mtp_on` order.
- Eight matched cells completed 48/48 measured batches and 108/108 measured requests with zero retry.
- Canonical bodies, request ordering and all non-MTP runtime parameters were paired; 24/24 paired batches had directionally consistent E2EL, TPOT and batch-throughput differences.
- The accepted claim is a frozen fixed-order descriptive mechanism effect. It is not randomized causality, statistical significance or universal MTP speedup.

## P6.3B — explicit Prefix Cache matched A/B

Accepted grade: `green_p6_3b_r4_r1_explicit_prefix_cache_matched_ab`.

- Same R2 hybrid-KV repair in both modes; explicit false/true Prefix Cache controls; two fresh lifecycles.
- 16/16 prime, 48/48 measured and 64/64 total requests completed.
- Off hit total was zero. On-side `32768/65536/131072 × 90%` primary groups produced 9/9 primary positive hit, with per-request hits `16384/49152/114688`, exactly the token-LCP 16K floor.
- The other 15 boundary followers remained zero-hit. The result establishes a primary-scope mechanism effect, not universal hits or Prefix Cache performance benefit.

## P6.3C — Chunked Prefill feasibility

Accepted grade: `blocked_p6_3c_not_strict_single_variable`.

The frozen CLI exposes explicit on/off booleans, but the off side is rejected before resolved runtime config because `max_num_batched_tokens=4096 < max_model_len=135168`. Raising the token budget or lowering max model length changes a forbidden second variable. Therefore this is a completed feasibility result and 不构成可执行 matched A/B；no P6.3C workload, runner or request bodies were created.

## Combined boundary

P6.3 green means the declared evidence structure closed within its exact workload. It does not erase the fixed-order limitation, does not promote profiled latency to the performance reference, and 不声称普遍优化收益。Any future Chunked Prefill experiment must be a new scheduler/feature-combination envelope outside strict P6.3C.

## Evidence sources

- `benchmarks/deepseek_v4_flash/workloads/p6_3a_mtp_matched_ab.yaml`
- `benchmarks/deepseek_v4_flash/workloads/p6_3b_r4_r1_explicit_prefix_cache_matched_ab.yaml`
- `benchmarks/deepseek_v4_flash/p6_3c_chunked_prefill_feasibility_audit.yaml`
