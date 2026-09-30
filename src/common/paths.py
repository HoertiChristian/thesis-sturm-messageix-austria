"""Project-root-relative path resolution.

Every module that needs a filesystem location imports it from here; nothing else
constructs paths to project data.
"""

from __future__ import annotations

from pathlib import Path

#: Project root. This file is ``src/common/paths.py`` → root is two levels up.
ROOT: Path = Path(__file__).resolve().parents[2]

#: Repository data tree — the curated input workbooks live here; ``austria_raw``
#: underneath holds raw source downloads (provenance only, never read at runtime).
DATA: Path = ROOT / "data"

#: Pre-calibrated Austria MESSAGEix baseline scenario in IIASA xlsx format, loaded
#: by :func:`messageix.build.load_base_scenario` (derived from the IIASA
#: guideline handover; third-party, see ``data/README.md``). The calibration is baked
#: in — see ``docs/data/baseline_4_changelog.md`` and the workbook's ``provenance``
#: sheet; the load path only validates, never mutates.
BASELINE_XLSX: Path = DATA / "MESSAGEix-AT_baseline_4.xlsx"

#: STURM stock-turnover model (R) — the IIASA ``message_ix_buildings/sturm``
#: package plus the headless runner; bundled here (third-party, see ``data/README.md``).
STURM_DIR: Path = ROOT / "src" / "sturm"
STURM_MODEL: Path = STURM_DIR / "model"
STURM_DATA: Path = STURM_DIR / "data"
STURM_RUNNER: Path = STURM_DIR / "run_sturm_headless.R"


#: Single consolidated input workbook for the curated, hand-editable inputs:
#: run config, the scenario matrix, the Austrian reference — one sheet each. The
#: companion to the MESSAGEix baseline workbook (:data:`BASELINE_XLSX`). Read by
#: :mod:`common.workbook`.
INPUTS_XLSX: Path = DATA / "inputs.xlsx"

#: Macko (2025) digitalization reduction tables (sheet ``macko_reduction``),
#: third-party. Kept in its own workbook so that :data:`INPUTS_XLSX` holds only
#: this project's own parameters. Read by :func:`common.workbook.macko_reduction`.
MACKO_XLSX: Path = DATA / "macko_reduction.xlsx"

#: Scenario-run outputs.
RESULTS: Path = ROOT / "results"
RESULTS_RUNS: Path = RESULTS / "runs"

#: STURM ``report_MESSAGE`` run outputs (regeneratable; created on demand).
STURM_OUTPUT: Path = RESULTS / "sturm"


def require_restricted(path: Path, what: str) -> Path:
    """Return ``path``, or fail with a clear message if a restricted input is absent.

    The MESSAGEix-Austria baseline (:data:`BASELINE_XLSX`) and the Macko (2025)
    reduction tables (:data:`MACKO_XLSX`) are third-party inputs that are not part
    of the public repository; they are available on request (see
    ``data/README.md``).

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{what} not found at {path}. This input is not included in the public "
            f"repository and is available on request from the author; place the "
            f"file at the path above to run the pipeline (see data/README.md)."
        )
    return path


def run_dir(scenario_id: str) -> Path:
    """Return the output directory for ``scenario_id``, creating it if absent.

    Args:
        scenario_id: Scenario identifier, e.g. ``pathway-reference__digi-baseline``.

    Returns:
        The created directory under :data:`RESULTS_RUNS`.
    """
    d = RESULTS_RUNS / scenario_id
    d.mkdir(parents=True, exist_ok=True)
    return d
