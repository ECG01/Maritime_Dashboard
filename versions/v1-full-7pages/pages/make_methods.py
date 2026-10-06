#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/methods.html - how every rating is made.

Renders config/thresholds.tsv LIVE, including its `source` column. The published
methodology therefore cannot drift from what engine/ratings.py actually does:
there is one copy of the numbers and this page reads it. A limit still marked
'- VERIFY' stays visibly unverified to every reader until somebody checks it,
which is the point.
"""
import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                       # noqa: E402
from engine import ratings as R          # noqa: E402

VAR_BI = {
    "wind_kt": ("Sustained wind", "Viento sostenido"),
    "gust_kt": ("Wind gusts", "Ráfagas de viento"),
    "hs_m": ("Significant wave height (Hs)", "Altura significativa del oleaje (Hs)"),
    "steepness": ("Wave steepness", "Escarpamiento del oleaje"),
    "lp_swell_m": ("Long-period swell", "Marejada de periodo largo"),
    "hs_beam_m": ("Beam-sea component", "Componente de oleaje de través"),
    "roll_ratio": ("Roll resonance margin", "Margen de resonancia de balance"),
    "wind_vs_curr": ("Wind against current", "Viento contra corriente"),
}
VAR_NOTE = {
    "steepness": (
        "S = Hs / (1.56 &middot; Tp&sup2;). Steepness, not height alone, is what makes a sea "
        "dangerous for a small boat: 1.5 m at 12 s is a comfortable swell, while 1.5 m at "
        "5 s is a wall of breaking chop.",
        "S = Hs / (1.56 &middot; Tp&sup2;). El escarpamiento, y no solo la altura, es lo que "
        "hace peligroso el mar para una embarcación pequeña: 1.5 m a 12 s es una marejada "
        "cómoda, mientras que 1.5 m a 5 s es una pared de rompientes."),
    "hs_beam_m": (
        "Hs &middot; |sin(encounter angle)|, where the encounter angle is 0&deg; in a following "
        "sea, 90&deg; on the beam and 180&deg; head-on. This is the number that decides whether "
        "a ferry crossing is comfortable.",
        "Hs &middot; |sen(ángulo de encuentro)|, donde el ángulo es 0&deg; con mar de popa, "
        "90&deg; de través y 180&deg; de proa. Este es el número que decide si una travesía "
        "en ferry resulta cómoda."),
    "roll_ratio": (
        "|Te/Tr &minus; 1|, comparing the encounter period Te with the vessel's natural roll "
        "period Tr. <b>Zero is the dangerous end</b> &mdash; a match means synchronous rolling, "
        "so this limit is read in the opposite direction to every other row.",
        "|Te/Tr &minus; 1|, comparando el periodo de encuentro Te con el periodo natural de "
        "balance Tr. <b>Cero es el extremo peligroso</b>: la coincidencia produce balance "
        "sincrónico, por lo que este límite se lee al revés que los demás."),
    "lp_swell_m": (
        "Evaluated <b>only</b> when the peak period is 14 s or longer. Below that it is not "
        "assessed at all, which is not the same as passing.",
        "Se evalúa <b>solo</b> cuando el periodo pico es de 14 s o más. Por debajo no se "
        "evalúa en absoluto, lo cual no equivale a aprobar."),
    "wind_vs_curr": (
        "A CariCOOS-defined index, not a standard quantity: the wind speed scaled by how "
        "directly the current opposes it. It exists so &quot;wind against tide&quot; can be "
        "rated on the same scale as wind itself.",
        "Un índice definido por CariCOOS, no una magnitud estándar: la velocidad del viento "
        "escalada por cuán directamente se le opone la corriente. Permite evaluar el "
        "&quot;viento contra corriente&quot; en la misma escala que el viento."),
}
KIND_BI = {"*": ("all locations", "todos los lugares"), "port": ("ports", "puertos"),
           "inlet": ("inlets", "entradas"), "anchorage": ("anchorages", "fondeaderos"),
           "passage": ("passages", "canales"), "fishing": ("fishing grounds", "pesqueros"),
           "route": ("ferry routes", "rutas de ferry")}
VAR_UNIT = {"wind_kt": "kt", "gust_kt": "kt", "hs_m": "m", "steepness": "-",
            "lp_swell_m": "m", "hs_beam_m": "m", "roll_ratio": "-", "wind_vs_curr": "kt"}

CSS = r"""
table.th{width:100%;border-collapse:collapse;background:var(--panel);
  border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-bottom:1.2rem}
table.th th{background:var(--controls);font:600 .76rem "Archivo",sans-serif;
  letter-spacing:.04em;text-transform:uppercase;color:var(--ink2);padding:.5rem .6rem;
  text-align:left;border-bottom:1px solid var(--line)}
table.th td{padding:.5rem .6rem;border-bottom:1px solid var(--grid);vertical-align:top;
  font-size:.92rem}
table.th td.lim{font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:600}
.verify{display:inline-block;background:var(--flag);color:#fff;font:700 .68rem "Archivo",sans-serif;
  letter-spacing:.06em;padding:.05rem .4rem;border-radius:3px;margin-left:.3rem}
.src{font-size:.85rem;color:var(--ink2)}
.vnote{font-size:.88rem;color:var(--ink2);margin:.2rem 0 0}
.keybox{display:flex;gap:.8rem;flex-wrap:wrap;margin:.6rem 0 1.2rem}
.keybox .k{display:flex;align-items:center;gap:.4rem;font-size:.9rem}
h3{font:700 1rem "Archivo",sans-serif;margin:1.4rem 0 .4rem}
.lead{max-width:62ch}
"""

JS = r"""
const LIMITS = __LIMITS__;
function onUnits(){
  document.querySelectorAll('[data-lim]').forEach(el=>{
    const k=el.dataset.kind, v=parseFloat(el.dataset.lim);
    el.textContent = (k==='-') ? v.toFixed(3) : fv(k,v,null);
  });
}
function onLang(){}
onUnits();
"""


def main():
    problems = M.validate()
    if problems:
        for p in problems:
            print(f"[make_methods] CONFIG ERROR: {p}")
        return 2
    ths = R.load_thresholds()

    key = "".join(
        f'<span class="k">{M.status_chip(s)}</span>'
        for s in ("favorable", "marginal", "unfavorable", "nodata", "notrated"))

    rows = []
    for cls in M.CLASSES:
        group = [t for t in ths if t.cls == cls]
        if not group:
            continue
        en, es = M.CLASS_BI[cls]
        rows.append(f'<tr><td colspan="5" style="background:var(--controls);'
                    f'font-weight:700">{M.bi(en, es)}</td></tr>')
        for t in sorted(group, key=lambda x: x.var):
            ven, ves = VAR_BI.get(t.var, (t.var, t.var))
            kinds = ", ".join(M.bi(*KIND_BI.get(k, (k, k))) for k in t.applies_to)
            unit = VAR_UNIT.get(t.var, "-")
            note = VAR_NOTE.get(t.var)
            verify = ('<span class="verify">VERIFY</span>'
                      if "VERIFY" in t.source.upper() else "")
            direction = M.bi("lower is worse", "menor es peor") if t.dir == "low" else ""
            rows.append(
                "<tr>"
                f'<td><b>{M.bi(ven, ves)}</b>'
                + (f'<div class="vnote">{M.bi(*note)}</div>' if note else "")
                + (f'<div class="vnote"><i>{direction}</i></div>' if direction else "")
                + "</td>"
                f'<td class="lim"><span data-lim="{t.marginal}" data-kind="{unit}">'
                f'{t.marginal}</span></td>'
                f'<td class="lim"><span data-lim="{t.unfavorable}" data-kind="{unit}">'
                f'{t.unfavorable}</span></td>'
                f"<td>{kinds}</td>"
                f'<td class="src">{html.escape(t.source)}{verify}</td>'
                "</tr>")

    lead = M.bi(
        "<b>Operational Suitability</b> is CariCOOS's own assessment. It compares observed and "
        "forecast conditions against the published limits below, separately for each vessel "
        "class, and reports the worst result with the variable that caused it. "
        "It is <b>not</b> an official forecast, advisory or warning &mdash; those are issued "
        "only by the National Weather Service, and this dashboard reproduces them verbatim in "
        "a separate panel without feeding them into any rating.",
        "La <b>Idoneidad Operacional</b> es la evaluación propia de CariCOOS. Compara las "
        "condiciones observadas y pronosticadas con los límites publicados abajo, por separado "
        "para cada clase de embarcación, e informa el peor resultado junto con la variable que "
        "lo causó. <b>No</b> es un pronóstico, aviso ni advertencia oficial: estos los emite "
        "únicamente el Servicio Nacional de Meteorología, y este tablero los reproduce "
        "literalmente en un panel aparte sin incorporarlos a ninguna evaluación.")

    policy = M.bi(
        "Every number below comes from <code>config/thresholds.tsv</code>, which this page "
        "reads directly. There is exactly one copy of these limits, so what you see here is "
        "what the ratings actually use. A limit whose provenance has not yet been confirmed "
        "carries a <span class=\"verify\">VERIFY</span> tag and keeps it until somebody checks it.",
        "Cada número proviene de <code>config/thresholds.tsv</code>, que esta página lee "
        "directamente. Existe una sola copia de estos límites, así que lo que ve aquí es lo que "
        "realmente usan las evaluaciones. Un límite cuya procedencia aún no se ha confirmado "
        "lleva la etiqueta <span class=\"verify\">VERIFY</span> hasta que alguien lo verifique.")

    nver = sum(1 for t in ths if "VERIFY" in t.source.upper())
    body = f"""
<p class="lead">{lead}</p>
<div class="keybox">{key}</div>
<h2>{M.bi("Thresholds", "Umbrales")}</h2>
<p class="lead">{policy}</p>
<table class="th">
<thead><tr>
<th>{M.bi("Variable", "Variable")}</th>
<th>{M.bi("Marginal", "Marginal")}</th>
<th>{M.bi("Unfavorable", "Desfavorable")}</th>
<th>{M.bi("Applies to", "Aplica a")}</th>
<th>{M.bi("Source", "Fuente")}</th>
</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
<h3>{M.bi("How a rating is combined", "Cómo se combina una evaluación")}</h3>
<p class="lead">{M.bi(
    "Each applicable variable is rated on its own, and the site takes the <b>worst</b> of them. "
    "When two variables are equally bad, the one furthest past its limit is reported as the "
    "driver, so a sea that is both tall and steep is correctly described as steep. "
    "A variable with no data is skipped rather than assumed to pass, and a location with no "
    "usable data at all reads <i>No data</i> &mdash; never <i>Favorable</i>.",
    "Cada variable aplicable se evalúa por separado y el lugar toma la <b>peor</b> de ellas. "
    "Cuando dos variables están igual de mal, se informa como causa la que más excede su "
    "límite, de modo que un mar alto y escarpado se describe correctamente como escarpado. "
    "Una variable sin datos se omite en vez de suponer que aprueba, y un lugar sin datos "
    "utilizables lee <i>Sin datos</i>, nunca <i>Favorable</i>.")}</p>
<h3>{M.bi("Where the numbers come from", "De dónde vienen los números")}</h3>
<p class="lead">{M.bi(
    "Forecast conditions come from the National Weather Service San Juan Coastal Waters "
    "Forecast for each location's marine zone. Wave period and direction are published for "
    "roughly the first three days; beyond that, ratings use wind and sea height only. "
    "Observed buoy and wind-station data are added in the next release.",
    "Las condiciones pronosticadas provienen del Pronóstico de Aguas Costeras del Servicio "
    "Nacional de Meteorología de San Juan para la zona marina de cada lugar. El periodo y la "
    "dirección del oleaje se publican aproximadamente para los primeros tres días; más allá, "
    "la evaluación usa solo viento y altura del oleaje. Los datos observados de boyas y "
    "estaciones de viento se añaden en la próxima versión.")}</p>
"""
    limits = {f"{t.cls}/{t.var}/{','.join(t.applies_to)}":
              {"marginal": t.marginal, "unfavorable": t.unfavorable,
               "unit": VAR_UNIT.get(t.var, "-")} for t in ths}
    gen = M.bi(
        f"Rendered directly from config/thresholds.tsv &middot; {len(ths)} thresholds, "
        f"{nver} still marked VERIFY.",
        f"Generado directamente desde config/thresholds.tsv &middot; {len(ths)} umbrales, "
        f"{nver} aún marcados VERIFY.")
    html_out = M.page_shell("methods.html", "Methods", "Métodos",
                            "How every rating is made", "Cómo se hace cada evaluación",
                            body, extra_css=CSS,
                            scripts=JS.replace("__LIMITS__", json.dumps(limits)),
                            generated=gen)
    out = os.path.join(M.WEBOUT, "methods.html")
    M.atomic_write_text(html_out, out)
    print(f"[make_methods] wrote {out} ({len(html_out):,} bytes, {len(ths)} thresholds, "
          f"{nver} unverified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
