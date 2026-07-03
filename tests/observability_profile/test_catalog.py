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
