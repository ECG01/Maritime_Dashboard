#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/conditions_now.html - the Operational Suitability board.

Reads ONLY from data/ (never the network), so a failed fetch degrades to the last
good payload with a visible age badge instead of an empty page.

The payload is injected once as `const D = {...}` and the table is rendered in the
browser, so the EN/ES, metric/marine and UTC/AST toggles all re-render from data
already in the page rather than needing a round trip.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402
from engine import cwf_parse as C       # noqa: E402
from engine import ratings as R         # noqa: E402

I18N = {
    "title": {"en": "Conditions now", "es": "Condiciones ahora"},
    "site": {"en": "Location", "es": "Lugar"},
    "wind": {"en": "Wind (from)", "es": "Viento (de)"},
    "gust": {"en": "Gust", "es": "Ráfaga"},
    "seas": {"en": "Seas (from)", "es": "Oleaje (de)"},
    "period": {"en": "Wave period", "es": "Periodo del oleaje"},
    "suit": {"en": "Operational Suitability", "es": "Idoneidad Operacional"},
    "src": {"en": "Source", "es": "Fuente"},
    "limit": {"en": "limit", "es": "límite"},
    "openin": {"en": "Open in new tab", "es": "Abrir en pestaña nueva"},
    "loadtool": {"en": "Load interactive tool", "es": "Cargar herramienta interactiva"},
    "nwsnone": {"en": "No NWS marine warnings, watches or advisories are in effect "
                      "for the zones on this board.",
                "es": "No hay advertencias, vigilancias ni avisos marinos del NWS "
                      "vigentes para las zonas de este tablero."},
    "nwshead": {"en": "NWS products in effect", "es": "Productos del NWS vigentes"},
    "fcst": {"en": "Forecast basis", "es": "Base del pronóstico"},
    "detail": {"en": "Details", "es": "Detalles"},
    "nrhint": {"en": "This vessel class is not assessed at this location",
               "es": "Esta clase de embarcación no se evalúa en este lugar"},
    # why a rating came out the way it did - key + value, never a baked sentence
    "why_wind_kt": {"en": "wind {v}", "es": "viento {v}"},
    "why_gust_kt": {"en": "gusts {v}", "es": "ráfagas {v}"},
    "why_hs_m": {"en": "seas {v}", "es": "oleaje {v}"},
    "why_steepness": {"en": "steep seas {v}", "es": "oleaje escarpado {v}"},
    "why_lp_swell_m": {"en": "long-period swell {v}", "es": "marejada de periodo largo {v}"},
    "why_hs_beam_m": {"en": "beam seas {v}", "es": "oleaje de través {v}"},
    "why_roll_ratio": {"en": "roll resonance {v}", "es": "resonancia de balance {v}"},
    "why_wind_vs_curr": {"en": "wind against current {v}", "es": "viento contra corriente {v}"},
}
# the unit KIND each variable is stored in, so the browser converts correctly
VAR_UNIT = {"wind_kt": "kt", "gust_kt": "kt", "hs_m": "m", "steepness": "-",
            "lp_swell_m": "m", "hs_beam_m": "m", "roll_ratio": "-", "wind_vs_curr": "kt"}


def build_payload(env):
    cwf = M.read_json("nws", "cwf.json") or {}
    alerts = M.read_json("nws", "alerts.json") or {"alerts": []}
    ths = R.load_thresholds()
    sites = M.load_sites()
    srcs = M.load_sources()
    embed_url = {"buoys": env["BUOYS_HUB_URL"], "mesonet": env["MESONET_HUB_URL"],
                 "modviewer": env["MODVIEWER_URL"], "classic": env["CLASSIC_VIEWER_URL"]}
    embed_name = {"buoys": ("Ocean Buoys Hub", "Centro de Boyas"),
                  "mesonet": ("Wind Stations Hub", "Centro de Estaciones de Viento"),
                  "modviewer": ("Model Viewer", "Visor de Modelos"),
                  "classic": ("Model Viewer (classic)", "Visor de Modelos (clásico)")}

    out = []
    for s in sites:
        fr = C.frames(cwf, s["zone"])
        p = fr[0] if fr else {}
        raw = {k: p.get(k) for k in ("hs_m", "tp_s", "dp_deg", "wind_kt", "gust_kt", "wdir_deg")}
        sample = R.prepare_sample(raw, kind=s["kind"])
        ratings = {}
        for c in M.CLASSES:
            if c not in s["classes"]:
                continue
            r = R.rate(sample, c, s["kind"], ths)
            ratings[c] = {"status": r.status, "driver": r.driver, "value": r.value,
                          "limit": r.limit, "unit": VAR_UNIT.get(r.driver, "-"),
                          "source": r.source}
        out.append({
            "id": s["site_id"], "en": s["name_en"], "es": s["name_es"],
            "group": s["group"], "kind": s["kind"], "zone": s["zone"],
            "lat": s["lat"], "lon": s["lon"],
            "notes_en": s["notes"], "notes_es": M.es_note(s["notes"]),
            "wind_kt": p.get("wind_kt"), "gust_kt": p.get("gust_kt"),
            "wdir": p.get("wdir_deg"), "hs_m": p.get("hs_m"),
            "tp_s": p.get("tp_s"), "dp": p.get("dp_deg"),
            "period_label": p.get("label"), "period_text": p.get("text"),
            "start_utc": p.get("start_utc"), "end_utc": p.get("end_utc"),
            "ratings": ratings,
            "embed": s["embed"], "embed_url": embed_url.get(s["embed"], ""),
            "embed_en": embed_name.get(s["embed"], ("", ""))[0],
            "embed_es": embed_name.get(s["embed"], ("", ""))[1],
            "obs_wave": [{"id": i, "name": srcs[i]["name_en"], "link": srcs[i]["link"],
                          "down": srcs[i]["down"]} for i in s["obs_wave"] if i in srcs],
            "obs_wind": [{"id": i, "name": srcs[i]["name_en"], "link": srcs[i]["link"],
                          "down": srcs[i]["down"]} for i in s["obs_wind"] if i in srcs],
        })

    groups = [{"key": g, "en": M.GROUP_BI[g][0], "es": M.GROUP_BI[g][1]}
              for g in M.GROUP_ORDER if any(x["group"] == g for x in out)]
    return {
        "generated_utc": M.utcnow().isoformat(),
        "cwf_issued": cwf.get("issued_utc"), "cwf_fetched": cwf.get("fetched_utc"),
        "cwf_url": cwf.get("product_url"), "office": cwf.get("office", "SJU"),
        "synopsis": cwf.get("synopsis"),
        "classes": [{"key": c, "en": M.CLASS_BI[c][0], "es": M.CLASS_BI[c][1]}
                    for c in M.CLASSES],
        "groups": groups, "sites": out,
        "alerts": alerts.get("alerts", []),
        "status_bi": {k: {"en": v[0], "es": v[1]} for k, v in M.STATUS_BI.items()},
        "glyph": M.STATUS_GLYPH,
    }


CSS = r"""
table.board{width:100%;border-collapse:collapse;background:var(--panel);
  border:1px solid var(--line);border-radius:8px;overflow:hidden}
table.board th{background:var(--controls);font:600 .78rem "Archivo",sans-serif;
  letter-spacing:.04em;text-transform:uppercase;color:var(--ink2);
  padding:.5rem .6rem;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
table.board td{padding:.45rem .6rem;border-bottom:1px solid var(--grid);vertical-align:middle}
table.board tr.grp td{background:var(--controls);font:700 .85rem "Archivo",sans-serif;
  letter-spacing:.05em;text-transform:uppercase;color:var(--navy);padding:.5rem .6rem}
:root[data-theme="dark"] table.board tr.grp td,
@media (prefers-color-scheme:dark){table.board tr.grp td{color:var(--teal)}}
table.board tr.site:hover{background:var(--sel)}
.sitename{font-weight:600;cursor:pointer;display:flex;align-items:center;gap:.4rem}
.sitename .caret{color:var(--ink2);font-size:.75rem;transition:transform .12s}
.sitename.open .caret{transform:rotate(90deg)}
.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.arrow{display:inline-block;color:var(--ink2)}
.drawer td{background:var(--surface);padding:.8rem 1rem}
.drawer .cols{display:flex;gap:1.2rem;flex-wrap:wrap}
.drawer .col{flex:1 1 260px;min-width:240px}
.drawer h4{margin:0 0 .3rem;font:700 .8rem "Archivo",sans-serif;text-transform:uppercase;
  letter-spacing:.05em;color:var(--ink2)}
.drawer .fcsttext{font-size:.88rem;line-height:1.45}
.embedbox{margin-top:.6rem;border:1px solid var(--line);border-radius:6px;overflow:hidden;
  background:var(--panel)}
.embedbox .bar{display:flex;align-items:center;justify-content:space-between;gap:.6rem;
  padding:.4rem .6rem;background:var(--controls);font-size:.85rem}
.embedbox iframe{display:block;width:100%;height:440px;border:0;background:var(--surface)}
.btn{font:600 .8rem "Source Sans 3",sans-serif;border:1px solid var(--line);
  background:var(--btn);color:var(--ink);padding:.3rem .7rem;border-radius:5px;cursor:pointer}
.btn:hover{background:var(--sel)}
.srcline{font-size:.85rem;color:var(--ink2)}
.srcline .down{color:var(--flag);font-weight:600}
.lead{max-width:68ch}
@media (max-width:860px){
  table.board{display:block;overflow-x:auto;white-space:nowrap}
  .drawer .col{min-width:200px}
}
"""

JS = r"""
const D = __DATA__;
const VU = __VARUNIT__;

function T(k){const d=I18N[k];return d?(d[L]||d.en||k):k;}
function nm(o){return L==='es'?(o.es||o.en):o.en;}
function dirArrow(deg){
  if(deg==null)return '';
  return '<span class="arrow" style="transform:rotate('+((deg+180)%360)+'deg)" '+
         'aria-hidden="true">&#8593;</span>';
}
function statusLabel(st){const s=D.status_bi[st]||D.status_bi.nodata;return nm(s);}
function why(r){
  if(!r.driver)return '';
  const v=fv(r.unit,r.value);
  let s=T('why_'+r.driver).replace('{v}',v);
  if(r.limit!=null)s+=' · '+T('limit')+' '+fv(r.unit,r.limit);
  return s;
}
function chip(r){
  if(!r)return '<span class="chip notrated"><span class="g">·</span></span>';
  const t=(r.status==='favorable'||r.status==='nodata'||r.status==='notrated')
          ?statusLabel(r.status):why(r);
  return '<span class="chip '+r.status+'" title="'+statusLabel(r.status)+
         (r.driver?(' — '+why(r).replace(/"/g,'&quot;')):'')+'">'+
         '<span class="g" aria-hidden="true">'+(D.glyph[r.status]||'')+'</span>'+
         statusLabel(r.status)+'</span>';
}
function fmtWindow(s,e){
  if(!s||!e)return '';
  const a=Math.floor(Date.parse(s)/1000), b=Math.floor(Date.parse(e)/1000);
  return fmtTZ(a,false)+' – '+fmtTZ(b,false)+' '+tzLabel();
}

function render(){
  const tb=document.getElementById('board');
  let h='<thead><tr>'+
    '<th>'+T('site')+'</th><th>'+T('wind')+'</th><th>'+T('seas')+'</th>'+
    '<th>'+T('period')+'</th>';
  D.classes.forEach(c=>{h+='<th>'+nm(c)+'</th>';});
  h+='</tr></thead><tbody>';
  D.groups.forEach(g=>{
    h+='<tr class="grp"><td colspan="'+(4+D.classes.length)+'">'+nm(g)+'</td></tr>';
    D.sites.filter(s=>s.group===g.key).forEach(s=>{
      const w=s.wind_kt==null?'–':(dirArrow(s.wdir)+' '+fv('kt',s.wind_kt,0)+
        (s.gust_kt!=null?(' <span class="srcline">G '+fv('kt',s.gust_kt,0)+'</span>'):''));
      const sea=s.hs_m==null?'–':(dirArrow(s.dp)+' '+fv('m',s.hs_m,1));
      const tp=s.tp_s==null?'–':fv('s',s.tp_s,0);
      h+='<tr class="site" data-id="'+s.id+'">'+
         '<td><span class="sitename" data-t="'+s.id+'"><span class="caret">▶</span>'+
         nm(s)+'</span></td>'+
         '<td class="num">'+w+'</td><td class="num">'+sea+'</td><td class="num">'+tp+'</td>';
      D.classes.forEach(c=>{
      /* An empty cell reads as "broken". Say plainly that the class is not
         assessed here instead of leaving a hole in the table. */
      h+='<td>'+(s.ratings[c.key]?chip(s.ratings[c.key])
        :'<span class="chip notrated" title="'+T('nrhint')+
         '"><span class="g" aria-hidden="true">\u00b7</span>'+
         statusLabel('notrated')+'</span>')+'</td>';});
      h+='</tr><tr class="drawer" id="d_'+s.id+'" hidden><td colspan="'+
         (4+D.classes.length)+'">'+drawer(s)+'</td></tr>';
    });
  });
  tb.innerHTML=h+'</tbody>';
  tb.querySelectorAll('.sitename').forEach(el=>{
    el.onclick=()=>{
      const row=document.getElementById('d_'+el.dataset.t);
      row.hidden=!row.hidden; el.classList.toggle('open',!row.hidden);
    };
  });
}

function drawer(s){
  const srcs=(a)=>a.length?a.map(x=>'<a href="'+x.link+'">'+x.id+'</a>'+
      (x.down?' <span class="down">('+noteT('offline')+')</span>':'')).join(', '):'–';
  let h='<div class="cols"><div class="col"><h4>'+T('fcst')+'</h4>'+
    '<div class="fcsttext"><b>'+s.zone+'</b> · '+fmtWindow(s.start_utc,s.end_utc)+'<br>'+
    '<span class="srcline">'+(s.period_text||'')+'</span></div>'+
    '<div class="srcline" style="margin-top:.5rem">'+T('src')+': NWS '+D.office+
    ' Coastal Waters Forecast'+(D.cwf_url?' · <a href="'+D.cwf_url+'">'+T('openin')+
    ' ↗</a>':'')+'</div></div>';
  h+='<div class="col"><h4>'+T('detail')+'</h4><div class="srcline">'+
     'Waves: '+srcs(s.obs_wave)+'<br>Wind: '+srcs(s.obs_wind)+'</div>'+
     (s.notes_en?('<div class="srcline" style="margin-top:.4rem">'+
      (L==='es'?s.notes_es:s.notes_en)+'</div>'):'')+'</div></div>';
  if(s.embed_url){
    h+='<div class="embedbox"><div class="bar"><span>'+
       (L==='es'?s.embed_es:s.embed_en)+'</span><span>'+
       '<button class="btn" data-embed="'+s.id+'">'+T('loadtool')+'</button> '+
       '<a class="btn" href="'+s.embed_url+'" target="_blank" rel="noopener">'+
       T('openin')+' ↗</a></span></div>'+
       '<div id="f_'+s.id+'"></div></div>';
  }
  return h;
}

/* Click-to-load: four full applications must not all start downloading just
   because someone opened this page. */
document.addEventListener('click',function(ev){
  const b=ev.target.closest('[data-embed]'); if(!b)return;
  const s=D.sites.find(x=>x.id===b.dataset.embed); if(!s)return;
  const box=document.getElementById('f_'+s.id);
  if(box.querySelector('iframe'))return;
  const f=document.createElement('iframe');
  f.src=s.embed_url; f.loading='lazy'; f.title=s.embed_en;
  f.referrerPolicy='no-referrer-when-downgrade';
  f.setAttribute('sandbox','allow-scripts allow-same-origin allow-popups allow-forms');
  box.appendChild(f); b.disabled=true;
});

function renderNws(){
  const el=document.getElementById('nws');
  let h='<h3>'+T('nwshead')+'</h3>';
  if(!D.alerts.length){
    h+='<div class="srcline">'+T('nwsnone')+'</div>';
  }else{
    D.alerts.forEach(a=>{
      /* NWS wording is reproduced verbatim and never translated. */
      h+='<div class="prod"><b>'+a.event+'</b> — '+(a.sender||'NWS')+
         '<div class="meta">'+(a.zones||[]).join(', ')+
         (a.expires?(' · until '+a.expires):'')+'</div>'+
         (a.headline?'<pre>'+a.headline+'</pre>':'')+'</div>';
    });
  }
  h+='<div class="attrib">Official marine products are issued by the National Weather '+
     'Service and are reproduced here verbatim. <a href="https://www.weather.gov/sju/" '+
     'target="_blank" rel="noopener">weather.gov/sju ↗</a></div>';
  el.innerHTML=h;
}

function onLang(){render();renderNws();}
function onUnits(){render();}
function onTZ(){render();}
render();renderNws();
"""

BODY = """
<div id="nws" class="nws"></div>
<p class="lead">{intro}</p>
<h2>{h2}</h2>
{legend}
<div class="panel" style="padding:0;overflow:hidden">
<table class="board" id="board"></table>
</div>
<p class="srcline" style="margin-top:.7rem">{basis}</p>
"""


def main():
    env = M.load_env()
    problems = M.validate()
    if problems:
        for p in problems:
            print(f"[make_conditions] CONFIG ERROR: {p}")
        return 2
    d = build_payload(env)
    if not d["sites"]:
        print("[make_conditions] no sites")
        return 2

    basis = M.bi(
        f"Operational Suitability is computed from the NWS {d['office']} Coastal Waters "
        f"Forecast for each site's marine zone. Wave period and direction are published "
        f"for roughly the first three days; beyond that, ratings use wind and sea height "
        f"only. Observed buoy and wind-station data are added in the next release.",
        f"La Idoneidad Operacional se calcula a partir del Pronóstico de Aguas Costeras "
        f"del NWS {d['office']} para la zona marina de cada lugar. El periodo y la "
        f"dirección del oleaje se publican para los primeros tres días aproximadamente; "
        f"más allá, la evaluación usa solo viento y altura del oleaje. Los datos "
        f"observados de boyas y estaciones se añaden en la próxima versión.")
    intro = M.bi(
        "Each row is a place; each of the last four columns is a kind of vessel. The colour "
        "is how suitable conditions are <b>for that kind of vessel at that place right now</b>, "
        "judged against the limits on the Methods page. Hover or tap a chip to see which limit "
        "is the binding one. <b>Click a place name</b> to see the forecast behind it and open "
        "the buoy or wind station it came from.",
        "Cada fila es un lugar; cada una de las últimas cuatro columnas es un tipo de "
        "embarcación. El color indica qué tan adecuadas son las condiciones <b>para ese tipo "
        "de embarcación en ese lugar ahora mismo</b>, según los límites de la página Métodos. "
        "Pase el cursor o toque una etiqueta para ver cuál es el límite determinante. "
        "<b>Haga clic en el nombre de un lugar</b> para ver el pronóstico detrás y abrir la "
        "boya o estación de viento de donde proviene.")
    body = BODY.format(h2=M.bi("Operational Suitability", "Idoneidad Operacional"),
                       basis=basis, intro=intro, legend=M.legend())
    scripts = (JS.replace("__DATA__", json.dumps(d, ensure_ascii=False, default=str))
                 .replace("__VARUNIT__", json.dumps(VAR_UNIT)))
    i18n = "const I18N = " + json.dumps(I18N, ensure_ascii=False) + ";" 
    gen = M.bi(f"Generated {d['generated_utc'][:16]}Z from NWS {d['office']} CWF issued "
               f"{(d['cwf_issued'] or '?')[:16]}Z. Refreshes every 10 minutes.",
               f"Generado {d['generated_utc'][:16]}Z del CWF del NWS {d['office']} emitido "
               f"{(d['cwf_issued'] or '?')[:16]}Z. Se actualiza cada 10 minutos.")
    html = M.page_shell("conditions_now.html", "Conditions now", "Condiciones ahora",
                        "CariCOOS Maritime Dashboard", "Tablero Marítimo CariCOOS",
                        body, extra_css=CSS, scripts=scripts, generated=gen,
                        i18n=i18n)
    out = os.path.join(M.WEBOUT, "conditions_now.html")
    M.atomic_write_text(html, out)
    print(f"[make_conditions] wrote {out} ({len(html):,} bytes, {len(d['sites'])} sites)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
