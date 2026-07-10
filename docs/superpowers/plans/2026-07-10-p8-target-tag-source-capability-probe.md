# P8 Target-tag Source Capability Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inspect the pinned vLLM `v0.20.2` and vLLM-Ascend `v0.20.2rc1`
Git objects without importing either runtime, then publish a deterministic,
evidence-backed source capability matrix whose claim ceiling is `instrumented`.

**Architecture:** A declarative YAML spec names pinned repositories, exact tag
commits, and plain-text evidence clauses. An isolated capability package reads
Git blobs at those commits, derives one of the approved P8 capability states,
and serializes YAML plus Markdown; the existing CLI is only the composition
root. Source evidence can never emit `validated_for_selected_workload` and does
not create `VllmAscendAdapter`.

**Tech Stack:** Python 3.11+, dataclasses, subprocess Git plumbing, PyYAML,
pytest.

## Global Constraints

- Inspect `v0.20.2@bc150f50299199599673614f80d12a196f377655` and
  `v0.20.2rc1@367b8e62da799870a7476ce34f5f7658589a8aad` exactly.
- Never checkout, modify, import, or add `reference_repos/` to `sys.path`.
- Source-derived status is capped at `instrumented`; selected-workload and
  server validation remain false.
- Keep `tools/ak_state_runtime` free of vLLM, vLLM-Ascend, torch, torch-npu,
  CANN, and `reference_repos` imports.
- Keep the real `VllmAscendAdapter` absent until the selected-workload/runtime
  gate is closed.
- Do not modify `通信模块/docs/developer-to-server.md` in this local-only gate.
- Every production behavior starts with a focused failing test.

---

### Task 1: Capability contracts and spec validation

**Files:**
- Create: `tools/ak_state_runtime/capabilities/__init__.py`
- Create: `tools/ak_state_runtime/capabilities/models.py`
- Create: `tests/ak_state_runtime/test_source_capability_probe.py`

**Interfaces:**
- Produces: `ProbeSpecError`, `EvidenceClause`, `TargetSpec`,
  `CapabilitySpec`, `SourceProbeSpec`, `EvidenceResult`, `CapabilityResult`,
  `SourceProbeResult`, and `parse_probe_spec(record)`.
- Status vocabulary: `unsupported`, `documented_unverified`,
  `available_uninstrumented`, `instrumented`,
  `validated_for_selected_workload`.

- [x] **Step 1: Write failing contract tests**

```python
def test_parse_probe_spec_requires_exact_pinned_commit():
    with pytest.raises(ProbeSpecError, match="expected_commit"):
        parse_probe_spec({"schema_name": "ak_target_tag_source_probe"})

def test_source_probe_claim_ceiling_cannot_be_selected_workload():
    record = minimal_spec(claim_ceiling="validated_for_selected_workload")
    with pytest.raises(ProbeSpecError, match="claim_ceiling"):
        parse_probe_spec(record)
```

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/ak_state_runtime/test_source_capability_probe.py -q`

Expected: FAIL because `tools.ak_state_runtime.capabilities` does not exist.

- [x] **Step 3: Implement immutable contracts and strict parser**

```python
SOURCE_CLAIM_CEILING = "instrumented"

def parse_probe_spec(record: Mapping[str, Any]) -> SourceProbeSpec:
    """Validate schema/version, unique IDs, target references, evidence
    groups, exact 40-hex commits, and the source-only claim ceiling."""
```

- [x] **Step 4: Verify GREEN**

Run: `python -m pytest tests/ak_state_runtime/test_source_capability_probe.py -q`

Expected: PASS for parsing tests.

### Task 2: Read-only pinned Git source evaluator

**Files:**
- Create: `tools/ak_state_runtime/capabilities/source.py`
- Modify: `tests/ak_state_runtime/test_source_capability_probe.py`

**Interfaces:**
- Consumes: `SourceProbeSpec`.
- Produces: `probe_source_capabilities(spec, repo_root) -> SourceProbeResult`.
- Git operations: `rev-parse <tag>^{commit}`, `rev-parse <commit>:<path>`, and
  `show <commit>:<path>` only.

- [x] **Step 1: Add real temporary-repository tests**

```python
def test_probe_derives_statuses_from_git_blobs(tmp_path: Path):
    repo = init_tagged_repo(tmp_path, {"impl.py": "class Feature: pass\n"})
    result = probe_source_capabilities(spec_for(repo), tmp_path)
    assert [item.status for item in result.capabilities] == [
        "available_uninstrumented",
        "instrumented",
        "documented_unverified",
        "unsupported",
    ]

def test_probe_rejects_tag_commit_drift(tmp_path: Path):
    with pytest.raises(SourceProbeError, match="expected commit"):
        probe_source_capabilities(spec_with_wrong_commit(tmp_path), tmp_path)
```

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/ak_state_runtime/test_source_capability_probe.py -q`

Expected: FAIL because the evaluator is absent.

- [x] **Step 3: Implement minimal Git blob inspection and status derivation**

```python
def probe_source_capabilities(
    spec: SourceProbeSpec,
    repo_root: Path,
) -> SourceProbeResult:
    """Verify pinned refs, inspect exact blobs, record blob OIDs and matching
    line numbers, then derive source-only statuses without importing runtime
    code."""
```

Derivation order:

```text
all source + non-empty all instrumentation -> instrumented
all source                                  -> available_uninstrumented
all documentation                           -> documented_unverified
otherwise                                   -> unsupported
```

- [x] **Step 4: Verify GREEN**

Run: `python -m pytest tests/ak_state_runtime/test_source_capability_probe.py -q`

Expected: PASS.

### Task 3: Deterministic outputs and CLI composition

**Files:**
- Create: `tools/ak_state_runtime/capabilities/report.py`
- Create: `tests/ak_state_runtime/test_source_capability_outputs.py`
- Modify: `tools/ak_state_runtime/cli.py`

**Interfaces:**
- Consumes: `SourceProbeResult`.
- Produces: `matrix_bytes(result)`, `report_bytes(result)`, and
  `write_source_probe_outputs(result, matrix_path, report_path)`.
- CLI: `python -m tools.ak_state_runtime.cli probe-source-capabilities
  --spec <yaml> --repo-root <path> --matrix-output <yaml>
  --report-output <md>`.

- [x] **Step 1: Write failing deterministic-output and subprocess tests**

```python
def test_source_probe_outputs_are_byte_identical(tmp_path: Path):
    result = probe_source_capabilities(valid_spec, tmp_path)
    assert matrix_bytes(result) == matrix_bytes(result)
    assert report_bytes(result) == report_bytes(result)

def test_cli_does_not_publish_on_tag_drift(tmp_path: Path):
    completed = run_probe_cli(spec_with_wrong_commit, tmp_path)
    assert completed.returncode != 0
    assert not matrix_output.exists()
    assert not report_output.exists()
```

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/ak_state_runtime/test_source_capability_outputs.py -q`

Expected: FAIL because reporting and CLI support are absent.

- [x] **Step 3: Implement stable YAML/Markdown serialization and CLI branch**

```python
def write_source_probe_outputs(
    result: SourceProbeResult,
    matrix_path: Path,
    report_path: Path,
) -> None:
    """Refuse pre-existing outputs, prepare both byte payloads, then publish
    the two small text artifacts."""
```

- [x] **Step 4: Verify GREEN**

Run: `python -m pytest tests/ak_state_runtime/test_source_capability_outputs.py -q`

Expected: PASS.

### Task 4: Target-tag evidence spec and committed matrix

**Files:**
- Create: `benchmarks/deepseek_v4_flash/p8/source_capability_probe.yaml`
- Create: `benchmarks/deepseek_v4_flash/p8/runtime_capability_matrix.yaml`
- Create: `benchmarks/deepseek_v4_flash/p8/p8_0_source_capability_probe_report.md`
- Modify: `tests/ak_state_runtime/test_source_capability_outputs.py`

**Interfaces:** The target spec covers DeepSeek-V4 model registration, MTP,
tool/reasoning parser, DSA-CP, FlashComm1, prefix cache, KV events, CPU offload,
UCM, KV pool, EPLB/static mapping, expert-load instrumentation, and weight
prefetch.

- [x] **Step 1: Write a failing committed-artifact boundary test**

```python
def test_committed_matrix_is_source_only_and_adapter_remains_gated():
    matrix = yaml.safe_load(MATRIX.read_text())
    assert matrix["claim_ceiling"] == "instrumented"
    assert matrix["selected_workload_validated"] is False
    assert matrix["real_vllm_ascend_adapter_gate"] == (
        "waiting_selected_workload_runtime_gate"
    )
    assert all(
        row["status"] != "validated_for_selected_workload"
        for row in matrix["capabilities"]
    )
```

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/ak_state_runtime/test_source_capability_outputs.py -q`

Expected: FAIL because the target artifacts do not exist.

- [x] **Step 3: Add exact evidence clauses and generate artifacts**

Run:

```bash
python -m tools.ak_state_runtime.cli probe-source-capabilities \
  --spec benchmarks/deepseek_v4_flash/p8/source_capability_probe.yaml \
  --repo-root . \
  --matrix-output benchmarks/deepseek_v4_flash/p8/runtime_capability_matrix.yaml \
  --report-output benchmarks/deepseek_v4_flash/p8/p8_0_source_capability_probe_report.md
```

Expected: both target commits verify; all results stay at or below
`instrumented` and explicitly preserve the runtime gate.

- [x] **Step 4: Verify GREEN and byte-identical regeneration**

Run the CLI into a temporary directory and compare both files with `cmp -s`.

Expected: both comparisons return exit code 0.

### Task 5: Independence, progress, and closeout

**Files:**
- Modify: `tests/ak_state_runtime/test_module_independence.py`
- Modify: `docs/P8_LAYERED_ENGINEERING_PROTOTYPE_PLAN.md`
- Modify: `工作记录与进度笔记本/01_工作记录.md`

- [x] **Step 1: Test that only CLI imports the concrete source evaluator and
  no `VllmAscendAdapter` exists**
- [x] **Step 2: Run `python -m pytest tests/ak_state_runtime -q`**
- [x] **Step 3: Run `python -m pytest tests/inference_contracts -q`**
- [x] **Step 4: Run `python -m pytest -q`**
- [x] **Step 5: Run `python -m compileall -q tools/ak_state_runtime` and
  `git diff --check`**
- [x] **Step 6: Record exact source statuses, target commits, artifact paths,
  static-evidence ceiling, and the still-closed adapter gate**
- [x] **Step 7: Commit the completed probe without issuing a server task**
