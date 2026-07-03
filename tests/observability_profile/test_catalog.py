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
