#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/model_viewer.html - the CARICOOS Model Viewer, as a panel.

Unlike the Data Analysis page, this one loads the application immediately and
gives it the whole screen. The reasoning is the reverse of the one there: a
reader who opened a page called Model Viewer has already said what they want,
so a click-to-load poster would only add a step. The cost is real - it is a
full MapLibre application - so it is on its own tab and nowhere else, and it
never loads for someone who did not ask.

The 'Open in new tab' link stays. Framing a map application breaks its deep
links and the browser's back button, so the escape hatch is not optional.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402

CSS = r"""
.mvbar{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;margin:0 0 .6rem}
.mvbar .what{flex:1 1 34ch;min-width:0;font-size:.9rem;color:var(--ink2);margin:0}
.btn{font:600 .85rem "Source Sans 3",sans-serif;border:1px solid var(--line);
  background:var(--btn);color:var(--ink);padding:.35rem .8rem;border-radius:5px;
  cursor:pointer;text-decoration:none;display:inline-block;flex:0 0 auto}
.btn:hover{background:var(--sel)}
/* El visor ocupa lo que queda de pantalla por debajo del encabezado, con un
   minimo para que en un telefono apaisado no quede una rendija. 100svh y no
   100vh: en moviles la barra del navegador se retrae y 100vh deja el mapa
   cortado por debajo del pliegue. */
.mvframe{border:1px solid var(--line);border-radius:8px;overflow:hidden;
  background:var(--panel)}
.mvframe iframe{display:block;width:100%;height:calc(100svh - 200px);
  min-height:420px;border:0}
@media (max-width:720px){
  /* En un telefono la barra de arriba se parte en dos lineas, asi que el
     descuento fijo ya no cuadra: se mide en proporcion de pantalla. */
  .mvframe iframe{height:65svh}
}
.mvnote{font-size:.85rem;color:var(--ink2);margin:.6rem 0 0;max-width:70ch}
"""

JS = r"""
/* Un navegador se niega a embeber una pagina http:// dentro de una https:// -
   contenido mixto, sin excepcion posible. Si el visor llegara a servirse por
   http no hay iframe que valga, asi que se dice y se manda al enlace. */
const T2=(en,es)=>L==='es'?es:en;
(function(){
  const box=document.getElementById('mvbox');
  if(!box)return;
  const url=box.dataset.url||'';
  if(location.protocol==='https:' && /^http:\/\//i.test(url)){
    box.innerHTML='<p style="padding:1rem;margin:0">'+T2(
      'The Model Viewer is being served over an insecure connection, so it cannot be shown inside this page. Use the link above to open it in a new tab.',
      'El Visor de Modelos se esta sirviendo por una conexion no segura, asi que no puede mostrarse dentro de esta pagina. Use el enlace de arriba para abrirlo en una pestana nueva.')+'</p>';
    return;
  }
  const f=document.createElement('iframe');
  f.src=url;
  f.title='CARICOOS Model Viewer';
  f.referrerPolicy='no-referrer-when-downgrade';
  f.setAttribute('allow','fullscreen');
  f.setAttribute('sandbox','allow-scripts allow-same-origin allow-popups allow-forms');
  box.appendChild(f);
})();
function onUnits(){}
function onLang(){}
function onTZ(){}
"""


def main():
    env = M.load_env()
    url = env.get("MODVIEWER_URL", "")

    what = M.bi(
        "Winds, waves, currents, water level, radar and satellite over Puerto Rico "
        "and the U.S. Virgin Islands &mdash; the forecast models as a map.",
        "Vientos, oleaje, corrientes, nivel del mar, radar y satélite sobre Puerto "
        "Rico y las Islas Vírgenes: los modelos de pronóstico en un mapa.")
    note = M.bi(
        "This is the pattern view: where a swell is coming from, how a front is "
        "moving, what the current is doing across a passage. For a number at a "
        "specific place and time, the Conditions now board is the measurement and "
        "the NWS Marine Forecast is the official word. A model is neither.",
        "Esta es la vista del patrón: de dónde viene una marejada, cómo se mueve un "
        "frente, qué hace la corriente en un canal. Para un número en un lugar y una "
        "hora concretos, el tablero de Condiciones ahora es la medición y el "
        "Pronóstico Marino NWS es la palabra oficial. Un modelo no es ninguna de las "
        "dos cosas.")

    # El visor clasico se sirve solo por http, asi que en una pagina https no
    # hay iframe posible - va como enlace y nada mas. Vive aqui y no en Analisis
    # de Datos porque es un visor de modelos, igual que el de arriba.
    classic = env.get("CLASSIC_VIEWER_URL", "")
    cl = ("" if not classic else
          '<p class="mvnote">' + M.bi(
              "Prefer the original animated loops &mdash; WRF, SWAN, FVCOM, RTOFS, "
              "STOFS? ", "\u00bfPrefiere las animaciones originales: WRF, SWAN, FVCOM, "
              "RTOFS, STOFS? ")
          + f'<a href="{classic}" target="_blank" rel="noopener">'
          + M.bi("Model Viewer (classic)", "Visor de Modelos (cl\u00e1sico)")
          + ' &#8599;</a></p>')

    body = f"""
<div class="mvbar">
  <p class="what">{what}</p>
  <a class="btn" href="{url}" target="_blank" rel="noopener">{
      M.bi("Open in new tab", "Abrir en pestaña nueva")} &#8599;</a>
</div>
<div class="mvframe" id="mvbox" data-url="{url}"></div>
<p class="mvnote">{note}</p>
{cl}
"""
    gen = M.bi(
        "The Model Viewer is maintained separately by CARICOOS; this page frames it.",
        "El Visor de Modelos lo mantiene CARICOOS por separado; esta página solo lo "
        "enmarca.")
    out_html = M.page_shell("model_viewer.html", "Model Viewer", "Visor de Modelos",
                            "The forecast models, as a map",
                            "Los modelos de pronóstico, en un mapa",
                            body, extra_css=CSS, scripts=JS, generated=gen,
                            # Sin el panel de preguntas: responde desde las
                            # mediciones del tablero, y un boton flotante sobre
                            # un mapa a pantalla completa estorba justo donde el
                            # lector vino a trabajar.
                            chat=False)
    out = os.path.join(M.WEBOUT, "model_viewer.html")
    M.atomic_write_text(out_html, out)
    print(f"[make_modviewer] wrote {out} ({len(out_html):,} bytes, url={url or 'MISSING'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
