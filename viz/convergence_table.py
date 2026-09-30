"""Extract per-cell convergence evidence from a pipeline runlog.

Mines ``results/logs/run_*.log`` for the linkage convergence trace and writes
``results/tables/convergence_evidence.csv`` with one row per cell run:
scenario id, iterations to convergence (or budget exhaustion), the
first-iteration L-∞ boundary change (the size of the price-feedback
signal), the final L-∞ change and the price-damping factor (W5.8). Feeds the
thesis appendix table.

Usage:
    python viz/convergence_table.py [logfile] [out_csv]
    # defaults: newest results/logs/run_*.log   results/tables/convergence_evidence.csv
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_RUNNING = re.compile(r"INFO (?:sturm_messageix|linkage)\.pipeline: Running (\S+)")
_ITER = re.compile(r"Iteration (\d+): L-inf (?:activity-bound|demand) change = ([0-9.eE+-]+)")
_CONV = re.compile(
    r"Linkage converged at iteration (\d+): L-inf (?:activity-bound|demand) change = ([0-9.eE+-]+)"
)
_OSC = re.compile(r"Iteration budget \((\d+)\) exhausted")
_ALPHA = re.compile(r"Price feedback damping alpha = ([0-9.eE+-]+)")


def parse(log: Path) -> list[dict[str, object]]:
    """One record per `Running <id>` block, in file order (repeats kept)."""
    rows: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if m := _RUNNING.search(line):
            current = {"scenario": m.group(1), "first_linf": None,
                       "iterations": None, "final_linf": None, "converged": False,
                       "price_damping": None}
            rows.append(current)
        elif current is not None and (m := _ALPHA.search(line)):
            current["price_damping"] = float(m.group(1))
        elif current is not None and (m := _ITER.search(line)):
            if current["first_linf"] is None:
                current["first_linf"] = float(m.group(2))
            current["iterations"] = int(m.group(1))
            current["final_linf"] = float(m.group(2))
        elif current is not None and (m := _CONV.search(line)):
            if current["first_linf"] is None:
                current["first_linf"] = float(m.group(2))
            current["iterations"] = int(m.group(1))
            current["final_linf"] = float(m.group(2))
            current["converged"] = True
        elif current is not None and _OSC.search(line):
            current["converged"] = False
    return rows


def main() -> None:
    import pandas as pd

    logs = sorted(Path("results/logs").glob("run_*.log"))
    log = Path(sys.argv[1]) if len(sys.argv) > 1 else (logs[-1] if logs else None)
    if log is None or not log.exists():
        raise SystemExit("No runlog found (results/logs/run_*.log)")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("results/tables/convergence_evidence.csv")

    rows = parse(log)
    if not rows:
        raise SystemExit(f"No cell runs found in {log}")
    df = pd.DataFrame(rows)
    # A cell may appear more than once in a log (re-runs); keep the last attempt.
    # tail(1), not .last(): GroupBy.last() is per-column NaN-skipping and could
    # stitch fields from two different attempts of the same scenario together.
    df = df.groupby("scenario", as_index=False).tail(1)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"wrote {out} from {log.name} ({len(df)} cells):")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
