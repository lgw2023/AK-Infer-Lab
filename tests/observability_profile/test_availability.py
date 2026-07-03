from tools.observability_profile.availability import (
    apply_manifest_evidence,
    apply_microbench_evidence,
    apply_probe_evidence,
    summarize_availability,
)
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


def test_apply_probe_evidence_marks_limited_mapped_fields_partial():
    fields = build_field_catalog()
    probes = [
        {
            "tool": "npu_smi_probe",
            "available": True,
            "permission_status": "limited",
            "artifact_path": "probe_results/npu_smi_probe.md",
            "maps_to_fields": ["npu_hbm_profile.hbm_free_bytes"],
            "blocked_reason": {"category": None, "detail": None},
        }
    ]
    updated = apply_probe_evidence(fields, probes, checked_at="2026-07-03T00:00:00Z")
    by_key = {f"{field['profile']}.{field['name']}": field for field in updated}
    availability = by_key["npu_hbm_profile.hbm_free_bytes"]["availability"]
    assert availability["status"] == "partial"
    assert availability["partial_reason"] == "tool reports limited permission"


def test_blocked_probe_copies_blocked_reason_per_mapped_field():
    fields = build_field_catalog()
    blocked_reason = {"category": "permission", "detail": "missing device access"}
    probes = [
        {
            "tool": "npu_smi_probe",
            "available": False,
            "permission_status": "blocked",
            "artifact_path": "probe_results/npu_smi_probe.md",
            "maps_to_fields": [
                "npu_hbm_profile.hbm_allocated_bytes",
                "npu_hbm_profile.hbm_free_bytes",
            ],
            "blocked_reason": blocked_reason,
        }
    ]

    updated = apply_probe_evidence(fields, probes, checked_at="2026-07-03T00:00:00Z")
    by_key = {f"{field['profile']}.{field['name']}": field for field in updated}
    first_reason = by_key["npu_hbm_profile.hbm_allocated_bytes"]["availability"]["blocked_reason"]
    second_reason = by_key["npu_hbm_profile.hbm_free_bytes"]["availability"]["blocked_reason"]

    assert first_reason == blocked_reason
    assert second_reason == blocked_reason
    assert first_reason is not second_reason
    assert first_reason is not blocked_reason

    first_reason["detail"] = "mutated"
    assert second_reason["detail"] == "missing device access"
    assert blocked_reason["detail"] == "missing device access"


def test_blocked_probe_clears_stale_partial_reason():
    fields = build_field_catalog()
    partial_update = apply_probe_evidence(
        fields,
        [
            {
                "tool": "npu_smi_probe",
                "available": True,
                "permission_status": "limited",
                "artifact_path": "probe_results/npu_smi_probe.md",
                "maps_to_fields": ["npu_hbm_profile.hbm_free_bytes"],
                "blocked_reason": {"category": None, "detail": None},
            }
        ],
        checked_at="2026-07-03T00:00:00Z",
    )

    blocked_update = apply_probe_evidence(
        partial_update,
        [
            {
                "tool": "npu_smi_probe",
                "available": False,
                "permission_status": "blocked",
                "artifact_path": "probe_results/npu_smi_probe.md",
                "maps_to_fields": ["npu_hbm_profile.hbm_free_bytes"],
                "blocked_reason": {"category": "permission", "detail": "missing device access"},
            }
        ],
        checked_at="2026-07-03T00:01:00Z",
    )
    by_key = {f"{field['profile']}.{field['name']}": field for field in blocked_update}
    availability = by_key["npu_hbm_profile.hbm_free_bytes"]["availability"]

    assert availability["status"] == "blocked"
    assert availability["partial_reason"] is None


def test_summarize_availability_counts_statuses():
    fields = build_field_catalog()
    summary = summarize_availability(fields)
    assert "request_runtime_profile" in summary
    assert summary["request_runtime_profile"]["unknown"] > 0


def test_apply_probe_evidence_ignores_probes_without_mapped_fields():
    fields = build_field_catalog()
    probes = [
        {
            "tool": "context_only_probe",
            "available": True,
            "permission_status": "ok",
            "artifact_path": "probe_results/context_only_probe.md",
            "maps_to_fields": [],
            "blocked_reason": {"category": None, "detail": None},
        }
    ]

    updated = apply_probe_evidence(fields, probes, checked_at="2026-07-03T00:00:00Z")

    assert updated == fields


def test_apply_manifest_evidence_marks_known_manifest_fields_measurable():
    fields = build_field_catalog()
    manifest = {
        "os_name": "Linux",
        "kernel_version": "5.10.0",
        "cann_version": "9.0.0",
        "container_privileged": False,
        "torch_npu_version": "2.6.0",
        "mindie_version": "unknown",
    }

    updated = apply_manifest_evidence(fields, manifest, checked_at="2026-07-03T00:00:00Z")
    by_key = {f"{field['profile']}.{field['name']}": field for field in updated}

    os_availability = by_key["server_observability_profile.os_name"]["availability"]
    privileged_availability = by_key["server_observability_profile.container_privileged"]["availability"]
    mindie_availability = by_key["server_observability_profile.mindie_version"]["availability"]

    assert os_availability["status"] == "measurable"
    assert os_availability["evidence_probe"] == "manifest"
    assert os_availability["evidence_artifact"] == "manifest.yaml"
    assert privileged_availability["status"] == "measurable"
    assert mindie_availability["status"] == "unknown"


def test_apply_manifest_evidence_rejects_timeout_version_text():
    fields = build_field_catalog()
    manifest = {
        "torch_npu_version": "TimeoutExpired: Command '['python', '-c', 'import torch_npu']' timed out after 5 seconds",
    }

    updated = apply_manifest_evidence(fields, manifest, checked_at="2026-07-03T00:00:00Z")
    by_key = {f"{field['profile']}.{field['name']}": field for field in updated}

    availability = by_key["server_observability_profile.torch_npu_version"]["availability"]
    assert availability["status"] == "unknown"


def test_apply_microbench_evidence_maps_only_related_fields():
    fields = build_field_catalog()
    results = [
        {
            "bench_name": "ssd_fio",
            "status": "blocked",
            "artifact_path": "microbench/ssd_fio.csv",
            "blocked_reason": {"category": "scratch_missing", "detail": "--scratch-dir is required"},
        },
        {
            "bench_name": "npu_copy_h2d",
            "status": "blocked",
            "artifact_path": "microbench/npu_copy_h2d.csv",
            "blocked_reason": {"category": "tool_missing", "detail": "torch-npu is not installed"},
        },
    ]

    updated = apply_microbench_evidence(fields, results, checked_at="2026-07-03T00:00:00Z")
    by_key = {f"{field['profile']}.{field['name']}": field for field in updated}

    ssd_iops = by_key["microbench_profile.ssd_iops"]["availability"]
    h2d_latency = by_key["microbench_profile.h2d_latency_us"]["availability"]
    d2h_latency = by_key["microbench_profile.d2h_latency_us"]["availability"]

    assert ssd_iops["status"] == "blocked"
    assert ssd_iops["blocked_reason"]["category"] == "scratch_missing"
    assert h2d_latency["status"] == "blocked"
    assert h2d_latency["blocked_reason"]["category"] == "tool_missing"
    assert d2h_latency["status"] == "unknown"
