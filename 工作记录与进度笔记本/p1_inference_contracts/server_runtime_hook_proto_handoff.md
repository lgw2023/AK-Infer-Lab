# Server Runtime Hook Prototype Handoff

Task ID: `runtime_hook_proto_2026_0705_p1_003`

This handoff follows P1.3 `runtime_hook_discovery_2026_0705_p1_002`. It asks the Ascend server to validate hook prototype feasibility without loading any model, touching the server `models/` directory, installing packages, or modifying vLLM/vLLM-Ascend source.

## Evidence Anchors

- P0.5 server baseline: `obs_2026_0705_atlas800t_a2_006`
- P1.2 contract smoke: `runtime_trace_smoke_2026_0705_p1_001`
- P1.3 hook discovery: `runtime_hook_discovery_2026_0705_p1_002`
- P1 contract directory: `工作记录与进度笔记本/p1_inference_contracts/`
- Current server instruction document: `通信模块/docs/developer-to-server.md`

## P1.3 Facts Used

- Server commit: `7527cd8`
- `tests/inference_contracts`: `11 passed in 0.20s`
- `host_marker_npu_smoke.jsonl`: `errors=0`, `events=4`
- `torch 2.9.0+cpu`, `torch_npu 2.9.0.post2`, `vllm`, `vllm_ascend`, `msprof`, and `msnpureport` are available.
- `mindie` and `mindspore` are missing and remain outside this task.
- `msprof --help` exposes `--msproftx` / `mstx` options, but CANN timeline pairing is still unconfirmed.

## Candidate Areas

- Request runtime: `vllm.v1.engine.core`, `vllm.v1.engine.async_llm`, `vllm.v1.engine.llm_engine`
- Scheduler: `vllm.v1.core.sched.scheduler`
- Model execution: `vllm.v1.worker.gpu_model_runner`, `vllm_ascend.worker.model_runner_v1`, `vllm_ascend.worker.worker`, `vllm_ascend.worker.v2.model_runner`
- State and KV: `vllm.v1.core.kv_cache_manager`, block pool modules, distributed KV connector modules
- Copy and profiler markers: `torch.npu.Stream`, `torch.npu.Event`, `torch.npu.synchronize`, `torch.profiler.record_function`, `msprof --msproftx=on`

## Scope

Allowed:

- Import candidate modules and inspect class/function signatures.
- Record source files and source start lines.
- Apply wrapper monkey-patches only inside a temporary Python process, then restore the original attributes before process exit.
- Emit a synthetic no-model `runtime_hook_proto_trace.jsonl` using the P1 schema and validate it.
- Run an extremely small NPU tensor script under `msprof --msproftx=on` to check whether marker names are visible in profiler output.

Forbidden:

- Real model inference or vLLM engine generation.
- Reading, listing, loading, copying, or tokenizing anything under the server `models/` directory.
- Running P000-P012 workload prompts.
- Installing, upgrading, uninstalling, or repairing inference framework packages.
- Modifying vLLM/vLLM-Ascend source files, CANN, driver, apt/dpkg, NPU runtime, or project code on the server.
- Server-side git commit or push.

## Expected Artifacts

The server should return:

- `run_context.txt`
- `pytest_inference_contracts.log`
- `hook_target_probe.py`
- `hook_target_probe.log`
- `hook_target_inventory.jsonl`
- `hook_patchability.tsv`
- `runtime_hook_proto_trace.jsonl`
- `runtime_hook_proto_validation.txt`
- `msprof_marker_smoke.py`
- `msprof_marker_smoke.log`
- `msprof_marker_artifacts.txt`
- `msprof_marker_search.txt`
- `summary.txt`
- `runtime_hook_proto_2026_0705_p1_003.zip`

## Acceptance

This task is successful if the server reports a clear result for each item:

- Candidate hook classes/functions can be imported and inspected, or import failures are recorded with exact error text.
- Wrapper patchability and restore status are recorded in TSV.
- The no-model runtime hook prototype trace validates with `errors=0`.
- `msprof --msproftx=on` marker smoke either succeeds and produces searchable artifacts, or fails with a bounded exit code and log.
- The report explicitly keeps CANN host/device timeline pairing as unconfirmed unless marker evidence proves otherwise.
