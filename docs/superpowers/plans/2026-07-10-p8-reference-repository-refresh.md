# P8 Reference Repository Refresh Implementation Plan

> **Post-completion correction (2026-07-10):** The temporary
> `reference_repos/vllm-ascend-v0.18.0/` deliverable documented below was
> removed at the user's request. The current policy keeps only rolling
> `vllm/` and `vllm-ascend/` checkouts and fetches `v0.20.2@bc150f5` and
> `v0.20.2rc1@367b8e6` into them. See
> `2026-07-10-vllm-0202-development-baseline-refresh.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh every third-party repository under `reference_repos/`, add the missing P8 UCM and pinned vLLM-Ascend 0.18.0 references, and keep all third-party source trees out of the AK-Infer-Lab Git index.

**Architecture:** Existing clean shallow clones are fast-forwarded on their configured upstream branches without submodules. The non-Git ServeGen snapshot is refreshed from the official GitHub default-branch archive, while UCM and the runtime-matched vLLM-Ascend tag are added as separate shallow references. Only `.gitignore`, `reference_repos/README.md`, this plan, and the current progress notebook are tracked by the main project.

**Tech Stack:** Git, GitHub HTTPS endpoints, Markdown, shell validation.

## Global Constraints

- Preserve all pre-existing local changes; stop rather than overwrite a dirty third-party checkout.
- Keep clones shallow and do not initialize submodules.
- Keep `reference_repos/**` ignored; only `reference_repos/README.md` remains tracked.
- Treat `vllm-ascend/` as latest-main code-reading evidence and `vllm-ascend-v0.18.0/` as the server-runtime-matched immutable source snapshot.
- Do not change `通信模块/docs/developer-to-server.md` or create a new server task.
- Do not commit or push unless the user requests it separately.

---

### Task 1: Record preflight and start status

**Files:**
- Modify: `工作记录与进度笔记本/01_工作记录.md`

**Interfaces:**
- Consumes: clean/dirty state, branch, upstream, origin, shallow/sparse mode for every existing checkout.
- Produces: an auditable start entry and a hard safety gate before network mutation.

- [x] **Step 1: Verify all existing Git references are clean and have an upstream.**

Run:

```bash
for repo_dir in reference_repos/*; do
  [ -d "$repo_dir/.git" ] || continue
  test -z "$(git -C "$repo_dir" status --porcelain=v1)"
  git -C "$repo_dir" rev-parse --abbrev-ref '@{upstream}'
done
```

Expected: every command exits zero and no dirty path is printed.

- [x] **Step 2: Append the refresh-start entry to the work notebook.**

Record the exact scope: all existing references, ServeGen archive, UCM, pinned vLLM-Ascend 0.18.0, `.gitignore`, and no server handoff change.

### Task 2: Fast-forward every existing Git checkout

**Files:**
- Modify locally but keep ignored: `reference_repos/*/`

**Interfaces:**
- Consumes: the clean upstream-tracking checkouts from Task 1.
- Produces: each checkout at the current tip of its configured upstream branch.

- [x] **Step 1: Pull each checkout with fast-forward-only semantics.**

Run per repository:

```bash
for repo_dir in reference_repos/*; do
  [ -d "$repo_dir/.git" ] || continue
  git -C "$repo_dir" pull --ff-only
done
```

Expected: `Already up to date.` or a successful fast-forward; no merge commit and no local modification.

- [x] **Step 2: Capture each resulting full commit and commit date.**

Run:

```bash
for repo_dir in reference_repos/*; do
  [ -d "$repo_dir/.git" ] || continue
  git -C "$repo_dir" show -s --format='%H%x09%cI' HEAD
done
```

Expected: one full SHA and ISO timestamp per Git repository.

### Task 3: Refresh the archive and add the missing P8 references

**Files:**
- Replace locally but keep ignored: `reference_repos/servegen/`
- Create locally but keep ignored: `reference_repos/unified-cache-management/`
- Create locally but keep ignored: `reference_repos/vllm-ascend-v0.18.0/`

**Interfaces:**
- Consumes: official upstream URLs and the vLLM-Ascend `v0.18.0` tag.
- Produces: current ServeGen source, current UCM source, and immutable server-version source evidence.

- [x] **Step 1: Verify the ServeGen default-branch snapshot before replacing it.**

Because upstream `main` remained at the recorded commit, use the GitHub tree API
and local Git blob hashes to avoid rewriting the 828 MiB snapshot:

```bash
sha=765b7a2339bbe7658205be8a95a5076f9f389590
gh api repos/alibaba/ServeGen/commits/main --jq .sha
gh api "repos/alibaba/ServeGen/git/trees/$sha?recursive=1"
find reference_repos/servegen -type f -exec git hash-object {} \;
```

Expected: upstream remains at `765b7a2339bbe7658205be8a95a5076f9f389590`
and all 864 local blob hashes match, so no directory swap is needed.

- [x] **Step 2: Clone UCM shallowly on its default branch.**

Run:

```bash
git clone --depth 1 https://github.com/ModelEngine-Group/unified-cache-management.git reference_repos/unified-cache-management
```

Expected: a clean shallow checkout with an official origin and a license file.

- [x] **Step 3: Clone the runtime-matched vLLM-Ascend tag shallowly.**

Run:

```bash
git clone --depth 1 --branch v0.18.0 https://github.com/vllm-project/vllm-ascend.git reference_repos/vllm-ascend-v0.18.0
```

Expected: detached `HEAD` at tag `v0.18.0`, commit `e18643f8a4d5bd9990727654318ad069ea0b56e2`, clean and shallow.

### Task 4: Update tracked policy and inventory

**Files:**
- Modify: `.gitignore`
- Modify: `reference_repos/README.md`
- Modify: `工作记录与进度笔记本/01_工作记录.md`

**Interfaces:**
- Consumes: final repository SHAs, dates, upstreams, branches/tags, and license names.
- Produces: one current inventory and an explicit main-repository ignore boundary.

- [x] **Step 1: Make the recursive ignore rule explicit.**

Use:

```gitignore
# Third-party reference source trees for P8 code reading; never vendor them.
/reference_repos/**
!/reference_repos/README.md
```

- [x] **Step 2: Rewrite the inventory with the refresh date and exact short SHAs.**

Include all existing repositories, ServeGen archive provenance, UCM, the pinned vLLM-Ascend snapshot, shallow/sparse policy, and the no-submodule/no-model-weights boundary.

- [x] **Step 3: Append the completion entry to the work notebook.**

Record counts of updated/unchanged/added references, exceptions, verification results, and that the P5 server handoff remained unchanged.

### Task 5: Verify the refreshed collection and main-project boundary

**Files:**
- Verify: `.gitignore`
- Verify: `reference_repos/README.md`
- Verify locally ignored: `reference_repos/*/`

**Interfaces:**
- Consumes: all outputs from Tasks 1-4.
- Produces: fresh evidence that repository state and project tracking boundaries match the request.

- [x] **Step 1: Verify every Git checkout is clean, shallow as intended, and matches its upstream or pinned tag.**

Expected: no dirty checkout; branch checkouts have `HEAD == @{upstream}`; the pinned tag resolves to `HEAD`.

- [x] **Step 2: Verify origin and license evidence.**

Expected: every inventory row has a reachable origin/archive URL and at least one recognized license or an explicit `license not found` note.

- [x] **Step 3: Verify main-project ignore behavior and tracked exceptions.**

Run:

```bash
git check-ignore -v reference_repos/vllm/README.md
test "$(git ls-files reference_repos)" = "reference_repos/README.md"
```

Expected: source content is ignored and only the inventory is tracked.

- [x] **Step 4: Run project-level regression checks.**

Run:

```bash
python -m pytest tests/inference_contracts -q
git diff --check
```

Expected: all inference-contract tests pass and no whitespace errors. If a
concurrent task changes `通信模块/docs/developer-to-server.md`, preserve that change and
record that this reference-refresh task did not edit the server handoff.
