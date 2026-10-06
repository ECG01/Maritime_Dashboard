#!/usr/bin/env bash
# run_pages_forecast - cron wrapper for the CariCOOS Maritime Dashboard.
#
# Holds its own lock, so an overlapping cron start simply skips that cycle rather
# than two runs fighting over the same output. Every step is non-fatal: a failed
# fetch must leave the previous payload in place and let the pages rebuild from
# it, because a board that disappears when one API hiccups is worse than useless
# to someone deciding whether to leave the dock.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
# shellcheck disable=SC1091
[ -f config/machine.env ] && . config/machine.env
BASE_DIR="${BASE_DIR:-$SCRIPT_DIR}"
PYTHON="${PYTHON:-python3}"

mkdir -p "$BASE_DIR/logs" "$BASE_DIR/state"
LOG="$BASE_DIR/logs/run_pages_forecast_$(date +%Y%m%d).log"
log(){ printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }

exec 8>"$BASE_DIR/state/run_pages_forecast.lock"
if ! flock -n 8; then
  log "still running - skipping this cycle"
  exit 0
fi

log "start"
"$PYTHON" pages/make_zones.py >> "$LOG" 2>&1 || log "WARN: zones failed (rc=$?)"

# Publish. --delay-updates stages the whole set and renames at the end, so a
# browser never catches a half-written page mid-transfer.
if [ -n "${DASHBOARD_WEBROOT:-}" ]; then
  W="$DASHBOARD_WEBROOT"
  mkdir -p "$W"
  # Also the SOURCE: on a freshly migrated host web/out/ does not exist
  # until the first generator has run, and rsync fails loudly on a
  # missing source directory. That turned the very first run on a new
  # server into a red error for no reason.
  mkdir -p "$BASE_DIR/web/out"
  # analytics.* stays local on purpose: it is an operator page, and the event
  # log that feeds it lives on this machine. Drop the two --exclude lines to
  # publish it (it carries no cookie, visitor id, session or typed text).
  # This must be on EVERY wrapper that publishes - it was on only one, so the
  # other three quietly pushed the page to the public webroot anyway.
  if rsync -a --delay-updates --exclude 'analytics.html' --exclude 'analytics.json' \
        "$BASE_DIR/web/out/" "$W/" >> "$LOG" 2>&1; then
    cp -f "$BASE_DIR/web/.htaccess" "$W/.htaccess" 2>/dev/null || true
    log "published to $W"
  else
    log "WARN: publish rsync failed"
  fi
else
  log "DASHBOARD_WEBROOT empty - publishing disabled"
fi

find "$BASE_DIR/logs" -name "run_pages_forecast_*.log" -mtime +30 -delete 2>/dev/null || true
log "done"
