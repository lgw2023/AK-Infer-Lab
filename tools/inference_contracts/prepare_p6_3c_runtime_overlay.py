from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import traceback
from typing import Any


MTP_OUTPUT_SHA256 = (
    "7b57fd392af62901bddbf83f6e1e9c38c936fded5ac32d17bbd715f4ed3cff02"
)
HYBRID_COORDINATOR_OUTPUT_SHA256 = (
    "a1ed9c82e308608cd20965a49baa29a3e95d723248fff699fd83dfb3caf10250"
)
HYBRID_INTERFACE_OUTPUT_SHA256 = (
    "524c933ef17806ecba0634804bc562de1f69dc095fe1346e2edd0103845bfa75"
)
ACL_GRAPH_COMPAT_OUTPUT_SHA256 = (
    "f81b08686b4e62daff5de4c795ce3eb80415a6eef133f82177876c7a3e18b0ad"
)
DEFAULT_ADMISSION_MODULE_NAME = "p6_3c_r2_f3_atomic_pair_admission"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validated_python_module_name(value: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) is None:
        raise ValueError(f"invalid Python module name: {value!r}")
    return value


def _run_patch(
    command: list[str],
    patch_path: Path,
    cwd: Path,
    log_path: Path,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        input=patch_path.read_bytes(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_bytes(completed.stdout)
    return completed


def _require_success(
    completed: subprocess.CompletedProcess[bytes],
    stage: str,
) -> None:
    if completed.returncode != 0:
        raise RuntimeError(f"{stage}_failed:exit={completed.returncode}")


def _apply_standard_patch(
    patch_path: Path,
    overlay_root: Path,
    runtime_dir: Path,
    stem: str,
) -> None:
    dry_run = _run_patch(
        ["patch", "-p1", "--dry-run"],
        patch_path,
        overlay_root,
        runtime_dir / f"{stem}_dry_run.txt",
    )
    _require_success(dry_run, f"{stem}_dry_run")
    apply = _run_patch(
        ["patch", "-p1"],
        patch_path,
        overlay_root,
        runtime_dir / f"{stem}_apply.txt",
    )
    _require_success(apply, f"{stem}_apply")


def _apply_deferred_patch(
    patch_path: Path,
    overlay_root: Path,
    runtime_dir: Path,
) -> str:
    dry_run = _run_patch(
        ["patch", "-l", "-p1", "--dry-run"],
        patch_path,
        overlay_root,
        runtime_dir / "deferred_patch_dry_run.txt",
    )
    if dry_run.returncode == 0:
        apply = _run_patch(
            ["patch", "-l", "-p1"],
            patch_path,
            overlay_root,
            runtime_dir / "deferred_patch_apply.txt",
        )
        _require_success(apply, "deferred_patch_apply")
        return "patch_l"

    check = subprocess.run(
        [
            "git",
            "apply",
            "--check",
            "--ignore-whitespace",
            str(patch_path),
        ],
        cwd=overlay_root,
        env={**os.environ, "GIT_DIR": "/dev/null"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    apply_log = runtime_dir / "deferred_patch_apply.txt"
    apply_log.write_bytes(check.stdout)
    _require_success(check, "deferred_git_apply_check")
    apply = subprocess.run(
        ["git", "apply", "--ignore-whitespace", str(patch_path)],
        cwd=overlay_root,
        env={**os.environ, "GIT_DIR": "/dev/null"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    with apply_log.open("ab") as handle:
        handle.write(apply.stdout)
    _require_success(apply, "deferred_git_apply")
    return "git_apply_ignore_whitespace"


def _assert_materialized_tree(overlay_root: Path, package_root: Path) -> dict[str, int]:
    overlay_real = overlay_root.resolve(strict=True)
    symlinks = []
    escaped = []
    file_count = 0
    directory_count = 0
    for path in package_root.rglob("*"):
        if path.is_symlink():
            symlinks.append(str(path))
            continue
        if path.is_dir():
            directory_count += 1
        elif path.is_file():
            file_count += 1
        try:
            path.resolve(strict=True).relative_to(overlay_real)
        except (FileNotFoundError, ValueError):
            escaped.append(str(path))
    if package_root.is_symlink() or symlinks:
        raise RuntimeError(
            f"overlay_contains_symlink:count={len(symlinks)}"
        )
    if escaped:
        raise RuntimeError(
            f"overlay_realpath_escape:count={len(escaped)}"
        )
    return {
        "materialized_file_count": file_count,
        "materialized_directory_count": directory_count,
        "symlink_count": len(symlinks),
        "realpath_escape_count": len(escaped),
    }


def prepare_overlay(args: argparse.Namespace) -> dict[str, Any]:
    runtime_dir = args.runtime_dir
    overlay_root = runtime_dir / "overlay_root"
    overlay_package = overlay_root / "vllm_ascend"
    if overlay_package.exists() or overlay_package.is_symlink():
        raise RuntimeError(f"overlay_destination_exists:{overlay_package}")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    overlay_root.mkdir(parents=True, exist_ok=True)

    base_plugin_root = args.base_plugin_root.resolve(strict=True)
    if base_plugin_root.name != "vllm_ascend":
        raise RuntimeError(f"base_plugin_root_invalid:{base_plugin_root}")
    shutil.copytree(
        base_plugin_root,
        overlay_package,
        symlinks=False,
        copy_function=shutil.copy2,
    )
    materialized = _assert_materialized_tree(overlay_root, overlay_package)

    _apply_standard_patch(
        args.mtp_patch,
        overlay_root,
        runtime_dir,
        "mtp_patch",
    )
    proposer = overlay_package / "spec_decode/llm_base_proposer.py"
    if _sha256(proposer) != MTP_OUTPUT_SHA256:
        raise RuntimeError("mtp_output_sha256_mismatch")

    patch_methods: dict[str, str] = {"mtp": "patch_p1"}
    if args.enable_acl_graph_compat:
        _apply_standard_patch(
            args.acl_graph_compat_patch,
            overlay_root,
            runtime_dir,
            "acl_graph_compat_patch",
        )
        acl_graph = overlay_package / "compilation/acl_graph.py"
        if _sha256(acl_graph) != ACL_GRAPH_COMPAT_OUTPUT_SHA256:
            raise RuntimeError("acl_graph_compat_output_sha256_mismatch")
        patch_methods["acl_graph_compat"] = "patch_p1"

    if args.shared_hybrid_kv_repair:
        shutil.copy2(
            args.runtime_impl,
            overlay_root / "p6_3b_hybrid_kv_runtime_impl.py",
        )
        shutil.copy2(
            args.runtime_loader,
            overlay_root / "p6_3b_r2_hybrid_kv_runtime_patch.py",
        )
        _apply_standard_patch(
            args.hybrid_patch,
            overlay_root,
            runtime_dir,
            "hybrid_patch",
        )
        patch_methods["hybrid"] = "patch_p1"
        patch_methods["deferred"] = _apply_deferred_patch(
            args.deferred_patch,
            overlay_root,
            runtime_dir,
        )
        (runtime_dir / "deferred_patch_method.txt").write_text(
            patch_methods["deferred"] + "\n",
            encoding="utf-8",
        )
        coordinator = (
            overlay_package
            / "patch/platform/patch_kv_cache_coordinator.py"
        )
        interface = (
            overlay_package / "patch/platform/patch_kv_cache_interface.py"
        )
        if _sha256(coordinator) != HYBRID_COORDINATOR_OUTPUT_SHA256:
            raise RuntimeError("hybrid_coordinator_output_sha256_mismatch")
        if _sha256(interface) != HYBRID_INTERFACE_OUTPUT_SHA256:
            raise RuntimeError("hybrid_interface_output_sha256_mismatch")

    if args.enable_atomic_pair_admission:
        admission_module_name = validated_python_module_name(
            args.admission_module_name
        )
        shutil.copy2(
            args.admission_controller,
            overlay_root / f"{admission_module_name}.py",
        )
        _apply_standard_patch(
            args.admission_patch,
            overlay_root,
            runtime_dir,
            "atomic_pair_admission_patch",
        )
        patch_methods["atomic_pair_admission"] = "patch_p1"

    if args.enable_observer:
        shutil.copy2(
            args.observer,
            overlay_root / "p6_3c_r1_scheduler_observer.py",
        )
        _apply_standard_patch(
            args.observer_patch,
            overlay_root,
            runtime_dir,
            "observer_patch",
        )
        patch_methods["observer"] = "patch_p1"

    materialized = _assert_materialized_tree(overlay_root, overlay_package)
    output_hashes = {
        "overlay_proposer_sha256": _sha256(proposer),
    }
    if args.shared_hybrid_kv_repair:
        output_hashes.update(
            {
                "overlay_ascend_coordinator_sha256": _sha256(
                    overlay_package
                    / "patch/platform/patch_kv_cache_coordinator.py"
                ),
                "overlay_ascend_interface_sha256": _sha256(
                    overlay_package
                    / "patch/platform/patch_kv_cache_interface.py"
                ),
            }
        )
    if args.enable_acl_graph_compat:
        output_hashes["overlay_acl_graph_sha256"] = _sha256(
            overlay_package / "compilation/acl_graph.py"
        )
    manifest = {
        "schema_version": 1,
        "base_plugin_root_requested": str(args.base_plugin_root),
        "base_plugin_root_resolved": str(base_plugin_root),
        "overlay_root": str(overlay_root.resolve(strict=True)),
        "overlay_package_root": str(overlay_package.resolve(strict=True)),
        "copy_semantics": "materialized_copy_dereference_symlinks_no_ownership",
        "shared_hybrid_kv_repair": args.shared_hybrid_kv_repair,
        "acl_graph_compat": args.enable_acl_graph_compat,
        "atomic_pair_admission": args.enable_atomic_pair_admission,
        "atomic_pair_admission_module": (
            validated_python_module_name(args.admission_module_name)
            if args.enable_atomic_pair_admission
            else None
        ),
        "observer": args.enable_observer,
        "patch_methods": patch_methods,
        "patch_source_sha256": {
            path.name: _sha256(path)
            for path in (
                args.mtp_patch,
                args.acl_graph_compat_patch,
                args.hybrid_patch,
                args.deferred_patch,
                args.admission_patch,
                args.observer_patch,
            )
            if path is not None and path.is_file()
        },
        "output_hashes": output_hashes,
        **materialized,
        "base_environment_mutated": False,
        "site_packages_mutated": False,
    }
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _tail_logs(runtime_dir: Path, limit: int = 4096) -> str:
    chunks = []
    for path in sorted(runtime_dir.glob("*patch*.txt")):
        payload = path.read_text(encoding="utf-8", errors="replace")
        chunks.append(f"== {path.name} ==\n{payload}")
    return "\n".join(chunks)[-limit:]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-plugin-root", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--mtp-patch", type=Path, required=True)
    parser.add_argument("--runtime-impl", type=Path)
    parser.add_argument("--runtime-loader", type=Path)
    parser.add_argument("--hybrid-patch", type=Path)
    parser.add_argument("--deferred-patch", type=Path)
    parser.add_argument("--acl-graph-compat-patch", type=Path)
    parser.add_argument("--admission-controller", type=Path)
    parser.add_argument("--admission-patch", type=Path)
    parser.add_argument(
        "--admission-module-name",
        default=DEFAULT_ADMISSION_MODULE_NAME,
    )
    parser.add_argument("--observer", type=Path)
    parser.add_argument("--observer-patch", type=Path)
    parser.add_argument("--shared-hybrid-kv-repair", action="store_true")
    parser.add_argument("--enable-acl-graph-compat", action="store_true")
    parser.add_argument("--enable-atomic-pair-admission", action="store_true")
    parser.add_argument("--enable-observer", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--failure-excerpt", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.shared_hybrid_kv_repair:
        for name in (
            "runtime_impl",
            "runtime_loader",
            "hybrid_patch",
            "deferred_patch",
        ):
            if getattr(args, name) is None:
                parser.error(f"--{name.replace('_', '-')} is required")
    if args.enable_acl_graph_compat and args.acl_graph_compat_patch is None:
        parser.error("--acl-graph-compat-patch is required")
    if args.enable_observer and (
        args.observer is None or args.observer_patch is None
    ):
        parser.error("--observer and --observer-patch are required")
    if args.enable_atomic_pair_admission and (
        args.admission_controller is None or args.admission_patch is None
    ):
        parser.error(
            "--admission-controller and --admission-patch are required"
        )
    if args.enable_atomic_pair_admission:
        try:
            validated_python_module_name(args.admission_module_name)
        except ValueError as exc:
            parser.error(str(exc))
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = prepare_overlay(args)
    except Exception as error:
        args.failure_excerpt.parent.mkdir(parents=True, exist_ok=True)
        args.failure_excerpt.write_text(
            "runtime_overlay_preparation_failed\n"
            f"error={error}\n"
            f"{_tail_logs(args.runtime_dir)}\n"
            f"{traceback.format_exc()[-2048:]}",
            encoding="utf-8",
        )
        print(args.failure_excerpt.read_text(encoding="utf-8"), end="")
        return 2
    args.failure_excerpt.write_text("none\n", encoding="utf-8")
    print(
        "runtime_overlay_prepared:"
        f"files={manifest['materialized_file_count']}:"
        f"symlinks={manifest['symlink_count']}:"
        f"escapes={manifest['realpath_escape_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
