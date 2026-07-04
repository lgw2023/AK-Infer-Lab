# Server Observability Profile

## 1. Run Summary

- profile_run_id: `obs_2026_0703_atlas800t_a2_001`
- server_id: `atlas800t-a2-node-001`
- schema_version: `0.1.0`
- hardware_topology_hash: `0a1d3979b9c220a2`
- software_stack_hash: `31a6ab85f96f296d`
- probe_script_version: `0.1.0`

## 2. Server And Tool Readiness

- `npu_smi_probe`: available=True permission=ok exit_code=0
- `cann_profiler_probe`: available=True permission=ok exit_code=0
- `perf_probe`: available=False permission=blocked exit_code=127
- `ebpf_probe`: available=False permission=blocked exit_code=127
- `fio_probe`: available=False permission=blocked exit_code=127
- `numa_probe`: available=False permission=blocked exit_code=127
- `container_permission_probe`: available=True permission=ok exit_code=0

## 3. Profile-Level Observability

- `cpu_dram_profile`: measurable=0 partial=0 blocked=0 unknown=17 not_applicable=0
- `kv_prefix_profile`: measurable=0 partial=0 blocked=0 unknown=12 not_applicable=0
- `microbench_profile`: measurable=0 partial=0 blocked=0 unknown=13 not_applicable=0
- `moe_expert_profile`: measurable=0 partial=0 blocked=0 unknown=15 not_applicable=0
- `npu_hbm_profile`: measurable=0 partial=0 blocked=0 unknown=16 not_applicable=0
- `operator_timeline_profile`: measurable=0 partial=0 blocked=0 unknown=13 not_applicable=0
- `power_stability_profile`: measurable=0 partial=0 blocked=0 unknown=16 not_applicable=0
- `request_runtime_profile`: measurable=0 partial=0 blocked=0 unknown=13 not_applicable=0
- `scheduler_policy_profile`: measurable=0 partial=0 blocked=0 unknown=11 not_applicable=0
- `server_observability_profile`: measurable=6 partial=0 blocked=4 unknown=7 not_applicable=0
- `ssd_io_profile`: measurable=0 partial=0 blocked=0 unknown=20 not_applicable=0
- `state_object_profile`: measurable=0 partial=0 blocked=0 unknown=13 not_applicable=0
- `transfer_overlap_profile`: measurable=0 partial=0 blocked=0 unknown=14 not_applicable=0

## 4. P0 Acceptance Fields

- `server_observability_profile.os_name`: measurable from `manifest.yaml`
- `server_observability_profile.kernel_version`: measurable from `manifest.yaml`
- `server_observability_profile.torch_npu_version`: measurable from `manifest.yaml`
- `server_observability_profile.npu_smi_available`: measurable from `probe_results/npu_smi_probe.md`
- `server_observability_profile.cann_profiler_available`: measurable from `probe_results/cann_profiler_probe.md`
- `server_observability_profile.container_cgroup_readable`: measurable from `probe_results/container_permission_probe.md`

## 5. Join-Key And Time-Alignment Readiness

- `request_runtime_profile + operator_timeline_profile`: partial; time_alignment=unknown
- `state_object_profile + transfer_overlap_profile`: blocked; time_alignment=unknown
- `moe_expert_profile + operator_timeline_profile`: blocked; time_alignment=unknown

## 6. Gap Summary

- `tool_missing`: 4
- `unknown`: 180

## 7. Recommended Next Actions

- Use `field_availability.yaml` and `join_key_readiness.yaml` to choose the first P0 probe fixes.
- Do not treat SSD cold tier, runtime hooks, or MoE expert hooks as P0 performance optimization work.
