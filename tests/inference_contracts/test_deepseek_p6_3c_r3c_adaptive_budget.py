from __future__ import annotations

from types import SimpleNamespace

from tools.inference_contracts import (
    p6_3c_r3c_adaptive_scheduler as controller,
)
from tools.inference_contracts import (
    run_deepseek_p6_3c_r3c_adaptive_budget as runner,
)


def _scheduler(*, waiting: int) -> SimpleNamespace:
    residents = [
        SimpleNamespace(num_prompt_tokens=256, num_computed_tokens=256)
        for _ in range(8)
    ]
    return SimpleNamespace(
        max_num_scheduled_tokens=12288,
        scheduler_config=SimpleNamespace(max_num_batched_tokens=12288),
        running=residents,
        waiting=[None] * waiting,
        skipped_waiting=[],
    )


def test_r3c_schedule_has_fixed_policy_and_mirror_counts() -> None:
    assert [row["config_id"] for row in runner.CONFIGS] == [
        "off_b12288",
        "static_on_b8192",
        "adaptive_on_t2048",
        "adaptive_on_t4096",
        "adaptive_on_t8192",
    ]
    mechanism_lifecycles = len(runner.ON_CONFIG_IDS)
    performance_lifecycles = len(runner.CONFIGS) * 2
    assert mechanism_lifecycles == 4
    assert performance_lifecycles == 10
    assert 10 * mechanism_lifecycles + 103 * performance_lifecycles == 1070
    assert 3 * mechanism_lifecycles + 19 * performance_lifecycles == 202
    assert len(runner.ON_CONFIG_IDS) * 2 * 6 == 48


def test_pressure_controller_caps_only_when_decode_and_waiting_coexist(
    monkeypatch,
) -> None:
    monkeypatch.setenv("P6_3C_R3C_ACTIVE_CHUNK_TOKENS", "4096")
    monkeypatch.setenv("P6_3C_R3C_DECODE_QUANTUM_TOKENS", "2")
    pressure = controller._effective_budget(_scheduler(waiting=1))  # noqa: SLF001
    assert pressure["decode_resident_count"] == 8
    assert pressure["decode_reserve_tokens"] == 16
    assert pressure["selected_budget"] == 4112
    assert pressure["decision"] == "pressure_capped"

    no_pressure = controller._effective_budget(_scheduler(waiting=0))  # noqa: SLF001
    assert no_pressure["selected_budget"] == 12288
    assert no_pressure["decision"] == "full_budget"


def test_adaptive_policy_keeps_configured_budget_at_capacity_ceiling() -> None:
    adaptive = [row for row in runner.CONFIGS if row["policy_type"] == "adaptive_on"]
    assert {row["max_num_batched_tokens"] for row in adaptive} == {12288}
    assert [row["active_chunk_target_tokens"] for row in adaptive] == [2048, 4096, 8192]
