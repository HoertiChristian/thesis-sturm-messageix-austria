"""Tee all run logs to a file, so a server run is reviewable without the notebook.

Downloading the executed ``.ipynb`` is unreliable; calling :func:`start` once at the
top of a run writes every INFO log — the linkage convergence trace, the
``Could not export …`` warnings, and the STURM per-run summary
(:func:`sturm.driver.run_offline`) — to a plain ``.log`` file under
``results/logs/`` that is trivial to download or ``cat``.

It does not capture the GAMS/CPLEX solver banner (that is printed by the GAMS
subprocess, not via Python logging); for that, export the notebook to HTML.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from common import paths

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def start(path: Path | None = None, *, level: int = logging.INFO) -> Path:
    """Attach a file handler to the root logger and return the log path.

    Idempotent for a given ``path`` (re-calling will not add a duplicate handler).

    Args:
        path: Log file to write; defaults to
            ``results/logs/run_<UTC-timestamp>.log``.
        level: Root log level to enforce (so library INFO lines are captured).

    Returns:
        The path being written to.
    """
    if path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = paths.RESULTS / "logs" / f"run_{ts}.log"
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    already = any(
        getattr(h, "_runlog", None) == str(path) for h in root.handlers
    )
    if not already:
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler._runlog = str(path)  # type: ignore[attr-defined]
        root.addHandler(handler)
    logging.getLogger(__name__).info("Run log started -> %s", path)
    return path
