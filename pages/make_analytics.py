#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/analytics.html - which parts of the dashboard people use.

Reads the raw event log written by the /event endpoint (chatbot/local_server.py,
and the Worker once it is deployed) and renders it as a small usage page.

Two deliberate choices:

  * The RAW events are baked into the page and every number is computed in the
    browser. That is what makes the date-range filter real: one filter row
    re-renders the hero, the tiles, all four charts and the tables against the
    same slice, so the numbers can never disagree with each other.
  * The page is NOT in NAV. It answers an operator's question, not a mariner's,
    and the board must stay a board. It is reachable by URL only.

There is no identity in any of this - no cookie, no visitor id, no session, no
free text. See marlib.analytics_js() for exactly what the browser sends.
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402

# Keep the page small enough to open on a phone. At a few hundred events a day
# this is months of history; past it the oldest events fall off the front.
MAX_EVENTS = 20000

EVENT_NAMES = {
    "page_view":     ("Page opened", "Página abierta"),
    "location_open": ("Location expanded", "Lugar desplegado"),
    "tool_embed":    ("Tool shown in page", "Herramienta mostrada en la página"),
    "tool_open_tab": ("Tool opened in a new tab", "Herramienta abierta en pestaña nueva"),
    "toggle_lang":   ("Language switched", "Idioma cambiado"),
    "toggle_units":  ("Units switched", "Unidades cambiadas"),
    "toggle_tz":     ("Time zone switched", "Zona horaria cambiada"),
}

PAGE_NAMES = {
    "index.html":        ("Conditions now", "Condiciones ahora"),
    "marine_zones.html": ("NWS forecast", "Pronóstico NWS"),
    "tools.html":        ("Tools", "Herramientas"),
    "analytics.html":    ("Usage", "Uso"),
}

TOOL_NAMES = {
    "buoys":     ("Ocean Buoys Hub", "Centro de Boyas"),
    "mesonet":   ("Wind Stations Hub", "Centro de Estaciones de Viento"),
    "modviewer": ("Model Viewer", "Visor de Modelos"),
    "classic":   ("Model Viewer (classic)", "Visor de Modelos (clásico)"),
}
TOOL_ENV = {"buoys": "BUOYS_HUB_URL", "mesonet": "MESONET_HUB_URL",
            "modviewer": "MODVIEWER_URL", "classic": "CLASSIC_VIEWER_URL"}

I18N = {
    "title": {"en": "Usage &middot; CariCOOS Maritime", "es": "Uso &middot; CariCOOS Maritime"},
    "range": {"en": "Range", "es": "Periodo"},
    "r7": {"en": "Last 7 days", "es": "Últimos 7 días"},
    "r30": {"en": "Last 30 days", "es": "Últimos 30 días"},
    "rall": {"en": "All", "es": "Todo"},
    "events": {"en": "events", "es": "eventos"},
    "recorded": {"en": "interactions recorded", "es": "interacciones registradas"},
    "since": {"en": "First recorded {a} &middot; last {b}",
              "es": "Primera el {a} &middot; última el {b}"},
    "k_pages": {"en": "Pages opened", "es": "Páginas abiertas"},
    "k_sites": {"en": "Location actions", "es": "Acciones en lugares"},
    "k_tools": {"en": "Tool actions", "es": "Acciones en herramientas"},
    "k_days": {"en": "Days with activity", "es": "Días con actividad"},
    "c_day": {"en": "Activity by day", "es": "Actividad por día"},
    "c_day_s": {"en": "Every recorded interaction, bucketed by day in the selected time zone.",
                "es": "Cada interacción registrada, agrupada por día en la zona horaria elegida."},
    "c_site": {"en": "Locations people open", "es": "Lugares que la gente abre"},
    "c_site_s": {"en": "Counts a row expanded on the board and a tool loaded for that "
                       "location. This is the question this page exists to answer.",
                 "es": "Cuenta una fila desplegada en el tablero y una herramienta cargada "
                       "para ese lugar. Es la pregunta que esta página existe para responder."},
    "c_tool": {"en": "Tools people use", "es": "Herramientas que la gente usa"},
    "c_tool_s": {"en": "Shown inside the page or opened in a new tab.",
                 "es": "Mostradas dentro de la página o abiertas en pestaña nueva."},
    "c_page": {"en": "Pages people open", "es": "Páginas que la gente abre"},
    "c_page_s": {"en": "One count each time the page is loaded.",
                 "es": "Un conteo cada vez que se carga la página."},
    "numbers": {"en": "Show the numbers", "es": "Ver los números"},
    "th_what": {"en": "What", "es": "Qué"},
    "th_n": {"en": "Count", "es": "Conteo"},
    "th_share": {"en": "Share", "es": "Porcentaje"},
    "th_day": {"en": "Day", "es": "Día"},
    "th_time": {"en": "Time", "es": "Hora"},
    "th_page": {"en": "Page", "es": "Página"},
    "th_event": {"en": "Interaction", "es": "Interacción"},
    "th_detail": {"en": "Detail", "es": "Detalle"},
    "s_break": {"en": "Every interaction", "es": "Todas las interacciones"},
    "s_break_s": {"en": "The raw event names, before any grouping above.",
                  "es": "Los nombres de evento en crudo, antes de agrupar arriba."},
    "s_lang": {"en": "Language chosen", "es": "Idioma elegido"},
    "s_recent": {"en": "Most recent 25", "es": "Las 25 más recientes"},
    "nodata": {"en": "Nothing recorded in this range yet.",
               "es": "Nada registrado en este periodo todavía."},
    "empty_h": {"en": "No usage recorded yet", "es": "Todavía no hay uso registrado"},
    "empty_on": {"en": "Recording is on. Open the board, click a few locations and "
                       "tools, then rebuild this page.",
                 "es": "El registro está activo. Abra el tablero, haga clic en algunos "
                       "lugares y herramientas, y luego reconstruya esta página."},
    "empty_off": {"en": "Recording is off: ANALYTICS_URL is not set in "
                        "config/machine.env, so the pages send nothing.",
                  "es": "El registro está apagado: ANALYTICS_URL no está definido en "
                        "config/machine.env, así que las páginas no envían nada."},
    "privacy": {"en": "No cookies, no visitor id, no session and no typed text is "
                      "recorded &mdash; only the page, the interaction, a short label "
                      "and the language.",
                "es": "No se registran cookies, ni identificador de visitante, ni sesión, "
                      "ni texto escrito &mdash; solo la página, la interacción, una "
                      "etiqueta corta y el idioma."},
    "stale": {"en": "Could not refresh &mdash; showing the last data received",
              "es": "No se pudo actualizar &mdash; mostrando los últimos datos recibidos"},
}

CSS = r"""
.hero{font:600 3.1rem "Source Sans 3",system-ui,sans-serif;line-height:1;margin:.5rem 0 .15rem}
.herosub{color:var(--ink2);font-size:.9rem;margin:0 0 1.2rem}
.filters{display:flex;gap:.4rem;align-items:center;flex-wrap:wrap;margin:.6rem 0 1rem}
.filters .fl{font-size:.82rem;color:var(--ink2);margin-right:.25rem}
.fbtn{font:600 .8rem "Source Sans 3",sans-serif;border:1px solid var(--line);
  background:var(--btn);color:var(--ink);padding:.26rem .8rem;border-radius:999px;
  cursor:pointer;min-height:1.9rem}
.fbtn[aria-pressed="true"]{background:var(--btn-on);color:var(--btn-on-ink);border-color:var(--btn-on)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:.7rem;margin:0 0 1.5rem}
@media(max-width:720px){.kpis{grid-template-columns:repeat(2,1fr)}.hero{font-size:2.4rem}}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:.7rem .85rem}
.kpi .k{font-size:.8rem;color:var(--ink2)}
.kpi .v{font:600 1.6rem "Source Sans 3",system-ui,sans-serif;margin-top:.1rem}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:.95rem 1rem 1.05rem;margin:0 0 1.1rem}
.card h3{margin:0;font:700 1rem "Archivo",sans-serif}
.card .cs{color:var(--ink2);font-size:.84rem;margin:.2rem 0 .9rem;max-width:60ch}
.empty{color:var(--ink2);font-size:.88rem;margin:.3rem 0 0}

/* --- horizontal bars: one series, one hue; length carries the magnitude ------ */
.brow{display:grid;grid-template-columns:minmax(6rem,12rem) 1fr;gap:.7rem;align-items:center;
  padding:.18rem .3rem;border-radius:5px;outline:none}
.brow:hover,.brow:focus-visible{background:var(--sel)}
.blab{font-size:.86rem;overflow-wrap:anywhere}
/* The right gutter is what keeps the value OUTSIDE the bar even at full scale:
   the longest bar stops 3.6rem short of the edge, so its label always has room.
   Putting it inside a full-width bar would mean white on --s1, which is under
   4.5:1 for text this size in both themes. */
.btrack{position:relative;height:24px;display:flex;align-items:center;padding-right:3.6rem}
.bfill{position:relative;height:14px;background:var(--s1);border-radius:0 4px 4px 0;min-width:2px}
.bval{position:absolute;left:100%;margin-left:.5rem;top:50%;transform:translateY(-50%);
  white-space:nowrap;font:600 .8rem "Source Sans 3",sans-serif;
  font-variant-numeric:tabular-nums;color:var(--ink2)}

/* --- columns ---------------------------------------------------------------- */
.plot{position:relative;padding-top:1.35rem}
.gmax{position:absolute;left:0;right:0;top:1.3rem;border-top:1px solid var(--grid)}
.cols{display:flex;align-items:flex-end;gap:2px;height:118px;border-bottom:1px solid var(--line)}
.col{flex:1 1 0;min-width:0;height:100%;display:flex;flex-direction:column;
  justify-content:flex-end;align-items:center;position:relative;outline:none}
.col:hover .cfill,.col:focus-visible .cfill{filter:brightness(1.14)}
.cfill{width:100%;max-width:24px;background:var(--s1);border-radius:4px 4px 0 0}
.cap{position:absolute;top:-1.15rem;left:-50%;right:-50%;text-align:center;
  font:600 .72rem "Source Sans 3",sans-serif;color:var(--ink2);font-variant-numeric:tabular-nums}
.xax{display:flex;gap:2px;margin-top:.35rem}
.xt{flex:1 1 0;min-width:0;text-align:center;font-size:.68rem;color:var(--ink2);white-space:nowrap}

/* --- table view (the twin of every chart above) ----------------------------- */
details.tv{margin-top:.8rem;border-top:1px solid var(--line);padding-top:.5rem}
details.tv summary{cursor:pointer;font-size:.82rem;color:var(--ink2)}
table.an{border-collapse:collapse;width:100%;font-size:.86rem;margin-top:.55rem}
table.an th,table.an td{border-bottom:1px solid var(--line);padding:.32rem .5rem;text-align:left}
table.an th{font:700 .72rem "Archivo",sans-serif;color:var(--ink2);text-transform:uppercase;
  letter-spacing:.05em;white-space:nowrap}
table.an td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.an td.d{color:var(--ink2);overflow-wrap:anywhere}

#vtip{position:fixed;z-index:60;pointer-events:none;display:none;max-width:17rem;
  background:var(--tip-bg);border:1px solid var(--tip-edge);border-radius:6px;
  padding:.4rem .6rem;box-shadow:0 4px 16px rgba(0,0,0,.2)}
#vtip .tv{font:600 1.02rem "Source Sans 3",sans-serif;font-variant-numeric:tabular-nums}
#vtip .tl{color:var(--ink2);font-size:.8rem;margin-top:.1rem}
#vtip .tk{display:inline-block;width:14px;height:2px;border-radius:1px;background:var(--s1);
  vertical-align:middle;margin-right:.45rem}
#wrap.stale{opacity:.55}
.note{color:var(--ink2);font-size:.82rem;margin:.9rem 0 0}
"""

JS = r"""
const D = __DATA__;
let RANGE = 7;                      /* days; 0 = everything */

const fnum = n => n.toLocaleString(L === 'es' ? 'es-PR' : 'en-US');
function el(t, c, x){const e=document.createElement(t); if(c)e.className=c;
  if(x!=null)e.textContent=x; return e;}
function nm(dict, key){const d = D[dict] && D[dict][key];
  return d ? (L === 'es' ? d.es : d.en) : key;}

/* ---- slicing ------------------------------------------------------------- */
function inRange(){
  if(!RANGE) return D.ev;
  const cut = Date.now()/1000 - RANGE*86400;
  return D.ev.filter(e => e[0] >= cut);
}
function tally(rows, keyfn){
  const m = new Map();
  rows.forEach(r => {const k = keyfn(r); if(k==null) return; m.set(k, (m.get(k)||0)+1);});
  return [...m.entries()].sort((a,b) => b[1]-a[1] || String(a[0]).localeCompare(String(b[0])));
}
/* A tool_open_tab carries the href, so resolve it back to the tool it points at. */
function toolKey(e){
  if(e[2] === 'tool_embed' && D.tools[e[3]]) return e[3];
  if(e[2] === 'tool_open_tab'){
    const u = e[3] || '';
    for(const p of D.toolurl) if(u.indexOf(p[0]) === 0) return p[1];
    return null;
  }
  return null;
}
/* On the board a tool_embed's label is the SITE, not the tool - loading the buoy
   hub for Ponce is interest in Ponce. Both count here; the raw names are in the
   "Every interaction" table below, so nothing is hidden by the grouping. */
const siteKey = e => (D.sites[e[3]] ? e[3] : null);

function dayBuckets(ev, days){
  const off = TZOFF()*1000;
  const m = new Map();
  ev.forEach(e => m.set(new Date(e[0]*1000+off).toISOString().slice(0,10),
                        (m.get(new Date(e[0]*1000+off).toISOString().slice(0,10))||0)+1));
  const today = new Date(Date.now()+off).toISOString().slice(0,10);
  const base = Date.parse(today+'T00:00:00Z');
  const out = [];
  for(let i=days-1; i>=0; i--){
    const d = new Date(base - i*86400000).toISOString().slice(0,10);
    out.push({d: d, n: m.get(d)||0});
  }
  return out;
}

/* ---- tooltip ------------------------------------------------------------- */
const TIP = document.getElementById('vtip');
function showTip(ev, value, label){
  TIP.textContent = '';
  const v = el('div','tv'); v.appendChild(el('span','tk')); 
  v.appendChild(document.createTextNode(fnum(value)+' '+T('events')));
  TIP.appendChild(v);
  TIP.appendChild(el('div','tl', label));
  TIP.style.display = 'block';
  const r = TIP.getBoundingClientRect();
  let x = (ev.clientX!==undefined ? ev.clientX : 0) + 14, y = (ev.clientY!==undefined ? ev.clientY : 0) + 16;
  if(ev.type === 'focus'){const b = ev.target.getBoundingClientRect(); x = b.left; y = b.bottom + 6;}
  TIP.style.left = Math.max(6, Math.min(x, innerWidth - r.width - 6)) + 'px';
  TIP.style.top  = Math.max(6, Math.min(y, innerHeight - r.height - 6)) + 'px';
}
function hideTip(){TIP.style.display = 'none';}
function hookTip(node, value, label){
  node.tabIndex = 0;
  node.addEventListener('pointermove', e => showTip(e, value, label));
  node.addEventListener('pointerleave', hideTip);
  node.addEventListener('focus', e => showTip(e, value, label));
  node.addEventListener('blur', hideTip);
}

/* ---- charts -------------------------------------------------------------- */
function hbars(host, rows){
  host.textContent = '';
  if(!rows.length){host.appendChild(el('p','empty', T('nodata'))); return;}
  const max = rows[0].n;
  rows.forEach(r => {
    const row = el('div','brow');
    row.appendChild(el('div','blab', r.label));
    const track = el('div','btrack');
    const fill = el('div','bfill');
    fill.style.width = Math.max(2, r.n/max*100)+'%';
    /* The value is a child of the fill, not of the track, so it sits exactly at
       the bar's tip whatever the width - no second percentage to keep in step. */
    fill.appendChild(el('span','bval', fnum(r.n)));
    track.appendChild(fill);
    row.appendChild(track);
    hookTip(row, r.n, r.label);
    host.appendChild(row);
  });
}

function columns(host, days){
  host.textContent = '';
  const max = Math.max(1, ...days.map(d => d.n));
  const plot = el('div','plot');
  /* The hairline alone carries the scale: the tallest column is always direct-
     labelled below, so a tick label on it too would print the same number twice. */
  plot.appendChild(el('div','gmax'));
  const cols = el('div','cols');
  let capped = false;
  days.forEach(d => {
    const c = el('div','col');
    if(d.n > 0){
      const f = el('div','cfill');
      f.style.height = (d.n/max*100)+'%';
      c.appendChild(f);
      /* Label the extreme only - a number over every column is noise, and the
         table below carries the rest. */
      if(d.n === max && !capped){c.appendChild(el('div','cap', fnum(d.n))); capped = true;}
    }
    hookTip(c, d.n, dayLabel(d.d));
    cols.appendChild(c);
  });
  plot.appendChild(cols);
  const ax = el('div','xax');
  const every = Math.ceil(days.length/7);
  days.forEach((d,i) => {
    const t = el('div','xt');
    if(i === days.length-1 || (days.length-1-i) % every === 0) t.textContent = d.d.slice(5).replace('-','/');
    ax.appendChild(t);
  });
  plot.appendChild(ax);
  host.appendChild(plot);
}

function dayLabel(iso){
  const d = new Date(iso+'T12:00:00Z');
  return d.toLocaleDateString(L === 'es' ? 'es-PR' : 'en-US',
                              {weekday:'short', month:'short', day:'numeric', timeZone:'UTC'});
}

/* ---- tables (the twin of every chart) ------------------------------------ */
function table(host, head, rows){
  host.textContent = '';
  const t = el('table','an'), thead = el('thead'), htr = el('tr');
  head.forEach(h => {const th = el('th', h[1]||'', h[0]); htr.appendChild(th);});
  thead.appendChild(htr); t.appendChild(thead);
  const tb = el('tbody');
  rows.forEach(r => {
    const tr = el('tr');
    r.forEach((c,i) => tr.appendChild(el('td', head[i][1]||'', c)));
    tb.appendChild(tr);
  });
  t.appendChild(tb); host.appendChild(t);
}
function countTable(host, rows, total, whatHdr){
  if(!rows.length){host.textContent = ''; host.appendChild(el('p','empty', T('nodata'))); return;}
  table(host, [[whatHdr||T('th_what'),''], [T('th_n'),'n'], [T('th_share'),'n']],
        rows.map(r => [r.label, fnum(r.n),
                       total ? Math.round(r.n/total*100)+'%' : '-']));
}

/* ---- render -------------------------------------------------------------- */
function render(){
  const ev = inRange();
  document.getElementById('wrap').hidden = (D.ev.length === 0);
  document.getElementById('none').hidden = (D.ev.length > 0);
  if(!D.ev.length){
    document.getElementById('nonetext').innerHTML = D.analytics_on ? T('empty_on') : T('empty_off');
    return;
  }

  const days = dayBuckets(ev, RANGE || 14);
  const pages = tally(ev.filter(e => e[2] === 'page_view'), e => e[1])
                  .map(p => ({label: nm('pages', p[0]), n: p[1]}));
  const sites = tally(ev.filter(siteKey), siteKey)
                  .map(p => ({label: nm('sites', p[0]), n: p[1]}));
  const tools = tally(ev, toolKey).map(p => ({label: nm('tools', p[0]), n: p[1]}));
  const evs   = tally(ev, e => e[2]).map(p => ({label: nm('events', p[0]), n: p[1]}));
  const langs = tally(ev, e => e[4] || '?')
                  .map(p => ({label: p[0] === 'es' ? 'Español' : (p[0] === 'en' ? 'English' : p[0]),
                              n: p[1]}));

  document.getElementById('hero').textContent = fnum(ev.length);
  document.getElementById('herosub').textContent = T('recorded');
  document.getElementById('kv_pages').textContent =
    fnum(ev.filter(e => e[2] === 'page_view').length);
  document.getElementById('kv_sites').textContent = fnum(ev.filter(siteKey).length);
  document.getElementById('kv_tools').textContent =
    fnum(ev.filter(e => toolKey(e) !== null).length);
  document.getElementById('kv_days').textContent = fnum(days.filter(d => d.n > 0).length);

  columns(document.getElementById('c_day'), days);
  table(document.getElementById('t_day'), [[T('th_day'),''], [T('th_n'),'n']],
        days.map(d => [dayLabel(d.d), fnum(d.n)]));
  hbars(document.getElementById('c_site'), sites);
  countTable(document.getElementById('t_site'), sites, ev.length);
  hbars(document.getElementById('c_tool'), tools);
  countTable(document.getElementById('t_tool'), tools, ev.length);
  hbars(document.getElementById('c_page'), pages);
  countTable(document.getElementById('t_page'), pages, ev.length);
  countTable(document.getElementById('t_break'), evs, ev.length, T('th_event'));
  countTable(document.getElementById('t_lang'), langs, ev.length);

  const recent = ev.slice(-25).reverse();
  table(document.getElementById('t_recent'),
        [[T('th_time'),''], [T('th_page'),''], [T('th_event'),''], [T('th_detail'),'d']],
        recent.map(e => [fmtTZ(e[0], true) + ' ' + tzLabel().slice(0,3),
                         nm('pages', e[1]), nm('events', e[2]),
                         e[3] ? (D.sites[e[3]] ? nm('sites', e[3])
                                : (D.tools[e[3]] ? nm('tools', e[3]) : e[3])) : '—']));

  const f = D.first ? fmtTZ(D.first, true) : '?', l = D.last ? fmtTZ(D.last, true) : '?';
  document.getElementById('span').innerHTML =
    T('since').replace('{a}', f).replace('{b}', l) + ' &middot; ' + tzLabel();
  hideTip();
}

document.querySelectorAll('.fbtn').forEach(b => b.onclick = () => {
  RANGE = +b.dataset.r;
  document.querySelectorAll('.fbtn').forEach(x =>
    x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
  render();
});

function onLang(){render();}
function onTZ(){render();}

/* The log grows while someone is clicking around, so pull the payload again
   rather than making them reload. The frame is held at reduced opacity during a
   failed pull instead of blanking - a stale number with a note beats no page. */
setInterval(function(){
  fetch('analytics.json?v=' + Date.now(), {cache: 'no-store'})
    .then(r => r.ok ? r.json() : Promise.reject())
    .then(function(j){
      D.ev = j.ev; D.first = j.first; D.last = j.last; D.analytics_on = j.analytics_on;
      document.getElementById('wrap').classList.remove('stale');
      document.getElementById('stalenote').hidden = true;
      render();
    })
    .catch(function(){
      document.getElementById('wrap').classList.add('stale');
      document.getElementById('stalenote').hidden = false;
    });
}, 60000);

render();
"""


def _load_events(path):
    """Read logs/events.jsonl -> compact rows, newest last. Never raises.

    A malformed line is skipped rather than failing the build: this log is
    appended to by a live HTTP handler, so a truncated final line is a normal
    thing to find, not a reason for the page to disappear.
    """
    rows, skipped = [], 0
    if not os.path.exists(path):
        return rows, skipped, False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
                t = dt.datetime.fromisoformat(o["received_utc"])
                if t.tzinfo is None:
                    t = t.replace(tzinfo=dt.timezone.utc)
                rows.append([int(t.timestamp()), str(o.get("page") or ""),
                             str(o.get("event") or ""),
                             (str(o["label"]) if o.get("label") else None),
                             str(o.get("lang") or "")])
            except Exception:
                skipped += 1
    rows.sort(key=lambda r: r[0])
    return rows[-MAX_EVENTS:], skipped, True


def _short(path):
    """Repo-relative when it is inside the repo, absolute when it is not.

    os.path.relpath alone prints ../../../.. for a log somewhere else on the
    machine, which is unreadable on the page.
    """
    rel = os.path.relpath(path, M.BASE)
    return path if rel.startswith("..") else rel


def main():
    env = M.load_env()
    log = os.environ.get("ANALYTICS_LOG") or os.path.join(M.LOGS, "events.jsonl")
    rows, skipped, found = _load_events(log)
    en, es, _g, _z, _d, _o = M.site_maps()

    d = {"ev": rows,
         "first": rows[0][0] if rows else None,
         "last": rows[-1][0] if rows else None,
         "analytics_on": bool((env.get("ANALYTICS_URL") or "").strip()),
         "sites": {k: {"en": en[k], "es": es[k]} for k in en},
         "tools": {k: {"en": v[0], "es": v[1]} for k, v in TOOL_NAMES.items()},
         "toolurl": sorted(((env.get(TOOL_ENV[k]) or "").strip(), k)
                           for k in TOOL_NAMES if (env.get(TOOL_ENV[k]) or "").strip()),
         "pages": {k: {"en": v[0], "es": v[1]} for k, v in PAGE_NAMES.items()},
         "events": {k: {"en": v[0], "es": v[1]} for k, v in EVENT_NAMES.items()},
         }

    def card(cid, tkey, skey):
        return (f'<section class="card"><h3 data-i18n="{tkey}">{M.bi(*_t(tkey))}</h3>'
                f'<p class="cs" data-i18n="{skey}">{M.bi(*_t(skey))}</p>'
                f'<div id="c_{cid}"></div>'
                f'<details class="tv"><summary data-i18n="numbers">{M.bi(*_t("numbers"))}'
                f'</summary><div id="t_{cid}"></div></details></section>')

    def _t(key):
        return I18N[key]["en"], I18N[key]["es"]

    def kpi(cid, key):
        return (f'<div class="kpi"><div class="k" data-i18n="{key}">{M.bi(*_t(key))}</div>'
                f'<div class="v" id="kv_{cid}">&ndash;</div></div>')

    body = f"""
<div id="none" hidden>
  <section class="card"><h3 data-i18n="empty_h">{M.bi(*_t("empty_h"))}</h3>
  <p class="cs" id="nonetext"></p>
  <p class="cs"><code>{M.bi("Log", "Registro")}: {_short(log)}</code></p></section>
</div>

<div id="wrap">
  <div class="filters">
    <span class="fl" data-i18n="range">{M.bi(*_t("range"))}</span>
    <button class="fbtn" type="button" data-r="7" aria-pressed="true"
            data-i18n="r7">{M.bi(*_t("r7"))}</button>
    <button class="fbtn" type="button" data-r="30" aria-pressed="false"
            data-i18n="r30">{M.bi(*_t("r30"))}</button>
    <button class="fbtn" type="button" data-r="0" aria-pressed="false"
            data-i18n="rall">{M.bi(*_t("rall"))}</button>
  </div>

  <div class="hero" id="hero">&ndash;</div>
  <p class="herosub"><span id="herosub"></span> &middot; <span id="span"></span></p>
  <p class="herosub" id="stalenote" hidden data-i18n="stale">{M.bi(*_t("stale"))}</p>

  <div class="kpis">
    {kpi("pages", "k_pages")}{kpi("sites", "k_sites")}
    {kpi("tools", "k_tools")}{kpi("days", "k_days")}
  </div>

  {card("site", "c_site", "c_site_s")}
  {card("day", "c_day", "c_day_s")}
  {card("tool", "c_tool", "c_tool_s")}
  {card("page", "c_page", "c_page_s")}

  <section class="card">
    <h3 data-i18n="s_break">{M.bi(*_t("s_break"))}</h3>
    <p class="cs" data-i18n="s_break_s">{M.bi(*_t("s_break_s"))}</p>
    <div id="t_break"></div>
    <h3 style="margin-top:1.3rem" data-i18n="s_lang">{M.bi(*_t("s_lang"))}</h3>
    <div id="t_lang"></div>
    <h3 style="margin-top:1.3rem" data-i18n="s_recent">{M.bi(*_t("s_recent"))}</h3>
    <div id="t_recent"></div>
  </section>

  <p class="note" data-i18n="privacy">{M.bi(*_t("privacy"))}</p>
</div>
<div id="vtip" role="status" aria-live="polite"></div>
"""
    gen = M.bi(
        f"Read from {_short(log)}"
        f"{f' &mdash; {skipped} unreadable line(s) skipped' if skipped else ''}. "
        f"{len(rows):,} interactions. Page not linked from the navigation.",
        f"Leído de {_short(log)}"
        f"{f' &mdash; {skipped} línea(s) ilegible(s) omitida(s)' if skipped else ''}. "
        f"{len(rows):,} interacciones. Página no enlazada desde la navegación.")

    scripts = JS.replace("__DATA__", json.dumps(d, ensure_ascii=False, separators=(",", ":")))
    i18n = "const I18N = " + json.dumps(I18N, ensure_ascii=False) + ";"
    html_out = M.page_shell("analytics.html", "Usage", "Uso",
                            "Which parts of the dashboard people open",
                            "Qué partes del tablero abre la gente",
                            body, extra_css=CSS, scripts=scripts, generated=gen, i18n=i18n)
    M.atomic_write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                        os.path.join(M.WEBOUT, "analytics.json"))
    out_path = os.path.join(M.WEBOUT, "analytics.html")
    M.atomic_write_text(html_out, out_path)
    print(f"[make_analytics] wrote {out_path} ({len(html_out):,} bytes, "
          f"{len(rows)} events, log {'found' if found else 'MISSING'}, {skipped} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
