"""Regenerate hublib.py: the presentation layer of buoys-ops/buoylib.py, byte-identical.

Run this again after a buoylib.py change to re-vendor. tools/check_hublib_drift.py
reports when the two have diverged.
"""
import ast, hashlib, os, sys, datetime

# Not hardcoded: this is the one dev tool that reaches into a sibling checkout,
# and a baked-in WSL path makes it a no-op on every other machine - including the
# server this may one day be maintained from. BUOYS_OPS_DIR is the same key the
# climatology fetcher uses, so one setting covers both.
_BASE = (os.environ.get("BUOYS_OPS_DIR") or "").strip()
if not _BASE:
    import re as _re
    _cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "machine.env")
    if os.path.exists(_cfg):
        for _l in open(_cfg, encoding="utf-8"):
            _m = _re.match(r'\s*(?:export\s+)?BUOYS_OPS_DIR\s*=\s*"?([^"\n]*)"?', _l)
            if _m:
                _BASE = _m.group(1).strip()
SRC = os.path.join(_BASE, "buoylib.py") if _BASE else ""
if not SRC or not os.path.exists(SRC):
    sys.exit("BUOYS_OPS_DIR is not set, or has no buoylib.py in it.\n"
             "This tool re-vendors hublib.py from the Ocean Buoys Hub checkout;\n"
             "without that checkout there is nothing to vendor from. Set it in\n"
             "config/machine.env or in the environment. hublib.py already in the\n"
             "tree stays valid - you only need this when buoylib.py has changed.")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hublib.py")

# Presentation layer only. Buoy DOMAIN logic (load_stations, station_maps, STREAM_SRC,
# VARS, load_stream, STORMS, SHORT) is deliberately NOT vendored -- see the plan.
WANT = ["THEME_CSS", "LANG_CSS", "LANG_BOOT_JS", "LANG_JS", "LANG_BTN",
        "TZ_JS", "TZ_BTN", "NOTE_ES", "FONTS_LINK",
        "bi", "es_note", "atomic_write_parquet", "atomic_write_text"]

src = open(SRC, encoding="utf-8").read()
lines = src.splitlines(keepends=True)
tree = ast.parse(src)

spans = {}
for node in tree.body:
    names = []
    if isinstance(node, ast.Assign):
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        names = [node.name]
    for n in names:
        if n in WANT:
            spans[n] = (node.lineno - 1, node.end_lineno)

missing = [n for n in WANT if n not in spans]
if missing:
    sys.exit(f"not found in {SRC}: {missing}")

sha = hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]
today = datetime.date.today().isoformat()

hdr = f'''# -*- coding: utf-8 -*-
"""Vendored presentation layer of the CariCOOS hub family.

  source : buoys-ops/buoylib.py  (sha256:{sha}, {len(lines)} lines)
  copied : {today}
  by     : tools/../scratchpad/vendor_hublib.py  (re-run to re-vendor)

The bodies below are BYTE-IDENTICAL to buoylib.py so the Ocean Buoys Hub, the Wind
Stations Hub and this Maritime Dashboard read as one family. Do not edit them here.
Maritime-only additions (the suitability palette, the marine unit system, the page
shell) live in marlib.py instead, so tools/check_hublib_drift.py stays clean.

Why vendored and not imported: on dm2 these are independent folders with independent
crons sharing a venv a fourth project owns. A sys.path hack into another clone means a
buoylib refactor silently breaks the maritime cron at 03:00, with no test and no owner.

!! localStorage is per-ORIGIN, not per-path. dm2.caricoos.org/Buoys_Dashboard/ and
!! dm2.caricoos.org/Maritime_Dashboard/ share one store, so the key below is
!! deliberately still 'buoys_lang': a user who picked Spanish on the Buoys Hub arrives
!! here already in Spanish. That is a feature. Do not "clean up" the name.
"""
import os

'''

parts = [hdr]
for n in WANT:
    a, b = spans[n]
    parts.append("".join(lines[a:b]).rstrip("\n") + "\n\n\n")

out = "".join(parts).rstrip("\n") + "\n"
open(OUT, "w", encoding="utf-8").write(out)
print(f"wrote {OUT}  ({len(out.splitlines())} lines, {len(WANT)} symbols, buoylib sha {sha})")
