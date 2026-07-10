# P5-P9 and P8 Layered Prototype Documentation Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align every current P5-P9 planning surface with the active P5 eight-card smoke and define P8 as an evidence-gated layered engineering prototype.

**Architecture:** Keep one stable P5-P9 experiment plan, one DeepSeek-specific plan, and one dedicated P8 engineering plan; make the notebook pages short current-state projections of those stable documents. P8 uses vLLM-Ascend as the currently available primary runtime, treats MindIE as a separately gated comparison runtime, and keeps runtime adapters, state metadata, policy, execution, and simulator responsibilities separate.

**Tech Stack:** Markdown, YAML planning artifacts, vLLM-Ascend 0.18.0 current server evidence, official vLLM-Ascend and MindIE documentation, existing `tests/inference_contracts` validation.

## Global Constraints

- Preserve all pre-existing uncommitted user changes; patch only lines required by this task.
- Do not change `通信模块/docs/developer-to-server.md`; P5 is already the active server handoff.
- Do not create P8 runtime code or server tasks in this round.
- Treat latest framework documentation as capability candidates, not proof that server vLLM-Ascend 0.18.0 exposes the same feature set.
- Treat MindIE as unavailable on the current server until a separate runtime-availability gate is closed.
- Keep SSD/NVMe out of the per-token decode critical path in P8 V0/V1.
- Separate smoke, controlled benchmark, profiled evidence, simulation, and hardware recommendation claim levels.

---

### Task 1: Freeze the current stage graph

**Files:**
- Modify: `docs/EXPERIMENT_PLAN.md`
- Modify: `docs/PROJECT_CHARTER.md`

**Interfaces:**
- Consumes: active P5 card and `通信模块/docs/developer-to-server.md` status.
- Produces: the canonical P5 → P6/P7 → P8 → P9 dependency graph and stage gates.

- [x] **Step 1: Replace readiness-only P5 wording with the active eight-card 128K smoke contract.**
- [x] **Step 2: Define explicit green/yellow/red transitions into P6.**
- [x] **Step 3: Separate P6 unprofiled performance, profiled attribution evidence, and one-variable A/B runs.**
- [x] **Step 4: Define P7 as a calibration/boundary stage rather than a full-model deployment promise.**
- [x] **Step 5: Run the stale-current-wording scan.**

Run:

```bash
rg -n "P5.*不下发|P5.*只做.*readiness|服务器路径占位|P0-P6" docs/EXPERIMENT_PLAN.md docs/PROJECT_CHARTER.md
```

Expected: no current-tense stale P5/P0-P6 planning statement.

### Task 2: Write the P8 layered engineering prototype plan

**Files:**
- Create: `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`

**Interfaces:**
- Consumes: `docs/TECHNICAL_ARCHITECTURE.md`, `docs/METRICS_AND_TRACE_SCHEMA.md`, P6/P7 evidence contracts, official runtime capability references.
- Produces: runtime-adapter boundaries, StateObject metadata contract, P8.0-P8.6 vertical slices, acceptance gates, planned file map, and P9 handoff contract.

- [x] **Step 1: Record current runtime truth and capability-probe requirements.**
- [x] **Step 2: Define StateObject metadata separately from payload movement and trace events.**
- [x] **Step 3: Define KV/Prefix real-path progression: baseline → CPU offload → UCM/External KV → cold persistence.**
- [x] **Step 4: Define MoE progression: trace → hotness → EPLB/static placement → simulated tiers → gated warm prefetch.**
- [x] **Step 5: Define observe-only, simulate-only, static-placement, and real-move execution modes.**
- [x] **Step 6: Add artifact, metrics, failure, and claim-boundary acceptance criteria.**

Run:

```bash
rg -n "P8\.[0-6]|StateObject|observe_only|simulate_only|static_placement|real_move|MindIE|EPLB|UCM|P9" docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md
```

Expected: every P8 vertical slice and runtime mode is present.

### Task 3: Align the DeepSeek and repository-facing plans

**Files:**
- Modify: `docs/DEEPSEEK_V4_FLASH_ASCEND_PLAN.md`
- Modify: `docs/README.md`
- Modify: `README.md`
- Modify: `benchmarks/deepseek_v4_flash/README.md`

**Interfaces:**
- Consumes: canonical experiment plan and detailed P8 plan.
- Produces: consistent entry points without duplicating the full P8 design.

- [x] **Step 1: Update real server paths and current P5 status.**
- [x] **Step 2: Link P8 details instead of restating incompatible mini-plans.**
- [x] **Step 3: Update documentation indexes and minimum-start path.**
- [x] **Step 4: Preserve the existing terminology/source-boundary edits in dirty files.**

Run:

```bash
git diff -- README.md docs/PROJECT_CHARTER.md
```

Expected: existing terminology edits remain, with only targeted planning additions.

### Task 4: Refresh the progress notebook at both ends of the round

**Files:**
- Modify: `工作记录与进度笔记本/01_工作记录.md`
- Modify: `工作记录与进度笔记本/05_下一步行动指导.md`
- Modify: `工作记录与进度笔记本/09_DeepSeek_V4_Flash_专项计划.md`
- Modify: `工作记录与进度笔记本/12_P5_P9_后续阶段重排计划.md`

**Interfaces:**
- Consumes: stable docs and current P5 handoff.
- Produces: a concise current-status view, immediate next actions, and an auditable start/end record.

- [x] **Step 1: Add the round-start record before document edits.**
- [x] **Step 2: Rewrite the P5-P9 notebook plan around the canonical stage graph.**
- [x] **Step 3: Refresh the DeepSeek plan and top next-action section.**
- [x] **Step 4: Add the round-end record with exact files and verification results.**

### Task 5: Verify consistency and scope

**Files:**
- Verify all files from Tasks 1-4.

**Interfaces:**
- Consumes: completed documentation set.
- Produces: evidence that current planning surfaces agree and no active server task was changed.

- [x] **Step 1: Verify Markdown whitespace and patch integrity.**

Run:

```bash
git diff --check
```

Expected: exit code 0.

- [x] **Step 2: Verify the active server handoff has no diff.**

Run:

```bash
git diff --exit-code -- 通信模块/docs/developer-to-server.md
```

Expected: exit code 0.

- [x] **Step 3: Run the existing inference-contract suite.**

Run:

```bash
python -m pytest tests/inference_contracts -q
```

Expected: all tests pass.

- [x] **Step 4: Search current planning surfaces for contradictory stage statements.**

Run:

```bash
rg -n "P5.*不下发|P5.*只做.*readiness|P5.*服务器路径占位|P0-P6" README.md docs/EXPERIMENT_PLAN.md docs/DEEPSEEK_V4_FLASH_ASCEND_PLAN.md 工作记录与进度笔记本/09_DeepSeek_V4_Flash_专项计划.md 工作记录与进度笔记本/12_P5_P9_后续阶段重排计划.md
```

Expected: no current-tense contradiction; any historical wording is explicitly labeled as superseded history.
