"""Write the coupling's boundary quantities onto the scenario (the ixmp half).

Two writers of the useful-energy coupling:

* :func:`apply_useful_demand` per iteration: the STURM-shaped useful total
  replaces the ``rc_therm`` demand; the projection fuel mix is left to the
  optimisation.
* :func:`apply_useful_anchor` once per cell: the **base-year calibration pin**
  and the pathway's **one-sided fossil-exit / bioenergy bounds** (without them
  the base year de-calibrates and a fossil exit cannot bind; see
  :func:`linkage.targets.useful_anchor_targets`), plus the removal of the
  baseline's dynamic activity limits that would collide with them (the uniform
  dynamics rule).

The frames themselves are derived in :mod:`linkage.targets` (pure DataFrame
math); this module holds the scenario mutation: ``bound_activity_{up,lo}``, the
stale electric-heat ``relation`` clean-up, the ``demand`` rewrite and the
dynamic-constraint strip.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

# Shared linkage vocabulary lives in linkage/common.py and the target derivation
# in linkage/targets.py; both are re-exported here because this module has
# historically been their import home (pipeline, pathways, tests).
from common.vocab import (  # noqa: F401  (re-export)
    ELEC_HEAT_RELATION,
    FUEL_TO_TECH,
    MIN_LIQUIDS_RELATION,
    RC_END_USE_TECHS,
    TARGET_COLUMNS,
    THERMAL_END_USES,
)
from common.vocab import MODE as _MODE
from common.vocab import NODE as _NODE
from common.vocab import TIME as _TIME
from common.vocab import UNIT as _UNIT
from linkage.targets import _input_coef  # noqa: F401  (re-export)

if TYPE_CHECKING:
    from message_ix import Scenario

log = logging.getLogger(__name__)


def _row_tol(years: pd.Series, tol: float, base_year: int, base_tol: float) -> pd.Series:
    """Per-row corridor half-width: ``base_tol`` at ``base_year``, else ``tol``.

    The base year carries observed reference levels, so it is pinned tightly
    (``base_tol``, typically ``0.0`` → equality); projection years keep the wider
    ``tol`` corridor.
    """
    is_base = years.astype(int) == base_year
    return is_base.map({True: base_tol, False: tol})


def _bound_frame(
    act: pd.DataFrame, *, side: int, tol: float, base_year: int, base_tol: float
) -> pd.DataFrame:
    """Build a ``bound_activity_*`` frame from ``activity`` target rows.

    ``side`` is ``+1`` for ``bound_activity_up`` and ``-1`` for ``bound_activity_lo``;
    the corridor half-width is per-row (tight at the base year — see :func:`_row_tol`).
    """
    factor = 1.0 + side * _row_tol(act["year"], tol, base_year, base_tol).to_numpy()
    return pd.DataFrame(
        {
            "node_loc": _NODE,
            "technology": act["technology"].to_numpy(),
            "year_act": act["year"].astype(int).to_numpy(),
            "mode": _MODE,
            "time": _TIME,
            "value": act["value"].to_numpy() * factor,
            "unit": _UNIT,
        }
    )


#: The four parameters that drive MESSAGEix's dynamic (period-on-period) activity
#: constraints. message_ix sets ``is_dynamic_activity_{up,lo}`` — which *generate*
#: ``ACTIVITY_CONSTRAINT_{UP,LO}`` — from the presence of *either* the growth *or*
#: the initial parameter, so all four must be cleared to drop the constraint.
_DYNAMIC_ACTIVITY_PARS: tuple[str, ...] = (
    "growth_activity_up",
    "growth_activity_lo",
    "initial_activity_up",
    "initial_activity_lo",
)

#: The up-side pair alone: expansion headroom. Under the r7 uniform rule these
#: are stripped for the fuel techs in *every* pathway (absorbers must be free to
#: cover whatever the demand and caps re-allocate), while the lo-side pair — the
#: no-collapse decline floors that carry the stock inertia — stays except under
#: a colliding zero-cap (see :func:`messageix.pathways.floor_strip_techs`).
_DYNAMIC_UP_PARS: tuple[str, ...] = ("growth_activity_up", "initial_activity_up")
_DYNAMIC_LO_PARS: tuple[str, ...] = ("growth_activity_lo", "initial_activity_lo")


def _relax_dynamic_constraints(
    scenario: Scenario, techs: list[str], years: set[int],
    params: tuple[str, ...] = _DYNAMIC_ACTIVITY_PARS,
) -> None:
    """Drop the baseline's dynamic (relative) activity limits on the techs/years we pin.

    The anchor's bounds are *absolute* activity constraints; the baseline's dynamic
    constraints (``ACTIVITY_CONSTRAINT_{UP,LO}``) are *relative* (period-on-period)
    ones, e.g. ``heat_rc`` may not fall below its previous-period activity. Left in
    place they fight the absolute bound — district heat's no-decline floor
    (~1.97 GWa) exceeds an anchored cap, making the solve infeasible.

    The dynamic constraints are generated wherever ``is_dynamic_activity_{up,lo}``
    is set, and message_ix sets that from *either* the ``growth_*`` *or* the
    ``initial_*`` parameter — so a side is only truly dropped when both its
    parameters go (:data:`_DYNAMIC_UP_PARS` / :data:`_DYNAMIC_LO_PARS`; the
    default ``params`` clears all four). Removal covers the cross-product of the
    touched technologies × the union of touched years — deliberately broader than
    the exact bounded (tech, year) pairs. Every other technology keeps its
    dynamics. Which sides are stripped where is the r7 **uniform rule** — see
    :func:`apply_useful_anchor` step 2.

    All four parameters share the index ``(node_loc, technology, year_act, time)``.
    """
    for parname in params:
        existing = scenario.par(parname, {"technology": techs})
        if existing.empty:
            continue
        existing = existing[existing["year_act"].astype(int).isin(years)]
        if not existing.empty:
            scenario.remove_par(
                parname, existing[["node_loc", "technology", "year_act", "time"]]
            )


def _write_activity_bounds(
    scenario: Scenario,
    act: pd.DataFrame,
    *,
    tol: float,
    base_year: int | None,
    base_tol: float,
    lower: bool,
    cap_only: set[str],
    floor_only: set[str] | None = None,
) -> None:
    """Replace ``bound_activity_{up,lo}`` for the touched techs/years from ``act`` rows.

    ``bound_activity_*`` is indexed by ``(node_loc, technology, year_act, mode, time)``;
    only the modelled years are replaced (incl. the reference-calibrated base year),
    leaving historical years and every other technology untouched. The lower side skips
    ``cap_only`` techs in *projection* years only (the base year keeps its two-sided
    equality pin — a fossil exit is a future ceiling, not a base-year change); the upper
    side symmetrically skips ``floor_only`` techs there (a bioenergy floor must not also
    cap expansion). Clearing the existing bound first is also how a one-sided tech's
    baseline bound on the other side is dropped.
    """
    floor_only = floor_only or set()
    techs = sorted(act["technology"].unique())
    years = {int(y) for y in act["year"]}
    _by = base_year if base_year is not None else -1
    specs = [("bound_activity_up", +1)]
    if lower:
        specs.append(("bound_activity_lo", -1))
    for parname, side in specs:
        existing = scenario.par(parname, {"technology": techs})
        if not existing.empty:
            existing = existing[existing["year_act"].astype(int).isin(years)]
            if not existing.empty:
                scenario.remove_par(
                    parname, existing[["node_loc", "technology", "year_act", "mode", "time"]]
                )
        # Use the sentinel (_by) so base_year=None keeps well-defined semantics:
        # no pinned base year → one-sided techs get no bound on the skipped side
        # in any year.
        skip = floor_only if side > 0 else cap_only
        add_act = act[~(act["technology"].isin(skip) & (act["year"].astype(int) != _by))]
        if not add_act.empty:
            scenario.add_par(
                parname, _bound_frame(add_act, side=side, tol=tol, base_year=_by, base_tol=base_tol)
            )


#: The three parameters that define the combined electric-heat relation, with the
#: index columns to remove a row by.
_ELEC_RELATION_PARS: tuple[tuple[str, list[str]], ...] = (
    ("relation_activity",
     ["relation", "node_rel", "year_rel", "node_loc", "technology", "year_act", "mode"]),
    ("relation_upper", ["relation", "node_rel", "year_rel"]),
    ("relation_lower", ["relation", "node_rel", "year_rel"]),
)


def _clear_elec_relation(scenario: Scenario) -> None:
    """Remove the combined electric-heat relation entirely (bounds + coefficients).

    Used when a run emits no relation rows so a relation written by a previous run
    on the same in-place scenario does not linger and keep electric heat pinned.
    """
    for parname, idx in _ELEC_RELATION_PARS:
        existing = scenario.par(parname, {"relation": ELEC_HEAT_RELATION})
        if not existing.empty:
            scenario.remove_par(parname, existing[idx])


def _strip_min_liquids_floor(scenario: Scenario, base_year: int) -> None:
    """Disable the baseline minimum-liquids-share relation over the projection years.

    ``min-liquids_res-com`` forces liquids (``loil_rc``/``eth_rc``/``meth_rc``) to
    ≥ 1/16 of total rc heating activity in every year — a downscaling inertia
    artifact of the received baseline (see
    :data:`~common.vocab.MIN_LIQUIDS_RELATION`). Under a fossil-exit pathway the
    oil ban zeroes ``loil_rc`` while the vocabulary-alignment caps hold
    ``eth_rc``/``meth_rc`` at ≈0, so the relation caps *total* rc supply below the
    imposed useful demand — presolve-proven infeasible (r6 §2b probe,
    2026-08-27). In r5 bounds mode the same relation was satisfied invisibly by
    phantom ``eth_rc``/``meth_rc`` activity excluded from every report.

    Removing only the ``relation_lower`` rows at ``year_rel > base_year`` disables
    the floor (the relation has no upper bound) while keeping the base-year row —
    the calibration pin satisfies it there — and leaving the accounting
    coefficients in place. Applied in every cell, Reference included: an artifact
    liquids floor in one pathway but not another would distort the RQ1 comparison,
    and Reference's oil inertia is already carried by the kept baseline growth
    dynamics. (The archived r5 hard-linkage results satisfied the relation
    invisibly through phantom liquids activity — documented in the thesis.)
    """
    existing = scenario.par("relation_lower", {"relation": MIN_LIQUIDS_RELATION})
    if existing.empty:
        return
    existing = existing[existing["year_rel"].astype(int) > base_year]
    if not existing.empty:
        scenario.remove_par("relation_lower", existing[["relation", "node_rel", "year_rel"]])


def apply_useful_demand(scenario: Scenario, demand: pd.Series, *, commit: str) -> None:
    """Write the ``rc_therm`` useful-demand trajectory (soft coupling, W5.4).

    The STURM-shaped useful total (:func:`linkage.targets.sturm_to_useful_demand`)
    replaces the baseline ``demand`` values on the given years and the fuel mix
    stays free — no bounds are written, no dynamic constraints stripped. The caller passes projection
    years only: the base-year demand row is the calibration and is never touched
    (the useful series equals it at the anchor by construction).

    Args:
        scenario: The MESSAGEix-Austria scenario (checked out and committed here).
        demand: Useful demand (GWa) indexed by year — projection/extra years only.
        commit: Commit message recorded on the scenario.
    """
    dem = scenario.par("demand", {"commodity": "rc_therm"})
    if dem.empty:
        raise ValueError("baseline has no rc_therm demand rows")
    template = dem.iloc[0]
    rows = pd.DataFrame(
        {
            "node": template["node"],
            "commodity": "rc_therm",
            "level": template["level"],
            "year": [int(y) for y in demand.index],
            "time": template["time"],
            "value": [float(v) for v in demand.to_numpy()],
            "unit": template["unit"],
        }
    )
    scenario.check_out()
    try:
        scenario.add_par("demand", rows)
    except Exception:
        scenario.discard_changes()
        raise
    scenario.commit(commit)


def apply_useful_anchor(
    scenario: Scenario,
    frame: pd.DataFrame,
    *,
    tol: float,
    base_year: int,
    base_tol: float,
    commit: str,
    cap_only: set[str] | None = None,
    floor_only: set[str] | None = None,
    floor_strip: set[str] | None = None,
) -> None:
    """Write the useful-mode static layer: base-year pin + one-sided pathway bounds.

    The once-per-cell companion of :func:`apply_useful_demand` (which only rewrites
    the projection ``demand``). Takes the frame from
    :func:`linkage.targets.useful_anchor_targets` — after
    :func:`messageix.pathways.constrain_targets` has ramped the fossil rows — and,
    inside one commit:

    1. **Hygiene reset**: every ``bound_activity_{up,lo}`` row on the linkage's
       fuel techs *and every tech the frame bounds* (incl. the uncovered
       carriers, :data:`~common.vocab.UNCOVERED_RC_TECHS`) at
       ``year_act ≥ base_year`` is removed, plus any stale electric-heat
       relation. Cells share one ixmp scenario across a batch; a cell run after
       another pathway's anchor would otherwise silently inherit the previous
       cell's caps. The baseline's own pre-base calibration bounds (2020)
       survive; ``sp_el_RC`` is never touched (deliberately outside the
       linkage). The
       baseline's minimum-liquids-share relation is disabled over the
       projection years in every useful cell
       (:func:`_strip_min_liquids_floor` — it collides with the fossil-exit
       caps and was only ever satisfied by phantom liquids carriers).
    2. **Dynamic-constraint strip — the r7 uniform rule (decision 2026-08-29)**:
       the pinned techs at the base year always (all four parameters, so the
       equality pin binds cleanly); then, identically in *every* pathway, the
       **up-side** dynamics (:data:`_DYNAMIC_UP_PARS`) are stripped from all
       fuel techs and all frame techs over the projection years (absorbers must
       be free to expand into whatever the demand and caps re-allocate), while
       the **lo-side** decline floors (:data:`_DYNAMIC_LO_PARS`) — the stock
       inertia — are kept everywhere except on ``floor_strip`` techs (the
       fossil-exit set from :func:`messageix.pathways.floor_strip_techs`, whose
       caps decline to zero below any floor). The constraint *rule* is thus the
       same in every cell; only the dials differ — the pre-r7 asymmetry
       (Reference with full inertia, capped pathways with none) is retired
       (2026-08-28 reviews, finding A3/7e).
    3. **Bound write**: base year two-sided at ``base_tol`` (equality pin);
       projection rows one-sided per ``cap_only`` (fossil exit ceilings) /
       ``floor_only`` (bioenergy floor).

    No-op on an empty frame (no anchor source — e.g. stubbed test scenarios).

    Args:
        scenario: The MESSAGEix-Austria scenario (checked out and committed here).
        frame: Anchor targets (:data:`~common.vocab.TARGET_COLUMNS`), pathway-ramped.
        tol: Corridor half-width for projection-year rows.
        base_year: The calibration year (pinned at ``base_tol``).
        base_tol: Corridor half-width at ``base_year`` (``0.0`` → equality pin).
        commit: Commit message recorded on the scenario.
        cap_only: Techs whose projection rows are upper caps only.
        floor_only: Techs whose projection rows are lower floors only.
        floor_strip: Techs whose lo-side dynamics (decline floors) are stripped
            over the projection years — the fossil-exit set under the r7
            uniform rule (:func:`messageix.pathways.floor_strip_techs`).
    """
    if frame.empty:
        log.info("Useful-mode anchor: empty target frame (no anchor source); skipping.")
        return
    cap_only = cap_only or set()
    floor_only = floor_only or set()
    act = frame[frame["kind"] == "activity"]
    # Hygiene covers the fuel techs AND every tech the frame bounds (since the
    # vocabulary alignment the uncovered carriers carry their own flat caps).
    linkage_techs = sorted(set(FUEL_TO_TECH.values()) | set(act["technology"]))

    if scenario.has_solution():
        scenario.remove_solution()
    scenario.check_out()
    try:
        for parname in ("bound_activity_up", "bound_activity_lo"):
            existing = scenario.par(parname, {"technology": linkage_techs})
            if not existing.empty:
                existing = existing[existing["year_act"].astype(int) >= base_year]
                if not existing.empty:
                    scenario.remove_par(
                        parname,
                        existing[["node_loc", "technology", "year_act", "mode", "time"]],
                    )
        _clear_elec_relation(scenario)
        _strip_min_liquids_floor(scenario, base_year)

        proj = act[act["year"].astype(int) > base_year]
        proj_years = {int(y) for y in proj["year"]}
        _relax_dynamic_constraints(
            scenario, sorted(set(act["technology"])), {base_year}
        )
        if proj_years:
            # r7 uniform rule (see the docstring): up-side freed everywhere,
            # decline floors kept except under colliding zero-caps.
            uniform = sorted(set(FUEL_TO_TECH.values()) | set(act["technology"]))
            _relax_dynamic_constraints(scenario, uniform, proj_years, params=_DYNAMIC_UP_PARS)
            strip_lo = sorted((floor_strip or set()) & set(uniform))
            if strip_lo:
                _relax_dynamic_constraints(scenario, strip_lo, proj_years, params=_DYNAMIC_LO_PARS)

        _write_activity_bounds(
            scenario, act, tol=tol, base_year=base_year, base_tol=base_tol,
            lower=True, cap_only=cap_only, floor_only=floor_only,
        )
        scenario.commit(commit)
    except Exception:
        scenario.discard_changes()
        raise
