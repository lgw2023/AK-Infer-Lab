import os
import shutil
import subprocess
from pathlib import Path


SCRIPT = Path("通信模块/server_local_git_sync.sh").resolve()


def _git(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _configure_identity(path: Path) -> None:
    _git(path, "config", "user.name", "Server Local Test")
    _git(path, "config", "user.email", "server-local@example.test")


def _commit_file(path: Path, filename: str, content: str, message: str) -> None:
    target = path / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(path, "add", filename)
    _git(path, "commit", "-m", message)


def _fixture(tmp_path: Path) -> dict[str, Path | dict[str, str]]:
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    mirror = tmp_path / "mirror"
    local_worktree = tmp_path / "server-local"
    reports = tmp_path / "reports"

    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(seed)], check=True, capture_output=True)
    _configure_identity(seed)
    _commit_file(seed, "base.txt", "base\n", "seed")
    _commit_file(
        seed,
        "shared.txt",
        "one\ntwo\nthree\nfour\n",
        "seed shared file",
    )
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "main")
    subprocess.run(
        ["git", "clone", "--branch", "main", str(origin), str(mirror)],
        check=True,
        capture_output=True,
    )
    _configure_identity(mirror)

    env = {
        **os.environ,
        "AK_SERVER_MIRROR_ROOT": str(mirror),
        "AK_SERVER_LOCAL_WORKTREE": str(local_worktree),
        "AK_SERVER_LOCAL_BRANCH": "server-local/runtime-adaptations",
        "AK_SERVER_GIT_REPORT_ROOT": str(reports),
    }
    return {
        "origin": origin,
        "seed": seed,
        "mirror": mirror,
        "local_worktree": local_worktree,
        "reports": reports,
        "env": env,
    }


def _run(mode: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), mode],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _report_dir(stdout: str) -> Path:
    value = next(
        line.removeprefix("REPORT_DIR=")
        for line in stdout.splitlines()
        if line.startswith("REPORT_DIR=")
    )
    return Path(value)


def test_init_creates_a_local_only_branch_and_separate_worktree(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    completed = _run("init", fixture["env"])

    assert completed.returncode == 0, completed.stderr
    local_worktree = fixture["local_worktree"]
    assert _git(local_worktree, "branch", "--show-current").stdout.strip() == (
        "server-local/runtime-adaptations"
    )
    assert _git(local_worktree, "rev-parse", "HEAD").stdout == _git(
        fixture["mirror"], "rev-parse", "origin/main"
    ).stdout
    remote_refs = subprocess.run(
        [
            "git",
            "ls-remote",
            "--heads",
            str(fixture["origin"]),
            "server-local/*",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert remote_refs.stdout == ""
    summary = (_report_dir(completed.stdout) / "summary.tsv").read_text(
        encoding="utf-8"
    )
    assert "status\tclean" in summary
    assert "merge_tree_mode\twrite-tree" in summary
    assert "merge_tree_exit_code\t0" in summary


def test_sync_merges_non_conflicting_upstream_into_local_branch_only(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    assert _run("init", fixture["env"]).returncode == 0
    local_worktree = fixture["local_worktree"]
    _configure_identity(local_worktree)
    _commit_file(local_worktree, "server.txt", "server\n", "server-only change")
    _commit_file(fixture["seed"], "external.txt", "external\n", "external change")
    _git(fixture["seed"], "push", "origin", "main")

    completed = _run("sync", fixture["env"])

    assert completed.returncode == 0, completed.stderr
    assert (local_worktree / "server.txt").read_text(encoding="utf-8") == "server\n"
    assert (local_worktree / "external.txt").read_text(encoding="utf-8") == "external\n"
    assert not (fixture["mirror"] / "server.txt").exists()
    remote_refs = subprocess.run(
        [
            "git",
            "ls-remote",
            "--heads",
            str(fixture["origin"]),
            "server-local/*",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert remote_refs.stdout == ""


def test_check_uses_one_locale_for_non_ascii_path_sets(tmp_path: Path) -> None:
    assert "LC_ALL=C comm -12" in SCRIPT.read_text(encoding="utf-8")
    fixture = _fixture(tmp_path)
    assert _run("init", fixture["env"]).returncode == 0
    _commit_file(
        fixture["seed"],
        "通信模块/locale.txt",
        "non-ascii path\n",
        "add non-ascii path",
    )
    _commit_file(
        fixture["seed"],
        "tests/ascii.txt",
        "ascii path\n",
        "add ascii path",
    )
    _git(fixture["seed"], "push", "origin", "main")
    env = {
        **fixture["env"],
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
    }

    completed = _run("check", env)

    assert completed.returncode == 0, completed.stderr
    report_dir = _report_dir(completed.stdout)
    assert (report_dir / "same_path_overlap.txt").read_text(encoding="utf-8") == ""
    assert "status\tclean" in (report_dir / "summary.tsv").read_text(
        encoding="utf-8"
    )


def test_sync_reports_real_conflict_without_changing_local_head(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    assert _run("init", fixture["env"]).returncode == 0
    local_worktree = fixture["local_worktree"]
    _configure_identity(local_worktree)
    _commit_file(local_worktree, "base.txt", "server version\n", "server conflict")
    local_head = _git(local_worktree, "rev-parse", "HEAD").stdout.strip()
    _commit_file(fixture["seed"], "base.txt", "external version\n", "external conflict")
    _git(fixture["seed"], "push", "origin", "main")

    completed = _run("sync", fixture["env"])

    assert completed.returncode == 2
    assert _git(local_worktree, "rev-parse", "HEAD").stdout.strip() == local_head
    report_dir = _report_dir(completed.stdout)
    assert (report_dir / "same_path_overlap.txt").read_text(encoding="utf-8") == (
        "base.txt\n"
    )
    assert (report_dir / "conflict_paths.txt").read_text(encoding="utf-8") == (
        "base.txt\n"
    )
    assert "status\tconflict" in (report_dir / "summary.tsv").read_text(
        encoding="utf-8"
    )
    assert "merge_tree_mode\twrite-tree" in (
        report_dir / "summary.tsv"
    ).read_text(encoding="utf-8")
    assert "merge_tree_exit_code\t1" in (
        report_dir / "summary.tsv"
    ).read_text(encoding="utf-8")
    assert "no merge was attempted" in completed.stderr


def test_sync_reports_delete_modify_conflict_with_write_tree(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    assert _run("init", fixture["env"]).returncode == 0
    local_worktree = fixture["local_worktree"]
    _configure_identity(local_worktree)
    (local_worktree / "base.txt").unlink()
    _git(local_worktree, "add", "-A")
    _git(local_worktree, "commit", "-m", "server deletes base")
    _commit_file(
        fixture["seed"],
        "base.txt",
        "external version\n",
        "external modifies base",
    )
    _git(fixture["seed"], "push", "origin", "main")

    completed = _run("check", fixture["env"])

    assert completed.returncode == 2
    report_dir = _report_dir(completed.stdout)
    assert (report_dir / "conflict_paths.txt").read_text(encoding="utf-8") == (
        "base.txt\n"
    )


def test_sync_reports_binary_conflict_with_write_tree(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    assert _run("init", fixture["env"]).returncode == 0
    local_worktree = fixture["local_worktree"]
    _configure_identity(local_worktree)
    (local_worktree / "base.txt").write_bytes(b"\x00server")
    _git(local_worktree, "add", "base.txt")
    _git(local_worktree, "commit", "-m", "server binary change")
    (fixture["seed"] / "base.txt").write_bytes(b"\x00external")
    _git(fixture["seed"], "add", "base.txt")
    _git(fixture["seed"], "commit", "-m", "external binary change")
    _git(fixture["seed"], "push", "origin", "main")

    completed = _run("check", fixture["env"])

    assert completed.returncode == 2
    report_dir = _report_dir(completed.stdout)
    assert (report_dir / "conflict_paths.txt").read_text(encoding="utf-8") == (
        "base.txt\n"
    )


def test_check_reports_merge_tree_tool_failure_separately(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    assert _run("init", fixture["env"]).returncode == 0
    real_git = shutil.which("git")
    assert real_git is not None
    wrapper_dir = tmp_path / "bin"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / "git"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "for arg in \"$@\"; do\n"
        "  if [ \"${arg}\" = merge-tree ]; then\n"
        "    echo simulated-merge-tree-failure >&2\n"
        "    exit 129\n"
        "  fi\n"
        "done\n"
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    env = {
        **fixture["env"],
        "PATH": f"{wrapper_dir}{os.pathsep}{fixture['env']['PATH']}",
    }

    completed = _run("check", env)

    assert completed.returncode == 5
    report_dir = _report_dir(completed.stdout)
    summary = (report_dir / "summary.tsv").read_text(encoding="utf-8")
    assert "status\tcheck_error" in summary
    assert "merge_tree_exit_code\t129" in summary
    assert (report_dir / "conflict_paths.txt").read_text(encoding="utf-8") == ""


def test_sync_requires_review_for_clean_same_path_overlap(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    assert _run("init", fixture["env"]).returncode == 0
    local_worktree = fixture["local_worktree"]
    _configure_identity(local_worktree)
    _commit_file(
        local_worktree,
        "shared.txt",
        "server one\ntwo\nthree\nfour\n",
        "server overlap",
    )
    local_head = _git(local_worktree, "rev-parse", "HEAD").stdout.strip()
    _commit_file(
        fixture["seed"],
        "shared.txt",
        "one\ntwo\nthree\nexternal four\n",
        "external overlap",
    )
    _git(fixture["seed"], "push", "origin", "main")

    blocked = _run("sync", fixture["env"])

    assert blocked.returncode == 4
    assert _git(local_worktree, "rev-parse", "HEAD").stdout.strip() == local_head
    report_dir = _report_dir(blocked.stdout)
    assert "status\toverlap_review_required" in (
        report_dir / "summary.tsv"
    ).read_text(encoding="utf-8")
    assert "requires external developer review" in blocked.stderr

    approved_env = {
        **fixture["env"],
        "AK_SERVER_ALLOW_SAME_PATH_OVERLAP": "1",
    }
    approved = _run("sync", approved_env)

    assert approved.returncode == 0, approved.stderr
    assert (local_worktree / "shared.txt").read_text(encoding="utf-8") == (
        "server one\ntwo\nthree\nexternal four\n"
    )


def test_script_contains_no_push_and_rejects_main_as_local_branch(tmp_path: Path) -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "git push" not in text
    fixture = _fixture(tmp_path)
    env = {**fixture["env"], "AK_SERVER_LOCAL_BRANCH": "main"}

    completed = _run("init", env)

    assert completed.returncode == 1
    assert "must not be main or master" in completed.stderr

    invalid_overlap_env = {
        **fixture["env"],
        "AK_SERVER_ALLOW_SAME_PATH_OVERLAP": "always",
    }
    invalid_overlap = _run("init", invalid_overlap_env)
    assert invalid_overlap.returncode == 1
    assert "must be 0 or 1" in invalid_overlap.stderr
