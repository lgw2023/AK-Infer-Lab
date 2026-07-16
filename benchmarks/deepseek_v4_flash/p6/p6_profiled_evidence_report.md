# P6 Profiled Evidence Report

Date: 2026-07-16

Accepted grade: `green_mtp_profiled_evidence`

Claim boundary: operator、phase memory、transfer 与 request-device aggregate 证据链；profiled latency 不是用户性能 baseline。

## Accepted result

- 3/3 representative cells completed on the first attempt: `4096+64+c1`, `131072+64+c1`, and `4096+256+c1`.
- Every cell produced a clean msprof SQLite root and a full request-device aggregate; heavy joins were not skipped.
- The package contained 6 phase-memory rows, each with eight-device coverage, and parse failure count was zero.
- MTP activity, request health, queue state, token correctness and cleanup gates passed; retry count was zero.
- P6.1 remains the unprofiled user-performance reference.

## Interpretation boundary

- Whole-device HBM samples are not KV-object bytes or HBM traffic.
- Process-group RSS/PSS is not an individual state-object footprint.
- Profiler-wrapped request duration includes instrumentation overhead and is not a replacement for P6.1 latency.
- The three selected shapes establish that the evidence pipeline works; they do not establish a universal workload bottleneck.
- The current evidence does not form a hardware-priority claim and 不形成硬件瓶颈或优化优先级归因。

## Evidence source

- `benchmarks/deepseek_v4_flash/workloads/p6_2_mtp_profiled_evidence.yaml`
- The bounded received package recorded by that workload remains the accepted developer-review source; raw traces remain server-local.

No profiler was run while producing this consolidated document.
