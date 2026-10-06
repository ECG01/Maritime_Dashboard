#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/tools.html - the four existing CARICOOS tools, embedded.

Each tool sits behind a click-to-load poster rather than an eager iframe: the
Model Viewer is a full MapLibre application and the two hubs carry large data
chunks, so loading all four on page open would cost a mariner on a phone several
megabytes before they had asked for anything.

Every tool also carries an 'Open in new tab' link. Framing a map application
breaks its deep links and the back button, so the escape hatch is not optional.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                     # noqa: E402

# (key, env var, title, what it is, when a mariner should reach for it)
TOOLS = [
    ("buoys", "BUOYS_HUB_URL",
     ("Ocean Buoys Hub", "Centro de Boyas Oceánicas"),
     ("Wave height, period and direction, water temperature, salinity and currents from the "
      "CariCOOS data buoys and Waveriders, back to 2009.",
      "Altura, periodo y dirección del oleaje, temperatura del agua, salinidad y corrientes "
      "de las boyas de datos y Waveriders de CariCOOS, desde 2009."),
     ("Use it when you want to check what the sea is <i>actually</i> doing right now at a "
      "specific buoy, or to see how today compares with the record.",
      "Úselo para comprobar qué está haciendo <i>realmente</i> el mar ahora en una boya "
      "concreta, o para comparar el día de hoy con el histórico.")),
    ("mesonet", "MESONET_HUB_URL",
     ("Wind Stations Hub", "Centro de Estaciones de Viento"),
     ("Quality-controlled wind speed, direction and gusts from 37 stations across Puerto Rico "
      "and the U.S. Virgin Islands, plus temperature and pressure.",
      "Velocidad, dirección y ráfagas de viento con control de calidad de 37 estaciones en "
      "Puerto Rico y las Islas Vírgenes, más temperatura y presión."),
     ("Use it when wind is the deciding factor &mdash; a lee shore, a gusty channel, or a "
      "berthing window.",
      "Úselo cuando el viento sea el factor decisivo: una costa de sotavento, un canal "
      "racheado o una ventana de atraque.")),
    ("modviewer", "MODVIEWER_URL",
     ("Model Viewer", "Visor de Modelos"),
     ("Interactive map of the forecast models &mdash; winds, waves, currents, water level, "
      "radar and satellite &mdash; over Puerto Rico and the U.S. Virgin Islands.",
      "Mapa interactivo de los modelos de pronóstico: vientos, oleaje, corrientes, nivel del "
      "mar, radar y satélite sobre Puerto Rico y las Islas Vírgenes."),
     ("Use it to see the <i>pattern</i>: where a swell is coming from, how a front is moving, "
      "or what the current is doing across a passage.",
      "Úselo para ver el <i>patrón</i>: de dónde viene una marejada, cómo se mueve un frente "
      "o qué hace la corriente en un canal.")),
    ("classic", "CLASSIC_VIEWER_URL",
     ("Model Viewer (classic)", "Visor de Modelos (clásico)"),
     ("The original model dashboard: animated WRF, SWAN, FVCOM, RTOFS and STOFS forecast "
      "imagery.",
      "El tablero de modelos original: animaciones de los pronósticos WRF, SWAN, FVCOM, "
      "RTOFS y STOFS."),
     ("Use it for a quick animated loop of a single model, or when you want the familiar "
      "view.",
      "Úselo para un lazo animado rápido de un solo modelo, o cuando prefiera la vista "
      "de siempre.")),
]

CSS = r"""
.tool{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  margin-bottom:1.4rem;overflow:hidden}
.tool .head{padding:.9rem 1rem .8rem}
.tool h3{margin:0;font:700 1.1rem "Archivo",sans-serif}
.tool .what{margin:.35rem 0 .2rem;max-width:66ch}
.tool .when{margin:.2rem 0 0;color:var(--ink2);font-size:.92rem;max-width:66ch}
.tool .bar{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;
  padding:.6rem 1rem;background:var(--controls);border-top:1px solid var(--line)}
.btn{font:600 .85rem "Source Sans 3",sans-serif;border:1px solid var(--line);
  background:var(--btn);color:var(--ink);padding:.35rem .8rem;border-radius:5px;
  cursor:pointer;text-decoration:none;display:inline-block}
.btn:hover{background:var(--sel)}
.btn.primary{background:var(--btn-on);color:var(--btn-on-ink);border-color:var(--btn-on)}
.frame{display:none}
.frame.on{display:block}
.frame iframe{display:block;width:100%;height:600px;border:0;background:var(--surface)}
.hint{font-size:.85rem;color:var(--ink2)}
.lead{max-width:64ch}
@media (max-width:720px){.frame iframe{height:420px}}
"""

JS = r"""
/* A browser refuses to embed an http:// page inside an https:// one - mixed
   content, no override. The classic Model Viewer has to be http (its S3 image
   host speaks no https), so on a secure page it cannot be framed at all. Rather
   than open an iframe the browser will silently blank, hide the "Show here"
   button for those and say why. */
/* The tools page uses T(key) against the shared I18N dict; T2 is the inline
   two-string form the rest of the site uses for one-off text. */
const T2=(en,es)=>L==='es'?es:en;
function blockedByMixedContent(url){
  return location.protocol==='https:' && /^http:\/\//i.test(url||'');
}
document.querySelectorAll('[data-load]').forEach(function(b){
  if(!blockedByMixedContent(b.dataset.url))return;
  const note=document.createElement('span');
  note.className='hint';
  note.textContent=T2('This tool only runs over an insecure connection, so it cannot be shown inside this page. Open it in a new tab.',
                      'Esta herramienta solo funciona por conexión no segura, así que no puede mostrarse dentro de esta página. Ábrela en una pestaña nueva.');
  b.replaceWith(note);
});
document.addEventListener('click',function(ev){
  const b=ev.target.closest('[data-load]'); if(!b)return;
  const k=b.dataset.load;
  const box=document.getElementById('f_'+k);
  if(!box.querySelector('iframe')){
    const f=document.createElement('iframe');
    f.src=b.dataset.url; f.loading='lazy'; f.title=b.dataset.title;
    f.referrerPolicy='no-referrer-when-downgrade';
    f.setAttribute('sandbox','allow-scripts allow-same-origin allow-popups allow-forms');
    box.appendChild(f);
  }
  box.classList.toggle('on');
  b.textContent = box.classList.contains('on') ? T('hide') : T('load');
});
function onLang(){
  document.querySelectorAll('[data-load]').forEach(b=>{
    const box=document.getElementById('f_'+b.dataset.load);
    b.textContent = box.classList.contains('on') ? T('hide') : T('load');
  });
}
"""


def main():
    env = M.load_env()
    cards = []
    for key, envvar, (ten, tes), (wen, wes), (uen, ues) in TOOLS:
        url = env.get(envvar, "")
        ext = url.startswith("http")
        cards.append(f"""
<div class="tool">
  <div class="head">
    <h3>{M.bi(ten, tes)}</h3>
    <p class="what">{M.bi(wen, wes)}</p>
    <p class="when">{M.bi(uen, ues)}</p>
  </div>
  <div class="bar">
    <button class="btn primary" data-load="{key}" data-url="{url}"
            data-title="{ten}">{M.bi("Show here", "Mostrar aquí")}</button>
    <a class="btn" href="{url}" target="_blank" rel="noopener">{
        M.bi("Open in new tab", "Abrir en pestaña nueva")} &#8599;</a>
    <span class="hint">{M.bi(
        "Opens full screen with its own address bar and back button."
        if ext else
        "Part of this site; opens full screen with its own address bar and back button.",
        "Se abre a pantalla completa con su propia barra de direcciones y botón atrás."
        if ext else
        "Forma parte de este sitio; se abre a pantalla completa con su propia barra de "
        "direcciones y botón atrás.")}</span>
  </div>
  <div class="frame" id="f_{key}"></div>
</div>""")

    lead = M.bi(
        "These are the four CARICOOS tools this dashboard draws on. Each one can be shown "
        "inline here, or opened full screen in its own tab &mdash; which is usually better if "
        "you want to zoom around a map or keep a link. Nothing loads until you ask for it.",
        "Estas son las cuatro herramientas de CARICOOS en las que se apoya este tablero. Cada "
        "una puede mostrarse aquí mismo o abrirse a pantalla completa en su propia pestaña, lo "
        "cual suele ser mejor si quiere moverse por un mapa o guardar un enlace. Nada se carga "
        "hasta que usted lo pida.")

    body = f'<p class="lead">{lead}</p>{"".join(cards)}'
    gen = M.bi("The tools above are maintained separately; this page only links and frames them.",
               "Las herramientas anteriores se mantienen por separado; esta página solo las "
               "enlaza y las enmarca.")
    out_html = M.page_shell("tools.html", "Tools", "Herramientas",
                            "The CARICOOS tools behind this board",
                            "Las herramientas de CARICOOS tras este tablero",
                            body, extra_css=CSS, scripts=JS, generated=gen,
                            i18n='const I18N={load:{en:"Show here",es:"Mostrar aqu\u00ed"},'
                                 'hide:{en:"Hide",es:"Ocultar"}};')
    out = os.path.join(M.WEBOUT, "tools.html")
    M.atomic_write_text(out_html, out)
    print(f"[make_tools] wrote {out} ({len(out_html):,} bytes, {len(TOOLS)} tools)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
