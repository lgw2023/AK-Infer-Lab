#!/usr/bin/env python3
"""Upload one complete result bundle after the user selects upload-api."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


NORMAL_MAX_BYTES = 50_000_000
DEFAULT_MAX_BYTES = 100_000_000
DEFAULT_UPLOAD_URL = "https://upload.ultrahardcore.net/v1/files"
CONFIRMED_METHOD = "upload-api"
CANDIDATE_METHODS = ["email", "upload-api", "server-local"]


class UploadError(RuntimeError):
    """A safe, user-facing upload failure."""


class ConfirmationError(UploadError):
    """The upload API was not explicitly selected by the user."""


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
        if key and key not in os.environ:
            os.environ[key] = _strip_env_value(value)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_env_file(PROJECT_ROOT / ".env")


def parse_bool(value: str) -> bool:
    return value not in {"0", "false", "False", "no", "NO"}


def parse_positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise UploadError(f"{name} 必须是正整数") from exc
    if parsed <= 0:
        raise UploadError(f"{name} 必须是正整数")
    return parsed


@dataclass(frozen=True)
class UploadConfig:
    url: str
    token: str = field(repr=False)
    use_proxychains: bool
    proxychains_bin: str
    proxychains_config: str
    curl_bin: str
    payload_dir: Path
    max_time: int


def get_config(env: Mapping[str, str] | None = None) -> UploadConfig:
    env = os.environ if env is None else env
    upload_proxy_default = env.get("AK_COMM_USE_PROXYCHAINS", "1")
    return UploadConfig(
        url=env.get("AK_COMM_UPLOAD_URL", DEFAULT_UPLOAD_URL).strip(),
        token=env.get("AK_COMM_UPLOAD_TOKEN", "").strip(),
        use_proxychains=parse_bool(
            env.get("AK_COMM_UPLOAD_USE_PROXYCHAINS", upload_proxy_default)
        ),
        proxychains_bin=env.get("AK_COMM_PROXYCHAINS_BIN", "proxychains4").strip(),
        proxychains_config=env.get("AK_COMM_PROXYCHAINS_CONFIG", "").strip(),
        curl_bin=env.get("AK_COMM_CURL_BIN", "curl").strip(),
        payload_dir=Path(env.get("AK_COMM_PAYLOAD_DIR", "/tmp")).expanduser(),
        max_time=parse_positive_int(
            env.get("AK_COMM_UPLOAD_MAX_TIME", "600"),
            "AK_COMM_UPLOAD_MAX_TIME",
        ),
    )


def build_config_report(
    env: Mapping[str, str] | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    config = get_config(env)
    return {
        "project": {
            "root": str(PROJECT_ROOT),
            "script": str(Path(__file__).resolve()),
            "env_file": str(PROJECT_ROOT / ".env"),
            "env_file_exists": (PROJECT_ROOT / ".env").is_file(),
        },
        "upload": {
            "url": config.url,
            "token_set": bool(config.token),
            "curl_bin": config.curl_bin,
            "curl_path": which(config.curl_bin) or "",
            "max_time_seconds": config.max_time,
        },
        "proxychains": {
            "enabled": config.use_proxychains,
            "bin": config.proxychains_bin,
            "bin_path": which(config.proxychains_bin) or "",
            "config": config.proxychains_config,
            "payload_dir": str(config.payload_dir),
        },
        "limits": {
            "unit": "decimal_bytes",
            "normal_max_bytes": NORMAL_MAX_BYTES,
            "default_max_bytes": DEFAULT_MAX_BYTES,
        },
        "confirmation": {
            "required": True,
            "exact_method": CONFIRMED_METHOD,
        },
    }


def require_executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise UploadError(f"找不到可执行文件: {name}")
    return path


def require_confirmation(confirmed_method: str | None) -> None:
    if confirmed_method != CONFIRMED_METHOD:
        raise ConfirmationError(
            "未记录用户明确选择 upload-api；不得上传或自动切换传输方式"
        )


def require_upload_config(config: UploadConfig, use_proxy: bool) -> None:
    if not config.url:
        raise UploadError("缺少 AK_COMM_UPLOAD_URL")
    url_parts = urlsplit(config.url)
    if url_parts.scheme != "https" or not url_parts.netloc:
        raise UploadError("AK_COMM_UPLOAD_URL 必须是有效的 HTTPS 地址")
    if not config.token:
        raise UploadError("缺少 AK_COMM_UPLOAD_TOKEN；真实密钥只能保存在服务器本地 .env")
    if "\r" in config.token or "\n" in config.token:
        raise UploadError("AK_COMM_UPLOAD_TOKEN 包含非法换行")
    if not config.payload_dir.is_dir():
        raise UploadError(f"临时目录不存在: {config.payload_dir}")
    require_executable(config.curl_bin)
    if use_proxy:
        require_executable(config.proxychains_bin)


def resolve_file(file_path: str | Path) -> Path:
    path = Path(file_path).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise UploadError(f"文件不存在: {path}") from exc
    if not resolved.is_file():
        raise UploadError(f"不是普通文件: {resolved}")
    if not os.access(resolved, os.R_OK):
        raise UploadError(f"文件不可读: {resolved}")
    return resolved


def sha256_file(file_path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_size(size_bytes: int) -> str:
    if size_bytes <= NORMAL_MAX_BYTES:
        return "normal"
    if size_bytes <= DEFAULT_MAX_BYTES:
        return "warning"
    return "oversize"


def inspect_file(file_path: str | Path) -> dict[str, object]:
    path = resolve_file(file_path)
    size_bytes = path.stat().st_size
    return build_file_report(path, size_bytes)


def build_file_report(path: Path, size_bytes: int) -> dict[str, object]:
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / 1_000_000, 6),
        "size_class": classify_size(size_bytes),
        "sha256": sha256_file(path),
        "candidate_methods": list(CANDIDATE_METHODS),
        "requires_user_confirmation": True,
        "sensitivity": "must-be-decided-by-user",
    }


def validate_session_name(session_name: str) -> str:
    normalized = unicodedata.normalize("NFC", session_name).strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or "/" in normalized
        or "\\" in normalized
        or any(unicodedata.category(char) == "Cc" for char in normalized)
        or len(normalized.encode("utf-8")) > 200
    ):
        raise UploadError("session_name 无效")
    return normalized


def build_upload_command(
    file_paths: Sequence[Path],
    session_name: str,
    header_path: Path,
    response_path: Path,
    config: UploadConfig,
    *,
    use_proxy: bool,
) -> list[str]:
    command: list[str] = []
    if use_proxy:
        command.append(config.proxychains_bin)
        if config.proxychains_config:
            command.extend(["-f", config.proxychains_config])

    command.extend(
        [
            config.curl_bin,
            "--silent",
            "--show-error",
            "--output",
            str(response_path),
            "--write-out",
            "%{http_code}\t%{time_total}",
            "--max-time",
            str(config.max_time),
            "--request",
            "POST",
            config.url,
            "--header",
            f"@{header_path}",
            "--form",
            f"session_name={session_name}",
        ]
    )
    for file_path in file_paths:
        command.extend(["--form", f"file=@{file_path}"])
    return command


def redact_secret(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "<redacted>")


def parse_curl_metrics(stdout: str) -> tuple[int, float]:
    parts = stdout.strip().split("\t")
    if len(parts) != 2:
        raise UploadError("curl 未返回可解析的 HTTP 状态和耗时")
    try:
        return int(parts[0]), float(parts[1])
    except ValueError as exc:
        raise UploadError("curl 返回的 HTTP 状态或耗时无效") from exc


def http_error_message(status: int) -> str:
    if status == 401:
        detail = "上传凭据无效或服务器本地配置未同步"
    elif status == 409:
        detail = "当天同名结果会话已存在或结果包内文件名冲突；是否改名后重传必须由用户决定"
    elif status == 413:
        detail = "触发上传服务或 Cloudflare 大小限制"
    elif status in {502, 530}:
        detail = "上传服务或 Tunnel 暂不可用"
    elif 300 <= status < 400:
        detail = "出现非预期重定向或代理告警"
    else:
        detail = "上传服务返回非成功状态"
    return (
        f"HTTP {status}: {detail}；不会自动切换通道，"
        "请在当前任务会话报告并重新等待用户选择"
    )


def _read_response_json(response_path: Path, token: str) -> dict[str, Any]:
    raw = response_path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        excerpt = redact_secret(raw[:240].replace("\n", " "), token)
        raise UploadError(f"HTTP 201 但响应不是 JSON；响应摘要: {excerpt}") from exc
    if not isinstance(payload, dict):
        raise UploadError("HTTP 201 但响应 JSON 不是对象")
    return payload


def _execute_upload(
    file_paths: Sequence[str | Path],
    session_name: str,
    config: UploadConfig,
    *,
    use_proxy: bool | None,
    allow_over_100mb: bool,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None,
) -> dict[str, object]:
    if not file_paths:
        raise UploadError("结果包至少需要一个正文或附件文件")
    normalized_session_name = validate_session_name(session_name)
    paths = [resolve_file(path) for path in file_paths]
    sizes = [path.stat().st_size for path in paths]
    total_size_bytes = sum(sizes)
    oversize_paths = [
        str(path)
        for path, size_bytes in zip(paths, sizes, strict=True)
        if classify_size(size_bytes) == "oversize"
    ]
    if (oversize_paths or total_size_bytes > DEFAULT_MAX_BYTES) and not allow_over_100mb:
        raise UploadError(
            "单文件或结果包总大小超过默认 100MB 上传保护；请让用户重新选择 server-local，"
            "或明确接受 413 风险后使用 --allow-over-100mb"
        )
    reports = [
        build_file_report(path, size_bytes)
        for path, size_bytes in zip(paths, sizes, strict=True)
    ]

    actual_use_proxy = config.use_proxychains if use_proxy is None else use_proxy
    require_upload_config(config, actual_use_proxy)
    actual_runner = subprocess.run if runner is None else runner

    header_path: Path | None = None
    response_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="ak_upload_header_",
            dir=config.payload_dir,
            delete=False,
        ) as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(f"Authorization: Bearer {config.token}\n")
            header_path = Path(handle.name)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="ak_upload_response_",
            dir=config.payload_dir,
            delete=False,
        ) as handle:
            os.fchmod(handle.fileno(), 0o600)
            response_path = Path(handle.name)

        command = build_upload_command(
            paths,
            normalized_session_name,
            header_path,
            response_path,
            config,
            use_proxy=actual_use_proxy,
        )
        try:
            completed = actual_runner(
                command,
                capture_output=True,
                text=True,
                timeout=config.max_time + 30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise UploadError(
                f"上传超时（{config.max_time} 秒限制）；不会自动重试或切换通道"
            ) from exc

        if completed.returncode != 0:
            detail = redact_secret(
                (completed.stderr or completed.stdout or "").strip()[:500],
                config.token,
            )
            if not detail:
                detail = f"exit code {completed.returncode}"
            raise UploadError(
                f"curl 上传失败: {detail}；不会自动重试或切换通道"
            )

        http_status, elapsed_seconds = parse_curl_metrics(completed.stdout)
        if http_status != 201:
            raise UploadError(http_error_message(http_status))

        response = _read_response_json(response_path, config.token)
        required_fields = {"session_name", "saved_directory", "files"}
        missing_fields = sorted(required_fields - response.keys())
        if missing_fields:
            raise UploadError(
                "HTTP 201 响应缺少字段: " + ", ".join(missing_fields)
            )
        if response["session_name"] != normalized_session_name:
            raise UploadError(
                "HTTP 201 但 session_name 不一致: "
                f"local={normalized_session_name}, remote={response['session_name']}"
            )
        remote_files = response["files"]
        if not isinstance(remote_files, list) or len(remote_files) != len(reports):
            raise UploadError(
                "HTTP 201 但 files 数量与本地结果包不一致: "
                f"local={len(reports)}, remote="
                f"{len(remote_files) if isinstance(remote_files, list) else 'invalid'}"
            )

        verified_files = []
        for path, report, remote_file in zip(paths, reports, remote_files, strict=True):
            if not isinstance(remote_file, dict):
                raise UploadError("HTTP 201 但 files 项不是对象")
            file_fields = {
                "original_filename",
                "stored_filename",
                "saved_path",
                "sha256",
            }
            missing_file_fields = sorted(file_fields - remote_file.keys())
            if missing_file_fields:
                raise UploadError(
                    "HTTP 201 的 files 项缺少字段: "
                    + ", ".join(missing_file_fields)
                )
            if remote_file["original_filename"] != path.name:
                raise UploadError(
                    "HTTP 201 但原始文件名不一致: "
                    f"local={path.name}, remote={remote_file['original_filename']}"
                )
            remote_sha = str(remote_file["sha256"]).lower()
            local_sha = str(report["sha256"]).lower()
            if remote_sha != local_sha:
                raise UploadError(
                    f"HTTP 201 但 SHA-256 不一致: file={path.name}, "
                    f"local={local_sha}, remote={remote_sha}"
                )
            verified_files.append(
                {
                    "original_filename": remote_file["original_filename"],
                    "stored_filename": remote_file["stored_filename"],
                    "saved_path": remote_file["saved_path"],
                    "size_bytes": report["size_bytes"],
                    "size_class": report["size_class"],
                    "local_sha256": local_sha,
                    "remote_sha256": remote_sha,
                }
            )

        return {
            "status": "success",
            "http_status": http_status,
            "session_name": normalized_session_name,
            "saved_directory": response["saved_directory"],
            "file_count": len(verified_files),
            "total_size_bytes": total_size_bytes,
            "files": verified_files,
            "elapsed_seconds": elapsed_seconds,
            "method": CONFIRMED_METHOD,
            "used_proxychains": actual_use_proxy,
        }
    finally:
        for temp_path in (header_path, response_path):
            if temp_path is None:
                continue
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def upload_files(
    file_paths: Sequence[str | Path],
    session_name: str,
    config: UploadConfig,
    *,
    confirmed_method: str | None,
    use_proxy: bool | None = None,
    allow_over_100mb: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, object]:
    require_confirmation(confirmed_method)
    return _execute_upload(
        file_paths,
        session_name,
        config,
        use_proxy=use_proxy,
        allow_over_100mb=allow_over_100mb,
        runner=runner,
    )


def upload_file(
    file_path: str | Path,
    config: UploadConfig,
    *,
    session_name: str,
    confirmed_method: str | None,
    use_proxy: bool | None = None,
    allow_over_100mb: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, object]:
    return upload_files(
        [file_path],
        session_name,
        config,
        confirmed_method=confirmed_method,
        use_proxy=use_proxy,
        allow_over_100mb=allow_over_100mb,
        runner=runner,
    )


def run_preflight(
    config: UploadConfig,
    *,
    confirmed_method: str | None,
    use_proxy: bool | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, object]:
    require_confirmation(confirmed_method)
    descriptor, raw_path = tempfile.mkstemp(
        prefix="ak_upload_preflight_",
        suffix=".txt",
        dir=config.payload_dir,
    )
    path = Path(raw_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("AK-Infer-Lab upload preflight\n")
        session_name = f"ak-upload-preflight-{uuid.uuid4().hex}"
        return upload_files(
            [path],
            session_name,
            config,
            confirmed_method=confirmed_method,
            use_proxy=use_proxy,
            runner=runner,
        )
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="经用户明确选择后，通过上传 API 一次性交付完整结果包",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", metavar="FILE", help="只读检查文件，不访问网络")
    mode.add_argument(
        "--upload",
        action="append",
        metavar="FILE",
        help="结果包文件，可重复指定；第一个应为 result_summary.md",
    )
    mode.add_argument("--preflight", action="store_true", help="上传唯一命名的小文件预检")
    mode.add_argument("--show-config", action="store_true", help="脱敏显示配置")
    parser.add_argument(
        "--confirmed-method",
        help="必须精确填写 upload-api，表示用户已针对当前完整结果包选择该方式",
    )
    parser.add_argument(
        "--session-name",
        help="upload API 会话目录名；上传结果包时必填且当天唯一",
    )
    parser.add_argument("--no-proxy", action="store_true", help="绕过 proxychains 直连")
    parser.add_argument(
        "--allow-over-100mb",
        action="store_true",
        help="用户知悉 413 风险后解除本地 100MB 保护",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        transfer_requested = bool(args.upload or args.preflight)
        if args.upload and not args.session_name:
            raise UploadError("--upload 必须同时提供 --session-name")
        if args.session_name and not args.upload:
            raise UploadError("--session-name 只能与 --upload 同时使用")
        if args.allow_over_100mb and not args.upload:
            raise UploadError("--allow-over-100mb 只能与 --upload 同时使用")
        if args.no_proxy and not transfer_requested:
            raise UploadError("--no-proxy 只能与 --upload 或 --preflight 同时使用")
        if args.confirmed_method and not transfer_requested:
            raise UploadError(
                "--confirmed-method 只能与 --upload 或 --preflight 同时使用"
            )

        if args.show_config:
            result = build_config_report()
        elif args.inspect:
            result = inspect_file(args.inspect)
        else:
            config = get_config()
            use_proxy = False if args.no_proxy else None
            if args.preflight:
                result = run_preflight(
                    config,
                    confirmed_method=args.confirmed_method,
                    use_proxy=use_proxy,
                )
            else:
                result = upload_files(
                    args.upload,
                    args.session_name,
                    config,
                    confirmed_method=args.confirmed_method,
                    use_proxy=use_proxy,
                    allow_over_100mb=args.allow_over_100mb,
                )
    except ConfirmationError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except (UploadError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
