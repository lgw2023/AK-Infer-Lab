"""Bootstrap hook copied as ``sitecustomize.py`` into an R3C overlay."""

from __future__ import annotations

import os


if os.environ.get("P6_3C_R3C_ADAPTIVE_ENABLED") == "1":
    try:
        from p6_3c_r3c_adaptive_scheduler import install_from_env

        install_from_env()
    except Exception as error:  # pragma: no cover - exercised on server
        # Do not silently change the scientific policy.  The mode runner's
        # self-test will fail closed if the server process cannot install the
        # controller; this breadcrumb is useful before the process exits.
        print(f"P6_3C_R3C_ADAPTIVE_BOOTSTRAP_ERROR={error!r}")
