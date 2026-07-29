from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any


PACKAGE_NAMES = ("vllm", "vllm_ascend")


def _resolved_package_root(package_name: str) -> tuple[Path, Path]:
    spec = importlib.util.find_spec(package_name)
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError(f"package_not_resolvable:{package_name}")
    locations = list(spec.submodule_search_locations)
    if len(locations) != 1:
        raise RuntimeError(
            f"package_location_count_not_one:{package_name}:{len(locations)}"
        )
    package_root = Path(locations[0]).resolve(strict=True)
    if package_root.name != package_name or not package_root.is_dir():
        raise RuntimeError(
            f"package_root_invalid:{package_name}:{package_root}"
        )
    if spec.origin is None:
        raise RuntimeError(f"package_origin_missing:{package_name}")
    package_init = Path(spec.origin).resolve(strict=True)
    if not package_init.is_file() or package_init.parent != package_root:
        raise RuntimeError(
            f"package_origin_outside_root:{package_name}:{package_init}"
        )
    return package_root, package_init


def resolve_runtime_layout(expected_env_prefix: Path | None) -> dict[str, Any]:
    python_executable = Path(sys.executable).resolve(strict=True)
    environment_prefix = Path(sys.prefix).resolve(strict=True)
    if (
        expected_env_prefix is not None
        and expected_env_prefix.resolve(strict=True) != environment_prefix
    ):
        raise RuntimeError(
            "python_prefix_mismatch:"
            f"expected={expected_env_prefix.resolve(strict=True)}:"
            f"actual={environment_prefix}"
        )

    packages: dict[str, Any] = {}
    for package_name in PACKAGE_NAMES:
        package_root, package_init = _resolved_package_root(package_name)
        try:
            package_root.relative_to(environment_prefix)
            source_kind = "environment_owned"
        except ValueError:
            source_kind = "editable_external"
        packages[package_name] = {
            "package_root": str(package_root),
            "package_init": str(package_init),
            "source_kind": source_kind,
        }

    vllm_bin = python_executable.parent / "vllm"
    if not vllm_bin.is_file() or not os.access(vllm_bin, os.X_OK):
        raise RuntimeError(f"vllm_entrypoint_missing:{vllm_bin}")

    return {
        "schema_version": 1,
        "resolution_method": (
            "target_environment_importlib_find_spec_then_realpath"
        ),
        "python_executable": str(python_executable),
        "environment_prefix": str(environment_prefix),
        "vllm_entrypoint": str(vllm_bin),
        "packages": packages,
        "base_vllm_root": packages["vllm"]["package_root"],
        "base_plugin_root": packages["vllm_ascend"]["package_root"],
        "site_packages_only_assumed": False,
        "editable_install_supported": True,
        "source_files_mutated": False,
    }


def _write_shell_exports(layout: dict[str, Any], output: Path) -> None:
    exports = {
        "ENV_PREFIX": layout["environment_prefix"],
        "PYTHON_BIN": layout["python_executable"],
        "BASE_PYTHON": layout["python_executable"],
        "VLLM_BIN": layout["vllm_entrypoint"],
        "BASE_VLLM_ROOT": layout["base_vllm_root"],
        "BASE_PLUGIN_ROOT": layout["base_plugin_root"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(
            f"export {name}={shlex.quote(str(value))}\n"
            for name, value in exports.items()
        ),
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-env-prefix", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shell-output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    layout = resolve_runtime_layout(args.expected_env_prefix)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(layout, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_shell_exports(layout, args.shell_output)
    print(
        "runtime_layout_resolved:"
        f"vllm={layout['base_vllm_root']}:"
        f"vllm_ascend={layout['base_plugin_root']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
