# Server Observability Profile

## 1. Run Summary

- profile_run_id: `obs_2026_0705_atlas800t_a2_006`
- server_id: `atlas800t-a2-node-001`
- schema_version: `0.1.0`
- hardware_topology_hash: `6d879ff4d98fcf45`
- software_stack_hash: `dd7f95802653a406`
- probe_script_version: `0.1.0`

## 2. Server And Tool Readiness

- `npu_smi_probe`: available=True permission=ok exit_code=0
- `cann_profiler_probe`: available=True permission=ok exit_code=0
- `perf_probe`: available=True permission=ok exit_code=0
- `ebpf_probe`: available=False permission=blocked exit_code=127
- `fio_probe`: available=True permission=ok exit_code=0
- `numa_probe`: available=True permission=ok exit_code=0
- `container_permission_probe`: available=True permission=ok exit_code=0

## 2.1 Microbench Results

- `npu_copy_h2d`: status=measurable artifact=`microbench/npu_copy_h2d.csv` blocked=none
- `npu_copy_d2h`: status=measurable artifact=`microbench/npu_copy_d2h.csv` blocked=none
- `npu_copy_overlap`: status=measurable artifact=`microbench/npu_copy_overlap.csv` blocked=none
- `npu_matmul_shape`: status=measurable artifact=`microbench/npu_matmul_shape.csv` blocked=none
- `cpu_kernel`: status=measurable artifact=`microbench/cpu_kernel.csv` blocked=none
- `cpu_perf`: status=measurable artifact=`microbench/cpu_perf.csv` blocked=none
- `dram_bandwidth`: status=measurable artifact=`microbench/dram_bandwidth.csv` blocked=none
- `numa_topology`: status=measurable artifact=`microbench/numa_topology.csv` blocked=none
- `ssd_fio`: status=measurable artifact=`microbench/ssd_fio.csv` blocked=none

## 3. Profile-Level Observability

- `cpu_dram_profile`: measurable=0 partial=0 blocked=0 unknown=17 not_applicable=0
- `kv_prefix_profile`: measurable=0 partial=0 blocked=0 unknown=12 not_applicable=0
- `microbench_profile`: measurable=9 partial=0 blocked=0 unknown=4 not_applicable=0
- `moe_expert_profile`: measurable=0 partial=0 blocked=0 unknown=15 not_applicable=0
- `npu_hbm_profile`: measurable=0 partial=0 blocked=0 unknown=16 not_applicable=0
- `operator_timeline_profile`: measurable=0 partial=0 blocked=0 unknown=13 not_applicable=0
- `power_stability_profile`: measurable=0 partial=0 blocked=0 unknown=16 not_applicable=0
- `request_runtime_profile`: measurable=0 partial=0 blocked=0 unknown=13 not_applicable=0
- `scheduler_policy_profile`: measurable=0 partial=0 blocked=0 unknown=11 not_applicable=0
- `server_observability_profile`: measurable=13 partial=0 blocked=1 unknown=3 not_applicable=0
- `ssd_io_profile`: measurable=0 partial=0 blocked=0 unknown=20 not_applicable=0
- `state_object_profile`: measurable=0 partial=0 blocked=0 unknown=13 not_applicable=0
- `transfer_overlap_profile`: measurable=0 partial=0 blocked=0 unknown=14 not_applicable=0

## 4. P0 Acceptance Fields

- `server_observability_profile.os_name`: measurable from `manifest.yaml`
- `server_observability_profile.kernel_version`: measurable from `manifest.yaml`
- `server_observability_profile.cann_version`: measurable from `manifest.yaml`
- `server_observability_profile.driver_version`: measurable from `manifest.yaml`
- `server_observability_profile.torch_npu_version`: measurable from `manifest.yaml`
- `server_observability_profile.vllm_ascend_version`: measurable from `manifest.yaml`
- `server_observability_profile.visible_npu_count`: measurable from `manifest.yaml`
- `server_observability_profile.npu_smi_available`: measurable from `probe_results/npu_smi_probe.md`
- `server_observability_profile.cann_profiler_available`: measurable from `probe_results/cann_profiler_probe.md`
- `server_observability_profile.perf_available`: measurable from `probe_results/perf_probe.md`
- `server_observability_profile.fio_available`: measurable from `probe_results/fio_probe.md`
- `server_observability_profile.numa_available`: measurable from `probe_results/numa_probe.md`
- `server_observability_profile.container_cgroup_readable`: measurable from `probe_results/container_permission_probe.md`
- `microbench_profile.npu_op_by_shape`: measurable from `microbench/npu_matmul_shape.csv`
- `microbench_profile.cpu_kernel_by_shape`: measurable from `microbench/cpu_kernel.csv`
- `microbench_profile.ddr_bandwidth_gbps`: measurable from `microbench/dram_bandwidth.csv`
- `microbench_profile.ssd_iops`: measurable from `microbench/ssd_fio.csv`
- `microbench_profile.h2d_latency_us`: measurable from `microbench/npu_copy_h2d.csv`
- `microbench_profile.d2h_latency_us`: measurable from `microbench/npu_copy_d2h.csv`
- `microbench_profile.h2d_bandwidth_gbps`: measurable from `microbench/npu_copy_h2d.csv`
- `microbench_profile.d2h_bandwidth_gbps`: measurable from `microbench/npu_copy_d2h.csv`
- `microbench_profile.copy_overlap_ratio`: measurable from `microbench/npu_copy_overlap.csv`

## 5. Join-Key And Time-Alignment Readiness

- `request_runtime_profile + operator_timeline_profile`: partial; time_alignment=unknown
- `state_object_profile + transfer_overlap_profile`: blocked; time_alignment=unknown
- `moe_expert_profile + operator_timeline_profile`: blocked; time_alignment=unknown

## 6. Gap Summary

- `tool_missing`: 1
- `unknown`: 167

## 7. Recommended Next Actions

- Use `field_availability.yaml` and `join_key_readiness.yaml` to choose the first P0 probe fixes.
- Do not treat SSD cold tier, runtime hooks, or MoE expert hooks as P0 performance optimization work.
