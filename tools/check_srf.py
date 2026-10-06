#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Golden vectors for engine/srf_parse.py. No test framework; exits 1 on a miss.

    $PYTHON tools/check_srf.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import srf_parse as S       # noqa: E402

# Trimmed from the live SRFSJU of 2026-09-29: both period forms, a wrapped beach
# list, the && glossary, and a second zone so the $$ split is exercised.
SAMPLE = """000
FZCA52 TJSJ 290729
SRFSJU

Surf Zone Forecast for Puerto Rico and the U.S. Virgin Islands
National Weather Service San Juan PR
329 AM AST Tue Sep 29 2026

PRZ005-292015-
North Central PR-
Including the beaches of Arecibo, Manati, Vega Baja,
Vega Alta and Dorado
329 AM AST Tue Sep 29 2026

.TODAY...
Rip Current Risk*...........Moderate.
Surf Height.................Around 5 feet.
Weather.....................Partly sunny. Scattered showers with
                            isolated thunderstorms.
Winds.......................East winds 10 to 15 mph.

.WEDNESDAY...
Rip Current Risk*...........High.
Surf Height.................6 to 8 feet.
Weather.....................Mostly sunny.
Winds.......................East winds 10 to 15 mph.

.THURSDAY...Surf height around 4 feet. Mostly sunny. Scattered
showers. East winds around 10 mph.

&&

Rip Current Risk Category
* Low Risk - The risk for rip currents is low, however,
life-threatening rip currents often occur in the vicinity of groins,
jetties, reefs, and piers.

$$

PRZ007-292015-
Ponce and Vicinity PR-
Including the beaches of Guayanilla and Ponce
329 AM AST Tue Sep 29 2026

.TODAY...
Rip Current Risk*...........Low.
Surf Height.................Around 2 feet.
Weather.....................Partly sunny.
Winds.......................East winds 5 to 10 mph.

$$
"""

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'ok ' if ok else 'FAIL'}] {label:<52} {got!r}")
    if not ok:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")


def main():
    p = S.parse(SAMPLE)
    z = {x["zone"]: x for x in p["zones"]}

    print("product")
    check("office is the AWIPS id, not the WMO station", p["office"], "SJU")
    check("issued from the WMO DDHHMM, in UTC", p["issued_utc"][11:16], "07:29")
    check("both zones parsed", sorted(z), ["PRZ005", "PRZ007"])

    print("zone header")
    check("name without its trailing hyphen", z["PRZ005"]["name"], "North Central PR")
    check("wrapped beach list is joined whole", z["PRZ005"]["beaches"],
          "Arecibo, Manati, Vega Baja, Vega Alta and Dorado")

    print("labelled periods")
    d = z["PRZ005"]["periods"]
    check("three periods", len(d), 3)
    check("day one risk", d[0]["risk"], "moderate")
    check("day one surf text", d[0]["surf_text"], "Around 5 feet")
    check("day one surf feet", d[0]["surf_ft"], (5, 5))
    check("wrapped weather joined to one line", d[0]["weather"],
          "Partly sunny. Scattered showers with isolated thunderstorms")
    check("day two risk", d[1]["risk"], "high")
    check("a range parses to both ends", d[1]["surf_ft"], (6, 8))

    print("outlook period (prose form)")
    # An outlook day carries no category. It must come back None, NOT "low" -
    # reporting an absent category as the safest one would invent a forecast.
    check("no risk category", d[2]["risk"], None)
    check("still yields surf height", d[2]["surf_ft"], (4, 4))
    check("period name", d[2]["name"], "Thursday")

    print("coverage + helpers")
    cov = S.coverage(p)
    check("zone count", cov["zones"], 2)
    check("every zone has a day-one category", cov["risk_rate"], 1.0)
    check("today() keys by zone", S.today(p)["PRZ007"]["risk"], "low")
    check("glossary after && is not a period",
          all("Low Risk" not in (q.get("weather") or "") for q in d), True)

    print("surf_ft parsing")
    check("'Around 4 feet'", S.surf_ft("Around 4 feet"), (4, 4))
    check("'3 to 5 feet'", S.surf_ft("3 to 5 feet"), (3, 5))
    check("descending range is ordered", S.surf_ft("8 to 6 feet"), (6, 8))
    check("no height at all", S.surf_ft("Mostly sunny"), None)
    check("empty input", S.surf_ft(""), None)

    print("degenerate input never raises")
    check("empty product", S.parse("")["zones"], [])
    check("garbage product", S.parse("not a product at all")["zones"], [])

    if FAILS:
        print("\n%d FAILED:" % len(FAILS))
        for f in FAILS:
            print("  " + f)
        return 1
    print("\nall golden vectors pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
