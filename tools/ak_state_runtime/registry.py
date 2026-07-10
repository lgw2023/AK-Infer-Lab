from __future__ import annotations

from dataclasses import replace

from .models import StateEvent, StateObject


OBJECT_SCOPES = {
    "kv_block": "request",
    "prefix_block": "session",
    "expert_weight": "model",
    "weight_shard": "model",
    "session": "session",
}


class StateRegistry:
    """Metadata-only object registry; it never owns runtime payloads."""

    def __init__(self) -> None:
        self._objects: dict[str, StateObject] = {}

    def apply(self, event: StateEvent) -> None:
        if event.object_id is None or event.object_type is None:
            return

        state_object = self._objects.get(event.object_id)
        if state_object is None:
            state_object = self._new_object(event)
            self._objects[event.object_id] = state_object
        else:
            self._update_object(state_object, event)

    def snapshot(self) -> tuple[StateObject, ...]:
        return tuple(replace(self._objects[key]) for key in sorted(self._objects))

    @staticmethod
    def _new_object(event: StateEvent) -> StateObject:
        hit_count = 1 if event.action == "hit" else 0
        miss_count = 1 if event.action == "miss" else 0
        return StateObject(
            schema_version="0.2.0",
            object_id=event.object_id or "",
            object_type=event.object_type or "",
            model_id=event.model_id,
            layer_id=event.layer_id,
            expert_id=None,
            owner_request_id=event.request_id,
            session_id=event.session_id,
            scope=OBJECT_SCOPES[event.object_type or ""],
            payload_ref=None,
            bytes=event.bytes,
            precision=None,
            layout=None,
            checksum_or_version=None,
            current_tier=_observed_tier(event),
            current_rank=event.rank_id,
            target_tier="none",
            hotness_score=None,
            reuse_distance=None,
            next_use_estimate_ms=None,
            load_cost_ms=None,
            evict_cost_ms=None,
            recompute_cost_ms=None,
            prefetch_lead_time_ms=None,
            hit_count=hit_count,
            miss_count=miss_count,
            last_access_ts_ns=event.timestamp_ns,
            evidence_source=event.evidence_source,
            quality_risk="high" if event.evidence_source == "offline_fixture" else "medium",
        )

    @staticmethod
    def _update_object(state_object: StateObject, event: StateEvent) -> None:
        if event.bytes is not None and state_object.bytes is None:
            state_object.bytes = event.bytes
        observed_tier = _observed_tier(event)
        if observed_tier != "unknown":
            state_object.current_tier = observed_tier
        if event.rank_id is not None:
            state_object.current_rank = event.rank_id
        if state_object.layer_id is None and event.layer_id is not None:
            state_object.layer_id = event.layer_id
        if event.action == "hit":
            state_object.hit_count += 1
        if event.action == "miss":
            state_object.miss_count += 1
        state_object.last_access_ts_ns = event.timestamp_ns


def _observed_tier(event: StateEvent) -> str:
    if event.target_tier not in {None, "none", "unknown"}:
        return event.target_tier
    return "unknown"
