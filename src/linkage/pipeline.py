"""Top-level orchestration: build, link and solve the scenario matrix.

One clear flow per matrix cell (:func:`run_scenario`):

1. open the ixmp platform and load the MESSAGEix-Austria baseline
   (:mod:`messageix.build`);
2. apply the pathway's constraints (:mod:`messageix.pathways`);
3. run the iterative STURM ⇄ MESSAGEix linkage — STURM final energy → useful
   demand → solve → commodity-price feedback, repeated to convergence
   (:func:`linkage.loop.run`);
4. write a reproducibility sidecar and the result tables (this module's
   ``_write_reports``).

Run via the ``sturm-messageix`` CLI or ``python -m linkage.pipeline``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from common import paths
from common.config import BUILDINGS_DEMAND_COMMODITIES, Config
from common.paths import run_dir
from common.reference import reference_by_fuel
from common.scenarios import Scenario, matrix
from common.validation.base_year import compare_by_fuel
from common.vocab import RC_END_USE_TECHS, RC_REPORTING_TECHS, UNCOVERED_RC_TECHS
from linkage import loop
from messageix import (
    activity_by_tech,
    build,
    buildings_co2,
    buildings_co2_by_fuel,
    buildings_co2_endogenous,
    buildings_final_energy_by_fuel,
    emission_factors,
    emission_price,
    final_energy_by_fuel,
    pathways,
    system_co2,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    import ixmp
    import pandas as pd
    from message_ix import Scenario as MsgScenario

    from linkage.convergence import ConvergenceStatus

log = logging.getLogger(__name__)

#: Power-sector techs exported to ``activity_electricity.csv`` — documents the
#: supply-dial effects (EAG PV in, coal/oil out, gas residual) and the fate of the
#: forced renewables (curtailment/absorption), which final-energy tables cannot show.
POWER_TECHS: tuple[str, ...] = (
    *(f"solar_res{i}" for i in range(1, 9)),
    *(f"wind_res{i}" for i in range(1, 5)),
    *(f"wind_res_hist_{y}" for y in (2000, 2005, 2010, 2015, 2020, 2025)),
    *(f"solar_res_hist_{y}" for y in (2000, 2005, 2010, 2015, 2020, 2025)),
    "hydro_hc", "hydro_lc", "bio_ppl", "bio_istig",
    "gas_cc", "gas_ppl", "gas_ct", "coal_ppl", "coal_adv", "igcc",
    "foil_ppl", "loil_ppl", "loil_cc",
    "solar_curtailment1", "solar_curtailment2", "solar_curtailment3",
    "wind_curtailment1", "wind_curtailment2", "wind_curtailment3",
    "stor_ppl", "h2_elec", "elec_exp_eurasia", "elec_exp_eur_afr",
    "elec_imp_eurasia", "elec_imp_eur_afr",
)



def run_id(scenario: Scenario, config: Config) -> str:
    """Output-folder id for a cell: the scenario id, plus a variant suffix.

    Non-default run variants must not overwrite the matrix folders: a
    sensitivity run with ``fossil_exit_shape != "logistic"`` gets a
    ``__shape-<shape>`` suffix and a once-through diagnostic an ``__once``
    suffix. The defaults keep the plain scenario id, so the matrix folders
    always hold headline runs. The viz collectors treat suffixed folders as
    non-matrix runs; a folder's full configuration is in its meta.json sidecar.
    """
    rid = scenario.id
    if config.fossil_exit_shape != "logistic":
        rid += f"__shape-{config.fossil_exit_shape}"
    if config.max_iterations == 1:
        rid += "__once"  # once-through diagnostic (no price feedback)
    return rid


def _write_sidecar(
    scenario: Scenario, config: Config, conv: ConvergenceStatus | None = None
) -> None:
    """Write the ``*.meta.json`` reproducibility sidecar.

    Since 2026-09-04 (external-review adoption) the sidecar is a small
    manifest: scenario id, timestamp, the full resolved config, the loop's
    :class:`~linkage.convergence.ConvergenceStatus`, the git state, and sha256
    prefixes of the two input workbooks — a result folder authenticates itself
    without the runlog.
    """
    rid = run_id(scenario, config)
    meta = {
        "scenario_id": scenario.id,
        "run_id": rid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "convergence": None if conv is None else conv._asdict(),
        "git": _git_state(),
        "input_hashes": _input_hashes(),
    }
    path = run_dir(rid) / f"{rid}.meta.json"
    path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")


def _git_state() -> dict[str, object]:
    """Commit/dirty state of the repo at run time (best-effort, never fatal)."""
    import subprocess

    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=paths.ROOT,
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=paths.ROOT,
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip())
        return {"commit": head, "dirty": dirty}
    except Exception:
        return {"commit": None, "dirty": None}


def _input_hashes() -> dict[str, str]:
    """sha256 prefixes of the input workbooks (self-authenticating results)."""
    import hashlib

    out: dict[str, str] = {}
    for name, p in (
        ("inputs.xlsx", paths.INPUTS_XLSX),
        ("baseline_4.xlsx", paths.BASELINE_XLSX),
        ("macko_reduction.xlsx", paths.MACKO_XLSX),
    ):
        try:
            out[name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        except OSError:
            out[name] = "unavailable"
    return out


def _base_year_check(msg: MsgScenario, config: Config) -> pd.DataFrame:
    """Per-fuel base-year **pin-integrity** table (NOT out-of-sample validation).

    In useful mode the anchor pins activity to ``reference / input_coef``, so this
    ``ACT × input_coef`` comparison is circular by construction — it verifies the
    pin was applied, nothing more (2026-08-28 reviews, A3/B3; the genuine
    validation is :func:`_inventory_check`). Kept because a non-zero row is a
    hard signal the pin failed to bind. Mechanically: modelled
    :func:`messageix.buildings_final_energy_by_fuel` at
    ``config.base_year`` against
    :func:`common.reference.reference_by_fuel` at
    ``config.calibration_year``. When the two years differ this is the
    forward-reconciled check — the off-grid reference vintage compared against the
    nearest model year; the ±3 % band absorbs the drift. Raises (and is thus skipped
    + logged by the exporter guard) if the reference data is absent.
    """
    model_fe = buildings_final_energy_by_fuel(msg, RC_END_USE_TECHS)
    modelled = (
        model_fe[model_fe["year"] == config.base_year].set_index("fuel")["value"].to_dict()
    )
    reference = reference_by_fuel(config.calibration_year).to_dict()
    return compare_by_fuel(modelled, reference, base_year=config.base_year)


def _inventory_check(msg: MsgScenario, config: Config) -> pd.DataFrame:
    """Out-of-sample validation: modelled base-year CO₂ vs the UBA Gebäude inventory.

    The r7 replacement for treating the (circular) ``base_year_check`` as
    validation — see :mod:`common.validation.inventory`.
    """
    from common.validation.inventory import compare_to_inventory

    co2 = buildings_co2(msg, RC_END_USE_TECHS)
    modelled = float(co2.loc[co2["year"] == config.base_year, "value"].iloc[0])
    return compare_to_inventory(modelled, config.base_year)


def _write_reports(msg: MsgScenario, scenario: Scenario, config: Config) -> None:
    """Export the solved scenario's result tables to ``run_dir(run_id(scenario, config))``.

    Each table is written independently and guarded: a missing or empty result
    (e.g. the reference workbook absent) is logged and skipped rather than aborting
    the run or the other exports.

    Args:
        msg: The solved MESSAGEix-Austria scenario.
        scenario: The matrix cell (supplies the output directory via its id).
        config: Run configuration (supplies the base year for the check).
    """
    out = run_dir(run_id(scenario, config))
    exporters = {
        "demand_buildings.csv": lambda: msg.par("demand").pipe(
            lambda d: d[d["commodity"].isin(BUILDINGS_DEMAND_COMMODITIES)]
        ),
        "price_commodity_final.csv": lambda: msg.var(
            "PRICE_COMMODITY", {"level": "final"}
        ),
        "buildings_co2.csv": lambda: buildings_co2(msg, RC_END_USE_TECHS),
        "buildings_co2_by_fuel.csv": lambda: buildings_co2_by_fuel(msg, RC_END_USE_TECHS),
        "buildings_co2_consumption.csv": lambda: buildings_co2(
            msg, RC_END_USE_TECHS, factors=emission_factors("total")
        ),
        "buildings_co2_endogenous.csv": lambda: buildings_co2_endogenous(msg),
        "price_emission.csv": lambda: emission_price(msg),
        "system_co2.csv": lambda: system_co2(msg),
        "final_energy_by_fuel.csv": lambda: final_energy_by_fuel(msg),
        "buildings_final_energy_by_fuel.csv": lambda: buildings_final_energy_by_fuel(msg, RC_END_USE_TECHS),
        "activity_rc.csv": lambda: activity_by_tech(msg, RC_REPORTING_TECHS),
        "activity_electricity.csv": lambda: activity_by_tech(msg, POWER_TECHS),
        "base_year_check.csv": lambda: _base_year_check(msg, config),
        "inventory_check.csv": lambda: _inventory_check(msg, config),
    }
    for name, fetch in exporters.items():
        try:
            fetch().to_csv(out / name, index=False)
        except Exception:
            log.warning("Could not export %s for %s", name, scenario.id, exc_info=True)


def run_scenario(
    scenario: Scenario, config: Config, platform: ixmp.Platform | None = None
) -> None:
    """Build, link and solve a single scenario cell, then write its outputs.

    Args:
        scenario: The pathway × digitalization combination to run.
        config: Run configuration.
        platform: An already-open ``ixmp`` platform to reuse. ``None`` opens a fresh
            one for this cell. **Reuse a single platform across cells** when running
            several (see :func:`run_scenarios`): the JDBC/HSQLDB backend corrupts its
            on-disk text store across repeated open→close→reopen cycles in one
            process, so opening a new platform per cell can fail to reopen the DB.
    """
    log.info("Running %s", run_id(scenario, config))

    platform = platform or build.get_platform(config)
    msg = build.load_base_scenario(config, platform)
    pathways.apply_pathway(msg, scenario.pathway)
    msg, conv = loop.run(msg, config, scenario.digitalization, scenario.pathway)

    _write_sidecar(scenario, config, conv)
    _write_reports(msg, scenario, config)
    _snapshot_sturm_artifacts(scenario, config)
    _log_base_year_supply_residual(msg, scenario, config)


def _snapshot_sturm_artifacts(scenario: Scenario, config: Config) -> None:
    """Copy this cell's STURM report + fed-price CSVs into its run folder.

    The files under ``results/sturm/`` are keyed by the STURM scenario *column*
    only, so two cells sharing a column (e.g. ``reference`` and ``ref_tax120``,
    both ``SSP2``) overwrite each other — after a batch the
    on-disk STURM artifacts belong to whichever cell ran last (2026-08-28
    robustness review, C8). The per-cell snapshot restores auditability.
    """
    import shutil

    from linkage.loop import sturm_scenario_name

    sturm_scenario = sturm_scenario_name(scenario.pathway)
    out = run_dir(run_id(scenario, config))
    for name in (
        f"report_MESSAGE_resid_{sturm_scenario}.csv",
        f"_prices_resid_{sturm_scenario}.csv",
    ):
        src = paths.STURM_OUTPUT / name
        if src.exists():
            shutil.copy2(src, out / f"sturm_{name.lstrip('_')}")


def _log_base_year_supply_residual(msg: MsgScenario, scenario: Scenario, config: Config) -> None:
    """Report the base-year ``rc_therm`` supply-vs-demand residual, loudly.

    The base-year equality pins sum to the reference-implied useful total,
    which exceeds the baseline's ``rc_therm`` demand row by ~15 % (the surplus
    is free-disposed under the GT balance) — the 2026-08-28 methodology-review
    blocker A1. Logged as a warning, not an assertion: the mismatch is a
    property of the received baseline, and this instrumentation exists so no
    future batch can run without the number being in the log.
    """
    try:
        act = msg.var("ACT", {"year_act": config.base_year})
        rc = act[act["technology"].isin(RC_END_USE_TECHS + UNCOVERED_RC_TECHS)]
        rc = rc[rc["technology"] != "sp_el_RC"]
        supply = float(rc["lvl"].sum())
        dem = msg.par("demand", {"commodity": "rc_therm"})
        demand = float(dem[dem["year"].astype(int) == config.base_year]["value"].sum())
        if demand > 0:
            log.warning(
                "Base-year rc_therm supply %.3f GWa vs demand %.3f GWa (residual %+.1f%%) "
                "— pinned surplus is free-disposed; see the 2026-08-28 review, A1.",
                supply, demand, (supply / demand - 1) * 100,
            )
    except Exception:
        log.warning("Could not compute the base-year supply residual", exc_info=True)


def run_scenarios(
    scenarios: Iterable[Scenario], config: Config, platform: ixmp.Platform | None = None
) -> None:
    """Run several cells reusing **one** ``ixmp`` platform (the safe way to batch).

    Opening a new platform per cell can corrupt/fail to reopen the HSQLDB file store
    in a long-running process; a single shared platform avoids every reopen. Outputs
    are written per cell as each finishes, so a later failure never loses earlier
    results.

    Args:
        scenarios: The cells to run.
        config: Run configuration.
        platform: An open platform to reuse; ``None`` opens one here and reuses it.
    """
    platform = platform or build.get_platform(config)
    for scenario in scenarios:
        run_scenario(scenario, config, platform=platform)


def run_matrix(config: Config | None = None) -> None:
    """Run every cell of the 3×3 scenario matrix, reusing one platform.

    Args:
        config: Run configuration; ``Config.load()`` if omitted (the ``config``
            sheet of ``data/inputs.xlsx``).
    """
    config = config or Config.load()
    run_scenarios(matrix(), config)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_matrix()
