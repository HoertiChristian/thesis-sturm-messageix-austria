"""STURM report → boundary quantities of the useful-energy coupling (the derivation half).

Pure DataFrame math — no ixmp mutation. The companion module
:mod:`linkage.bounds` writes the derived frames onto the scenario.

Two derivations:

1. :func:`sturm_to_useful_demand` (every iteration): STURM final energy per fuel,
   summed over the thermal end-uses (heat/cool/hotwater), is converted to useful
   energy with the MESSAGEix conversion technologies' own ``input`` coefficients;
   only the trajectory shape ``U(y)/U(base)`` is taken from STURM, the level is the
   calibrated ``rc_therm`` demand of the baseline.
2. :func:`useful_anchor_targets` (once per cell): the base-year per-fuel calibration
   pin at the Austrian reference level (Statistik Austria final energy ÷ the tech's
   input coefficient) plus the flat rows that the pathway dials ramp into one-sided
   caps and floors. Since W5.6 STURM reports resistive (``electr``) and heat-pump
   (``elec_hp``) electricity as explicit carriers; only the observed *reference*
   electricity total needs splitting (``base_hp_share``, Mikrozensus 2023/24).

``sp_el_RC`` (specific electricity) is **not** targeted: STURM reports ~0 for its
``other``/specific-electricity bucket (outside STURM's thermal scope), so it
cannot be anchored — it is left free (the baseline demand drives it).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

import pandas as pd

from common.vocab import (
    FUEL_TO_TECH,
    TARGET_COLUMNS,
    THERMAL_END_USES,
    UNCOVERED_RC_TECHS,
)
from sturm.driver import split_commodity

if TYPE_CHECKING:
    from message_ix import Scenario

log = logging.getLogger(__name__)


def _anchor_activity(
    scenario: Scenario, techs: Sequence[str], anchor_year: int
) -> dict[str, float]:
    """Baseline ``bound_activity_up`` per tech at ``anchor_year`` (the Austria anchor)."""
    bound = scenario.par("bound_activity_up", {"technology": list(techs)})
    if bound.empty:
        return {}
    bound = bound[bound["year_act"].astype(int) == anchor_year]
    return bound.groupby("technology")["value"].sum().to_dict()


def _observed_base_activity(
    scenario: Scenario, techs: Sequence[str], base_year: int
) -> dict[str, float]:
    """Latest pre-/at-base calibration ``bound_activity_up`` per tech.

    The baseline carries its calibration bounds at historical years (2020 for the
    rc techs) while the linkage base year is 2025, so the observed level for a
    tech outside the Austrian reference is the bound at the **latest year ≤
    base_year** that has one. Techs with no such bound (the future carriers)
    resolve to absent — the caller treats that as an observed level of zero.
    """
    bound = scenario.par("bound_activity_up", {"technology": list(techs)})
    if bound.empty:
        return {}
    bound = bound.copy()
    bound["year_act"] = bound["year_act"].astype(int)
    bound = bound[bound["year_act"] <= base_year]
    if bound.empty:
        return {}
    latest_year = bound.groupby("technology")["year_act"].transform("max")
    latest = bound[bound["year_act"] == latest_year]
    return latest.groupby("technology")["value"].sum().to_dict()


def _input_coef(
    scenario: Scenario, tech: str, commodity: str, year: int
) -> float | None:
    """Final-energy ``input`` coefficient of ``tech`` for ``commodity`` in ``year``.

    Picks the same-vintage (``year_vtg == year_act == year``) coefficient, else
    the latest available vintage operating in ``year``. A tech that has ``input``
    rows but none operating in ``year`` raises: the old all-rows-mean fallback
    could silently blend across decades of efficiency change (2026-09-04,
    external-review adoption — never exercised by the r7 baseline, where every
    end-use tech operates in every model year). (Related but deliberately not
    identical: ``model.build._sp_el_input_coef`` selects on ``year_act`` only.)
    """
    inp = scenario.par(
        "input", {"technology": tech, "commodity": commodity, "level": "final"}
    )
    if inp.empty:
        return None
    inp = inp.assign(
        year_vtg=inp["year_vtg"].astype(int), year_act=inp["year_act"].astype(int)
    )
    exact = inp[(inp["year_act"] == year) & (inp["year_vtg"] == year)]
    if not exact.empty:
        return float(exact["value"].mean())
    active = inp[inp["year_act"] == year]
    if not active.empty:
        return float(active.sort_values("year_vtg")["value"].iloc[-1])
    raise ValueError(
        f"input coefficient for tech {tech!r} / commodity {commodity!r} has rows "
        f"but none operating in year {year}; refusing to average across vintages"
    )


def _therm_reference(reference: pd.DataFrame) -> dict[str, float]:
    """``rc_therm`` final energy (GWa) per fuel from a reference frame."""
    therm = reference[reference["commodity"] == "rc_therm"]
    return therm.groupby("fuel")["value_gwa"].sum().to_dict()


def _fuel_commodity(fuel: str) -> str:
    """STURM fuel → the MESSAGEix commodity its technology consumes.

    The explicit heat-pump carrier (W5.6) is STURM-side only — ``hp_el_rc`` draws
    the ``electr`` commodity; every other fuel name doubles as the commodity name.
    """
    return "electr" if fuel == "elec_hp" else fuel


def _require_input_coef(
    scenario: Scenario, tech: str, commodity: str, year: int
) -> float:
    """Fail-loud input coefficient: the calibrated baseline must carry the rows."""
    coef = _input_coef(scenario, tech, commodity, year)
    if not coef or coef <= 0:
        raise ValueError(
            f"no positive 'input' coefficient for {tech}/{commodity} at {year}; "
            "the baseline must carry the final-energy input rows (no fallback)"
        )
    return float(coef)


def _anchor_level(
    scenario: Scenario,
    ref_therm: dict[str, float] | None,
    fallback: dict[str, float],
    tech: str,
    fuel: str,
    anchor_year: int,
) -> float:
    """Base-year activity level for ``tech``: from the Austrian reference (final energy
    ÷ the tech's input coef), else the model's own ``bound_activity_up`` fallback.

    A missing or non-positive coefficient raises (no silent 1.0 default).
    """
    if ref_therm is not None:
        ref_final = float(ref_therm.get(fuel, 0.0))
        if ref_final <= 0:
            return 0.0
        coef = _require_input_coef(scenario, tech, _fuel_commodity(fuel), anchor_year)
        return ref_final / coef
    return float(fallback.get(tech, 0.0))


def _split_electric_reference(
    ref_therm: dict[str, float],
    scenario: Scenario,
    anchor_year: int,
    base_hp_share: float,
) -> dict[str, float]:
    """Split the observed electricity final energy into resistive / heat-pump carriers.

    The Austrian reference records one electricity-for-heat total; since W5.6 STURM
    carries ``electr`` (resistive) and ``elec_hp`` explicitly, so the anchor splits
    the observed total with ``base_hp_share`` (Mikrozensus 2023/24 dwelling counts,
    HP fraction of electric-heat *useful* energy) and the two techs' own electricity
    input coefficients — final(HP) = s·c_hp / ((1−s)·c_res + s·c_hp) of the total, so
    the combined final electricity still equals the statistic (calibration preserved;
    the same arithmetic the retired ``elec_heat_sturm`` relation split used).
    """
    total = float(ref_therm.get("electr", 0.0))
    out = dict(ref_therm)
    if total <= 0:
        return out
    s_hp = min(max(base_hp_share, 0.0), 1.0)
    coef_res = _require_input_coef(scenario, "elec_rc", "electr", anchor_year)
    coef_hp = _require_input_coef(scenario, "hp_el_rc", "electr", anchor_year)
    denom = (1.0 - s_hp) * coef_res + s_hp * coef_hp
    if denom <= 0:
        return out
    out["electr"] = total * (1.0 - s_hp) * coef_res / denom
    out["elec_hp"] = total * s_hp * coef_hp / denom
    return out


def _carry_forward(
    targets: pd.DataFrame, last_year: int, extra_years: Sequence[int]
) -> pd.DataFrame:
    """Replicate each key's ``last_year`` target onto every ``extra_years`` year.

    STURM and Macko stop at the horizon; rather than leave post-horizon years
    unconstrained (the model re-fossilises to cheap gas), the horizon-end bound is
    held constant so the decarbonised end-of-horizon fuel mix carries forward.
    """
    extra = [int(y) for y in extra_years if int(y) > last_year]
    if not extra or targets.empty:
        return targets
    tail = targets[targets["year"] == last_year]
    carried = pd.concat(
        [tail.assign(year=y) for y in extra], ignore_index=True
    )
    return pd.concat([targets, carried], ignore_index=True)


def useful_anchor_targets(
    scenario: Scenario,
    reference: pd.DataFrame | None,
    *,
    base_year: int,
    years: Sequence[int],
    extra_years: Sequence[int] = (),
    base_hp_share: float = 0.0,
    projection_techs: set[str] | None = None,
) -> pd.DataFrame:
    """Static per-tech anchor targets for the useful (soft-coupling) mode.

    ``sturm_to_useful_demand`` writes only the projection-year ``rc_therm`` demand;
    on its own that leaves the **base-year fuel mix free** (the baseline workbook
    carries calibration bounds only at 2020), so MESSAGEix picks a cheapest — i.e.
    fossil-heavy — 2025 mix and the growth dynamics propagate it forward (the
    2026-07-14 "6.6 Mt anomaly" diagnosis). This frame closes that gap and carries
    the pathway dials that need a per-tech handle even when the fuel mix is
    otherwise free:

    * **Base-year rows for every fuel tech** at the reference-anchored level
      (:func:`_anchor_level` / :func:`_split_electric_reference`) — written as a
      two-sided equality pin, restoring the Statistik Austria calibration.
    * **Flat-at-base projection rows** only for ``projection_techs`` (the fossil
      techs under a ``fossil_exit_year``; ``biomass_rc`` under a bioenergy dial —
      see :func:`messageix.pathways.useful_bound_sides`). Fed through
      :func:`messageix.pathways.constrain_targets`, the flat rows become the
      fuel-specific logistic/linear exit ramp — one source of truth for the
      trajectory. Written one-sided (cap or floor) by
      :func:`linkage.bounds.apply_useful_anchor`.
    * **Rows for the uncovered carriers** (:data:`~common.vocab.UNCOVERED_RC_TECHS`
      — the ``rc_therm`` techs with no STURM fuel: solar thermal and the
      minor/future carriers): each is held at its observed base-year level (the
      baseline's latest calibration bound at or before ``base_year``; zero where
      none exists, i.e. the hydrogen techs). With the fuel mix otherwise free,
      leaving them unbounded would let the optimisation route thermal demand
      through carriers STURM cannot see — the vocabulary-alignment decision
      (2026-08-25) makes "re-allocation only among STURM-represented carriers"
      explicit. They are always in ``projection_techs``/``cap_only`` (flat caps,
      decline allowed).

    Unlike the per-iteration demand this frame is STURM-independent (level-only,
    no trajectory shape), so it is derived and applied **once per cell** before
    the loop. Returns an empty frame when no anchor source is available (no
    reference and no baseline bounds — e.g. stubbed test scenarios), which the
    writer treats as a no-op.

    Args:
        scenario: The MESSAGEix-Austria scenario (input coefficients; fallback anchor).
        reference: Austrian reference ``[commodity, fuel, value_gwa]`` (final energy).
        base_year: The calibration/base year (rows for every fuel tech).
        years: Modelled years (incl. ``base_year``); projection rows use the rest.
        extra_years: Post-horizon model years (horizon-end cap carried forward).
        base_hp_share: Heat-pump fraction of base-year electric-heat useful energy.
        projection_techs: Techs that also get flat-at-base projection rows.

    Returns:
        A tidy :data:`~common.vocab.TARGET_COLUMNS` frame (``kind="activity"`` only —
        no relation rows; the electric split is explicit per-tech at the base year).
    """
    projection = set(projection_techs or ())
    target_years = [int(y) for y in years]
    ref_therm = (
        _therm_reference(reference)
        if reference is not None and not reference.empty
        else None
    )
    fallback = (
        _anchor_activity(scenario, list(FUEL_TO_TECH.values()), base_year)
        if ref_therm is None
        else {}
    )
    if ref_therm is not None and "electr" in ref_therm:
        ref_therm = _split_electric_reference(ref_therm, scenario, base_year, base_hp_share)

    proj_years = sorted(y for y in target_years if y > base_year)
    rows: list[dict[str, object]] = []
    for fuel, tech in FUEL_TO_TECH.items():
        if ref_therm is None and tech not in fallback:
            log.warning(
                "No anchor for %s (no reference, no baseline bound at %d); leaving unpinned",
                tech, base_year,
            )
            continue
        a = _anchor_level(scenario, ref_therm, fallback, tech, fuel, base_year)
        rows.append({"key": tech, "technology": tech, "year": base_year,
                     "kind": "activity", "value": a})
        if tech in projection:
            rows += [
                {"key": tech, "technology": tech, "year": y, "kind": "activity", "value": a}
                for y in proj_years
            ]
    if rows:  # only with an anchor source — stubbed test scenarios stay a no-op
        observed = _observed_base_activity(scenario, UNCOVERED_RC_TECHS, base_year)
        for tech in UNCOVERED_RC_TECHS:
            a = float(observed.get(tech, 0.0))
            rows.append({"key": tech, "technology": tech, "year": base_year,
                         "kind": "activity", "value": a})
            if tech in projection:
                rows += [
                    {"key": tech, "technology": tech, "year": y, "kind": "activity",
                     "value": a}
                    for y in proj_years
                ]
    frame = pd.DataFrame(rows, columns=TARGET_COLUMNS)
    if frame.empty:
        return frame
    return _carry_forward(frame, max(target_years), extra_years)


def sturm_to_useful_demand(
    report: pd.DataFrame,
    scenario: Scenario,
    years: Sequence[int],
    *,
    extra_years: Sequence[int] = (),
    coefficients: Mapping[tuple[str, int], float] | None = None,
) -> pd.Series:
    """Convert a STURM report into an ``rc_therm`` useful-demand trajectory (W5.4).

    The soft-coupling precedent (Mastrucci, 2026-07-07): STURM's per-fuel *final*
    energy is converted to *useful* energy with the MESSAGEix technologies' own
    base-year ``input`` coefficients — "use the energy-efficiency coefficients in
    MESSAGE" — and the total drives the ``rc_therm`` demand, leaving the fuel mix to
    the optimisation. STURM supplies the trajectory shape ``U(y)/U(base)``, the
    calibrated baseline demand supplies the level, so the base year is preserved
    exactly.

    Since W5.6 STURM reports resistive (``electr``) and heat-pump (``elec_hp``)
    electricity explicitly, so every fuel converts with its own technology's
    coefficient (``elec_hp`` uses the MESSAGEix commodity ``electr`` — it is
    electricity on the supply side). Since r7 (B7) the coefficient is looked up
    **per year** rather than frozen at the anchor year; note the residual
    limitation that the received baseline itself keeps ``hp_el_rc`` at 0.40
    (COP 2.5) for every ``year_act``, so the heat-pump conversion only improves
    if that baseline row set is ever re-baked (changelog §22). ``base_hp_share``
    is unused here since W5.6 (kept for signature stability of the loop call).

    ``coefficients`` (the r8 efficiency channel): an explicit
    ``{(fuel, year): coef}`` map replaces the scenario lookup — the loop passes the
    coefficients snapshotted *before* :func:`linkage.digital.apply_digital_efficiency`
    scaled them, so the imposed demand is the calibrated service demand.

    Returns:
        Useful demand (GWa) indexed by year over ``years`` plus ``extra_years``
        (horizon-end value carried forward).
    """
    parsed = split_commodity(report)
    final = parsed[parsed["level"] == "final"].copy()
    final["year"] = final["year"].astype(int)
    final["value"] = pd.to_numeric(final["value"], errors="coerce").fillna(0.0)

    target_years = [int(y) for y in years]
    final = final[final["year"].isin(target_years)]  # stray-year guard
    thermal = final[final["end_use"].isin(THERMAL_END_USES)]
    fuel_year = thermal.groupby(["fuel", "year"], as_index=False)["value"].sum()
    anchor_year = min(target_years)

    present = sorted(set(fuel_year["fuel"]))
    unknown = [f for f in present if f not in FUEL_TO_TECH]
    if unknown:
        raise ValueError(
            f"STURM reports fuel(s) {unknown} with no FUEL_TO_TECH mapping; "
            "extend the vocabulary rather than silently converting at coef 1.0"
        )
    # Per-year coefficients (r7 B7): the pre-r7 conversion froze every fuel's
    # base-year coefficient for all years — for heat pumps a COP of 2.5 through
    # 2110 while both models' stock efficiencies improve, biasing the imposed
    # 2040 demand ~5–15% low (2026-08-28 methodology review, B1). Each (fuel,
    # year) now converts with the technology's own coefficient at that year;
    # the anchor year keeps its own, so the base-year calibration is unchanged.
    report_years = sorted(set(int(y) for y in fuel_year["year"]))
    if coefficients is not None:
        missing_c = [(f, y) for f in present for y in report_years if (f, y) not in coefficients]
        if missing_c:
            raise KeyError(f"coefficient override lacks entries for {missing_c[:6]}")
        coef_fy = {(f, y): float(coefficients[(f, y)]) for f in present for y in report_years}
    else:
        coef_fy = {
            (fuel, year): _require_input_coef(
                scenario, FUEL_TO_TECH[fuel], _fuel_commodity(fuel), int(year)
            )
            for fuel in present
            for year in report_years
        }

    useful = (
        fuel_year.assign(
            useful=lambda d: [
                v / coef_fy[(f, int(y))]
                for v, f, y in zip(d["value"], d["fuel"], d["year"])
            ]
        )
        .groupby("year")["useful"]
        .sum()
    )
    u0 = float(useful.get(anchor_year, 0.0))
    if u0 <= 0:
        raise ValueError(f"STURM reports no thermal energy at the anchor year {anchor_year}")

    dem = scenario.par("demand", {"commodity": "rc_therm"})
    dem = dem.assign(year=dem["year"].astype(int))
    base_rows = dem[dem["year"] == anchor_year]
    if base_rows.empty:
        raise ValueError(f"baseline has no rc_therm demand at {anchor_year}")
    base_demand = float(base_rows["value"].sum())

    # A target year STURM did not report must fail loud, not flat-fill with the
    # anchor value (2026-09-04, external-review adoption — the r7 STURM output
    # covers every target year, so this was never exercised). Deliberate
    # flat-filling exists only for the post-horizon ``extra_years`` below.
    missing = [y for y in target_years if y not in useful.index]
    if missing:
        raise ValueError(f"STURM output has no thermal energy for target year(s) {missing}")
    series = pd.Series(
        {y: base_demand * float(useful[y]) / u0 for y in target_years},
        name="rc_therm_useful",
    )
    last = max(target_years)
    for y in (int(y) for y in extra_years):
        if y > last:
            series[y] = series[last]
    return series.sort_index()
