#!/usr/bin/env bash
# Backfill three prior days with distinct AU news topic focuses (sequential).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
LOG="$ROOT/logs/backfill-three-days.log"
mkdir -p "$ROOT/logs"

run_day() {
  local day="$1"
  local topics="$2"
  echo "===== START ${day} topics=${topics} =====" | tee -a "$LOG"
  "$PY" -m ai_art.run \
    --date "$day" \
    --topics "$topics" \
    --force \
    --skip-email \
    >>"$LOG" 2>&1
  local rc=$?
  echo "===== END ${day} rc=${rc} =====" | tee -a "$LOG"
  return "$rc"
}

# Going back three days from 2026-09-06 → 09-03, 09-04, 09-05
run_day "2026-09-03" "politics,parliament,democracy,elections,governance"
run_day "2026-09-04" "climate,environment,bushfire,El Niño,weather,reef"
run_day "2026-09-05" "housing,economy,cost of living,wages,interest rates"

echo "backfill complete" | tee -a "$LOG"
