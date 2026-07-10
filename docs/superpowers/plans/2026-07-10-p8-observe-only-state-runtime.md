# P8 Observe-only State Runtime Implementation Plan

> **For agentic workers:** Implement task-by-task with a strict RED → GREEN →
> regression cycle. Do not modify the active server handoff.

**Goal:** Build the first P8 offline, observe-only vertical slice that converts
the existing P1 trace fixture into deterministic StateObject, StateEvent,
PlacementDecision, and TraceBundle artifacts.

**Architecture:** A dependency-free core owns contracts, metadata state,
observe-only decisions, replay, and bundle serialization. Runtime-specific
knowledge lives only in adapters; the first adapter reads the legacy P1 fixture.
The CLI is the composition root and no core module imports vLLM, torch, CANN, or
`reference_repos`.

**Tech Stack:** Python 3.11+, dataclasses, typing.Protocol, JSONL, YAML, pytest.

## Global Constraints

- Preserve `工作记录与进度笔记本/p1_inference_contracts/` as a read-only input contract.
- Do not import vLLM, vLLM-Ascend, torch, torch-npu, CANN, or `reference_repos`.
- Do not change `通信模块/docs/developer-to-server.md`.
- Do not emit server or performance claims from the offline fixture.
- Unknown bytes/tier/type values remain explicit; never infer them from whole-device metrics.
- Every implementation task starts with a failing focused test.

---

### Task 1: Schema contracts and core models

**Files:**
- Create: `tools/ak_state_runtime/__init__.py`
- Create: `tools/ak_state_runtime/models.py`
- Create: `tools/ak_state_runtime/schema/ak_state_object.schema.yaml`
- Create: `tools/ak_state_runtime/schema/ak_state_event.schema.yaml`
- Create: `tools/ak_state_runtime/schema/placement_decision.schema.yaml`
- Create: `tools/ak_state_runtime/validation.py`
- Test: `tests/ak_state_runtime/test_schema_validation.py`

**Interfaces:** `StateObject`, `StateEvent`, `PlacementDecision`,
`ValidationError`, `load_contracts()`, and `validate_record()`.

- [x] Write tests proving the three schemas expose version `0.2.0`, required
  fields, and allowed enum members from the approved design.
- [x] Run `python -m pytest tests/ak_state_runtime/test_schema_validation.py -q`
  and confirm failure because the package does not exist.
- [x] Implement frozen event/decision dataclasses, mutable StateObject, schema
  loading, required-field checks, enum checks, and nullable handling.
- [x] Re-run the focused test and confirm pass.

### Task 2: P1 anti-corruption adapter

**Files:**
- Create: `tools/ak_state_runtime/adapters/__init__.py`
- Create: `tools/ak_state_runtime/adapters/base.py`
- Create: `tools/ak_state_runtime/adapters/p1_fixture.py`
- Create: `tests/ak_state_runtime/fixtures/duplicate_event_id.jsonl`
- Create: `tests/ak_state_runtime/fixtures/missing_trace_id.jsonl`
- Test: `tests/ak_state_runtime/test_p1_fixture_adapter.py`

**Interfaces:** `RuntimeEventAdapter`, `AdaptedTrace`, `AdapterError`, and
`P1FixtureAdapter(model_id, runtime_label).read(path)`.

- [x] Write tests for the existing eight-record fixture, exact event-type
  counts, KV/Prefix mapping, byte ambiguity, duplicate IDs, and missing trace ID.
- [x] Run the focused test and confirm failure because the adapter is absent.
- [x] Implement line-aware JSONL parsing and explicit mapping rules; warnings and
  skipped records must be data, not log-only side effects.
- [x] Re-run the focused test and confirm pass.

### Task 3: Registry and observe-only policy

**Files:**
- Create: `tools/ak_state_runtime/registry.py`
- Create: `tools/ak_state_runtime/policies/__init__.py`
- Create: `tools/ak_state_runtime/policies/observe_only.py`
- Test: `tests/ak_state_runtime/test_registry.py`
- Test: `tests/ak_state_runtime/test_observe_only_policy.py`

**Interfaces:** `StateRegistry.apply()`, `StateRegistry.snapshot()`, and
`ObserveOnlyPolicy.decide()`.

- [x] Write registry tests for two final objects, tiers, hit/miss counts, and
  unambiguous byte values from the approved fixture.
- [x] Write policy tests proving request-only events receive no decision and all
  object events receive deterministic, unexecuted `no_op` decisions.
- [x] Run both focused tests and confirm failure.
- [x] Implement minimal metadata-only registry and policy behavior.
- [x] Re-run both focused tests and confirm pass.

### Task 4: Deterministic replay and bundle writer

**Files:**
- Create: `tools/ak_state_runtime/replay.py`
- Create: `tools/ak_state_runtime/bundle.py`
- Test: `tests/ak_state_runtime/test_replay_bundle.py`

**Interfaces:** `ReplayResult`, `replay()`, `validate_replay_result()`, and
`write_bundle()`.

- [x] Write tests for stable ordering, unique IDs, object/decision joins,
  deterministic JSONL bytes, SHA-256 manifest fields, and refusal to publish an
  invalid bundle.
- [x] Run the focused test and confirm failure.
- [x] Implement replay and bundle serialization without importing a concrete
  adapter.
- [x] Re-run the focused test and confirm pass.

### Task 5: CLI and generated exemplar

**Files:**
- Create: `tools/ak_state_runtime/cli.py`
- Create: `benchmarks/deepseek_v4_flash/p8/offline_tracer_bullet/manifest.yaml`
- Create: `benchmarks/deepseek_v4_flash/p8/offline_tracer_bullet/state_objects.jsonl`
- Create: `benchmarks/deepseek_v4_flash/p8/offline_tracer_bullet/state_events.jsonl`
- Create: `benchmarks/deepseek_v4_flash/p8/offline_tracer_bullet/placement_decisions.jsonl`
- Create: `benchmarks/deepseek_v4_flash/p8/offline_tracer_bullet/validation_report.json`
- Test: extend `tests/ak_state_runtime/test_replay_bundle.py`

**Interfaces:** `python -m tools.ak_state_runtime.cli build-offline-bundle ...`.

- [x] Write a subprocess test proving the CLI produces a valid bundle and that a
  second build is byte-identical.
- [x] Run the focused test and confirm failure.
- [x] Implement the composition-root CLI with explicit model/runtime labels and
  `server_validated=false`, `claim_level=toolchain_only`.
- [x] Generate the committed exemplar from the existing P1 fixture.
- [x] Re-run the focused test and confirm pass.

### Task 6: Independence, regression, and progress closeout

**Files:**
- Create: `tests/ak_state_runtime/test_module_independence.py`
- Modify: `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`
- Modify: `工作记录与进度笔记本/01_工作记录.md`

- [x] Test the core import graph and source tree for forbidden runtime/reference
  imports; verify the active server handoff hash is unchanged.
- [x] Run `python -m pytest tests/ak_state_runtime -q`.
- [x] Run `python -m pytest tests/inference_contracts -q`.
- [x] Run `python -m pytest -q`.
- [x] Run `python -m compileall -q tools/ak_state_runtime` and `git diff --check`.
- [x] Record exact evidence and next adapter gate in the P8 plan and notebook.
