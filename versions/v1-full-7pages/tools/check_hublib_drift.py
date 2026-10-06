#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Report when hublib.py has drifted from the buoys-ops buoylib.py it was copied from.

hublib.py is a deliberate copy, not an import (see its header for why). A copy can
rot, so this compares the vendored symbols against the original whenever both are
present on the same machine, and tells you to re-run tools/vendor_hublib.py.

Exit 0 = in sync, or the source clone is not on this machine (nothing to compare).
Exit 1 = drifted.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.join(os.path.dirname(HERE), "Ocean_Buoys_HUB", "buoylib.py")


def symbols(path):
    src = open(path, encoding="utf-8").read()
    lines = src.splitlines(keepends=True)
    out = {}
    for node in ast.parse(src).body:
        names = []
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [node.name]
        for n in names:
            out[n] = "".join(lines[node.lineno - 1:node.end_lineno]).rstrip("\n")
    return out


def main(argv):
    src = argv[0] if argv else os.environ.get("BUOYLIB", DEFAULT_SRC)
    mine = os.path.join(HERE, "hublib.py")
    if not os.path.exists(src):
        print(f"[drift] buoylib not on this machine ({src}); nothing to compare")
        return 0
    a, b = symbols(src), symbols(mine)
    vendored = [k for k in b if k in a or k in ("bi", "es_note")]
    drifted = [k for k in vendored if k in a and a[k] != b[k]]
    missing = [k for k in vendored if k not in a]
    for k in drifted:
        print(f"[drift] {k} differs from buoylib.py")
    for k in missing:
        print(f"[drift] {k} no longer exists in buoylib.py")
    if drifted or missing:
        print(f"[drift] {len(drifted) + len(missing)} symbol(s) out of sync -- "
              f"re-run tools/vendor_hublib.py and re-check the pages")
        return 1
    print(f"[drift] in sync ({len(vendored)} vendored symbols)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
