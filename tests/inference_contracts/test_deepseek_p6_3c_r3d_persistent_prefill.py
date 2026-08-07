from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.inference_contracts import (
    p6_3c_r3d_hybrid_kv_runtime_patch as runtime_patch,
)
from tools.inference_contracts import (
    p6_3c_r3d_persistent_scheduler as controller,
)
from tools.inference_contracts import (
    run_deepseek_p6_3c_r3d_persistent_prefill as runner,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _request(*, prompt: int, computed: int) -> SimpleNamespace:
    return SimpleNamespace(
        num_prompt_tokens=prompt,
        num_computed_tokens=computed,
    )


def _scheduler(
    *, waiting_prefill: bool = False, running_prefill: bool = False
) -> SimpleNamespace:
    running = [_request(prompt=256, computed=256) for _ in range(8)]
    if running_prefill:
        running.append(_request(prompt=12281, computed=512))
    waiting = [_request(prompt=12281, computed=0)] if waiting_prefill else []
    return SimpleNamespace(
        max_num_scheduled_tokens=12288,
        scheduler_config=SimpleNamespace(max_num_batched_tokens=12288),
        running=running,
        waiting=waiting,
        skipped_waiting=[],
    )


def test_r3d_policy_grid_is_capacity_matched() -> None:
    assert [row["config_id"] for row in runner.CONFIGS] == [
        "off_b12288",
        "admission_on_t4096",
        "persistent_on_t128",
        "persistent_on_t256",
        "persistent_on_t512",
        "persistent_on_t1024",
    ]
    assert {row["max_num_batched_tokens"] for row in runner.CONFIGS} == {12288}
    assert runner.PERSISTENT_TARGETS == (128, 256, 512, 1024)
    assert len(runner.ON_CONFIG_IDS) == 5


def test_r3d_publishes_server_proven_compatibility_before_npu_lifecycle() -> None:
    graph_patch = (
        REPO_ROOT
        / "benchmarks/deepseek_v4_flash/patches/"
        "vllm_ascend_v0221rc1_acl_graph_update_params_compat.patch"
    ).read_text(encoding="utf-8")
    server_task = (
        REPO_ROOT
        / "tools/inference_contracts/run_deepseek_p6_3c_r2_server_task.sh"
    ).read_text(encoding="utf-8")
    r3d_task = (
        REPO_ROOT
        / "tools/inference_contracts/run_deepseek_p6_3c_r3d_server_task.sh"
    ).read_text(encoding="utf-8")

    assert 'hasattr(impl_cls, "update_graph_params")' in graph_patch
    assert "P6_3C_ACL_GRAPH_COMPAT=1" in r3d_task
    assert "smoke_p6_3c_runtime_overlay.py" in server_task
    assert "runtime_overlay_preflight_smoke.json" in server_task
    assert server_task.index("runtime_overlay_preflight_smoke.json") < (
        server_task.index('bash "${BASE_SERVER_TASK}"')
    )


def test_r3d_aligns_stale_manager_aliases_to_ascend_exact_keys() -> None:
    class BaseMLAAttentionSpec:
        pass

    class BaseSlidingWindowMLASpec:
        pass

    class AscendMLAAttentionSpec:
        pass

    class AscendSlidingWindowMLASpec:
        pass

    class FullAttentionManager:
        pass

    class SlidingWindowManager:
        pass

    manager = SimpleNamespace(
        MLAAttentionSpec=BaseMLAAttentionSpec,
        SlidingWindowMLASpec=BaseSlidingWindowMLASpec,
        spec_manager_map={
            BaseMLAAttentionSpec: FullAttentionManager,
            BaseSlidingWindowMLASpec: SlidingWindowManager,
        },
    )
    interface = SimpleNamespace(
        AscendMLAAttentionSpec=AscendMLAAttentionSpec,
        AscendSlidingWindowMLASpec=AscendSlidingWindowMLASpec,
    )

    evidence = runtime_patch.align_ascend_manager_resolution(
        manager_module=manager,
        interface_module=interface,
    )

    assert manager.MLAAttentionSpec is AscendMLAAttentionSpec
    assert manager.SlidingWindowMLASpec is AscendSlidingWindowMLASpec
    assert manager.spec_manager_map[AscendMLAAttentionSpec] is FullAttentionManager
    assert (
        manager.spec_manager_map[AscendSlidingWindowMLASpec]
        is SlidingWindowManager
    )
    assert manager.spec_manager_map[BaseMLAAttentionSpec] is FullAttentionManager
    assert evidence["mapping_size"] == 4
    assert all(
        runtime_patch.require_ascend_manager_resolution(
            manager_module=manager,
            interface_module=interface,
        ).values()
    )


def test_persistent_scope_keeps_cap_after_prefill_moves_to_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P6_3C_R3D_PRESSURE_SCOPE", "persistent_prefill")
    monkeypatch.setenv("P6_3C_R3D_ACTIVE_CHUNK_TOKENS", "512")
    monkeypatch.setenv("P6_3C_R3D_DECODE_QUANTUM_TOKENS", "2")

    decision = controller._effective_budget(  # noqa: SLF001
        _scheduler(running_prefill=True)
    )
    assert decision["decode_resident_count"] == 8
    assert decision["waiting_prefill_count"] == 0
    assert decision["running_unfinished_prefill_count"] == 1
    assert decision["active_prefill_count"] == 1
    assert decision["selected_budget"] == 528
    assert decision["decision"] == "pressure_capped"


def test_admission_only_anchor_reverts_when_waiting_becomes_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P6_3C_R3D_PRESSURE_SCOPE", "admission_only")
    monkeypatch.setenv("P6_3C_R3D_ACTIVE_CHUNK_TOKENS", "4096")
    monkeypatch.setenv("P6_3C_R3D_DECODE_QUANTUM_TOKENS", "2")

    first = controller._effective_budget(_scheduler(waiting_prefill=True))  # noqa: SLF001
    later = controller._effective_budget(_scheduler(running_prefill=True))  # noqa: SLF001
    assert first["selected_budget"] == 4112
    assert first["decision"] == "pressure_capped"
    assert later["running_unfinished_prefill_count"] == 1
    assert later["active_prefill_count"] == 0
    assert later["selected_budget"] == 12288
    assert later["decision"] == "full_budget"


def test_no_decode_resident_uses_full_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P6_3C_R3D_PRESSURE_SCOPE", "persistent_prefill")
    scheduler = _scheduler(waiting_prefill=True)
    scheduler.running = []
    decision = controller._effective_budget(scheduler)  # noqa: SLF001
    assert decision["decode_resident_count"] == 0
    assert decision["selected_budget"] == 12288
    assert decision["decision"] == "full_budget"


def test_invalid_pressure_scope_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P6_3C_R3D_PRESSURE_SCOPE", "stale_policy")
    with pytest.raises(ValueError, match="admission_only or persistent_prefill"):
        controller._effective_budget(_scheduler(waiting_prefill=True))  # noqa: SLF001
