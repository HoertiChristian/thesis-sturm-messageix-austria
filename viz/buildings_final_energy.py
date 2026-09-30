"""Buildings final energy by fuel, the consumption-basis decomposition and the factor table.

The run folders carry no per-vintage activity, so buildings final energy (what the
end-use technologies *consume*) is reconstructed exactly from what they do carry:

* combustion fuels (gas, light oil, coal, biomass): direct CO₂eq per fuel
  (``buildings_co2_by_fuel.csv``) ÷ direct factor;
* district heat: ``heat_rc`` activity × 1.0 (its coefficient in every vintage)
  × the digitalization efficiency factor of the cell and year;
* heat-pump and resistive electricity: activity × coefficient (0.40 and 1/0.95,
  constant across vintages) × the efficiency factor;
* specific electricity (``sp_el_RC``): the remainder of the consumption-basis
  total (``buildings_co2_consumption.csv``) after all other fuels, ÷ the total
  electricity factor — it must be identical across adoption levels (checked).

Checks: 2025 reproduces the calibration pin per fuel; Σ direct factor × FE
reproduces ``buildings_co2.csv``. Also writes the consumption-basis decomposition
(coefficient effect vs activity effect) for the 2040 adoption comparisons and the
twelve emission factors of the workbook.

Outputs: ``results/tables/buildings_final_energy_by_fuel.csv``,
``results/tables/consumption_decomposition_2040.csv``, ``results/tables/emission_factors.csv``.

Usage:
    python viz/buildings_final_energy.py [results_dir] [out_dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common import paths  # noqa: E402
from common.scenarios import Digitalization, digitalization_levels  # noqa: E402
from linkage.digital import reduction_factors  # noqa: E402
from messageix.emissions import emission_factors  # noqa: E402

YEARS = (2025, 2030, 2035, 2040)
HOURS = 8760.0  # kt CO2eq = GWa × 8760 × tCO2eq/MWh
PATHWAYS = {"reference": "Reference", "renewables_push": "Renewables Push", "bio_bridge": "Bio-Bridge"}
LEVEL_LABEL = {"none": "no additional digitalization", "stagnating": "stagnating",
               "baseline": "baseline", "accelerated": "accelerated"}
COMBUSTION = ("gas", "lightoil", "coal", "biomass")
#: Vintage-invariant input coefficients (final energy per unit of useful output) in
#: the received baseline — checked against data/MESSAGEix-AT_baseline_4.xlsx!input.
COEF = {"heat_rc": 1.0, "hp_el_rc": 0.40, "elec_rc": 1.0 / 0.95}
PIN_2025 = {"biomass": 2.700097, "d_heat": 1.933017, "gas": 1.878178, "lightoil": 0.805685,
            "electr": 3.176, "coal": 0.005133}  # Statistik Austria reference, forward-reconciled


def _levels() -> dict[str, Digitalization]:
    out = dict(digitalization_levels())
    out["none"] = Digitalization(id="none", label="No additional digitalization",
                                 macko_column="Baseline_Digitalization")
    return out


def _factors(level: Digitalization) -> dict[int, float]:
    f = reduction_factors(level, list(YEARS), base_year=2025)
    return {int(y): float(f[y]) for y in YEARS}


def _cell(results: Path, pid: str, lid: str) -> Path | None:
    d = results / f"pathway-{pid}__digi-{lid}"
    return d if (d / "buildings_co2_by_fuel.csv").exists() else None


def reconstruct(results: Path, ef_direct: dict, ef_total: dict) -> pd.DataFrame:
    rows = []
    levels = _levels()
    for pid, plabel in PATHWAYS.items():
        for lid, level in levels.items():
            d = _cell(results, pid, lid)
            if d is None:
                continue
            fac = _factors(level)
            byf = pd.read_csv(d / "buildings_co2_by_fuel.csv")
            act = pd.read_csv(d / "activity_rc.csv")
            cons = pd.read_csv(d / "buildings_co2_consumption.csv").set_index("year")["value"]
            terr = pd.read_csv(d / "buildings_co2.csv").set_index("year")["value"]
            for y in YEARS:
                fe: dict[str, float] = {}
                b = byf[byf.year == y].set_index("fuel")["value"]
                for fuel in COMBUSTION:
                    fe[fuel] = float(b.get(fuel, 0.0)) / (ef_direct[fuel] * HOURS) if ef_direct[fuel] > 0 else 0.0
                a = act[act.year == y].set_index("technology")["value"]
                fe["d_heat"] = float(a.get("heat_rc", 0.0)) * COEF["heat_rc"] * fac[y]
                hp = float(a.get("hp_el_rc", 0.0)) * COEF["hp_el_rc"] * fac[y]
                res = float(a.get("elec_rc", 0.0)) * COEF["elec_rc"] * fac[y]
                other = sum(fe[f] * ef_total[f] for f in (*COMBUSTION, "d_heat")) * HOURS
                elec_total = (float(cons[y]) - other) / (ef_total["electr"] * HOURS)
                fe["electr"] = elec_total
                spec = elec_total - hp - res
                # identity check: direct CO2 from the reconstruction = buildings_co2.csv
                direct = sum(fe[f] * ef_direct[f] for f in COMBUSTION) * HOURS
                assert abs(direct - float(terr[y])) < 1e-6 * max(1.0, float(terr[y])), (pid, lid, y, direct, terr[y])
                for fuel, v in fe.items():
                    rows.append(dict(pathway=plabel, level=LEVEL_LABEL[lid], year=y, fuel=fuel, final_energy_gwa=v))
                rows.append(dict(pathway=plabel, level=LEVEL_LABEL[lid], year=y, fuel="electr_heat_pump", final_energy_gwa=hp))
                rows.append(dict(pathway=plabel, level=LEVEL_LABEL[lid], year=y, fuel="electr_resistive", final_energy_gwa=res))
                rows.append(dict(pathway=plabel, level=LEVEL_LABEL[lid], year=y, fuel="electr_specific", final_energy_gwa=spec))
    df = pd.DataFrame(rows)
    # pin check at 2025 (every cell shares the pinned base year)
    p25 = df[(df.year == 2025) & (df.fuel.isin(PIN_2025))].groupby("fuel")["final_energy_gwa"].agg(["min", "max"])
    for fuel, ref in PIN_2025.items():
        assert abs(p25.loc[fuel, "min"] - ref) < 2e-3 and abs(p25.loc[fuel, "max"] - ref) < 2e-3, (fuel, p25.loc[fuel].to_dict(), ref)
    spec = df[df.fuel == "electr_specific"].groupby(["pathway", "year"])["final_energy_gwa"].agg(["min", "max"])
    assert ((spec["max"] - spec["min"]).abs() < 1e-6).all(), "specific electricity differs across adoption levels"
    return df


def decompose(df: pd.DataFrame, ef_total: dict) -> pd.DataFrame:
    """Consumption-basis saving between two adoption levels, split per fuel into the
    coefficient effect (less fuel per unit of output at unchanged output) and the
    activity effect (changed output at the reference level's coefficient)."""
    levels = _levels()
    fac = {LEVEL_LABEL[k]: _factors(v)[2040] for k, v in levels.items()}
    fuel_ef = {"gas": ef_total["gas"], "lightoil": ef_total["lightoil"], "coal": ef_total["coal"],
               "biomass": ef_total["biomass"], "d_heat": ef_total["d_heat"],
               "electr_heat_pump": ef_total["electr"], "electr_resistive": ef_total["electr"],
               "electr_specific": ef_total["electr"]}
    scaled = {"gas", "lightoil", "coal", "biomass", "d_heat", "electr_heat_pump", "electr_resistive"}
    rows = []
    for plabel in PATHWAYS.values():
        for a, b in (("no additional digitalization", "accelerated"), ("stagnating", "accelerated"),
                     ("no additional digitalization", "baseline")):
            da = df[(df.pathway == plabel) & (df.level == a) & (df.year == 2040)].set_index("fuel")["final_energy_gwa"]
            db = df[(df.pathway == plabel) & (df.level == b) & (df.year == 2040)].set_index("fuel")["final_energy_gwa"]
            if da.empty or db.empty:
                continue
            fa, fb = fac[a], fac[b]
            tot = dict(delta=0.0, coef=0.0, act=0.0)
            for fuel, ef in fuel_ef.items():
                fe_a, fe_b = float(da.get(fuel, 0.0)), float(db.get(fuel, 0.0))
                delta = (fe_a - fe_b) * ef * HOURS
                if fuel in scaled:
                    coef_eff = fe_b * (fa / fb - 1.0) * ef * HOURS
                    act_eff = (fe_a - fe_b * fa / fb) * ef * HOURS
                else:
                    coef_eff, act_eff = 0.0, delta
                rows.append(dict(pathway=plabel, comparison=f"{a} minus {b}", fuel=fuel,
                                 saving_kt=round(delta, 1) + 0.0, coefficient_effect_kt=round(coef_eff, 1) + 0.0,
                                 activity_effect_kt=round(act_eff, 1) + 0.0))  # "+ 0.0" folds -0.0 into 0.0
                for k, v in (("delta", delta), ("coef", coef_eff), ("act", act_eff)):
                    tot[k] += v
            rows.append(dict(pathway=plabel, comparison=f"{a} minus {b}", fuel="TOTAL",
                             saving_kt=round(tot["delta"], 1), coefficient_effect_kt=round(tot["coef"], 1),
                             activity_effect_kt=round(tot["act"], 1)))
    return pd.DataFrame(rows)


def main() -> None:
    results = Path(sys.argv[1] if len(sys.argv) > 1 else "results/runs")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "results/tables")
    out.mkdir(parents=True, exist_ok=True)
    ef_direct, ef_total = emission_factors("direct"), emission_factors("total")
    pd.DataFrame({"fuel": list(ef_direct), "ef_direct_tco2eq_per_mwh": list(ef_direct.values()),
                  "ef_total_tco2eq_per_mwh": [ef_total[f] for f in ef_direct]}).to_csv(out / "emission_factors.csv", index=False)
    df = reconstruct(results, ef_direct, ef_total)
    # Decompose at full precision; round only the presentation copy of the table
    # (rounding before the decomposition produced totals 0.1-0.2 kt off the
    # emissions files and spurious non-zero activity effects on fixed fuels).
    dec = decompose(df, ef_total)
    df = df.assign(final_energy_gwa=df["final_energy_gwa"].round(4))
    df.to_csv(out / "buildings_final_energy_by_fuel.csv", index=False)
    dec.to_csv(out / "consumption_decomposition_2040.csv", index=False)
    print(df[(df.year == 2040) & (df.pathway == "Reference")].pivot(index="fuel", columns="level", values="final_energy_gwa").to_string())
    print(dec[dec.fuel.isin(("TOTAL", "electr_heat_pump", "d_heat", "gas"))].to_string(index=False))
    print(f"wrote {out / 'buildings_final_energy_by_fuel.csv'}, {out / 'consumption_decomposition_2040.csv'}, {out / 'emission_factors.csv'}")


if __name__ == "__main__":
    main()
