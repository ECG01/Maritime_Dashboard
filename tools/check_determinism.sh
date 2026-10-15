#!/usr/bin/env bash
# Same input twice must give byte-identical output, once the run timestamp is
# masked. Catches dict-ordering and float-repr noise, keeping future diffs useful.
#
# Arguments are generator:output pairs, because the two names do not always
# match - make_conditions.py writes index.html, since the board IS the landing
# page in the three-page build.
#
# The timestamp appears BOTH as footer prose and as the "generated_utc" key
# inside the injected JSON payload, which sits on one very long line. Mask both,
# or every payload-bearing page looks non-deterministic when it is not.
set -u
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 1
PYTHON="${PYTHON:-$HOME/venvs/meson_env/bin/python}"
mask(){ sed -E 's/"generated_utc": ?"[^"]*"/"generated_utc":"X"/g; s/Generated [0-9T:.+-]*Z?/Generated X/g; s/Generado [0-9T:.+-]*Z?/Generado X/g'; }
rc=0
for pair in "$@"; do
  gen="${pair%%:*}"; out="${pair##*:}"
  if [ ! -f "pages/make_$gen.py" ]; then echo "  make_$gen.py missing"; rc=1; continue; fi
  "$PYTHON" "pages/make_$gen.py" >/dev/null 2>&1
  mask < "web/out/$out.html" > "/tmp/det_a_$out"
  "$PYTHON" "pages/make_$gen.py" >/dev/null 2>&1
  mask < "web/out/$out.html" > "/tmp/det_b_$out"
  if diff -q "/tmp/det_a_$out" "/tmp/det_b_$out" >/dev/null; then
    echo "  $out.html deterministic"
  else
    echo "  $out.html NON-DETERMINISTIC"; diff "/tmp/det_a_$out" "/tmp/det_b_$out" | head -4; rc=1
  fi
done
exit $rc
