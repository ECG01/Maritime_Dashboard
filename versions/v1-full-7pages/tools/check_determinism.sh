#!/usr/bin/env bash
# Same input twice must give byte-identical output, once the run timestamp is
# masked. Catches dict-ordering and float-repr noise, and keeps future diffs
# meaningful. NOTE the timestamp appears BOTH as footer prose and as the
# "generated_utc" key inside the injected JSON payload, which sits on one long
# line - mask both or the payload alone will look non-deterministic.
set -u
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 1
PYTHON="${PYTHON:-$HOME/venvs/meson_env/bin/python}"
mask(){ sed -E 's/"generated_utc": ?"[^"]*"/"generated_utc":"X"/g; s/Generated [0-9T:.+-]*Z?/Generated X/g; s/Generado [0-9T:.+-]*Z?/Generado X/g'; }
rc=0
for p in "$@"; do
  "$PYTHON" "pages/make_$p.py" >/dev/null 2>&1
  mask < "web/out/$p.html" > "/tmp/det_a_$p"
  "$PYTHON" "pages/make_$p.py" >/dev/null 2>&1
  mask < "web/out/$p.html" > "/tmp/det_b_$p"
  if diff -q "/tmp/det_a_$p" "/tmp/det_b_$p" >/dev/null; then
    echo "  $p.html deterministic"
  else
    echo "  $p.html NON-DETERMINISTIC"; diff "/tmp/det_a_$p" "/tmp/det_b_$p" | head -4; rc=1
  fi
done
exit $rc
