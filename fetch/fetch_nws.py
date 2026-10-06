#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fetch the NWS Coastal Waters Forecast and any active marine products.

Writes, atomically, under data/nws/:
    cwf.json      the parsed forecast PLUS the verbatim product text
    srf.json      the Surf Zone Forecast: rip current risk and surf by beach zone
    alerts.json   active products for the PR and VI marine zones, verbatim
    zones.json    zone id -> official name, discovered from the API

Two rules this file exists to enforce:

1. The verbatim NWS text is carried alongside the parsed numbers and is NEVER
   rewritten or translated. Pages show it as issued, attributed to NWS, in its own
   panel. The parsed numbers drive CariCOOS Operational Suitability, which is a
   separate thing with a separate name.

2. A bad fetch must not destroy a good cache. If the download fails, or the parse
   comes back with implausibly thin coverage (NWS changed the wording, or we got a
   truncated product), the previous payload is LEFT IN PLACE and the failure is
   recorded in the manifest. status.html then shows the age. A dashboard that
   blanks out when one API hiccups is worse than useless to someone deciding
   whether to leave the dock.

    $PYTHON fetch/fetch_nws.py [--dry-run]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                       # noqa: E402
from engine import cwf_parse as C        # noqa: E402
from engine import srf_parse as SR       # noqa: E402

# Below these, assume the product or the parser is broken and keep the cache.
MIN_ZONES = 6
MIN_WIND_RATE = 0.75
# The SRF covers 12 beach zones (10 PR + 2 VI). Accept some slack for a zone
# NWS drops, but a parse that collapses to a handful means the wording moved.
MIN_SRF_ZONES = 8
MIN_SRF_RISK_RATE = 0.75


def log(msg):
    print(f"[fetch_nws] {msg}", flush=True)


def fetch_cwf(env, dry=False):
    api, ua = env["NWS_API"], env["NWS_USER_AGENT"]
    office = env["NWS_CWF_OFFICE"]
    listing = f"{api}/products/types/CWF/locations/{office}"
    try:
        graph = M.http_json(listing, ua).get("@graph") or []
        if not graph:
            raise RuntimeError("no CWF products listed")
        pid = str(graph[0]["id"]).rsplit("/", 1)[-1]
        url = f"{api}/products/{pid}"
        prod = M.http_json(url, ua)
        text = prod.get("productText") or ""
        if not text.strip():
            raise RuntimeError("empty productText")
    except Exception as e:
        M.record("nws_cwf", listing, False, error=repr(e))
        log(f"WARN: CWF fetch failed ({e!r}); keeping the cached forecast")
        return None

    parsed = C.parse(text)
    cov = C.coverage(parsed)
    if cov["zones"] < MIN_ZONES or cov["wind_rate"] < MIN_WIND_RATE:
        M.record("nws_cwf", url, False, len(text),
                 error=f"implausible coverage {cov}", extra={"coverage": cov})
        log(f"WARN: CWF parsed to {cov['zones']} zones / wind_rate {cov['wind_rate']:.2f} "
            f"- below the floor, keeping the cached forecast. Check the product wording.")
        return None

    payload = {
        "issued_utc": parsed["issued_utc"],
        "synopsis": parsed["synopsis"],
        "zones": parsed["zones"],
        "product_id": pid,
        "product_url": url,
        # verbatim, unaltered, for the NWS panel
        "product_text": text,
        "office": office,
        "coverage": cov,
        "fetched_utc": M.utcnow().isoformat(),
    }
    if not dry:
        M.write_json(payload, "nws", "cwf.json")
        M.record("nws_cwf", url, True, len(text), extra={"coverage": cov})
    log(f"CWF {pid}: {cov['zones']} zones, {cov['periods']} periods, "
        f"wind {cov['wind_rate']:.0%}, wave detail {cov['wave_rate']:.0%}")
    return payload


def fetch_srf(env, dry=False):
    """The Surf Zone Forecast - rip current risk and surf height by beach zone.

    Worth its own fetch because it is the hazard the alerts feed cannot show:
    a MODERATE rip current risk is never issued as a product, so it is invisible
    in alerts.json while still being the number that decides whether a family
    should swim. Only a HIGH risk becomes a Rip Current Statement.

    It is a FORECAST. Pages must label it as such - it is not an advisory, and
    calling it one would misstate what NWS issued.
    """
    api, ua = env["NWS_API"], env["NWS_USER_AGENT"]
    office = env["NWS_CWF_OFFICE"]
    listing = f"{api}/products/types/SRF/locations/{office}"
    try:
        graph = M.http_json(listing, ua).get("@graph") or []
        if not graph:
            raise RuntimeError("no SRF products listed")
        pid = str(graph[0]["id"]).rsplit("/", 1)[-1]
        url = f"{api}/products/{pid}"
        text = (M.http_json(url, ua).get("productText") or "")
        if not text.strip():
            raise RuntimeError("empty productText")
    except Exception as e:
        M.record("nws_srf", listing, False, error=repr(e))
        log(f"WARN: SRF fetch failed ({e!r}); keeping the cached surf forecast")
        return None

    parsed = SR.parse(text)
    cov = SR.coverage(parsed)
    if cov["zones"] < MIN_SRF_ZONES or cov["risk_rate"] < MIN_SRF_RISK_RATE:
        M.record("nws_srf", url, False, len(text),
                 error=f"implausible coverage {cov}", extra={"coverage": cov})
        log(f"WARN: SRF parsed to {cov['zones']} zones / risk_rate "
            f"{cov['risk_rate']:.2f} - below the floor, keeping the cache. "
            f"Check the product wording.")
        return None

    payload = {
        "issued_utc": parsed["issued_utc"],
        "zones": parsed["zones"],
        "risk_meaning": SR.RISK_MEANING,
        "product_id": pid,
        "product_url": url,
        # verbatim, unaltered, for the NWS panel
        "product_text": text,
        "office": parsed["office"] or office,
        "coverage": cov,
        "fetched_utc": M.utcnow().isoformat(),
    }
    if not dry:
        M.write_json(payload, "nws", "srf.json")
        M.record("nws_srf", url, True, len(text), extra={"coverage": cov})
    high = [z["zone"] for z in parsed["zones"]
            if (z["periods"] or [{}])[0].get("risk") == "high"]
    log(f"SRF {pid}: {cov['zones']} beach zones, risk on {cov['risk_rate']:.0%}"
        + (f", HIGH rip current risk in {', '.join(high)}" if high else ""))
    return payload


def fetch_alerts(env, dry=False):
    api, ua = env["NWS_API"], env["NWS_USER_AGENT"]
    out, ok = [], True
    for area in ("PR", "VI"):
        url = f"{api}/alerts/active?area={area}"
        try:
            d = M.http_json(url, ua)
        except Exception as e:
            ok = False
            log(f"WARN: alerts {area} failed ({e!r})")
            continue
        for f in d.get("features", []):
            p = f.get("properties", {})
            zones = [z.rsplit("/", 1)[-1] for z in (p.get("affectedZones") or [])]
            marine = [z for z in zones if z.startswith("AMZ")]
            land = [z for z in zones if not z.startswith("AMZ")]
            # EVERY active product for PR/USVI, with no zone filter at all.
            # This started as marine-only, which hid a live Rip Current Statement
            # reading "life-threatening rip currents"; narrowing it again to
            # marine+coastal would hide the next thing nobody predicted - a heat
            # advisory before a day on the water, a drought notice, a flood
            # warning on the road to the marina. Deciding for the reader which
            # NWS products matter is how the first omission happened.
            out.append({
                "scope": "marine" if marine else "land",
                "id": p.get("id"), "event": p.get("event"), "severity": p.get("severity"),
                "urgency": p.get("urgency"), "certainty": p.get("certainty"),
                "onset": p.get("onset"), "expires": p.get("expires"), "ends": p.get("ends"),
                "sender": p.get("senderName"),
                # verbatim NWS wording - never reworded, never translated
                "headline": p.get("headline"), "description": p.get("description"),
                "instruction": p.get("instruction"),
                "zones": marine or land,
                "marine_zones": marine, "land_zones": land,
            })
    payload = {"fetched_utc": M.utcnow().isoformat(), "count": len(out), "alerts": out}
    if not dry:
        M.write_json(payload, "nws", "alerts.json")
        M.record("nws_alerts", f"{api}/alerts/active", ok, len(str(out)))
    nm = sum(1 for a in out if a["scope"] == "marine")
    log(f"active NWS products: {nm} marine, {len(out) - nm} land "
        + (f"({', '.join(sorted({a['event'] for a in out}))})" if out else ""))
    return payload


def discover_zones(env, sites, dry=False):
    """Confirm each site's configured zone against the API, by its offshore point.

    Harbour coordinates fall outside every marine polygon (Cruz Bay and Salinas
    both do), which is what sites.tsv's zone_lat/zone_lon columns are for. A
    mismatch here is a config error worth shouting about: it would silently rate a
    site against the wrong stretch of water.
    """
    api, ua = env["NWS_API"], env["NWS_USER_AGENT"]
    found, mismatched = {}, []
    for s in sites:
        url = f"{api}/zones?type=marine&point={s['zone_lat']},{s['zone_lon']}"
        try:
            d = M.http_json(url, ua)
        except Exception as e:
            log(f"WARN: zone lookup for {s['site_id']} failed ({e!r})")
            continue
        ids = [f["properties"]["id"] for f in d.get("features", [])]
        names = {f["properties"]["id"]: f["properties"].get("name") for f in d.get("features", [])}
        if not ids:
            mismatched.append((s["site_id"], s["zone"], "NO ZONE at zone_lat/zone_lon"))
            continue
        found.update(names)
        if s["zone"] not in ids:
            mismatched.append((s["site_id"], s["zone"], ",".join(ids)))
    for sid, want, got in mismatched:
        log(f"WARN: {sid} is configured as {want} but its point resolves to {got}")
    if not dry:
        M.write_json({"fetched_utc": M.utcnow().isoformat(), "zones": found,
                      "mismatched": mismatched}, "nws", "zones.json")
        M.record("nws_zones", f"{api}/zones?type=marine", not mismatched, len(str(found)))
    log(f"zones confirmed: {len(found)}, mismatches: {len(mismatched)}")
    return found


def main(argv):
    dry = "--dry-run" in argv
    problems = M.validate()
    if problems:
        for p in problems:
            log(f"CONFIG ERROR: {p}")
        return 2
    env = M.load_env()
    fetch_cwf(env, dry)
    fetch_srf(env, dry)
    fetch_alerts(env, dry)
    if "--zones" in argv:
        discover_zones(env, M.load_sites(), dry)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
