"""Energy/activity reporting for solved MESSAGEix-Austria scenarios.

Thin wrappers over the model's own ``var`` / ``par`` retrieval API. The keys
assumed here (``ACT``, ``output``/``input``, ``final`` level) match the
MESSAGEix-Austria baseline; a diverging scenario would need them adjusted.
CO₂ reporting lives in :mod:`messageix.emissions`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from message_ix import Scenario


def final_energy_by_fuel(scenario: Scenario) -> pd.DataFrame:
    """Return system final energy by fuel commodity for a solved scenario.

    Activity (``ACT``) is multiplied by the corresponding ``output`` coefficient
    at ``level='final'`` and summed across technology, vintage, mode and
    sub-annual time, yielding ``(year, commodity, value)``.

    Args:
        scenario: A solved MESSAGEix-Austria scenario.

    Returns:
        Long-format frame with ``year``, ``commodity`` and ``value`` (in the
        commodity's own unit, typically GWa).
    """
    coef = scenario.par("output", {"level": "final"})
    return _act_times_coef(scenario, coef, value_col="commodity")


def buildings_final_energy_by_fuel(
    scenario: Scenario, technologies: list[str] | tuple[str, ...]
) -> pd.DataFrame:
    """Final energy *consumed* by the given end-use techs, by input fuel.

    Unlike :func:`final_energy_by_fuel` (which sums what technologies *produce* at
    ``level='final'``), this sums what the buildings end-use technologies *consume*:
    ``ACT × input`` coefficient at ``level='final'``, grouped by the input commodity.
    That makes it directly comparable to the Statistik Austria buildings reference
    (:func:`common.reference.reference_by_fuel`).

    Args:
        scenario: A solved MESSAGEix-Austria scenario.
        technologies: The rc end-use technologies (e.g.
            :data:`common.vocab.RC_END_USE_TECHS`).

    Returns:
        Long frame with ``year``, ``fuel`` (input commodity) and ``value`` (GWa).
    """
    coef = scenario.par("input", {"technology": list(technologies), "level": "final"})
    return _act_times_coef(scenario, coef, value_col="fuel")


def _act_times_coef(
    scenario: Scenario, coef: pd.DataFrame, *, value_col: str
) -> pd.DataFrame:
    """``ACT × coefficient`` summed per ``(year, commodity)`` — the shared pipeline.

    The body of :func:`final_energy_by_fuel` (produced energy, ``output`` rows)
    and :func:`buildings_final_energy_by_fuel` (consumed energy, ``input`` rows).
    The activity pull covers exactly the techs present in ``coef``, and the
    merge is inner, so pre-filtering ``ACT`` further would not change the result.
    """
    if coef.empty:
        return pd.DataFrame(columns=["year", value_col, "value"])
    act = scenario.var("ACT", {"technology": coef["technology"].unique().tolist()})
    join = ["node_loc", "technology", "year_vtg", "year_act", "mode", "time"]
    merged = act.merge(
        coef[[*join, "commodity", "value"]].rename(columns={"value": "coef"}),
        on=join,
        how="inner",
    )
    merged["final_energy"] = merged["lvl"] * merged["coef"]
    return (
        merged.groupby(["year_act", "commodity"], as_index=False)["final_energy"]
        .sum()
        .rename(columns={"year_act": "year", "commodity": value_col, "final_energy": "value"})
        .sort_values(["year", value_col])
        .reset_index(drop=True)
    )


def activity_by_tech(
    scenario: Scenario, technologies: list[str] | tuple[str, ...]
) -> pd.DataFrame:
    """Return realised activity (``ACT``) per technology, for bound-vs-actual checks.

    Sums ``ACT`` over vintage, mode and sub-annual time, so the result is directly
    comparable to the ``bound_activity_{up,lo}`` corridor written by
    :mod:`linkage.bounds` (which is keyed on ``year_act``).

    Args:
        scenario: A solved MESSAGEix-Austria scenario.
        technologies: Technologies to report (e.g.
            :data:`common.vocab.RC_END_USE_TECHS`).

    Returns:
        Long-format frame with ``year``, ``technology`` and ``value`` (GWa).
    """
    act = scenario.var("ACT", {"technology": list(technologies)})
    if act.empty:
        return pd.DataFrame(columns=["year", "technology", "value"])
    return (
        act.groupby(["year_act", "technology"], as_index=False)["lvl"]
        .sum()
        .rename(columns={"year_act": "year", "lvl": "value"})
        .sort_values(["year", "technology"])
        .reset_index(drop=True)
    )
