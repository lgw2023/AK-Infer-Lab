# A+K Observability Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a P0 server observability capability profiling framework that generates the run directory defined in `docs/superpowers/specs/2026-07-03-ak-observability-profile-design.md`.

**Architecture:** Create a small Python tool under `tools/observability_profile/` with a static field catalog, safe probe runner, manifest generator, field availability evaluator, join-key readiness evaluator, P0 acceptance field generator, and Markdown renderer. The tool produces a complete observability run directory without implementing performance optimization, complex runtime hooks, or model-serving modifications.

**Tech Stack:** Python 3.11+, standard library, PyYAML, pytest.

---

## File Structure

- Create `pyproject.toml`: minimal project metadata and pytest configuration for this repo-local tool.
- Create `tools/observability_profile/__init__.py`: package marker and version.
- Create `tools/observability_profile/constants.py`: enums, profile names, availability states, blocked reason categories, and output filenames.
- Create `tools/observability_profile/catalog.py`: static field catalog generator with profile-level fields and shared object fields.
- Create `tools/observability_profile/manifest.py`: run manifest generation, environment probing, and topology/software hash helpers.
- Create `tools/observability_profile/probes.py`: safe command probes for NPU, CANN profiler, perf, eBPF, fio, NUMA, and container permissions.
- Create `tools/observability_profile/availability.py`: field availability population from catalog and probe evidence.
- Create `tools/observability_profile/join_keys.py`: join-key and time-alignment readiness generation.
- Create `tools/observability_profile/p0_acceptance.py`: P0 hard acceptance field extraction.
- Create `tools/observability_profile/render.py`: human-readable `server_observability_profile.md` renderer.
- Create `tools/observability_profile/cli.py`: command-line entry point to generate a full observability run.
- Create `tests/observability_profile/test_catalog.py`: catalog shape and coverage tests.
- Create `tests/observability_profile/test_manifest.py`: manifest and hash tests.
- Create `tests/observability_profile/test_availability.py`: availability status and blocked reason tests.
- Create `tests/observability_profile/test_join_keys.py`: join-key readiness and time alignment tests.
- Create `tests/observability_profile/test_cli.py`: end-to-end run generation using mocked probes.

## Implementation Rules

- Do not implement model-serving hooks, runtime hooks, KV hooks, MoE hooks, or performance optimizations in this P0 plan.
- Probe commands must be non-destructive and must not require sudo.
- Probe failures are data, not fatal errors. The run must still generate artifacts with structured `blocked` or `unknown` status.
- Machine-readable YAML files are the source of truth. The Markdown summary only renders from YAML data.
- All generated paths must live under `工作记录与进度笔记本/observability_profiles/<run_dir>/`.

---

### Task 1: Project Skeleton And Test Harness

**Files:**
- Create: `pyproject.toml`
- Create: `tools/observability_profile/__init__.py`
- Create: `tools/observability_profile/constants.py`
- Create: `tests/observability_profile/test_catalog.py`

- [ ] **Step 1: Create the initial failing test**

Create `tests/observability_profile/test_catalog.py` with:

```python
from tools.observability_profile.constants import (
    AVAILABILITY_STATUSES,
    BLOCKED_REASON_CATEGORIES,
    OUTPUT_FILENAMES,
    PROFILES,
)


def test_profile_and_status_constants_cover_spec():
    assert "server_observability_profile" in PROFILES
    assert "request_runtime_profile" in PROFILES
    assert "operator_timeline_profile" in PROFILES
    assert "npu_hbm_profile" in PROFILES
    assert "state_object_profile" in PROFILES
    assert "moe_expert_profile" in PROFILES
    assert "not_applicable" in AVAILABILITY_STATUSES
    assert "join_key_missing" in BLOCKED_REASON_CATEGORIES
    assert OUTPUT_FILENAMES["manifest"] == "manifest.yaml"
    assert OUTPUT_FILENAMES["field_availability"] == "field_availability.yaml"
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python -m pytest tests/observability_profile/test_catalog.py -q
```

Expected: FAIL because `tools.observability_profile.constants` does not exist.

- [ ] **Step 3: Create project metadata**

Create `pyproject.toml` with:

```toml
[project]
name = "ak-infer-lab-observability"
version = "0.1.0"
description = "Server observability capability profiling tools for AK-Infer-Lab"
requires-python = ">=3.11"
dependencies = [
  "PyYAML>=6.0",
]

[project.optional-dependencies]
test = [
  "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 4: Create the package marker**

Create `tools/observability_profile/__init__.py` with:

```python
"""Observability capability profiling helpers for AK-Infer-Lab."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Create constants**

Create `tools/observability_profile/constants.py` with:

```python
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
```

- [ ] **Step 6: Run the test**

Run:

```bash
python -m pytest tests/observability_profile/test_catalog.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tools/observability_profile/__init__.py tools/observability_profile/constants.py tests/observability_profile/test_catalog.py
git commit -m "feat: add observability profile skeleton"
```

---

### Task 2: Field Catalog Generator

**Files:**
- Create: `tools/observability_profile/catalog.py`
- Modify: `tests/observability_profile/test_catalog.py`

- [ ] **Step 1: Extend catalog tests**

Replace `tests/observability_profile/test_catalog.py` with:

```python
from tools.observability_profile.catalog import build_field_catalog
from tools.observability_profile.constants import (
    AVAILABILITY_STATUSES,
    BLOCKED_REASON_CATEGORIES,
    OUTPUT_FILENAMES,
    PROFILES,
)


def test_profile_and_status_constants_cover_spec():
    assert "server_observability_profile" in PROFILES
    assert "request_runtime_profile" in PROFILES
    assert "operator_timeline_profile" in PROFILES
    assert "npu_hbm_profile" in PROFILES
    assert "state_object_profile" in PROFILES
    assert "moe_expert_profile" in PROFILES
    assert "not_applicable" in AVAILABILITY_STATUSES
    assert "join_key_missing" in BLOCKED_REASON_CATEGORIES
    assert OUTPUT_FILENAMES["manifest"] == "manifest.yaml"
    assert OUTPUT_FILENAMES["field_availability"] == "field_availability.yaml"


def test_field_catalog_has_every_profile_and_required_metadata():
    fields = build_field_catalog()
    profiles = {field["profile"] for field in fields}
    assert set(PROFILES).issubset(profiles)
    assert len(fields) >= 90

    required_keys = {
        "name",
        "profile",
        "meaning",
        "layer",
        "field_type",
        "unit",
        "required_for_p0",
        "sampling_mode",
        "measurement_source",
        "expected_tool",
        "permission_need",
        "collection_overhead",
        "expected_artifact",
        "join_key",
        "time_base",
        "availability",
        "validation_method",
        "acceptance_rule",
        "fallback",
        "notes",
    }
    for field in fields:
        assert required_keys.issubset(field.keys()), field["name"]
        assert field["availability"]["status"] == "unknown"
        assert field["availability"]["confidence"] == "low"


def test_state_object_children_inherit_common_object_fields():
    fields = build_field_catalog()
    by_name = {f"{field['profile']}.{field['name']}": field for field in fields}
    assert "state_object_profile.object_type" in by_name
    assert "state_object_profile.load_cost_us" in by_name
    assert "kv_prefix_profile.restore_vs_recompute_decision" in by_name
    assert "moe_expert_profile.prefetch_lead_time_us" in by_name
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/observability_profile/test_catalog.py -q
```

Expected: FAIL because `tools.observability_profile.catalog` does not exist.

- [ ] **Step 3: Implement the catalog generator**

Create `tools/observability_profile/catalog.py` with:

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_AVAILABILITY = {
    "status": "unknown",
    "confidence": "low",
    "evidence_probe": None,
    "evidence_artifact": None,
    "blocked_reason": {"category": None, "detail": None},
    "partial_reason": None,
    "last_checked_at": None,
}


def _field(
    *,
    profile: str,
    name: str,
    meaning: str,
    layer: str,
    field_type: str,
    unit: str,
    required_for_p0: bool,
    sampling_mode: str,
    measurement_source: str,
    expected_tool: str,
    permission_need: str,
    collection_overhead: str,
    expected_artifact: str,
    join_key: list[str],
    time_base: str,
    validation_method: str,
    acceptance_rule: str,
    fallback: str,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "profile": profile,
        "meaning": meaning,
        "layer": layer,
        "field_type": field_type,
        "unit": unit,
        "required_for_p0": required_for_p0,
        "sampling_mode": sampling_mode,
        "measurement_source": measurement_source,
        "expected_tool": expected_tool,
        "permission_need": permission_need,
        "collection_overhead": collection_overhead,
        "expected_artifact": expected_artifact,
        "join_key": join_key,
        "time_base": time_base,
        "availability": deepcopy(DEFAULT_AVAILABILITY),
        "validation_method": validation_method,
        "acceptance_rule": acceptance_rule,
        "fallback": fallback,
        "notes": notes,
    }


def _profile_fields(
    profile: str,
    layer: str,
    names: list[tuple[str, str, str, str]],
    *,
    required_for_p0: bool,
    sampling_mode: str,
    measurement_source: str,
    expected_tool: str,
    permission_need: str,
    collection_overhead: str,
    expected_artifact: str,
    join_key: list[str],
    time_base: str,
    validation_method: str,
    acceptance_rule: str,
    fallback: str,
) -> list[dict[str, Any]]:
    return [
        _field(
            profile=profile,
            name=name,
            meaning=meaning,
            layer=layer,
            field_type=field_type,
            unit=unit,
            required_for_p0=required_for_p0,
            sampling_mode=sampling_mode,
            measurement_source=measurement_source,
            expected_tool=expected_tool,
            permission_need=permission_need,
            collection_overhead=collection_overhead,
            expected_artifact=expected_artifact,
            join_key=join_key,
            time_base=time_base,
            validation_method=validation_method,
            acceptance_rule=acceptance_rule,
            fallback=fallback,
        )
        for name, meaning, field_type, unit in names
    ]


def build_field_catalog() -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []

    fields.extend(_profile_fields(
        "server_observability_profile",
        "server",
        [
            ("os_name", "operating system name", "inventory", "text"),
            ("kernel_version", "kernel version", "inventory", "text"),
            ("cann_version", "CANN version", "inventory", "text"),
            ("driver_version", "Ascend driver version", "inventory", "text"),
            ("firmware_version", "device firmware version", "inventory", "text"),
            ("torch_npu_version", "torch-npu version", "inventory", "text"),
            ("mindie_version", "MindIE version", "inventory", "text"),
            ("vllm_ascend_version", "vLLM-Ascend version", "inventory", "text"),
            ("container_privileged", "whether current container is privileged", "inventory", "bool"),
            ("visible_npu_count", "number of visible NPUs", "counter", "count"),
        ],
        required_for_p0=True,
        sampling_mode="one_shot",
        measurement_source="host and container inventory commands",
        expected_tool="uname, python, npu-smi, container runtime metadata",
        permission_need="shell_access",
        collection_overhead="low",
        expected_artifact="manifest.yaml",
        join_key=["profile_run_id"],
        time_base="host_wall_clock",
        validation_method="compare command outputs with manifest fields",
        acceptance_rule="measurable if command returns a non-empty value or explicit not_applicable",
        fallback="record unknown with command failure evidence",
    ))

    fields.extend(_profile_fields(
        "request_runtime_profile",
        "runtime",
        [
            ("arrival_time_ns", "request arrival timestamp", "event", "ns"),
            ("enqueue_time_ns", "request enqueue timestamp", "event", "ns"),
            ("dequeue_time_ns", "request dequeue timestamp", "event", "ns"),
            ("queue_wait_us", "request queue wait duration", "metric", "us"),
            ("admission_decision", "request admission decision", "event", "text"),
            ("batch_id", "runtime batch identifier", "event", "text"),
            ("batch_size", "runtime batch size", "counter", "count"),
            ("prefill_start_ns", "prefill start timestamp", "event", "ns"),
            ("prefill_end_ns", "prefill end timestamp", "event", "ns"),
            ("decode_step_start_ns", "decode step start timestamp", "event", "ns"),
            ("decode_step_end_ns", "decode step end timestamp", "event", "ns"),
            ("sampling_end_ns", "sampling end timestamp", "event", "ns"),
            ("jct_us", "job completion time", "metric", "us"),
        ],
        required_for_p0=True,
        sampling_mode="per_request",
        measurement_source="runtime request log or wrapper log",
        expected_tool="vLLM/MindIE log hook or wrapper logger",
        permission_need="app_log_access",
        collection_overhead="low",
        expected_artifact="runtime_queue_trace.jsonl",
        join_key=["trace_id", "request_id", "phase"],
        time_base="host_monotonic_ns",
        validation_method="run synthetic single request and verify monotonic timestamps",
        acceptance_rule="measurable if non-null for at least 95 percent of requests",
        fallback="wrapper-level request timestamps",
    ))

    fields.extend(_profile_fields(
        "scheduler_policy_profile",
        "runtime",
        [
            ("policy_name", "scheduler or cache policy name", "event", "text"),
            ("why_this_device", "reason device was selected", "event", "text"),
            ("why_prefetch", "reason prefetch was issued", "event", "text"),
            ("why_evict", "reason object was evicted", "event", "text"),
            ("why_recompute", "reason recompute was selected", "event", "text"),
            ("cache_allocation_event", "cache allocation event", "event", "text"),
            ("cache_free_event", "cache free event", "event", "text"),
            ("pin_unpin_event", "pin or unpin event", "event", "text"),
            ("ttl_expiry_event", "TTL expiry event", "event", "text"),
            ("backpressure_event", "backpressure event", "event", "text"),
            ("reject_reason", "request rejection reason", "event", "text"),
        ],
        required_for_p0=False,
        sampling_mode="per_request",
        measurement_source="runtime decision log",
        expected_tool="runtime hook or wrapper logger",
        permission_need="framework_hook",
        collection_overhead="medium",
        expected_artifact="runtime_queue_trace.jsonl",
        join_key=["trace_id", "request_id", "phase"],
        time_base="host_monotonic_ns",
        validation_method="verify decisions align with synthetic queue and cache actions",
        acceptance_rule="partial if decision exists at request granularity without object granularity",
        fallback="record unavailable framework hook gap",
    ))

    fields.extend(_profile_fields(
        "operator_timeline_profile",
        "operator",
        [
            ("layer_id", "model layer identifier", "event", "count"),
            ("op_name", "framework operator name", "event", "text"),
            ("kernel_name", "device kernel name", "event", "text"),
            ("cann_op_name", "CANN operator name", "event", "text"),
            ("input_shape", "operator input shape", "event", "text"),
            ("dtype", "operator dtype", "event", "text"),
            ("tiling_id", "tiling identifier", "event", "text"),
            ("launch_overhead_us", "kernel launch overhead", "metric", "us"),
            ("kernel_duration_us", "kernel duration", "metric", "us"),
            ("stream_id", "device stream identifier", "event", "text"),
            ("graph_compile_us", "graph compile duration", "metric", "us"),
            ("graph_cache_hit", "graph cache hit flag", "event", "bool"),
            ("dynamic_shape_fallback", "dynamic shape fallback flag", "event", "bool"),
        ],
        required_for_p0=True,
        sampling_mode="per_layer",
        measurement_source="CANN profiler timeline",
        expected_tool="CANN profiler",
        permission_need="profiler_permission",
        collection_overhead="high",
        expected_artifact="operator_timeline.jsonl",
        join_key=["trace_id", "phase", "layer_id", "stream_id"],
        time_base="cann_device_timeline",
        validation_method="run small model profile and verify timeline has ordered kernel events",
        acceptance_rule="partial if kernel events exist without request_id alignment",
        fallback="framework log operator timing if profiler unavailable",
    ))

    fields.extend(_profile_fields(
        "npu_hbm_profile",
        "hbm",
        [
            ("ai_core_util", "AI Core utilization", "counter", "percent"),
            ("aiv_util", "AIV utilization", "counter", "percent"),
            ("cube_util", "Cube utilization", "counter", "percent"),
            ("npu_busy_time_us", "NPU busy time", "metric", "us"),
            ("npu_idle_time_us", "NPU idle time", "metric", "us"),
            ("hbm_allocated_bytes", "allocated HBM bytes", "counter", "bytes"),
            ("hbm_reserved_bytes", "reserved HBM bytes", "counter", "bytes"),
            ("hbm_free_bytes", "free HBM bytes", "counter", "bytes"),
            ("hbm_peak_bytes", "peak HBM bytes", "counter", "bytes"),
            ("hbm_fragmentation_ratio", "HBM fragmentation ratio", "derived_metric", "ratio"),
            ("workspace_peak_bytes", "workspace peak bytes", "counter", "bytes"),
            ("kv_pool_bytes", "KV pool bytes", "counter", "bytes"),
            ("expert_cache_bytes", "expert cache bytes", "counter", "bytes"),
            ("hbm_read_gbps", "HBM read bandwidth", "counter", "GB/s"),
            ("hbm_write_gbps", "HBM write bandwidth", "counter", "GB/s"),
            ("hbm_stall_us", "HBM stall duration", "metric", "us"),
        ],
        required_for_p0=True,
        sampling_mode="periodic",
        measurement_source="npu-smi and CANN profiler counters",
        expected_tool="npu-smi, CANN profiler",
        permission_need="npu_visibility",
        collection_overhead="medium",
        expected_artifact="probe_results/npu_smi_probe.md",
        join_key=["profile_run_id", "npu_id", "timestamp_ns"],
        time_base="host_wall_clock_or_tool_timestamp",
        validation_method="compare repeated samples and verify non-negative counters",
        acceptance_rule="measurable if values are present for all visible NPUs",
        fallback="CANN profiler memory counters when npu-smi lacks field",
    ))

    fields.extend(_profile_fields(
        "cpu_dram_profile",
        "cpu_dram",
        [
            ("thread_name", "CPU thread name", "event", "text"),
            ("core_id", "CPU core identifier", "event", "count"),
            ("numa_node", "NUMA node identifier", "event", "count"),
            ("cpu_user_percent", "CPU user utilization", "counter", "percent"),
            ("cpu_sys_percent", "CPU system utilization", "counter", "percent"),
            ("cpu_iowait_percent", "CPU iowait utilization", "counter", "percent"),
            ("context_switches", "context switch count", "counter", "count"),
            ("runqueue_length", "runqueue length", "counter", "count"),
            ("scheduler_time_us", "scheduler time", "metric", "us"),
            ("tokenizer_time_us", "tokenizer time", "metric", "us"),
            ("sampler_time_us", "sampler time", "metric", "us"),
            ("cache_lookup_time_us", "cache lookup time", "metric", "us"),
            ("dram_read_gbps", "DRAM read bandwidth", "counter", "GB/s"),
            ("dram_write_gbps", "DRAM write bandwidth", "counter", "GB/s"),
            ("pinned_memory_bytes", "pinned memory bytes", "counter", "bytes"),
            ("page_faults", "page fault count", "counter", "count"),
            ("host_oom_event", "host OOM event", "event", "bool"),
        ],
        required_for_p0=True,
        sampling_mode="periodic",
        measurement_source="perf, pidstat, numastat, runtime logs",
        expected_tool="perf, pidstat, numastat",
        permission_need="host_perf_or_proc_access",
        collection_overhead="medium",
        expected_artifact="probe_results/perf_probe.md",
        join_key=["profile_run_id", "pid", "thread_id", "timestamp_ns"],
        time_base="host_monotonic_ns",
        validation_method="verify counters change during synthetic CPU workload",
        acceptance_rule="partial if process-level counters exist without request_id alignment",
        fallback="process-level ps and procfs samples",
    ))

    fields.extend(_profile_fields(
        "transfer_overlap_profile",
        "transfer",
        [
            ("direction", "copy direction", "event", "text"),
            ("transfer_bytes", "copy size", "counter", "bytes"),
            ("transfer_latency_us", "copy latency", "metric", "us"),
            ("effective_gbps", "effective transfer bandwidth", "metric", "GB/s"),
            ("setup_cost_us", "copy setup cost", "metric", "us"),
            ("copy_submit_ns", "copy submit timestamp", "event", "ns"),
            ("copy_complete_ns", "copy completion timestamp", "event", "ns"),
            ("copy_stream_id", "copy stream identifier", "event", "text"),
            ("compute_stream_id", "compute stream identifier", "event", "text"),
            ("compute_overlap_us", "compute time overlapping copy", "derived_metric", "us"),
            ("copy_exposed_us", "copy time exposed on critical path", "derived_metric", "us"),
            ("overlap_ratio", "copy and compute overlap ratio", "derived_metric", "ratio"),
            ("sync_barrier_event", "sync barrier event", "event", "text"),
            ("event_wait_us", "event wait duration", "metric", "us"),
        ],
        required_for_p0=True,
        sampling_mode="microbench",
        measurement_source="copy microbench and CANN timeline",
        expected_tool="custom copy microbench, CANN profiler",
        permission_need="npu_runtime_access",
        collection_overhead="medium",
        expected_artifact="copy_overlap_trace.csv",
        join_key=["trace_id", "stream_id", "object_id", "timestamp_ns"],
        time_base="host_monotonic_ns_and_cann_device_timeline",
        validation_method="compare no-overlap and intentional-overlap microbench runs",
        acceptance_rule="partial if host-side overlap estimate exists without device stream alignment",
        fallback="host-side submit and complete timestamps",
    ))

    fields.extend(_profile_fields(
        "ssd_io_profile",
        "ssd",
        [
            ("seq_read_gbps", "sequential read bandwidth", "metric", "GB/s"),
            ("seq_write_gbps", "sequential write bandwidth", "metric", "GB/s"),
            ("random_read_iops", "random read IOPS", "metric", "IOPS"),
            ("random_write_iops", "random write IOPS", "metric", "IOPS"),
            ("qd1_iops", "QD1 IOPS", "metric", "IOPS"),
            ("qd4_iops", "QD4 IOPS", "metric", "IOPS"),
            ("qd32_iops", "QD32 IOPS", "metric", "IOPS"),
            ("qd64_iops", "QD64 IOPS", "metric", "IOPS"),
            ("io_p50_us", "I/O p50 latency", "metric", "us"),
            ("io_p95_us", "I/O p95 latency", "metric", "us"),
            ("io_p99_us", "I/O p99 latency", "metric", "us"),
            ("io_p999_us", "I/O p999 latency", "metric", "us"),
            ("io_size_histogram", "I/O size histogram", "trace", "text"),
            ("direct_io_enabled", "direct I/O flag", "event", "bool"),
            ("page_cache_used", "page cache flag", "event", "bool"),
            ("mmap_used", "mmap flag", "event", "bool"),
            ("readahead_kb", "readahead size", "counter", "KB"),
            ("submit_path", "I/O submit path", "event", "text"),
            ("ssd_temperature_c", "SSD temperature", "counter", "C"),
            ("ssd_throttling_event", "SSD throttling event", "event", "bool"),
        ],
        required_for_p0=False,
        sampling_mode="microbench",
        measurement_source="fio, iostat, lsblk, smartctl when available",
        expected_tool="fio, iostat, lsblk",
        permission_need="block_device_read_access",
        collection_overhead="high",
        expected_artifact="probe_results/fio_probe.md",
        join_key=["profile_run_id", "device_id"],
        time_base="fio_timestamp",
        validation_method="verify fio reports non-empty latency and IOPS sections",
        acceptance_rule="measurable for capability profile if fio runs successfully on configured scratch path",
        fallback="lsblk and iostat inventory without workload",
    ))

    common_object_fields = [
        ("object_type", "state object type", "event", "text"),
        ("object_id", "state object identifier", "event", "text"),
        ("owner_request", "owning request identifier", "event", "text"),
        ("layer_id", "owning layer identifier", "event", "count"),
        ("object_bytes", "state object size", "counter", "bytes"),
        ("tier", "storage or memory tier", "event", "text"),
        ("lifecycle_event", "state object lifecycle event", "event", "text"),
        ("load_cost_us", "object load cost", "metric", "us"),
        ("evict_cost_us", "object evict cost", "metric", "us"),
        ("recompute_cost_us", "object recompute cost", "metric", "us"),
        ("hotness", "object hotness score", "derived_metric", "score"),
        ("next_use", "predicted next use", "derived_metric", "text"),
        ("consistency_scope", "object consistency scope", "event", "text"),
    ]
    fields.extend(_profile_fields(
        "state_object_profile",
        "state_object",
        common_object_fields,
        required_for_p0=True,
        sampling_mode="per_request",
        measurement_source="runtime object event hook",
        expected_tool="runtime hook or wrapper logger",
        permission_need="framework_hook",
        collection_overhead="medium",
        expected_artifact="state_object_trace.jsonl",
        join_key=["trace_id", "request_id", "object_id", "layer_id"],
        time_base="host_monotonic_ns",
        validation_method="verify create and delete lifecycle events for synthetic request objects",
        acceptance_rule="blocked until object_id and lifecycle_event are emitted",
        fallback="derive coarse object events from runtime logs",
    ))

    fields.extend(_profile_fields(
        "kv_prefix_profile",
        "state_object",
        [
            ("kv_object_id", "KV object identifier", "event", "text"),
            ("tokens_range", "token range covered by KV object", "event", "text"),
            ("block_size", "KV block size", "counter", "tokens"),
            ("block_table_entries", "KV block table entries", "counter", "count"),
            ("kv_fragmentation_ratio", "KV fragmentation ratio", "derived_metric", "ratio"),
            ("hit_tier", "tier where KV or prefix hit occurred", "event", "text"),
            ("miss_reason", "KV or prefix miss reason", "event", "text"),
            ("prefix_hash", "prefix hash", "event", "text"),
            ("matched_tokens", "matched prefix token count", "counter", "tokens"),
            ("position_shift", "prefix position shift", "metric", "tokens"),
            ("reuse_distance", "reuse distance", "metric", "requests"),
            ("restore_vs_recompute_decision", "restore versus recompute decision", "event", "text"),
        ],
        required_for_p0=True,
        sampling_mode="per_request",
        measurement_source="KV and prefix cache runtime hook",
        expected_tool="runtime hook or wrapper logger",
        permission_need="framework_hook",
        collection_overhead="medium",
        expected_artifact="state_object_trace.jsonl",
        join_key=["trace_id", "request_id", "object_id", "layer_id"],
        time_base="host_monotonic_ns",
        validation_method="run repeated-prefix workload and verify hit or miss events",
        acceptance_rule="partial if prefix hit is request-level only without per-layer KV block mapping",
        fallback="request-level prefix cache logs",
    ))

    fields.extend(_profile_fields(
        "moe_expert_profile",
        "state_object",
        [
            ("router_scores", "router scores or logits", "trace", "text"),
            ("top_k_expert_ids", "selected top-k expert identifiers", "trace", "text"),
            ("top_k_probs", "top-k expert probabilities", "trace", "text"),
            ("router_entropy", "router entropy", "derived_metric", "score"),
            ("expert_frequency", "expert frequency", "counter", "count"),
            ("expert_hotness", "expert hotness", "derived_metric", "score"),
            ("expert_reuse_distance", "expert reuse distance", "metric", "tokens"),
            ("expert_resident", "expert resident flag", "event", "bool"),
            ("expert_prefetched", "expert prefetched flag", "event", "bool"),
            ("expert_evicted", "expert evicted flag", "event", "bool"),
            ("expert_hit", "expert hit flag", "event", "bool"),
            ("expert_miss_tier", "tier where expert miss was served", "event", "text"),
            ("expert_load_latency_us", "expert load latency", "metric", "us"),
            ("prefetch_lead_time_us", "prefetch lead time", "metric", "us"),
            ("prefetch_accuracy", "prefetch accuracy", "derived_metric", "ratio"),
        ],
        required_for_p0=False,
        sampling_mode="per_layer",
        measurement_source="MoE router and expert cache hook",
        expected_tool="model hook or profiler operator mapping",
        permission_need="framework_hook",
        collection_overhead="high",
        expected_artifact="expert_trace.jsonl",
        join_key=["trace_id", "request_id", "layer_id", "object_id"],
        time_base="host_monotonic_ns",
        validation_method="run MoE workload and verify top-k expert ids exist for MoE layers",
        acceptance_rule="blocked until router top-k or expert cache events are emitted",
        fallback="operator-level MoE dispatch timing without expert identity",
    ))

    fields.extend(_profile_fields(
        "power_stability_profile",
        "power",
        [
            ("npu_power_w", "NPU power", "counter", "W"),
            ("cpu_power_w", "CPU package power", "counter", "W"),
            ("dram_power_w", "DRAM power", "counter", "W"),
            ("ssd_power_w", "SSD power", "counter", "W"),
            ("system_power_w", "system power", "counter", "W"),
            ("energy_per_token_j", "energy per token", "derived_metric", "J/token"),
            ("npu_temperature_c", "NPU temperature", "counter", "C"),
            ("cpu_temperature_c", "CPU temperature", "counter", "C"),
            ("ssd_temperature_c", "SSD temperature", "counter", "C"),
            ("npu_frequency_mhz", "NPU frequency", "counter", "MHz"),
            ("cpu_frequency_mhz", "CPU frequency", "counter", "MHz"),
            ("thermal_throttling_event", "thermal throttling event", "event", "bool"),
            ("oom_event", "OOM event", "event", "bool"),
            ("cann_error_event", "CANN error event", "event", "bool"),
            ("ssd_timeout_event", "SSD timeout event", "event", "bool"),
            ("long_run_p99_drift", "long run p99 drift", "derived_metric", "ratio"),
        ],
        required_for_p0=False,
        sampling_mode="periodic",
        measurement_source="npu-smi, system sensors, logs",
        expected_tool="npu-smi, sensors, journal logs",
        permission_need="host_sensor_access",
        collection_overhead="low",
        expected_artifact="probe_results/npu_smi_probe.md",
        join_key=["profile_run_id", "timestamp_ns"],
        time_base="host_wall_clock",
        validation_method="verify repeated samples remain within physical ranges",
        acceptance_rule="partial if NPU power and temperature are available without CPU or SSD power",
        fallback="temperature-only stability tracking",
    ))

    fields.extend(_profile_fields(
        "microbench_profile",
        "microbench",
        [
            ("npu_op_by_shape", "NPU operator latency by shape", "trace", "text"),
            ("cpu_kernel_by_shape", "CPU kernel latency by shape", "trace", "text"),
            ("ddr_bandwidth_gbps", "DDR bandwidth", "metric", "GB/s"),
            ("ssd_iops", "SSD IOPS", "metric", "IOPS"),
            ("h2d_latency_us", "H2D latency", "metric", "us"),
            ("d2h_latency_us", "D2H latency", "metric", "us"),
            ("h2d_bandwidth_gbps", "H2D bandwidth", "metric", "GB/s"),
            ("d2h_bandwidth_gbps", "D2H bandwidth", "metric", "GB/s"),
            ("pageable_copy_latency_us", "pageable copy latency", "metric", "us"),
            ("pinned_copy_latency_us", "pinned copy latency", "metric", "us"),
            ("sync_copy_latency_us", "sync copy latency", "metric", "us"),
            ("async_copy_latency_us", "async copy latency", "metric", "us"),
            ("copy_overlap_ratio", "copy overlap ratio", "derived_metric", "ratio"),
        ],
        required_for_p0=True,
        sampling_mode="microbench",
        measurement_source="safe microbench commands and existing tools",
        expected_tool="fio, perf, CANN sample or custom copy microbench",
        permission_need="tool_specific_access",
        collection_overhead="high",
        expected_artifact="probe_results/fio_probe.md",
        join_key=["profile_run_id", "benchmark_id"],
        time_base="host_monotonic_ns",
        validation_method="verify command exits zero and reports numeric metric",
        acceptance_rule="partial if inventory and tool availability are verified before workload execution",
        fallback="record tool availability only",
    ))

    return fields
```

- [ ] **Step 4: Run catalog tests**

Run:

```bash
python -m pytest tests/observability_profile/test_catalog.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/observability_profile/catalog.py tests/observability_profile/test_catalog.py
git commit -m "feat: add observability field catalog"
```

---

### Task 3: Manifest Generator

**Files:**
- Create: `tools/observability_profile/manifest.py`
- Create: `tests/observability_profile/test_manifest.py`

- [ ] **Step 1: Write manifest tests**

Create `tests/observability_profile/test_manifest.py` with:

```python
from pathlib import Path

from tools.observability_profile.manifest import build_manifest, stable_hash


def test_stable_hash_is_ordered_and_repeatable():
    first = stable_hash({"b": "2", "a": "1"})
    second = stable_hash({"a": "1", "b": "2"})
    assert first == second
    assert len(first) == 16


def test_build_manifest_contains_required_run_identity(tmp_path: Path):
    manifest = build_manifest(
        run_id="obs_2026_0703_atlas800t_a2_001",
        output_root=tmp_path,
        server_id="atlas800t-a2-node-001",
        operator="codex",
        probe_script_version="0.1.0",
    )
    assert manifest["profile_run_id"] == "obs_2026_0703_atlas800t_a2_001"
    assert manifest["schema_version"] == "0.1.0"
    assert manifest["server_id"] == "atlas800t-a2-node-001"
    assert manifest["operator"] == "codex"
    assert manifest["hardware_topology_hash"]
    assert manifest["software_stack_hash"]
    assert manifest["probe_script_version"] == "0.1.0"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/observability_profile/test_manifest.py -q
```

Expected: FAIL because `tools.observability_profile.manifest` does not exist.

- [ ] **Step 3: Implement manifest generation**

Create `tools/observability_profile/manifest.py` with:

```python
from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.observability_profile import __version__


def _run_text(command: list[str], timeout: int = 5) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return f"{type(exc).__name__}: {exc}"
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    return output[:4000]


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _inside_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    cgroup = Path("/proc/1/cgroup")
    if cgroup.exists():
        text = cgroup.read_text(errors="ignore")
        return "docker" in text or "containerd" in text or "kubepods" in text
    return False


def _container_id() -> str | None:
    cgroup = Path("/proc/self/cgroup")
    if not cgroup.exists():
        return None
    text = cgroup.read_text(errors="ignore")
    for token in text.replace("/", " ").replace(":", " ").split():
        if len(token) >= 12 and all(ch.isalnum() or ch in "-_" for ch in token):
            return token[:64]
    return None


def _git_commit(repo_root: Path) -> str:
    result = _run_text(["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"])
    if "fatal:" in result or "FileNotFoundError" in result:
        return "unknown"
    return result.splitlines()[0].strip() if result.strip() else "unknown"


def build_manifest(
    *,
    run_id: str,
    output_root: Path,
    server_id: str,
    operator: str,
    probe_script_version: str = __version__,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    repo_root = Path(__file__).resolve().parents[2]
    hardware_inputs = {
        "npu_smi": _run_text(["npu-smi", "info"]),
        "lspci": _run_text(["lspci"]),
        "numactl": _run_text(["numactl", "--hardware"]),
        "lsblk": _run_text(["lsblk", "-J"]),
    }
    software_inputs = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cann": _run_text(["bash", "-lc", "echo ${ASCEND_HOME_PATH:-unknown} && which npu-smi || true"]),
        "torch_npu": _run_text(["python", "-c", "import torch_npu; print(torch_npu.__version__)"]),
        "mindie": _run_text(["bash", "-lc", "python -c 'import mindie; print(getattr(mindie, \"__version__\", \"unknown\"))'"]),
        "vllm_ascend": _run_text(["bash", "-lc", "python -c 'import vllm_ascend; print(getattr(vllm_ascend, \"__version__\", \"unknown\"))'"]),
        "container_image": os.environ.get("CONTAINER_IMAGE", "unknown"),
    }
    return {
        "profile_run_id": run_id,
        "schema_version": "0.1.0",
        "server_id": server_id,
        "timestamp_start": now,
        "timestamp_end": None,
        "operator": operator,
        "git_commit": _git_commit(repo_root),
        "host_name": socket.gethostname(),
        "container_id": _container_id(),
        "container_image": os.environ.get("CONTAINER_IMAGE", "unknown"),
        "inside_container": _inside_container(),
        "container_privileged": os.geteuid() == 0,
        "cann_version": software_inputs["cann"],
        "driver_version": "unknown",
        "npu_count": "unknown",
        "hbm_per_npu_gb": "unknown",
        "field_catalog_version": "0.1.0",
        "hardware_topology_hash": stable_hash(hardware_inputs),
        "software_stack_hash": stable_hash(software_inputs),
        "probe_script_version": probe_script_version,
        "output_root": str(output_root),
        "notes": "Generated by P0 observability profile tool.",
    }
```

- [ ] **Step 4: Run manifest tests**

Run:

```bash
python -m pytest tests/observability_profile/test_manifest.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/observability_profile/manifest.py tests/observability_profile/test_manifest.py
git commit -m "feat: add observability manifest generation"
```

---

### Task 4: Safe Probe Runner

**Files:**
- Create: `tools/observability_profile/probes.py`
- Create: `tests/observability_profile/test_probes.py`

- [ ] **Step 1: Write probe tests**

Create `tests/observability_profile/test_probes.py` with:

```python
from tools.observability_profile.probes import ProbeCommand, run_probe_command, run_standard_probes


def test_run_probe_command_records_exit_code_and_context():
    result = run_probe_command(ProbeCommand(name="python_version", command=["python", "--version"]))
    assert result["tool"] == "python_version"
    assert result["exit_code"] == 0
    assert result["runtime_ms"] >= 0
    assert "run_as_user" in result
    assert "inside_container" in result
    assert "output_excerpt" in result


def test_standard_probes_are_non_empty():
    probes = run_standard_probes()
    names = {probe["tool"] for probe in probes}
    assert "npu_smi_probe" in names
    assert "container_permission_probe" in names
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/observability_profile/test_probes.py -q
```

Expected: FAIL because `tools.observability_profile.probes` does not exist.

- [ ] **Step 3: Implement safe probes**

Create `tools/observability_profile/probes.py` with:

```python
from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProbeCommand:
    name: str
    command: list[str]
    maps_to_fields: tuple[str, ...] = ()
    timeout_s: int = 10


def inside_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    cgroup = Path("/proc/1/cgroup")
    if not cgroup.exists():
        return False
    text = cgroup.read_text(errors="ignore")
    return "docker" in text or "containerd" in text or "kubepods" in text


def run_probe_command(probe: ProbeCommand) -> dict[str, Any]:
    start = time.time()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start))
    try:
        completed = subprocess.run(
            probe.command,
            capture_output=True,
            text=True,
            timeout=probe.timeout_s,
            check=False,
        )
        exit_code = completed.returncode
        output = "\n".join(
            part for part in [completed.stdout.strip(), completed.stderr.strip()] if part
        )
        available = exit_code == 0
        blocked_category = None if available else "tool_missing"
        blocked_detail = None if available else f"exit_code={exit_code}"
    except FileNotFoundError as exc:
        exit_code = 127
        output = str(exc)
        available = False
        blocked_category = "tool_missing"
        blocked_detail = str(exc)
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        output = str(exc)
        available = False
        blocked_category = "unknown"
        blocked_detail = f"timeout after {probe.timeout_s}s"
    end = time.time()
    end_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end))
    permission_status = "ok" if available else "blocked"
    return {
        "tool": probe.name,
        "available": available,
        "permission_status": permission_status,
        "command": shlex.join(probe.command),
        "exit_code": exit_code,
        "start_time": start_iso,
        "end_time": end_iso,
        "runtime_ms": int((end - start) * 1000),
        "run_as_user": str(os.geteuid()),
        "inside_container": inside_container(),
        "container_privileged": os.geteuid() == 0,
        "output_excerpt": output[:2000],
        "artifact_path": None,
        "maps_to_fields": list(probe.maps_to_fields),
        "blocked_reason": {"category": blocked_category, "detail": blocked_detail},
    }


STANDARD_PROBES = [
    ProbeCommand(
        name="npu_smi_probe",
        command=["npu-smi", "info"],
        maps_to_fields=("npu_hbm_profile.hbm_free_bytes", "power_stability_profile.npu_power_w"),
    ),
    ProbeCommand(
        name="cann_profiler_probe",
        command=["bash", "-lc", "which msprof && msprof --help | head -40"],
        maps_to_fields=("operator_timeline_profile.kernel_duration_us", "npu_hbm_profile.hbm_read_gbps"),
    ),
    ProbeCommand(
        name="perf_probe",
        command=["perf", "--version"],
        maps_to_fields=("cpu_dram_profile.context_switches", "cpu_dram_profile.cpu_user_percent"),
    ),
    ProbeCommand(
        name="ebpf_probe",
        command=["bash", "-lc", "which bpftrace && bpftrace --version"],
        maps_to_fields=("cpu_dram_profile.scheduler_time_us",),
    ),
    ProbeCommand(
        name="fio_probe",
        command=["fio", "--version"],
        maps_to_fields=("ssd_io_profile.random_read_iops", "microbench_profile.ssd_iops"),
    ),
    ProbeCommand(
        name="numa_probe",
        command=["numactl", "--hardware"],
        maps_to_fields=("cpu_dram_profile.numa_node", "cpu_dram_profile.dram_read_gbps"),
    ),
    ProbeCommand(
        name="container_permission_probe",
        command=["bash", "-lc", "id && test -r /proc/1/cgroup && head -5 /proc/1/cgroup"],
        maps_to_fields=("server_observability_profile.container_privileged",),
    ),
]


def run_standard_probes() -> list[dict[str, Any]]:
    return [run_probe_command(probe) for probe in STANDARD_PROBES]
```

- [ ] **Step 4: Run probe tests**

Run:

```bash
python -m pytest tests/observability_profile/test_probes.py -q
```

Expected: PASS. Some probes may return `available: false` on a Mac or non-Ascend machine; the test only requires structured records.

- [ ] **Step 5: Commit**

```bash
git add tools/observability_profile/probes.py tests/observability_profile/test_probes.py
git commit -m "feat: add safe observability probes"
```

---

### Task 5: Field Availability Evaluation

**Files:**
- Create: `tools/observability_profile/availability.py`
- Create: `tests/observability_profile/test_availability.py`

- [ ] **Step 1: Write availability tests**

Create `tests/observability_profile/test_availability.py` with:

```python
from tools.observability_profile.availability import apply_probe_evidence, summarize_availability
from tools.observability_profile.catalog import build_field_catalog


def test_apply_probe_evidence_marks_mapped_fields_measurable():
    fields = build_field_catalog()
    probes = [
        {
            "tool": "npu_smi_probe",
            "available": True,
            "permission_status": "ok",
            "artifact_path": "probe_results/npu_smi_probe.md",
            "maps_to_fields": ["npu_hbm_profile.hbm_free_bytes"],
            "blocked_reason": {"category": None, "detail": None},
        }
    ]
    updated = apply_probe_evidence(fields, probes, checked_at="2026-07-03T00:00:00Z")
    by_key = {f"{field['profile']}.{field['name']}": field for field in updated}
    availability = by_key["npu_hbm_profile.hbm_free_bytes"]["availability"]
    assert availability["status"] == "measurable"
    assert availability["confidence"] == "medium"
    assert availability["evidence_probe"] == "npu_smi_probe"


def test_summarize_availability_counts_statuses():
    fields = build_field_catalog()
    summary = summarize_availability(fields)
    assert "request_runtime_profile" in summary
    assert summary["request_runtime_profile"]["unknown"] > 0
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/observability_profile/test_availability.py -q
```

Expected: FAIL because `tools.observability_profile.availability` does not exist.

- [ ] **Step 3: Implement availability evaluation**

Create `tools/observability_profile/availability.py` with:

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any

from tools.observability_profile.constants import AVAILABILITY_STATUSES


def _field_key(field: dict[str, Any]) -> str:
    return f"{field['profile']}.{field['name']}"


def apply_probe_evidence(
    fields: list[dict[str, Any]],
    probes: list[dict[str, Any]],
    *,
    checked_at: str,
) -> list[dict[str, Any]]:
    updated = deepcopy(fields)
    by_key = {_field_key(field): field for field in updated}

    for probe in probes:
        for mapped_field in probe.get("maps_to_fields", []):
            field = by_key.get(mapped_field)
            if field is None:
                continue
            availability = field["availability"]
            availability["evidence_probe"] = probe["tool"]
            availability["evidence_artifact"] = probe.get("artifact_path")
            availability["last_checked_at"] = checked_at
            if probe.get("available") and probe.get("permission_status") in {"ok", "limited"}:
                availability["status"] = "measurable" if probe["permission_status"] == "ok" else "partial"
                availability["confidence"] = "medium"
                availability["blocked_reason"] = {"category": None, "detail": None}
                availability["partial_reason"] = None if probe["permission_status"] == "ok" else "tool reports limited permission"
            else:
                availability["status"] = "blocked"
                availability["confidence"] = "medium"
                availability["blocked_reason"] = probe.get(
                    "blocked_reason",
                    {"category": "unknown", "detail": "probe failed without blocked_reason"},
                )
    return updated


def summarize_availability(fields: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for field in fields:
        profile = field["profile"]
        status = field["availability"]["status"]
        if status not in AVAILABILITY_STATUSES:
            status = "unknown"
        summary.setdefault(profile, {state: 0 for state in AVAILABILITY_STATUSES})
        summary[profile][status] += 1
    return summary
```

- [ ] **Step 4: Run availability tests**

Run:

```bash
python -m pytest tests/observability_profile/test_availability.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/observability_profile/availability.py tests/observability_profile/test_availability.py
git commit -m "feat: add field availability evaluation"
```

---

### Task 6: Join-Key Readiness And P0 Acceptance

**Files:**
- Create: `tools/observability_profile/join_keys.py`
- Create: `tools/observability_profile/p0_acceptance.py`
- Create: `tests/observability_profile/test_join_keys.py`

- [ ] **Step 1: Write join-key and P0 tests**

Create `tests/observability_profile/test_join_keys.py` with:

```python
from tools.observability_profile.catalog import build_field_catalog
from tools.observability_profile.join_keys import build_join_key_readiness
from tools.observability_profile.p0_acceptance import build_p0_acceptance_fields


def test_join_key_readiness_includes_time_alignment():
    readiness = build_join_key_readiness()
    pairs = {item["profile_pair"]: item for item in readiness["join_key_readiness"]}
    pair = pairs["state_object_profile + transfer_overlap_profile"]
    assert pair["required_keys"] == ["trace_id", "object_id", "lifecycle_event", "stream_id"]
    assert "time_alignment" in pair
    assert pair["time_alignment"]["alignment_method"] == "unavailable"


def test_p0_acceptance_only_includes_measurable_or_partial_required_fields():
    fields = build_field_catalog()
    fields[0]["required_for_p0"] = True
    fields[0]["availability"]["status"] = "measurable"
    fields[1]["required_for_p0"] = True
    fields[1]["availability"]["status"] = "blocked"
    result = build_p0_acceptance_fields(fields)
    statuses = {item["status"] for item in result["p0_acceptance_fields"]}
    assert statuses == {"measurable"}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/observability_profile/test_join_keys.py -q
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement join-key readiness**

Create `tools/observability_profile/join_keys.py` with:

```python
from __future__ import annotations

from typing import Any


def build_join_key_readiness() -> dict[str, list[dict[str, Any]]]:
    return {
        "join_key_readiness": [
            {
                "profile_pair": "request_runtime_profile + operator_timeline_profile",
                "required_keys": ["trace_id", "request_id", "phase", "layer_id"],
                "status": "partial",
                "missing_keys": ["layer_id"],
                "time_alignment": {
                    "status": "unknown",
                    "time_bases": ["host_monotonic_ns", "cann_device_timeline"],
                    "alignment_method": "unavailable",
                    "max_expected_skew_us": None,
                    "consequence": "can attribute request-level delay, cannot attribute per-layer stall",
                },
                "consequence": "operator timeline cannot yet explain per-request slow tokens",
                "fix": "add layer_id mapping and wrapper event markers around prefill and decode",
            },
            {
                "profile_pair": "state_object_profile + transfer_overlap_profile",
                "required_keys": ["trace_id", "object_id", "lifecycle_event", "stream_id"],
                "status": "blocked",
                "missing_keys": ["object_id", "stream_id"],
                "time_alignment": {
                    "status": "unknown",
                    "time_bases": ["host_monotonic_ns", "cann_device_timeline"],
                    "alignment_method": "unavailable",
                    "max_expected_skew_us": None,
                    "consequence": "cannot prove object restore/load caused exposed copy time",
                },
                "consequence": "cannot attribute KV restore or expert load to copy overlap loss",
                "fix": "add object event hook, copy stream tagging, and wrapper event marker",
            },
            {
                "profile_pair": "moe_expert_profile + operator_timeline_profile",
                "required_keys": ["trace_id", "request_id", "layer_id", "object_id"],
                "status": "blocked",
                "missing_keys": ["object_id"],
                "time_alignment": {
                    "status": "unknown",
                    "time_bases": ["host_monotonic_ns", "cann_device_timeline"],
                    "alignment_method": "unavailable",
                    "max_expected_skew_us": None,
                    "consequence": "cannot prove expert miss caused TPOT spike",
                },
                "consequence": "MoE routing can be analyzed only after expert identity is available",
                "fix": "add router top-k capture and expert object identifiers",
            },
        ]
    }
```

- [ ] **Step 4: Implement P0 acceptance extraction**

Create `tools/observability_profile/p0_acceptance.py` with:

```python
from __future__ import annotations

from typing import Any


def build_p0_acceptance_fields(fields: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    accepted = []
    for field in fields:
        status = field["availability"]["status"]
        if not field["required_for_p0"] or status not in {"measurable", "partial"}:
            continue
        accepted.append(
            {
                "field": f"{field['profile']}.{field['name']}",
                "status": status,
                "source": field["expected_artifact"],
                "acceptance_rule": field["acceptance_rule"],
                "caveat": field["availability"].get("partial_reason"),
            }
        )
    return {"p0_acceptance_fields": accepted}
```

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest tests/observability_profile/test_join_keys.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/observability_profile/join_keys.py tools/observability_profile/p0_acceptance.py tests/observability_profile/test_join_keys.py
git commit -m "feat: add join key readiness and p0 acceptance"
```

---

### Task 7: Markdown Renderer And CLI Orchestrator

**Files:**
- Create: `tools/observability_profile/render.py`
- Create: `tools/observability_profile/cli.py`
- Create: `tests/observability_profile/test_cli.py`

- [ ] **Step 1: Write end-to-end CLI test**

Create `tests/observability_profile/test_cli.py` with:

```python
from pathlib import Path

import yaml

from tools.observability_profile.cli import run_observability_profile


def test_run_observability_profile_writes_all_outputs(tmp_path: Path):
    run_dir = run_observability_profile(
        output_base=tmp_path,
        run_id="obs_2026_0703_atlas800t_a2_001",
        server_id="atlas800t-a2-node-001",
        operator="codex",
        probes=[
            {
                "tool": "npu_smi_probe",
                "available": True,
                "permission_status": "ok",
                "command": "npu-smi info",
                "exit_code": 0,
                "start_time": "2026-07-03T00:00:00Z",
                "end_time": "2026-07-03T00:00:01Z",
                "runtime_ms": 1000,
                "run_as_user": "501",
                "inside_container": False,
                "container_privileged": False,
                "output_excerpt": "OK",
                "artifact_path": None,
                "maps_to_fields": ["npu_hbm_profile.hbm_free_bytes"],
                "blocked_reason": {"category": None, "detail": None},
            }
        ],
    )
    assert (run_dir / "manifest.yaml").exists()
    assert (run_dir / "server_observability_profile.md").exists()
    assert (run_dir / "field_availability.yaml").exists()
    assert (run_dir / "join_key_readiness.yaml").exists()
    assert (run_dir / "p0_acceptance_fields.yaml").exists()
    assert (run_dir / "probe_results" / "npu_smi_probe.md").exists()

    field_data = yaml.safe_load((run_dir / "field_availability.yaml").read_text())
    assert "fields" in field_data
    p0_data = yaml.safe_load((run_dir / "p0_acceptance_fields.yaml").read_text())
    assert "p0_acceptance_fields" in p0_data
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -m pytest tests/observability_profile/test_cli.py -q
```

Expected: FAIL because CLI and renderer do not exist.

- [ ] **Step 3: Implement Markdown renderer**

Create `tools/observability_profile/render.py` with:

```python
from __future__ import annotations

from typing import Any

from tools.observability_profile.availability import summarize_availability


def render_server_observability_profile(
    *,
    manifest: dict[str, Any],
    fields: list[dict[str, Any]],
    probes: list[dict[str, Any]],
    join_key_readiness: dict[str, Any],
    p0_acceptance_fields: dict[str, Any],
) -> str:
    summary = summarize_availability(fields)
    lines = [
        "# Server Observability Profile",
        "",
        "## 1. Run Summary",
        "",
        f"- profile_run_id: `{manifest['profile_run_id']}`",
        f"- server_id: `{manifest['server_id']}`",
        f"- schema_version: `{manifest['schema_version']}`",
        f"- hardware_topology_hash: `{manifest['hardware_topology_hash']}`",
        f"- software_stack_hash: `{manifest['software_stack_hash']}`",
        f"- probe_script_version: `{manifest['probe_script_version']}`",
        "",
        "## 2. Server And Tool Readiness",
        "",
    ]
    for probe in probes:
        lines.append(f"- `{probe['tool']}`: available={probe['available']} permission={probe['permission_status']} exit_code={probe['exit_code']}")
    lines.extend(["", "## 3. Profile-Level Observability", ""])
    for profile, counts in sorted(summary.items()):
        lines.append(
            f"- `{profile}`: measurable={counts['measurable']} partial={counts['partial']} blocked={counts['blocked']} unknown={counts['unknown']} not_applicable={counts['not_applicable']}"
        )
    lines.extend(["", "## 4. P0 Acceptance Fields", ""])
    for field in p0_acceptance_fields["p0_acceptance_fields"]:
        lines.append(f"- `{field['field']}`: {field['status']} from `{field['source']}`")
    lines.extend(["", "## 5. Join-Key And Time-Alignment Readiness", ""])
    for item in join_key_readiness["join_key_readiness"]:
        lines.append(f"- `{item['profile_pair']}`: {item['status']}; time_alignment={item['time_alignment']['status']}")
    lines.extend(["", "## 6. Gap Summary", ""])
    gaps: dict[str, int] = {}
    for field in fields:
        availability = field["availability"]
        if availability["status"] not in {"blocked", "unknown"}:
            continue
        category = availability.get("blocked_reason", {}).get("category") or "unknown"
        gaps[category] = gaps.get(category, 0) + 1
    for category, count in sorted(gaps.items()):
        lines.append(f"- `{category}`: {count}")
    lines.extend(["", "## 7. Recommended Next Actions", ""])
    lines.append("- Use `field_availability.yaml` and `join_key_readiness.yaml` to choose the first P0 probe fixes.")
    lines.append("- Do not treat SSD cold tier, runtime hooks, or MoE expert hooks as P0 performance optimization work.")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Implement CLI orchestration**

Create `tools/observability_profile/cli.py` with:

```python
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tools.observability_profile.availability import apply_probe_evidence
from tools.observability_profile.catalog import build_field_catalog
from tools.observability_profile.join_keys import build_join_key_readiness
from tools.observability_profile.manifest import build_manifest
from tools.observability_profile.p0_acceptance import build_p0_acceptance_fields
from tools.observability_profile.probes import run_standard_probes
from tools.observability_profile.render import render_server_observability_profile


def _write_yaml(path: Path, data: Any) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_probe_result(path: Path, probe: dict[str, Any]) -> None:
    content = [
        f"# {probe['tool']}",
        "",
        "```yaml",
        yaml.safe_dump(probe, allow_unicode=True, sort_keys=False).strip(),
        "```",
        "",
    ]
    path.write_text("\n".join(content), encoding="utf-8")


def run_observability_profile(
    *,
    output_base: Path,
    run_id: str,
    server_id: str,
    operator: str,
    probes: list[dict[str, Any]] | None = None,
) -> Path:
    run_dir = output_base / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_atlas800t-a2_observability_run"
    probe_dir = run_dir / "probe_results"
    probe_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(run_id=run_id, output_root=run_dir, server_id=server_id, operator=operator)
    probe_results = probes if probes is not None else run_standard_probes()
    for probe in probe_results:
        probe_path = probe_dir / f"{probe['tool']}.md"
        probe["artifact_path"] = str(probe_path.relative_to(run_dir))
        _write_probe_result(probe_path, probe)

    checked_at = datetime.now(timezone.utc).isoformat()
    fields = apply_probe_evidence(build_field_catalog(), probe_results, checked_at=checked_at)
    join_key_readiness = build_join_key_readiness()
    p0_acceptance_fields = build_p0_acceptance_fields(fields)

    _write_yaml(run_dir / "manifest.yaml", manifest)
    _write_yaml(run_dir / "field_availability.yaml", {"fields": fields})
    _write_yaml(run_dir / "join_key_readiness.yaml", join_key_readiness)
    _write_yaml(run_dir / "p0_acceptance_fields.yaml", p0_acceptance_fields)
    summary = render_server_observability_profile(
        manifest=manifest,
        fields=fields,
        probes=probe_results,
        join_key_readiness=join_key_readiness,
        p0_acceptance_fields=p0_acceptance_fields,
    )
    (run_dir / "server_observability_profile.md").write_text(summary, encoding="utf-8")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an AK observability profile run.")
    parser.add_argument(
        "--output-base",
        default="工作记录与进度笔记本/observability_profiles",
        help="Directory where the observability run directory will be created.",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--operator", default="codex")
    args = parser.parse_args()
    run_dir = run_observability_profile(
        output_base=Path(args.output_base),
        run_id=args.run_id,
        server_id=args.server_id,
        operator=args.operator,
    )
    print(run_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run CLI test**

Run:

```bash
python -m pytest tests/observability_profile/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Run all tests**

Run:

```bash
python -m pytest tests/observability_profile -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/observability_profile/render.py tools/observability_profile/cli.py tests/observability_profile/test_cli.py
git commit -m "feat: generate observability profile run outputs"
```

---

### Task 8: Documentation, P0 Execution Command, And Final Verification

**Files:**
- Create: `docs/superpowers/plans/2026-07-03-ak-observability-profile.md` already exists from this plan.
- Create: `工作记录与进度笔记本/07_可观测能力体检执行说明.md`

- [ ] **Step 1: Create the execution guide**

Create `工作记录与进度笔记本/07_可观测能力体检执行说明.md` with:

```markdown
# 07 可观测能力体检执行说明

## 目标

运行一次服务器可观测能力体检，生成 `observability_profiles/<run>/`。这不是性能测试，不判断模型性能优劣，也不承诺 KV offload、expert hot cache、SSD cold tier 或 CPU fallback 收益。

## 输出

一次体检应生成：

- `manifest.yaml`
- `server_observability_profile.md`
- `field_availability.yaml`
- `join_key_readiness.yaml`
- `p0_acceptance_fields.yaml`
- `probe_results/`

## 推荐命令

```bash
python -m tools.observability_profile.cli \
  --run-id obs_2026_0703_atlas800t_a2_001 \
  --server-id atlas800t-a2-node-001 \
  --operator codex
```

## 判读顺序

1. 先看 `manifest.yaml`，确认硬件拓扑、软件栈和 probe 脚本版本。
2. 再看 `field_availability.yaml`，确认每个字段是 `measurable`、`partial`、`blocked`、`unknown` 还是 `not_applicable`。
3. 再看 `join_key_readiness.yaml`，确认多源 trace 是否能通过 join key 和 time alignment 做归因。
4. 再看 `p0_acceptance_fields.yaml`，确认 P3/P4/P5 可引用的 P0 硬验收字段。
5. 最后看 `server_observability_profile.md`，只作为人读摘要。

## P0 边界

P0 只打通体检框架、工具权限、字段状态和 artifact 链路。不实现复杂 runtime hook，不做 SSD cold tier 性能优化，不做 MoE expert hot cache，也不做 trace-driven simulator。
```

- [ ] **Step 2: Run full test suite**

Run:

```bash
python -m pytest tests/observability_profile -q
```

Expected: PASS.

- [ ] **Step 3: Run a local dry-run profile**

Run:

```bash
python -m tools.observability_profile.cli \
  --run-id obs_2026_0703_atlas800t_a2_001 \
  --server-id atlas800t-a2-node-001 \
  --operator codex
```

Expected: command prints a path under `工作记录与进度笔记本/observability_profiles/`. It may mark Ascend-specific fields as `blocked` or `unknown` on non-Ascend machines.

- [ ] **Step 4: Verify required output files exist**

Run:

```bash
RUN_DIR="$(find 工作记录与进度笔记本/observability_profiles -maxdepth 1 -type d -name '*atlas800t-a2_observability_run' | sort | tail -1)"
test -f "$RUN_DIR/manifest.yaml"
test -f "$RUN_DIR/server_observability_profile.md"
test -f "$RUN_DIR/field_availability.yaml"
test -f "$RUN_DIR/join_key_readiness.yaml"
test -f "$RUN_DIR/p0_acceptance_fields.yaml"
test -d "$RUN_DIR/probe_results"
```

Expected: exit code 0.

- [ ] **Step 5: Inspect generated YAML keys**

Run:

```bash
python - <<'PY'
from pathlib import Path
import yaml

base = Path("工作记录与进度笔记本/observability_profiles")
run_dir = sorted(base.glob("*atlas800t-a2_observability_run"))[-1]
manifest = yaml.safe_load((run_dir / "manifest.yaml").read_text())
fields = yaml.safe_load((run_dir / "field_availability.yaml").read_text())
join_keys = yaml.safe_load((run_dir / "join_key_readiness.yaml").read_text())
p0 = yaml.safe_load((run_dir / "p0_acceptance_fields.yaml").read_text())

assert manifest["hardware_topology_hash"]
assert manifest["software_stack_hash"]
assert manifest["probe_script_version"]
assert "fields" in fields and len(fields["fields"]) >= 90
assert "join_key_readiness" in join_keys
assert "p0_acceptance_fields" in p0
print(run_dir)
PY
```

Expected: prints the run directory path.

- [ ] **Step 6: Review diff for scope**

Run:

```bash
git status --short
git diff --stat
```

Expected: changes are limited to `pyproject.toml`, `tools/observability_profile/`, `tests/observability_profile/`, `工作记录与进度笔记本/07_可观测能力体检执行说明.md`, and generated `工作记录与进度笔记本/observability_profiles/` run artifacts if the dry run was kept.

- [ ] **Step 7: Commit implementation**

If the dry-run artifacts are useful as the first local evidence run, include them. If they are from a non-Ascend development machine and should not be treated as server evidence, remove only the generated run directory before committing.

Commit command when keeping only code and docs:

```bash
git add pyproject.toml tools/observability_profile tests/observability_profile '工作记录与进度笔记本/07_可观测能力体检执行说明.md'
git commit -m "feat: add observability profile runner"
```

Commit command when also keeping the generated run:

```bash
git add pyproject.toml tools/observability_profile tests/observability_profile '工作记录与进度笔记本/07_可观测能力体检执行说明.md' '工作记录与进度笔记本/observability_profiles'
git commit -m "feat: add observability profile runner"
```

## Self-Review Checklist

- Spec coverage: tasks cover field catalog, probe runner, manifest, field availability, join-key readiness, P0 acceptance fields, Markdown summary, run directory generation, and P0 execution guide.
- Placeholder scan: no task depends on unspecified fields, unspecified files, or deferred validation.
- Type consistency: output filenames, availability statuses, blocked reason categories, profile names, join-key structures, and manifest hash fields are defined once and reused.
- Scope check: plan implements the observability capability profiling framework only. It does not implement performance optimization, runtime hooks, KV object hooks, MoE expert hooks, SSD cold tier optimization, or trace-driven simulator logic.
