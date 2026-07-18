from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence


SCHEMA_VERSION = "ak_infer_lab_server_argv_v1"


def canonical_argv_bytes(argv: Sequence[str]) -> bytes:
    payload = {
        "argv": list(argv),
        "schema_version": SCHEMA_VERSION,
    }
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("server_argv", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    server_argv = args.server_argv
    if server_argv[:1] == ["--"]:
        server_argv = server_argv[1:]
    if not server_argv:
        raise SystemExit("server argv must not be empty")
    encoded = canonical_argv_bytes(server_argv)
    if args.output is not None:
        args.output.write_bytes(encoded)
    print(hashlib.sha256(encoded).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
