"""Typed access to the scenario matrix in ``data/inputs.xlsx``.

The matrix is data, not code: this module only loads, types, and iterates the
``pathways`` and ``digitalization`` sheets.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class Pathway:
    """A climate-neutrality pathway (a column of the scenario matrix)."""

    id: str
    label: str
    fossil_exit_year: int | None
    bioenergy_share_target_2040: str | None
    #: Flat carbon price (USD/tCO₂) imposed on the ``GHG`` emission type via
    #: ``tax_emission`` in :func:`messageix.pathways.apply_pathway`.
    #: ``None`` → no carbon tax. Requires the baseline emission bake (CO₂ ``emission_factor``).
    carbon_price: float | None = None
    #: Id of a carbon-price *time path* in the workbook's ``carbon_price_paths``
    #: sheet (r7 B2: the legislated NEHG/ETS2 path on the Reference). Written as
    #: per-year ``tax_emission`` rows, last path year carried forward. Mutually
    #: exclusive with the flat ``carbon_price``.
    carbon_price_path: str | None = None
    #: Wilson-band demand modifier (r7 B8): scales the useful-mode ``rc_therm``
    #: demand by ``1 + m·ramp(year)`` with a linear ramp 2025→2050 (the Wilson,
    #: Zakeri et al. 2026 study window; see ``viz/digitalization_band.py`` for
    #: the modifier provenance). Sensitivity cells only — ``None`` in the matrix.
    demand_modifier: float | None = None
    #: Cumulative CO₂ budget (MtCO₂) over the horizon imposed via ``bound_emission``.
    #: ``None`` → no cap.
    emission_budget: float | None = None
    #: Supply-side renewable-electricity expansion: ``None`` (baseline),
    #: ``"eag2030"`` (EAG +11 TWh PV / +10 TWh wind by 2030, held flat after), or
    #: ``"eag_continued"`` (EAG build rates continued linearly to 2040). Applied as
    #: aggregate activity-floor relations over the solar/wind resource grades in
    #: :func:`messageix.pathways.apply_pathway`.
    renewable_expansion: str | None = None
    #: Fossil *power* exit: coal/oil plants capped to 0 from 2030; gas power capped
    #: on a declining path reaching a 25% flexibility residual at this year.
    #: ``None`` → no power-sector caps.
    fossil_power_exit_year: int | None = None
    #: Renovation-rate ambition inside STURM (W5.2): ``None`` keeps the default
    #: corridor (max 1→1.5%/yr, the observed-practice range); ``"at_target"``
    #: selects the ``_RENAT`` STURM manifest variant, which raises the endogenous
    #: renovation-rate ceiling to the Austrian 3%/yr policy target from 2030
    #: (baked into the STURM CSVs — see the workbook's ``provenance`` sheet; the
    #: minimum is untouched, so the rate stays a lifecycle-cost decision within a
    #: wider corridor).
    renovation_ambition: str | None = None


@dataclass(frozen=True)
class Digitalization:
    """A digitalization-adoption level (a row of the scenario matrix)."""

    id: str
    label: str
    macko_column: str


@dataclass(frozen=True)
class Scenario:
    """One cell of the matrix: a pathway × digitalization combination."""

    pathway: Pathway
    digitalization: Digitalization

    @property
    def id(self) -> str:
        """Filesystem-safe identifier."""
        return f"pathway-{self.pathway.id}__digi-{self.digitalization.id}"


def parse_scenario_id(scenario_id: str) -> tuple[str, str] | None:
    """Invert :attr:`Scenario.id`: ``pathway-<p>__digi-<d>`` → ``(p, d)``.

    Used to recover the matrix cell from a run-folder name. Returns ``None``
    for names that do not follow the scheme (e.g. ad-hoc probe folders that
    only prefix it, or unrelated directories).
    """
    if not scenario_id.startswith("pathway-") or "__digi-" not in scenario_id:
        return None
    pathway_id, digi_id = scenario_id[len("pathway-"):].split("__digi-", 1)
    return pathway_id, digi_id


def _opt_str(value: object) -> str | None:
    """Coerce a workbook cell to ``str`` (blank / NaN → ``None``)."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    s = str(value).strip()
    return s or None


def _opt_int(value: object) -> int | None:
    """Coerce a workbook cell to ``int`` (blank / non-numeric / NaN → ``None``)."""
    f = _opt_float(value)
    return None if f is None else int(f)


def _opt_float(value: object) -> float | None:
    """Coerce a workbook cell to ``float`` (blank / non-numeric / NaN → ``None``)."""
    if value is None:
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN guard


def pathways() -> dict[str, Pathway]:
    """Return all pathways keyed by id (the ``pathways`` sheet of ``inputs.xlsx``)."""
    from common import workbook

    return {
        r["id"]: Pathway(
            id=str(r["id"]),
            label=str(r["label"]),
            fossil_exit_year=_opt_int(r["fossil_exit_year"]),
            bioenergy_share_target_2040=None if r["bioenergy_share_target_2040"] is None
            else str(r["bioenergy_share_target_2040"]),
            carbon_price=_opt_float(r.get("carbon_price")),
            carbon_price_path=_opt_str(r.get("carbon_price_path")),
            demand_modifier=_opt_float(r.get("demand_modifier")),
            emission_budget=_opt_float(r.get("emission_budget")),
            renewable_expansion=_opt_str(r.get("renewable_expansion")),
            fossil_power_exit_year=_opt_int(r.get("fossil_power_exit_year")),
            renovation_ambition=_opt_str(r.get("renovation_ambition")),
        )
        for r in workbook.pathway_records()
    }


def digitalization_levels() -> dict[str, Digitalization]:
    """Return all digitalization levels keyed by id (the ``digitalization`` sheet)."""
    from common import workbook

    return {
        r["id"]: Digitalization(
            id=str(r["id"]), label=str(r["label"]), macko_column=str(r["macko_column"])
        )
        for r in workbook.digitalization_records()
    }


def matrix() -> Iterator[Scenario]:
    """Yield every pathway × digitalization combination (9 scenarios)."""
    for p in pathways().values():
        for d in digitalization_levels().values():
            yield Scenario(pathway=p, digitalization=d)
