#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Parse the NWS Surf Zone Forecast (SRF) for Puerto Rico and the USVI.

This product is a FORECAST, not an alert, and the distinction is the whole point
of carrying it: a Moderate rip current risk never becomes a Rip Current
Statement, so it is invisible in the alerts feed while still being the thing a
swimmer or a small-boat operator most needs to know. Only a HIGH risk is issued
as a product.

The segment shape, verified against SRFSJU 2026-09-29:

    PRZ001-292015-
    San Juan and Vicinity PR-
    Including the beaches of Carolina, San Juan and Toa Baja
    329 AM AST Tue Sep 29 2026

    .TODAY...
    Rip Current Risk*...........Moderate.
    Surf Height.................Around 4 feet.
    Weather.....................Partly sunny. Scattered showers with
                                isolated thunderstorms.
    Winds.......................East winds 10 to 15 mph.

    .THURSDAY...Surf height around 4 feet. Mostly sunny. ...

    &&
    <risk category glossary>
    $$

Two period forms in ONE product: the first days use a labelled block, the outlook
days are one prose line. Both are parsed; only the labelled form carries a risk
category, which is why `risk` is None rather than "low" on an outlook day - an
absent category is not a low one.
"""
import re

# The categories are the product's own, quoted here so the meaning travels with
# the value and the page never has to invent a definition for them.
RISK_MEANING = {
    "low": "Low Risk - The risk for rip currents is low, however, life-threatening "
           "rip currents often occur in the vicinity of groins, jetties, reefs, and piers.",
    "moderate": "Moderate Risk - Life-threatening rip currents are possible in the surf zone.",
    "high": "High Risk - Life-threatening rip currents are likely in the surf zone.",
}
RISK_ES = {"low": "Bajo", "moderate": "Moderado", "high": "Alto"}

_ZONE = re.compile(r"^([A-Z]{2}Z\d{3})(?:-[A-Z]{2}Z\d{3})*-\d{6}-\s*$", re.M)
_ISSUED = re.compile(r"^(\d{3,4})\s+(AM|PM)\s+([A-Z]{3})\s+\w+\s+(\w+)\s+(\d+)\s+(\d{4})\s*$", re.M)
_WMO = re.compile(r"^\w{6}\s+(\w{4})\s+(\d{6})\s*$", re.M)
# A labelled row: dots, then the value, running on until the next labelled row,
# the next period, or the end of the block.
_ROW = re.compile(r"^([A-Z][A-Za-z ]+?)\*?\.{3,}\s*(.*?)(?=^\S|\Z)", re.M | re.S)
_PERIOD = re.compile(r"^\.([A-Z][A-Z ]*?)\.\.\.", re.M)
_FT = re.compile(r"(\d+)(?:\s*(?:to|-)\s*(\d+))?\s*(?:feet|foot|ft)", re.I)


def _clean(s):
    """Collapse the product's hard wrapping into one line."""
    return re.sub(r"\s+", " ", (s or "")).strip().rstrip(".").strip()


def _risk(text):
    t = (text or "").strip().lower()
    for k in ("high", "moderate", "low"):
        if k in t:
            return k
    return None


def surf_ft(text):
    """'Around 4 feet' -> (4, 4); '3 to 5 feet' -> (3, 5); no match -> None."""
    m = _FT.search(text or "")
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return (min(lo, hi), max(lo, hi))


def _periods(block):
    """Split one zone's forecast into its periods, handling both forms."""
    out = []
    marks = list(_PERIOD.finditer(block))
    for i, m in enumerate(marks):
        name = m.group(1).strip().title()
        body = block[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(block))]
        rows = {_clean(k).lower(): _clean(v) for k, v in _ROW.findall(body)}
        if rows:
            risk_text = rows.get("rip current risk")
            surf = rows.get("surf height", "")
            p = {"name": name, "risk": _risk(risk_text), "risk_text": risk_text or None,
                 "surf_text": surf or None, "weather": rows.get("weather") or None,
                 "winds": rows.get("winds") or None}
        else:
            # The outlook form: one prose line. It carries surf height and
            # weather but never a risk category.
            prose = _clean(body)
            sm = re.search(r"(Surf height[^.]*\.)", prose, re.I)
            p = {"name": name, "risk": None, "risk_text": None,
                 "surf_text": _clean(sm.group(1)) if sm else None,
                 "weather": prose or None, "winds": None}
        p["surf_ft"] = surf_ft(p["surf_text"])
        out.append(p)
    return out


def parse(text):
    """SRF product text -> {issued_utc, office, zones:[...]}. Never raises."""
    text = (text or "").replace("\r", "")
    zones = []
    for seg in text.split("$$"):
        zm = _ZONE.search(seg)
        if not zm:
            continue
        # Everything after && is the risk-category glossary, not forecast.
        body = seg.split("&&")[0]
        after = body[zm.end():]
        lines = [l.rstrip() for l in after.split("\n")]
        name, beaches = None, None
        for i, l in enumerate(lines):
            s = l.strip()
            if not s:
                continue
            if name is None and s.endswith("-"):
                name = s[:-1].strip()
                continue
            if s.lower().startswith("including the beaches"):
                # The list wraps over as many lines as it needs; stop at the
                # blank line, the issuance-time line, or the first period.
                # Reading only the first line truncated "Arecibo, Manati, Vega
                # Baja," mid-list, trailing comma and all.
                buf = [s]
                for nxt in lines[i + 1:]:
                    t = nxt.strip()
                    if not t or t.startswith(".") or re.match(r"^\d", t):
                        break
                    buf.append(t)
                joined = " ".join(buf)
                beaches = _clean(joined.split(" of ", 1)[-1]
                                 if " of " in joined.lower() else joined)
                continue
            if s.startswith("."):
                break
        periods = _periods(after)
        if not periods:
            continue
        zones.append({"zone": zm.group(1), "name": name or zm.group(1),
                      "beaches": beaches, "periods": periods})
    return {"issued_utc": issued_utc(text), "office": office(text), "zones": zones}


_AWIPS = re.compile(r"^SRF([A-Z]{3})\s*$", re.M)


def office(text):
    """From the AWIPS id line (SRFSJU -> SJU).

    NOT from the WMO header: that carries the transmitting station TJSJ, and
    slicing it gives JSJ, which is not an office anywhere.
    """
    m = _AWIPS.search(text or "")
    return m.group(1) if m else ""


def issued_utc(text):
    """The WMO header's DDHHMM stamp is already UTC - use it, not the local line.

    The plain-language line says '329 AM AST', and turning that back into UTC
    means guessing the year and the offset. The header does not.
    """
    import datetime as dt
    m = _WMO.search(text or "")
    if not m:
        return None
    ddhhmm = m.group(2)
    now = dt.datetime.now(dt.timezone.utc)
    try:
        day, hh, mm = int(ddhhmm[:2]), int(ddhhmm[2:4]), int(ddhhmm[4:6])
        y, mo = now.year, now.month
        # A day-of-month far ahead of today means the product crossed a month end.
        if day - now.day > 15:
            mo -= 1
            if mo == 0:
                mo, y = 12, y - 1
        return dt.datetime(y, mo, day, hh, mm, tzinfo=dt.timezone.utc).isoformat()
    except ValueError:
        return None


def coverage(parsed):
    """What fraction of zones actually produced a risk category for day one."""
    zones = parsed.get("zones") or []
    with_risk = sum(1 for z in zones
                    if any(p.get("risk") for p in z.get("periods") or []))
    return {"zones": len(zones),
            "risk_rate": (with_risk / len(zones)) if zones else 0.0,
            "periods": sum(len(z.get("periods") or []) for z in zones)}


def today(parsed):
    """zone id -> its first period, for a quick per-zone read."""
    return {z["zone"]: (z["periods"][0] if z.get("periods") else None)
            for z in parsed.get("zones") or []}
