"""Apply climate-neutrality pathway constraints to a MESSAGEix-Austria scenario.

Each pathway (see the ``pathways`` sheet of ``data/inputs.xlsx``) is a set of qualitative dials —
``fossil_exit_year``, ``bioenergy_share_target_2040``, the carbon-price
dials and the supply-side dials. The buildings-side dials act through the
once-per-cell static anchor of the useful-energy coupling:
:func:`useful_bound_sides` selects which techs are cap-only / floor-only and
:func:`constrain_targets` ramps the flat anchor rows
(:func:`linkage.targets.useful_anchor_targets`,
:func:`linkage.bounds.apply_useful_anchor`). The mapping:

================================  ============================================
Dial                              Effect on the anchor rows
================================  ============================================
``fossil_exit_year = Y``          Cap the fossil end-use techs to **0 along a
                                  fuel-specific schedule**: ``Y`` is the *gas*
                                  operating-ban year, while ``loil_rc``/``coal_rc``
                                  lead it by :func:`_fossil_exit_lead` years
                                  (e.g. ``Y = 2040`` ⇒ gas 2040, oil/coal 2035).
                                  The ban years follow the Austrian CLIM/COMP
                                  net-zero scenarios of Kettner et al. (2026) —
                                  oil heating banned 2035, gas 2040. The decline
                                  to each fuel's ban year is a **logistic**
                                  (S-shaped) substitution curve by default, the
                                  canonical diffusion form (Grübler 1997, Wilson
                                  2012) and the mirror of the adoption S-curve;
                                  ``linear`` is available as the sensitivity-branch
                                  comparator. Applied as an *upper cap only*
                                  (:func:`useful_bound_sides`) so the phase-out
                                  cannot force an oversupply infeasibility.
``bioenergy_share_target_2040``   ``low``: hold ``biomass_rc`` flat at its
                                  base-year level (it may not expand to absorb the
                                  fossil exit). ``high``: floor it at base level.
================================  ============================================

The Reference pathway leaves the buildings dials unset (it carries the
carbon-price path). (The former ``electrification_intensity`` dial was removed
2026-09-04: a structural no-op — the fuel mix is free by construction.)
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import pandas as pd

from common.scenarios import Pathway
from common.units import TWH_PER_GWA
from common.vocab import (
    FUEL_TO_TECH,
    MODE,
    NODE,
    TIME,
    UNCOVERED_RC_TECHS,
    UNIT,
)
from messageix.ixmp_utils import ensure_units, has_co2

if TYPE_CHECKING:
    from message_ix import Scenario

log = logging.getLogger(__name__)


def _constants() -> dict[str, object]:
    """The ``pathway_constants`` sheet of ``data/inputs.xlsx``, read once per process."""
    from common import workbook

    return workbook.pathway_constant_items()


#: STURM fuels whose end-use technology is phased out by a ``fossil_exit_year``.
#: District heat (``d_heat``) decarbonises upstream and biomass is bioenergy, so
#: neither is a direct-combustion fossil end-use here.
_FOSSIL_FUELS: tuple[str, ...] = ("gas", "coal", "lightoil")

#: The buildings end-use technologies a fossil exit zeroes out.
_FOSSIL_TECHS: tuple[str, ...] = tuple(FUEL_TO_TECH[f] for f in _FOSSIL_FUELS)

#: The end-use technology a ``bioenergy_share_target_2040`` dial governs.
_BIOENERGY_TECH: str = FUEL_TO_TECH["biomass"]


def _fossil_exit_lead() -> dict[str, int]:
    """Years each fossil end-use tech's ban *leads* the pathway ``fossil_exit_year``.

    The exit year is read as the final/gas exit. Grounded in the Austrian CLIM/COMP
    net-zero scenarios of Kettner et al. (2026): oil heating operating-ban 2035, gas
    2040 — a 5-year lead. Coal (≈0 in the calibrated Austrian base) is retired with
    oil. So ``fossil_exit_year = 2040`` ⇒ gas 2040, oil/coal 2035. Values live in the
    ``pathway_constants`` sheet as ``fossil_exit_lead.<tech>`` keys.
    """
    prefix = "fossil_exit_lead."
    return {
        key.removeprefix(prefix): int(val)  # type: ignore[call-overload]
        for key, val in _constants().items()
        if key.startswith(prefix)
    }


#: Default phase-out shape. ``logistic`` is the canonical technology-substitution
#: form (Grübler 1997, Wilson 2012) and mirrors the adoption S-curve used for
#: digitalization; ``linear`` is the sensitivity-branch comparator. At runtime the
#: shape comes from ``Config.fossil_exit_shape`` (loop.run passes it); this module
#: default is only the fallback for direct callers and tests.
_DEFAULT_EXIT_SHAPE: str = "logistic"


def _logistic_k() -> float:
    """Logistic steepness of the fossil-exit S-curve.

    Sets the curvature only — the curve is affine-rescaled to hit exactly 1.0 at
    the base year and 0.0 at the ban year regardless of ``k``.
    """
    return float(_constants()["logistic_k"])  # type: ignore[arg-type]


def _has_activity_dials(pathway: Pathway) -> bool:
    """Whether ``pathway`` carries an *activity-target* dial (applied in the linkage)."""
    return (
        pathway.fossil_exit_year is not None
        or pathway.bioenergy_share_target_2040 is not None
    )


def _has_carbon_policy(pathway: Pathway) -> bool:
    """Whether ``pathway`` imposes a carbon tax/path or budget (applied on the scenario)."""
    return (
        pathway.carbon_price is not None
        or pathway.carbon_price_path is not None
        or pathway.emission_budget is not None
    )


def _resolve_carbon_prices(pathway: Pathway, model_years: list[int]) -> dict[int, float]:
    """Per-model-year carbon tax (USD/tCO₂) from the pathway's flat price or path.

    A flat ``carbon_price`` covers every model year. A ``carbon_price_path``
    (r7 B2 — the legislated NEHG/ETS2 path on the Reference) resolves via
    :func:`common.workbook.carbon_price_path`: path years map directly, years
    between/after path years carry the latest path value at or before them
    (step-wise, matching how legislated prices hold until amended), and model
    years before the first path year are untaxed. Flat and path together are a
    configuration error (fail loud rather than guess precedence).
    """
    if pathway.carbon_price is not None and pathway.carbon_price_path is not None:
        raise ValueError(
            f"pathway {pathway.id!r} sets both carbon_price and carbon_price_path — "
            "use exactly one"
        )
    if pathway.carbon_price is not None:
        return {y: float(pathway.carbon_price) for y in model_years}
    from common import workbook

    path = workbook.carbon_price_path(str(pathway.carbon_price_path))
    path_years = sorted(path)
    out: dict[int, float] = {}
    for y in model_years:
        at_or_before = [py for py in path_years if py <= y]
        if at_or_before:
            out[y] = path[at_or_before[-1]]
    return out


def _has_supply_dials(pathway: Pathway) -> bool:
    """Whether ``pathway`` carries power-sector dials (applied on the scenario)."""
    return (
        pathway.renewable_expansion is not None
        or pathway.fossil_power_exit_year is not None
    )


#: EAG (Erneuerbaren-Ausbau-Gesetz, BGBl. I 150/2021, §4) 2030 expansion targets,
#: **additional generation vs 2020** — the law's own unit is TWh/yr, which maps
#: 1:1 onto activity floors for the *expansion* resource-grade techs (the
#: pre-2020 fleet lives in the separate ``*_res_hist_*`` vintages, whose 2020
#: activity matches observed Austrian generation: solar 0.233 GWa ≈ 2.0 TWh,
#: wind 0.775 GWa ≈ 6.8 TWh). Hydro (+5 TWh) is not imposed — the baseline caps
#: hydro capacity at its built-out level; biomass (+1 TWh) is minor and left to
#: the model. ``eag_continued`` extends the 2020→2030 build rates linearly to
#: 2040, consistent with the NEKP/REP-0951 climate-neutrality narrative.
#:
#: **The EAG wind target (+10 TWh) is NOT imposed** — empirically proven
#: infeasible in the received baseline (2026-07-05 probes: even +5 TWh by 2030
#: yields "Model has been proven infeasible"). The baseline's VRE-integration
#: layer (``wind_step1–3`` → ``wind_res_cv``) leaves only ``wind_cv1``/``cv2``
#: operable, capping absorbable wind at ≈ 0.122·elec_t_d ≈ 0.89 GWa ≈ 7.8 TWh —
#: roughly Austria's 2020 generation and *below its actual 2024 level*, i.e. a
#: downscaling artifact of the global integration parameterisation, not an
#: Austrian resource limit. Documented in the provenance note as a limitation
#: (the pathway under-delivers the EAG total for a model-structural reason);
#: the solar path was verified feasible at every level.
def _eag_twh_additional() -> dict[str, dict[str, dict[int, float]]]:
    """The ``renewable_floors`` sheet as ``{expansion_level: {family: {year: TWh}}}``."""
    from common import workbook

    out: dict[str, dict[str, dict[int, float]]] = {}
    for row in workbook.renewable_floors().itertuples():
        out.setdefault(str(row.expansion_level), {}).setdefault(str(row.family), {})[
            int(row.year)
        ] = float(row.twh_additional)
    return out

#: The expansion resource-grade technologies the renewable floors aggregate over
#: (the actual electricity producers; ``solar_pv_ppl``/``wind_ppl`` exist in the
#: technology set but have no ``output`` rows in this baseline — vestigial).
_RENEWABLE_GRADES: dict[str, tuple[str, ...]] = {
    "solar": tuple(f"solar_res{i}" for i in range(1, 9)),
    "wind": tuple(f"wind_res{i}" for i in range(1, 5)),
}

#: Relation names for the aggregate renewable-expansion floors.
_RENEWABLE_RELATIONS: dict[str, str] = {"solar": "eag_solar", "wind": "eag_wind"}

#: Fossil power plants capped to zero from 2030 under a ``fossil_power_exit_year``
#: (Austria's last coal plant closed 2020; oil power is marginal — the caps are
#: hygiene against re-entry). Advanced coal variants included to block substitution.
_FOSSIL_POWER_ZERO: tuple[str, ...] = ("coal_ppl", "coal_adv", "igcc", "foil_ppl", "loil_ppl")

#: Gas power declines to a flexibility residual (fraction of its 2020
#: ``historical_activity``) at the exit year — gas plants persist as balancing
#: capacity in the NEKP/REP-0951 WAM narrative rather than exiting entirely.
#: ``gas_ct`` (the open-cycle peaker) is deliberately exempt: it carries the
#: largest operating-reserve coefficient in the baseline's VRE-integration layer
#: (``oper_res``: gas_ct 1.0 vs gas_cc 0.4) while supplying only ~2.5% of gas
#: power energy — capping it starves the reserves the renewable floors need.
_GAS_POWER_TECHS: tuple[str, ...] = ("gas_cc", "gas_ppl")


def _gas_power_residual() -> float:
    """Fraction of 2020 gas-power activity retained as flexibility residual."""
    return float(_constants()["gas_power_residual"])  # type: ignore[arg-type]


def _has_binding_dials(pathway: Pathway) -> bool:
    """Whether ``pathway`` carries constraints beyond the unconstrained baseline.

    The Reference pathway (``NEKP-current``) leaves every dial unset and runs at
    baseline electrification — it *is* the scenario as received — so it needs no
    constraint application. Pathways with a forced fossil exit, a bioenergy-share
    target, a carbon policy, or
    supply-side power dials do.
    """
    return (
        _has_activity_dials(pathway)
        or _has_carbon_policy(pathway)
        or _has_supply_dials(pathway)
    )


def apply_pathway(scenario: Scenario, pathway: Pathway) -> None:
    """Apply a pathway's *scenario-level* (non-activity) constraints.

    The activity dials (``fossil_exit_year``, ``bioenergy_share_target_2040``)
    bound the buildings fuel mix and are applied through the static anchor
    (see :func:`useful_bound_sides` / :func:`constrain_targets`), not here —
    the anchor's hygiene reset would overwrite them. What *does* belong
    here is the **carbon policy** (``carbon_price`` / ``emission_budget``): a
    ``tax_emission`` / ``bound_emission`` on the ``GHG`` type is year-independent and
    not an activity bound, so it persists across the loop's solves.

    Args:
        scenario: The MESSAGEix-Austria scenario.
        pathway: The pathway whose dials apply.
    """
    if _has_activity_dials(pathway):
        log.info(
            "Pathway %s: activity dials applied as target transforms in the linkage.",
            pathway.id,
        )
    if _has_carbon_policy(pathway):
        _apply_carbon_policy(scenario, pathway)
    elif scenario is not None:
        # Batch hygiene: cells share one ixmp scenario (pipeline.run_scenarios), so
        # a previous pathway's tax/bound must not leak into this one.
        _clear_carbon_policy(scenario)
    if _has_supply_dials(pathway):
        _apply_supply_dials(scenario, pathway)
    elif scenario is not None:
        _clear_supply_dials(scenario)
    if not _has_binding_dials(pathway):
        log.info("Pathway %s has no binding constraints (baseline); no-op.", pathway.id)


def _apply_carbon_policy(scenario: Scenario, pathway: Pathway) -> None:
    """Impose ``pathway``'s carbon tax / budget on the scenario's ``GHG`` emission type.

    A flat ``carbon_price`` (USD/tCO₂) becomes a ``tax_emission`` on every model
    year; a ``carbon_price_path`` becomes per-year ``tax_emission`` rows (step-wise
    carry-forward — see :func:`_resolve_carbon_prices`); an ``emission_budget``
    (MtCO₂) becomes a cumulative ``bound_emission``. All target
    ``type_emission="GHG"``, ``type_tec="all"`` (the standard message_ix idiom). A no-op
    with a clear warning if the baseline has no ``CO2`` species — the carbon levers need
    the emission bake in the baseline workbook to bite.
    """
    if not has_co2(scenario):
        log.warning(
            "Pathway %s sets a carbon policy but the baseline has no CO2 emission_factor; "
            "restore the baked workbook from the repository (docs/data/baseline_4_changelog.md). "
            "Skipping carbon policy.",
            pathway.id,
        )
        return

    model_years = [
        int(y) for y in scenario.set("year") if int(y) >= int(scenario.firstmodelyear)
    ]
    ensure_units(scenario, ("USD/tCO2", "MtCO2"))

    # Cells share one scenario across a batch: ixmp's check_out() raises on a
    # solved scenario, and a previous cell's carbon policy must not carry over.
    if scenario.has_solution():
        scenario.remove_solution()
    scenario.check_out()
    for par in ("tax_emission", "bound_emission"):
        old = scenario.par(par)
        if not old.empty:
            scenario.remove_par(par, old)
    if "GHG" not in {str(t) for t in scenario.set("type_emission")}:
        scenario.add_cat("emission", "GHG", "CO2")
    new_ty = [str(y) for y in model_years if str(y) not in {str(t) for t in scenario.set("type_year")}]
    if new_ty:
        scenario.add_set("type_year", new_ty)

    if pathway.carbon_price is not None or pathway.carbon_price_path is not None:
        prices = _resolve_carbon_prices(pathway, model_years)
        if prices:
            scenario.add_par(
                "tax_emission",
                pd.DataFrame({
                    "node": NODE, "type_emission": "GHG", "type_tec": "all",
                    "type_year": list(prices), "value": list(prices.values()),
                    "unit": "USD/tCO2",
                }),
            )
            span = (min(prices.values()), max(prices.values()))
            log.info(
                "Pathway %s: carbon tax %s on %d model years (%.1f–%.1f USD/tCO2)",
                pathway.id,
                pathway.carbon_price_path or f"flat {pathway.carbon_price:.1f}",
                len(prices), span[0], span[1],
            )
    if pathway.emission_budget is not None:
        scenario.add_par(
            "bound_emission",
            pd.DataFrame({
                "node": [NODE], "type_emission": ["GHG"], "type_tec": ["all"],
                "type_year": ["cumulative"], "value": [float(pathway.emission_budget)],
                "unit": ["MtCO2"],
            }),
        )
        log.info("Pathway %s: cumulative emission budget %.1f MtCO2",
                 pathway.id, pathway.emission_budget)
    scenario.commit(f"carbon policy for pathway {pathway.id}")


def _clear_carbon_policy(scenario: Scenario) -> None:
    """Remove any leftover ``tax_emission``/``bound_emission`` from a shared scenario.

    ``pipeline.run_scenarios`` reuses one ixmp scenario across all matrix cells;
    without this, a carbon-pricing cell would silently tax every later cell. A
    no-op (no check-out) when the scenario carries no carbon policy.
    """
    leftovers = {
        par: scenario.par(par)
        for par in ("tax_emission", "bound_emission")
        if not scenario.par(par).empty
    }
    if not leftovers:
        return
    log.info("Clearing leftover carbon policy from a previous cell: %s", sorted(leftovers))
    if scenario.has_solution():
        scenario.remove_solution()
    scenario.check_out()
    for par, old in leftovers.items():
        scenario.remove_par(par, old)
    scenario.commit("sturm-messageix: clear leftover carbon policy")


def _supply_years(scenario: Scenario) -> list[int]:
    """Model years the supply dials act on (2030 onward, incl. post-horizon)."""
    fmy = int(scenario.firstmodelyear)
    return sorted(int(y) for y in scenario.set("year") if int(y) >= max(2030, fmy))


def _gas_cap_fraction(year: int, exit_year: int) -> float:
    """Gas-power cap as a fraction of 2020 history: 1.0 at 2030, declining
    linearly to :func:`_gas_power_residual` at ``exit_year``, held after."""
    if year <= 2030:
        return 1.0
    if year >= exit_year:
        return _gas_power_residual()
    return 1.0 - (1.0 - _gas_power_residual()) * (year - 2030) / (exit_year - 2030)


def _apply_supply_dials(scenario: Scenario, pathway: Pathway) -> None:
    """Impose the pathway's power-sector dials on the scenario.

    ``renewable_expansion``: aggregate activity-floor *relations* over the solar and
    wind resource grades (the floors are additional generation vs 2020 in TWh/8.76
    GWa — the pre-2020 fleet lives in the ``*_res_hist_*`` vintages, so the grades'
    combined activity *is* the expansion the EAG targets). ``fossil_power_exit_year``:
    coal/oil plants capped to 0 from 2030; gas power capped on a linear decline to a
    25% flexibility residual at the exit year. Both persist across the linkage loop
    (the linkage only rewrites the buildings end-use bounds). Idempotent per cell:
    previous supply rows are cleared first (batch hygiene, like the carbon policy).
    """
    if scenario.has_solution():
        scenario.remove_solution()
    scenario.check_out()
    _remove_supply_rows(scenario)
    years = _supply_years(scenario)

    if pathway.renewable_expansion is not None:
        twh = _eag_twh_additional()[pathway.renewable_expansion]
        # Only the families present in the TWh table get a floor (wind is
        # deliberately absent — see the EAG comment block above; the values
        # come from the renewable_floors sheet of data/inputs.xlsx).
        for family in twh:
            grades = _RENEWABLE_GRADES[family]
            rel = _RENEWABLE_RELATIONS[family]
            if rel not in set(scenario.set("relation")):
                scenario.add_set("relation", rel)
            path = twh[family]
            last = max(path)
            ra = [
                {"relation": rel, "node_rel": NODE, "year_rel": y, "node_loc": NODE,
                 "technology": t, "year_act": y, "mode": MODE, "value": 1.0, "unit": UNIT}
                for y in years for t in grades
            ]
            rl = [
                {"relation": rel, "node_rel": NODE, "year_rel": y,
                 "value": path.get(y, path[last]) / TWH_PER_GWA, "unit": UNIT}
                for y in years
            ]
            scenario.add_par("relation_activity", pd.DataFrame(ra))
            scenario.add_par("relation_lower", pd.DataFrame(rl))
            log.info("Pathway %s: %s floor %s (GWa: %s)", pathway.id, rel,
                     pathway.renewable_expansion,
                     {y: round(path.get(y, path[last]) / TWH_PER_GWA, 3) for y in years[:3]})

    if pathway.fossil_power_exit_year is not None:
        exit_year = int(pathway.fossil_power_exit_year)
        rows = [
            {"node_loc": NODE, "technology": t, "year_act": y, "mode": MODE,
             "time": TIME, "value": 0.0, "unit": UNIT}
            for t in _FOSSIL_POWER_ZERO for y in years
        ]
        hist = scenario.par("historical_activity", {"technology": list(_GAS_POWER_TECHS)})
        hist2020 = (
            hist[hist["year_act"].astype(int) == 2020].groupby("technology")["value"].sum()
            if not hist.empty else pd.Series(dtype=float)
        )
        for t in _GAS_POWER_TECHS:
            base = float(hist2020.get(t, 0.0))
            rows += [
                {"node_loc": NODE, "technology": t, "year_act": y, "mode": MODE,
                 "time": TIME, "value": base * _gas_cap_fraction(y, exit_year), "unit": UNIT}
                for y in years
            ]
        scenario.add_par("bound_activity_up", pd.DataFrame(rows))
        log.info("Pathway %s: fossil power exit %d (coal/oil→0 from 2030; gas → %.0f%% residual)",
                 pathway.id, exit_year, 100 * _gas_power_residual())

    scenario.commit(f"supply dials for pathway {pathway.id}")


def _remove_supply_rows(scenario: Scenario) -> None:
    """Delete the dial-owned supply rows (inside an open check-out).

    Restricted to ``year_act >= 2030`` — the dials only ever write from 2030
    on (:func:`_supply_years`), and the baseline **does** carry its own
    ``bound_activity_up`` rows on these techs (2020 calibration bounds, plus
    ``coal_ppl = 0`` at 2080–2110), contrary to what this docstring claimed
    before 2026-08-28. The year filter protects the 2020 calibration rows;
    the baseline's post-2080 coal zero-caps in the 2030+ window are removed
    and — when the fossil-power dial is active — rewritten identically by the
    dial (both are zeros). In a no-dial cell they are dropped: a documented
    residual imperfection beyond the reported horizon (2026-08-28 robustness
    review, B1).
    """
    ba = scenario.par("bound_activity_up",
                      {"technology": [*_FOSSIL_POWER_ZERO, *_GAS_POWER_TECHS]})
    if not ba.empty:
        ba = ba[ba["year_act"].astype(int) >= 2030]
    if not ba.empty:
        scenario.remove_par(
            "bound_activity_up", ba[["node_loc", "technology", "year_act", "mode", "time"]]
        )
    for rel in _RENEWABLE_RELATIONS.values():
        for par, idx in (
            ("relation_activity",
             ["relation", "node_rel", "year_rel", "node_loc", "technology", "year_act", "mode"]),
            ("relation_lower", ["relation", "node_rel", "year_rel"]),
        ):
            existing = scenario.par(par, {"relation": rel})
            if not existing.empty:
                scenario.remove_par(par, existing[idx])


def _clear_supply_dials(scenario: Scenario) -> None:
    """Remove leftover supply dials from a shared scenario (batch hygiene).

    A no-op (no check-out) when nothing dial-written is present.
    """
    ba = scenario.par("bound_activity_up",
                      {"technology": [*_FOSSIL_POWER_ZERO, *_GAS_POWER_TECHS]})
    if not ba.empty:
        # Match _remove_supply_rows' scope: the baseline's own pre-2030
        # calibration bounds are not "leftover dials" and must not trigger a
        # clearing pass on a fresh import.
        ba = ba[ba["year_act"].astype(int) >= 2030]
    has_rel = any(
        not scenario.par("relation_lower", {"relation": r}).empty
        for r in _RENEWABLE_RELATIONS.values()
    )
    if ba.empty and not has_rel:
        return
    log.info("Clearing leftover supply dials from a previous cell")
    if scenario.has_solution():
        scenario.remove_solution()
    scenario.check_out()
    _remove_supply_rows(scenario)
    scenario.commit("sturm-messageix: clear leftover supply dials")


def useful_bound_sides(pathway: Pathway) -> tuple[set[str], set[str]]:
    """Bound sides for the useful-mode static anchor: ``(cap_only, floor_only)``.

    The projection fuel mix is free, so the dials that need a per-tech handle are
    written as **one-sided** static bounds on top of the ``rc_therm`` demand (see
    :func:`linkage.bounds.apply_useful_anchor`):

    * ``fossil_exit_year`` → the fossil end-use techs are *cap-only* (a declining
      ceiling that goes to zero; a floor on the same technology would force it to
      keep emitting and can make the solve infeasible).
    * ``bioenergy_share_target_2040 = "low"`` → ``biomass_rc`` joins the caps
      (it may not expand to absorb the fossil exit).
    * ``bioenergy_share_target_2040 = "high"`` → ``biomass_rc`` is *floor-only*
      (held at least at base level, expansion free).
    * The **uncovered carriers** (:data:`~common.vocab.UNCOVERED_RC_TECHS` —
      ``rc_therm`` techs with no STURM fuel) are *cap-only* in **every**
      pathway: held flat at their observed base-year level so the free fuel mix
      re-allocates only among STURM-represented carriers (vocabulary-alignment
      decision, 2026-08-25).

    silently absorbed.
    """
    cap_only: set[str] = set(UNCOVERED_RC_TECHS)
    floor_only: set[str] = set()
    if pathway.fossil_exit_year is not None:
        cap_only |= set(_FOSSIL_TECHS)
    if pathway.bioenergy_share_target_2040 == "low":
        cap_only.add(_BIOENERGY_TECH)
    elif pathway.bioenergy_share_target_2040 == "high":
        floor_only.add(_BIOENERGY_TECH)
    return cap_only, floor_only


def floor_strip_techs(pathway: Pathway) -> set[str]:
    """Techs whose *decline floors* the useful-mode anchor may strip (r7 B3).

    Under the uniform constraint rule (decision 2026-08-29) every pathway keeps
    the baseline's lo-side dynamics (``growth/initial_activity_lo`` — the
    no-collapse floors that carry the stock inertia) and frees only the up-side.
    The single exception is dial-driven and identical in form for all pathways:
    a fossil-exit cap declines to **zero** within the horizon, which no decline
    floor can satisfy — keeping both is mathematically infeasible — so exactly
    the ramped fossil techs lose their floors. Flat caps (bioenergy "low",
    the uncovered carriers) do not collide with decline floors and keep them.
    """
    return set(_FOSSIL_TECHS) if pathway.fossil_exit_year is not None else set()


def constrain_targets(
    targets: pd.DataFrame,
    pathway: Pathway,
    *,
    base_year: int,
    shape: str = _DEFAULT_EXIT_SHAPE,
) -> pd.DataFrame:
    """Apply ``pathway``'s dials to an anchor-target frame (see module docs).

    Operates on the tidy frame produced by
    :func:`linkage.targets.useful_anchor_targets`
    (columns ``key``, ``technology``, ``year``, ``kind``, ``value``). The base
    year is calibration and is never altered; only projection years (``> base_year``)
    are reshaped. The Reference pathway returns the frame unchanged.

    Args:
        targets: The STURM-derived per-technology activity targets.
        pathway: The pathway whose dials to apply.
        base_year: The calibration/base year (left untouched).
        shape: Fossil phase-out curve — ``"logistic"`` (default) or ``"linear"``
            (the sensitivity-branch comparator).

    Returns:
        The reshaped targets frame.
    """
    if targets.empty or not _has_binding_dials(pathway):
        return targets

    t = targets.copy()
    if pathway.fossil_exit_year is not None:
        t = _ramp_fossil_out(t, base_year, pathway.fossil_exit_year, shape)
    if pathway.bioenergy_share_target_2040 is not None:
        t = _bound_bioenergy(t, pathway.bioenergy_share_target_2040, base_year)
    return t


def _fossil_fraction(year: int, base_year: int, ban_year: int, shape: str) -> float:
    """Fossil cap as a fraction of base for ``year``, declining to 0 at ``ban_year``.

    ``1.0`` at ``base_year`` and ``0.0`` at (and after) ``ban_year``. ``linear`` is a
    straight ramp; ``logistic`` is an S-shaped substitution curve affine-rescaled to
    hit those endpoints exactly (so ``logistic_k`` controls only the curvature).
    """
    if year <= base_year:
        return 1.0
    if year >= ban_year:
        return 0.0
    x = (year - base_year) / (ban_year - base_year)  # 0 → 1 across the window
    if shape == "linear":
        return 1.0 - x
    if shape == "logistic":
        k = _logistic_k()
        g = lambda u: 1.0 / (1.0 + math.exp(k * (u - 0.5)))  # noqa: E731
        return (g(x) - g(1.0)) / (g(0.0) - g(1.0))
    raise ValueError(f"unknown fossil_exit_shape {shape!r} (expected linear|logistic)")


def _ramp_fossil_out(
    t: pd.DataFrame, base_year: int, fossil_exit_year: int, shape: str
) -> pd.DataFrame:
    """Cap each fossil tech to zero at its fuel-specific ban year (see module docs).

    ``fossil_exit_year`` is the final (gas) exit; each tech's ban year leads it by
    :func:`_fossil_exit_lead`. A true cap: the STURM/Macko target is kept wherever
    it is already below the ramp, so the digitalization signal survives in the
    fossil techs and the phase-out never *loosens* a bound.
    """
    sel = (
        t["technology"].isin(_FOSSIL_TECHS)
        & (t["kind"] == "activity")
        & (t["year"] > base_year)
    )
    if not sel.any():
        return t
    base = (
        t[
            t["technology"].isin(_FOSSIL_TECHS)
            & (t["kind"] == "activity")
            & (t["year"] == base_year)
        ]
        .set_index("technology")["value"]
    )

    lead = _fossil_exit_lead()  # hoisted: not once per DataFrame row
    def _capped(row: pd.Series) -> float:
        tech = row["technology"]
        b = float(base.get(tech, 0.0))
        ban_year = fossil_exit_year - lead.get(tech, 0)
        ramp = b * _fossil_fraction(int(row["year"]), base_year, ban_year, shape)
        return min(float(row["value"]), ramp)

    t.loc[sel, "value"] = t[sel].apply(_capped, axis=1)
    return t


def _bound_bioenergy(t: pd.DataFrame, level: str, base_year: int) -> pd.DataFrame:
    """Cap (``low``) or floor (``high``) biomass at its base-year level."""
    is_bio = (t["technology"] == _BIOENERGY_TECH) & (t["kind"] == "activity")
    base_rows = t[is_bio & (t["year"] == base_year)]
    proj = is_bio & (t["year"] > base_year)
    if base_rows.empty or not proj.any():
        return t
    base_val = float(base_rows["value"].iloc[0])
    if level == "low":
        t.loc[proj, "value"] = t.loc[proj, "value"].clip(upper=base_val)
    elif level == "high":
        t.loc[proj, "value"] = t.loc[proj, "value"].clip(lower=base_val)
    return t