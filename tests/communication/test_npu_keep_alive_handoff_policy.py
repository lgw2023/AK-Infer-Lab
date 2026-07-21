from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF = REPO_ROOT / "通信模块" / "docs" / "developer-to-server.md"
COMMUNICATION_README = REPO_ROOT / "通信模块" / "README.md"

STOP_COMMAND = "bash /data/node0_disk1/Public/npu_stop.sh 0 1 2 3 4 5 6 7"
RESTORE_COMMAND = (
    "bash /data/node0_disk1/Public/npu_keep_alive.sh 0 1 2 3 4 5 6 7"
)


def test_current_server_handoff_keeps_npu_stop_and_restore_policy() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert STOP_COMMAND in handoff
    assert RESTORE_COMMAND in handoff
    assert handoff.index(STOP_COMMAND) < handoff.index(RESTORE_COMMAND)
    assert "末尾数字是卡号" in handoff
    assert "实际停卡卡号、实际恢复卡号与恢复状态" in handoff


def test_communication_readme_keeps_policy_for_future_handoffs() -> None:
    readme = COMMUNICATION_README.read_text(encoding="utf-8")

    assert STOP_COMMAND in readme
    assert RESTORE_COMMAND in readme
    assert "每份 `docs/developer-to-server.md` 都必须" in readme
