"""Bootstrap the R3D controller from a task-local runtime overlay."""

from __future__ import annotations

import os


if (
    os.environ.get("P6_3C_R3D_ADAPTIVE_ENABLED") == "1"
    or os.environ.get("P6_3C_R3C_ADAPTIVE_ENABLED") == "1"
):
    try:
        from p6_3c_r3d_persistent_scheduler import install_from_env

        install_from_env()
    except Exception as error:  # pragma: no cover - server-only bootstrap
        print(f"P6_3C_R3D_ADAPTIVE_BOOTSTRAP_ERROR={error!r}")
