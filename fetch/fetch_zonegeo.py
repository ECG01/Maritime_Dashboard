#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Download the NWS marine zone outlines once and store them as SVG paths.

The locator map on the forecast page needs to answer "where is AMZ726?" at a
glance. Rather than pull in a map library and tile server, the zone polygons are
fetched once, simplified, projected, and written out as plain SVG path strings
that the page draws inline. No external requests at render time, works offline,
and themes with the rest of the site.

Zone boundaries do not change, so this is a one-shot: it skips work entirely
unless the cache is missing or --force is passed.

Raw geometry is 443 KB over ten zones (18k vertices). At the size this map is
drawn - a few hundred pixels - that detail is invisible, so it is simplified at
0.005 degrees (~500 m) and rounded to one decimal in SVG units.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402

TOL = 0.005
W = 620.0                                # SVG user units
BBOX = (-68.0, 17.0, -64.0, 19.6)        # lon0, lat0, lon1, lat1


def log(msg):
    print(f"[fetch_zonegeo] {msg}", flush=True)


def project(lon, lat, sx, sy, lon0, lat1):
    """Equirectangular, with the longitude scale corrected for latitude so the
    islands are not stretched east-west. Y is flipped for SVG."""
    return ((lon - lon0) * sx, (lat1 - lat) * sy)


def rings(geom):
    """Polygon/MultiPolygon -> list of coordinate rings."""
    t = geom.get("type")
    cs = geom.get("coordinates") or []
    if t == "Polygon":
        return list(cs)
    if t == "MultiPolygon":
        return [r for poly in cs for r in poly]
    return []


def main(argv):
    out_path = os.path.join(M.DATA, "nws", "zones_geo.json")
    if os.path.exists(out_path) and "--force" not in argv:
        log("cache present; use --force to re-download")
        return 0
    try:
        from shapely.geometry import shape
    except ImportError:
        log("shapely not installed - the locator map will be skipped")
        return 0

    env = M.load_env()
    zones = sorted({s["zone"] for s in M.load_sites()} |
                   set((M.read_json("nws", "cwf.json") or {}).get("zones", {})))

    lon0, lat0, lon1, lat1 = BBOX
    import math
    kx = math.cos(math.radians((lat0 + lat1) / 2.0))
    sx = W / ((lon1 - lon0) * kx)
    sy = sx
    H = round((lat1 - lat0) * sy, 1)

    paths, names, failed = {}, {}, []
    label_xy, extent = {}, {}
    for z in zones:
        url = f"{env['NWS_API']}/zones/marine/{z}"
        try:
            d = M.http_json(url, env["NWS_USER_AGENT"])
        except Exception as e:
            failed.append(z)
            log(f"  {z}: {type(e).__name__}")
            continue
        geom = d.get("geometry")
        if not geom:
            failed.append(z)
            continue
        names[z] = (d.get("properties") or {}).get("name", "")
        simple = shape(geom).simplify(TOL, preserve_topology=True)
        parts = []
        for ring in rings(simple.__geo_interface__):
            pts = []
            for lon, lat in ring:
                x, y = project(lon, lat, sx, sy, lon0, lat1)
                pts.append(f"{x:.1f} {y:.1f}")
            if len(pts) > 2:
                parts.append("M" + "L".join(pts) + "Z")
        if parts:
            paths[z] = "".join(parts)
            # Representative point (not the centroid: a C-shaped coastal zone's
            # centroid falls on land, or inside a different zone) and the zone's
            # own extent, so the page can label and crop without re-parsing paths.
            rp = simple.representative_point()
            lx, ly = project(rp.x, rp.y, sx, sy, lon0, lat1)
            label_xy[z] = [round(lx, 1), round(ly, 1)]
            x0, y0, x1, y1 = simple.bounds
            a = project(x0, y1, sx, sy, lon0, lat1)
            b = project(x1, y0, sx, sy, lon0, lat1)
            extent[z] = [round(a[0], 1), round(a[1], 1), round(b[0], 1), round(b[1], 1)]

    # Crop to what is actually drawn. The declared bbox is a generous frame and
    # left wide empty margins on both sides of the map.
    if extent:
        xs0 = min(e[0] for e in extent.values()); ys0 = min(e[1] for e in extent.values())
        xs1 = max(e[2] for e in extent.values()); ys1 = max(e[3] for e in extent.values())
        pad = 6.0
        view = [round(xs0 - pad, 1), round(ys0 - pad, 1),
                round(xs1 - xs0 + 2 * pad, 1), round(ys1 - ys0 + 2 * pad, 1)]
    else:
        view = [0, 0, W, H]
    payload = {"fetched_utc": M.utcnow().isoformat(), "bbox": BBOX,
               "width": W, "height": H, "tolerance_deg": TOL, "viewbox": view,
               "label_xy": label_xy, "extent": extent,
               "paths": paths, "names": names, "failed": failed}
    M.write_json(payload, "nws", "zones_geo.json")
    M.record("nws_zonegeo", f"{env['NWS_API']}/zones/marine", bool(paths),
             len(json.dumps(payload)), extra={"zones": len(paths)})
    kb = len(json.dumps(payload)) / 1024
    log(f"{len(paths)} zones -> {kb:.0f} KB of SVG paths, viewBox 0 0 {W:.0f} {H:.0f}"
        + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
