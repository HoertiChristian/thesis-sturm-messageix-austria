"""Obtain and prepare the MESSAGEix-Austria base scenario.

MESSAGEix-Austria is a :class:`message_ix.Scenario` loaded from the IIASA Austria
guideline baseline workbook (:data:`common.paths.BASELINE_XLSX`; see
``data/README.md`` for how to obtain it). Acquisition is load-or-import: if the
scenario already exists on the platform it is returned as-is; otherwise it is
created from the workbook via :meth:`message_ix.Scenario.read_excel`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from common import paths
from common.config import Config
from messageix.ixmp_utils import has_co2

if TYPE_CHECKING:
    import ixmp
    import pandas as pd
    from message_ix import Scenario

log = logging.getLogger(__name__)


def get_platform(config: Config) -> ixmp.Platform:
    """Open the ``ixmp`` platform for the run.

    Args:
        config: Run configuration; :attr:`Config.platform_name` selects the
            platform (``None`` → the local default database).

    Returns:
        An open :class:`ixmp.Platform`.
    """
    try:
        import ixmp
    except ImportError as exc:  # core install only
        raise ImportError(
            "ixmp/message_ix are not installed — building and solving scenarios needs the "
            "model extra: pip install -e '.[model]' (plus a GAMS licence and a Java runtime)"
        ) from exc

    return ixmp.Platform(name=config.platform_name) if config.platform_name else ixmp.Platform()


def load_base_scenario(config: Config, platform: ixmp.Platform) -> Scenario:
    """Import the guideline MESSAGEix-Austria baseline — fresh, on every call.

    Deliberately **no caching**: each cell of a batch gets its own pristine
    import from :attr:`Config.xlsx_path` (~25 s), so no pathway dial, anchor
    bound, dynamics strip or carbon policy can leak from one cell into the
    next. (A cache lookup existed here until 2026-08-28 but could never hit —
    nothing ever called ``set_as_default()``, so ``platform.scenario_list()``
    returned no default versions. The r6 batch's cell isolation rested on that
    accident; it is now the documented design. See the 2026-08-28 robustness
    review, finding A2.)

    Calibration is **not** performed here. The baseline workbook ships pre-calibrated
    (``firstmodelyear`` advanced to the base year, ``rc_spec`` demand reconciled to
    STATcube — see ``docs/data/calibration_changelog.md`` and the workbook's
    ``provenance`` sheet; the bake tooling is not part of this repository).
    On import this only **validates** that
    calibration via :func:`_assert_baseline_calibrated`, which raises if an uncalibrated
    workbook (e.g. a pre-calibration baseline) is loaded. No solve, no GAMS licence.

    Args:
        config: Run configuration.
        platform: Open ``ixmp`` platform.

    Returns:
        The base :class:`message_ix.Scenario`, before pathway constraints.
    """
    from message_ix import Scenario

    xlsx = paths.require_restricted(config.xlsx_path, "MESSAGEix-Austria baseline workbook")
    log.info("Importing %s/%s from %s", config.model_name, config.scenario_name, xlsx)
    scen = Scenario(platform, config.model_name, config.scenario_name, version="new")
    scen.read_excel(xlsx, add_units=True, commit_steps=True, init_items=True)
    _assert_baseline_calibrated(scen, config)
    return scen


def _assert_baseline_calibrated(scenario: Scenario, config: Config) -> None:
    """Verify the imported baseline already carries the offline calibration.

    Calibration is baked into the input workbook offline (recorded in
    ``docs/data/calibration_changelog.md``); the runtime only imports and validates
    it — it must not re-calibrate in-process. Raises a ``RuntimeError`` if an
    uncalibrated baseline is loaded, rather than silently rescaling.

    Checks:
      1. ``firstmodelyear`` already equals ``config.base_year``;
      2. base-year ``rc_spec`` final electricity (``demand × coef``) is within
         :func:`~common.validation.base_year.tolerance` of the STATcube
         reference.

    The rc_spec check is skipped (with a warning) when the reference, base-year
    demand, or end-use coefficient is unavailable/zero — the same guard the
    retired reconciliation bake used (not part of this repository).
    """
    from common.validation.base_year import tolerance

    tol = tolerance()

    name = config.xlsx_path.name
    hint = (
        "restore the baked data/MESSAGEix-AT_baseline_4.xlsx from the repository "
        "(see docs/data/calibration_changelog.md; bake tooling in pre-refactor history)"
    )

    fmy = int(scenario.firstmodelyear)
    if fmy != config.base_year:
        raise RuntimeError(
            f"Baseline firstmodelyear {fmy} != base_year {config.base_year}: the loaded "
            f"workbook ({name}) is not pre-calibrated; {hint}."
        )

    ref, _, base_val, coef = _rc_spec_calibration_inputs(scenario, config)
    if ref <= 0 or base_val <= 0 or coef <= 0:
        log.warning(
            "rc_spec calibration check skipped: reference=%s, base=%s, coef=%s", ref, base_val, coef
        )
        return

    modelled_final = base_val * coef
    deviation = abs(modelled_final - ref) / ref
    if deviation > tol:
        raise RuntimeError(
            f"Baseline rc_spec is not calibrated: base-year final electricity "
            f"{modelled_final:.4f} GWa deviates {deviation:.1%} from the STATcube reference "
            f"{ref:.4f} GWa (tolerance {tol:.0%}). The loaded workbook ({name}) is not "
            f"pre-calibrated; {hint}."
        )
    log.info(
        "Baseline calibration verified: firstmodelyear=%d; rc_spec base-year final %.4f GWa "
        "within %.0f%% of reference %.4f GWa.",
        fmy, modelled_final, tol * 100, ref,
    )

    # Endogenous buildings emissions (CO2 emission_factor on the rc techs) are baked
    # separately. Unlike the rc_spec/firstmodelyear calibration — shipped in baseline_4 —
    # this addition may post-date the on-disk workbook, so a missing bake is a WARNING
    # (post-hoc CO2 still works; only endogenous EMISS / carbon policy are unavailable),
    # not a hard failure that would block every run.
    if not has_co2(scenario):
        log.warning(
            "Baseline %s carries no CO2 emission_factor: endogenous buildings emissions and "
            "carbon-policy pathways are inert. Restore the baked workbook from the repository "
            "(see docs/data/baseline_4_changelog.md).",
            name,
        )


def _rc_spec_calibration_inputs(
    scenario: Scenario, config: Config
) -> tuple[float, pd.DataFrame, float, float]:
    """The shared inputs of the rc_spec calibration check and reconciliation.

    Returns:
        ``(ref, demand, base_val, coef)`` — the STATcube reference *final*
        electricity (GWa) at ``config.calibration_year``, the full ``rc_spec``
        ``demand`` frame, its base-year *useful* sum, and the ``sp_el_RC``
        final-per-useful input coefficient at the base year.
    """
    from common.reference import reference_commodity_total

    ref = reference_commodity_total("rc_spec", config.calibration_year)
    demand = scenario.par("demand", {"commodity": "rc_spec"})
    base = demand[demand["year"].astype(int) == config.base_year]
    base_val = float(base["value"].sum())
    coef = _sp_el_input_coef(scenario, config.base_year)
    return ref, demand, base_val, coef


def _sp_el_input_coef(scenario: Scenario, year: int) -> float:
    """``sp_el_RC`` electricity input coefficient (final per useful) for ``year``.

    Picks the same-year coefficient (on ``year_act``), else the latest operating
    year at/before ``year``, else the mean; ``0.0`` if ``sp_el_RC`` has no
    ``input`` rows — so the caller's calibration-check skip guard
    (``coef <= 0``) actually fires instead of silently checking at an identity
    coefficient (2026-08-28 robustness review, B5).
    """
    inp = scenario.par("input", {"technology": "sp_el_RC", "commodity": "electr", "level": "final"})
    if inp.empty:
        return 0.0
    same = inp[inp["year_act"].astype(int) == year]
    if not same.empty:
        return float(same["value"].mean())
    prior = inp[inp["year_act"].astype(int) <= year]
    if not prior.empty:
        latest = prior["year_act"].astype(int).max()
        return float(prior[prior["year_act"].astype(int) == latest]["value"].mean())
    return float(inp["value"].mean())
