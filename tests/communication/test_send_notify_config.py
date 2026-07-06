import importlib.util
from pathlib import Path


MODULE_PATH = Path("通信模块/send_notify.py")


def load_send_notify(monkeypatch, mail_to="yilili1023@gmail.com"):
    defaults = {
        "AK_COMM_SMTP_HOST": "smtp.163.com",
        "AK_COMM_SMTP_PORT": "465",
        "AK_COMM_SMTP_USER": "sender@example.com",
        "AK_COMM_SMTP_PASSWORD": "dummy-secret",
        "AK_COMM_MAIL_FROM": "sender@example.com",
        "AK_COMM_USE_PROXYCHAINS": "1",
        "AK_COMM_PROXYCHAINS_BIN": "proxychains4",
        "AK_COMM_PAYLOAD_DIR": "/tmp",
    }
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)
    if mail_to is None:
        monkeypatch.delenv("AK_COMM_MAIL_TO", raising=False)
    else:
        monkeypatch.setenv("AK_COMM_MAIL_TO", mail_to)

    spec = importlib.util.spec_from_file_location("send_notify_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_mail_recipient_is_yilili_only(monkeypatch):
    send_notify = load_send_notify(monkeypatch, mail_to=None)

    assert send_notify.DEFAULT_MAIL_TO == "yilili1023@gmail.com"
    assert send_notify.parse_mail_recipients(send_notify.DEFAULT_MAIL_TO) == [
        "yilili1023@gmail.com"
    ]
    assert send_notify.build_config_report()["mail"]["recipients"] == [
        "yilili1023@gmail.com"
    ]


def test_redact_url_credentials_masks_proxy_account_and_password(monkeypatch):
    send_notify = load_send_notify(monkeypatch)

    redacted = send_notify.redact_url_credentials(
        "http://proxy_user:proxy_password@proxysg.huawei.com:8080/"
    )

    assert redacted == "http://<credentials>@proxysg.huawei.com:8080/"
    assert "proxy_user" not in redacted
    assert "proxy_password" not in redacted


def test_build_config_report_uses_booleans_and_redacted_proxy_urls(monkeypatch):
    send_notify = load_send_notify(monkeypatch)
    env = {
        "AK_COMM_SMTP_HOST": "smtp.163.com",
        "AK_COMM_SMTP_PORT": "465",
        "AK_COMM_SMTP_USER": "17621223203@163.com",
        "AK_COMM_SMTP_PASSWORD": "smtp-auth-code",
        "AK_COMM_MAIL_FROM": "17621223203@163.com",
        "AK_COMM_MAIL_TO": "yilili1023@gmail.com",
        "AK_COMM_USE_PROXYCHAINS": "1",
        "AK_COMM_PROXYCHAINS_BIN": "proxychains4",
        "AK_COMM_PROXYCHAINS_CONFIG": "/etc/proxychains4.conf",
        "AK_COMM_PAYLOAD_DIR": "/tmp",
        "AK_HTTP_PROXY": "http://proxy_user:proxy_password@proxysg.huawei.com:8080/",
        "AK_HTTPS_PROXY": "http://proxy_user:proxy_password@proxysg.huawei.com:8080/",
        "AK_NO_PROXY": "localhost,127.0.0.1,::1,*.huawei.com,*.huaweicloud.com",
    }

    report = send_notify.build_config_report(env=env)

    assert report["smtp"]["password_set"] is True
    assert "password" not in report["smtp"]
    assert report["mail"]["recipients"] == ["yilili1023@gmail.com"]
    assert report["proxychains"]["config"] == "/etc/proxychains4.conf"
    assert report["shell_proxy"]["AK_HTTP_PROXY"] == (
        "http://<credentials>@proxysg.huawei.com:8080/"
    )
    assert "smtp-auth-code" not in str(report)
    assert "proxy_password" not in str(report)


def test_proxychains_command_includes_optional_config_file(monkeypatch):
    send_notify = load_send_notify(monkeypatch)

    command = send_notify.build_proxychains_command(
        payload_path="/tmp/payload.json",
        proxychains_bin="proxychains4",
        script_path="/repo/通信模块/send_notify.py",
        python_executable="/usr/bin/python3",
        proxychains_config="/etc/proxychains4.conf",
    )

    assert command == [
        "proxychains4",
        "-f",
        "/etc/proxychains4.conf",
        "/usr/bin/python3",
        "/repo/通信模块/send_notify.py",
        "--send-mail-internal",
        "/tmp/payload.json",
    ]
