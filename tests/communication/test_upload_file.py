import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest


MODULE_PATH = Path("通信模块/upload_file.py")


def load_upload_file():
    module_name = "upload_file_under_test"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def upload_file_module():
    return load_upload_file()


@pytest.fixture
def config(upload_file_module, tmp_path):
    return upload_file_module.UploadConfig(
        url="https://upload.example.test/v1/files",
        token="FAKE_UPLOAD_TOKEN_SENTINEL",
        use_proxychains=True,
        proxychains_bin="proxychains4",
        proxychains_config="/etc/proxychains4.conf",
        curl_bin="curl",
        payload_dir=tmp_path,
        max_time=600,
    )


def test_config_report_redacts_token_and_resolves_proxy_settings(upload_file_module, tmp_path):
    env = {
        "AK_COMM_UPLOAD_URL": "https://upload.example.test/v1/files",
        "AK_COMM_UPLOAD_TOKEN": "FAKE_UPLOAD_TOKEN_SENTINEL",
        "AK_COMM_UPLOAD_USE_PROXYCHAINS": "1",
        "AK_COMM_PROXYCHAINS_BIN": "proxychains4",
        "AK_COMM_PROXYCHAINS_CONFIG": "/etc/proxychains4.conf",
        "AK_COMM_CURL_BIN": "curl",
        "AK_COMM_PAYLOAD_DIR": str(tmp_path),
        "AK_COMM_UPLOAD_MAX_TIME": "600",
    }

    report = upload_file_module.build_config_report(env, which=lambda name: f"/usr/bin/{name}")

    assert report["upload"]["url"] == "https://upload.example.test/v1/files"
    assert report["upload"]["token_set"] is True
    assert report["proxychains"]["enabled"] is True
    assert report["proxychains"]["config"] == "/etc/proxychains4.conf"
    assert report["limits"]["normal_max_bytes"] == 50_000_000
    assert report["limits"]["default_max_bytes"] == 100_000_000
    assert "FAKE_UPLOAD_TOKEN_SENTINEL" not in json.dumps(report)


def test_inspect_file_is_read_only_and_reports_hash_and_options(upload_file_module, tmp_path, monkeypatch):
    path = tmp_path / "result file.txt"
    path.write_bytes(b"hello upload")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("inspect must not launch a subprocess")

    monkeypatch.setattr(upload_file_module.subprocess, "run", fail_if_called)

    report = upload_file_module.inspect_file(path)

    assert report["path"] == str(path.resolve())
    assert report["size_bytes"] == 12
    assert report["size_class"] == "normal"
    assert report["sha256"] == "2d119f1cd272958a492a144af600b9dc36531f73027b34073967345b027021b1"
    assert report["candidate_methods"] == ["email", "upload-api", "server-local"]
    assert report["requires_user_confirmation"] is True


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (0, "normal"),
        (50_000_000, "normal"),
        (50_000_001, "warning"),
        (100_000_000, "warning"),
        (100_000_001, "oversize"),
    ],
)
def test_size_classification_boundaries(upload_file_module, size_bytes, expected):
    assert upload_file_module.classify_size(size_bytes) == expected


def test_upload_requires_exact_user_confirmed_method(upload_file_module, config, tmp_path, monkeypatch):
    path = tmp_path / "result.txt"
    path.write_text("result", encoding="utf-8")
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must stay closed")

    monkeypatch.setattr(upload_file_module.subprocess, "run", fail_if_called)

    with pytest.raises(upload_file_module.UploadError, match="用户明确选择 upload-api"):
        upload_file_module.upload_file(path, config, confirmed_method=None)
    with pytest.raises(upload_file_module.UploadError, match="用户明确选择 upload-api"):
        upload_file_module.upload_file(path, config, confirmed_method="email")

    assert called is False


def test_proxy_and_direct_commands_are_lists_without_token(upload_file_module, config, tmp_path):
    file_path = tmp_path / "result file.txt"
    header_path = tmp_path / "header"
    response_path = tmp_path / "response"

    proxied = upload_file_module.build_upload_command(
        file_path, header_path, response_path, config, use_proxy=True
    )
    direct = upload_file_module.build_upload_command(
        file_path, header_path, response_path, config, use_proxy=False
    )

    assert proxied[:3] == ["proxychains4", "-f", "/etc/proxychains4.conf"]
    assert direct[0] == "curl"
    assert "--header" in direct
    assert f"@{header_path}" in direct
    assert f"file=@{file_path}" in direct
    assert "FAKE_UPLOAD_TOKEN_SENTINEL" not in " ".join(proxied)
    assert "FAKE_UPLOAD_TOKEN_SENTINEL" not in " ".join(direct)


@pytest.mark.parametrize(
    ("config_change", "message"),
    [
        ({"url": "http://upload.example.test/v1/files"}, "有效的 HTTPS 地址"),
        ({"token": ""}, "缺少 AK_COMM_UPLOAD_TOKEN"),
        ({"token": "token\nInjected: value"}, "包含非法换行"),
    ],
)
def test_upload_config_rejects_insecure_or_missing_credentials(
    upload_file_module, config, tmp_path, monkeypatch, config_change, message
):
    path = tmp_path / "result.txt"
    path.write_text("result", encoding="utf-8")
    monkeypatch.setattr(upload_file_module, "require_executable", lambda name: f"/usr/bin/{name}")

    with pytest.raises(upload_file_module.UploadError, match=message):
        upload_file_module.upload_file(
            path,
            replace(config, **config_change),
            confirmed_method="upload-api",
        )


def test_oversize_upload_is_rejected_before_network(upload_file_module, config, tmp_path, monkeypatch):
    path = tmp_path / "large.bin"
    with path.open("wb") as handle:
        handle.truncate(100_000_001)
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must stay closed")

    monkeypatch.setattr(upload_file_module, "sha256_file", fail_if_called)
    monkeypatch.setattr(upload_file_module.subprocess, "run", fail_if_called)

    with pytest.raises(upload_file_module.UploadError, match="超过默认 100MB"):
        upload_file_module.upload_file(
            path,
            config,
            confirmed_method="upload-api",
            allow_over_100mb=False,
        )

    assert called is False


def test_success_requires_201_and_matching_sha_and_cleans_temp_files(
    upload_file_module, config, tmp_path, monkeypatch
):
    path = tmp_path / "result.txt"
    path.write_text("result", encoding="utf-8")
    expected_sha = upload_file_module.sha256_file(path)
    observed = {}

    monkeypatch.setattr(upload_file_module, "require_executable", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):
        observed["command"] = command
        header_path = Path(command[command.index("--header") + 1][1:])
        response_path = Path(command[command.index("--output") + 1])
        observed["header_path"] = header_path
        observed["response_path"] = response_path
        observed["header_mode"] = header_path.stat().st_mode & 0o777
        observed["response_mode"] = response_path.stat().st_mode & 0o777
        assert header_path.read_text(encoding="utf-8") == (
            "Authorization: Bearer FAKE_UPLOAD_TOKEN_SENTINEL\n"
        )
        response_path.write_text(
            json.dumps(
                {
                    "original_filename": "result.txt",
                    "stored_filename": "result.txt",
                    "saved_path": "/Volumes/SSD1/Inbox/2026-07-10/result.txt",
                    "sha256": expected_sha,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="201\t0.125", stderr="")

    result = upload_file_module.upload_file(
        path,
        config,
        confirmed_method="upload-api",
        runner=fake_run,
    )

    assert result["status"] == "success"
    assert result["http_status"] == 201
    assert result["local_sha256"] == expected_sha
    assert result["remote_sha256"] == expected_sha
    assert result["elapsed_seconds"] == 0.125
    assert observed["header_mode"] == 0o600
    assert observed["response_mode"] == 0o600
    assert "FAKE_UPLOAD_TOKEN_SENTINEL" not in " ".join(observed["command"])
    assert not observed["header_path"].exists()
    assert not observed["response_path"].exists()


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "上传凭据无效"),
        (409, "当天同名文件已存在"),
        (413, "大小限制"),
        (502, "上传服务或 Tunnel 暂不可用"),
        (530, "上传服务或 Tunnel 暂不可用"),
        (302, "重定向或代理告警"),
    ],
)
def test_http_errors_are_actionable_without_fallback(
    upload_file_module, config, tmp_path, monkeypatch, status, message
):
    path = tmp_path / "result.txt"
    path.write_text("result", encoding="utf-8")
    monkeypatch.setattr(upload_file_module, "require_executable", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):
        response_path = Path(command[command.index("--output") + 1])
        response_path.write_text("proxy or service response", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=f"{status}\t0.25", stderr="")

    with pytest.raises(upload_file_module.UploadError, match=message) as exc_info:
        upload_file_module.upload_file(
            path,
            config,
            confirmed_method="upload-api",
            runner=fake_run,
        )

    assert "自动" in str(exc_info.value) or "重新选择" in str(exc_info.value)


@pytest.mark.parametrize("failure", ["non_json", "sha_mismatch"])
def test_201_with_invalid_response_is_not_success(
    upload_file_module, config, tmp_path, monkeypatch, failure
):
    path = tmp_path / "result.txt"
    path.write_text("result", encoding="utf-8")
    expected_sha = upload_file_module.sha256_file(path)
    monkeypatch.setattr(upload_file_module, "require_executable", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):
        response_path = Path(command[command.index("--output") + 1])
        if failure == "non_json":
            response_path.write_text("<html>warning</html>", encoding="utf-8")
        else:
            response_path.write_text(
                json.dumps(
                    {
                        "original_filename": "result.txt",
                        "stored_filename": "result.txt",
                        "saved_path": "/tmp/result.txt",
                        "sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(command, 0, stdout="201\t0.25", stderr="")

    expected_message = "不是 JSON" if failure == "non_json" else "SHA-256 不一致"
    with pytest.raises(upload_file_module.UploadError, match=expected_message):
        upload_file_module.upload_file(
            path,
            config,
            confirmed_method="upload-api",
            runner=fake_run,
        )


def test_timeout_is_redacted_and_not_retried(upload_file_module, config, tmp_path, monkeypatch):
    path = tmp_path / "result.txt"
    path.write_text("result", encoding="utf-8")
    calls = 0
    monkeypatch.setattr(upload_file_module, "require_executable", lambda name: f"/usr/bin/{name}")

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired(command, timeout=kwargs["timeout"])

    with pytest.raises(upload_file_module.UploadError, match="上传超时") as exc_info:
        upload_file_module.upload_file(
            path,
            config,
            confirmed_method="upload-api",
            runner=fake_run,
        )

    assert calls == 1
    assert "FAKE_UPLOAD_TOKEN_SENTINEL" not in str(exc_info.value)


def test_preflight_uses_unique_local_file_and_cleans_it(upload_file_module, config, monkeypatch):
    observed_paths = []

    def fake_upload(path, passed_config, **kwargs):
        observed_paths.append(Path(path))
        assert Path(path).is_file()
        assert Path(path).name.startswith("ak_upload_preflight_")
        assert passed_config == config
        assert kwargs["confirmed_method"] == "upload-api"
        return {"status": "success", "original_filename": Path(path).name}

    monkeypatch.setattr(upload_file_module, "upload_file", fake_upload)

    first = upload_file_module.run_preflight(config, confirmed_method="upload-api")
    second = upload_file_module.run_preflight(config, confirmed_method="upload-api")

    assert first["original_filename"] != second["original_filename"]
    assert len(observed_paths) == 2
    assert all(not path.exists() for path in observed_paths)
