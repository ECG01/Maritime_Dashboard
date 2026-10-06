#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/marine_zones.html - the official NWS forecast, verbatim.

Editorial rule, and the reason this page is separate from every other one:
the National Weather Service text is reproduced AS ISSUED, in English, and is
never machine-translated. Translating an official marine forecast would create a
second, unofficial version of a safety product under CariCOOS's name.

Beside it sits our own bilingual summary of the numbers we parsed out. That part
is clearly ours, and labelled as such.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402
from engine import cwf_parse as C       # noqa: E402

CSS = r"""
.zone{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  margin-bottom:1.2rem;overflow:hidden}
.zone .zh{padding:.7rem 1rem;background:var(--controls);border-bottom:1px solid var(--line)}
.zone .zh h3{margin:0;font:700 1rem "Archivo",sans-serif}
.zone .zh .zid{font:600 .8rem "JetBrains Mono",monospace;color:var(--teal)}
.zone .zh .sites{font-size:.85rem;color:var(--ink2);margin-top:.2rem}
.cols{display:flex;gap:0;flex-wrap:wrap}
.verb{flex:1 1 380px;min-width:300px;padding:.8rem 1rem;border-right:1px solid var(--line)}
.ours{flex:1 1 300px;min-width:260px;padding:.8rem 1rem;background:var(--surface)}
.colh{font:700 .72rem "Archivo",sans-serif;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink2);margin-bottom:.5rem}
.verb .colh{color:var(--s2)}
.per{margin-bottom:.6rem}
.per b{font:700 .82rem "Archivo",sans-serif;letter-spacing:.04em}
.per .txt{font-size:.9rem;line-height:1.45}
table.sum{width:100%;border-collapse:collapse;font-size:.88rem}
table.sum th{text-align:left;font:600 .72rem "Archivo",sans-serif;text-transform:uppercase;
  letter-spacing:.04em;color:var(--ink2);padding:.25rem .3rem;border-bottom:1px solid var(--line)}
table.sum td{padding:.25rem .3rem;border-bottom:1px solid var(--grid);
  font-variant-numeric:tabular-nums;white-space:nowrap}
.synopsis{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--s2);
  border-radius:6px;padding:.8rem 1rem;margin-bottom:1.2rem;line-height:1.5}
.lead{max-width:64ch}
@media (max-width:820px){.verb{border-right:0;border-bottom:1px solid var(--line)}}
"""

JS = r"""
const D=__DATA__;
function onUnits(){
  document.querySelectorAll('[data-v]').forEach(el=>{
    const k=el.dataset.k, v=el.dataset.v;
    el.textContent = v===''? '–' : fv(k, parseFloat(v), k==='s'?0:1);
  });
}
function onLang(){}
function onTZ(){}
onUnits();
"""


def main():
    cwf = M.read_json("nws", "cwf.json") or {}
    alerts = (M.read_json("nws", "alerts.json") or {}).get("alerts", [])
    sites = M.load_sites()
    by_zone = {}
    for s in sites:
        by_zone.setdefault(s["zone"], []).append(s)

    zones = cwf.get("zones", {})
    # our own zones first, then the rest of the office's zones for context
    order = sorted(zones, key=lambda z: (z not in by_zone, z))

    blocks = []
    for z in order:
        zd = zones[z]
        mine = by_zone.get(z, [])
        periods = zd.get("periods", [])[:6]
        verb = "".join(
            f'<div class="per"><b>{html.escape(p["label"])}</b>'
            f'<div class="txt">{html.escape(p.get("text", ""))}</div></div>'
            for p in periods)
        rows = "".join(
            "<tr>"
            f'<td>{html.escape(p["label"].title())}</td>'
            f'<td><span data-k="kt" data-v="{p.get("wind_kt", "")}"></span></td>'
            f'<td><span data-k="m" data-v="{p.get("hs_m", "")}"></span></td>'
            f'<td><span data-k="s" data-v="{p.get("tp_s", "")}"></span></td>'
            "</tr>" for p in periods)
        sitelist = (", ".join(M.bi(s["name_en"], s["name_es"]) for s in mine)
                    if mine else M.bi("No board locations in this zone",
                                      "Ningún lugar del tablero en esta zona"))
        blocks.append(f"""
<div class="zone">
  <div class="zh"><span class="zid">{z}</span>
    <h3>{html.escape(zd.get("name", ""))}</h3>
    <div class="sites">{sitelist}</div></div>
  <div class="cols">
    <div class="verb"><div class="colh">{M.bi(
        "National Weather Service &mdash; as issued",
        "Servicio Nacional de Meteorología &mdash; tal como se emitió")}</div>{verb}</div>
    <div class="ours"><div class="colh">{M.bi(
        "CariCOOS reading of the numbers", "Lectura CariCOOS de los números")}</div>
      <table class="sum"><thead><tr>
        <th>{M.bi("Period", "Periodo")}</th><th>{M.bi("Wind", "Viento")}</th>
        <th>{M.bi("Seas", "Oleaje")}</th><th>{M.bi("Per.", "Per.")}</th>
      </tr></thead><tbody>{rows}</tbody></table></div>
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

    lead = M.bi(
        "This is the official National Weather Service Coastal Waters Forecast, reproduced "
        "exactly as issued. <b>It is not translated</b> &mdash; an official marine forecast "
        "should be read in the words the forecaster wrote. The panel on the right is CariCOOS's "
        "own reading of the numbers we extract from that text, and is translated.",
        "Este es el Pronóstico oficial de Aguas Costeras del Servicio Nacional de Meteorología, "
        "reproducido exactamente como se emitió. <b>No está traducido</b>: un pronóstico marino "
        "oficial debe leerse con las palabras que escribió el meteorólogo. El panel de la "
        "derecha es la lectura propia de CariCOOS de los números que extraemos de ese texto, "
        "y sí está traducido.")

    syn = cwf.get("synopsis")
    synblock = (f'<div class="synopsis"><div class="colh" style="color:var(--s2)">'
                f'{M.bi("Synopsis &mdash; NWS, as issued", "Sinopsis &mdash; NWS, tal como se emitió")}'
                f"</div>{html.escape(syn)}</div>" if syn else "")

    body = f"""
<div id="nws" class="nws"><h3>{M.bi("NWS products in effect", "Productos del NWS vigentes")}</h3>
{prods}
<div class="attrib">{M.bi(
    'Official marine products are issued by the National Weather Service and reproduced here '
    'verbatim. <a href="https://www.weather.gov/sju/" target="_blank" rel="noopener">'
    'weather.gov/sju &#8599;</a>',
    'Los productos marinos oficiales los emite el Servicio Nacional de Meteorología y aquí se '
    'reproducen literalmente. <a href="https://www.weather.gov/sju/" target="_blank" '
    'rel="noopener">weather.gov/sju &#8599;</a>')}</div></div>

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
    out_html = M.page_shell("marine_zones.html", "NWS marine zones", "Zonas marinas NWS",
                            "The official forecast, as issued",
                            "El pronóstico oficial, tal como se emitió",
                            body, extra_css=CSS,
                            scripts=JS.replace("__DATA__", "{}"), generated=gen)
    out = os.path.join(M.WEBOUT, "marine_zones.html")
    M.atomic_write_text(out_html, out)
    print(f"[make_zones] wrote {out} ({len(out_html):,} bytes, {len(order)} zones, "
          f"{len(alerts)} active products)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
