import ast
from pathlib import Path


PACKAGE_DIR = Path("tools/ak_state_runtime")
FORBIDDEN_IMPORT_ROOTS = {
    "vllm",
    "vllm_ascend",
    "torch",
    "torch_npu",
    "cann",
    "reference_repos",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_package_has_no_runtime_or_reference_repository_imports() -> None:
    violations: list[str] = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        for imported in sorted(_imports(path)):
            root = imported.split(".", maxsplit=1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS:
                violations.append(f"{path}: {imported}")

    assert violations == []


def test_only_cli_imports_the_concrete_p1_adapter() -> None:
    importers = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        if any(imported.endswith("adapters.p1_fixture") for imported in _imports(path)):
            importers.append(path.relative_to(PACKAGE_DIR).as_posix())

    assert importers == ["cli.py"]


def test_legacy_p1_vocabulary_is_confined_to_the_adapter_and_cli() -> None:
    violations: list[str] = []
    allowed = {"adapters/p1_fixture.py", "cli.py"}
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        relative = path.relative_to(PACKAGE_DIR).as_posix()
        if relative in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if "p1_fixture" in text or "p1_inference_contracts" in text:
            violations.append(relative)

    assert violations == []


def test_registry_and_policy_depend_only_on_core_models() -> None:
    targets = [PACKAGE_DIR / "registry.py", PACKAGE_DIR / "policies/observe_only.py"]
    violations: list[str] = []
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                if node.module != "models":
                    violations.append(f"{path}: {node.module}")

    assert violations == []
