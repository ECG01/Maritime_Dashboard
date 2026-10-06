#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read a `const D={...}` payload out of another project's generated HTML.

The Ocean Buoys Hub and the Wind Stations Hub both publish their climatology by
inlining one big JSON object into a page. That object is the only place the
day-of-year percentile bands exist - there is no data file behind them - so this
module is how the maritime chatbot gets to them.

It is the most fragile dependency in this project: a sibling project's HTML
template is not an API, and nobody there has promised us anything. The defence is
not clever parsing, it is refusing to accept a payload that does not look right.
A payload that parses but means something else is far more dangerous than one
that fails outright, because it reaches a mariner with no sign anything is wrong.

Pure text in, dict out - no I/O, no network - so tools/check_climatology.py can
prove every branch.
"""
import json
import re


class EmbeddedPayloadError(ValueError):
    """The payload is missing, unreadable, or not what we expect."""


def _find_marker(text, var):
    """Line index and offset of the single `const <var>=` line."""
    hits = []
    off = 0
    for line in text.split("\n"):
        stripped = line.lstrip()
        # The trailing '=' matters: without it `const D=` also matches
        # `const DATA=`, and we would parse the wrong object entirely.
        if stripped.startswith(f"const {var}="):
            hits.append(off + (len(line) - len(stripped)))
        off += len(line) + 1
    if not hits:
        raise EmbeddedPayloadError(f"no `const {var}=` line found")
    if len(hits) > 1:
        raise EmbeddedPayloadError(
            f"{len(hits)} `const {var}=` lines found - the template changed; "
            f"refusing to guess which one is the data")
    return hits[0]


def _balanced_end(text, start):
    """Index of the `}` closing the object that opens at `start`.

    Brace-counting alone is not enough and a regex is worse. The value strings
    contain braces (a station called "Ponce {test}") and escaped quotes, and the
    line often carries something after the payload - a `;`, a `</script>`. Only
    tracking string state gives an answer that stays correct when the sibling
    changes its line ending, which it will, without telling us.
    """
    depth = 0
    in_str = False
    esc = False
    for k in range(start, len(text)):
        c = text[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return k
    raise EmbeddedPayloadError(
        "payload never closes - the file is truncated or the braces are unbalanced")


def extract(text, var="D"):
    """`const <var>={...}` -> dict. Raises EmbeddedPayloadError on anything else."""
    if not text or not text.strip():
        raise EmbeddedPayloadError("empty document")
    pos = _find_marker(text, var)
    brace = text.find("{", pos)
    if brace < 0:
        raise EmbeddedPayloadError(f"`const {var}=` is not followed by an object")
    end = _balanced_end(text, brace)
    try:
        return json.loads(text[brace:end + 1])
    except ValueError as e:
        raise EmbeddedPayloadError(f"payload is not valid JSON: {e}") from None


# Keys that are not stations. The mesonet extremes report carries a `__short__`
# name map beside the real entries; iterating naively yields a station called
# `__short__` and a chatbot that cheerfully quotes its records.
def stations_of(obj, require=("years",)):
    """The real station entries, with sentinels and malformed rows dropped."""
    src = obj.get("stations") if isinstance(obj.get("stations"), dict) else obj
    out = {}
    for k, v in src.items():
        if k.startswith("__") or not isinstance(v, dict):
            continue
        if require and not all(r in v for r in require):
            continue
        out[k] = v
    return out


_BAND = ("yp10", "yp50", "yp90")
YEAR_LENS = (365, 366)


def coverage_station_climate(obj, doy_index=None, variables=None):
    """How much of a station_climate payload is actually usable.

    `doy_index` is OUR day of the year, never the payload's own `todoy`: the
    sibling page is rebuilt on its own schedule and its index is routinely a day
    or more behind, which would hand back yesterday's band labelled as today's.

    `variables` limits the count to the ones we actually consume. Without it the
    rate is meaningless: the wind payload carries `pres`, `temp` and `rain`
    bands we deliberately drop, and counting their nulls pushed a perfectly
    healthy file under the floor. A null band on a station too new to have a
    climatology is also correct upstream behaviour, not a broken payload - such
    a station is simply omitted downstream.
    """
    st = stations_of(obj, require=())
    pairs = 0
    good = 0
    ordered = 0
    for sid, s in st.items():
        for var, b in s.items():
            if variables and var not in variables:
                continue
            if not isinstance(b, dict) or not isinstance(b.get("yp50"), list):
                continue
            pairs += 1
            lens = {len(b[k]) for k in _BAND if isinstance(b.get(k), list)}
            if len(lens) != 1 or lens.pop() not in YEAR_LENS:
                continue
            i = doy_index if doy_index is not None else 0
            i = min(i, len(b["yp50"]) - 1)
            trio = [b[k][i] for k in _BAND]
            if any(v is None for v in trio):
                continue
            good += 1
            # p10 <= p50 <= p90 is free to check and is the one assertion that
            # catches a silent key rename or a column swap upstream.
            if trio[0] <= trio[1] <= trio[2]:
                ordered += 1
    return {"stations": len(st), "pairs": pairs, "usable": good,
            "band_rate": (good / pairs) if pairs else 0.0,
            "order_rate": (ordered / good) if good else 0.0,
            "built": obj.get("built")}


def coverage_extremes(obj):
    st = stations_of(obj, require=("years",))
    entries = sum(len(v.get("years") or {}) for v in st.values())
    return {"stations": len(st), "year_entries": entries}


def band_at(block, index):
    """[p10, p50, p90] at a day-of-year index, or None.

    Clamps rather than wrapping: on 31 December of a leap year against a
    365-long array, wrapping would silently return 1 January.
    """
    if not isinstance(block, dict):
        return None
    try:
        arrs = [block[k] for k in _BAND]
    except (KeyError, TypeError):
        return None
    if not all(isinstance(a, list) and a for a in arrs):
        return None
    i = max(0, min(int(index), min(len(a) for a in arrs) - 1))
    trio = [a[i] for a in arrs]
    if any(v is None for v in trio):
        return None
    return [round(float(v), 2) for v in trio]


_BUILT = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def built_date(obj):
    """The upstream page's own build date as YYYY-MM-DD, or None."""
    m = _BUILT.search(str(obj.get("built") or ""))
    return m.group(0) if m else None
