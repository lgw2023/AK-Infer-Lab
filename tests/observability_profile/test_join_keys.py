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


def test_p0_acceptance_prefers_actual_evidence_artifact():
    fields = build_field_catalog()
    fields[0]["required_for_p0"] = True
    fields[0]["expected_artifact"] = "expected_template.yaml"
    fields[0]["availability"]["status"] = "measurable"
    fields[0]["availability"]["evidence_artifact"] = "manifest.yaml"

    result = build_p0_acceptance_fields(fields)

    assert result["p0_acceptance_fields"][0]["source"] == "manifest.yaml"
