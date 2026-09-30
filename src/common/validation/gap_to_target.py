"""RQ1 — residual gap to the 2040 buildings-sector emission targets.

RQ1 asks how far each pathway closes the gap to Austria's 2040 buildings-sector
targets. The target basis is UBA REP-0995 (2025), "Energie- und Treibhausgas-
Szenarien 2025", Tabelle 7, KSG sector "Gebäude" (kt CO₂eq; adopted 2026-08-25,
superseding REP-0951):

* WAM 2040 = 1,300 kt — with-additional-measures path (the 2040-neutrality
  target path; unchanged from REP-0951). This is the primary target:
  :attr:`GapResult.met` is judged against it.
* WEM 2040 = 3,400 kt — existing-measures benchmark, reported for context
  (REP-0951's WEM was 5,100 kt).

The older NEKP/LTRS milestone of ~3,900 kt (2020 base 8,100 kt) is legacy and
deliberately not exposed as a constant; cite it as a footnote only. No
model-basis rescale is applied (the earlier ~2,695 kt rescale is superseded —
see ``viz/plots.R`` for the STATcube↔UBA offset rationale).
"""

from __future__ import annotations


def _targets() -> dict[str, object]:
    from common import workbook

    return workbook.targets_items()


def wam_target_kt() -> float:
    """Primary 2040 buildings target, kt CO₂eq — REP-0995 WAM (neutrality path)."""
    return float(_targets()["target_2040_wam_kt"])  # type: ignore[arg-type]


def wem_target_kt() -> float:
    """Existing-measures benchmark, kt CO₂eq — REP-0995 WEM."""
    return float(_targets()["target_2040_wem_kt"])  # type: ignore[arg-type]
