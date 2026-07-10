from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateEvent:
    schema_version: str
    event_id: str
    timestamp_ns: int
    trace_id: str
    request_id: str | None
    session_id: str | None
    object_id: str | None
    object_type: str | None
    model_id: str
    runtime: str
    rank_id: int | None
    layer_id: int | None
    phase: str
    event_type: str
    action: str
    source_tier: str | None
    target_tier: str | None
    bytes: int | None
    latency_ms: float | None
    source_event_id: str
    evidence_source: str
    artifact_path: str
    reason: str


@dataclass
class StateObject:
    schema_version: str
    object_id: str
    object_type: str
    model_id: str
    layer_id: int | None
    expert_id: int | None
    owner_request_id: str | None
    session_id: str | None
    scope: str
    payload_ref: str | None
    bytes: int | None
    precision: str | None
    layout: str | None
    checksum_or_version: str | None
    current_tier: str
    current_rank: int | None
    target_tier: str
    hotness_score: float | None
    reuse_distance: int | None
    next_use_estimate_ms: float | None
    load_cost_ms: float | None
    evict_cost_ms: float | None
    recompute_cost_ms: float | None
    prefetch_lead_time_ms: float | None
    hit_count: int
    miss_count: int
    last_access_ts_ns: int | None
    evidence_source: str
    quality_risk: str


@dataclass(frozen=True)
class PlacementDecision:
    schema_version: str
    decision_id: str
    object_id: str
    policy_name: str
    policy_version: str
    action: str
    source_tier: str
    target_tier: str
    issued_ts_ns: int
    deadline_ts_ns: int | None
    expected_benefit_ms: float | None
    expected_cost_ms: float | None
    confidence: float | None
    execution_mode: str
    executed: bool
    execution_result: str
    reason: str
