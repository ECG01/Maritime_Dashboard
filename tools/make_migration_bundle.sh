#!/usr/bin/env bash
# Package everything the Maritime Dashboard needs to run on another machine.
#
#   ./tools/make_migration_bundle.sh [OUTDIR]
#
# What goes in, and why each one:
#
#   the source tree      code, config TSVs, wrappers, docs
#   logs/events.jsonl    the ONLY irreplaceable runtime file. Usage analytics
#                        history; nothing regenerates it.
#   data/climo/          the climatology cache. Carried on purpose: the fetcher
#                        merges per block, so on a host WITHOUT the sibling hub
#                        checkouts the monthly tables, records and periods of
#                        record survive from this file while the day-of-year
#                        bands refresh daily over HTTP. Without it that host
#                        gets bands only, permanently.
#   data/nws, data/tides seed caches, so the first page build has something to
#                        render even before the first fetch lands.
#
# What stays out:
#
#   config/machine.env   machine-specific paths AND the only place a webroot is
#   chatbot/.env         named. Recreated per host - see docs/MIGRATION.md.
#   chatbot/.venv        platform-specific; rebuilt by chatbot/run_local.sh
#   web/out              100% generated; one pipeline run recreates it
#   state/               fetch bookkeeping; regenerates, and a stale manifest on
#                        a new host would report ages that never happened there
#   __pycache__          compiled for a different interpreter
#   versions/            the retired 7-page snapshot - reference, not runtime
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
SRC="$PWD"
OUT="${1:-$HOME}"
STAMP="$(date -u +%Y%m%d-%H%M)"
TAR="$OUT/maritime-dashboard-$STAMP.tar.gz"

mkdir -p "$OUT" || exit 1

# --exclude patterns are matched against the archived path, so anchor them.
tar -czf "$TAR" \
  --exclude='./chatbot/.venv' \
  --exclude='./chatbot/node_modules' \
  --exclude='./chatbot/.env' \
  --exclude='./config/machine.env' \
  --exclude='./config/secrets.env' \
  --exclude='./web/out' \
  --exclude='./state' \
  --exclude='./versions' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.tmp' \
  --exclude='./logs/run_*.log' \
  -C "$SRC" . || { echo "tar failed"; exit 1; }

SIZE=$(du -h "$TAR" | cut -f1)
echo "wrote $TAR  ($SIZE)"
echo
echo "carried:"
for f in logs/events.jsonl data/climo/climatology.json; do
  if tar -tzf "$TAR" | grep -q "^\./$f$"; then
    echo "  yes  $f"
  else
    echo "  NO   $f   <-- expected; check it exists in $SRC"
  fi
done
echo
echo "NOT carried - recreate on the target (see docs/MIGRATION.md):"
echo "  config/machine.env    paths, webroot, sibling dirs"
echo "  chatbot/.env          ANTHROPIC_API_KEY (Worker secret if deploying the Worker)"
