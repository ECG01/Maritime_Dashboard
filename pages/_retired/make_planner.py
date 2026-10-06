#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate web/out/planner.html - the five-day departure-window grid.

Columns are the NWS forecast periods themselves (12-hourly), not an interpolated
3-hourly grid: the source publishes 12-hour periods and pretending otherwise would
imply a precision the forecast does not have.

Wave period and direction are only published for roughly the first three days, so
later columns are rated on wind and sea height alone. The page says so rather than
letting the later columns look equally well-informed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import marlib as M                      # noqa: E402
from engine import cwf_parse as C       # noqa: E402
from engine import ratings as R         # noqa: E402
from engine import windows as W         # noqa: E402

VAR_UNIT = {"wind_kt": "kt", "gust_kt": "kt", "hs_m": "m", "steepness": "-",
            "lp_swell_m": "m", "hs_beam_m": "m", "roll_ratio": "-", "wind_vs_curr": "kt"}

I18N = {
    "title": {"en": "Planner", "es": "Planificador"},
    "site": {"en": "Location", "es": "Lugar"},
    "forclass": {"en": "Showing", "es": "Mostrando"},
    "best": {"en": "Best departure windows", "es": "Mejores ventanas de salida"},
    "nowin": {"en": "No window of {h} hours or more is Favorable in the next five days "
                    "for this class.",
              "es": "No hay ninguna ventana de {h} horas o más Favorable en los próximos "
                    "cinco días para esta clase."},
    "relaxed": {"en": "No fully Favorable window was found, so these include Marginal "
                      "conditions.",
                "es": "No se encontró ninguna ventana totalmente Favorable, así que estas "
                      "incluyen condiciones Marginales."},
    "hrs": {"en": "{h} h", "es": "{h} h"},
    "limit": {"en": "limit", "es": "límite"},
    "nrhint": {"en": "This vessel class is not assessed at this location",
               "es": "Esta clase de embarcación no se evalúa en este lugar"},
    "nowave": {"en": "Wind and sea height only (no wave period published this far out)",
               "es": "Solo viento y altura del oleaje (no se publica periodo a este plazo)"},
    "why_wind_kt": {"en": "wind {v}", "es": "viento {v}"},
    "why_gust_kt": {"en": "gusts {v}", "es": "ráfagas {v}"},
    "why_hs_m": {"en": "seas {v}", "es": "oleaje {v}"},
    "why_steepness": {"en": "steep seas {v}", "es": "oleaje escarpado {v}"},
    "why_lp_swell_m": {"en": "long-period swell {v}", "es": "marejada de periodo largo {v}"},
    "why_hs_beam_m": {"en": "beam seas {v}", "es": "oleaje de través {v}"},
    "why_roll_ratio": {"en": "roll resonance {v}", "es": "resonancia de balance {v}"},
    "why_wind_vs_curr": {"en": "wind against current {v}", "es": "viento contra corriente {v}"},
}

CSS = r"""
.classbar{display:flex;gap:.4rem;flex-wrap:wrap;margin:.2rem 0 1rem;align-items:center}
.classbar .btn{font:600 .85rem "Source Sans 3",sans-serif;border:1px solid var(--line);
  background:var(--btn);color:var(--ink);padding:.35rem .8rem;border-radius:999px;cursor:pointer}
.classbar .btn[aria-pressed="true"]{background:var(--btn-on);color:var(--btn-on-ink);
  border-color:var(--btn-on)}
.gridwrap{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px}
table.pg{border-collapse:collapse;width:100%;min-width:760px}
table.pg th{background:var(--controls);font:600 .72rem "Archivo",sans-serif;letter-spacing:.03em;
  color:var(--ink2);padding:.4rem .35rem;border-bottom:1px solid var(--line);
  text-align:center;white-space:nowrap}
table.pg th.day{text-transform:uppercase}
table.pg th.rowh,table.pg td.rowh{position:sticky;left:0;background:var(--panel);
  text-align:left;padding:.4rem .6rem;border-right:1px solid var(--line);
  font-weight:600;font-size:.88rem;white-space:nowrap;z-index:1}
table.pg th.rowh{background:var(--controls)}
table.pg td{padding:2px;border-bottom:1px solid var(--grid)}
table.pg td .cell{cursor:default}
table.pg tr.grp td{background:var(--controls);font:700 .78rem "Archivo",sans-serif;
  letter-spacing:.05em;text-transform:uppercase;color:var(--navy);padding:.35rem .6rem}
.nowave{opacity:.62}
.wins{margin:1.1rem 0 0}
.win{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--ok);
  border-radius:6px;padding:.55rem .8rem;margin-bottom:.45rem;font-size:.93rem}
.win.relaxed{border-left-color:var(--warn)}
.win b{font-variant-numeric:tabular-nums}
.win .sitename{font-weight:700}
.note{color:var(--ink2);font-size:.9rem;max-width:64ch}
.lead{max-width:64ch}
"""

JS = r"""
const D = __DATA__;
/* Default to the class rated at the MOST locations (small craft: every site).
   Defaulting to the first class alphabetically meant opening on "Commercial ship",
   which is only assessed at ports and passages - so two thirds of the grid was
   "not rated" dots and the page looked broken on arrival. */
let CLS = D.default_class;
try{const s=localStorage.getItem('maritime_class'); if(s&&D.classes.some(c=>c.key===s))CLS=s;}catch(e){}

function T(k){const d=I18N[k];return d?(d[L]||d.en||k):k;}
function nm(o){return L==='es'?(o.es||o.en):o.en;}
function statusLabel(st){return nm(D.status_bi[st]||D.status_bi.nodata);}
function why(r){
  if(!r||!r.driver)return '';
  let s=T('why_'+r.driver).replace('{v}',fv(r.unit,r.value));
  if(r.limit!=null)s+=' · '+T('limit')+' '+fv(r.unit,r.limit);
  return s;
}
function colLabel(p){
  const a=Math.floor(Date.parse(p.start_utc)/1000);
  return fmtTZ(a,false);
}

function render(){
  /* column headers: the forecast's own periods, labelled in the active zone */
  let h='<thead><tr><th class="rowh">'+T('site')+'</th>';
  D.cols.forEach(c=>{
    h+='<th class="day"><div>'+nm(c.label)+'</div>'+
       '<div style="font-weight:400;font-size:.68rem">'+colLabel(c)+'</div></th>';
  });
  h+='</tr></thead><tbody>';
  D.groups.forEach(g=>{
    h+='<tr class="grp"><td colspan="'+(1+D.cols.length)+'">'+nm(g)+'</td></tr>';
    D.sites.filter(s=>s.group===g.key).forEach(s=>{
      h+='<tr><td class="rowh">'+nm(s)+'</td>';
      D.cols.forEach((c,i)=>{
        const r=(s.series[CLS]||[])[i];
        if(!r){h+='<td><div class="cell notrated" title="'+statusLabel('notrated')+
                 '">·</div></td>';return;}
        const t=statusLabel(r.status)+(r.driver?(' — '+why(r)):'')+
                (c.nowave?(' · '+T('nowave')):'');
        h+='<td><div class="cell '+r.status+(c.nowave?' nowave':'')+
           '" title="'+t.replace(/"/g,'&quot;')+'">'+(D.glyph[r.status]||'')+'</div></td>';
      });
      h+='</tr>';
    });
  });
  document.getElementById('pg').innerHTML=h+'</tbody>';
  document.querySelectorAll('.classbar .btn').forEach(b=>{
    b.setAttribute('aria-pressed', b.dataset.cls===CLS ? 'true':'false');
  });
  renderWins();
}

function renderWins(){
  const el=document.getElementById('wins');
  let h='<h2>'+T('best')+'</h2>';
  let any=false, anyRelaxed=false;
  D.sites.forEach(s=>{
    const w=(s.windows[CLS]||{});
    if(!w.list||!w.list.length)return;
    any=true; if(w.relaxed)anyRelaxed=true;
    const top=w.list[0];
    const a=Math.floor(Date.parse(top.start_utc)/1000), b=Math.floor(Date.parse(top.end_utc)/1000);
    h+='<div class="win'+(w.relaxed?' relaxed':'')+'">'+
       '<span class="sitename">'+nm(s)+'</span> &mdash; <b>'+fmtTZ(a,false)+
       '</b> → <b>'+fmtTZ(b,false)+'</b> '+tzLabel()+
       ' · '+T('hrs').replace('{h}',Math.round(top.hours))+
       ' · '+statusLabel(top.worst)+'</div>';
  });
  if(!any)h+='<p class="note">'+T('nowin').replace('{h}',D.min_hours)+'</p>';
  else if(anyRelaxed)h+='<p class="note">'+T('relaxed')+'</p>';
  el.innerHTML=h;
}

document.addEventListener('click',function(ev){
  const b=ev.target.closest('.classbar .btn'); if(!b)return;
  CLS=b.dataset.cls;
  try{localStorage.setItem('maritime_class',CLS);}catch(e){}
  render();
});
function onLang(){render();}
function onUnits(){render();}
function onTZ(){render();}
render();
"""


def main():
    env = M.load_env()
    problems = M.validate()
    if problems:
        for p in problems:
            print(f"[make_planner] CONFIG ERROR: {p}")
        return 2

    cwf = M.read_json("nws", "cwf.json") or {}
    ths = R.load_thresholds()
    sites = M.load_sites()
    min_hours = 12.0

    # the column axis comes from the zone with the most periods, so every row lines up
    ref_zone = max(({s["zone"] for s in sites}),
                   key=lambda z: len(C.frames(cwf, z)), default=None)
    ref = C.frames(cwf, ref_zone) if ref_zone else []
    cols = [{"label": {"en": p["label"].title(), "es": _es_label(p["label"])},
             "start_utc": p["start_utc"], "end_utc": p["end_utc"],
             "nowave": p.get("tp_s") is None} for p in ref]

    out_sites = []
    for s in sites:
        fr = C.frames(cwf, s["zone"])
        series, wins = {}, {}
        for c in s["classes"]:
            row, rated = [], []
            for i, col in enumerate(cols):
                p = fr[i] if i < len(fr) else None
                if p is None:
                    row.append(None)
                    continue
                raw = {k: p.get(k) for k in
                       ("hs_m", "tp_s", "dp_deg", "wind_kt", "gust_kt", "wdir_deg")}
                r = R.rate(R.prepare_sample(raw, kind=s["kind"]), c, s["kind"], ths)
                row.append({"status": r.status, "driver": r.driver, "value": r.value,
                            "limit": r.limit, "unit": VAR_UNIT.get(r.driver, "-")})
                rated.append({"start_utc": p["start_utc"], "end_utc": p["end_utc"],
                              "status": r.status})
            series[c] = row
            lst, relaxed = W.best_windows(rated, min_hours=min_hours, limit=2)
            wins[c] = {"list": lst, "relaxed": relaxed}
        out_sites.append({"id": s["site_id"], "en": s["name_en"], "es": s["name_es"],
                          "group": s["group"], "series": series, "windows": wins})

    groups = [{"key": g, "en": M.GROUP_BI[g][0], "es": M.GROUP_BI[g][1]}
              for g in M.GROUP_ORDER if any(x["group"] == g for x in out_sites)]
    d = {"generated_utc": M.utcnow().isoformat(), "cwf_issued": cwf.get("issued_utc"),
         "office": cwf.get("office", "SJU"), "cols": cols, "groups": groups,
         "sites": out_sites, "min_hours": int(min_hours),
         "default_class": max(M.CLASSES,
                              key=lambda c: sum(1 for s in sites if c in s["classes"])),
         "classes": [{"key": c, "en": M.CLASS_BI[c][0], "es": M.CLASS_BI[c][1]}
                     for c in M.CLASSES],
         "status_bi": {k: {"en": v[0], "es": v[1]} for k, v in M.STATUS_BI.items()},
         "glyph": M.STATUS_GLYPH}

    classbar = ('<div class="classbar"><span class="note">'
                + M.bi("Showing", "Mostrando") + ":</span>"
                + "".join(f'<button class="btn" data-cls="{c}" aria-pressed="false">'
                          f'{M.bi(*M.CLASS_BI[c])}</button>' for c in M.CLASSES)
                + "</div>")

    lead = M.bi(
        "Each column is one National Weather Service forecast period. Pick a vessel class and "
        "read across: the colour is the Operational Suitability for that class at that time, "
        "and hovering a cell says what drives it. Faded columns are beyond the range where the "
        "forecast publishes wave period, so those are rated on wind and sea height alone.",
        "Cada columna es un periodo de pronóstico del Servicio Nacional de Meteorología. Elija "
        "una clase de embarcación y lea de izquierda a derecha: el color es la Idoneidad "
        "Operacional para esa clase en ese momento, y al pasar el cursor se indica qué la "
        "determina. Las columnas atenuadas están más allá del plazo en que el pronóstico "
        "publica el periodo del oleaje, así que se evalúan solo con viento y altura.")

    body = f"""
<p class="lead">{lead}</p>
{M.legend()}
{classbar}
<div class="gridwrap"><table class="pg" id="pg"></table></div>
<div class="wins" id="wins"></div>
"""
    gen = M.bi(
        f"Generated {d['generated_utc'][:16]}Z from NWS {d['office']} CWF issued "
        f"{(d['cwf_issued'] or '?')[:16]}Z. Refreshes every 6 hours.",
        f"Generado {d['generated_utc'][:16]}Z del CWF del NWS {d['office']} emitido "
        f"{(d['cwf_issued'] or '?')[:16]}Z. Se actualiza cada 6 horas.")
    scripts = JS.replace("__DATA__", json.dumps(d, ensure_ascii=False, default=str))
    i18n = "const I18N = " + json.dumps(I18N, ensure_ascii=False) + ";" 
    out_html = M.page_shell("planner.html", "Planner", "Planificador",
                            "Five-day departure windows", "Ventanas de salida a cinco días",
                            body, extra_css=CSS, scripts=scripts, generated=gen,
                            i18n=i18n)
    out = os.path.join(M.WEBOUT, "planner.html")
    M.atomic_write_text(out_html, out)
    nowave = sum(1 for c in cols if c["nowave"])
    print(f"[make_planner] wrote {out} ({len(out_html):,} bytes, {len(cols)} periods "
          f"({nowave} without wave detail), {len(out_sites)} sites)")
    return 0


_ES = {"TODAY": "Hoy", "TONIGHT": "Esta noche", "MONDAY": "Lunes", "TUESDAY": "Martes",
       "WEDNESDAY": "Miércoles", "THURSDAY": "Jueves", "FRIDAY": "Viernes",
       "SATURDAY": "Sábado", "SUNDAY": "Domingo"}


def _es_label(lab):
    u = lab.upper()
    if u.endswith(" NIGHT"):
        base = _ES.get(u[:-6].strip(), u[:-6].strip().title())
        return f"{base} noche"
    return _ES.get(u, lab.title())


if __name__ == "__main__":
    sys.exit(main())
