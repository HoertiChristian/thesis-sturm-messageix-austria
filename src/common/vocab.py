"""Shared vocabulary of the linkage: tech maps, grid constants, frame schemas.

The single home for the names both halves of the linkage (target derivation and
bound writing), the pathway layer and the reporting layer agree on. Nothing here
touches ixmp.
"""

from __future__ import annotations

#: STURM thermal end-uses summed per fuel into one MESSAGEix end-use technology.
THERMAL_END_USES: frozenset[str] = frozenset({"heat", "cool", "hotwater"})

#: STURM fuel → the single MESSAGEix end-use technology that consumes it to
#: produce ``rc_therm`` (useful). Since W5.6 STURM carries resistive (``electr``)
#: and heat-pump (``elec_hp``) electricity explicitly, so both map like any other
#: fuel; ``sp_el_RC`` is intentionally absent (left free).
FUEL_TO_TECH: dict[str, str] = {
    "gas": "gas_rc",
    "biomass": "biomass_rc",
    "coal": "coal_rc",
    "d_heat": "heat_rc",
    "lightoil": "loil_rc",
    "electr": "elec_rc",
    "elec_hp": "hp_el_rc",
}

#: MESSAGEix ``rc_therm`` technologies with **no STURM carrier** (solar thermal
#: and the minor/future carriers fuel oil, ethanol, methanol, hydrogen). STURM
#: cannot re-allocate demand onto them, so the useful-mode static anchor holds
#: each at its observed base-year level (baseline calibration bound; 0 where
#: none exists) with flat one-sided caps over the horizon — fuel-mix
#: re-allocation happens only among the STURM-represented carriers. Documented
#: vocabulary-alignment decision, 2026-08-25 (changelog §19).
UNCOVERED_RC_TECHS: tuple[str, ...] = (
    "solar_rc",
    "foil_rc",
    "eth_rc",
    "meth_rc",
    "h2_rc",
    "h2_fc_RC",
)

#: Electric-heating technologies (resistive + heat pump). Until W5.6 these were
#: constrained jointly via the ``elec_heat_sturm`` relation; now each has its own
#: per-fuel treatment and the relation machinery is retired (the anchor still
#: clears a stale relation left on an in-place scenario by pre-W5.6 runs).
ELEC_HEAT_TECHS: tuple[str, ...] = ("elec_rc", "hp_el_rc")

#: Name of the (retired) relation that bounded combined electric-heat final energy.
ELEC_HEAT_RELATION: str = "elec_heat_sturm"

#: Baseline relation forcing a minimum liquids share in rc heating: per year,
#: ``15·(loil_rc + eth_rc + meth_rc) − 1·(other rc techs) ≥ 0`` — i.e. liquids
#: ≥ 1/16 of total rc activity. A downscaling inertia artifact of the received
#: MESSAGEix-Austria baseline, not an Austrian policy statement. It contradicts
#: the Kettner oil ban (``loil_rc → 0`` by 2035) once the vocabulary-alignment
#: caps hold ``eth_rc``/``meth_rc`` at ≈0: with all three liquids capped, the
#: relation caps *total* rc supply below the useful demand → presolve-infeasible
#: (diagnosed 2026-08-27, r6 §2b probe). The anchor therefore strips its lower
#: bound over the projection years (changelog §21).
MIN_LIQUIDS_RELATION: str = "min-liquids_res-com"

#: All residential/commercial end-use techs the linkage touches or reports on.
#: De-duplicated (``elec_rc``/``hp_el_rc`` appear in both FUEL_TO_TECH and
#: ELEC_HEAT_TECHS; a duplicate in an ixmp filter is backend-dependent).
RC_END_USE_TECHS: tuple[str, ...] = tuple(
    dict.fromkeys((*FUEL_TO_TECH.values(), *ELEC_HEAT_TECHS, "sp_el_RC"))
)

#: Every technology that supplies ``rc_therm`` — the reporting set for
#: ``activity_rc.csv``, so the exported activities visibly sum to the demand
#: (the uncovered carriers, chiefly ``solar_rc`` at ~0.24 GWa, were previously
#: absent and the table failed to close; 2026-08-28 robustness review, C3).
#: CO₂/final-energy accounting deliberately keeps :data:`RC_END_USE_TECHS`
#: (the uncovered carriers would inject non-reference fuels into the
#: base-year comparison).
RC_REPORTING_TECHS: tuple[str, ...] = tuple(
    dict.fromkeys((*RC_END_USE_TECHS, *UNCOVERED_RC_TECHS))
)

#: MESSAGEix-Austria grid labels shared by every parameter frame the linkage and
#: the pathway layer write.
NODE: str = "Austria"
MODE: str = "M1"
TIME: str = "year"
UNIT: str = "GWa"

#: Columns of the tidy anchor-target frame exchanged between
#: ``useful_anchor_targets``, ``constrain_targets`` and ``apply_useful_anchor``.
TARGET_COLUMNS: list[str] = ["key", "technology", "year", "kind", "value"]

#: Allowed values of the target frame's ``kind`` column.
