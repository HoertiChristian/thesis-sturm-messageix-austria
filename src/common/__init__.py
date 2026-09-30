"""Shared infrastructure for the STURM ⇄ MESSAGEix-Austria linkage.

Everything the demand side (:mod:`sturm`), supply side (:mod:`messageix`) and
the coupling (:mod:`linkage`) import together: project-relative paths, the
strict :mod:`~common.workbook` reader for ``data/inputs.xlsx`` (the single
source of truth for every tunable parameter), the typed run
:class:`~common.config.Config`, the scenario matrix (:mod:`~common.scenarios`),
unit constants, the STURM-fuel → MESSAGEix-technology vocabulary
(:mod:`~common.vocab`) and the validation reporters.

See ``README.md`` for the layout and how the pieces fit together.
"""

try:  # single source of truth: pyproject.toml via the installed metadata
    from importlib.metadata import version as _version

    __version__ = _version("sturm-messageix")
except Exception:  # not installed (sys.path use) — fine, no second hardcopy
    __version__ = "unknown"
