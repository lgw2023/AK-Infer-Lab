# Runtime Hook Join Key Design

This document is a local P1 design artifact. 本轮不下发服务器任务 and does not request a new Atlas run.

Current evidence anchor: `obs_2026_0705_atlas800t_a2_006`.

Local fixture anchor: `fixtures/minimal_runtime_trace.jsonl`.

## Required Join Keys

- `trace_id`: one end-to-end inference request trace.
- `request_id`: runtime request identifier.
- `layer_id`: model layer identifier for operator and object mapping.
- `object_id`: KV, prefix, expert, weight, activation, workspace, or logits object identifier.
- `stream_id`: compute or copy stream identifier.

## Profile Pair Targets

### request_runtime_profile + operator_timeline_profile

Required keys: `trace_id`, `request_id`, `phase`, `layer_id`, `stream_id`.

Minimum design: wrapper emits phase markers around prefill and decode, and profiler events carry a layer mapping table. Until `layer_id` and clock alignment are available, request delay can be described but not attributed to a specific operator.

### state_object_profile + transfer_overlap_profile

Required keys: `trace_id`, `request_id`, `object_id`, `lifecycle_event`, `stream_id`.

Minimum design: object lifecycle hooks emit create, hit, miss, restore, prefetch, evict, and release events. Copy hooks tag the same `object_id` and `stream_id`. Until both keys exist, H2D/D2H copy cannot be claimed as the cause of a TPOT spike.

### moe_expert_profile + operator_timeline_profile

Required keys: `trace_id`, `request_id`, `layer_id`, `object_id`.

Minimum design: router top-k capture emits expert ids and probabilities. Expert cache events reuse the same `object_id`. Until expert ids are stable, MoE analysis remains request-level only.

## Time Alignment

- Host wrapper timestamps use `host_monotonic_ns`.
- CANN profiler events use `cann_device_timeline`.
- The first runtime hook must emit paired host markers around profiler ranges before attribution claims.
- If time alignment remains unknown, emit `stall_reason=profiler_unaligned` instead of inventing a causal bottleneck.

## Local Fixture Acceptance

`fixtures/minimal_runtime_trace.jsonl` is the minimum local example for the first runtime hook task. It must remain static and must not require a model, tokenizer, server artifact, or live repository scan.

The fixture proves only structural alignment:

- request runtime events share `trace_id` and `request_id`.
- operator marker events add `layer_id` and `stream_id`.
- state object events add `object_type` and `object_id`.
- transfer overlap events reuse the same `object_id` and a copy `stream_id`.

It does not prove runtime correctness, timing accuracy, or bottleneck attribution. Those claims require a later Atlas server trace run.
