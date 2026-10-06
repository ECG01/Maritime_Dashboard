#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pull the climatology the sibling CariCOOS hubs have already computed.

Writes data/climo/climatology.json: per-station day-of-year percentile bands,
monthly tables, all-time records, and the period of record behind each one.

Two rules this file exists to enforce.

1. **We read their numbers; we never re-derive them.** Both hubs compute their
   climatology from their own QC'd archives, with masking, outage windows and
   window rules this project does not implement. Recomputing here would produce
   numbers that disagree with the published hubs by a little, which is worse
   than not having them - a mariner who checks would find CariCOOS contradicting
   CariCOOS.

2. **A bad read must not destroy a good cache.** Each block is merged
   independently, so a broken wind payload keeps yesterday's wind bands while
   today's buoy bands update. Every outcome lands in state/manifest.json.

The day-of-year slice deliberately does NOT happen here. This runs daily;
make_chat_context.py runs every ten minutes and slices there. If the slice
happened here, one failed daily run would leave the chatbot quoting yesterday's
band while calling it today's - a silent off-by-N with no symptom. Verified
worth guarding: both sibling pages currently say `todoy: 271` while today is
272, so their own index is already a day stale.

    $PYTHON fetch/fetch_climatology.py [--dry-run] [--verify]
"""
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                              # noqa: E402
from engine import embedded_json as E           # noqa: E402

# What we carry. Wind air temperature and pressure are dropped on purpose: the
# mesonet publishes them in Fahrenheit and millibars, while the snapshot's
# units_note promises metric, and a degF value inside a document that declares
# degC is exactly how a confidently wrong answer gets made. Buoy water
# temperature stays - it is already degC.
BUOY_VARS = ("hs", "tp", "temp")
WIND_VARS = ("ws", "gust", "temp")
BUOY_MONTHLY = ("hs_mean", "hs_p95", "tp_mean", "temp_mean")
WIND_MONTHLY = ("ws_mean", "gust_p95", "temp_mean")

# The mesonet publishes air temperature in FAHRENHEIT while every live reading
# in the snapshot is Celsius. Carried raw, the assistant would compare a live
# 29.4 C against a "normal for the date" of 80-84 and report a warm afternoon as
# far below normal. Convert here, once, rather than hope the reader notices -
# the buoys' own `temp` is water temperature and already Celsius, so only the
# wind side is touched.
def _f_to_c(v):
    return None if v is None else round((float(v) - 32.0) * 5.0 / 9.0, 2)


CONVERT = {"wind": {"temp": _f_to_c, "temp_mean": _f_to_c}}

# Below these, assume the payload or the parser is broken and keep the cache.
MIN_BUOY_STATIONS = 4
MIN_WIND_STATIONS = 20
MIN_BAND_RATE = 0.70
MAX_BUILT_AGE_DAYS = 35

# A station with less than this in the monthly table has no climatology worth
# the name. B41058 currently carries two months and would otherwise appear
# beside a seventeen-year record as though the two were comparable.
MIN_MONTHLY_HOURS = 500

# Records where SMALLER is the extreme. Everything else takes the maximum.
MIN_KEYS = ("tmin", "tmind", "salmin", "pmin")

# Which records we carry. The reports also publish daily-mean variants (hsd,
# tmaxd, tmind) that restate the hourly extreme a little smaller, plus salinity
# and current speed. Carrying all of them doubled the block for information
# nobody asks a maritime dashboard about; these are the ones people do ask for.
KEEP_RECORDS = {
    "buoy": ("hs", "hmax", "tp", "tmax", "tmin"),
    "wind": ("ws", "gust", "pmin"),
}

# config/sources.tsv calls Tres Palmas TPALMAS; the mesonet analysis calls it by
# its WeatherFlow id. One alias today, there will be more.
ALIASES = {"E9889": "TPALMAS"}


def log(msg):
    print(f"[fetch_climatology] {msg}", flush=True)


def resolve(env, dir_key, relpath, url_key=None):
    """(text, route) - the local file if configured, else HTTP, else nothing.

    Local first on every machine including dm2, because HTTP gives only one of
    the four blocks: the monthly tables, the records and the period of record
    live in files the hubs do not publish. Checking the FILE rather than the
    directory matters under WSL, where an unmounted drive still resolves as an
    empty directory.
    """
    base = (env.get(dir_key) or "").strip()
    if base:
        path = os.path.join(base, relpath)
        if os.path.exists(path):
            return open(path, encoding="utf-8", errors="replace").read(), "local"
    url = (env.get(url_key) or "").strip() if url_key else ""
    if url:
        try:
            return M.http_text(url, env["NWS_USER_AGENT"]), "http"
        except Exception as e:                                   # noqa: BLE001
            log(f"WARN: {url} unreachable ({e!r})")
    return None, "absent"


def _num(v, nd=2):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, nd)          # NaN -> None


def read_bands(env, kind):
    """station_climate payload -> {station: {var: {yp10,yp50,yp90}}}, plus meta."""
    if kind == "buoy":
        text, route = resolve(env, "BUOYS_OPS_DIR", "plots/station_climate.html",
                              "BUOYS_CLIMATE_URL")
        vars_, floor = BUOY_VARS, MIN_BUOY_STATIONS
    else:
        text, route = resolve(env, "MESONET_OPS_DIR",
                              "mesonet-ops/plots/station_climate.html",
                              "MESONET_CLIMATE_URL")
        vars_, floor = WIND_VARS, MIN_WIND_STATIONS
    if text is None:
        return None, {"route": "absent"}

    obj = E.extract(text)                    # raises EmbeddedPayloadError
    doy = M.utcnow().timetuple().tm_yday - 1
    cov = E.coverage_station_climate(obj, doy_index=doy, variables=vars_)
    if cov["stations"] < floor:
        raise E.EmbeddedPayloadError(
            f"only {cov['stations']} stations, expected at least {floor}")
    if cov["band_rate"] < MIN_BAND_RATE:
        raise E.EmbeddedPayloadError(
            f"only {cov['band_rate']:.0%} of bands usable, floor {MIN_BAND_RATE:.0%}")
    if cov["order_rate"] < 1.0:
        raise E.EmbeddedPayloadError(
            "p10 <= p50 <= p90 does not hold everywhere - columns moved upstream")
    built = E.built_date(obj)
    if built:
        age = (M.utcnow().date() - dt.date.fromisoformat(built)).days
        if age > MAX_BUILT_AGE_DAYS:
            raise E.EmbeddedPayloadError(
                f"upstream page was built {age} days ago - it stopped rebuilding")

    out = {}
    for sid, st in E.stations_of(obj, require=()).items():
        sid = ALIASES.get(sid, sid)
        keep = {}
        conv = CONVERT.get(kind, {})
        for v in vars_:
            b = st.get(v)
            if isinstance(b, dict) and isinstance(b.get("yp50"), list):
                f = conv.get(v)
                keep[v] = {k: ([f(x) for x in b[k]] if f else b[k])
                           for k in ("yp10", "yp50", "yp90") if k in b}
        if not keep:
            continue
        entry = {"name": st.get("loc") or sid, "bands": keep}
        # The buoy payload carries its record length per variable; the wind one
        # does not, so wind years come from the coverage CSV instead.
        yrs = [st[v].get("years") for v in vars_
               if isinstance(st.get(v), dict) and st[v].get("years")]
        if yrs:
            entry["years"] = max(yrs)
        out[sid] = entry
    return out, {"route": route, "built": obj.get("built"), **cov}


def read_monthly(env, kind):
    """climatology_monthly.csv -> {station: [[...] x 12]} (Jan..Dec, null where absent)."""
    if kind == "buoy":
        text, route = resolve(env, "BUOYS_OPS_DIR",
                              "analysis/results/climatology_monthly.csv")
        cols = BUOY_MONTHLY
    else:
        text, route = resolve(env, "MESONET_OPS_DIR",
                              "Mesonet_ANALYSIS/results/climatology_monthly.csv")
        cols = WIND_MONTHLY
    if text is None:
        return None, {"route": "absent"}
    rows, hours = {}, {}
    for r in csv.DictReader(text.splitlines()):
        sid = ALIASES.get(r["site"], r["site"])
        try:
            mo = int(r["month"])
        except (TypeError, ValueError):
            continue
        conv = CONVERT.get(kind, {})
        rows.setdefault(sid, [None] * 12)[mo - 1] = [
            (conv[c](_num(r.get(c))) if c in conv else _num(r.get(c))) for c in cols]
        hours[sid] = hours.get(sid, 0) + int(float(r.get("hours") or 0))
    out = {s: v for s, v in rows.items() if hours.get(s, 0) >= MIN_MONTHLY_HOURS}
    return out, {"route": route, "sites": len(out),
                 "dropped_thin": sorted(set(rows) - set(out))}


def read_records(env, kind):
    """extremes_report -> {station: {var: [value, when, storm?]}} - all-time only."""
    if kind == "buoy":
        text, route = resolve(env, "BUOYS_OPS_DIR",
                              "analysis/report/extremes_report.html")
    else:
        text, route = resolve(env, "MESONET_OPS_DIR",
                              "Mesonet_ANALYSIS/report/extremes_report.html")
    if text is None:
        return None, {"route": "absent"}
    obj = E.extract(text)
    out = {}
    # stations_of drops the `__short__` name map the mesonet report carries
    # beside its real entries - iterating naively invents a station called that.
    for sid, st in E.stations_of(obj, require=("years",)).items():
        sid = ALIASES.get(sid, sid)
        best = {}
        keep = KEEP_RECORDS[kind]
        for _y, rec in (st.get("years") or {}).items():
            for k, x in (rec or {}).items():
                if k not in keep:
                    continue
                if not isinstance(x, dict) or x.get("v") is None:
                    continue
                v = _num(x["v"])
                if v is None:
                    continue
                row = [v, x.get("t")] + ([x["s"]] if x.get("s") else [])
                cur = best.get(k)
                if cur is None or (v < cur[0] if k in MIN_KEYS else v > cur[0]):
                    best[k] = row
        if best:
            out[sid] = {"name": st.get("loc") or sid, "records": best}
    return out, {"route": route, "stations": len(out)}


def read_periods(env, kind):
    """Period of record per station, and a status for the dead and the new."""
    if kind == "wind":
        text, route = resolve(env, "MESONET_OPS_DIR",
                              "Mesonet_ANALYSIS/results/mesonet_hourly_coverage.csv")
        if text is None:
            return None, {"route": "absent"}
        out = {}
        today = M.utcnow().date()
        for r in csv.DictReader(text.splitlines()):
            sid = ALIASES.get(r["station"], r["station"])
            start, end = (r.get("start") or "")[:10], (r.get("end") or "")[:10]
            if not start or not end:
                continue
            e = dt.date.fromisoformat(end)
            span = (e - dt.date.fromisoformat(start)).days
            entry = {"record": [start[:7], end[:7]], "years": max(0, span // 365)}
            # Derived mechanically, not curated: a station that stopped years ago
            # still has a perfectly valid climatology, and quoting it without
            # saying so is misleading even though every number is correct.
            if (today - e).days > 180:
                entry["status"] = "no longer reporting - climatology only"
            elif span < 730:
                entry["status"] = "short record - under two years"
            out[sid] = entry
        return out, {"route": route, "stations": len(out)}

    text, route = resolve(env, "BUOYS_OPS_DIR", "analysis/results/inventory.csv")
    if text is None:
        return None, {"route": "absent"}
    out = {}
    for r in csv.DictReader(text.splitlines()):
        sid = ALIASES.get(r["site"], r["site"])
        first, last = (r.get("first") or "")[:7], (r.get("last") or "")[:7]
        if not first or not last:
            continue
        cur = out.get(sid)
        if cur is None:
            out[sid] = {"record": [first, last]}
        else:
            cur["record"] = [min(cur["record"][0], first), max(cur["record"][1], last)]
    return out, {"route": route, "stations": len(out)}


def _merge(prev, fresh, key):
    """Fresh block if we got one, otherwise whatever was cached."""
    return fresh if fresh is not None else (prev or {}).get(key)


def main(argv):
    env = M.load_env()
    dry = "--dry-run" in argv
    prev = M.read_json("climo", "climatology.json") or {}
    payload = {"fetched_utc": M.utcnow().isoformat()}
    meta = {}

    for kind in ("buoy", "wind"):
        for name, fn in (("bands", read_bands), ("monthly", read_monthly),
                         ("records", read_records), ("periods", read_periods)):
            key = f"{kind}_{name}"
            try:
                block, info = fn(env, kind)
            except Exception as e:                               # noqa: BLE001
                M.record(f"climo_{key}", key, False, error=repr(e))
                log(f"WARN: {key} failed ({e}); keeping the cached block")
                block, info = None, {"route": "failed", "error": str(e)}
            payload[key] = _merge(prev, block, key)
            meta[key] = info
            if block is not None and not dry:
                M.record(f"climo_{key}", info.get("route", "?"), True,
                         len(str(block)), extra={"coverage": info})

    payload["meta"] = meta
    have = [k for k, v in payload.items()
            if k.endswith(("bands", "monthly", "records", "periods")) and v]
    if not have:
        log("no climatology from any source and no cache - writing nothing")
        return 0
    if not dry:
        M.write_json(payload, "climo", "climatology.json")

    for k in sorted(meta):
        i = meta[k]
        n = len(payload.get(k) or {})
        log(f"  {k:16s} {i.get('route','?'):7s} {n:3d} stations"
            + (f"  band {i['band_rate']:.0%}" if "band_rate" in i else "")
            + (f"  thin-dropped {i['dropped_thin']}" if i.get("dropped_thin") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
