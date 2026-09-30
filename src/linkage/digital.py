"""Digitalization as an efficiency effect on the conversion technologies (r8).

Macko (2025) quantifies digitalization as *final-energy* savings at constant
useful energy (thesis §6.2, §6.6): the same heat delivered with less fuel. The
r7 design carried that signal as reduced heating *operating hours* in STURM —
a reduction of the heating service — which is a different physical mechanism
(thesis change specification CH-14; decided 2026-09-08, changelog §26).

The executed channel (the only one since the r8 prune):

* STURM runs the plain ``SSP2`` operating hours for every adoption level, so
  the useful demand handed to MESSAGEix is invariant to adoption;
* the Macko reduction ``r(y)`` — :data:`MACKO_CHANNEL`, re-based to 0 at the
  run base year and held flat after Macko's last year (provenance sheet row
  ``digitalization_efficiency_channel``) — scales the ``input`` coefficient
  (final energy per unit of useful output) of every STURM-covered
  ``rc_therm`` technology by ``1 − r(y)`` in each projection year
  (:func:`apply_digital_efficiency`);
* the baked ``CO2`` ``emission_factor`` on the combusting techs, which is
  ``ef_direct × input × 8.76`` per unit of activity (baseline changelog §7),
  is scaled by the same factor, so the endogenous emissions and the carbon
  tax respond consistently with the post-hoc ``ACT × input × EF`` accounting;
* the STURM→useful conversion keeps the *unmodified* coefficients, snapshotted
  by :func:`base_input_coefficients` before the scaling: the imposed demand is
  the calibrated service demand, not one inflated by the efficiency gain.

The signal therefore no longer moves the demand vector at all; it moves the
fuel each technology needs per unit of heat, which is what Macko's tables
measure. The ``"none"`` adoption level applies no scaling.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

import pandas as pd

from common.vocab import FUEL_TO_TECH
from linkage.targets import _fuel_commodity, _require_input_coef
from sturm.macko import load_reduction

if TYPE_CHECKING:
    from message_ix import Scenario

    from common.scenarios import Digitalization

log = logging.getLogger(__name__)

#: The Macko reduction series that carries the executed channel: residential
#: smart space heating (the only end use STURM models). Applied to the combined
#: residential+commercial ``rc_therm`` technologies — a documented
#: simplification (thesis ch. 3).
MACKO_CHANNEL: tuple[str, str] = ("Smart_space_heating", "Residential")

#: The conversion technologies whose ``input`` coefficient carries the
#: efficiency effect: every STURM-covered ``rc_therm`` technology. The
#: uncovered carriers (solar thermal, minor fuels) and ``sp_el_RC`` are
#: untouched, as in the r7 hours channel.
EFFICIENCY_TECHS: tuple[str, ...] = tuple(dict.fromkeys(FUEL_TO_TECH.values()))

#: Emission species carried by the baked buildings emission factors.
_CO2: str = "CO2"


def reduction_factors(
    digitalization: Digitalization, years: Sequence[int], *, base_year: int
) -> pd.Series:
    """Multiplicative efficiency factors ``1 − r'(y)`` per year for an adoption level.

    ``r'(y) = max(0, r(y) − r(base_year))`` re-bases Macko's 2020-normalised
    curve so the base year is unreduced (the observed base year already embeds
    the digitalization realised by then). Years beyond Macko's last year
    carry its last value (flat after 2040); years before
    the first entry carry no reduction. The ``"none"`` level returns all ones.

    Args:
        digitalization: Adoption level (selects the Macko scenario column).
        years: Model years to cover (any order; the result is sorted).
        base_year: Run base year at which the factor is exactly 1.

    Returns:
        Series of factors in ``(0, 1]`` indexed by year.
    """
    idx = sorted(int(y) for y in years)
    if digitalization.id == "none":
        return pd.Series(1.0, index=idx, name="efficiency_factor")
    tech, sector = MACKO_CHANNEL
    red = load_reduction(tech, sector)
    curve = (
        red.assign(year=red["Year"].astype(int))
        .set_index("year")[digitalization.macko_column]
        .astype(float)
        .sort_index()
    )
    at_base = float(curve.get(base_year, 0.0))
    rebased = (curve - at_base).clip(lower=0.0)
    last_year, last_val = int(rebased.index.max()), float(rebased.iloc[-1])
    out = {}
    for y in idx:
        if y in rebased.index:
            r = float(rebased[y])
        elif y > last_year:
            r = last_val
        else:
            r = 0.0
        out[y] = 1.0 - r
    return pd.Series(out, name="efficiency_factor")


def base_input_coefficients(
    scenario: Scenario, years: Sequence[int]
) -> dict[tuple[str, int], float]:
    """Snapshot the unmodified ``input`` coefficients used by the useful conversion.

    Keyed ``(STURM fuel, year)`` for every fuel in :data:`common.vocab.FUEL_TO_TECH`,
    exactly as :func:`linkage.targets.sturm_to_useful_demand` looks them up.
    Call **before** :func:`apply_digital_efficiency` and pass the result as its
    ``coefficients`` override, so the imposed useful demand stays the calibrated
    service demand.
    """
    return {
        (fuel, int(year)): _require_input_coef(
            scenario, FUEL_TO_TECH[fuel], _fuel_commodity(fuel), int(year)
        )
        for fuel in FUEL_TO_TECH
        for year in years
    }


def apply_digital_efficiency(
    scenario: Scenario,
    factors: Mapping[int, float] | pd.Series,
    *,
    techs: Sequence[str] = EFFICIENCY_TECHS,
    commit: str,
) -> pd.DataFrame:
    """Scale the ``input`` and ``CO2`` ``emission_factor`` of ``techs`` by ``factors``.

    Every ``input`` row of the technologies at ``level='final'`` whose
    ``year_act`` is in ``factors`` is multiplied by ``factors[year_act]`` (all
    vintages alike, so the same-vintage lookup of the conversion and the
    latest-vintage fallback see one consistent efficiency); every ``CO2``
    ``emission_factor`` row of the same technologies is multiplied by the same
    factor, keeping ``emission_factor == ef_direct × input × 8.76`` (the bake
    identity) true after the scaling. Years absent from ``factors`` are left
    untouched (the base year, whose factor is 1 anyway, and history).

    Applied once per fresh import of the baseline — :func:`linkage.pipeline.run_scenario`
    imports the workbook afresh for every cell, so the scaling never compounds.

    Args:
        scenario: The MESSAGEix-Austria scenario (checked out and committed here).
        factors: ``{year_act: factor}``; factors of 1.0 are skipped.
        techs: Technologies to scale; defaults to :data:`EFFICIENCY_TECHS`.
        commit: Commit message recorded on the scenario.

    Returns:
        The scaled ``input`` rows that were written (empty if nothing changed).
    """
    fac = {int(y): float(f) for y, f in dict(factors).items() if float(f) != 1.0}
    if not fac:
        log.info("Digital efficiency: no year carries a reduction; scenario unchanged")
        return pd.DataFrame()
    inp = scenario.par("input", {"technology": list(techs), "level": "final"})
    if inp.empty:
        raise ValueError(f"no 'input' rows for {list(techs)} at level 'final' to scale")
    inp = inp.assign(year_act=inp["year_act"].astype(int))
    sel = inp[inp["year_act"].isin(fac)].copy()
    sel["value"] = sel["value"].astype(float) * sel["year_act"].map(fac)

    ef = scenario.par("emission_factor", {"technology": list(techs), "emission": _CO2})
    if not ef.empty:
        ef = ef.assign(year_act=ef["year_act"].astype(int))
        ef = ef[ef["year_act"].isin(fac)].copy()
        ef["value"] = ef["value"].astype(float) * ef["year_act"].map(fac)

    scenario.check_out()
    try:
        scenario.add_par("input", sel)
        if not ef.empty:
            scenario.add_par("emission_factor", ef)
    except Exception:
        scenario.discard_changes()
        raise
    scenario.commit(commit)
    years = sorted(fac)
    log.info(
        "Digital efficiency: input coefficients of %d techs scaled over %d–%d "
        "(factor %.4f at %d); %d CO2 emission-factor rows scaled alike",
        len(techs), years[0], years[-1], fac[years[-1]], years[-1], len(ef),
    )
    return sel
