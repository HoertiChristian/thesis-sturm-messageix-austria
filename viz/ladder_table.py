"""Carbon-price ladder table (r7 B2): 2040 buildings CO₂ vs flat price level.

Collects the `pathway-ref_tax<level>__digi-baseline` cells into one table so the
gas→heat-pump switching threshold is reported as a finding. In r7 the response
is a step: 0 USD → re-fossilisation; ≥40 USD → the decline-floor corner
(identical mix in every priced cell), so the threshold lies below the ladder's
first rung — state the bracket, don't interpolate.

Usage:
    python viz/ladder_table.py [results_dir] [out_csv]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import co2_series

LEVELS = (0, 40, 55, 80, 120)


def main() -> None:
    results = Path(sys.argv[1] if len(sys.argv) > 1 else "results/runs")
    out_csv = Path(sys.argv[2] if len(sys.argv) > 2 else "results/tables/carbon_price_ladder.csv")

    rows = []
    for level in LEVELS:
        run = results / f"pathway-ref_tax{level}__digi-baseline"
        if not run.exists():
            print(f"(no ladder cell for {level} USD — skipped)")
            continue
        co2 = co2_series(run, (2030, 2040))
        act = pd.read_csv(run / "activity_rc.csv")
        a40 = act[act["year"] == 2040].set_index("technology")["value"]
        rows.append({
            "price_usd_per_t": level,
            "co2_2030_kt": round(float(co2.get(2030, float("nan"))), 1),
            "co2_2040_kt": round(float(co2.get(2040, float("nan"))), 1),
            "gas_rc_2040_gwa": round(float(a40.get("gas_rc", 0.0)), 3),
            "hp_el_rc_2040_gwa": round(float(a40.get("hp_el_rc", 0.0)), 3),
        })
    df = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    print(df.to_string(index=False))
    print(f"table -> {out_csv}")


if __name__ == "__main__":
    main()
