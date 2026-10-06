#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fetch tide observations and high/low predictions from NOAA CO-OPS.

Writes data/tides/tides.json: for every CO-OPS station named in sites.tsv, the
latest observed water level plus the next few high/low predictions.

Two things worth knowing about this source:

  * Observed water level and predicted high/low are DIFFERENT products. The
    observed value is what the gauge reads right now (and can be missing, or
    offset from prediction by wind and pressure); the high/low list is
    astronomical prediction only. They are kept separate here and labelled
    separately on the page, because presenting a prediction as a measurement is
    exactly the kind of quiet error that matters to someone judging clearance.

  * Everything is stored in METRES on the MLLW datum. The page converts for the
    units toggle. Requesting 'english' here and converting later would mean
    round-tripping feet -> metres -> feet.

A station that fails is skipped, not fatal: one dead gauge must not cost the
whole board its tide column.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402

APPLICATION = "CariCOOS_Maritime_Dashboard"
PRED_DAYS = 2


def log(msg):
    print(f"[fetch_tides] {msg}", flush=True)


def _get(env, **q):
    q.setdefault("application", APPLICATION)
    url = env["COOPS_API"] + "?" + urllib.parse.urlencode(q)
    return M.http_json(url, env["NWS_USER_AGENT"], accept="application/json"), url


def fetch_station(env, sid):
    """-> dict for one gauge, or None if nothing usable came back."""
    out = {"station": sid, "observed": None, "observed_utc": None, "predictions": []}

    try:
        d, _ = _get(env, product="water_level", date="latest", station=sid,
                    datum="MLLW", units="metric", time_zone="gmt", format="json")
        rows = d.get("data") or []
        if rows and rows[0].get("v") not in (None, ""):
            out["observed"] = float(rows[0]["v"])
            out["observed_utc"] = rows[0]["t"].replace(" ", "T") + ":00+00:00"
            out["name"] = (d.get("metadata") or {}).get("name")
    except Exception as e:
        log(f"  {sid}: observed unavailable ({type(e).__name__})")

    try:
        now = M.utcnow()
        d, _ = _get(env, product="predictions", interval="hilo",
                    begin_date=now.strftime("%Y%m%d"),
                    end_date=(now + dt.timedelta(days=PRED_DAYS)).strftime("%Y%m%d"),
                    station=sid, datum="MLLW", units="metric", time_zone="gmt",
                    format="json")
        for p in d.get("predictions") or []:
            t = p["t"].replace(" ", "T") + ":00+00:00"
            if t <= now.isoformat():
                continue                      # keep only what is still ahead
            out["predictions"].append({"t": t, "v": float(p["v"]), "type": p["type"]})
        out["predictions"] = out["predictions"][:4]
    except Exception as e:
        log(f"  {sid}: predictions unavailable ({type(e).__name__})")

    if out["observed"] is None and not out["predictions"]:
        return None
    return out


def main(argv):
    problems = M.validate()
    if problems:
        for p in problems:
            log(f"CONFIG ERROR: {p}")
        return 2
    env = M.load_env()
    sites = M.load_sites()
    srcs = M.load_sources()

    ids = []
    for s in sites:
        t = s.get("tide")
        if t and t in srcs and t not in ids:
            ids.append(t)

    stations, failed = {}, []
    for sid in ids:
        r = fetch_station(env, sid)
        if r:
            stations[sid] = r
        else:
            failed.append(sid)

    payload = {"fetched_utc": M.utcnow().isoformat(), "datum": "MLLW", "units": "m",
               "stations": stations, "failed": failed}
    if "--dry-run" not in argv:
        M.write_json(payload, "tides", "tides.json")
        M.record("coops_tides", env["COOPS_API"], bool(stations), len(str(payload)),
                 error=("no data for " + ",".join(failed)) if failed and not stations else "",
                 extra={"stations": len(stations), "failed": len(failed)})
    log(f"{len(stations)}/{len(ids)} gauges"
        + (f", failed: {', '.join(failed)}" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
