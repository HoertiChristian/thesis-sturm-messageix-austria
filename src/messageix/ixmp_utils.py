"""Small ixmp/message_ix scenario helpers shared across modules.

Used by both the offline bake (:mod:`messageix.build`) and the
runtime pathway layer (:mod:`messageix.pathways`).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from message_ix import Scenario


def has_co2(scenario: Scenario) -> bool:
    """Whether the scenario's ``emission`` set contains the ``CO2`` species."""
    return "CO2" in {str(e) for e in scenario.set("emission")}


def ensure_units(scenario: Scenario, units: Iterable[str]) -> None:
    """Register ``units`` on the scenario's platform, tolerating re-registration."""
    for unit in units:
        try:
            scenario.platform.add_unit(unit)
        except Exception:
            pass
