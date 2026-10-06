#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/chat_context.json - the only thing the chatbot ever sees.

A curated snapshot, deliberately NOT the raw internal files. Three reasons:

  * Only web/out/ is published. data/nws/, data/obs/ and data/tides/ stay on the
    server, so a chatbot hosted elsewhere cannot read them at all.
  * The raw files carry plenty the bot has no business reasoning about - fetch
    bookkeeping, per-file paths, QC internals, the full 10-period forecast for
    ten zones. Handing it everything invites confident answers about the wrong
    thing.
  * Every value here arrives WITH its provenance - which instrument, how old,
    measured or forecast. The bot is told to quote that, which is the main
    defence against it inventing a sea state.

Keep this file small. It is re-read on every question, so its size is a direct
per-question cost.
"""
import datetime as _dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402
from engine import embedded_json as E   # noqa: E402
from engine import cwf_parse as C       # noqa: E402
from engine import derive as D          # noqa: E402

#: Forecast periods per zone. The CWF publishes ten - roughly five days out.
#: This was 4 to keep the snapshot small, which quietly made "which day is best
#: to go to the beach?" unanswerable: the bot could only see as far as tomorrow
#: and had no way to know it was missing the rest. Carrying all ten costs about
#: 12 KB and is the difference between a now-board and something you can plan
#: with.
PERIODS = 10


def main():
    env = M.load_env()
    cwf = M.read_json("nws", "cwf.json") or {}
    srf = M.read_json("nws", "srf.json") or {}
    obs = (M.read_json("obs", "obs.json") or {}).get("stations", {})
    tides = (M.read_json("tides", "tides.json") or {}).get("stations", {})
    board = M.read_json_path(os.path.join(M.WEBOUT, "board.json")) or {}
    srcs = M.load_sources()

    by_id = {s["id"]: s for s in board.get("sites", [])}
    sites = []
    for s in M.load_sites():
        b = by_id.get(s["site_id"], {})
        prov = b.get("prov") or {}
        tide = b.get("tide") or {}
        steep = D.steepness(b.get("hs_m"), b.get("tp_s"))
        sites.append({
            "id": s["site_id"], "name_en": s["name_en"], "name_es": s["name_es"],
            "kind": s["kind"], "group": s["group"], "zone": s["zone"],
            "lat": s["lat"], "lon": s["lon"],
            "wind_kt": _r(b.get("wind_kt"), 1), "gust_kt": _r(b.get("gust_kt"), 1),
            "wind_from_deg": _r(b.get("wdir"), 0),
            "seas_m": _r(b.get("hs_m"), 2), "wave_period_s": _r(b.get("tp_s"), 1),
            "seas_from_deg": _r(b.get("dp"), 0),
            "steepness": _r(steep, 4),
            "wind_source": _prov(prov.get("wind"), srcs),
            "wave_source": _prov(prov.get("wave"), srcs),
            "observed_at_utc": prov.get("obs_utc"),
            "next_tide": ({"type": "high" if tide.get("next", {}).get("type") == "H" else "low",
                           "at_utc": tide["next"]["t"],
                           "level_m": _r(tide["next"].get("v"), 2)}
                          if tide.get("next") else None),
            # The whole upcoming run of highs and lows, not just the next one -
            # "when are today's tides?" is a normal question and one entry cannot
            # answer it.
            "upcoming_tides": [
                {"type": "high" if t.get("type") == "H" else "low",
                 "at_utc": t["t"], "level_m": _r(t.get("v"), 2)}
                for t in (tides.get(s["tide"], {}).get("predictions") or [])
            ] if s.get("tide") else [],
            "tide_level_now_m": _r(tide.get("observed"), 2),
            "tide_station": s.get("tide"),
            "notes": s["notes"] or None,
        })

    zones = {}
    for z, zd in (cwf.get("zones") or {}).items():
        fr = C.frames(cwf, z)[:PERIODS]
        zones[z] = {
            "name": zd.get("name"),
            "covers_utc": [fr[0]["start_utc"], fr[-1]["end_utc"]] if fr else None,
            "periods": [{"label": p["label"], "from_utc": p.get("start_utc"),
                         "to_utc": p.get("end_utc"),
                         "nws_text_verbatim": p.get("text"),
                         "wind_kt": _r(p.get("wind_kt"), 0),
                         "gust_kt": _r(p.get("gust_kt"), 0),
                         "seas_m": _r(p.get("hs_m"), 2),
                         "wave_period_s": _r(p.get("tp_s"), 1)} for p in fr],
            # Rolled up per calendar day, because "which day is calmest?" is the
            # question people actually ask and answering it from ten separate
            # day/night periods means holding ten numbers in mind at once. The
            # bot got it wrong by simply stopping after the first three. These
            # are the SAME numbers, just already reduced to a worst case per day.
            "daily_worst_case": _daily(fr),
        }

    # Every station's CURRENT reading and its last 24 hours. Previously this held
    # only names and positions, so a question about a station that does not feed
    # one of the 14 board locations - "what is the wind at Culebrita?" - could not
    # be answered at all, even though the reading was sitting in obs.json.
    stations = {}
    for sid, r in obs.items():
        s = srcs.get(sid)
        h24 = r.get("last24h") or {}
        w24 = r.get("wind24h") or {}
        # The observation TIME, not "minutes ago". age_min is computed when the
        # file is written and then frozen: a snapshot two hours old still claimed
        # its readings were 11 minutes fresh, so the assistant would have quoted
        # a provenance that was flatly untrue. The request carries the current
        # time instead, and the age is worked out from these two.
        entry = {"name": s["name_en"] if s else sid,
                 "lat": s["lat"] if s else None, "lon": s["lon"] if s else None,
                 "observed_utc": r.get("obs_utc"), "stale": r.get("stale", False)}
        if r.get("stale"):
            # Down stations are listed so the bot can say "that station is down"
            # instead of inventing a reason, but their numbers are not carried.
            entry["note"] = "not reporting - readings withheld"
            stations[sid] = entry
            continue
        for k, out in (("wind_kt", "wind_kt"), ("gust_kt", "gust_kt"),
                       ("wdir_deg", "wind_from_deg"), ("hs_m", "seas_m"),
                       ("tp_s", "wave_period_s"), ("dp_deg", "seas_from_deg"),
                       ("wtemp_c", "water_temp_c"), ("atemp_c", "air_temp_c"),
                       ("salinity_psu", "salinity_psu")):
            v = _r(r.get(k), 2)
            if v is not None:
                entry[out] = v
        last24 = {}
        for src_block in (h24, w24, r.get("ocean24h") or {}):
            for k, v in src_block.items():
                if isinstance(v, dict):
                    last24[k] = v
        if last24:
            entry["last_24h_min_max_median"] = last24
        stations[sid] = entry

    payload = {
        "generated_utc": M.utcnow().isoformat(),
        "timezone_note": "All times are UTC. Puerto Rico and the USVI use AST, "
                         "which is UTC-4 year round with no daylight saving.",
        "units_note": "Wind and gusts in knots, seas and tide levels in metres, "
                      "wave period in seconds, directions in degrees the wind or "
                      "waves come FROM. Steepness is Hs/(1.56*Tp^2), dimensionless.",
        "forecast": {
            "office": cwf.get("office", "SJU"),
            "product": "NWS Coastal Waters Forecast",
            "issued_utc": cwf.get("issued_utc"),
            "note": "Every zone carries the full run of NWS periods, about five "
                    "days out. Later periods drop the Wave Detail clause, so they "
                    "have wind and sea height but no wave period.",
            "synopsis_verbatim": cwf.get("synopsis"),
            "url": cwf.get("product_url"),
            "zones": zones,
        },
        # EVERY active NWS product for PR/USVI, marine or not - a heat advisory
        # or a flood warning matters to someone planning a day on the water, and
        # the assistant is asked "is there any advisory right now?". Expired ones
        # are dropped here so it cannot quote a product that has lapsed.
        "nws_products_in_effect": [
            {"event": a.get("event"), "sender": a.get("sender"),
             "scope": a.get("scope"), "zones": a.get("zones"),
             "expires": a.get("expires"),
             "headline_verbatim": a.get("headline"),
             "description_verbatim": a.get("description"),
             "instruction_verbatim": a.get("instruction")}
            for a in (M.read_json("nws", "alerts.json") or {}).get("alerts", [])
            if _still_live(a.get("expires"))
        ],
        # The Surf Zone Forecast. It answers "is it safe to swim / take the kids
        # to the beach", which nothing else here can: a Low or Moderate rip
        # current risk is never issued as an alert, so it is absent from
        # nws_products_in_effect no matter how relevant it is. It is a FORECAST -
        # the assistant must not call it an advisory.
        "surf_zone_forecast": {
            "office": srf.get("office", "SJU"),
            "product": "NWS Surf Zone Forecast",
            "issued_utc": srf.get("issued_utc"),
            "url": srf.get("product_url"),
            "note": "A forecast, NOT an advisory or warning. Only a HIGH rip "
                    "current risk is issued as a Rip Current Statement, which "
                    "would then also appear in nws_products_in_effect. Surf "
                    "heights are in feet, as the NWS issues them. Outlook days "
                    "carry no risk category at all - report that as 'not "
                    "forecast', never as low.",
            "risk_categories_verbatim": srf.get("risk_meaning"),
            "zones": [
                {"zone": z.get("zone"), "area": z.get("name"),
                 "beaches": z.get("beaches"),
                 # Only the first two periods carry a risk category, and only
                 # they are worth their verbatim weather and winds: the outlook
                 # days repeat what the Coastal Waters Forecast already says at
                 # length, and carrying both put 21% of the snapshot - and of
                 # every question's cost - into text the bot already had.
                 "periods": [_srf_period(q, i) for i, q in
                             enumerate(z.get("periods") or [])]}
                for z in (srf.get("zones") or [])
            ],
        },
        "sites": sites,
        "stations": stations,
        "tools": [
            {"name": "Ocean Buoys Hub", "url": env["BUOYS_HUB_URL"],
             "what": "Wave height, period and direction, water temperature, salinity "
                     "and currents from the CariCOOS buoys and Waveriders, back to 2009."},
            {"name": "Wind Stations Hub", "url": env["MESONET_HUB_URL"],
             "what": "Quality-controlled wind speed, direction and gusts from the "
                     "station network across Puerto Rico and the USVI."},
            {"name": "Model Viewer", "url": env["MODVIEWER_URL"],
             "what": "Interactive map of the forecast models - winds, waves, currents, "
                     "water level, radar and satellite."},
            {"name": "Model Viewer (classic)", "url": env["CLASSIC_VIEWER_URL"],
             "what": "The original model dashboard: animated WRF, SWAN, FVCOM, RTOFS "
                     "and STOFS forecast imagery."},
        ],
    }
    # Omitted entirely when there is no climatology, rather than emitted empty:
    # an absent key makes the assistant say it has no historical data, while an
    # empty one invites it to report that every station has none.
    clim = _climatology()
    if clim:
        payload["climatology"] = clim

    out = os.path.join(M.WEBOUT, "chat_context.json")
    M.atomic_write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), out)
    kb = os.path.getsize(out) / 1024
    ckb = len(json.dumps(clim, ensure_ascii=False, separators=(",", ":"))) / 1024 if clim else 0
    print(f"[make_chat_context] wrote {out} ({kb:.1f} KB, {len(sites)} sites, "
          f"{len(zones)} zones x {PERIODS} periods, {len(stations)} stations, "
          f"climatology {len(clim['stations']) if clim else 0} stations / {ckb:.1f} KB)")
    return 0


def _climatology():
    """The historical block: what conditions have USUALLY been, from the archives.

    Returns None when no climatology has been fetched, and the caller then omits
    the key entirely rather than emitting an empty one - the chatbot simply has
    no history and says so, which is the correct degraded state.

    Station ids are prefixed `buoy:` / `wind:` because PR1, PR2, PR3, VI1 and
    VIA appear in BOTH archives - as buoys carrying waves and water temperature,
    and as wind stations carrying speed and gusts - computed by different
    analyses over different periods of record. Merging them into one key would
    quietly attach a 17-year wave record's authority to a wind number that does
    not have it.

    Monthly tables and records use positional arrays with a legend: named keys
    repeat "hs_mean" 12 times per station across 44 stations and cost three
    times as much for the same information.
    """
    c = M.read_json("climo", "climatology.json")
    if not c:
        return None

    # OUR day of the year, in AST, never the sibling payload's own `todoy`.
    # Those pages rebuild on their own schedule and their index is routinely a
    # day behind - which would hand back yesterday's band labelled as today's.
    now_ast = M.utcnow() - _dt.timedelta(hours=4)
    doy = now_ast.timetuple().tm_yday - 1

    stations, normal, monthly, records = {}, {}, {}, {}
    for kind, vars_ in (("buoy", ("hs", "tp", "temp")),
                            ("wind", ("ws", "gust", "temp"))):
        bands = c.get(f"{kind}_bands") or {}
        mon = c.get(f"{kind}_monthly") or {}
        rec = c.get(f"{kind}_records") or {}
        per = c.get(f"{kind}_periods") or {}
        for sid in sorted(set(bands) | set(mon) | set(rec)):
            key = f"{kind}:{sid}"
            b = bands.get(sid) or {}
            p = per.get(sid) or {}
            r = rec.get(sid) or {}
            info = {"name": b.get("name") or r.get("name") or sid}
            if p.get("record"):
                info["record"] = p["record"]
            # Years come from the buoy payload itself; the wind payload has no
            # such field, so wind falls back to the coverage file. Where neither
            # gives one the key is simply absent - never invented.
            yrs = b.get("years") or p.get("years")
            if yrs:
                info["years"] = yrs
            if p.get("status"):
                info["status"] = p["status"]
            stations[key] = info

            band = {v: E.band_at((b.get("bands") or {}).get(v), doy) for v in vars_}
            band = {v: t for v, t in band.items() if t}
            if band:
                normal[key] = band
            if mon.get(sid):
                monthly[key] = mon[sid]
            if r.get("records"):
                records[key] = r["records"]

    if not stations:
        return None
    return {
        "note": "Statistics from past years - NOT a forecast, and it says nothing "
                "about what will happen. Percentile bands are computed over PRIOR "
                "years only: the current year is excluded by construction, which is "
                "what makes 'this September is above normal' a meaningful statement.",
        "units": "hs and hmax m, tp s, ws and gust kt, pressure mb, salinity PSU. "
                 "ALL temperatures in degC - buoy `temp` is WATER temperature, "
                 "wind-station `temp` is AIR temperature (converted from the "
                 "Fahrenheit the mesonet publishes, so it is comparable to the "
                 "live readings).",
        "legend": {
            "normal_today": "[p10, p50, p90] for this calendar day, from prior years",
            "monthly": "12 entries, January..December, null where a month has no "
                       "data. buoy: [hs_mean, hs_p95, tp_mean, temp_mean]. "
                       "wind: [ws_mean, gust_p95, air_temp_mean].",
            "records": "[value, when_AST, named_storm?] - the highest value in the "
                       "whole record (the LOWEST for tmin, tmind, salmin, pmin). "
                       "The third element appears only when the event carries a "
                       "named storm.",
        },
        "for_date_ast": now_ast.date().isoformat(),
        "built": {k: (c.get("meta", {}).get(k) or {}).get("built")
                  for k in ("buoy_bands", "wind_bands")},
        "stations": stations,
        "normal_today": normal,
        "monthly": monthly,
        "records": records,
    }


def _daily(frames):
    """Per calendar day (AST): the roughest value each field reaches that day.

    Worst case, not average: a day whose afternoon gusts to 25 kt is not a
    15-knot day to anyone deciding whether to take a small boat out. Days are
    AST, because that is the day the reader means.
    """
    import datetime as _d
    by_day = {}
    for p in frames:
        start = p.get("start_utc")
        if not start:
            continue
        try:
            t = _d.datetime.fromisoformat(start)
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=_d.timezone.utc)
        key = (t - _d.timedelta(hours=4)).date().isoformat()
        d = by_day.setdefault(key, {"date_ast": key, "periods": [],
                                    "wind_kt_max": None, "gust_kt_max": None,
                                    "seas_m_max": None, "wave_period_s_max": None})
        d["periods"].append(p.get("label"))
        for src, dst in (("wind_kt", "wind_kt_max"), ("gust_kt", "gust_kt_max"),
                         ("hs_m", "seas_m_max"), ("tp_s", "wave_period_s_max")):
            v = p.get(src)
            if v is None:
                continue
            d[dst] = v if d[dst] is None else max(d[dst], v)
    out = []
    for k in sorted(by_day):
        d = by_day[k]
        out.append({"date_ast": d["date_ast"], "periods": d["periods"],
                    "wind_kt_max": _r(d["wind_kt_max"], 0),
                    "gust_kt_max": _r(d["gust_kt_max"], 0),
                    "seas_m_max": _r(d["seas_m_max"], 2),
                    "wave_period_s_max": _r(d["wave_period_s_max"], 1)})
    return out


def _srf_period(q, i):
    """One SRF period: full detail for the days that have a risk category."""
    out = {"name": q.get("name"), "rip_current_risk": q.get("risk"),
           "surf_ft": q.get("surf_ft")}
    if i < 2:
        out["surf_verbatim"] = q.get("surf_text")
        out["weather_verbatim"] = q.get("weather")
        out["winds_verbatim"] = q.get("winds")
    return out


def _still_live(expires):
    """Is this product still in effect?

    NWS stamps `expires` in LOCAL time with an offset ("...T14:45:00-04:00"),
    while our clock is UTC. Comparing the two as strings looked fine and was
    wrong: "14:45:00-04:00" sorts before "18:33:00+00:00" even though 14:45 AST
    is 18:45 UTC - still twelve minutes away. That bug hid a live Special
    Weather Statement warning of 40 mph gusts and hail. Parse, then compare.
    """
    if not expires:
        return True
    try:
        return _dt.datetime.fromisoformat(expires) > M.utcnow()
    except ValueError:
        return True          # unparseable - show it rather than silently drop it


def _r(v, n):
    return None if v is None else round(float(v), n)


def _prov(p, srcs):
    """Provenance in the shape the bot is told to quote back."""
    if not p:
        return None
    if not p.get("observed"):
        return {"measured": False, "from": "NWS zone forecast"}
    sid = p.get("src")
    s = srcs.get(sid)
    return {"measured": True, "station": sid,
            "station_name": s["name_en"] if s else None}


if __name__ == "__main__":
    sys.exit(main())
