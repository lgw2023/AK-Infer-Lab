# vLLM 0.20.2 Development Baseline Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the obsolete vLLM-Ascend 0.18.0 snapshot and make the rolling vLLM/vLLM-Ascend checkouts contain the exact 0.20.2 development-base tags while staying on current upstream `main`.

**Architecture:** Keep one shallow rolling checkout for each of vLLM and vLLM-Ascend instead of parallel version directories. Fetch the exact release tags into those repositories without switching their working trees away from `main`; future first-party development will branch from the tag commits outside `reference_repos/`. Record the complete compatible runtime stack as a target baseline, not as locally or server-verified installation evidence.

**Tech Stack:** Git shallow fetch, Markdown, pytest.

## Global Constraints

- Development baseline: `vLLM 0.20.2`, `vLLM-Ascend 0.20.2rc1`, `CANN 9.0.0`, `PyTorch 2.10.0`, `torch-npu 2.10.0`, `triton-ascend 3.2.1`.
- Remove `reference_repos/vllm-ascend-v0.18.0/`; do not create a replacement version-directory snapshot.
- Keep `reference_repos/vllm/` and `reference_repos/vllm-ascend/` on clean upstream `main`.
- Fetch exact tag `v0.20.2` at `bc150f50299199599673614f80d12a196f377655` into `vllm/`.
- Fetch exact tag `v0.20.2rc1` at `367b8e62da799870a7476ce34f5f7658589a8aad` into `vllm-ascend/`.
- Do not clone PyTorch, CANN, torch-npu, or triton-ascend source repositories in this correction.
- Preserve concurrent P5 RED/upgrade-waiting changes and do not edit `通信模块/docs/developer-to-server.md`.
- Do not commit or push unless requested separately.

---

### Task 1: Verify and record the corrected scope

**Files:**
- Modify: `工作记录与进度笔记本/01_工作记录.md`

**Interfaces:**
- Consumes: current checkout cleanliness, official tag refs, and the user-specified runtime stack.
- Produces: a notebook start entry and a safety gate for deleting the old ignored directory.

- [x] **Step 1: Verify the rolling checkouts and obsolete snapshot are clean.**

```bash
for repo_dir in reference_repos/vllm reference_repos/vllm-ascend reference_repos/vllm-ascend-v0.18.0; do
  test -z "$(git -C "$repo_dir" status --porcelain=v1)"
done
```

Expected: all three outputs are empty.

- [x] **Step 2: Verify official target tags and exact commits.**

```bash
git -C reference_repos/vllm ls-remote --tags origin refs/tags/v0.20.2
git -C reference_repos/vllm-ascend ls-remote --tags origin refs/tags/v0.20.2rc1
```

Expected: `bc150f50299199599673614f80d12a196f377655` and `367b8e62da799870a7476ce34f5f7658589a8aad`.

- [x] **Step 3: Append the correction-start entry to the work notebook.**

Record the six-package target stack, removal of the 0.18.0 directory, tag-in-main-checkout policy, and no server-handoff mutation.

### Task 2: Align source references without duplicate snapshots

**Files:**
- Delete locally ignored: `reference_repos/vllm-ascend-v0.18.0/`
- Update locally ignored Git refs: `reference_repos/vllm/.git/`
- Update locally ignored Git refs: `reference_repos/vllm-ascend/.git/`

**Interfaces:**
- Consumes: clean source directories and verified tag SHAs.
- Produces: two latest-main worktrees with exact development-base tag objects available locally.

- [x] **Step 1: Remove the clean obsolete snapshot directory.**

```bash
rm -rf -- reference_repos/vllm-ascend-v0.18.0
```

Expected: the path no longer exists and no other `reference_repos/` path is removed.

- [x] **Step 2: Fast-forward both rolling main branches.**

```bash
git -C reference_repos/vllm pull --ff-only --quiet
git -C reference_repos/vllm-ascend pull --ff-only --quiet
```

Expected: both remain clean on `main` and equal `origin/main`.

- [x] **Step 3: Fetch the two exact development-base tags shallowly.**

```bash
git -C reference_repos/vllm fetch --depth 1 origin tag v0.20.2
git -C reference_repos/vllm-ascend fetch --depth 1 origin tag v0.20.2rc1
```

Expected: each tag resolves to its exact SHA while the checked-out branch remains `main`.

### Task 3: Update current documentation and inventory

**Files:**
- Modify: `reference_repos/README.md`
- Modify: `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`
- Modify: `docs/SOURCES_AND_BOUNDARIES.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-10-p8-reference-repository-refresh.md`
- Modify: `工作记录与进度笔记本/01_工作记录.md`

**Interfaces:**
- Consumes: final main SHAs, target tag SHAs, and the six-package target stack.
- Produces: one current development-baseline statement with historical 0.18.0 evidence preserved only where it describes the failed first run.

- [x] **Step 1: Remove the obsolete snapshot from the inventory and correct counts.**

Expected: `24 shallow Git checkouts plus 1 source snapshot`; no current inventory row for `vllm-ascend-v0.18.0/`.

- [x] **Step 2: Record rolling-main versus development-base-tag roles.**

Expected: `vllm/` and `vllm-ascend/` stay latest-main references; `v0.20.2` and `v0.20.2rc1` are locally fetched branch points, not extra directories.

- [x] **Step 3: Record the complete target stack and evidence boundary.**

Expected: all six versions appear; the stack is labeled target/upgrade-in-progress until server feedback confirms it.

- [x] **Step 4: Mark the previous reference-refresh plan as corrected.**

Expected: the previous plan retains historical execution detail but clearly states that its 0.18.0 snapshot deliverable was removed by this correction.

- [x] **Step 5: Append the correction-completion entry to the work notebook.**

Record directory removal, tag SHAs, rolling-main status, documentation scope, and validation results.

### Task 4: Verify source, documentation, and project boundaries

**Files:**
- Verify: `reference_repos/README.md`
- Verify: `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`
- Verify: `docs/SOURCES_AND_BOUNDARIES.md`
- Verify: `README.md`

**Interfaces:**
- Consumes: Tasks 1-3 outputs.
- Produces: completion evidence without claiming the target runtime is already installed or server-validated.

- [x] **Step 1: Verify directory and Git-ref state.**

Expected: obsolete path absent; both working trees clean on remote-matched `main`; both exact tags present at expected SHAs.

- [x] **Step 2: Scan current documentation for stale snapshot claims.**

Expected: `vllm-ascend-v0.18.0/` appears only in the correction history, not as a current deliverable; historical v0.18.0 server evidence remains unchanged.

- [x] **Step 3: Run project regression checks.**

```bash
python -m pytest tests/inference_contracts -q
git diff --check
```

Expected: all inference-contract tests pass and no whitespace errors are reported.
