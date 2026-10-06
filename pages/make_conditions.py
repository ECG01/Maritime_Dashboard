#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/index.html - the board, and the whole landing page.

Built for a fast read, in this order:

  1. Pick your vessel class ONCE, at the top. The previous version showed four
     verdict columns per row, which meant scanning a 14x4 grid to answer a
     one-vessel question. Now you choose the class and every row carries a
     single, large verdict.
  2. A headline that states the answer in words before any table: either "all
     clear" or the names of the places that need attention, as links.
  3. Then the detail, grouped by coast so a mariner can find their own water.

The class choice is remembered (localStorage), so a regular arrives at their
own answer immediately.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402
from engine import cwf_parse as C       # noqa: E402
from engine import ratings as R         # noqa: E402

I18N = {
    "site": {"en": "Location", "es": "Lugar"},
    "wind": {"en": "Wind from", "es": "Viento de"},
    "seas": {"en": "Seas from", "es": "Oleaje de"},
    "period": {"en": "Wave period", "es": "Periodo"},
    "gust": {"en": "Gust", "es": "Ráfaga"},
    "tide": {"en": "Next tide", "es": "Próxima marea"},
    "obsfrom": {"en": "measured \u00b7 {s}", "es": "medido \u00b7 {s}"},
    "fcfrom": {"en": "NWS forecast", "es": "pronóstico NWS"},
    "obshelp": {"en": "Measured by station {s}, {a} min ago",
                "es": "Medido por la estación {s}, hace {a} min"},
    "fchelp": {"en": "From the NWS zone forecast \u2014 no fresh instrument covers this",
               "es": "Del pronóstico de zona del NWS \u2014 ningún instrumento reciente lo cubre"},
    "measured": {"en": "Measured", "es": "Medido"},
    "updated": {"en": "Updated just now", "es": "Actualizado ahora"},
    "offline": {"en": "Could not reach the server \u2014 showing the last data received",
                "es": "No se pudo contactar el servidor \u2014 mostrando los últimos datos recibidos"},
    "forecast": {"en": "Forecast", "es": "Pronóstico"},
    "tidehelp": {"en": "The next high or low water, and the sea level at that point "
                       "above MLLW. This is water depth, not wave height.",
                 "es": "La próxima pleamar o bajamar, y el nivel del mar en ese momento "
                       "sobre MLLW. Es altura de agua, no altura de ola."},
    "hi": {"en": "High", "es": "Pleamar"}, "lo": {"en": "Low", "es": "Bajamar"},
    # The observed level and the high/low times come from DIFFERENT CO-OPS
    # products: one is what the gauge reads, the other is astronomical
    # prediction. Labelled separately on purpose - showing a prediction as a
    # measurement is the quiet kind of error that matters for clearance.
    "tideobs": {"en": "measured {v}", "es": "medido {v}"},
    "tidepred": {"en": "predicted {v}", "es": "previsto {v}"},
    "tideobshelp": {"en": "Water level measured by the gauge right now, above MLLW",
                    "es": "Nivel del agua medido por el mareógrafo ahora, sobre MLLW"},
    "tidepredhelp": {"en": "Predicted water level at that high or low, above MLLW. This "
                           "station has no real-time gauge.",
                     "es": "Nivel de agua previsto en esa pleamar o bajamar, sobre MLLW. "
                           "Esta estación no tiene mareógrafo en tiempo real."},
    "notide": {"en": "No tide station for this location",
               "es": "Sin estación de marea para este lugar"},
    "asof": {"en": "Data as of", "es": "Datos al"},
    "when": {"en": "Data date / time", "es": "Fecha / hora del dato"},
    "whenhelp": {"en": "The forecast period these numbers describe. Identical across "
                       "locations, because the NWS issues one set of periods for all "
                       "Puerto Rico and USVI marine zones.",
                 "es": "El periodo de pronóstico que describen estos números. Es igual en "
                       "todos los lugares, porque el NWS emite un mismo juego de periodos "
                       "para todas las zonas marinas de Puerto Rico y las Islas Vírgenes."},
    "fc_issued": {"en": "NWS forecast issued", "es": "Pronóstico NWS emitido"},
    "fc_valid": {"en": "covering", "es": "cubre"},
    "tide_read": {"en": "Tide read", "es": "Marea consultada"},
    "obs_read": {"en": "Instruments read", "es": "Instrumentos leídos"},
    "obs_n": {"en": "{n} of {t} locations measured", "es": "{n} de {t} lugares medidos"},
    "page_built": {"en": "Page built", "es": "Página generada"},
    "ago_min": {"en": "{n} min ago", "es": "hace {n} min"},
    "ago_hr": {"en": "{n} h ago", "es": "hace {n} h"},
    "ago_day": {"en": "{n} d ago", "es": "hace {n} d"},
    "stalewarn": {"en": "This page has not refreshed recently \u2014 the numbers below may "
                        "be out of date. Check the forecast link before relying on them.",
                  "es": "Esta página no se ha actualizado recientemente: los números pueden "
                        "estar desfasados. Verifique el enlace del pronóstico antes de usarlos."},
    # A dash in the gust column means NWS did not publish a gust for this period,
    # NOT that the wind is steady. The CWF only mentions gusts when they are
    # notable - currently about a third of periods - so saying "0" there would be
    # inventing data.
    "nogust": {"en": "Not published for this period", "es": "No publicada para este periodo"},
    "allclear": {"en": "All clear for {c}", "es": "Todo despejado para {c}"},
    "allclearsub": {"en": "All {n} locations are within every published limit.",
                    "es": "Los {n} lugares están dentro de todos los límites publicados."},
    "attention": {"en": "{k} of {n} locations need attention for {c}",
                  "es": "{k} de {n} lugares requieren atención para {c}"},
    "nodatafor": {"en": "No usable data for {c} right now.",
                  "es": "No hay datos utilizables para {c} ahora mismo."},
    "notrated": {"en": "{c} is not assessed at {n} of these locations.",
                 "es": "{c} no se evalúa en {n} de estos lugares."},
    "openin": {"en": "Open in new tab", "es": "Abrir en pestaña nueva"},
    "loadtool": {"en": "Show the interactive tool", "es": "Mostrar la herramienta"},
    "fcst": {"en": "Forecast for this zone, as issued by NWS",
             "es": "Pronóstico para esta zona, emitido por el NWS"},
    "stations": {"en": "Stations behind this location",
                 "es": "Estaciones tras este lugar"},
    "nwsnone": {"en": "No NWS marine warnings, watches or advisories in effect.",
                "es": "Sin advertencias, vigilancias ni avisos marinos del NWS vigentes."},
    "nwsother": {"en": "Other NWS products for Puerto Rico and the USVI",
                 "es": "Otros productos del NWS para Puerto Rico y las Islas Vírgenes"},
    "nwshead": {"en": "NWS products in effect", "es": "Productos del NWS vigentes"},
    "tap": {"en": "Tap a row for the forecast behind it",
            "es": "Toque una fila para ver el pronóstico detrás"},
    "why_wind_kt": {"en": "wind {v}", "es": "viento {v}"},
    "why_gust_kt": {"en": "gusts {v}", "es": "ráfagas {v}"},
    "why_hs_m": {"en": "seas {v}", "es": "oleaje {v}"},
    "why_lp_swell_m": {"en": "long-period swell {v}", "es": "marejada larga {v}"},
    "why_hs_beam_m": {"en": "beam seas {v}", "es": "oleaje de través {v}"},
}
VAR_UNIT = {"wind_kt": "kt", "gust_kt": "kt", "hs_m": "m", "steepness": "-",
            "lp_swell_m": "m", "hs_beam_m": "m", "roll_ratio": "-", "wind_vs_curr": "kt"}

CSS = r"""
.pick{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;margin:.2rem 0 1rem}
.pick .lbl{font:600 .9rem "Source Sans 3",sans-serif;color:var(--ink2);margin-right:.2rem}
.pick .btn{font:600 .95rem "Source Sans 3",sans-serif;border:1.5px solid var(--line);
  background:var(--panel);color:var(--ink);padding:.5rem 1.05rem;border-radius:999px;
  cursor:pointer;transition:background .12s,border-color .12s}
.pick .btn:hover{border-color:var(--teal)}
.pick .btn[aria-pressed="true"]{background:var(--btn-on);color:var(--btn-on-ink);
  border-color:var(--btn-on)}


table.board{width:100%;border-collapse:collapse;background:var(--panel);
  border:1px solid var(--line);border-radius:10px;overflow:hidden}
table.board th{background:var(--controls);font:600 .74rem "Archivo",sans-serif;
  letter-spacing:.05em;text-transform:uppercase;color:var(--ink2);padding:.55rem .7rem;
  text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
table.board td{padding:.6rem .7rem;border-bottom:1px solid var(--grid);vertical-align:middle}
table.board tr.grp td{background:var(--controls);font:700 .78rem "Archivo",sans-serif;
  letter-spacing:.06em;text-transform:uppercase;color:var(--navy);padding:.4rem .7rem}
table.board tr.site{cursor:pointer}
table.board tr.site:hover{background:var(--sel)}
table.board tr.site td:first-child{border-left:5px solid transparent;font-weight:600}
tr.site.favorable td:first-child{border-left-color:var(--ok)}
tr.site.marginal td:first-child{border-left-color:var(--warn)}
tr.site.unfavorable td:first-child{border-left-color:var(--flag)}
tr.site.nodata td:first-child,tr.site.notrated td:first-child{border-left-color:var(--line)}
.vd{display:flex;flex-direction:column;gap:.15rem;align-items:flex-start}
.vd .why{font-size:.84rem;color:var(--ink2)}
.num{font-variant-numeric:tabular-nums;white-space:nowrap;font-size:.98rem}
.arrow{display:inline-block;color:var(--ink2)}
.g2{color:var(--ink2);font-size:.82rem}
.stp{display:block;font-variant-numeric:tabular-nums}
td.when{white-space:nowrap}
td.when .stp{font-weight:600}
.sw{display:block;font-size:.8rem}
.sw.ok{color:var(--ok)}
.sw.warn{color:var(--warn)}
.sw.bad{color:var(--flag)}
.sw.obs{color:var(--ok)}
.sw.fc{color:var(--ink2);font-style:italic}
.hint{color:var(--ink2);font-size:.86rem;margin:.5rem 0 0}
.stamp{margin:0 0 .2rem}
.pollnote{font:600 .84rem "Source Sans 3",sans-serif;min-height:1.1rem;margin:0 0 .7rem;
  padding:0 .2rem;transition:color .2s}
.pollnote.ok{color:var(--ok)}
.pollnote.bad{color:var(--flag)}
.stamp-in{display:flex;gap:.2rem 1.3rem;flex-wrap:wrap;align-items:baseline;
  background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:.5rem .85rem;font-size:.88rem}
.stamp-in .lab{font:700 .7rem "Archivo",sans-serif;letter-spacing:.07em;
  text-transform:uppercase;color:var(--ink2)}
.stamp-in .it{font-variant-numeric:tabular-nums}
.stamp-in .it b{font-weight:600;color:var(--ink2);font-size:.82rem}
.stamp-in .tzl{margin-left:auto;font:600 .78rem "Archivo",sans-serif;color:var(--teal)}
.stamp-in.stale{border-color:var(--warn);border-left:5px solid var(--warn)}
.stamp-warn{margin-top:.35rem;padding:.5rem .85rem;border-radius:8px;
  background:var(--warn);color:var(--warn-ink);font-size:.88rem}
@media (max-width:760px){.stamp-in .tzl{margin-left:0}}

.drawer td{background:var(--surface);padding:.9rem 1rem}
.drawer h4{margin:0 0 .3rem;font:700 .74rem "Archivo",sans-serif;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ink2)}
.drawer .cols{display:flex;gap:1.3rem;flex-wrap:wrap}
.drawer .col{flex:1 1 300px;min-width:250px}
.fcsttext{font-size:.92rem;line-height:1.5}
.embedbox{margin-top:.7rem;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.embedbox .bar{display:flex;align-items:center;justify-content:space-between;gap:.6rem;
  padding:.45rem .7rem;background:var(--controls);font-size:.88rem}
.embedbox iframe{display:block;width:100%;height:460px;border:0;background:var(--surface)}
.btn2{font:600 .85rem "Source Sans 3",sans-serif;border:1px solid var(--line);
  background:var(--btn);color:var(--ink);padding:.3rem .8rem;border-radius:5px;cursor:pointer;
  text-decoration:none;display:inline-block}
.btn2:hover{background:var(--sel)}
.lead{max-width:66ch}

/* phone: the table becomes stacked cards, because a 6-column table on a
   flybridge is unreadable */
@media (max-width:760px){
  table.board thead{display:none}
  table.board,table.board tbody,table.board tr,table.board td{display:block;width:100%}
  table.board tr.site{border-bottom:1px solid var(--line);padding:.2rem 0}
  table.board tr.site td{border-bottom:0;padding:.25rem .8rem}
  table.board tr.site td:first-child{font-size:1.05rem;padding-top:.6rem}
  table.board td.m::before{content:attr(data-l) " ";color:var(--ink2);font-size:.8rem;
    text-transform:uppercase;letter-spacing:.04em}
  .head h2{font-size:1.15rem}
}
"""

JS = r"""
let D = __DATA__;

function T(k){const d=I18N[k];return d?(d[L]||d.en||k):k;}
function nm(o){return L==='es'?(o.es||o.en):o.en;}
/* Next high or low, with the observed level underneath when a real gauge exists.
   Many PR/USVI stations are prediction-only subordinate stations with no gauge at
   all, so the observed line is genuinely optional and its absence is not an error. */
function tideCell(t){
  if(!t)return '<span class="g2" title="'+T('notide')+'">–</span>';
  let h='';
  if(t.next){
    const when=Math.floor(Date.parse(t.next.t)/1000);
    /* Just the clock time: the next high or low is always within about twelve
       hours, so the date is noise in a column people scan. */
    const hhmm=fmtTZ(when,false).slice(-5);
    h+='<span class="stp">'+(t.next.type==='H'?T('hi'):T('lo'))+' '+hhmm+'</span>';
  }
  if(t.observed!=null)
    h+='<span class="g2 sw" title="'+T('tideobshelp')+'">'+
       T('tideobs').replace('{v}',fv('m',t.observed,1))+'</span>';
  else if(t.next)
    h+='<span class="g2 sw" title="'+T('tidepredhelp')+'">'+
       T('tidepred').replace('{v}',fv('m',t.next.v,1))+'</span>';
  return h||'–';
}
const MON={en:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
           es:['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']};
/* When the row's numbers are from. If anything on this row was measured, show the
   INSTRUMENT's own observation time - that is the honest answer for a board headed
   "Conditions now". Only a row with no fresh instrument falls back to the forecast
   period it describes. */
function whenCell(s){
  const obsT=s.prov?s.prov.obs_utc:null;
  const iso=obsT||s.start_utc;
  if(!iso)return '–';
  const d=new Date((Math.floor(Date.parse(iso)/1000)+TZOFF())*1000);
  const day=d.getUTCDate(), mon=(MON[L]||MON.en)[d.getUTCMonth()];
  const a=Math.floor(Date.parse(iso)/1000);
  let sub;
  if(obsT){
    sub='<span class="g2 sw obs">'+T('measured')+' '+fmtTZ(a,false).slice(-5)+'</span>';
  }else{
    const bt=s.end_utc?Math.floor(Date.parse(s.end_utc)/1000):null;
    sub='<span class="g2 sw fc">'+T('forecast')+' '+fmtTZ(a,false).slice(-5)+
        (bt?('–'+fmtTZ(bt,false).slice(-5)):'')+'</span>';
  }
  return '<span class="stp">'+day+' '+mon+'</span>'+sub;
}
function dirArrow(deg){
  if(deg==null)return '';
  return '<span class="arrow" style="display:inline-block;transform:rotate('+
         ((deg+180)%360)+'deg)" aria-hidden="true">&#8593;</span> ';
}

function ago(iso){
  if(!iso)return '';
  const m=Math.max(0,(Date.now()-Date.parse(iso))/60000);
  if(m<90)  return T('ago_min').replace('{n}',Math.round(m));
  if(m<2880)return T('ago_hr').replace('{n}',Math.round(m/60));
  return T('ago_day').replace('{n}',Math.round(m/1440));
}
function clock(iso){return iso?fmtTZ(Math.floor(Date.parse(iso)/1000),false).slice(-5):'\u2013';}

/* The receipt: when every number on this page is from. Rendered client-side so
   it follows the UTC/AST toggle like everything else - a timestamp frozen in UTC
   while the rest of the page reads AST is worse than no timestamp. */
function renderStamp(){
  const gen=D.generated_utc;
  const mins=gen?(Date.now()-Date.parse(gen))/60000:0;
  const stale=mins>45;
  let h='<div class="stamp-in'+(stale?' stale':'')+'">'+
        '<span class="lab">'+T('asof')+'</span>';
  h+='<span class="it"><b>'+T('fc_issued')+'</b> '+clock(D.cwf_issued)+
     (D.valid_from?(' \u00b7 '+T('fc_valid')+' '+clock(D.valid_from)+'\u2013'+
      clock(D.valid_to)):'')+'</span>';
  if(D.obs_fetched)
    h+='<span class="it"><b>'+T('obs_read')+'</b> '+clock(D.obs_fetched)+
       ' <span class="g2">('+T('obs_n').replace('{n}',D.obs_count)
       .replace('{t}',D.sites.length)+')</span></span>';
  if(D.tides_fetched)
    h+='<span class="it"><b>'+T('tide_read')+'</b> '+clock(D.tides_fetched)+'</span>';
  h+='<span class="it"><b>'+T('page_built')+'</b> '+clock(gen)+
     ' <span class="g2">('+ago(gen)+')</span></span>';
  h+='<span class="tzl">'+tzLabel()+'</span></div>';
  if(stale)h+='<div class="stamp-warn">'+T('stalewarn')+'</div>';
  return h;
}

function render(){
  document.getElementById('stamp').innerHTML=renderStamp();
  let h='<thead><tr>'+
        '<th title="'+T('whenhelp')+'">'+T('when')+'</th>'+
        '<th>'+T('site')+'</th>'+
        '<th>'+T('wind')+'</th><th>'+T('gust')+'</th><th>'+T('seas')+'</th>'+
        '<th>'+T('period')+'</th>'+
        '<th title="'+T('tidehelp')+'">'+T('tide')+'</th></tr></thead><tbody>';
  D.groups.forEach(g=>{
    h+='<tr class="grp"><td colspan="7">'+nm(g)+'</td></tr>';
    D.sites.filter(s=>s.group===g.key).forEach(s=>{
      /* Say where each group of numbers came from, in the cell itself. Wind and
         waves resolve independently, so one row can legitimately mix a measured
         wind with a forecast sea. */
      const pw=s.prov?s.prov.wind:null, pv=s.prov?s.prov.wave:null;
      const tag=pr=>{
        if(!pr)return '';
        return pr.observed
          ? '<span class="g2 sw obs" title="'+T('obshelp').replace('{s}',pr.src)
              .replace('{a}',Math.round(pr.age_min))+'">'+
              T('obsfrom').replace('{s}',pr.src)+'</span>'
          : '<span class="g2 sw fc" title="'+T('fchelp')+'">'+T('fcfrom')+'</span>';
      };
      const w=s.wind_kt==null?'–':(dirArrow(s.wdir)+fv('kt',s.wind_kt,0))+tag(pw);
      const gust=s.gust_kt==null
        ? '<span class="g2" title="'+T('nogust')+'">–</span>'
        : fv('kt',s.gust_kt,0);
      const tide=tideCell(s.tide);
      const when=whenCell(s);
      const sea=s.hs_m==null?'–':(dirArrow(s.dp)+fv('m',s.hs_m,1))+tag(pv);
      const tp=s.tp_s==null?'–':fv('s',s.tp_s,0);
      h+='<tr class="site" id="r_'+s.id+'" data-t="'+s.id+'">'+
         '<td class="m when" data-l="'+T('when')+'">'+when+'</td>'+
         '<td>'+nm(s)+'</td>'+
         '<td class="num m" data-l="'+T('wind')+'">'+w+'</td>'+
         '<td class="num m" data-l="'+T('gust')+'">'+gust+'</td>'+
         '<td class="num m" data-l="'+T('seas')+'">'+sea+'</td>'+
         '<td class="num m" data-l="'+T('period')+'">'+tp+'</td>'+
         '<td class="num m" data-l="'+T('tide')+'">'+tide+'</td></tr>'+
         '<tr class="drawer" id="d_'+s.id+'" hidden><td colspan="7">'+drawer(s)+'</td></tr>';
    });
  });
  document.getElementById('board').innerHTML=h+'</tbody>';
  document.querySelectorAll('tr.site').forEach(tr=>{
    tr.onclick=()=>{const d=document.getElementById('d_'+tr.dataset.t);d.hidden=!d.hidden;};
  });
}

function drawer(s){
  const srcs=a=>a.length?a.map(x=>'<a href="'+x.link+'">'+x.id+'</a>'+
      (x.down?' <span style="color:var(--flag)">●</span>':'')).join(', '):'–';
  let h='<div class="cols"><div class="col"><h4>'+T('fcst')+'</h4>'+
    '<div class="fcsttext"><b>'+s.zone+'</b> · '+(s.period_label||'')+'<br>'+
    '<span class="g2">'+(s.period_text||'')+'</span></div></div>'+
    '<div class="col"><h4>'+T('stations')+'</h4><div class="g2">'+
    T('seas')+': '+srcs(s.obs_wave)+'<br>'+T('wind')+': '+srcs(s.obs_wind)+'</div>'+
    (s.notes_en?('<div class="g2" style="margin-top:.4rem">'+
      (L==='es'?s.notes_es:s.notes_en)+'</div>'):'')+'</div></div>';
  if(s.embed_url){
    h+='<div class="embedbox"><div class="bar"><span>'+
       (L==='es'?s.embed_es:s.embed_en)+'</span><span>'+
       '<button class="btn2" data-embed="'+s.id+'">'+T('loadtool')+'</button> '+
       '<a class="btn2" href="'+s.embed_url+'" target="_blank" rel="noopener">'+
       T('openin')+' ↗</a></span></div><div id="f_'+s.id+'"></div></div>';
  }
  return h;
}

document.addEventListener('click',function(ev){
  const b=ev.target.closest('[data-embed]');
  if(!b)return;
  ev.stopPropagation();
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
  /* Drop anything past its expiry. The page can sit open for hours and it
     auto-refreshes, but a product that lapses between rebuilds would otherwise
     keep showing - and a stale advisory on screen is as wrong as a missing one. */
  const now=Date.now();
  const live=D.alerts.filter(a=>!a.expires || Date.parse(a.expires)>now);
  const marine=live.filter(a=>a.scope==='marine');
  const other=live.filter(a=>a.scope!=='marine');
  /* NWS wording verbatim, never translated. Coastal products get their own
     group rather than being mixed in: a rip current statement is issued against
     land zones and matters to a swimmer, not a vessel offshore - but it must not
     read as though a marine product were in effect either. Showing only marine
     products is what hid a live "life-threatening rip currents" statement while
     this panel said nothing was in effect. */
  const prod=a=>'<div class="prod"><b>'+a.event+'</b> \u2014 '+(a.sender||'NWS')+
    '<div class="meta">'+(a.zones||[]).join(', ')+
    (a.expires?(' \u00b7 until '+a.expires):'')+'</div>'+
    (a.headline?'<pre>'+a.headline+'</pre>':'')+
    (a.description?'<pre class="desc">'+a.description+'</pre>':'')+'</div>';
  let h='<h3>'+T('nwshead')+'</h3>';
  if(!marine.length){h+='<div class="g2">'+T('nwsnone')+'</div>';}
  else{marine.forEach(a=>{h+=prod(a);});}
  if(other.length){
    h+='<div class="coastal"><div class="ch">'+T('nwsother')+'</div>';
    other.forEach(a=>{h+=prod(a);});
    h+='</div>';
  }
  h+='<div class="attrib">Issued by the National Weather Service, reproduced verbatim. '+
     '<a href="https://www.weather.gov/sju/" target="_blank" rel="noopener">'+
     'weather.gov/sju ↗</a></div>';
  el.innerHTML=h;
}
/* Auto-refresh. A board headed "Conditions now" that silently freezes the moment
   someone leaves it open is the worst version of this page: it looks current and
   is not. Every POLL_MS the page pulls board.json and, if the build timestamp
   changed, swaps the data in and redraws.

   Two things it deliberately does NOT do:
   - It never redraws while an embedded CARICOOS tool is loaded in an open drawer.
     Rebuilding the table would tear down that iframe and throw away whatever map
     the user had panned to. In that case only the provenance bar is updated, and
     the full redraw waits until the drawer is closed.
   - It never blanks anything on failure. A failed poll leaves the current data on
     screen; the bar keeps ageing and turns amber on its own, which is the honest
     signal that what you are reading is getting old. */
const POLL_MS = 180000;

function openDrawers(){
  return [...document.querySelectorAll('tr.drawer')].filter(d=>!d.hidden)
         .map(d=>d.id.slice(2));
}
function reopen(ids){
  ids.forEach(id=>{const d=document.getElementById('d_'+id); if(d)d.hidden=false;});
}
function flash(msg, bad){
  const el=document.getElementById('pollnote');
  if(!el)return;
  el.textContent=msg;
  el.className='pollnote'+(bad?' bad':' ok');
  clearTimeout(flash._t);
  flash._t=setTimeout(()=>{el.textContent='';el.className='pollnote';}, bad?20000:6000);
}

async function poll(){
  try{
    const r=await fetch('board.json?t='+Date.now(), {cache:'no-store'});
    if(!r.ok)throw new Error(r.status);
    const fresh=await r.json();
    if(fresh.generated_utc===D.generated_utc){
      document.getElementById('stamp').innerHTML=renderStamp();
      return;
    }
    D=fresh;
    if(document.querySelector('.embedbox iframe')){
      /* a tool is loaded - refresh only the bar, redraw once it is closed */
      document.getElementById('stamp').innerHTML=renderStamp();
      return;
    }
    const open=openDrawers();
    render(); renderNws(); reopen(open);
    flash(T('updated'), false);
  }catch(e){
    flash(T('offline'), true);
    document.getElementById('stamp').innerHTML=renderStamp();
  }
}
setInterval(poll, POLL_MS);
/* Someone coming back to a tab left open for hours should not have to wait for
   the next tick to find out the numbers moved. */
document.addEventListener('visibilitychange', ()=>{ if(!document.hidden) poll(); });

function onLang(){render();renderNws();}
function onUnits(){render();}
function onTZ(){render();}
render();renderNws();
"""


WAVE_KEYS = ("hs_m", "tp_s", "dp_deg")
WIND_KEYS = ("wind_kt", "gust_kt", "wdir_deg")


def pick_obs(site, col, keys, obs):
    """First source in the site's priority list that is fresh and has the data.

    sites.tsv lists obs_wave / obs_wind in priority order. A stale station is
    skipped rather than used, which is the whole point of the list: VI1 has been
    dead since 2026-07 and sits first for the USVI sites, so without this they
    would show three-month-old seas as current.
    """
    for sid in site.get(col, []):
        r = obs.get(sid)
        if not r or r.get("stale"):
            continue
        if all(r.get(k) is None for k in keys):
            continue
        return sid, r
    return None, None


def merge_obs(site, fc, obs):
    """Observed values where we have them, forecast for the rest.

    Returns (values, provenance). Waves and wind are resolved as GROUPS, never
    field by field: mixing an observed wave height with a forecast wave period
    would produce a steepness that describes no real sea state.
    """
    vals = {k: fc.get(k) for k in
            ("hs_m", "tp_s", "dp_deg", "wind_kt", "gust_kt", "wdir_deg")}
    prov = {"wave": {"observed": False, "src": None, "age_min": None},
            "wind": {"observed": False, "src": None, "age_min": None},
            "obs_utc": None}

    for col, keys, tag in (("obs_wave", WAVE_KEYS, "wave"), ("obs_wind", WIND_KEYS, "wind")):
        sid, r = pick_obs(site, col, keys, obs)
        if not r:
            continue
        for k in keys:
            if r.get(k) is not None:
                vals[k] = r[k]
        prov[tag] = {"observed": True, "src": sid, "age_min": r.get("age_min")}
        if r.get("obs_utc") and (prov["obs_utc"] is None or r["obs_utc"] > prov["obs_utc"]):
            prov["obs_utc"] = r["obs_utc"]
    return vals, prov


def tide_for(site, tides):
    """The tide readout for one site, or None when it has no tidal station.

    Only the NEXT high/low is carried to the page - a mariner glancing at a board
    wants "High 18:42", not a table of four. The full list stays in the payload's
    source file for anything later.
    """
    sid = site.get("tide")
    st = tides.get(sid) if sid else None
    if not st:
        return None
    nxt = st["predictions"][0] if st.get("predictions") else None
    if nxt is None and st.get("observed") is None:
        return None
    return {"station": sid, "observed": st.get("observed"), "next": nxt}


def main():
    env = M.load_env()
    problems = M.validate()
    if problems:
        for p in problems:
            print(f"[make_conditions] CONFIG ERROR: {p}")
        return 2

    cwf = M.read_json("nws", "cwf.json") or {}
    tides = (M.read_json("tides", "tides.json") or {}).get("stations", {})
    obs = (M.read_json("obs", "obs.json") or {}).get("stations", {})
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
        fc = {k: p.get(k) for k in ("hs_m", "tp_s", "dp_deg", "wind_kt", "gust_kt", "wdir_deg")}
        raw, prov = merge_obs(s, fc, obs)
        sample = R.prepare_sample(raw, kind=s["kind"])
        out.append({
            "id": s["site_id"], "en": s["name_en"], "es": s["name_es"],
            "group": s["group"], "zone": s["zone"],
            "notes_en": s["notes"], "notes_es": M.es_note(s["notes"]),
            "wind_kt": raw.get("wind_kt"), "gust_kt": raw.get("gust_kt"),
            "wdir": raw.get("wdir_deg"), "hs_m": raw.get("hs_m"),
            "tp_s": raw.get("tp_s"), "dp": raw.get("dp_deg"),
            "prov": prov,
            "tide": tide_for(s, tides),
            "period_label": (p.get("label") or "").title(), "period_text": p.get("text"),
            "start_utc": p.get("start_utc"), "end_utc": p.get("end_utc"),
            "embed_url": embed_url.get(s["embed"], ""),
            "embed_en": embed_name.get(s["embed"], ("", ""))[0],
            "embed_es": embed_name.get(s["embed"], ("", ""))[1],
            "obs_wave": [{"id": i, "link": srcs[i]["link"], "down": srcs[i]["down"]}
                         for i in s["obs_wave"] if i in srcs],
            "obs_wind": [{"id": i, "link": srcs[i]["link"], "down": srcs[i]["down"]}
                         for i in s["obs_wind"] if i in srcs],
        })

    groups = [{"key": g, "en": M.GROUP_BI[g][0], "es": M.GROUP_BI[g][1]}
              for g in M.GROUP_ORDER if any(x["group"] == g for x in out)]
    d = {"generated_utc": M.utcnow().isoformat(), "cwf_issued": cwf.get("issued_utc"),
         "office": cwf.get("office", "SJU"), "groups": groups, "sites": out,
         # Provenance, so the board can show WHEN each number is from. A mariner
         # needs to know whether they are reading a fresh forecast or one from
         # before a front went through, and the footer alone is too easy to miss.
         "cwf_fetched": cwf.get("fetched_utc"),
         "tides_fetched": (M.read_json("tides", "tides.json") or {}).get("fetched_utc"),
         "obs_fetched": (M.read_json("obs", "obs.json") or {}).get("fetched_utc"),
         "obs_count": sum(1 for x in out if x["prov"]["wave"]["observed"]
                          or x["prov"]["wind"]["observed"]),
         "valid_from": (out[0].get("start_utc") if out else None),
         "valid_to": (out[0].get("end_utc") if out else None),
         "alerts": alerts.get("alerts", []),
         }

    body = f"""
<div id="stamp" class="stamp"></div>
<div id="pollnote" class="pollnote"></div>
<div id="nws" class="nws"></div>
<table class="board" id="board"></table>
<p class="hint">{M.bi("Tap a row to see the forecast behind it and open the CARICOOS tool "
                      "for that location.",
                      "Toque una fila para ver el pronóstico detrás y abrir la herramienta "
                      "CARICOOS de ese lugar.")}</p>
"""
    gen = M.bi(
        f"From the NWS {d['office']} Coastal Waters Forecast issued "
        f"{(d['cwf_issued'] or '?')[:16]}Z. Refreshes every 10 minutes.",
        f"Del Pronóstico de Aguas Costeras del NWS {d['office']} emitido "
        f"{(d['cwf_issued'] or '?')[:16]}Z. Se actualiza cada 10 minutos.")
    scripts = JS.replace("__DATA__", json.dumps(d, ensure_ascii=False, default=str))
    i18n = "const I18N = " + json.dumps(I18N, ensure_ascii=False) + ";"
    html_out = M.page_shell("index.html", "Conditions now", "Condiciones ahora",
                            "Puerto Rico &amp; the U.S. Virgin Islands",
                            "Puerto Rico y las Islas Vírgenes",
                            body, extra_css=CSS, scripts=scripts, generated=gen, i18n=i18n)
    # The same payload, written separately so a page left open can pull a fresh
    # copy without a full reload. It stays inlined in the HTML as well, so the
    # first paint needs no second request and the page still works from a file://
    # copy or with no network.
    M.atomic_write_text(json.dumps(d, ensure_ascii=False, default=str),
                        os.path.join(M.WEBOUT, "board.json"))
    out_path = os.path.join(M.WEBOUT, "index.html")
    M.atomic_write_text(html_out, out_path)
    measured = sum(1 for x in out if x["prov"]["wave"]["observed"]
                   or x["prov"]["wind"]["observed"])
    print(f"[make_conditions] wrote {out_path} ({len(html_out):,} bytes, {len(out)} sites, "
          f"{measured} measured)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
