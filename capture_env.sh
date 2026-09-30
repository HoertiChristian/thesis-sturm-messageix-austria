#!/usr/bin/env bash
# Environment capture for Appendix D (reproducibility). Run ON THE SERVER
# from the repo root:  bash capture_env.sh
# Writes one self-contained file: env_capture_<date>.txt — copy it back to
# your run records (it documents the environment that produced the results).
set -u
OUT="env_capture_$(date +%F).txt"
{
  echo "# Environment capture — $(hostname), $(date -Iseconds)"
  echo "# repo commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'n/a (rsynced worktree)')"
  echo
  echo "## Python";      python --version 2>&1
  echo
  echo "## Key packages"
  python - <<'PY'
for m in ("message_ix", "ixmp", "pandas", "numpy", "openpyxl"):
    try:
        mod = __import__(m); print(f"{m:12s} {getattr(mod, '__version__', '?')}")
    except Exception as e:
        print(f"{m:12s} MISSING ({e})")
PY
  echo
  echo "## GAMS";        (gams 2>/dev/null | head -3) || echo "gams not on PATH"
  echo
  echo "## Java";        java -version 2>&1 | head -2
  echo
  echo "## R";           R --version 2>/dev/null | head -1 || echo "R not on PATH"
  echo "## R packages (STURM-relevant)"
  Rscript -e 'for (p in c("tidyverse","readxl","ggplot2","readr","dplyr","tidyr","scales")) cat(sprintf("%-8s %s\n", p, tryCatch(as.character(packageVersion(p)), error=function(e) "MISSING")))' 2>/dev/null
  echo
  echo "## Full pip freeze"
  pip freeze
} > "$OUT"
echo "wrote $OUT ($(wc -l < "$OUT") lines) — keep it with the run records"
