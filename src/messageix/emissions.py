"""CO₂ reporting for solved scenarios.

The MESSAGEix-Austria baseline accounts emissions *upstream* (only a ``TCE`` —
tonnes carbon-equivalent — species, on ~15 supply technologies; the buildings
end-use techs carry no emission factor). So the RQ1 buildings-sector CO₂ cannot be
read from the model's emission variable; it is computed post-hoc from the buildings
final energy by fuel × per-fuel emission factors (:func:`buildings_co2`). The
model's native whole-economy carbon is exposed separately as :func:`system_co2`.

Two factor sets live in the ``emission_factors`` sheet of ``data/inputs.xlsx``,
both from the Umweltbundesamt report **REP-0989** "Harmonisierte österreichische
direkte und vorgelagerte THG-Emissionsfaktoren" (*Datenstand 2025*, Wien 2025;
Tabelle 1 Raumwärme p. 9, Tabelle 4 Strom p. 12; CO₂eq, GWP-100; adopted
2026-08-25, superseding REP-0948 — all territorial/direct values identical,
only the consumption-basis electr/d_heat totals moved):

* ``ef_direct`` — the table's **direct** (on-site combustion) column. This is the
  *territorial* basis: it matches the UNFCCC inventory buildings sector (CRF 1.A.4),
  so district heat and electricity are 0 (their emissions sit in energy industries,
  1.A.1) and biogenic CO₂ from biomass is 0 (its 0.015 is CH₄/N₂O; coal has no UBA
  residential-Raumwärme value → IPCC 2006 bituminous, immaterial at coal_rc ≈ 0.003
  GWa). Directly comparable to the 2040 NEKP buildings targets (REP-0995: WAM 1,300
  / WEM 3,400 kt CO₂eq) — the RQ1 headline.
* ``ef_total`` — the **total** (direct + upstream/Vorkette) column, including the
  emissions attributable to delivered district heat (Fernwärme Durchschnitt
  Österreich) and electricity (Stromaufbringung Österreich). A
  *consumption/attributional* basis used as a sensitivity, so that electrification
  (heat pumps, digitalization) shows its electricity-side cost rather than scoring
  0. NOT comparable to the territorial NEKP target.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from common.vocab import NODE
from messageix.report import buildings_final_energy_by_fuel

if TYPE_CHECKING:
    from message_ix import Scenario

from common.units import MWH_PER_GWA


def emission_factors(basis: str = "direct") -> dict[str, float]:
    """Per-fuel CO₂eq factors (tCO₂eq/MWh) for ``basis`` ∈ ``{"direct", "total"}``.

    Read from the ``emission_factors`` sheet of ``data/inputs.xlsx`` — the single
    source of truth (UBA REP-0989; basis semantics in the module docstring).
    ``direct`` is the territorial basis; ``total`` the consumption basis. A missing
    workbook or sheet raises.
    """
    from common import workbook

    df = workbook.emission_factors()
    col = {"direct": "ef_direct", "total": "ef_total"}[basis]
    return {str(f): float(v) for f, v in zip(df["fuel"], df[col], strict=False)}


def buildings_co2(
    scenario: Scenario,
    technologies: list[str] | tuple[str, ...],
    factors: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Buildings-sector CO₂eq from end-use final energy by fuel (RQ1 metric).

    Computed from :func:`messageix.buildings_final_energy_by_fuel` ×
    per-fuel emission factors. With the default (the workbook's direct factors,
    ``emission_factors("direct")`` — territorial basis) it is directly comparable
    to the 2040 buildings targets (REP-0995: WAM 1,300 / WEM 3,400 kt CO₂eq);
    pass ``emission_factors("total")`` for the consumption-basis sensitivity.

    Args:
        scenario: A solved MESSAGEix-Austria scenario.
        technologies: The rc end-use technologies.
        factors: tCO₂eq/MWh per fuel; defaults to ``emission_factors("direct")``.

    Returns:
        Long frame with ``year`` and ``value`` (kt CO₂eq).
    """
    # The invariant "by-fuel sums to the total" is structural: this IS the
    # by-fuel frame summed (one arithmetic site, cannot drift).
    by_fuel = buildings_co2_by_fuel(scenario, technologies, factors)
    if by_fuel.empty:
        return pd.DataFrame(columns=["year", "value"])
    return (
        by_fuel.groupby("year", as_index=False)["value"]
        .sum()
        .sort_values("year")
        .reset_index(drop=True)
    )


def buildings_co2_by_fuel(
    scenario: Scenario,
    technologies: list[str] | tuple[str, ...],
    factors: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Buildings-sector CO₂eq broken down **by fuel** — the per-fuel detail behind
    :func:`buildings_co2`.

    Identical arithmetic to :func:`buildings_co2` (final energy by fuel × per-fuel
    factor), but grouped by ``(year, fuel)`` rather than summed over fuels, so a figure
    can show which carriers carry the territorial emissions (gas, heating oil, coal,
    biomass) and which sit at 0 — district heat and electricity, whose emissions are
    accounted in energy industries (CRF 1.A.1), not buildings. Summing ``value`` over
    ``fuel`` reproduces :func:`buildings_co2` exactly.

    Args:
        scenario: A solved MESSAGEix-Austria scenario.
        technologies: The rc end-use technologies.
        factors: tCO₂eq/MWh per fuel; defaults to ``emission_factors("direct")``.

    Returns:
        Long frame with ``year``, ``fuel`` and ``value`` (kt CO₂eq).
    """
    factors = factors if factors is not None else emission_factors("direct")
    fe = buildings_final_energy_by_fuel(scenario, technologies)
    if fe.empty:
        return pd.DataFrame(columns=["year", "fuel", "value"])
    fe = fe.copy()
    # GWa × (tCO₂/MWh) × (MWh/GWa) = tCO₂; /1000 → kt CO₂eq.
    fe["value"] = fe["fuel"].map(factors).fillna(0.0) * fe["value"] * (MWH_PER_GWA / 1000.0)
    return (
        fe.groupby(["year", "fuel"], as_index=False)["value"]
        .sum()
        .sort_values(["year", "fuel"])
        .reset_index(drop=True)
    )


def buildings_co2_endogenous(scenario: Scenario, emission: str = "CO2") -> pd.DataFrame:
    """Buildings-sector CO₂ solved **in-model** (MtCO₂), from the ``CO2`` emission_factor.

    Only the buildings rc techs carry a ``CO2`` ``emission_factor`` (baked into
    the baseline workbook — ``docs/data/baseline_4_changelog.md``), so ``EMISS`` for the
    ``CO2`` species *is* the buildings sector — no per-technology filtering needed. The
    value is already MtCO₂ (activity GWa × factor tCO₂/kWa), so no ``×44/12`` conversion
    (unlike :func:`system_co2`, whose ``TCE`` species is tonnes of *carbon*).

    Returns an empty frame when the scenario carries no ``CO2`` ``EMISS`` — i.e. the
    emission bake has not been applied (restore the baked baseline workbook from the repository).

    Args:
        scenario: A solved MESSAGEix-Austria scenario.
        emission: Emission species; defaults to ``"CO2"``.

    Returns:
        Long frame with ``year`` and ``value`` (MtCO₂eq, territorial basis).
    """
    return _emiss_by_year(scenario, emission)


def emission_price(scenario: Scenario, type_emission: str = "GHG") -> pd.DataFrame:
    """Carbon price by year — the ``PRICE_EMISSION`` dual (USD/tCO₂).

    Non-empty only when the pathway imposed a ``tax_emission`` or ``bound_emission`` on
    the ``GHG`` type (see :func:`messageix.pathways.apply_pathway`); for an
    unpriced/uncapped scenario ``PRICE_EMISSION`` is absent and this returns empty.

    Args:
        scenario: A solved MESSAGEix-Austria scenario.
        type_emission: Emission type whose dual to read; defaults to ``"GHG"``.

    Returns:
        Long frame with ``year`` and ``value`` (USD/tCO₂).
    """
    df = scenario.var("PRICE_EMISSION")
    if df.empty:
        return pd.DataFrame(columns=["year", "value"])
    if "type_emission" in df.columns:
        df = df[df["type_emission"] == type_emission]
    if df.empty:
        return pd.DataFrame(columns=["year", "value"])
    return (
        df.groupby("year", as_index=False)["lvl"]
        .mean()
        .rename(columns={"lvl": "value"})
        .sort_values("year")
        .reset_index(drop=True)
    )


def system_co2(scenario: Scenario, emission: str = "TCE") -> pd.DataFrame:
    """System-wide CO₂eq from the model's native carbon accounting (context, not RQ1).

    Sums ``EMISS`` over technologies and converts tC → tCO₂ (× 44/12). It is
    *whole-economy*, not buildings-specific — use :func:`buildings_co2` for RQ1.

    Args:
        scenario: A solved MESSAGEix-Austria scenario.
        emission: Emission species; defaults to ``"TCE"`` (the only one populated).

    Returns:
        Long frame with ``year`` and ``value`` (CO₂eq in the model's mass unit).
    """
    return _emiss_by_year(scenario, emission, scale=44.0 / 12.0)


def _emiss_by_year(scenario: Scenario, emission: str, scale: float = 1.0) -> pd.DataFrame:
    """``EMISS`` for one species, per year, model node only, optionally scaled.

    The shared body of :func:`buildings_co2_endogenous` (scale 1 — the baked
    factors already yield MtCO₂) and :func:`system_co2` (×44/12 — ``TCE`` is
    tonnes of carbon). ``EMISS`` is reported for the model node AND its parent
    aggregate (World); summing both exactly doubles the sector, so only the
    model node is kept.
    """
    df = scenario.var("EMISS", {"emission": emission})
    if df.empty:
        return pd.DataFrame(columns=["year", "value"])
    df = df[df["node"] == NODE]
    return (
        df.groupby("year", as_index=False)["lvl"]
        .sum()
        .assign(value=lambda d: d["lvl"] * scale)
        .drop(columns="lvl")
        .sort_values("year")
        .reset_index(drop=True)
    )
