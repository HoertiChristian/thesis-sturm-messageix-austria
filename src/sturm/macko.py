"""Load Macko (2025) digitalization datasets.

Macko's analysis produced two output tiers; only **Reduction** — *fractional*
energy-demand reduction per year, one table per technology × {Residential,
Commercial}, with one column per digitalization scenario — is consumed by the
linkage (:func:`load_reduction`, consumed by :mod:`linkage.digital`), from the
``macko_reduction`` sheet of ``data/macko_reduction.xlsx`` (a restricted input,
not in the public repository; available on request, see ``data/README.md``). The **Adoption** tier
(S-curve technology penetration ``%`` per year) is upstream provenance only:
the reductions already embed the adoption S-curves. The raw CSV export lives in
the development history (pre-refactor ``src/Macko-analysis/``, not part of this repository); provenance is recorded in
the workbook's ``provenance`` sheet.

Caveats carried from the data review (see data/README.md):

* Reduction values are fractions, not absolute energy — they scale the
  conversion technologies' input coefficients (:mod:`linkage.digital`).
* ``smart_shading`` benefit is allocated into both cooling and lighting; the
  ``Total_smart_cooling`` and ``Total_smart_lighting_shading`` files therefore
  both embed shading. Do not sum across end-uses naively.
* ``old_smart_lighting_*`` files are a superseded revision — ignore.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from common.schemas import MACKO_REDUCTION_COLUMNS, require_columns

Sector = Literal["Residential", "Commercial"]


def load_reduction(technology: str, sector: Sector) -> pd.DataFrame:
    """Load a Macko energy-reduction file.

    Args:
        technology: File stem, e.g. ``Smart_space_heating`` or
            ``Total_smart_cooling``.
        sector: ``Residential`` or ``Commercial``.

    Returns:
        Data frame with columns :data:`MACKO_REDUCTION_COLUMNS`; the three
        scenario columns hold fractional reductions in ``[0, 1]``.
    """
    from common import workbook

    df = workbook.macko_reduction(technology, sector)
    require_columns(
        df, MACKO_REDUCTION_COLUMNS, source=f"macko_reduction.xlsx {technology}/{sector}"
    )
    return df
