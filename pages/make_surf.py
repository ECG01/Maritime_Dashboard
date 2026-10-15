#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/surf_zone.html - the NWS Surf Zone Forecast, on its own page.

Why it is its own page and no longer a block at the top of marine_zones.html:
the people it serves are not the people the Coastal Waters Forecast serves. Rip
current risk is a swimmer's and a beachgoer's number; the CWF is a vessel's. Each
was burying the other.

Editorial rule, unchanged: this is a FORECAST. A Low or Moderate rip current risk
is never issued as an alert product, and the only thing that becomes one is a High
risk, which the NWS issues as a Rip Current Statement. Nothing here is called an
advisory, a warning or a watch.
"""
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402

CSS = r"""
.lead{max-width:66ch}
.colh{font:700 .7rem "Archivo",sans-serif;letter-spacing:.07em;text-transform:uppercase;
  color:var(--ink2);margin-bottom:.45rem}

/* --- Surf Zone Forecast ----------------------------------------------------
   Same 2px --s2 frame the NWS products panel uses, because this is NWS content
   too. The risk chip carries colour AND an ordered glyph AND the word: the
   glyphs fill up as the risk rises, so it survives greyscale, CVD and
   forced-colors, and it is a different glyph set from our own suitability chips
   on purpose - this is the NWS's category, not a CariCOOS rating. */
.srf{border:2px solid var(--s2);border-radius:8px;background:var(--panel);
  padding:.85rem 1rem;margin:0 0 1.2rem}
.srf h3{margin:0 0 .35rem;font:700 .95rem "Archivo",sans-serif;letter-spacing:.04em;
  text-transform:uppercase;color:var(--s2)}
.srf .lead2{font-size:.9rem;line-height:1.5;max-width:68ch;margin:.2rem 0 .8rem}
.srf .hi{background:var(--flag);color:#fff;border-radius:6px;padding:.45rem .7rem;
  font-weight:600;margin:0 0 .8rem}
/* La nota de procedencia vivia sin estilo: .attrib solo estaba definido dentro
   de .nws, y aqui el bloque no es .nws. */
.srf .attrib{font:400 .78rem "Source Sans 3",sans-serif;color:var(--ink2);margin-top:.5rem}
table.beach{width:100%;border-collapse:collapse;font-size:.88rem}
table.beach th{text-align:left;font:700 .68rem "Archivo",sans-serif;text-transform:uppercase;
  letter-spacing:.05em;color:var(--ink2);padding:.3rem .45rem;border-bottom:1px solid var(--line)}
/* El grupo que abarca las dos columnas de resaca: centrado y con una linea
   debajo que deja ver hasta donde llega. */
table.beach th.grp{text-align:center;color:var(--s2);border-bottom:2px solid var(--s2)}
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
/* Con la columna de playas fuera quedan cinco, y en 390 px seguian pasandose
   por catorce pixeles: la pagina entera se iba de lado por una tabla. Menos
   relleno en la celda y en la pastilla, que es de donde salia el ancho. */
@media (max-width:480px){
  table.beach{font-size:.84rem}
  table.beach th,table.beach td{padding:.3rem .22rem}
  .rc{padding:.12rem .42rem;font-size:.78rem}
  .rc .g{font-size:.8em}
  /* Quien se comia el ancho era el titulo, no el dato: "TOMORROW" es una sola
     palabra que no parte, y a .68rem con espaciado medía 80 px y dejaba la
     columna del area en 68. Con el area estrecha "San Juan and Vicinity PR"
     caia en tres lineas. */
  table.beach th{font-size:.6rem;letter-spacing:.01em}
  table.beach td.z{font-size:.68rem}
}
/* Por debajo de unos 380 px - un iPhone SE - ni con los titulos encogidos cabe
   la tabla, y lo que se salia arrastraba la pagina entera de lado. Que se
   deslice ella dentro de su caja y no el documento: asi no se pierde ni la
   columna del codigo NWS ni ninguna de las dos de resaca. */
@media (max-width:380px){
  .beachwrap{overflow-x:auto}
  .beachwrap table.beach{min-width:330px}
}
"""

# Open circle -> half -> full. Ordered, so the glyph alone carries the ranking
# for a reader in greyscale, with a colour vision deficiency, or no colour
# at all. Deliberately NOT the chips our own suitability uses: this is the NWS's
# category, and the two must never look like the same judgement.
RC_GLYPH = {"low": "○", "moderate": "◐", "high": "●"}
RC_ES = {"low": "Bajo", "moderate": "Moderado", "high": "Alto"}


def rc_chip(risk):
    """Colour + ordered glyph + the word. Never colour alone."""
    if not risk:
        return ('<span class="rc none"><span class="g">–</span>'
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
    """Rip current risk and surf by beach zone, from the NWS product."""
    zones = srf.get("zones") or []
    if not zones:
        # Sin el producto la pagina sigue en pie y lo dice. Una tabla vacia se
        # leeria como "no hay riesgo", que es lo contrario de "no se sabe".
        return ('<div class="srf"><h3>'
                + M.bi("NWS Surf Zone Forecast",
                       "Pronóstico de Zona de Rompiente NWS")
                + '</h3><p class="lead2">' + M.bi(
                    "The Surf Zone Forecast is not available right now. This page "
                    "does not estimate rip current risk on its own &mdash; the "
                    "categories are the National Weather Service's and only it "
                    "issues them.",
                    "El Pronóstico de Zona de Rompiente no está disponible en este "
                    "momento. Esta página no estima el riesgo de corrientes de "
                    "resaca por su cuenta: las categorías son del Servicio Nacional "
                    "de Meteorología y solo él las emite.") + "</p></div>")
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
            # Las dos columnas de resaca van juntas. Antes la rompiente se
            # metia entre ellas y la ultima se titulaba solo "Mañana", asi que
            # se leia como la rompiente de mañana cuando era el riesgo de
            # resaca. La columna del medio no puede pertenecer a otro grupo.
            f'<td>{rc_chip((d0 or {}).get("risk"))}</td>'
            f'<td>{rc_chip((d1 or {}).get("risk"))}</td>'
            f"{surf_cell(d0)}"
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
    "A Low or Moderate rip current risk is never issued as a warning product, so it "
    "appears nowhere else on this site &mdash; only a High risk becomes a Rip "
    "Current Statement, and those are listed under <i>NWS products in effect</i> on "
    "the Conditions now board. The categories and their wording are the NWS's own.",
    "Riesgo de corrientes de resaca y altura de rompiente por zona de playa, del "
    "Pronóstico de Zona de Rompiente del Servicio Nacional de Meteorología. "
    "<b>Esto es un pronóstico, no un aviso.</b> Un riesgo Bajo o Moderado nunca se "
    "emite como producto de advertencia, así que no aparece en ningún otro sitio de "
    "esta página: solo un riesgo Alto se convierte en un Rip Current Statement, y "
    "esos salen en <i>Productos del NWS vigentes</i> en el tablero de Condiciones "
    "ahora. Las categorías y su redacción son del NWS.")}</p>
<div class="beachwrap"><table class="beach"><thead><tr>
  <th rowspan="2">{M.bi("Zone", "Zona")}</th>
  <th rowspan="2">{M.bi("Area", "Área")}</th>
  <th rowspan="2" class="b">{M.bi("Beaches", "Playas")}</th>
  <th colspan="2" class="grp">{M.bi("Rip current risk", "Riesgo de resaca")}</th>
  <th rowspan="2">{M.bi("Surf today", "Rompiente hoy")}</th>
</tr><tr>
  <th>{d0h}</th><th>{d1h}</th>
</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
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


JS = """
function onUnits(){
  document.querySelectorAll('[data-v]').forEach(el=>{
    const k=el.dataset.k, v=el.dataset.v;
    el.textContent = v===''? '\\u2013' : fv(k, parseFloat(v), k==='s'?0:1);
  });
}
function onLang(){paintStamp();}
function onTZ(){paintStamp();}
onUnits();
"""


def main():
    srf = M.read_json("nws", "srf.json") or {}
    zones = srf.get("zones") or []

    lead = M.bi(
        "Where the water is dangerous to be <i>in</i>, rather than to be on. Rip "
        "currents kill more people on these beaches than any other marine hazard, "
        "and the risk is highest on days that look perfectly calm from the sand. "
        "The risk category and the surf height below are the National Weather "
        "Service's own, by beach zone.",
        "Dónde es peligroso estar <i>dentro</i> del agua, no sobre ella. Las "
        "corrientes de resaca matan a más gente en estas playas que cualquier otro "
        "peligro marino, y el riesgo es mayor en días que desde la arena se ven "
        "perfectamente tranquilos. La categoría de riesgo y la altura de rompiente "
        "de abajo son del Servicio Nacional de Meteorología, por zona de playa.")

    body = f'{M.STAMP_HTML}<p class="lead">{lead}</p>\n{surf_section(srf)}'
    gen = M.bi(
        f"NWS {srf.get('office', 'SJU')} Surf Zone Forecast issued "
        f"{(srf.get('issued_utc') or '?')[:16]}Z. Refreshes every 30 minutes.",
        f"Pronóstico de Zona de Rompiente del NWS {srf.get('office', 'SJU')} "
        f"emitido {(srf.get('issued_utc') or '?')[:16]}Z. Se actualiza cada 30 "
        f"minutos.")
    out_html = M.page_shell("surf_zone.html",
                            "NWS Surf Zone Forecast",
                            "Pronóstico de Zona de Rompiente NWS",
                            "Rip current risk and surf, by beach zone",
                            "Riesgo de resaca y rompiente, por zona de playa",
                            body, extra_css=CSS + M.STAMP_CSS,
                            scripts=JS + M.stamp_js([
                                {"en": "Surf Zone Forecast issued",
                                 "es": "Pron\u00f3stico de rompiente emitido",
                                 "iso": srf.get("issued_utc"), "date": True},
                                {"en": "Page built", "es": "P\u00e1gina generada",
                                 "gen": True, "ago": True},
                            ], M.utcnow().isoformat()),
                            generated=gen)
    out = os.path.join(M.WEBOUT, "surf_zone.html")
    M.atomic_write_text(out_html, out)
    print(f"[make_surf] wrote {out} ({len(out_html):,} bytes, {len(zones)} beach zones)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
