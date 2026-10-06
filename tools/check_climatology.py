#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Golden vectors for engine/embedded_json.py. No test framework; exits 1 on a miss.

    $PYTHON tools/check_climatology.py

Every case here is a failure mode that would otherwise reach a mariner as a
confident number. The parser cases matter most: this module reads another
project's generated HTML, which is not an API and carries no promises.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import embedded_json as E      # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "fetch"))
import fetch_climatology as FC             # noqa: E402

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'ok ' if ok else 'FAIL'}] {label:<56} {got!r}")
    if not ok:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")


def raises(label, fn, *a, **k):
    try:
        fn(*a, **k)
    except E.EmbeddedPayloadError as e:
        print(f"  [ok ] {label:<56} rejected: {str(e)[:48]}")
        return
    except Exception as e:                                   # noqa: BLE001
        print(f"  [FAIL] {label:<56} wrong exception {type(e).__name__}")
        FAILS.append(f"{label}: raised {type(e).__name__}, want EmbeddedPayloadError")
        return
    print(f"  [FAIL] {label:<56} ACCEPTED - should have been rejected")
    FAILS.append(f"{label}: accepted a payload it should have rejected")


PAGE = '<html><script>\nconst D={"stations":{"PR1":{"loc":"Ponce"}}};\n</script>'


def main():
    print("extract - the happy paths")
    check("plain payload", E.extract(PAGE)["stations"]["PR1"]["loc"], "Ponce")
    # The naive `rstrip(";")` passes today and breaks the day the sibling's
    # template puts anything else on the same line. Balancing does not care.
    check("trailing </script> on the same line",
          E.extract('const D={"a":1};</script>')["a"], 1)
    check("braces inside a string value",
          E.extract('const D={"loc":"Ponce {test} buoy"}')["loc"], "Ponce {test} buoy")
    check("escaped quote inside a string",
          E.extract(r'const D={"loc":"St. John \"VI1\""}')["loc"], 'St. John "VI1"')
    check("indented marker", E.extract('  const D={"a":2}')["a"], 2)
    check("a different variable name", E.extract('const P={"a":3}', var="P")["a"], 3)

    print("extract - what it must refuse")
    raises("truncated mid-payload", E.extract, 'const D={"stations":{"PR1":')
    raises("marker absent", E.extract, "<html>nothing here</html>")
    raises("empty document", E.extract, "")
    # `const DATA=` must not satisfy a search for `D` - it is a different object.
    raises("const DATA= when looking for D", E.extract, 'const DATA={"a":1}')
    raises("two payload lines", E.extract, 'const D={"a":1}\nconst D={"a":2}')
    raises("marker with no object", E.extract, "const D=42;")
    raises("payload is not JSON", E.extract, "const D={oops:1}")

    print("stations_of - sentinels and malformed rows")
    # Verified live: the mesonet extremes report really does carry `__short__`
    # beside its 38 stations. Iterating naively invents a station called that.
    obj = {"PR1": {"years": {}}, "XAGU": {"years": {}},
           "__short__": {"PR1": "Ponce"}, "BAD": "not a dict", "NOYRS": {"loc": "x"}}
    check("sentinel and malformed rows dropped", sorted(E.stations_of(obj)), ["PR1", "XAGU"])
    check("without a 'require' filter, only __ and non-dicts go",
          sorted(E.stations_of(obj, require=())), ["NOYRS", "PR1", "XAGU"])

    print("band_at - the day-of-year slice")
    blk = {"yp10": [0.1, 0.2, 0.3], "yp50": [1.0, 1.1, 1.2], "yp90": [2.0, 2.1, 2.2]}
    check("index 0", E.band_at(blk, 0), [0.1, 1.0, 2.0])
    check("index 2", E.band_at(blk, 2), [0.3, 1.2, 2.2])
    # Clamping, not wrapping: on 31 December of a leap year against a 365-long
    # array, wrapping would quietly hand back 1 January.
    check("index past the end clamps to the last", E.band_at(blk, 99), [0.3, 1.2, 2.2])
    check("negative index clamps to the first", E.band_at(blk, -5), [0.1, 1.0, 2.0])
    check("rounded to 2 dp", E.band_at({"yp10": [0.123456], "yp50": [1.0], "yp90": [2.0]}, 0),
          [0.12, 1.0, 2.0])
    check("a null in the trio yields nothing",
          E.band_at({"yp10": [None], "yp50": [1.0], "yp90": [2.0]}, 0), None)
    check("missing band key", E.band_at({"yp50": [1.0]}, 0), None)
    check("not a dict", E.band_at(None, 0), None)

    print("coverage_station_climate")
    good = {"stations": {
        "A": {"hs": {"yp10": [1.0] * 365, "yp50": [2.0] * 365, "yp90": [3.0] * 365}},
        "B": {"ws": {"yp10": [1.0] * 365, "yp50": [2.0] * 365, "yp90": [3.0] * 365}}},
        "built": "2026-09-28 18:06 UTC"}
    cov = E.coverage_station_climate(good, doy_index=100)
    check("station count", cov["stations"], 2)
    check("a variable filter excludes what we do not consume",
          E.coverage_station_climate(good, doy_index=100, variables=("hs",))["pairs"], 1)
    check("every pair usable", cov["band_rate"], 1.0)
    check("every trio ordered", cov["order_rate"], 1.0)
    check("build date parsed", E.built_date(good), "2026-09-28")

    allnull = {"stations": {"A": {"hs": {"yp10": [None] * 365, "yp50": [None] * 365,
                                        "yp90": [None] * 365}}}}
    # Parses perfectly, means nothing. This is the payload a naive floor accepts.
    check("an all-null payload has zero usable bands",
          E.coverage_station_climate(allnull, doy_index=10)["band_rate"], 0.0)

    wrong = {"stations": {"A": {"hs": {"yp10": [1.0] * 30, "yp50": [2.0] * 30,
                                      "yp90": [3.0] * 30}}}}
    check("a 30-long year array is not usable",
          E.coverage_station_climate(wrong, doy_index=10)["band_rate"], 0.0)

    swapped = {"stations": {"A": {"hs": {"yp10": [3.0] * 365, "yp50": [2.0] * 365,
                                        "yp90": [1.0] * 365}}}}
    # p10 > p90 means the columns moved upstream. Free to check, and the only
    # signal we would get that a rename happened.
    check("p10 > p90 is caught by the ordering rate",
          E.coverage_station_climate(swapped, doy_index=10)["order_rate"], 0.0)

    print("coverage_extremes")
    ext = {"PR1": {"years": {"2009": {}, "2010": {}}},
           "XAGU": {"years": {"2011": {}}}, "__short__": {"PR1": "Ponce"}}
    c2 = E.coverage_extremes(ext)
    check("sentinel not counted as a station", c2["stations"], 2)
    check("year entries summed", c2["year_entries"], 3)

    print("against the real files, when they are present")
    # Paths come from machine.env, not from a baked-in WSL path, so this check
    # stays meaningful on a server. Where the sibling checkout is absent - which
    # is the normal case on a deploy host - the case is skipped, not failed: the
    # golden vectors above already prove the parser without any of these files.
    import marlib as M                                          # noqa: PLC0415
    env = M.load_env()
    real = [("buoys", os.path.join(env.get("BUOYS_OPS_DIR") or "",
                                   "plots/station_climate.html"), 4,
             ("hs", "tp", "temp")),
            ("wind", os.path.join(env.get("MESONET_OPS_DIR") or "",
                                  "mesonet-ops/plots/station_climate.html"), 20,
             ("ws", "gust"))]
    for tag, path, floor, vars_ in real:
        if not os.path.exists(path):
            print(f"  [skip] {tag}: not on this machine")
            continue
        obj = E.extract(open(path, encoding="utf-8", errors="replace").read())
        cov = E.coverage_station_climate(obj, doy_index=271, variables=vars_)
        # Assert the SAME floor the fetcher enforces, never a stricter one of our
        # own: these are live upstream files that change daily, and a test with
        # its own tighter threshold flaps for reasons that are not bugs. Seen
        # 2026-09-30, when an overnight rebuild moved the wind band rate from
        # 81% to 79.7% and tripped an ad-hoc 80% check while the real floor is 70%.
        ok = (cov["stations"] >= floor
              and cov["band_rate"] >= FC.MIN_BAND_RATE
              and cov["order_rate"] == 1.0)
        print(f"  [{'ok ' if ok else 'FAIL'}] {tag:<52} "
              f"{cov['stations']} stations, band {cov['band_rate']:.0%}, "
              f"order {cov['order_rate']:.0%}")
        if not ok:
            FAILS.append(f"real {tag} file: {cov}")

    if FAILS:
        print(f"\n{len(FAILS)} FAILED:")
        for f in FAILS:
            print("  " + f)
        return 1
    print("\nall golden vectors pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
