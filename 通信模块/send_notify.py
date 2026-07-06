#!/usr/bin/env python3
"""
通过 163 邮箱从服务器向外部发送通知邮件。

本脚本用于本项目“开发机 <-> 服务器”通信链路：
- 服务器只能通过 SMTP 邮件向外发送状态、日志、告警等消息；
- 开发人员在开发机上通过收件箱获取服务器消息；
- 开发机写入本目录内的 Markdown/文本指令，服务器通过 git pull 获取。

安全说明：SMTP 账号、授权码、默认收件人通过环境变量配置，避免将密钥写入仓库。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import socket
import smtplib
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(env_path: Path) -> None:
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_value(value)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_env_file(PROJECT_ROOT / ".env")


SMTP_HOST = os.getenv("AK_COMM_SMTP_HOST", "smtp.163.com")
SMTP_PORT = int(os.getenv("AK_COMM_SMTP_PORT", "465"))
SMTP_USER = os.getenv("AK_COMM_SMTP_USER", "")
SMTP_PASSWORD = os.getenv("AK_COMM_SMTP_PASSWORD", "")
MAIL_FROM = os.getenv("AK_COMM_MAIL_FROM", SMTP_USER)
DEFAULT_MAIL_TO = os.getenv("AK_COMM_MAIL_TO", "")

USE_PROXYCHAINS_FOR_MAIL = os.getenv("AK_COMM_USE_PROXYCHAINS", "1") not in {"0", "false", "False", "no", "NO"}
PROXYCHAINS_BIN = os.getenv("AK_COMM_PROXYCHAINS_BIN", "proxychains4")
PROXYCHAINS_CONFIG = os.getenv("AK_COMM_PROXYCHAINS_CONFIG", "")
PAYLOAD_DIR = os.getenv("AK_COMM_PAYLOAD_DIR", "/tmp")
SCRIPT_PATH = os.path.abspath(__file__)
SHELL_PROXY_KEYS = ("AK_HTTP_PROXY", "AK_HTTPS_PROXY", "AK_FTP_PROXY", "AK_NO_PROXY")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def parse_mail_recipients(mail_to: str) -> list[str]:
    recipients = [x.strip() for x in mail_to.split(",") if x.strip()]
    if not recipients:
        raise ValueError("收件人不能为空；请设置 AK_COMM_MAIL_TO 或使用 -t/--to")
    return recipients


def redact_url_credentials(value: str) -> str:
    parts = urlsplit(value)
    if not parts.netloc or "@" not in parts.netloc:
        return value

    host_part = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((
        parts.scheme,
        f"<credentials>@{host_part}",
        parts.path,
        parts.query,
        parts.fragment,
    ))


def build_config_report(env: Mapping[str, str] | None = None) -> dict[str, object]:
    env = os.environ if env is None else env
    mail_to = env.get("AK_COMM_MAIL_TO", "")
    try:
        recipients = parse_mail_recipients(mail_to)
    except ValueError:
        recipients = []

    proxychains_bin = env.get("AK_COMM_PROXYCHAINS_BIN", "proxychains4")
    shell_proxy = {
        key: redact_url_credentials(env[key])
        for key in SHELL_PROXY_KEYS
        if key in env and env[key]
    }

    return {
        "project": {
            "root": str(PROJECT_ROOT),
            "script": SCRIPT_PATH,
            "env_file": str(PROJECT_ROOT / ".env"),
            "env_file_exists": (PROJECT_ROOT / ".env").is_file(),
        },
        "smtp": {
            "host": env.get("AK_COMM_SMTP_HOST", "smtp.163.com"),
            "port": env.get("AK_COMM_SMTP_PORT", "465"),
            "user": env.get("AK_COMM_SMTP_USER", ""),
            "from": env.get("AK_COMM_MAIL_FROM", env.get("AK_COMM_SMTP_USER", "")),
            "password_set": bool(env.get("AK_COMM_SMTP_PASSWORD", "")),
        },
        "mail": {
            "recipients": recipients,
            "raw": mail_to,
        },
        "proxychains": {
            "enabled": env.get("AK_COMM_USE_PROXYCHAINS", "1")
            not in {"0", "false", "False", "no", "NO"},
            "bin": proxychains_bin,
            "bin_path": shutil.which(proxychains_bin) or "",
            "config": env.get("AK_COMM_PROXYCHAINS_CONFIG", ""),
            "payload_dir": env.get("AK_COMM_PAYLOAD_DIR", "/tmp"),
        },
        "shell_proxy": shell_proxy,
    }


def require_mail_config() -> None:
    missing = []
    if not SMTP_USER:
        missing.append("AK_COMM_SMTP_USER")
    if not SMTP_PASSWORD:
        missing.append("AK_COMM_SMTP_PASSWORD")
    if not MAIL_FROM:
        missing.append("AK_COMM_MAIL_FROM 或 AK_COMM_SMTP_USER")
    if missing:
        raise ValueError("缺少邮件配置环境变量: " + ", ".join(missing))


def get_host_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        pass

    try:
        ips = subprocess.check_output(
            ["hostname", "-I"], text=True, timeout=5
        ).strip().split()
        if ips:
            return ips[0]
    except (OSError, subprocess.SubprocessError):
        pass

    return "unknown"


def _attach_file(msg: MIMEMultipart, file_path: Path) -> None:
    with file_path.open("rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        "attachment",
        filename=("utf-8", "", file_path.name),
    )
    msg.attach(part)


def build_message(
    subject: str,
    body: str,
    mail_to: str,
    attachment_paths: list[Path] | None = None,
) -> MIMEMultipart:
    require_mail_config()
    msg = MIMEMultipart()
    msg["From"] = MAIL_FROM
    msg["To"] = mail_to
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in attachment_paths or []:
        if not path.is_file():
            raise FileNotFoundError(f"附件不存在: {path}")
        _attach_file(msg, path)

    return msg


def _send_mail_direct(
    subject: str,
    body: str,
    mail_to: str,
    attachment_paths: list[Path] | None = None,
) -> None:
    recipients = parse_mail_recipients(mail_to)
    msg = build_message(subject, body, mail_to, attachment_paths)

    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(MAIL_FROM, recipients, msg.as_string())
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(MAIL_FROM, recipients, msg.as_string())


def build_proxychains_command(
    payload_path: str,
    proxychains_bin: str = PROXYCHAINS_BIN,
    script_path: str = SCRIPT_PATH,
    python_executable: str = sys.executable,
    proxychains_config: str = PROXYCHAINS_CONFIG,
) -> list[str]:
    cmd = [proxychains_bin]
    if proxychains_config:
        cmd.extend(["-f", proxychains_config])
    cmd.extend([
        python_executable,
        script_path,
        "--send-mail-internal",
        payload_path,
    ])
    return cmd


def _send_mail_via_proxychains(
    subject: str,
    body: str,
    mail_to: str,
    attachment_paths: list[Path] | None = None,
) -> None:
    payload = {
        "subject": subject,
        "body": body,
        "mail_to": mail_to,
        "attachments": [str(p) for p in (attachment_paths or [])],
    }
    payload_path = os.path.join(
        PAYLOAD_DIR,
        f"send_notify_payload_{os.getpid()}_{int(datetime.now().timestamp())}.json",
    )
    with open(payload_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    cmd = build_proxychains_command(payload_path)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            detail = stderr or stdout or f"exit code {result.returncode}"
            raise RuntimeError(f"proxychains 发信失败: {detail}")
    finally:
        try:
            os.remove(payload_path)
        except OSError:
            pass


def send_mail(
    subject: str,
    body: str,
    mail_to: str | None = None,
    attachment_paths: list[Path] | None = None,
    use_proxy: bool | None = None,
) -> None:
    if mail_to is None:
        mail_to = DEFAULT_MAIL_TO
    if use_proxy is None:
        use_proxy = USE_PROXYCHAINS_FOR_MAIL

    if use_proxy:
        logging.debug("Sending mail via %s", PROXYCHAINS_BIN)
        _send_mail_via_proxychains(subject, body, mail_to, attachment_paths)
    else:
        _send_mail_direct(subject, body, mail_to, attachment_paths)


def run_send_mail_internal(payload_path: str) -> None:
    try:
        with open(payload_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        attachments = [Path(p) for p in payload.get("attachments", [])]
        _send_mail_direct(
            payload["subject"],
            payload["body"],
            mail_to=payload["mail_to"],
            attachment_paths=attachments or None,
        )
    finally:
        try:
            os.remove(payload_path)
        except OSError:
            pass


def send_test_mail(mail_to: str, use_proxy: bool) -> None:
    hostname = socket.gethostname()
    host_ip = get_host_ip()
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    recipients = parse_mail_recipients(mail_to)

    subject = f"[服务器通知-邮件测试] {hostname}"
    body = "\n".join([
        "这是一封 send_notify.py 的邮件连通性测试，请忽略业务含义。",
        "",
        f"主机：{hostname}",
        f"IP：{host_ip}",
        f"时间：{now_text}",
        f"SMTP：{SMTP_HOST}:{SMTP_PORT}",
        f"发件人：{MAIL_FROM}",
        f"收件人：{', '.join(recipients)}",
        f"代理：{PROXYCHAINS_BIN if use_proxy else 'direct'}",
        "",
        "若收到本邮件，说明邮件发送功能正常。",
    ])

    via = PROXYCHAINS_BIN if use_proxy else "direct"
    logging.info("Sending test mail to %s via %s ...", ", ".join(recipients), via)
    send_mail(subject, body, mail_to=mail_to, use_proxy=use_proxy)
    logging.info("Test mail sent successfully")


def read_body(args: argparse.Namespace) -> str:
    if args.body is not None:
        return args.body
    if args.body_file is not None:
        path = Path(args.body_file)
        if not path.is_file():
            raise FileNotFoundError(f"正文文件不存在: {path}")
        return path.read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError("请通过 -b/--body、--body-file 或 stdin 提供邮件正文")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="通过 163 邮箱从服务器向外部发送通知邮件",
    )
    parser.add_argument("-s", "--subject", help="邮件主题")
    parser.add_argument("-b", "--body", help="邮件正文（纯文本）")
    parser.add_argument("--body-file", metavar="FILE", help="从文件读取邮件正文")
    parser.add_argument(
        "-t",
        "--to",
        default=DEFAULT_MAIL_TO,
        help="收件人，逗号分隔（默认读取 AK_COMM_MAIL_TO）",
    )
    parser.add_argument(
        "--attach",
        action="append",
        default=[],
        metavar="FILE",
        help="附加文件，可多次指定",
    )
    parser.add_argument("--test", action="store_true", help="发送测试邮件并退出")
    parser.add_argument("--no-proxy", action="store_true", help="不经 proxychains，直连 SMTP")
    parser.add_argument("--show-config", action="store_true", help="脱敏打印当前通信配置并退出")
    parser.add_argument("--send-mail-internal", metavar="PAYLOAD_FILE", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    use_proxy = False if args.no_proxy else USE_PROXYCHAINS_FOR_MAIL

    if args.send_mail_internal:
        try:
            run_send_mail_internal(args.send_mail_internal)
        except Exception:
            logging.exception("Internal mail send failed")
            return 1
        return 0

    if args.show_config:
        print(json.dumps(build_config_report(), ensure_ascii=False, indent=2))
        return 0

    if args.test:
        try:
            send_test_mail(args.to, use_proxy=use_proxy)
            print("测试邮件已发送，请查收收件箱（含垃圾邮件文件夹）。")
        except Exception as e:
            logging.exception("Test mail failed: %s", e)
            print(f"测试邮件发送失败：{e}", file=sys.stderr)
            return 1
        return 0

    if not args.subject:
        print("错误：除 --test 外必须指定 -s/--subject", file=sys.stderr)
        return 2

    try:
        body = read_body(args)
    except (ValueError, FileNotFoundError) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2

    attachments = [Path(p) for p in args.attach]
    try:
        send_mail(
            args.subject,
            body,
            mail_to=args.to,
            attachment_paths=attachments or None,
            use_proxy=use_proxy,
        )
    except Exception as e:
        logging.exception("Send mail failed: %s", e)
        print(f"邮件发送失败：{e}", file=sys.stderr)
        return 1

    recipients = parse_mail_recipients(args.to)
    if attachments:
        names = ", ".join(p.name for p in attachments)
        print(f"发送成功 -> {', '.join(recipients)}，已附加: {names}")
    else:
        print(f"发送成功 -> {', '.join(recipients)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
