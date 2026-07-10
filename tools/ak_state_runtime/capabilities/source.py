from __future__ import annotations

import subprocess
from pathlib import Path

from .models import (
    CapabilityResult,
    CapabilitySpec,
    EvidenceClause,
    EvidenceResult,
    SourceProbeResult,
    SourceProbeSpec,
    TargetResult,
    TargetSpec,
)


class SourceProbeError(RuntimeError):
    """Raised when pinned source cannot be inspected safely."""


def probe_source_capabilities(
    spec: SourceProbeSpec,
    repo_root: Path,
) -> SourceProbeResult:
    target_specs = {target.target_id: target for target in spec.targets}
    target_results = tuple(
        _inspect_target(target, repo_root) for target in spec.targets
    )
    observed_commits = {
        target.target_id: target.observed_commit for target in target_results
    }
    capabilities = tuple(
        _inspect_capability(
            capability,
            target_specs=target_specs,
            observed_commits=observed_commits,
            repo_root=repo_root,
            runtime_gate=spec.selected_workload_gate,
        )
        for capability in spec.capabilities
    )
    return SourceProbeResult(
        probe_id=spec.probe_id,
        probe_date=spec.probe_date,
        claim_ceiling=spec.claim_ceiling,
        selected_workload_model_id=spec.selected_workload_model_id,
        selected_workload_validated=spec.selected_workload_validated,
        selected_workload_gate=spec.selected_workload_gate,
        real_vllm_ascend_adapter_gate=spec.real_vllm_ascend_adapter_gate,
        targets=target_results,
        capabilities=capabilities,
    )


def _inspect_target(target: TargetSpec, repo_root: Path) -> TargetResult:
    repo = repo_root / target.repo_path
    if not repo.is_dir():
        raise SourceProbeError(
            f"target {target.target_id} repository does not exist: "
            f"{target.repo_path}"
        )
    completed = _git(repo, "rev-parse", "--verify", f"{target.tag}^{{commit}}")
    if completed.returncode != 0:
        raise SourceProbeError(
            f"target {target.target_id} tag cannot be resolved: {target.tag}"
        )
    observed_commit = completed.stdout.decode("ascii", errors="strict").strip()
    if observed_commit != target.expected_commit:
        raise SourceProbeError(
            f"target {target.target_id} expected commit {target.expected_commit} "
            f"but {target.tag} resolved to {observed_commit}"
        )
    return TargetResult(
        target_id=target.target_id,
        repo_path=target.repo_path,
        tag=target.tag,
        expected_commit=target.expected_commit,
        observed_commit=observed_commit,
        ref_verified=True,
    )


def _inspect_capability(
    capability: CapabilitySpec,
    *,
    target_specs: dict[str, TargetSpec],
    observed_commits: dict[str, str],
    repo_root: Path,
    runtime_gate: str,
) -> CapabilityResult:
    source = _inspect_group(
        capability.source_evidence,
        "source",
        target_specs,
        observed_commits,
        repo_root,
    )
    instrumentation = _inspect_group(
        capability.instrumentation_evidence,
        "instrumentation",
        target_specs,
        observed_commits,
        repo_root,
    )
    documentation = _inspect_group(
        capability.documentation_evidence,
        "documentation",
        target_specs,
        observed_commits,
        repo_root,
    )
    return CapabilityResult(
        capability_id=capability.capability_id,
        runtime_scope=capability.runtime_scope,
        status=_derive_status(source, instrumentation, documentation),
        source_evidence=source,
        instrumentation_evidence=instrumentation,
        documentation_evidence=documentation,
        selected_workload_validated=False,
        runtime_gate=runtime_gate,
    )


def _inspect_group(
    clauses: tuple[EvidenceClause, ...],
    group: str,
    target_specs: dict[str, TargetSpec],
    observed_commits: dict[str, str],
    repo_root: Path,
) -> tuple[EvidenceResult, ...]:
    return tuple(
        _inspect_evidence(
            clause,
            group=group,
            target=target_specs[clause.target_id],
            commit=observed_commits[clause.target_id],
            repo_root=repo_root,
        )
        for clause in clauses
    )


def _inspect_evidence(
    clause: EvidenceClause,
    *,
    group: str,
    target: TargetSpec,
    commit: str,
    repo_root: Path,
) -> EvidenceResult:
    repo = repo_root / target.repo_path
    object_name = f"{commit}:{clause.path}"
    oid_result = _git(repo, "rev-parse", "--verify", object_name)
    if oid_result.returncode != 0:
        return EvidenceResult(
            evidence_id=clause.evidence_id,
            evidence_group=group,
            target_id=clause.target_id,
            path=clause.path,
            contains=clause.contains,
            matched=False,
            blob_oid=None,
            matched_lines=(),
            error="path_missing_at_target",
        )

    blob_oid = oid_result.stdout.decode("ascii", errors="strict").strip()
    show_result = _git(repo, "show", object_name)
    if show_result.returncode != 0:
        return EvidenceResult(
            evidence_id=clause.evidence_id,
            evidence_group=group,
            target_id=clause.target_id,
            path=clause.path,
            contains=clause.contains,
            matched=False,
            blob_oid=blob_oid,
            matched_lines=(),
            error="blob_read_failed",
        )
    try:
        text = show_result.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return EvidenceResult(
            evidence_id=clause.evidence_id,
            evidence_group=group,
            target_id=clause.target_id,
            path=clause.path,
            contains=clause.contains,
            matched=False,
            blob_oid=blob_oid,
            matched_lines=(),
            error="blob_not_utf8",
        )

    matched_lines = tuple(
        line_number
        for line_number, line in enumerate(text.splitlines(), start=1)
        if clause.contains in line
    )
    return EvidenceResult(
        evidence_id=clause.evidence_id,
        evidence_group=group,
        target_id=clause.target_id,
        path=clause.path,
        contains=clause.contains,
        matched=bool(matched_lines),
        blob_oid=blob_oid,
        matched_lines=matched_lines,
        error=None if matched_lines else "substring_not_found",
    )


def _derive_status(
    source: tuple[EvidenceResult, ...],
    instrumentation: tuple[EvidenceResult, ...],
    documentation: tuple[EvidenceResult, ...],
) -> str:
    source_available = bool(source) and all(item.matched for item in source)
    instrumentation_available = bool(instrumentation) and all(
        item.matched for item in instrumentation
    )
    documentation_available = bool(documentation) and all(
        item.matched for item in documentation
    )
    if source_available and instrumentation_available:
        return "instrumented"
    if source_available:
        return "available_uninstrumented"
    if documentation_available:
        return "documented_unverified"
    return "unsupported"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
    )
