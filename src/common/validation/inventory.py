"""Out-of-sample check: modelled base-year buildings CO₂ vs the UBA inventory.

The r7 replacement (decision B5, 2026-08-29) for the *circular* base-year
final-energy check: in useful mode `base_year_check.csv` verifies the anchor pin
against the data it was pinned to and cannot fail, so it is reported as pin
integrity, not validation. This check is genuinely out-of-sample: the modelled
base-year buildings CO₂ (territorial basis, Statistik Austria activity data ×
UBA REP-0989 factors) against the UNFCCC/KSG **Gebäude inventory** value from
the ``targets`` sheet (UBA REP-0951 Tabelle 3, Inventur 2022; optionally
updated to the REP-0995 series).

The two are *different vintages* (model base 2025 vs inventory year) and
*different activity sources* (STATcube vs UBA), so the comparison reports the
deviation with that context rather than pass/fail against a band — the
documented STATcube↔UBA offset is ~500 kt at a common year, plus genuine
decline between the inventory year and 2025.
"""

from __future__ import annotations

import pandas as pd


def compare_to_inventory(modelled_kt: float, base_year: int) -> pd.DataFrame:
    """One-row frame: modelled base-year buildings CO₂ vs the UBA inventory anchor.

    Args:
        modelled_kt: Modelled territorial buildings CO₂ (kt) at ``base_year``.
        base_year: The model base year the value belongs to.

    Returns:
        Columns ``[modelled_year, modelled_kt, inventory_year, inventory_kt,
        deviation_kt, deviation_pct, note]``.
    """
    from common import workbook

    targets = workbook.targets_items()
    inv_kt = float(targets["uba_inventory_gebaeude_kt"])  # type: ignore[arg-type]
    inv_year = int(float(targets["uba_inventory_year"]))  # the sheet column is read as float
    dev = modelled_kt - inv_kt
    return pd.DataFrame([
        {
            "modelled_year": base_year,
            "modelled_kt": round(modelled_kt, 1),
            "inventory_year": inv_year,
            "inventory_kt": inv_kt,
            "deviation_kt": round(dev, 1),
            "deviation_pct": round(dev / inv_kt * 100, 2),
            "note": (
                "different vintages and activity sources (STATcube vs UBA); "
                "documented offset ~500 kt at a common year plus real "
                f"{inv_year}->{base_year} decline — context, not a pass/fail band"
            ),
        }
    ])
