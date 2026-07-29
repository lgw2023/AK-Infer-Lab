from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping
import urllib.request
from urllib.parse import urlsplit


LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_NO_PROXY_ENTRIES = ("127.0.0.1", "localhost", "::1")
PROXY_ENVIRONMENT_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def validate_loopback_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != LOOPBACK_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is None
    ):
        raise ValueError(
            "P6.3C local HTTP transport requires "
            "http://127.0.0.1:<port> with no credentials"
        )
    return url


def open_loopback(
    target: str | urllib.request.Request,
    *,
    timeout: float,
):
    url = target.full_url if isinstance(target, urllib.request.Request) else target
    validate_loopback_url(url)
    return _DIRECT_OPENER.open(target, timeout=timeout)


def _no_proxy_entries(value: str) -> set[str]:
    return {
        entry.strip()
        for entry in value.split(",")
        if entry.strip()
    }


def transport_contract(
    base_url: str,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    validate_loopback_url(base_url)
    env = os.environ if environment is None else environment
    upper_entries = _no_proxy_entries(env.get("NO_PROXY", ""))
    lower_entries = _no_proxy_entries(env.get("no_proxy", ""))
    required = set(LOOPBACK_NO_PROXY_ENTRIES)
    return {
        "contract_version": 1,
        "base_url": base_url.rstrip("/"),
        "loopback_host_required": LOOPBACK_HOST,
        "loopback_url_validated": True,
        "shell_curl_noproxy_all": True,
        "shell_curl_empty_proxy": True,
        "python_proxy_handler": "empty",
        "python_environment_proxy_lookup_allowed": False,
        "NO_PROXY_loopback_entries_complete": required <= upper_entries,
        "no_proxy_loopback_entries_complete": required <= lower_entries,
        "environment_proxy_variable_names_present": sorted(
            name for name in PROXY_ENVIRONMENT_NAMES if env.get(name)
        ),
        "environment_proxy_values_recorded": False,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write the credential-free P6.3C loopback transport contract."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-no-proxy-env", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    contract = transport_contract(args.base_url)
    if args.require_no_proxy_env and not (
        contract["NO_PROXY_loopback_entries_complete"]
        and contract["no_proxy_loopback_entries_complete"]
    ):
        raise ValueError(
            "both NO_PROXY and no_proxy must contain all loopback entries"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
