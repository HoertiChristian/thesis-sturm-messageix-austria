# baseline_3 → baseline_4 changelog

Regenerated 2026-09-05 (audit reconciliation) by a full parameter-level diff of
the shipped `data/MESSAGEix-AT_baseline_4.xlsx` against the original handover
workbook `MESSAGEix-AT_baseline_3.xlsx` (the received handover file; not part of this repository). The previous
version of this file predated the changelog-§7 emission bake and the
changelog-§22 demand reconciliation and understated the diff.

Both workbooks carry the same 100 sheets; no sheet was added or removed. Eight
sheets differ:

| Sheet | Change | Provenance |
|---|---|---|
| `cat_year` | `firstmodelyear` 2020 → **2025** | base-year move (§9) |
| `demand` | **33 values changed**: 13 `rc_spec` rows re-reconciled to the sp_el split (2025: 2.584 → 1.229 GWa) and **20 `rc_therm` rows × 1.148350** (2025: 7.3003 → 8.3833 GWa — the demand-closure bake) | §9 / **§22**, provenance #25 |
| `emission_factor` | **+80 rows**: CO₂ factors on the four combusting buildings techs (`gas_rc`, `loil_rc`, `coal_rc`, `biomass_rc`), all vintage-years | **§7** (buildings emission bake), workbook provenance #8/#9 |
| `cat_emission`, `type_emission`, `emission` | +1 row each: the `GHG` emission type/category the carbon policy taxes | §7 |
| `historical_activity` | **+152 rows** (emission-species accounting technologies for the GHG bake) and **6 values changed** (`sp_el_RC` history rescaled × 0.4758 to match the reconciled `rc_spec`) | §7 / §9 (patch_sp_el_history) |
| `historical_new_capacity` | +32 rows | §7 |

All other 92 sheets — costs, lifetimes, capacity factors, growth/decline
dynamics (including the decline floors), efficiencies, resources — are
**byte-equal to the handover**: the thesis did not alter any techno-economic
parameter of the received scenario beyond the six sheets above. The handover
content itself remains externally unverified (upstream-audit gap list, item 2).

Regeneration: extract the original via
`git show 540307f:src/Message-ix-guideline/MESSAGEix-AT_baseline_3.xlsx` and
diff per sheet on all non-`value` columns.
