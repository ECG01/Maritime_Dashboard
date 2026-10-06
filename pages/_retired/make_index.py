#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/index.html - the landing page.

Generated rather than hand-written so it can lead with something true right now:
how many locations are currently Unfavorable for each vessel class, and any
active NWS marine product. A landing page that only lists links makes a mariner
click before learning anything.
"""
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402
from engine import cwf_parse as C       # noqa: E402
from engine import ratings as R         # noqa: E402

CARDS = [
    ("conditions_now.html", ("Conditions now", "Condiciones ahora"),
     ("Every location on one board, rated for each vessel class, with the reason behind "
      "each rating and a drill-down into the buoy or wind station behind the numbers.",
      "Todos los lugares en un tablero, evaluados para cada clase de embarcación, con la "
      "razón de cada evaluación y acceso a la boya o estación de viento tras los números."),
     ("Deciding whether to go out today", "Decidir si salir hoy")),
    ("planner.html", ("Planner", "Planificador"),
     ("A five-day grid of every location against every forecast period, plus the best "
      "departure windows for the class you pick.",
      "Una cuadrícula de cinco días de cada lugar contra cada periodo de pronóstico, más "
      "las mejores ventanas de salida para la clase que elija."),
     ("Scheduling a transit, a haul or a charter", "Programar un tránsito, una faena o un chárter")),
    ("marine_zones.html", ("NWS marine zones", "Zonas marinas NWS"),
     ("The official National Weather Service Coastal Waters Forecast, reproduced exactly as "
      "issued, alongside the numbers we read from it.",
      "El Pronóstico oficial de Aguas Costeras del Servicio Nacional de Meteorología, "
      "reproducido tal como se emitió, junto a los números que leemos de él."),
     ("Reading the forecaster's own words", "Leer las palabras del meteorólogo")),
    ("tools.html", ("Tools", "Herramientas"),
     ("The four CARICOOS tools this board draws on &mdash; buoys, wind stations and both "
      "model viewers &mdash; embedded or opened full screen.",
      "Las cuatro herramientas de CARICOOS en las que se apoya este tablero: boyas, "
      "estaciones de viento y ambos visores de modelos, integradas o a pantalla completa."),
     ("Looking at the data yourself", "Ver los datos usted mismo")),
    ("methods.html", ("Methods", "Métodos"),
     ("Every threshold behind every rating, with its source, rendered straight from the "
      "configuration the ratings actually use.",
      "Cada umbral tras cada evaluación, con su fuente, generado directamente desde la "
      "configuración que usan las evaluaciones."),
     ("Deciding whether to trust this", "Decidir si confiar en esto")),
    ("status.html", ("Data status", "Estado de datos"),
     ("What fetched when, which stations are down, and whether the configuration is "
      "consistent.",
      "Qué se descargó y cuándo, qué estaciones están fuera de servicio y si la "
      "configuración es consistente."),
     ("Something looks wrong", "Algo se ve mal")),
]

CSS = r"""
.hero{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:1rem 1.1rem;margin-bottom:1.2rem}
.hero .line{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;margin:.35rem 0}
.hero .cls{font-weight:600;min-width:9.5rem}
.hero .cnt{color:var(--ink2);font-size:.92rem}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:.9rem}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:1rem;
  display:flex;flex-direction:column}
.card h3{margin:0 0 .2rem;font:700 1.05rem "Archivo",sans-serif}
.card .use{font:600 .74rem "Archivo",sans-serif;letter-spacing:.05em;text-transform:uppercase;
  color:var(--teal);margin-bottom:.4rem}
.card p{margin:0 0 .8rem;font-size:.92rem;flex:1}
.card a.primary{align-self:flex-start;background:var(--btn-on);color:var(--btn-on-ink);
  text-decoration:none;font:600 .88rem "Source Sans 3",sans-serif;padding:.35rem .9rem;
  border-radius:5px}
.lead{max-width:64ch}
"""

JS = r"""
const D=__DATA__;
function nm(o){return L==='es'?(o.es||o.en):o.en;}
function render(){
  let h='';
  D.classes.forEach(c=>{
    const t=D.tally[c.key]||{};
    const worst = t.unfavorable>0?'unfavorable':(t.marginal>0?'marginal':'favorable');
    const lab = nm(D.status_bi[worst]);
    h+='<div class="line"><span class="cls">'+nm(c)+'</span>'+
       '<span class="chip '+worst+'"><span class="g" aria-hidden="true">'+
       (D.glyph[worst]||'')+'</span>'+lab+'</span>'+
       '<span class="cnt">'+
       (T('tally').replace('{u}',t.unfavorable||0).replace('{m}',t.marginal||0)
                  .replace('{n}',t.total||0))+'</span></div>';
  });
  document.getElementById('hero').innerHTML=h;
}
function T(k){const d=I18N[k];return d?(d[L]||d.en):k;}
function onLang(){render();}
function onUnits(){}
function onTZ(){}
render();
"""


def main():
    cwf = M.read_json("nws", "cwf.json") or {}
    alerts = (M.read_json("nws", "alerts.json") or {}).get("alerts", [])
    ths = R.load_thresholds()
    sites = M.load_sites()

    tally = {c: {"favorable": 0, "marginal": 0, "unfavorable": 0, "nodata": 0, "total": 0}
             for c in M.CLASSES}
    for s in sites:
        fr = C.frames(cwf, s["zone"])
        if not fr:
            continue
        p = fr[0]
        raw = {k: p.get(k) for k in ("hs_m", "tp_s", "dp_deg", "wind_kt", "gust_kt", "wdir_deg")}
        sample = R.prepare_sample(raw, kind=s["kind"])
        for c in s["classes"]:
            r = R.rate(sample, c, s["kind"], ths)
            if r.status in tally[c]:
                tally[c][r.status] += 1
                tally[c]["total"] += 1

    if alerts:
        prods = "".join(
            f'<div class="prod"><b>{html.escape(a.get("event") or "")}</b> &mdash; '
            f'{html.escape(a.get("sender") or "NWS")}'
            f'<div class="meta">{", ".join(a.get("zones") or [])}</div></div>'
            for a in alerts)
    else:
        prods = ('<div class="srcline">' + M.bi(
            "No NWS marine warnings, watches or advisories are in effect.",
            "No hay advertencias, vigilancias ni avisos marinos del NWS vigentes.") + "</div>")

    cards = "".join(f"""
<div class="card">
  <div class="use">{M.bi(uen, ues)}</div>
  <h3>{M.bi(ten, tes)}</h3>
  <p>{M.bi(den, des)}</p>
  <a class="primary" href="{href}">{M.bi("Open", "Abrir")}</a>
</div>""" for href, (ten, tes), (den, des), (uen, ues) in CARDS)

    lead = M.bi(
        "This board answers one question: <b>can I go, and if not now, when?</b> It compares "
        "conditions at named places around Puerto Rico and the U.S. Virgin Islands against "
        "published limits for four kinds of vessel, and tells you which limit is the binding "
        "one. It does not replace the National Weather Service &mdash; official products appear "
        "here exactly as issued, in their own panel.",
        "Este tablero responde una pregunta: <b>¿puedo salir y, si no ahora, cuándo?</b> Compara "
        "las condiciones en lugares concretos de Puerto Rico y las Islas Vírgenes con límites "
        "publicados para cuatro tipos de embarcación, y le dice cuál es el límite determinante. "
        "No sustituye al Servicio Nacional de Meteorología: los productos oficiales aparecen "
        "aquí tal como se emiten, en su propio panel.")

    body = f"""
<p class="lead">{lead}</p>
<div id="nws" class="nws"><h3>{M.bi("NWS products in effect", "Productos del NWS vigentes")}</h3>
{prods}
<div class="attrib">{M.bi(
    'Issued by the National Weather Service, reproduced verbatim. '
    '<a href="https://www.weather.gov/sju/" target="_blank" rel="noopener">weather.gov/sju &#8599;</a>',
    'Emitidos por el Servicio Nacional de Meteorología, reproducidos literalmente. '
    '<a href="https://www.weather.gov/sju/" target="_blank" rel="noopener">weather.gov/sju &#8599;</a>')}
</div></div>

<h2>{M.bi("Right now", "Ahora mismo")}</h2>
<div class="hero" id="hero"></div>

<h2>{M.bi("Where to go next", "A dónde ir")}</h2>
<div class="cards">{cards}</div>
"""
    d = {"tally": tally,
         "classes": [{"key": c, "en": M.CLASS_BI[c][0], "es": M.CLASS_BI[c][1]}
                     for c in M.CLASSES],
         "status_bi": {k: {"en": v[0], "es": v[1]} for k, v in M.STATUS_BI.items()},
         "glyph": M.STATUS_GLYPH}
    gen = M.bi(
        f"Generated {M.utcnow().isoformat()[:16]}Z from NWS {cwf.get('office', 'SJU')} CWF "
        f"issued {(cwf.get('issued_utc') or '?')[:16]}Z. Refreshes every 10 minutes.",
        f"Generado {M.utcnow().isoformat()[:16]}Z del CWF del NWS {cwf.get('office', 'SJU')} "
        f"emitido {(cwf.get('issued_utc') or '?')[:16]}Z. Se actualiza cada 10 minutos.")
    out_html = M.page_shell("index.html", "CariCOOS Maritime", "CariCOOS Marítimo",
                            "Puerto Rico &amp; the U.S. Virgin Islands",
                            "Puerto Rico y las Islas Vírgenes",
                            body, extra_css=CSS,
                            scripts=JS.replace("__DATA__", json.dumps(d, ensure_ascii=False)),
                            i18n='const I18N={tally:{en:"{u} unfavorable, {m} marginal of '
                                 '{n} locations",es:"{u} desfavorables, {m} marginales de '
                                 '{n} lugares"}};',
                            generated=gen)
    out = os.path.join(M.WEBOUT, "index.html")
    M.atomic_write_text(out_html, out)
    print(f"[make_index] wrote {out} ({len(out_html):,} bytes)")
    for c in M.CLASSES:
        t = tally[c]
        print(f"    {c:6s} {t['favorable']} fav / {t['marginal']} marg / "
              f"{t['unfavorable']} unfav  (of {t['total']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
