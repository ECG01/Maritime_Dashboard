# -*- coding: utf-8 -*-
"""Parse the NWS Coastal Waters Forecast (CWF) into per-zone forecast frames.

The CWF for NWS San Juan (product CWFSJU) carries, for every PR/USVI marine zone,
a five-day forecast in '.PERIOD...' paragraphs with wind direction and speed in
knots, gusts, seas in feet and - the valuable part - a 'Wave Detail:' clause
giving wave direction, height and PERIOD. That is Hs, Tp and Dp per zone out to
five days, which is why Phase 1 of this dashboard needs no model data at all.

    AMZ726-182200-
    Coastal waters east of Puerto Rico, around Vieques, and around and
    just north of Culebra and Saint John-
    343 AM AST Fri Sep 18 2026

    .TODAY...East winds 10 to 15 knots. Seas 3 to 4 feet, occasionally
    to 5 feet. Wave Detail: East 4 feet at 6 seconds. Scattered showers...

IMPORTANT - what this module does and does not do. It extracts NUMBERS so the
dashboard can compute its own Operational Suitability. It never rewrites, reworks
or translates the NWS text itself: the forecast wording is reproduced verbatim,
in English, attributed to NWS, in its own panel. See marlib.DISCLAIMER_EN.

The product is free text, so parsing is defensive: anything unrecognised is left
as None rather than guessed at, and the caller checks coverage before publishing.
"""
import datetime as dt
import re

# NWS writes directions as words. 16-point compass -> degrees the wind/waves come FROM.
DIRS = {
    "north": 0.0, "north-northeast": 22.5, "northeast": 45.0, "east-northeast": 67.5,
    "east": 90.0, "east-southeast": 112.5, "southeast": 135.0, "south-southeast": 157.5,
    "south": 180.0, "south-southwest": 202.5, "southwest": 225.0, "west-southwest": 247.5,
    "west": 270.0, "west-northwest": 292.5, "northwest": 315.0, "north-northwest": 337.5,
}
FT_TO_M = 0.3048
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_SEG_ZONE = re.compile(r"^(AMZ\d{3})((?:-\d{3})*)-(\d{6})-", re.M)
_PERIOD = re.compile(r"^\.([A-Z][A-Z .'/-]*?)\.\.\.", re.M)
_WIND = re.compile(
    r"\b([a-z-]+)(?:\s+to\s+([a-z-]+))?\s+winds?\s+(?:around\s+)?(\d+)(?:\s+to\s+(\d+))?\s+kt?s?\b|"
    r"\b([a-z-]+)(?:\s+to\s+([a-z-]+))?\s+winds?\s+(?:around\s+)?(\d+)(?:\s+to\s+(\d+))?\s+knots?\b",
    re.I)
_GUST = re.compile(r"gusts?\s+(?:up\s+)?to\s+(\d+)\s+knots?", re.I)
_SEAS = re.compile(r"\bseas?\s+(?:around\s+)?(\d+)(?:\s+to\s+(\d+))?\s+(?:feet|foot|ft)\b", re.I)
_SEAS_OCC = re.compile(r"occasionally\s+to\s+(\d+)\s+(?:feet|foot|ft)", re.I)
_WAVE_DETAIL = re.compile(r"wave\s+detail:\s*(.+?)(?:\n\s*\n|$)", re.I | re.S)
_WAVE_ITEM = re.compile(r"([a-z-]+)\s+(\d+(?:\.\d+)?)\s+(?:feet|foot|ft)\s+at\s+(\d+)\s+seconds?", re.I)
_ISSUED = re.compile(r"^\s*(\d{3,4})\s+(AM|PM)\s+([A-Z]{3})\s+\w{3}\s+(\w{3})\s+(\d{1,2})\s+(\d{4})",
                     re.M)


def _dir_deg(word, word2=None):
    """'east' -> 90.0; 'east to southeast' -> the midpoint, 112.5."""
    if not word:
        return None
    a = DIRS.get(word.strip().lower())
    if word2:
        b = DIRS.get(word2.strip().lower())
        if a is not None and b is not None:
            d = ((b - a + 180.0) % 360.0) - 180.0
            return (a + d / 2.0) % 360.0
    return a


def _issued_utc(text):
    """Issuance time from the '343 AM AST Fri Sep 18 2026' line -> aware UTC datetime.

    Puerto Rico is AST (UTC-4) year round with no daylight saving, which is why
    this can be a fixed offset rather than a tz database lookup.
    """
    m = _ISSUED.search(text)
    if not m:
        return None
    hhmm, ampm, tz, mon, day, year = m.groups()
    hhmm = hhmm.zfill(4)
    hh, mm = int(hhmm[:2]), int(hhmm[2:])
    if ampm == "PM" and hh != 12:
        hh += 12
    if ampm == "AM" and hh == 12:
        hh = 0
    try:
        local = dt.datetime.strptime(f"{mon} {day} {year} {hh:02d}:{mm:02d}", "%b %d %Y %H:%M")
    except ValueError:
        return None
    off = {"AST": 4, "EST": 5, "EDT": 4}.get(tz, 4)
    return local.replace(tzinfo=dt.timezone.utc) + dt.timedelta(hours=off)


def _period_window(label, issued_utc):
    """'.SATURDAY NIGHT...' -> (start_utc, end_utc). None when unrecognised.

    Day periods run 06-18 AST, night periods 18-06 AST. AST is UTC-4.
    """
    if issued_utc is None:
        return (None, None)
    lab = label.strip().lower()
    local = issued_utc - dt.timedelta(hours=4)
    day0 = local.replace(hour=0, minute=0, second=0, microsecond=0)

    def w(dayoffset, night):
        s = day0 + dt.timedelta(days=dayoffset, hours=18 if night else 6)
        e = s + dt.timedelta(hours=12)
        return (s + dt.timedelta(hours=4), e + dt.timedelta(hours=4))   # back to UTC

    if lab in ("today", "rest of today", "this afternoon", "this morning"):
        s, e = w(0, False)
        return (max(s, issued_utc), e)
    if lab in ("tonight", "rest of tonight", "this evening", "overnight"):
        s, e = w(0, True)
        return (max(s, issued_utc), e)
    night = lab.endswith(" night")
    name = lab[:-6].strip() if night else lab
    if name in _WEEKDAYS:
        for k in range(0, 8):
            d = day0 + dt.timedelta(days=k)
            if _WEEKDAYS[d.weekday()] == name:
                return w(k, night)
    return (None, None)


def parse_periods(body):
    """The '.PERIOD...' paragraphs of one zone segment -> list of dicts."""
    out = []
    marks = list(_PERIOD.finditer(body))
    for i, m in enumerate(marks):
        label = m.group(1).strip()
        chunk = body[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(body)]
        flat = " ".join(chunk.split())
        p = {"label": label, "text": flat.strip()}

        wm = _WIND.search(flat)
        if wm:
            g = wm.groups()
            d1, d2, lo, hi = (g[0], g[1], g[2], g[3]) if g[2] else (g[4], g[5], g[6], g[7])
            p["wdir_deg"] = _dir_deg(d1, d2)
            lo, hi = (int(lo) if lo else None), (int(hi) if hi else None)
            # rate on the TOP of the forecast range: a captain plans for the worst
            # of the window, not its midpoint.
            p["wind_kt"] = float(hi if hi is not None else lo) if lo is not None else None
            p["wind_kt_low"] = float(lo) if lo is not None else None

        gm = _GUST.search(flat)
        if gm:
            p["gust_kt"] = float(gm.group(1))

        sm = _SEAS.search(flat)
        if sm:
            lo = int(sm.group(1))
            hi = int(sm.group(2)) if sm.group(2) else lo
            p["seas_ft"] = float(hi)
            p["hs_m"] = float(hi) * FT_TO_M
        om = _SEAS_OCC.search(flat)
        if om:
            p["seas_occ_ft"] = float(om.group(1))

        wd = _WAVE_DETAIL.search(chunk)
        if wd:
            items = []
            for it in _WAVE_ITEM.finditer(" ".join(wd.group(1).split())):
                items.append({"dir_deg": _dir_deg(it.group(1)),
                              "hs_m": float(it.group(2)) * FT_TO_M,
                              "tp_s": float(it.group(3))})
            if items:
                # the largest listed train is the one that decides suitability
                lead = max(items, key=lambda x: x["hs_m"])
                p["dp_deg"] = lead["dir_deg"]
                p["tp_s"] = lead["tp_s"]
                p["wave_trains"] = items
                p.setdefault("hs_m", lead["hs_m"])
        out.append(p)
    return out


def parse(text):
    """Full CWF product text -> {'issued_utc', 'synopsis', 'zones': {zone: {...}}}."""
    issued = _issued_utc(text)
    zones, synopsis = {}, None
    for seg in text.split("$$"):
        m = _SEG_ZONE.search(seg)
        if not m:
            continue
        ids = [m.group(1)]
        if m.group(2):
            prefix = m.group(1)[:3]
            ids += [prefix + x for x in m.group(2).strip("-").split("-") if x]
        body = seg[m.end():]
        # the zone name is the line(s) between the header and the timestamp line
        name = ""
        lines = [ln.rstrip() for ln in body.splitlines()]
        for ln in lines:
            if not ln.strip():
                continue
            if _ISSUED.match(ln) or ln.strip().startswith("."):
                break
            name += (" " if name else "") + ln.strip().rstrip("-")
        periods = parse_periods(body)
        if ids[0].endswith("700") and not periods:
            synopsis = " ".join(body.split("...", 1)[-1].split()) if "..." in body else None
            continue
        for z in ids:
            zones[z] = {"zone": z, "name": name.strip(), "periods": periods,
                        "issued_utc": issued.isoformat() if issued else None}
    return {"issued_utc": issued.isoformat() if issued else None,
            "synopsis": synopsis, "zones": zones}


def coverage(parsed):
    """Sanity metrics the fetcher checks before overwriting a good cached parse."""
    zs = parsed.get("zones", {})
    per = sum(len(z["periods"]) for z in zs.values())
    wave = sum(1 for z in zs.values() for p in z["periods"] if p.get("tp_s") is not None)
    wind = sum(1 for z in zs.values() for p in z["periods"] if p.get("wind_kt") is not None)
    return {"zones": len(zs), "periods": per, "with_wave_detail": wave, "with_wind": wind,
            "wave_rate": (wave / per) if per else 0.0, "wind_rate": (wind / per) if per else 0.0}


def frames(parsed, zone):
    """One zone's periods as a contiguous, time-stamped series for the planner.

    Adds 'start_utc'/'end_utc' to each period and clamps the FIRST window back to
    the issuance time: the CWF is often issued around 03:40 AST while its first
    'TODAY' window begins at 06:00 AST, and without this the board would show an
    unexplained gap for the couple of hours a pre-dawn departure actually cares
    about. Periods whose label could not be mapped to a window are dropped, and
    the caller can see that in coverage().
    """
    z = parsed.get("zones", {}).get(zone)
    if not z:
        return []
    issued = z.get("issued_utc") or parsed.get("issued_utc")
    iss = dt.datetime.fromisoformat(issued) if issued else None
    out = []
    for p in z["periods"]:
        s, e = _period_window(p["label"], iss)
        if s is None:
            continue
        q = dict(p)
        q["start_utc"], q["end_utc"] = s.isoformat(), e.isoformat()
        out.append(q)
    out.sort(key=lambda x: x["start_utc"])
    if out and iss is not None:
        first = dt.datetime.fromisoformat(out[0]["start_utc"])
        if iss < first:
            out[0]["start_utc"] = iss.isoformat()
    return out
