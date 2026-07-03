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
