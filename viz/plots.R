#!/usr/bin/env Rscript
# Visualise STURM <-> MESSAGEix-Austria run outputs (ggplot2).
#
# Reads results/runs/<scenario-id>/*.csv and renders 11 PNGs + figures.pdf:
#   emissions_trajectory_territorial / _consumption — buildings CO2 vs the 2040 benchmarks (RQ1)
#   buildings_fuel_mix, buildings_co2_by_source     — rc end-use activity / CO2 by technology
#   base_year_validation                            — modelled vs Statistik-Austria reference by fuel
#   system_final_energy                             — whole-system final energy by carrier
#   heating_transition, heating_transition_gwa      — buildings heat by technology (shares / GWa)
#   rq2_digitalization, rq2_digitalization_bars     — CO2 by digitalization level (RQ2 signal)
#   gap_to_target                                   — 2040 buildings CO2 vs benchmarks, per scenario (RQ1)
#
# Scenario folders are pathway-<p>__digi-<d>: figures separate the two dimensions —
# pathway (RQ1) by facet/fill, digitalization (RQ2) by colour — so 1 or many
# pathways render correctly.
#
# Usage:  Rscript viz/plots.R [results_dir=results/runs] [out_dir=results/figures]
# Needs R packages: ggplot2, readr, dplyr, tidyr, scales.

suppressPackageStartupMessages({
  library(ggplot2); library(readr); library(dplyr); library(tidyr); library(scales)
})

args      <- commandArgs(trailingOnly = TRUE)
results_dir <- if (length(args) >= 1) args[[1]] else "results/runs"
out_dir     <- if (length(args) >= 2) args[[2]] else "results/figures"
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

YEARS <- c(2025, 2040)          # plotting window (modelled horizon; base year 2025)
# 2040 buildings reference lines — UBA REP-0995 (2025), "Energie- und Treibhausgas-
# Szenarien 2025", Tabelle 7, KSG sector "Gebäude" (kt CO2eq):
#   WEM 2040 = 3,400 (existing measures ~ current policy; supersedes REP-0951's 5,100);
#   WAM 2040 = 1,300 (additional measures ~ the 2040-neutrality target path; unchanged).
# Keep these in sync with data/inputs.xlsx!targets (the single source of truth, read by
# viz/summary_tables.py wem_target_kt(); this R script mirrors the values as constants).
# The model is calibrated to STATcube buildings energy (2025 base ~5,598 kt). At a COMMON
# year the STATcube<->UBA offset is small (~500 kt: UBA Gebäude ~6,000 kt in 2025 vs the
# model's 5,598) — most of the old 8,100->5,598 gap was REAL 2020->2025 decline (UBA
# Gebäude 8,100/2020 -> 7,400/2022 -> ~6,400/2023), not a data-source artifact. So no
# target rescale is applied: this SUPERSEDES the earlier ~2,695 "model-basis" dotted line.
# Legacy: the older NEKP/LTRS gave a 2040 buildings milestone of ~3,900 kt (2020 base
# 8,100) — kept as a footnote reference only, not plotted.
NEKP_WAM_KT <- 1300             # 2040 target — with additional measures (neutrality path)
NEKP_WEM_KT <- 3400             # existing-measures benchmark (REP-0995 WEM 2025)
TARGET_BLUE <- "#0072B2"
TARGET_GREY <- "grey45"

# The WAM/WEM reference lines + labels, spliced into a plot as a layer list
# (the block was previously duplicated verbatim in two figures; the numbers in
# the label strings are guarded by tests/test_workbook_schema.py).
# Both lines are official *projections* (REP-0995), used as comparison benchmarks —
# not legal targets; the labels say so.
target_lines <- function(x_at, wam_vjust = -0.6, wem_vjust = 1.5) list(
  geom_hline(yintercept = NEKP_WAM_KT, linetype = "dashed", colour = TARGET_BLUE),
  annotate("text", x = x_at, y = NEKP_WAM_KT, vjust = wam_vjust, hjust = 0,
           label = "WAM projection 1,300 kt (UBA 2025)", size = 3.2, colour = TARGET_BLUE),
  # existing-measures projection — UBA REP-0995 WEM 2025
  geom_hline(yintercept = NEKP_WEM_KT, linetype = "dotted", colour = TARGET_GREY),
  annotate("text", x = x_at, y = NEKP_WEM_KT, vjust = wem_vjust, hjust = 0,
           label = "WEM projection 3,400 kt (UBA 2025)", size = 3.2, colour = TARGET_GREY)
)

# ---- shared look ------------------------------------------------------------
# Larger base size so figures stay legible when scaled to 6-8" on a slide;
# horizontal bottom legend reclaims width (esp. the side-by-side slide-7 pair).
theme_smx <- function(base_size = 15) {
  theme_minimal(base_size = base_size) +
    theme(panel.grid.minor = element_blank(),
          plot.title = element_text(face = "bold", size = rel(1.05)),
          plot.title.position = "plot",
          plot.subtitle = element_text(colour = "grey35", size = rel(0.85)),
          axis.title = element_text(face = "bold"),
          strip.text = element_text(face = "bold"),
          strip.text.y = element_text(angle = 0, margin = margin(l = 4, r = 4)),
          panel.spacing.x = unit(1.4, "lines"),
          legend.position = "bottom",
          legend.key.size = unit(0.9, "lines"),
          plot.margin = margin(8, 12, 6, 8))
}

# ---- ONE global colour map (single source of truth) -------------------------
# Every figure draws its colours from these maps via scale_*_manual(), so a given
# technology / fuel / carrier / pathway / digitalization level keeps the SAME
# colour in EVERY plot (e.g. biomass is always green, electricity always blue) —
# comparable across figures, scenarios and runs. No label may fall through to grey
# by accident or to ggplot's default hue cycle. Okabe-Ito (colour-blind safe),
# extended with a few Tol colours for the minor carriers so all 9 system fuels
# are distinguishable at once.
OKABE <- c(orange="#E69F00", skyblue="#56B4E9", green="#009E73", yellow="#F0E442",
           blue="#0072B2", vermillion="#D55E00", purple="#CC79A7", black="#222222",
           grey="#999999")
EXTRA <- c(brown="#8C510A", olive="#999933", wine="#882255", teal="#44AA99")

# Fuels / technologies. The rc-technology labels and the system-commodity labels
# map to the SAME colour where they mean the same thing (Electricity, Biomass,
# Gas, District heat, Heating oil) so the buildings and system figures agree.
FUEL_COL <- c(
  "Gas"=OKABE[["orange"]], "Biomass"=OKABE[["green"]], "Coal"=OKABE[["black"]],
  "District heat"=OKABE[["purple"]], "Heating oil"=OKABE[["vermillion"]],
  "Electricity (resistive)"=OKABE[["blue"]], "Heat pump"=OKABE[["skyblue"]],
  "Electricity (specific)"=OKABE[["yellow"]], "Electricity"=OKABE[["blue"]],
  "Solar thermal"="#DDCC77",
  "Fuel oil"=EXTRA[["brown"]], "Ethanol"=EXTRA[["olive"]],
  "Methanol"=EXTRA[["wine"]], "Hydrogen"=EXTRA[["teal"]],
  "LNG"=OKABE[["grey"]], "Other"=OKABE[["grey"]])

# Fixed stacking / legend order, shared by all stacked-area figures so bands never
# reorder across years, scenarios or figures. Declining fossils grouped at one end,
# clean / growing carriers (electricity, heat pump) at the other.
FUEL_ORDER <- c("Coal", "Heating oil", "Fuel oil", "Gas", "Ethanol", "Methanol",
                "LNG", "District heat", "Biomass", "Solar thermal", "Hydrogen", "Electricity",
                "Electricity (resistive)", "Electricity (specific)", "Heat pump")

# Pathway palette (RQ1 dimension), fixed and reused identically everywhere.
PATH_COL <- c("Reference"=OKABE[["grey"]], "Renewables Push"=OKABE[["blue"]],
              "Bio-Bridge"=OKABE[["green"]])
# Digitalization palette (RQ2 dimension), fixed and reused identically everywhere.
DIGI_COL <- c("Stagnating"=OKABE[["vermillion"]], "Baseline"=OKABE[["grey"]],
              "Accelerated"=OKABE[["green"]])

TECH_LAB <- c(gas_rc="Gas", biomass_rc="Biomass", coal_rc="Coal",
              heat_rc="District heat", loil_rc="Heating oil",
              elec_rc="Electricity (resistive)", hp_el_rc="Heat pump",
              solar_rc="Solar thermal", sp_el_RC="Electricity (specific)")
FUEL_LAB <- c(gas="Gas", biomass="Biomass", coal="Coal", d_heat="District heat",
              lightoil="Heating oil", fueloil="Fuel oil", electr="Electricity",
              ethanol="Ethanol", methanol="Methanol")

relabel <- function(x, map) ifelse(x %in% names(map), map[x], x)

# ---- discover runs ----------------------------------------------------------
run_dirs <- list.dirs(results_dir, recursive = FALSE)
run_dirs <- run_dirs[grepl("pathway-.*__digi-", basename(run_dirs))]
if (length(run_dirs) == 0) stop(sprintf("No scenario dirs under %s", results_dir))

pretty_id <- function(x) tools::toTitleCase(gsub("_", " ", x))
scen_of <- function(d) {
  b <- basename(d)
  pathway <- sub("__digi-.*", "", sub("^pathway-", "", b))
  digi    <- sub(".*__digi-", "", b)
  pathway <- pretty_id(pathway)
  if (pathway == "Bio Bridge") pathway <- "Bio-Bridge"   # thesis spelling
  list(id = b, pathway = pathway, digitalization = pretty_id(digi))
}

# Order factors so legends/facets read sensibly regardless of folder order.
PATH_ORDER <- c("Reference", "Renewables Push", "Bio Bridge", "Bio-Bridge")
DIGI_ORDER <- c("Stagnating", "Baseline", "Accelerated")

# Keep only the matrix pathways — drop ad-hoc/probe runs (e.g. a carbon-price probe
# `pathway-ref_tax120__digi-*`) so they don't appear as a spurious "NA" facet.
run_dirs <- run_dirs[vapply(run_dirs, function(d) {
  s <- scen_of(d)  # variant runs (…__shape-linear) parse to an unknown digi label
  s$pathway %in% PATH_ORDER && s$digitalization %in% DIGI_ORDER
}, logical(1))]
if (length(run_dirs) == 0) stop("No matrix-pathway scenario dirs found under results/runs")
order_dims <- function(df) {
  df$pathway <- factor(df$pathway, levels = intersect(PATH_ORDER, unique(df$pathway)))
  df$digitalization <- factor(df$digitalization,
                              levels = intersect(DIGI_ORDER, unique(df$digitalization)))
  df
}
# Facet by pathway only when more than one is present (keeps single-pathway tidy).
multi_path <- function(df) nlevels(droplevels(df$pathway)) > 1

read_one <- function(d, file) {
  p <- file.path(d, file)
  if (!file.exists(p)) return(NULL)
  df <- suppressMessages(read_csv(p, show_col_types = FALSE))
  s <- scen_of(d)
  df$pathway <- s$pathway; df$digitalization <- s$digitalization; df
}
read_all <- function(file) {
  out <- lapply(run_dirs, read_one, file = file)
  out <- out[!vapply(out, is.null, logical(1))]
  if (length(out) == 0) NULL else order_dims(bind_rows(out))
}

# Make a long stacked-area frame continuous: keep only series non-zero in at least
# one plotted year, then fill every (pathway, digitalization, year, series) cell
# with 0. Prevents the "pop-in jumps" where a carrier absent in some years breaks
# the stack and shoves every band upward. `series_col` is "technology"/"commodity";
# assumes columns year, value, pathway, digitalization are present (year already
# filtered to the plotting window so complete() only crosses the modelled years).
complete_series <- function(df, series_col) {
  s <- sym(series_col)
  df |>
    group_by(across(all_of(series_col))) |>
    filter(any(value > 0)) |> ungroup() |>
    group_by(pathway, digitalization) |>
    complete(year, !!s, fill = list(value = 0)) |>
    ungroup()
}

figs <- list()
save_fig <- function(name, p, w = 8, h = 5) {
  ggsave(file.path(out_dir, paste0(name, ".png")), p, width = w, height = h, dpi = 300)
  figs[[name]] <<- p
  message("wrote ", file.path(out_dir, paste0(name, ".png")))
}

# ---- 1. emissions trajectory (RQ1) -----------------------------------------
# Two bases (UBA REP-0888): territorial (direct, NEKP-comparable) and consumption
# (incl. electricity & district heat). They differ ~3-4x in magnitude, so they are
# drawn as TWO separate figures (each auto-scaled) rather than one shared y-axis.
# Pathways are faceted (RQ1); digitalization is the colour (RQ2).
emissions_fig <- function(d, title, subtitle, show_target) {
  d <- d |> filter(year >= YEARS[1], year <= YEARS[2])
  p <- ggplot(d, aes(year, value, colour = digitalization))
  if (show_target) {
    p <- p +
      # official 2040 projections — UBA REP-0995 (2025), WAM and WEM
      target_lines(YEARS[1] + 0.3)
  }
  p <- p + geom_line(linewidth = 1.2) + geom_point(size = 2.4) +
    scale_colour_manual(values = DIGI_COL, drop = TRUE) +
    scale_y_continuous(labels = comma, limits = c(0, NA)) +
    scale_x_continuous(breaks = seq(YEARS[1], YEARS[2], 5), expand = expansion(mult = 0.08)) +
    labs(title = title, subtitle = subtitle, x = NULL, y = "kt CO2eq / yr",
         colour = "Digitalization") +
    theme_smx()
  if (multi_path(d)) p <- p + facet_wrap(~pathway)
  p
}
co2 <- read_all("buildings_co2.csv")
if (!is.null(co2)) {
  save_fig("emissions_trajectory_territorial",
           emissions_fig(co2, "Territorial buildings emissions",
                         "Direct combustion in buildings (CRF 1.A.4); dashed and dotted lines: official 2040 projections", TRUE),
           w = 9, h = 5.6)
} else message("skip emissions_trajectory_territorial: no buildings_co2.csv")
co2c <- read_all("buildings_co2_consumption.csv")
if (!is.null(co2c)) {
  save_fig("emissions_trajectory_consumption",
           emissions_fig(co2c, "Consumption-basis buildings emissions",
                         "Direct emissions plus the attributed emissions of purchased electricity and district heat (fixed factors)", FALSE),
           w = 9, h = 5.6)
} else message("skip emissions_trajectory_consumption: no buildings_co2_consumption.csv")

# ---- 2. buildings fuel/tech mix (RQ2) --------------------------------------
act <- read_all("activity_rc.csv")
facet_cell <- function(p, df) {
  if (multi_path(df)) p + facet_grid(pathway ~ digitalization, labeller = label_wrap_gen(11))
  else p + facet_wrap(~digitalization)
}
if (!is.null(act)) {
  # Heating-system story only: exclude specific electricity (sp_el_RC, appliances/plug
  # loads) — it grows with baseline demand and would mask the heating fuel transition.
  d <- act |> filter(year >= YEARS[1], year <= YEARS[2], technology != "sp_el_RC") |>
    complete_series("technology") |>
    mutate(tech = factor(relabel(technology, TECH_LAB), levels = FUEL_ORDER))
  p <- ggplot(d, aes(year, value, fill = tech)) +
    geom_area(position = "stack", colour = "white", linewidth = 0.1) +
    scale_fill_manual(values = FUEL_COL, drop = TRUE) +
    scale_x_continuous(breaks = seq(YEARS[1], YEARS[2], 5), expand = expansion(mult = 0.08)) +
    labs(title = "Buildings heating-system activity by technology",
         subtitle = "Rows: pathway, columns: adoption level",
         x = NULL, y = "GWa", fill = "Technology") +
    theme_smx()
  save_fig("buildings_fuel_mix", facet_cell(p, d), w = if (multi_path(d)) 10 else 8,
           h = if (multi_path(d)) 6.5 else 5)
} else message("skip buildings_fuel_mix: no activity_rc.csv")

# ---- 3. base-year validation -----------------------------------------------
by <- read_all("base_year_check.csv")
if (!is.null(by)) {
  # The base year is the same calibrated 2025 across every scenario, so collapse
  # the (identical) per-scenario rows into a single clean panel rather than
  # repeating it 6×.
  d <- by |> filter(fuel != "TOTAL") |>
    mutate(Fuel = relabel(fuel, FUEL_LAB)) |>
    pivot_longer(c(modelled_gwa, reference_gwa), names_to = "source", values_to = "gwa") |>
    mutate(source = recode(source, modelled_gwa = "Model",
                           reference_gwa = "Statistik Austria")) |>
    group_by(Fuel, source) |> summarise(gwa = mean(gwa), .groups = "drop")
  p <- ggplot(d, aes(Fuel, gwa, fill = source)) +
    geom_col(position = position_dodge(0.8), width = 0.75) +
    scale_fill_manual(values = c("Model" = OKABE[["blue"]],
                                 "Statistik Austria" = OKABE[["orange"]])) +
    labs(title = "Base-year (2025) pin integrity (imposed calibration)",
         subtitle = "Buildings final energy by fuel: the anchor pin reproduces Statistik Austria by construction",
         x = NULL, y = "GWa (final energy)", fill = NULL) +
    theme_smx() + theme(axis.text.x = element_text(angle = 30, hjust = 1))
  save_fig("base_year_validation", p, h = 4.8)
} else message("skip base_year_validation: no base_year_check.csv")

# ---- 4. system final-energy mix --------------------------------------------
fe <- read_all("final_energy_by_fuel.csv")
if (!is.null(fe)) {
  d <- fe |> filter(year >= YEARS[1], year <= YEARS[2]) |>
    complete_series("commodity") |>
    mutate(Fuel = factor(relabel(commodity, FUEL_LAB), levels = FUEL_ORDER))
  p <- ggplot(d, aes(year, value, fill = Fuel)) +
    geom_area(position = "stack", colour = "white", linewidth = 0.1) +
    scale_fill_manual(values = FUEL_COL, drop = TRUE) +
    scale_x_continuous(breaks = seq(YEARS[1], YEARS[2], 5), expand = expansion(mult = 0.08)) +
    labs(title = "System final energy by carrier",
         subtitle = "Rows: pathway, columns: adoption level",
         x = NULL, y = "GWa", fill = "Carrier") +
    theme_smx()
  save_fig("system_final_energy", facet_cell(p, d), w = if (multi_path(d)) 10 else 8,
           h = if (multi_path(d)) 6.5 else 5)
} else message("skip system_final_energy: no final_energy_by_fuel.csv")

# ---- 5. heating-system transition (share) ----------------------------------
# Share of buildings *heating* supplied per technology — the heat-pump takeover.
# sp_el_RC (specific electricity, not heating) is excluded; shares sum to 1 per year.
if (!is.null(act)) {
  heat_techs <- setdiff(names(TECH_LAB), "sp_el_RC")
  d <- act |>
    filter(year >= YEARS[1], year <= YEARS[2], technology %in% heat_techs) |>
    complete_series("technology") |>
    group_by(pathway, digitalization, year) |> mutate(share = value / sum(value)) |> ungroup() |>
    mutate(tech = factor(relabel(technology, TECH_LAB), levels = FUEL_ORDER))
  p <- ggplot(d, aes(year, share, fill = tech)) +
    geom_area(position = "stack", colour = "white", linewidth = 0.1) +
    scale_fill_manual(values = FUEL_COL, drop = TRUE) +
    scale_y_continuous(labels = percent) +
    scale_x_continuous(breaks = seq(YEARS[1], YEARS[2], 5), expand = expansion(mult = 0.08)) +
    labs(title = "Heating-system transition",
         subtitle = "Share of useful-energy output by technology, incl. solar thermal; rows: pathway, columns: adoption level",
         x = NULL, y = "Share of heating output", fill = "Technology") +
    theme_smx()
  save_fig("heating_transition", facet_cell(p, d), w = if (multi_path(d)) 10 else 8,
           h = if (multi_path(d)) 6.5 else 5)
} else message("skip heating_transition: no activity_rc.csv")

# ---- 5b. heating-system transition (absolute GWa) --------------------------
# Same heat techs as the share figure, but in absolute final-energy (GWa) — the
# "actual numbers" view: heat-pump GWa overtaking the declining fossil heat, without
# the share normalisation that hides the shrinking total. Replaces the % chart on the
# RQ2 slide.
if (!is.null(act)) {
  heat_techs <- setdiff(names(TECH_LAB), "sp_el_RC")
  d <- act |>
    filter(year >= YEARS[1], year <= YEARS[2], technology %in% heat_techs) |>
    complete_series("technology") |>
    mutate(tech = factor(relabel(technology, TECH_LAB), levels = FUEL_ORDER))
  p <- ggplot(d, aes(year, value, fill = tech)) +
    geom_area(position = "stack", colour = "white", linewidth = 0.1) +
    scale_fill_manual(values = FUEL_COL, drop = TRUE) +
    scale_x_continuous(breaks = seq(YEARS[1], YEARS[2], 5), expand = expansion(mult = 0.08)) +
    labs(title = "Heating-system transition (useful-energy output, GWa)",
         subtitle = "Rows: pathway, columns: adoption level",
         x = NULL, y = "GWa", fill = "Technology") +
    theme_smx()
  save_fig("heating_transition_gwa", facet_cell(p, d), w = if (multi_path(d)) 10 else 8,
           h = if (multi_path(d)) 6.5 else 5)
} else message("skip heating_transition_gwa: no activity_rc.csv")

# ---- 6. digitalization effect on CO2 (RQ2) ---------------------------------
# Territorial buildings CO2 by digitalization level, faceted by pathway, zoomed so
# the small cross-digitalization spread is visible (fig 1 overlays both bases).
if (!is.null(co2)) {
  d <- co2 |> filter(year >= YEARS[1], year <= YEARS[2])  # co2 is territorial-only
  spr <- d |> filter(year == YEARS[2]) |> summarise(lo = min(value), hi = max(value))
  p <- ggplot(d, aes(year, value, colour = digitalization)) +
    geom_line(linewidth = 1.2) + geom_point(size = 2.4) +
    scale_colour_manual(values = DIGI_COL, drop = TRUE) +
    scale_x_continuous(breaks = seq(YEARS[1], YEARS[2], 5), expand = expansion(mult = 0.08)) +
    scale_y_continuous(labels = comma) +
    labs(title = "Digitalization effect on territorial buildings CO2eq (RQ2)",
         subtitle = sprintf("2040 spread %s-%s kt across adoption levels",
                            comma(round(spr$lo)), comma(round(spr$hi))),
         x = NULL, y = "kt CO2eq / yr", colour = "Digitalization") +
    theme_smx()
  if (multi_path(d)) p <- p + facet_wrap(~pathway, scales = "free_y")
  save_fig("rq2_digitalization", p)
} else message("skip rq2_digitalization: no buildings_co2.csv")

# ---- 7. 2040 gap to target (RQ1) -------------------------------------------
# 2040 territorial CO2 per cell: digitalization on x, pathway by fill — the
# pathway gap to the target is the RQ1 headline.
if (!is.null(co2)) {
  d <- co2 |> filter(year == YEARS[2])  # co2 is territorial-only
  p <- ggplot(d, aes(digitalization, value, fill = pathway)) +
    geom_col(width = 0.7, position = position_dodge(0.75)) +
    target_lines(0.55, wam_vjust = -0.5) +
    geom_text(aes(label = comma(round(value))), position = position_dodge(0.75),
              vjust = -0.4, size = 4) +
    scale_fill_manual(values = PATH_COL, drop = TRUE) +
    scale_y_continuous(labels = comma, limits = c(0, NA)) +
    labs(title = "2040 buildings CO2eq against the official projections (RQ1)",
         x = NULL, y = "kt CO2eq (2040)", fill = "Pathway") +
    theme_smx()
  save_fig("gap_to_target", p, h = 4.5)
} else message("skip gap_to_target: no buildings_co2.csv")

# ---- 8. 2040 CO2 by digitalization level (RQ2, zoomed bars) ----------------
# The RQ2 signal as bars, faceted by pathway with a FREE y-axis so the small
# cross-digitalization spread is actually visible (on a shared 0-3000 axis the three
# bars look identical and just restate the RQ1 gap chart). Each panel zooms to its own
# range, exposing the monotonic stagnating > baseline > accelerated decline and the
# pathway interaction (r6: ~314 kt spread in Reference; 0 in the capped pathways,
# where the binding fossil caps, not demand, set the 2040 emissions).
if (!is.null(co2)) {
  d <- co2 |> filter(year == YEARS[2])  # co2 is territorial-only
  spr <- d |> group_by(pathway) |>
    summarise(spread = max(value) - min(value), .groups = "drop")
  sub <- paste(sprintf("%s ~%s kt", spr$pathway, comma(round(spr$spread))), collapse = "  ·  ")
  p <- ggplot(d, aes(digitalization, value, fill = digitalization)) +
    geom_col(width = 0.7) +
    geom_text(aes(label = comma(round(value))), vjust = -0.4, size = 3.6) +
    scale_fill_manual(values = DIGI_COL, drop = TRUE, guide = "none") +
    scale_y_continuous(labels = comma, expand = expansion(mult = c(0, 0.12))) +
    labs(title = "2040 territorial buildings CO2eq by adoption level (RQ2)",
         subtitle = paste0("Spread across adoption levels: ", sub),
         x = NULL, y = "kt CO2eq (2040)") +
    theme_smx() + theme(axis.text.x = element_text(angle = 20, hjust = 1))
  if (multi_path(d)) p <- p + facet_wrap(~pathway, scales = "free_y")
  save_fig("rq2_digitalization_bars", p, w = 9, h = 4.8)
} else message("skip rq2_digitalization_bars: no buildings_co2.csv")

# ---- 9. buildings CO2 by source/fuel (RQ1 — territorial) -------------------
# Which carriers carry the territorial buildings emissions: gas/heating oil/coal/
# biomass appear; district heat & electricity sit at 0 (their emissions are in energy
# industries, CRF 1.A.1, not buildings) so they do not show — the visual of why
# electrification drives buildings CO2 toward zero. One digitalization level (Baseline)
# per pathway for legibility. Needs buildings_co2_by_fuel.csv (added to the report
# exporters): re-run the report step to emit it; skipped if absent.
co2f <- read_all("buildings_co2_by_fuel.csv")
if (!is.null(co2f)) {
  d <- co2f |>
    filter(year >= YEARS[1], year <= YEARS[2], digitalization == "Baseline", value > 0) |>
    complete_series("fuel") |>
    mutate(Fuel = factor(relabel(fuel, FUEL_LAB), levels = FUEL_ORDER))
  p <- ggplot(d, aes(year, value, fill = Fuel)) +
    geom_area(position = "stack", colour = "white", linewidth = 0.1) +
    scale_fill_manual(values = FUEL_COL, drop = TRUE) +
    scale_y_continuous(labels = comma, limits = c(0, NA)) +
    scale_x_continuous(breaks = seq(YEARS[1], YEARS[2], 5), expand = expansion(mult = 0.08)) +
    labs(title = "Territorial buildings CO2eq by source",
         subtitle = "Baseline adoption; district heat and electricity carry no direct emissions (CRF 1.A.1)",
         x = NULL, y = "kt CO2eq / yr", fill = "Fuel") +
    theme_smx()
  if (multi_path(d)) p <- p + facet_wrap(~pathway)
  save_fig("buildings_co2_by_source", p, w = 9, h = 5.6)
} else message("skip buildings_co2_by_source: no buildings_co2_by_fuel.csv (re-run the report exporters on the server)")

# ---- combined PDF -----------------------------------------------------------
if (length(figs) > 0) {
  pdf(file.path(out_dir, "figures.pdf"), width = 9, height = 5.5)
  for (p in figs) print(p)
  invisible(dev.off())
  message("wrote ", file.path(out_dir, "figures.pdf"))
}
