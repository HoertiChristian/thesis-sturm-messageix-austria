"""Runtime configuration for a linkage run.

Runtime *options* live in the ``config`` sheet of ``data/inputs.xlsx`` — the
single source of truth for every tunable parameter — and are loaded into the
typed :class:`Config` dataclass via :meth:`Config.load`. Scenario *identities* —
the 3×3 pathway × digitalization matrix — are separate data in the ``pathways``
and ``digitalization`` sheets (:mod:`common.scenarios`).

There are no in-code defaults: a missing workbook, sheet, or key raises
immediately rather than silently running a stale configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from common import paths

#: Buildings-sector demand keys in the baseline scenario, in useful energy (GWa):
#: ``rc_therm`` (residential & commercial thermal — space heating, cooling, hot
#: water) and ``rc_spec`` (specific electricity — appliances, lighting). Industry
#: keys (``i_therm``/``i_spec``/``i_feed``) are out of scope.
BUILDINGS_DEMAND_COMMODITIES: tuple[str, ...] = ("rc_therm", "rc_spec")


@dataclass
class Config:
    """Runtime options for one linkage run, read from the ``config`` sheet.

    Every field must be present in the workbook — there are no code defaults.
    Tests and notebooks construct variants via :meth:`Config.load` +
    ``dataclasses.replace`` (or the test-suite ``make_config`` factory).

    Attributes:
        base_year: Model anchor year — STURM's first year and the MESSAGEix base
            year on the 5-year grid. The buildings reference (:attr:`calibration_year`)
            is forward-reconciled to it.
        calibration_year: Vintage of the Statistik Austria buildings reference used as
            the anchor *level* (the closest year with real data). May differ from
            :attr:`base_year`: MESSAGEix is grid-locked to 5-year steps, so an off-grid
            data year (e.g. 2024) is pinned at the nearest model year (e.g. 2025).
        horizon: First and last modelled years, inclusive (5-year resolution).
        max_iterations: Iteration budget for the STURM ⇄ MESSAGEix loop.
        convergence_tol: Stop criterion — L-infinity relative change in the
            ``rc_therm`` useful-demand vector exchanged at the boundary.
        bound_tol: Half-width applied to the static anchor's *projection*-year rows
            (the pathway's one-sided fossil-exit caps and bioenergy floor):
            ``bound_activity_up = target×(1+bound_tol)``, ``…_lo = ×(1-bound_tol)``.
        base_bound_tol: Half-width of the anchor's *base*-year pin. ``0.0`` pins it as
            an equality (``up == lo == target``) — the base year is observed data, so
            it is calibrated tightly to the reference rather than left a wide corridor.
        base_hp_share: Heat-pump fraction of base-year electric space-heating *useful*
            energy. STURM tracks heating by fuel (no resistive/heat-pump split), so the
            base-year split is set here; projection years are left to the model. Set from
            Statistik Austria (Mikrozensus *Energieeinsatz der Haushalte* 2023/24):
            591,874 heat-pump vs 258,086 resistive electrically-heated dwellings →
            0.696 ≈ 0.70 (dwelling-count basis). Does not affect the CO₂ metrics.
        platform_name: ``ixmp`` platform name; ``None`` opens the local default database.
        model_name: MESSAGEix model name (the key the baseline is registered under).
        scenario_name: MESSAGEix scenario name within :attr:`model_name`.
        baseline_xlsx: Path the loader imports from when the scenario is absent;
            ``None`` falls back to :data:`common.paths.BASELINE_XLSX`.
        solve: Keyword arguments forwarded to :meth:`message_ix.Scenario.solve`.
    """

    base_year: int
    calibration_year: int
    horizon: tuple[int, int]

    max_iterations: int
    convergence_tol: float
    bound_tol: float
    base_bound_tol: float
    base_hp_share: float

    #: Add the pathway's carbon tax to the fuel prices STURM receives (W5.3):
    #: ``price += tax_emission(y) × EF_direct(fuel) × 8.76`` ($/kWa). Without it the
    #: tax bites only on the end-use technologies' activity — *downstream* of the
    #: final-level commodity balance the loop reads — so STURM's operating costs
    #: never see the carbon signal (the 2026-07-07 transmission-gap diagnostic:
    #: 120 USD/t left the STURM price vector identical to the last digit).
    carbon_price_passthrough: bool

    #: Under-relaxation factor for the price vector fed to STURM each iteration
    #: (W5.8): ``p_fed = α·p_new + (1−α)·p_fed_prev``. ``1.0`` reproduces the
    #: undamped pre-W5.8 behavior, which limit-cycles once STURM is genuinely
    #: price-responsive (the W5.6 endogenous-DH period-2 oscillation: LP duals are
    #: piecewise-constant in the bounds, STURM's logit shares are near
    #: winner-take-all, so the raw feedback flip-flops between two model states).
    #: ``0.5`` lands the first blend on the midpoint of a period-2 cycle; drop to
    #: ``0.3`` for a stubborn cell (``dataclasses.replace`` in the notebook).
    price_damping: float

    #: STURM ``region_bld`` to run. ``"C-AUT"`` is the Austria-calibrated region
    #: (Statistik Austria / IEA inputs). The old ``"C-WEU-AUT"`` WEU-defaults fallback
    #: was removed by the W5.1 region prune (2026-07-10) — foreign-region rows only
    #: exist only in the development history now.
    sturm_region: str

    #: Functional form of the pathway fossil phase-out (see
    #: :mod:`messageix.pathways`). ``"logistic"`` is the literature-grounded
    #: default (diffusion S-curve); ``"linear"`` is the sensitivity-branch comparator.
    fossil_exit_shape: str

    platform_name: str | None
    model_name: str
    scenario_name: str
    baseline_xlsx: Path | None
    solve: dict[str, Any]

    @property
    def years(self) -> list[int]:
        """Modelled years from :attr:`horizon`, at 5-year resolution."""
        lo, hi = self.horizon
        return list(range(lo, hi + 1, 5))

    @property
    def xlsx_path(self) -> Path:
        """Resolved baseline xlsx, defaulting to :data:`paths.BASELINE_XLSX`."""
        return self.baseline_xlsx or paths.BASELINE_XLSX

    @classmethod
    def load(cls) -> Config:
        """Load run options from the ``config`` sheet of ``data/inputs.xlsx``.

        This is the entry point the CLI and pipeline use. Fails loudly: a missing
        workbook raises :class:`FileNotFoundError` (via the workbook reader) and a
        missing key raises :class:`KeyError` naming every absent key.

        The ``SMX_PLATFORM`` environment variable overrides :attr:`platform_name` —
        a quick way to point every entry point (CLI, notebook) at a private ixmp
        database without editing the workbook (e.g. to avoid a corrupt shared
        default DB on a server: ``export SMX_PLATFORM=my-private-db``).
        """
        from common import workbook

        items = workbook.config_items()
        known = {f.name for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        unknown: list[str] = []
        for key, val in items.items():
            if key == "horizon" and isinstance(val, str):
                lo, hi = (int(x) for x in val.split(","))
                kwargs["horizon"] = (lo, hi)
            elif key == "solve_model":
                kwargs["solve"] = {"model": str(val)}
            elif key in known:
                kwargs[key] = val
            else:
                unknown.append(str(key))
        if unknown:
            raise KeyError(
                f"config sheet of {paths.INPUTS_XLSX} has unknown keys {sorted(unknown)} — "
                f"the run configuration reads only the Config fields (no silent extras)"
            )
        missing = sorted(known - set(kwargs))
        if missing:
            raise KeyError(
                f"config sheet of {paths.INPUTS_XLSX} is missing keys: {missing} "
                f"(horizon is entered as 'lo,hi'; solve as 'solve_model')"
            )
        return cls._coerce(kwargs)._with_platform_env()

    def _with_platform_env(self) -> Config:
        """Return a copy with ``platform_name`` overridden by ``$SMX_PLATFORM`` if set."""
        import dataclasses
        import os

        plat = os.environ.get("SMX_PLATFORM")
        return dataclasses.replace(self, platform_name=plat) if plat else self

    @classmethod
    def _coerce(cls, kwargs: dict[str, Any]) -> Config:
        """Build a Config from raw kwargs, coercing types and blank→None."""
        def _opt(v: Any) -> Any:
            return None if v in ("", None) or (isinstance(v, float) and v != v) else v

        if "horizon" in kwargs and not isinstance(kwargs["horizon"], tuple):
            kwargs["horizon"] = tuple(kwargs["horizon"])
        for k in ("base_year", "calibration_year", "max_iterations"):
            if k in kwargs and kwargs[k] is not None:
                kwargs[k] = int(kwargs[k])
        for k in ("convergence_tol", "bound_tol", "base_bound_tol", "base_hp_share",
                  "price_damping"):
            if k in kwargs and kwargs[k] is not None:
                kwargs[k] = float(kwargs[k])
        for k in ("carbon_price_passthrough",):
            if k in kwargs:
                v = kwargs[k]
                # The workbook cell is hand-editable: a text "false"/"no" must not
                # coerce to True via bool() on a non-empty string.
                if isinstance(v, str):
                    v = v.strip().lower() not in ("false", "no", "0", "")
                kwargs[k] = bool(v)
        if "platform_name" in kwargs:
            kwargs["platform_name"] = _opt(kwargs["platform_name"])
        bx = _opt(kwargs.get("baseline_xlsx"))
        kwargs["baseline_xlsx"] = Path(bx) if bx else None
        return cls(**kwargs)
