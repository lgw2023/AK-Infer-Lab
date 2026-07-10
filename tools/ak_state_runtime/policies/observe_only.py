from __future__ import annotations

from ..models import PlacementDecision, StateEvent


class ObserveOnlyPolicy:
    name = "observe_only"
    version = "0.1.0"

    def decide(self, event: StateEvent) -> PlacementDecision | None:
        if event.object_id is None:
            return None

        observed_tier = event.target_tier
        if observed_tier in {None, "none", "unknown"}:
            observed_tier = "unknown"
        decision = PlacementDecision(
            schema_version="0.2.0",
            decision_id=f"decision:{event.source_event_id}",
            object_id=event.object_id,
            policy_name=self.name,
            policy_version=self.version,
            action="no_op",
            source_tier=observed_tier,
            target_tier=observed_tier,
            issued_ts_ns=event.timestamp_ns,
            deadline_ts_ns=None,
            expected_benefit_ms=None,
            expected_cost_ms=None,
            confidence=None,
            execution_mode="observe_only",
            executed=False,
            execution_result="skipped",
            reason="observe_only_does_not_move_payload",
        )
        return decision
