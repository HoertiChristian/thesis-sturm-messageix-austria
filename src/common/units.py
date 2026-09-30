"""Canonical energy-unit conversion constants.

Everything derives from one year of one gigawatt: 1 GWa = 8,760 GWh. The values
are exact; modules re-export the name they use so call sites read naturally.
"""

from __future__ import annotations

#: 1 GWa = 8,760 GWh = 8.76e6 MWh.
MWH_PER_GWA: float = 8.76e6

#: 1 kWa = 8,760 kWh = 8.76 MWh (= ``MWH_PER_GWA / 1e6``). Used where MESSAGEix
#: emission factors are entered per kW·a of activity.
MWH_PER_KWA: float = 8.76

#: 1 GWa = 8.76 TWh — divide TWh/yr by this to enter activity in GWa.
TWH_PER_GWA: float = 8.76
