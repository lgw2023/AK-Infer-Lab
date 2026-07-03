from __future__ import annotations

PROFILES = [
    "server_observability_profile",
    "request_runtime_profile",
    "scheduler_policy_profile",
    "operator_timeline_profile",
    "npu_hbm_profile",
    "cpu_dram_profile",
    "transfer_overlap_profile",
    "ssd_io_profile",
    "state_object_profile",
    "kv_prefix_profile",
    "moe_expert_profile",
    "power_stability_profile",
    "microbench_profile",
]

FIELD_TYPES = [
    "inventory",
    "counter",
    "event",
    "metric",
    "trace",
    "derived_metric",
]

SAMPLING_MODES = [
    "one_shot",
    "per_request",
    "per_token",
    "per_layer",
    "periodic",
    "microbench",
]

AVAILABILITY_STATUSES = [
    "measurable",
    "partial",
    "blocked",
    "unknown",
    "not_applicable",
]

CONFIDENCE_LEVELS = ["high", "medium", "low"]

BLOCKED_REASON_CATEGORIES = [
    "permission",
    "tool_missing",
    "framework_hook_missing",
    "container_isolation",
    "timestamp_unaligned",
    "join_key_missing",
    "hardware_not_exposed",
    "workload_not_available",
    "unknown",
]

OUTPUT_FILENAMES = {
    "manifest": "manifest.yaml",
    "summary": "server_observability_profile.md",
    "field_availability": "field_availability.yaml",
    "join_key_readiness": "join_key_readiness.yaml",
    "p0_acceptance_fields": "p0_acceptance_fields.yaml",
}

PROBE_NAMES = [
    "npu_smi_probe",
    "cann_profiler_probe",
    "perf_probe",
    "ebpf_probe",
    "fio_probe",
    "numa_probe",
    "container_permission_probe",
]
