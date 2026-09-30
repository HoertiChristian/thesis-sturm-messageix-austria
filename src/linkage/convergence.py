"""Convergence metrics for the iterative linkage.

The stopping criterion is the L-infinity relative change in the STURM-derived
activity-bound vector handed across the boundary (per ``key``/``year``, where
``key`` is the end-use technology or the electric-heat relation). The metrics
themselves are generic over any aligned pair of :class:`pandas.Series`.
"""

from __future__ import annotations

from typing import NamedTuple

import pandas as pd


class ConvergenceStatus(NamedTuple):
    """The loop's result contract (2026-09-04, external-review adoption).

    Returned by :func:`linkage.loop.run` alongside the scenario and recorded in
    the run sidecar, so a result folder states on its face whether the cell
    converged, in how many solves, and at what residual — instead of that
    living only in the runlog.
    """

    converged: bool
    iterations: int
    final_linf: float | None
    oscillation_corrected: bool


def relative_changes(previous: pd.Series, current: pd.Series) -> pd.Series:
    """Return the per-entry relative changes between two activity-bound vectors.

    Robust to **hard zeros** in the vector: a pathway fossil exit pins some bounds
    to exactly ``0`` for the exit years, so a plain ``|Δ| / |previous|`` would divide
    by zero. A zero baseline that stays zero (``0 → 0``) is *converged* (change 0);
    a zero baseline that moves (``0 → x``) is a real change, scored relative to the
    vector's overall scale rather than as ``inf``. Entries with a non-zero baseline
    use the ordinary relative change.

    Args:
        previous: Activity bounds from the previous iteration, indexed comparably
            to ``current``.
        current: Activity bounds from the current iteration.

    Aligned over the **union** of the two indices (2026-09-04, external-review
    adoption): an entry that appears or disappears between iterations is a real
    boundary change and scores like a zero-baseline move — the previous inner
    join silently ignored exactly those entries. Duplicate index labels and
    non-finite values are rejected (a malformed boundary vector must fail the
    run, not converge by accident).

    Returns:
        ``|current - previous| / denom`` over the union-aligned index, where
        ``denom`` is ``|previous|`` for non-zero baselines and the vector scale
        for zero baselines; all-zero entries score ``0``.

    Raises:
        ValueError: On duplicate index labels or non-finite entries.
    """
    for name, s in (("previous", previous), ("current", current)):
        if not s.index.is_unique:
            raise ValueError(f"{name} boundary vector has duplicate index labels")
        if len(s) and not pd.Series(s.to_numpy()).map(pd.notna).all():
            raise ValueError(f"{name} boundary vector has non-finite entries")
        if len(s) and not pd.Series(s.to_numpy()).map(lambda v: abs(v) != float("inf")).all():
            raise ValueError(f"{name} boundary vector has non-finite entries")
    prev, curr = previous.align(current, join="outer")
    prev, curr = prev.fillna(0.0), curr.fillna(0.0)  # appear/disappear = move from/to 0
    if len(prev) == 0:
        return prev  # empty, same (lack of) index
    diff = (curr - prev).abs()
    denom = prev.abs()
    scale = max(float(denom.max()), float(curr.abs().max()))
    if scale == 0.0:  # both vectors all zero → fully converged
        return diff  # all zeros
    # Zero-baseline entries: compare against the vector scale instead of dividing
    # by zero (0 → 0 gives diff 0 → 0; 0 → x gives a finite x / scale).
    denom = denom.where(denom > 0, scale)
    return diff / denom


def top_changes(previous: pd.Series, current: pd.Series, n: int = 3) -> pd.Series:
    """Return the ``n`` largest per-entry relative changes (loop diagnostics).

    The entries driving :func:`linf_relative_change` — logged each iteration so a
    limit cycle's oscillating components (e.g. the W5.6 endogenous-DH swing) are
    readable straight from the server runlog.
    """
    return relative_changes(previous, current).nlargest(n)


def linf_relative_change(previous: pd.Series, current: pd.Series) -> float:
    """Return the L-infinity relative change between two activity-bound vectors.

    The maximum of :func:`relative_changes`, with the edge cases pinned: ``inf``
    if the indices do not overlap, ``0.0`` if both vectors are all zero.

    Args:
        previous: Activity bounds from the previous iteration, indexed comparably
            to ``current``.
        current: Activity bounds from the current iteration.

    Returns:
        ``max(|current - previous| / denom)`` over the aligned index (see
        :func:`relative_changes` for the denominators).
    """
    changes = relative_changes(previous, current)
    if len(changes) == 0:
        return float("inf")
    return float(changes.max())
