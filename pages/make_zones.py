#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/marine_zones.html - the official NWS forecast, verbatim.

Editorial rule, and the reason this page is separate from every other one:
the National Weather Service text is reproduced AS ISSUED, in English, and is
never machine-translated. Translating an official marine forecast would create a
second, unofficial version of a safety product under CariCOOS's name. Our own
bilingual reading of the numbers sits beside it, clearly labelled as ours.

Two things this page has to do that plain text cannot:

  * Say WHERE. "AMZ726" means nothing until you see it. An overview map at the
    top and a small locator beside each zone answer that before any reading.
  * Stay short. Ten zones by six forecast periods is a wall of text nobody
    scans. Only the first two periods are open; the rest sit behind a disclosure.

Maps are inline SVG built from cached NWS polygons (fetch/fetch_zonegeo.py) -
no map library, no tile server, no request at render time.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402

OPEN_PERIODS = 2

CSS = r"""
.zone{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  margin-bottom:1rem;overflow:hidden}
.zone .zh{display:flex;gap:.9rem;align-items:flex-start;padding:.75rem .9rem;
  background:var(--controls);border-bottom:1px solid var(--line)}
.zone .zh .txt{flex:1;min-width:0}
.zone .zh h3{margin:0;font:700 1rem "Archivo",sans-serif}
.zone .zid{font:700 .78rem "JetBrains Mono",monospace;color:var(--teal);letter-spacing:.04em}
.zone .sites{font-size:.85rem;color:var(--ink2);margin-top:.15rem}
.cols{display:flex;gap:0;flex-wrap:wrap}
.verb{flex:1 1 400px;min-width:300px;padding:.8rem .9rem;border-right:1px solid var(--line)}
.ours{flex:0 1 290px;min-width:250px;padding:.8rem .9rem;background:var(--surface)}
.colh{font:700 .7rem "Archivo",sans-serif;letter-spacing:.07em;text-transform:uppercase;
  color:var(--ink2);margin-bottom:.45rem}
.verb .colh{color:var(--s2)}
.per{margin-bottom:.55rem}
.per b{font:700 .8rem "Archivo",sans-serif;letter-spacing:.04em}
.per .txt{font-size:.9rem;line-height:1.45}
details.more{margin-top:.3rem}
details.more summary{cursor:pointer;font:600 .84rem "Source Sans 3",sans-serif;
  color:var(--s1);list-style:none}
details.more summary::-webkit-details-marker{display:none}
details.more summary::before{content:"\25B8 ";display:inline-block;transition:transform .12s}
details.more[open] summary::before{transform:rotate(90deg)}
table.sum{width:100%;border-collapse:collapse;font-size:.86rem}
table.sum th{text-align:left;font:600 .68rem "Archivo",sans-serif;text-transform:uppercase;
  letter-spacing:.05em;color:var(--ink2);padding:.2rem .25rem;border-bottom:1px solid var(--line)}
table.sum td{padding:.2rem .25rem;border-bottom:1px solid var(--grid);
  font-variant-numeric:tabular-nums;white-space:nowrap}
tr.trains td{border-bottom:1px solid var(--grid);padding:.1rem .25rem .3rem;
  white-space:normal;line-height:1.5}
tr.trains .lbl{font:700 .62rem "Archivo",sans-serif;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink2);margin-right:.4rem}
tr.trains .tr{display:inline-block;font-size:.8rem;background:var(--btn);
  border:1px solid var(--line);border-radius:4px;padding:.02rem .34rem;
  margin:.1rem .25rem .1rem 0;white-space:nowrap}
tr.trains .at{color:var(--ink2);margin:0 .18rem}
.nodet{font-size:.76rem;color:var(--ink2);line-height:1.4;margin-top:.45rem;
  padding-top:.4rem;border-top:1px dashed var(--line)}

/* maps */
.locator{flex:0 0 auto;width:132px}
.locator svg{display:block;width:132px;height:auto;border:1px solid var(--line);
  border-radius:6px;background:var(--surface)}
.overview{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:.8rem;margin-bottom:1.2rem}
.overview svg{display:block;width:100%;height:auto;max-height:430px}
.zoneshape{fill:var(--btn);stroke:var(--ink2);stroke-width:1.1;stroke-opacity:.55;
  vector-effect:non-scaling-stroke}
.zoneshape.on{fill:var(--teal);fill-opacity:.42;stroke:var(--teal);stroke-width:1.6}
.ovz{fill:var(--btn);stroke:var(--ink2);stroke-width:1.2;stroke-opacity:.6;
  vector-effect:non-scaling-stroke;cursor:pointer;transition:fill .12s}
.ovz:hover{fill:var(--sel)}
.ovlabel{font:700 11px "JetBrains Mono",monospace;fill:var(--navy);pointer-events:none;
  paint-order:stroke;stroke:var(--panel);stroke-width:3px;stroke-linejoin:round}
.sitedot{fill:var(--s2);stroke:#fff;stroke-width:1}
.sitelbl{font:600 9.5px "Source Sans 3",sans-serif;fill:var(--ink);pointer-events:none}
.maplegend{display:flex;gap:1.1rem;flex-wrap:wrap;font-size:.84rem;color:var(--ink2);
  margin-top:.5rem;align-items:center}
.maplegend i{display:inline-block;width:11px;height:11px;border-radius:2px;
  background:var(--btn);border:1px solid var(--line);margin-right:.3rem;vertical-align:-1px}
.maplegend i.dot{border-radius:50%;background:var(--s2);border-color:#fff}

.synopsis{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--s2);
  border-radius:8px;padding:.8rem .95rem;margin-bottom:1.1rem;line-height:1.5}
.lead{max-width:66ch}

/* --- Surf Zone Forecast ----------------------------------------------------
   Same 2px --s2 frame as the products panel, because this is NWS content too.
   The risk chip carries colour AND an ordered glyph AND the word: the glyphs
   fill up as the risk rises, so it survives greyscale, CVD and forced-colors,
   and it is a different glyph set from our own suitability chips on purpose -
   this is the NWS's category, not a CariCOOS rating. */
.srf{border:2px solid var(--s2);border-radius:8px;background:var(--panel);
  padding:.85rem 1rem;margin:0 0 1.2rem}
.srf h3{margin:0 0 .35rem;font:700 .95rem "Archivo",sans-serif;letter-spacing:.04em;
  text-transform:uppercase;color:var(--s2)}
.srf .lead2{font-size:.9rem;line-height:1.5;max-width:68ch;margin:.2rem 0 .8rem}
.srf .hi{background:var(--flag);color:#fff;border-radius:6px;padding:.45rem .7rem;
  font-weight:600;margin:0 0 .8rem}
table.beach{width:100%;border-collapse:collapse;font-size:.88rem}
table.beach th{text-align:left;font:700 .68rem "Archivo",sans-serif;text-transform:uppercase;
  letter-spacing:.05em;color:var(--ink2);padding:.3rem .45rem;border-bottom:1px solid var(--line)}
table.beach td{padding:.34rem .45rem;border-bottom:1px solid var(--grid);vertical-align:top}
table.beach td.z{font:700 .74rem "JetBrains Mono",monospace;color:var(--teal);white-space:nowrap}
table.beach td.b{color:var(--ink2);font-size:.84rem}
table.beach td.s{font-variant-numeric:tabular-nums;white-space:nowrap}
.rc{display:inline-flex;align-items:center;gap:.35em;white-space:nowrap;
  font:600 .82rem "Source Sans 3",sans-serif;padding:.14rem .55rem;border-radius:999px}
.rc .g{font-size:.86em;line-height:1;letter-spacing:.06em}
.rc.low{background:var(--ok);color:#fff}
.rc.moderate{background:var(--warn);color:var(--warn-ink)}
.rc.high{background:var(--flag);color:#fff}
.rc.none{background:var(--btn);color:var(--ink2);border:1px dashed var(--line)}
.rcdef{margin-top:.75rem;padding-top:.6rem;border-top:1px dashed var(--line)}
.rcdef .colh{color:var(--s2)}
.rcdef ul{margin:.3rem 0 0;padding-left:1.1rem;font-size:.85rem;line-height:1.5}
@media (max-width:720px){
  table.beach td.b,table.beach th.b{display:none}
}
@media (max-width:820px){
  .verb{border-right:0;border-bottom:1px solid var(--line)}
  .zone .zh{flex-wrap:wrap}
  .locator{width:104px}.locator svg{width:104px}
}
"""


_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def compass(deg):
    """Grados -> rumbo de 16 puntos. Un marino lee 'ENE', no '67 grados'."""
    if deg is None:
        return ""
    return _COMPASS[int((float(deg) % 360) / 22.5 + 0.5) % 16]


def _view(geo):
    vb = geo.get("viewbox") or [0, 0, geo["width"], geo["height"]]
    return " ".join(str(v) for v in vb)


def _proj(lat, lon, geo):
    """Same projection fetch_zonegeo.py used, so sites land on the zone shapes."""
    import math
    lon0, lat0, lon1, lat1 = geo["bbox"]
    kx = math.cos(math.radians((lat0 + lat1) / 2.0))
    sx = geo["width"] / ((lon1 - lon0) * kx)
    return ((lon - lon0) * sx, (lat1 - lat) * sx)


def sprite(geo):
    """Every zone outline defined ONCE, for <use> to reference.

    Inlining all ten paths into each of the eleven maps on this page produced a
    395 KB document - the same 30 KB of geometry eleven times over. Defined once
    and referenced, the whole page costs that 30 KB a single time.
    """
    if not geo:
        return ""
    defs = "".join(f'<path id="z{z}" d="{d}"/>' for z, d in geo["paths"].items())
    return f'<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>{defs}</defs></svg>'


def locator(geo, zone):
    """Small map: every zone faint, this one picked out."""
    if not geo or zone not in geo.get("paths", {}):
        return ""
    others = "".join(f'<use class="zoneshape" href="#z{z}"/>'
                     for z in geo["paths"] if z != zone)
    return (f'<div class="locator"><svg viewBox="{_view(geo)}" '
            f'role="img" aria-label="Location of {zone}">{others}'
            f'<use class="zoneshape on" href="#z{zone}"/></svg></div>')


def overview(geo, sites):
    """The map that answers "where am I looking?" before any text."""
    if not geo:
        return ""
    shapes, labels = [], []
    for z in geo["paths"]:
        shapes.append(f'<a href="#{z}"><use class="ovz" href="#z{z}"><title>{z} '
                      f'{html.escape(geo["names"].get(z, ""))}</title></use></a>')
    for z, xy in (geo.get("label_xy") or {}).items():
        labels.append(f'<text class="ovlabel" x="{xy[0]}" y="{xy[1]}" '
                      f'text-anchor="middle">{z}</text>')
    dots = []
    for s in sites:
        x, y = _proj(s["lat"], s["lon"], geo)
        dots.append(f'<circle class="sitedot" cx="{x:.1f}" cy="{y:.1f}" r="4">'
                    f'<title>{html.escape(s["name_en"])} &middot; {s["zone"]}</title></circle>')
    return f"""
<div class="overview">
  <div class="colh">{M.bi("NWS marine zones and the locations on this board",
                          "Zonas marinas del NWS y los lugares de este tablero")}</div>
  <svg viewBox="{_view(geo)}" role="img"
       aria-label="Marine zones of Puerto Rico and the U.S. Virgin Islands">
    {''.join(shapes)}{''.join(dots)}{''.join(labels)}
  </svg>
  <div class="maplegend">
    <span><i></i>{M.bi("Marine zone &mdash; click to jump to its forecast",
                       "Zona marina &mdash; haga clic para ir a su pronóstico")}</span>
    <span><i class="dot"></i>{M.bi("Board location &mdash; hover for its name",
                                    "Lugar del tablero &mdash; pase el cursor para su nombre")}</span>
  </div>
</div>"""


# The glyphs fill up as the risk rises, so the scale still reads with no colour
# at all. Deliberately NOT the chips our own suitability uses: this is the NWS's
# category, and the two must never look like the same judgement.
RC_GLYPH = {"low": "\u25cb", "moderate": "\u25d0", "high": "\u25cf"}
RC_ES = {"low": "Bajo", "moderate": "Moderado", "high": "Alto"}


def rc_chip(risk):
    """Colour + ordered glyph + the word. Never colour alone."""
    if not risk:
        return ('<span class="rc none"><span class="g">\u2013</span>'
                + M.bi("not forecast", "sin pronóstico") + "</span>")
    return (f'<span class="rc {risk}"><span class="g">{RC_GLYPH[risk]}</span>'
            + M.bi(risk.title(), RC_ES[risk]) + "</span>")


def surf_cell(period):
    """Surf height in the reader's units, from the NWS's own feet."""
    ft = (period or {}).get("surf_ft")
    if not ft:
        return "<td class=\"s\">&ndash;</td>"
    mid = (ft[0] + ft[1]) / 2.0 * 0.3048
    return f'<td class="s"><span data-k="m" data-v="{mid:.3f}"></span></td>'


def surf_section(srf):
    """The Surf Zone Forecast panel: rip current risk and surf by beach zone.

    Why this page carries it at all: a MODERATE rip current risk is never issued
    as an alert, so it cannot appear in the products panel above - yet it is the
    hazard most likely to matter to someone reading this page. Labelled as a
    forecast throughout; it is not an advisory and must never be called one.
    """
    zones = srf.get("zones") or []
    if not zones:
        return ""
    rows = []
    for z in zones:
        ps = z.get("periods") or []
        d0 = ps[0] if ps else None
        d1 = ps[1] if len(ps) > 1 else None
        rows.append(
            "<tr>"
            f'<td class="z">{html.escape(z.get("zone", ""))}</td>'
            f'<td>{html.escape(z.get("name") or "")}</td>'
            f'<td class="b">{html.escape(z.get("beaches") or "")}</td>'
            f'<td>{rc_chip((d0 or {}).get("risk"))}</td>'
            f"{surf_cell(d0)}"
            f'<td>{rc_chip((d1 or {}).get("risk"))}</td>'
            "</tr>")

    high = [z for z in zones
            if ((z.get("periods") or [{}])[0] or {}).get("risk") == "high"]
    hi = ""
    if high:
        names = ", ".join(html.escape(z.get("name") or z.get("zone", "")) for z in high)
        hi = ('<p class="hi">' + M.bi(
            f"The National Weather Service forecasts a HIGH rip current risk today "
            f"for {names}. In its own words: life-threatening rip currents are "
            f"likely in the surf zone.",
            f"El Servicio Nacional de Meteorología pronostica riesgo ALTO de "
            f"corrientes de resaca hoy para {names}. En sus propias palabras: "
            f"corrientes de resaca potencialmente mortales son probables en la "
            f"zona de rompiente.") + "</p>")

    # Low -> Moderate -> High, in the product's own words, so the page never
    # has to paraphrase what a category means.
    meaning = srf.get("risk_meaning") or {}
    defs = "".join(f"<li>{html.escape(meaning[k])}</li>"
                   for k in ("low", "moderate", "high") if meaning.get(k))
    d0h, d1h = M.bi("Today", "Hoy"), M.bi("Tomorrow", "Mañana")
    issued = (srf.get("issued_utc") or "?")[:16]
    return f"""
<div class="srf">
<h3>{M.bi("NWS Surf Zone Forecast", "Pronóstico de Zona de Rompiente NWS")}</h3>
{hi}
<p class="lead2">{M.bi(
    "Rip current risk and surf height for the beach zones, from the National "
    "Weather Service Surf Zone Forecast. <b>This is a forecast, not an advisory.</b> "
    "A Low or Moderate rip current risk is never issued as a warning product, so "
    "it will not appear in the panel above &mdash; only a High risk becomes a Rip "
    "Current Statement. The categories and their wording are the NWS's own.",
    "Riesgo de corrientes de resaca y altura de rompiente por zona de playa, del "
    "Pronóstico de Zona de Rompiente del Servicio Nacional de Meteorología. "
    "<b>Esto es un pronóstico, no un aviso.</b> Un riesgo Bajo o Moderado nunca se "
    "emite como producto de advertencia, así que no aparecerá en el panel de "
    "arriba: solo un riesgo Alto se convierte en un Rip Current Statement. Las "
    "categorías y su redacción son del NWS.")}</p>
<table class="beach"><thead><tr>
  <th>{M.bi("Zone", "Zona")}</th><th>{M.bi("Area", "Área")}</th>
  <th class="b">{M.bi("Beaches", "Playas")}</th>
  <th>{M.bi("Rip current risk", "Riesgo de resaca")} &mdash; {d0h}</th>
  <th>{M.bi("Surf", "Rompiente")}</th>
  <th>{d1h}</th>
</tr></thead><tbody>{"".join(rows)}</tbody></table>
<div class="rcdef"><div class="colh">{M.bi(
    "Risk categories &mdash; NWS, as issued",
    "Categorías de riesgo &mdash; NWS, tal como se emitieron")}</div>
<ul>{defs}</ul></div>
<div class="attrib">{M.bi(
    f"Surf Zone Forecast issued {issued}Z by the National Weather Service "
    f"{html.escape(srf.get('office') or 'SJU')}, reproduced verbatim. ",
    f"Pronóstico de Zona de Rompiente emitido {issued}Z por el Servicio Nacional "
    f"de Meteorología {html.escape(srf.get('office') or 'SJU')}, reproducido "
    f"literalmente. ")}
<a href="{html.escape(srf.get('product_url') or '')}" target="_blank" rel="noopener">{
    M.bi("full product", "producto completo")} &#8599;</a></div>
</div>
"""


def main():
    cwf = M.read_json("nws", "cwf.json") or {}
    alerts = (M.read_json("nws", "alerts.json") or {}).get("alerts", [])
    srf = M.read_json("nws", "srf.json") or {}
    geo = M.read_json("nws", "zones_geo.json")
    sites = M.load_sites()
    by_zone = {}
    for s in sites:
        by_zone.setdefault(s["zone"], []).append(s)

    zones = cwf.get("zones", {})
    order = sorted(zones, key=lambda z: (z not in by_zone, z))

    blocks = []
    for z in order:
        zd = zones[z]
        mine = by_zone.get(z, [])
        periods = zd.get("periods", [])

        def per_html(ps):
            return "".join(
                f'<div class="per"><b>{html.escape(p["label"])}</b>'
                f'<div class="txt">{html.escape(p.get("text", ""))}</div></div>' for p in ps)

        head, rest = periods[:OPEN_PERIODS], periods[OPEN_PERIODS:]
        more = (f'<details class="more"><summary>'
                f'{M.bi(f"{len(rest)} more periods", f"{len(rest)} periodos más")}'
                f'</summary>{per_html(rest)}</details>' if rest else "")
        def row(p):
            h = ("<tr>"
                 f'<td>{html.escape(p["label"].title())}</td>'
                 f'<td><span data-k="kt" data-v="{p.get("wind_kt", "")}"></span></td>'
                 f'<td><span data-k="kt" data-v="{p.get("gust_kt", "")}"></span></td>'
                 f'<td><span data-k="m" data-v="{p.get("hs_m", "")}"></span></td>'
                 f'<td><span data-k="s" data-v="{p.get("tp_s", "")}"></span></td>'
                 "</tr>")
            # El NWS lista a veces DOS trenes de ola, y la fila de arriba solo
            # lleva el mayor. Esconder el otro borra la diferencia que importa:
            # 0.9 m del este a 5 s y 0.9 m del norte a 11 s miden igual y no se
            # parecen en nada - la de periodo largo es la que mueve un barco
            # atracado y rompe en la barra.
            #
            # Se muestra tambien con UN solo tren, aunque parezca redundante:
            # la fila de arriba no tiene columna de direccion, asi que esta es
            # la unica linea donde aparece de donde viene la mar. Con la
            # condicion en >1 se perdia en 10 de los 100 periodos.
            trains = p.get("wave_trains") or []
            if trains:
                cel = " ".join(
                    f'<span class="tr">{compass(t.get("dir_deg"))} '
                    f'<span data-k="m" data-v="{t.get("hs_m", "")}"></span>'
                    f'<span class="at">@</span>'
                    f'<span data-k="s" data-v="{t.get("tp_s", "")}"></span></span>'
                    for t in trains)
                h += (f'<tr class="trains"><td colspan="5">'
                      f'<span class="lbl">{M.bi("Wave detail", "Detalle de olas")}</span>'
                      f'{cel}</td></tr>')
            return h

        rows = "".join(row(p) for p in head)
        # El NWS deja de publicar "Wave Detail" en los dias lejanos - 40 de 100
        # periodos ahora mismo. Sin decirlo, una fila sin esa linea se lee como
        # un fallo nuestro en vez de como el limite del producto que es.
        sin_detalle = [p for p in head if not (p.get("wave_trains") or [])]
        nota = (f'<div class="nodet">{M.bi(
            "The NWS stops publishing Wave Detail on the later days, so those "
            "periods carry sea height but no direction or period.",
            "El NWS deja de publicar el Wave Detail en los días lejanos, así que "
            "esos periodos traen altura de mar pero no dirección ni periodo.")}</div>'
            if sin_detalle else "")
        sitelist = (", ".join(M.bi(s["name_en"], s["name_es"]) for s in mine)
                    if mine else M.bi("No board locations in this zone",
                                      "Ningún lugar del tablero en esta zona"))
        blocks.append(f"""
<div class="zone" id="{z}">
  <div class="zh">
    {locator(geo, z)}
    <div class="txt"><span class="zid">{z}</span>
      <h3>{html.escape(zd.get("name", ""))}</h3>
      <div class="sites">{sitelist}</div></div>
  </div>
  <div class="cols">
    <div class="verb"><div class="colh">{M.bi(
        "National Weather Service &mdash; as issued",
        "Servicio Nacional de Meteorología &mdash; tal como se emitió")}</div>
      {per_html(head)}{more}</div>
    <div class="ours"><div class="colh">{M.bi(
        "Summary of the Numbers", "Resumen de los números")}</div>
      <table class="sum"><thead><tr>
        <th>{M.bi("Period", "Periodo")}</th><th>{M.bi("Wind", "Viento")}</th>
        <th>{M.bi("Gust", "Ráfaga")}</th>
        <th>{M.bi("Seas", "Oleaje")}</th><th>{M.bi("Per.", "Per.")}</th>
      </tr></thead><tbody>{rows}</tbody></table>{nota}</div>
  </div>
</div>""")

    if alerts:
        prods = "".join(
            f'<div class="prod"><b>{html.escape(a.get("event") or "")}</b> &mdash; '
            f'{html.escape(a.get("sender") or "NWS")}'
            f'<div class="meta">{", ".join(a.get("zones") or [])}'
            f'{" &middot; until " + html.escape(a["expires"]) if a.get("expires") else ""}</div>'
            f'<pre>{html.escape(a.get("headline") or "")}</pre></div>' for a in alerts)
    else:
        prods = ('<div class="srcline">' + M.bi(
            "No NWS marine warnings, watches or advisories are in effect for these zones.",
            "No hay advertencias, vigilancias ni avisos marinos del NWS vigentes para "
            "estas zonas.") + "</div>")

    syn = cwf.get("synopsis")
    synblock = (f'<div class="synopsis"><div class="colh" style="color:var(--s2)">'
                f'{M.bi("Synopsis &mdash; NWS, as issued", "Sinopsis &mdash; NWS, tal como se emitió")}'
                f"</div>{html.escape(syn)}</div>" if syn else "")

    lead = M.bi(
        "The official National Weather Service forecast, reproduced exactly as issued. "
        "<b>It is not translated</b> &mdash; an official marine forecast should be read in the "
        "words the forecaster wrote. The panel on the right is CariCOOS's own reading of the "
        "numbers, and is translated.",
        "El pronóstico oficial del Servicio Nacional de Meteorología, reproducido exactamente "
        "como se emitió. <b>No está traducido</b>: un pronóstico marino oficial debe leerse con "
        "las palabras que escribió el meteorólogo. El panel de la derecha es la lectura propia "
        "de CariCOOS de los números, y sí está traducido.")

    body = f"""
<div id="nws" class="nws"><h3>{M.bi("NWS products in effect", "Productos del NWS vigentes")}</h3>
{prods}
<div class="attrib">{M.bi(
    'Issued by the National Weather Service, reproduced verbatim. '
    '<a href="https://www.weather.gov/sju/" target="_blank" rel="noopener">weather.gov/sju &#8599;</a>',
    'Emitidos por el Servicio Nacional de Meteorología, reproducidos literalmente. '
    '<a href="https://www.weather.gov/sju/" target="_blank" rel="noopener">weather.gov/sju &#8599;</a>')}
</div></div>

{surf_section(srf)}

{sprite(geo)}
{overview(geo, sites)}
<p class="lead">{lead}</p>
{synblock}
{"".join(blocks)}
"""
    gen = M.bi(
        f"NWS {cwf.get('office', 'SJU')} Coastal Waters Forecast issued "
        f"{(cwf.get('issued_utc') or '?')[:16]}Z &middot; "
        f'<a href="{cwf.get("product_url", "")}">full product &#8599;</a>. Refreshes every 30 minutes.',
        f"Pronóstico de Aguas Costeras del NWS {cwf.get('office', 'SJU')} emitido "
        f"{(cwf.get('issued_utc') or '?')[:16]}Z &middot; "
        f'<a href="{cwf.get("product_url", "")}">producto completo &#8599;</a>. '
        f"Se actualiza cada 30 minutos.")
    JS = """
function onUnits(){
  document.querySelectorAll('[data-v]').forEach(el=>{
    const k=el.dataset.k, v=el.dataset.v;
    el.textContent = v===''? '\\u2013' : fv(k, parseFloat(v), k==='s'?0:1);
  });
}
function onLang(){}
function onTZ(){}
onUnits();
"""
    out_html = M.page_shell("marine_zones.html", "NWS forecast", "Pronóstico NWS",
                            "The official forecast, as issued",
                            "El pronóstico oficial, tal como se emitió",
                            body, extra_css=CSS, scripts=JS, generated=gen)
    out = os.path.join(M.WEBOUT, "marine_zones.html")
    M.atomic_write_text(out_html, out)
    print(f"[make_zones] wrote {out} ({len(out_html):,} bytes, {len(order)} zones, "
          f"{len(alerts)} active products, "
          f"{len(srf.get('zones') or [])} beach zones, map={'yes' if geo else 'no'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
