#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Golden-vector self-test for the Operational Suitability core.

No test framework and no network: this proves engine/derive.py and
engine/ratings.py against hand-computed expectations, so rating correctness is
established before any fetcher exists. Prints a table; exits 1 on any mismatch.

    $PYTHON tools/check_ratings.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import derive as D                                    # noqa: E402
from engine.ratings import (FAVORABLE, MARGINAL, NODATA, UNFAVORABLE,  # noqa: E402
                            load_thresholds, prepare_sample, rate)

THS = load_thresholds()
fails = []


def check(label, got, want, fmt="{}"):
    ok = got == want
    if isinstance(want, float) and isinstance(got, (int, float)):
        ok = abs(got - want) < 1e-3
    if not ok:
        fails.append(f"{label}: got {fmt.format(got)}, want {fmt.format(want)}")
    print(f"  [{'ok ' if ok else 'FAIL'}] {label:58s} {fmt.format(got)}")


def rating(raw, cls, kind, **kw):
    return rate(prepare_sample(raw, kind=kind, **kw), cls, kind, THS)


print("\n-- derived quantities ------------------------------------------------")
check("steepness 1.5 m @ 5 s", D.steepness(1.5, 5), 0.0385, "{:.4f}")
check("steepness 1.5 m @ 12 s", D.steepness(1.5, 12), 0.0067, "{:.4f}")
check("rel_angle track 090, waves from 180 (beam)", D.rel_angle(90, 180), 90.0, "{:.1f}")
check("rel_angle track 090, waves from 270 (following)", D.rel_angle(90, 270), 0.0, "{:.1f}")
check("rel_angle track 090, waves from 090 (head)", D.rel_angle(90, 90), 180.0, "{:.1f}")
check("beam_component 2.0 m, track 090, from 180", D.beam_component(2.0, 90, 180), 2.00, "{:.2f}")
check("beam_component 2.0 m, track 090, from 270", D.beam_component(2.0, 90, 270), 0.00, "{:.2f}")
check("exposed(310, '290-070') wraps past 360", D.exposed(310, "290-070"), True)
check("exposed(180, '290-070')", D.exposed(180, "290-070"), False)
# following sea stretches the encounter period, head sea compresses it
te_follow = D.encounter_period(8.0, 20.0, 90, 270)
te_head = D.encounter_period(8.0, 20.0, 90, 90)
check("encounter period, following sea > wave period", te_follow > 8.0, True)
check("encounter period, head sea < wave period", te_head < 8.0, True)
check("roll_ratio at exact resonance is 0", D.roll_ratio(8.0, 8.0), 0.0, "{:.2f}")
check("wind 20 kt from 090 vs 2 kt current toward 090 (opposed)",
      D.wind_vs_current(20, 90, 2.0, 90), 20.0, "{:.1f}")
check("wind 20 kt from 090 vs 2 kt current toward 270 (aligned)",
      D.wind_vs_current(20, 90, 2.0, 270), 0.0, "{:.1f}")

print("\n-- small craft --------------------------------------------------------")
r = rating({"wind_kt": 20.0}, "small", "port")
check("wind 20 kt -> marginal", r.status, MARGINAL)
check("  driver is wind_kt", r.driver, "wind_kt")
check("wind 26 kt -> unfavorable", rating({"wind_kt": 26.0}, "small", "port").status, UNFAVORABLE)
check("Hs 2.1 m -> unfavorable", rating({"hs_m": 2.1}, "small", "port").status, UNFAVORABLE)

# the headline case: same wave height, opposite verdicts, decided by period
r = rating({"hs_m": 1.4, "tp_s": 5.0}, "small", "port")
check("Hs 1.4 m @ 5 s -> marginal", r.status, MARGINAL)
check("  driver is steepness, not hs_m", r.driver, "steepness")
r = rating({"hs_m": 1.4, "tp_s": 12.0}, "small", "port")
check("Hs 1.4 m @ 12 s -> favorable", r.status, FAVORABLE)

# a kind-specific limit must beat the catch-all
check("Hs 1.2 m at a port -> favorable", rating({"hs_m": 1.2}, "small", "port").status, FAVORABLE)
check("Hs 1.2 m at an inlet -> marginal (stricter bar limit)",
      rating({"hs_m": 1.2}, "small", "inlet").status, MARGINAL)

print("\n-- ferry --------------------------------------------------------------")
beam = {"hs_m": 2.0, "tp_s": 8.0, "dp_deg": 180.0}
r = rating(beam, "ferry", "route", track_deg=90)
check("2.0 m beam sea -> unfavorable", r.status, UNFAVORABLE)
check("  driver is hs_beam_m", r.driver, "hs_beam_m")
r = rating({"hs_m": 2.0, "tp_s": 8.0, "dp_deg": 270.0}, "ferry", "route", track_deg=90)
check("2.0 m following sea -> beam component 0", r.reasons and
      dict((x[0], x[2]) for x in r.reasons).get("hs_beam_m"), 0.0, "{:.2f}")
r = rating({"hs_m": 1.0, "tp_s": 8.0, "dp_deg": 180.0}, "ferry", "route",
           track_deg=90, roll_period_s=8.0, speed_kt=0.0)
check("encounter period == roll period -> resonance unfavorable", r.status, UNFAVORABLE)
check("  driver is roll_ratio", r.driver, "roll_ratio")

print("\n-- ship / long-period swell -------------------------------------------")
lp = {"hs_m": 1.3, "tp_s": 16.0}
check("Tp 16 s, Hs 1.3 m at a port -> unfavorable (berth ranging)",
      rating(lp, "ship", "port").status, UNFAVORABLE)
check("  driver is lp_swell_m", rating(lp, "ship", "port").driver, "lp_swell_m")
check("same sea at an anchorage -> lp_swell_m not evaluated",
      "lp_swell_m" in dict((x[0], x[2]) for x in rating(lp, "rec", "anchorage").reasons), False)
check("Tp 9 s, Hs 1.3 m at a port -> favorable (not a long-period swell)",
      rating({"hs_m": 1.3, "tp_s": 9.0}, "ship", "port").status, FAVORABLE)

print("\n-- missing data must never read as 'fine' -----------------------------")
check("empty sample -> nodata", rating({}, "small", "port").status, NODATA)
check("  and has no driver", rating({}, "small", "port").driver, None)
check("wind present, waves missing -> rates on wind alone",
      rating({"wind_kt": 26.0}, "small", "port").status, UNFAVORABLE)

print("\n-- worst-case combination ---------------------------------------------")
r = rating({"wind_kt": 12.0, "hs_m": 2.2, "tp_s": 10.0}, "small", "port")
check("calm wind + big seas -> unfavorable on the seas", r.status, UNFAVORABLE)
check("  driver is hs_m", r.driver, "hs_m")

print()
if fails:
    print(f"FAILED ({len(fails)}):")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("all golden vectors pass")
