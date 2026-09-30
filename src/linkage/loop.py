"""Iterative price-feedback driver for the soft-linkage.

Each iteration: STURM produces buildings final energy (Austria only), which is
converted to useful energy with the conversion technologies' own coefficients
and imposed on MESSAGEix-Austria as the ``rc_therm`` useful-demand trajectory,
with the fuel mix left to the optimisation (the Mastrucci soft coupling). A
once-per-cell static anchor pins the base-year calibration and carries the
pathway's one-sided fossil-exit/bioenergy bounds
(:func:`linkage.bounds.apply_useful_anchor`); the digitalization signal enters as
an efficiency effect on the conversion technologies (:mod:`linkage.digital`).
The scenario is solved and the resulting commodity prices feed back into the
next STURM run, under-relaxed by ``Config.price_damping`` (:func:`_blend_prices`,
W5.8) so the price-responsive STURM fuel choice cannot limit-cycle against the
LP duals. The loop stops when the demand vector crossing the boundary converges
(:mod:`linkage.convergence`) or the ``max_iterations`` budget is exhausted, in
which case an oscillation correction (the mean of the last two vectors) is
applied.

Running STURM here means invoking the **R** model via ``Rscript`` (see
:func:`sturm.driver.run_offline`).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from common import paths, vocab
from common.config import Config
from common.reference import load_reference
from common.units import MWH_PER_KWA
from linkage import bounds, convergence, digital
from linkage.targets import sturm_to_useful_demand, useful_anchor_targets
from messageix import pathways
from sturm.driver import load_report, run_offline

if TYPE_CHECKING:
    from message_ix import Scenario

    from common.scenarios import Digitalization, Pathway

log = logging.getLogger(__name__)

#: STURM's MESSAGEix price-input schema (consumed by ``F10``: it does the
#: ``lvl / 31.71`` conversion and the commodity→fuel mapping itself).
_PRICE_COLUMNS: list[str] = ["node", "commodity", "level", "year", "time", "lvl", "mrg"]

#: Identity of a price row — everything in :data:`_PRICE_COLUMNS` except the values.
_PRICE_KEY: list[str] = ["node", "commodity", "level", "year", "time"]

#: Node label STURM's ``F10`` price join expects (it reads region from chars 5-7
#: → "WEU", and the R11/R12 column name from chars 1-3 → "R12"). Both the calibrated
#: ``C-AUT`` and the original ``C-WEU-AUT`` keep ``R11 = R12 = WEU``, so the price join is
#: unchanged regardless of ``Config.sturm_region`` — only ``region_gea`` differs (AUT vs WEU).
_STURM_NODE: str = "R12_WEU"

#: Final-energy carriers whose MESSAGEix prices feed STURM's fuel-choice modules.
#: ``d_heat`` is included and — since the W5.6 fork — delivered to STURM's fuel
#: choice (``F10`` used to drop it; the fork's remap keeps it).
_PRICE_CARRIERS: frozenset[str] = frozenset(
    {"electr", "gas", "biomass", "coal", "lightoil", "d_heat"}
)


def run_sturm(
    prices: pd.DataFrame | None,
    *,
    first_iteration: bool,
    sector: str = "resid",
    scenario: str = "SSP2",
    region_select: list[str] | None = None,
    years: Sequence[int] | None = None,
) -> pd.DataFrame:
    """Invoke the STURM R model, optionally with MESSAGEix price feedback.

    Serializes ``prices`` to STURM's price-input schema and delegates to
    :func:`sturm.driver.run_offline`. On the first iteration (or when no
    prices are available yet) STURM runs against its bundled price defaults.

    Args:
        prices: MESSAGEix commodity prices from the previous solve, in the
            :data:`_PRICE_COLUMNS` schema; ``None`` uses STURM's default prices.
        first_iteration: Whether this is the first call. On the first call there
            is no prior solve, so bundled default prices are used.
        sector: ``resid`` or ``comm``.
        scenario: STURM scenario / SSP variant.
        region_select: ``region_bld`` codes to subset to (e.g. ``["C-AUT"]``).
        years: Modelled years to run STURM over; ``None`` uses ``run_offline``'s
            default.

    Returns:
        A STURM ``report_MESSAGE`` frame for the next demand update.
    """
    prices_csv: Path | None = None
    if not first_iteration and prices is not None and not prices.empty:
        prices_csv = paths.STURM_OUTPUT / f"_prices_{sector}_{scenario}.csv"
        prices_csv.parent.mkdir(parents=True, exist_ok=True)
        out = prices[_PRICE_COLUMNS]
        # The explicit HP carrier (W5.6) is electricity on the MESSAGEix side; STURM
        # prices it as its own fuel, so the electr row is duplicated under the
        # elec_hp name (a missing fuel price NA-poisons F05's market shares).
        hp = out[out["commodity"] == "electr"].assign(commodity="elec_hp")
        pd.concat([out, hp], ignore_index=True).to_csv(prices_csv, index=False)

    kwargs: dict[str, object] = dict(
        sector=sector, scenario=scenario, region_select=region_select, prices_csv=prices_csv
    )
    if years is not None:
        kwargs["years"] = tuple(years)
    report_path = run_offline(**kwargs)  # type: ignore[arg-type]
    return load_report(report_path)


def _extract_prices(scenario: Scenario) -> pd.DataFrame:
    """Pull final-energy carrier prices from a solved scenario, keyed for STURM.

    Args:
        scenario: A solved MESSAGEix-Austria scenario.

    Returns:
        A frame in the :data:`_PRICE_COLUMNS` schema with ``node`` relabelled to
        :data:`_STURM_NODE`, restricted to :data:`_PRICE_CARRIERS` at
        ``level == "final"`` on the model node (aggregate/global rows — the stray
        near-zero ``GLB`` lightoil price of the 2026-07-07 diagnostic — are dropped
        *before* the relabel, which would otherwise disguise them as Austrian rows).
        Dual-gap years are filled to a stable shape (:func:`_fill_missing_years`).
    """
    price = scenario.var("PRICE_COMMODITY")
    price = price[
        (price["node"] == vocab.NODE)
        & (price["level"] == "final")
        & (price["commodity"].isin(_PRICE_CARRIERS))
    ].copy()
    price["node"] = _STURM_NODE
    return _fill_missing_years(price[_PRICE_COLUMNS].reset_index(drop=True))


def _fill_missing_years(price: pd.DataFrame) -> pd.DataFrame:
    """Give the extracted price vector a stable ``(commodity, year)`` shape (W5.8b).

    ``PRICE_COMMODITY`` drops a row when a commodity balance is non-binding in a
    period (zero dual, sparse GAMS storage) — in the r5 exports ``d_heat`` has no
    2030 row. A row that flickers in and out between solves escapes the W5.8
    blend: the one-sided keep hands it through alternately raw and stale, and
    exactly that channel (``heat_rc``) kept the 2026-07-12 damped batch's
    stubborn cells oscillating. Filling the gaps keeps the vector's shape fixed,
    so :func:`_blend_prices` is two-sided on every entry and the damping bites
    everywhere.

    Per commodity, ``year`` is reindexed to the union of years present in the
    frame; interior gaps in ``lvl`` are interpolated linearly on the year axis
    (a dual gap is a degeneracy artifact, not a zero consumer price — smoothing
    it is the same call as damping itself); edge gaps take the nearest value.
    ``mrg`` fills 0; the key columns are constant per commodity and carried over.

    Args:
        price: Extracted prices in the :data:`_PRICE_COLUMNS` schema.

    Returns:
        The frame with every commodity covering the full year set, in
        :data:`_PRICE_COLUMNS` order, sorted on :data:`_PRICE_KEY`.
    """
    if price.empty:
        return price
    years = sorted(price["year"].unique())
    filled: list[pd.DataFrame] = []
    holes: list[str] = []
    for commodity, group in price.groupby("commodity", sort=False):
        g = group.set_index("year").reindex(years)
        missing = g["lvl"].isna()
        if missing.any():
            holes += [f"{commodity}/{y}" for y in g.index[missing]]
            g["lvl"] = g["lvl"].interpolate(method="index").ffill().bfill()
            g["mrg"] = g["mrg"].fillna(0.0)
            for col in ("node", "commodity", "level", "time"):
                g[col] = group[col].iloc[0]
        filled.append(g.reset_index())
    if holes:
        log.info("Price vector: filled %d dual-gap rows (%s)", len(holes), ", ".join(holes))
    out = pd.concat(filled, ignore_index=True)
    return out[_PRICE_COLUMNS].sort_values(_PRICE_KEY).reset_index(drop=True)


#: Wilson-band ramp window (Wilson, Zakeri et al. 2026 study horizon; the same
#: window `viz/digitalization_band.py` documents — modifier provenance lives there).
_WILSON_BASE_YEAR: int = 2025
_WILSON_STUDY_YEAR: int = 2050


def _wilson_factor(year: int, modifier: float) -> float:
    """Demand scale ``1 + m·ramp(year)`` for a Wilson-band cell (r7 B8).

    Linear ramp from 0 at 2025 to the full modifier at 2050, clamped outside —
    matching the ex-post band's phase-in so the endogenous cells replace it
    like-for-like. At 2040 the factor is ``1 + 0.6·m``.
    """
    ramp = (year - _WILSON_BASE_YEAR) / (_WILSON_STUDY_YEAR - _WILSON_BASE_YEAR)
    return 1.0 + modifier * min(max(ramp, 0.0), 1.0)


def _add_carbon_price(prices: pd.DataFrame, scenario: Scenario) -> pd.DataFrame:
    """Fold the scenario's carbon tax into the fuel prices STURM receives (W5.3).

    The tax (``tax_emission``, USD/tCO₂ on ``type_emission="GHG"``) bites on the
    end-use technologies' activity — *downstream* of the final-level commodity
    balance whose duals the loop reads — so without this passthrough STURM's
    operating costs never see the carbon signal (2026-07-07 diagnostic: the 120-USD
    probe left the STURM price vector identical to the last digit).

    Adds ``tax(year) × EF_direct(fuel) × MWH_PER_KWA`` to ``lvl`` — $/tCO₂ ×
    tCO₂/MWh × MWh/kWa = $/kWa, the ``PRICE_COMMODITY`` unit (M$/GWa). Direct (on-site
    combustion) factors only, matching the territorial tax base: electricity and
    district heat carry no direct factor and are untouched. No-op when the scenario
    prices no emissions.
    """
    from messageix.emissions import emission_factors

    tax = scenario.par("tax_emission")
    if tax is None or tax.empty:
        return prices
    tax = tax[tax["type_emission"] == "GHG"]
    if tax.empty:
        return prices
    tax_by_year = {int(y): float(v) for y, v in zip(tax["type_year"], tax["value"])}
    ef = emission_factors("direct")
    out = prices.copy()
    adder = [
        tax_by_year.get(int(y), 0.0) * ef.get(str(c), 0.0) * MWH_PER_KWA
        for y, c in zip(out["year"], out["commodity"])
    ]
    out["lvl"] = out["lvl"] + pd.Series(adder, index=out.index)
    return out


def _blend_prices(
    new: pd.DataFrame, previous: pd.DataFrame | None, alpha: float
) -> pd.DataFrame:
    """Under-relax the price vector fed to STURM (W5.8): ``α·new + (1−α)·previous``.

    The raw solve-to-solve price feedback limit-cycles once STURM is genuinely
    price-responsive (the W5.6 endogenous-DH oscillation): ``PRICE_COMMODITY``
    duals are piecewise-constant in the activity bounds — a small bound shift flips
    the binding set and the duals jump — and STURM's near-winner-take-all logit
    turns that jump into a large fuel-mix swing, which flips the bounds back.
    Blending each new dual vector into the previously *fed* one moves the STURM
    input toward the cycle midpoint, where the (smooth) logit stabilises and the
    binding set stops flipping.

    ``previous`` is the vector fed to STURM this iteration (``None`` on the first
    extraction — STURM ran on its bundled defaults, for which no numeric vector
    exists), so passing the result back in recursively yields the damped state.
    Outer-joined on :data:`_PRICE_KEY`: a row present on only one side keeps its
    single-sided ``lvl`` instead of vanishing from STURM's price file (a missing
    fuel price NA-poisons F05's market shares). ``mrg`` is carried from ``new`` (F10 ignores it).

    Args:
        new: Freshly extracted (and tax-loaded) prices in the
            :data:`_PRICE_COLUMNS` schema.
        previous: The vector fed to STURM in the current iteration, or ``None``.
        alpha: Under-relaxation factor in ``(0, 1]``; ``1.0`` = no damping.

    Returns:
        The blended frame in :data:`_PRICE_COLUMNS` order, sorted on
        :data:`_PRICE_KEY` for determinism.
    """
    if not 0.0 < alpha <= 1.0:
        raise ValueError(f"price_damping must be in (0, 1], got {alpha}")
    if previous is None or alpha == 1.0:
        return new
    merged = new.merge(previous, on=_PRICE_KEY, how="outer", suffixes=("_new", "_prev"))
    one_sided = merged["lvl_new"].isna() | merged["lvl_prev"].isna()
    if one_sided.any():
        log.warning(
            "Price blend: %d rows present in only one of the last two price vectors; "
            "keeping their single-sided values.", int(one_sided.sum()),
        )
    merged["lvl"] = alpha * merged["lvl_new"] + (1.0 - alpha) * merged["lvl_prev"]
    merged["lvl"] = merged["lvl"].fillna(merged["lvl_new"]).fillna(merged["lvl_prev"])
    merged["mrg"] = merged["mrg_new"].fillna(merged["mrg_prev"])
    return merged[_PRICE_COLUMNS].sort_values(_PRICE_KEY).reset_index(drop=True)


def sturm_scenario_name(pathway: Pathway) -> str:
    """Compose the STURM manifest column for a matrix cell: ``SSP2[_RENAT]``.

    Every adoption level runs the plain ``SSP2`` operating hours — the
    digitalization signal is applied on the MESSAGEix side (:mod:`linkage.digital`);
    a renovation-ambitious pathway (``renovation_ambition == "at_target"``, W5.2)
    appends the ``_RENAT`` suffix (renovation ceiling at the Austrian 3%/yr policy
    target, baked into the STURM CSVs — see the provenance sheet).
    """
    name = "SSP2"
    if pathway.renovation_ambition == "at_target":
        name += "_RENAT"
    return name


def _linkage_years(config: Config) -> list[int]:
    """Years STURM runs over and the loop bounds: base year + modelled horizon.

    Ascending so STURM's base year (``config.base_year``) is first and its stock
    dynamics run forwards. Deliberately *not* taken from the scenario's ``demand``
    (which carries the full 1990–2110 calibration span) — feeding STURM history or
    far-future years collapses its construction/renovation calculations.
    """
    return sorted({config.base_year, *config.years})


def run(
    scenario: Scenario,
    config: Config,
    digitalization: Digitalization,
    pathway: Pathway,
) -> tuple[Scenario, convergence.ConvergenceStatus]:
    """Drive the iterative STURM ⇄ MESSAGEix loop to convergence.

    Returns the solved scenario together with the loop's
    :class:`~linkage.convergence.ConvergenceStatus` result contract
    (converged flag, iteration count, final L-infinity change,
    oscillation-correction flag).

    Args:
        scenario: The prepared MESSAGEix-Austria scenario.
        config: Run configuration (``max_iterations``, ``convergence_tol``,
            ``price_damping``, ``solve``).
        digitalization: The active digitalization-adoption level for this cell.
        pathway: The active climate-neutrality pathway. Its dials are written once
            per cell as the static anchor (:func:`messageix.pathways.useful_bound_sides`,
            :func:`messageix.pathways.constrain_targets`) before the loop starts.

    Returns:
        The solved scenario at convergence (or after the iteration budget, with
        the oscillation correction applied).
    """
    # Base year + modelled horizon only, ascending — STURM's base year must come
    # first and the dynamic loop must run forwards. (Do NOT derive these from the
    # demand parameter: the baseline spans 1990–2110, which would feed STURM history
    # and far-future years and collapse its stock dynamics.)
    sturm_years = _linkage_years(config)

    # Anchor STURM's per-fuel levels to the authoritative Austrian reference (STURM
    # is WEU-calibrated; only its trajectory shape is used). The reference vintage
    # (config.calibration_year) may differ from the model base year — its level is
    # pinned at STURM's first year (config.base_year), i.e. forward-reconciled.
    reference = load_reference(config.calibration_year)

    # Model years beyond the horizon: STURM/Macko stop at the horizon, so the
    # horizon-end bound is carried forward to these (holds the decarbonised end-of-
    # horizon fuel mix instead of letting the model re-fossilise post-horizon).
    horizon_end = max(sturm_years)
    extra_years = sorted(y for y in (int(y) for y in scenario.set("year")) if y > horizon_end)

    # Once-per-cell static layer (STURM-independent, so outside the loop):
    # base-year per-fuel calibration pin + the pathway's one-sided fossil-exit /
    # bioenergy bounds. Without the pin the base-year fuel mix is free (the
    # baseline calibrates only 2020) and MESSAGEix picks a fossil-heavy 2025
    # mix that the growth dynamics propagate — the 6.6 Mt useful-mode anomaly.
    cap_only, floor_only = pathways.useful_bound_sides(pathway)
    anchor = useful_anchor_targets(
        scenario, reference,
        base_year=config.base_year, years=sturm_years, extra_years=extra_years,
        base_hp_share=config.base_hp_share,
        projection_techs=cap_only | floor_only,
    )
    anchor = pathways.constrain_targets(
        anchor, pathway, base_year=config.base_year, shape=config.fossil_exit_shape
    )
    bounds.apply_useful_anchor(
        scenario, anchor, tol=config.bound_tol,
        base_year=config.base_year, base_tol=config.base_bound_tol,
        cap_only=cap_only, floor_only=floor_only,
        floor_strip=pathways.floor_strip_techs(pathway),
        commit=f"sturm-messageix: useful-mode anchor + pathway caps ({pathway.id})",
    )

    # STURM manifest column for this cell (see sturm_scenario_name): plain SSP2
    # hours, composed with the pathway's renovation-ambition variant (W5.2).
    sturm_scenario = sturm_scenario_name(pathway)
    log.info("STURM scenario column: %s", sturm_scenario)

    # r8 efficiency channel (changelog §26): Macko's final-energy saving scales the
    # conversion technologies' input coefficients (and their baked CO2 factors)
    # over the projection years; STURM keeps the SSP2 hours, so the useful demand
    # is adoption-invariant. The conversion below must use the coefficients as
    # they were BEFORE this scaling — snapshotted here.
    coef_override = digital.base_input_coefficients(scenario, sturm_years)
    factors = digital.reduction_factors(
        digitalization, [*sturm_years, *extra_years], base_year=config.base_year
    )
    digital.apply_digital_efficiency(
        scenario, factors,
        commit=f"sturm-messageix: digital efficiency ({digitalization.id})",
    )
    log.info(
        "Digitalization %s: efficiency factor %.4f at %d (useful demand unchanged)",
        digitalization.id, float(factors.get(max(sturm_years), 1.0)), max(sturm_years),
    )

    prices: pd.DataFrame | None = None
    last_change: float | None = None
    prev: pd.Series | None = None
    recent: list[pd.DataFrame] = []
    log.info("Price feedback damping alpha = %g", config.price_damping)

    # One iteration = re-derive the useful demand from the latest STURM run,
    # solve, then read the commodity prices that cross the boundary back to STURM
    # for the next round — under-relaxed (W5.8) so the dual-price jumps cannot
    # sustain a limit cycle. Convergence is judged on the demand vector (what we
    # impose), not the prices.
    for i in range(config.max_iterations):
        report = run_sturm(
            prices,
            first_iteration=(i == 0),
            scenario=sturm_scenario,
            region_select=[config.sturm_region],
            years=sturm_years,
        )
        if scenario.has_solution():
            scenario.remove_solution()

        # FE → useful via the techs' (unscaled) input coefficients → rc_therm demand;
        # fuel mix free (no bounds written). The tested interface state is the
        # demand vector (projection years; the base-year demand is the calibration
        # and equals the series there by construction, so it is neither written
        # nor tested).
        demand = sturm_to_useful_demand(
            report, scenario, sturm_years, extra_years=extra_years,
            coefficients=coef_override,
        ).drop(config.base_year)
        if pathway.demand_modifier is not None:
            factors = pd.Series(
                [_wilson_factor(int(y), pathway.demand_modifier) for y in demand.index],
                index=demand.index,
            )
            demand = demand * factors
            if i == 0:
                log.info(
                    "Pathway %s: Wilson demand modifier %+.0f%% (ramped 2025→2050; "
                    "2040 factor %.3f)",
                    pathway.id, pathway.demand_modifier * 100,
                    _wilson_factor(2040, pathway.demand_modifier),
                )
        bounds.apply_useful_demand(
            scenario, demand, commit=f"sturm-messageix: useful-mode iter {i}"
        )
        scenario.solve(**config.solve)
        recent = [*recent[-1:], demand.rename_axis("year").rename("value").reset_index()]
        curr = demand
        if prev is not None:
            change = convergence.linf_relative_change(prev, curr)
            if change <= config.convergence_tol:
                log.info(
                    "Linkage converged at iteration %d: "
                    "L-inf demand change = %.4g (tol=%g)",
                    i, change, config.convergence_tol,
                )
                return scenario, convergence.ConvergenceStatus(
                    converged=True, iterations=i + 1, final_linf=float(change),
                    oscillation_corrected=False,
                )
            last_change = float(change)
            log.info("Iteration %d: L-inf demand change = %.4g", i, change)
            # The years driving the L-inf — makes a limit cycle's oscillating
            # components readable straight from the server runlog.
            log.info(
                "Iteration %d: top changers: %s", i,
                ", ".join(
                    f"{k}={v:.3g}" for k, v in convergence.top_changes(prev, curr).items()
                ),
            )
        prev = curr
        # `prices` still holds what was fed to STURM this iteration (None on the
        # first pass), so blending into it recursively yields the damped state.
        new_prices = _extract_prices(scenario)
        if config.carbon_price_passthrough:
            new_prices = _add_carbon_price(new_prices, scenario)  # blend AFTER the tax
        prices = _blend_prices(new_prices, prices, config.price_damping)

    log.warning(
        "Iteration budget (%d) exhausted without convergence; applying oscillation "
        "correction (mean of last two demand vectors).",
        config.max_iterations,
    )
    if len(recent) == 2:
        if scenario.has_solution():
            scenario.remove_solution()
        averaged_demand = (
            recent[0].set_index("year")["value"] + recent[1].set_index("year")["value"]
        ) / 2.0
        bounds.apply_useful_demand(
            scenario, averaged_demand,
            commit="sturm-messageix: useful-mode oscillation mean",
        )
        scenario.solve(**config.solve)
    return scenario, convergence.ConvergenceStatus(
        converged=False, iterations=config.max_iterations, final_linf=last_change,
        oscillation_corrected=len(recent) == 2,
    )
