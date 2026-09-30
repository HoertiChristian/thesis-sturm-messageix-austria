#!/usr/bin/env Rscript
# NOTE (2026-09-05 audit): --sector=comm is an auxiliary interface only. The
# linkage never invokes it, and its defaults (endogenous, price-sensitive) do
# NOT reproduce upstream's commercial offline runner (no prices, exogenous
# construction/renovation). Residential is the supported sector.
#
# Headless STURM runner (thesis-authored).
#
# A non-RStudio entry point for the vendored STURM model. It mirrors the
# upstream `run_STURM_offline_resid_SSP_2023.R` but (a) drops the `rstudioapi`
# dependency and the interactive `setwd()`, (b) takes all settings as
# `--key=value` command-line arguments, and (c) writes a single
# `report_MESSAGE` CSV to an explicit `--out` path. Invoked from Python by
# `sturm.driver.run_offline`.
#
# Example:
#   Rscript run_sturm_headless.R \
#     --sector=resid --scenario=SSP2 --years=2020,2025,2030 \
#     --region_select=C-WEU-AUT \
#     --model_dir=.../src/sturm/model --data_dir=.../src/sturm/data \
#     --out=.../results/sturm/report_MESSAGE_resid_SSP2.csv

suppressPackageStartupMessages({
  library(tidyverse)
  library(readxl)
})

# ---- argument parsing -------------------------------------------------------
# Accept `--key=value` pairs; everything has a sensible default so the script is
# runnable from the vendored layout with no arguments.
parse_args <- function() {
  raw <- commandArgs(trailingOnly = TRUE)
  out <- list()
  for (a in raw) {
    if (!grepl("^--", a) || !grepl("=", a)) {
      stop(sprintf("Bad argument '%s': expected --key=value", a))
    }
    kv <- sub("^--", "", a)
    key <- sub("=.*$", "", kv)
    val <- sub("^[^=]*=", "", kv)
    out[[key]] <- val
  }
  out
}
args <- parse_args()
arg <- function(key, default) if (!is.null(args[[key]])) args[[key]] else default

# This script lives in src/sturm/; default the model/data dirs next to it.
this_file <- sub("^--file=", "",
                 commandArgs(trailingOnly = FALSE)[grep("^--file=", commandArgs(FALSE))])
script_dir <- if (length(this_file)) normalizePath(dirname(this_file)) else getwd()

sector          <- arg("sector", "resid")
scenario        <- arg("scenario", "SSP2")
geo_level_report<- arg("geo_level_report", "R12")
years           <- as.integer(strsplit(arg("years", "2020,2025,2030"), ",")[[1]])
mod_new         <- arg("mod_new", "endogenous")
mod_ren         <- arg("mod_ren", "endogenous")
model_dir       <- arg("model_dir", file.path(script_dir, "model"))
data_dir        <- arg("data_dir",  file.path(script_dir, "data"))
input_dir       <- arg("input_dir", file.path(data_dir,
                        paste0("input_csv_SSP_2023_", sector)))
prices_csv      <- arg("prices", file.path(data_dir, "input_prices_R12.csv"))
file_inputs     <- arg("file_inputs",
                       sprintf("input_list_%s_SSP_2023.csv", sector))
out_csv         <- arg("out", file.path(script_dir, "output",
                        sprintf("report_MESSAGE_%s_%s.csv", sector, scenario)))

# region_select: comma-separated region_bld codes, or empty for the full run.
rs_raw <- arg("region_select", "")
region_select <- if (nzchar(rs_raw)) {
  list("region_bld", strsplit(rs_raw, ",")[[1]])
} else {
  NULL
}

cat(sprintf("[run_sturm_headless] sector=%s scenario=%s years=%s region=%s\n",
            sector, scenario, paste(years, collapse=","),
            if (is.null(region_select)) "ALL" else rs_raw))

# ---- run --------------------------------------------------------------------
source(file.path(model_dir, "F10_scenario_runs_MESSAGE_2100.R"))

prices <- readr::read_csv(prices_csv, show_col_types = FALSE)

report <- run_scenario(
  run              = scenario,
  sector           = sector,
  path_in          = paste0(data_dir, "/"),
  path_inputs      = paste0(input_dir, "/"),
  path_rcode       = paste0(model_dir, "/"),
  path_out         = paste0(dirname(out_csv), "/"),
  prices           = prices,
  file_inputs      = file_inputs,
  geo_level        = "region_bld",
  geo_level_aggr   = "region_gea",
  geo_levels       = c("region_bld", "region_gea"),
  geo_level_report = geo_level_report,
  region_select    = region_select,
  yrs              = years,
  input_mode       = "csv",
  mod_arch         = "stock",
  mod_new          = mod_new,
  mod_ren          = mod_ren,
  report_type      = c("MESSAGE"),
  report_var       = c("energy", "material")
)

# Drop the no-heat virtual commodities, as the upstream runner does, then write.
report <- report %>% filter(!grepl("_v_no_heat", commodity))
dir.create(dirname(out_csv), recursive = TRUE, showWarnings = FALSE)
readr::write_csv(report, out_csv)
cat(sprintf("[run_sturm_headless] wrote %d rows -> %s\n", nrow(report), out_csv))
