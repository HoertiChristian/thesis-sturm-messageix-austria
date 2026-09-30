"""Column contracts for the upstream CSV inputs.

These are the *interfaces* between the package and its upstream inputs. They are
verified facts from the reference code and from Macko's result files, not
assumptions:

* STURM ``report_MESSAGE`` columns — ``message_ix_buildings/sturm/model/
  R01_report_MESSAGE.R``.
* Macko column names — headers of the files in
  ``src/Macko-analysis/Reduction - results/``.
"""

from __future__ import annotations

import pandas as pd

#: STURM ``report_MESSAGE_*.csv`` columns, in order.
STURM_REPORT_COLUMNS: list[str] = [
    "node",
    "commodity",
    "level",
    "year",
    "time",
    "value",
    "unit",
]

#: Macko energy-reduction CSV columns. Values are *fractional* demand reductions.
MACKO_REDUCTION_COLUMNS: list[str] = [
    "Year",
    "Baseline_Digitalization",
    "Accelerated_Digitalization",
    "Stagnating_Digitalization",
]

class SchemaError(ValueError):
    """Raised when a loaded CSV does not match its expected column contract."""


def require_columns(df: pd.DataFrame, expected: list[str], source: str) -> None:
    """Assert that ``df`` contains exactly ``expected`` columns.

    Args:
        df: The loaded data frame.
        expected: The required column names, in any order.
        source: Human-readable input name, for the error message.

    Raises:
        SchemaError: If columns are missing or unexpected.
    """
    missing = set(expected) - set(df.columns)
    extra = set(df.columns) - set(expected)
    if missing or extra:
        raise SchemaError(
            f"{source}: column mismatch — missing={sorted(missing)}, "
            f"unexpected={sorted(extra)}"
        )
