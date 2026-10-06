# -*- coding: utf-8 -*-
"""Shared library for the CariCOOS Maritime Dashboard.

Everything more than one generator needs lives here so the site table, the unit
system, the suitability palette and the page shell are defined exactly once:

  load_sites() / load_sources() / load_routes() / site_maps()
                            config/*.tsv, the single source of truth
  validate()                cross-checks the TSVs against each other
  UNITS_JS                  metric / marine toggle (key maritime_units, default marine)
  STATUS_CSS                Favorable / Marginal / Unfavorable / No data
  page_shell()              the bilingual page frame every generator renders into
  DISCLAIMER_EN / _ES       the wording that must appear on every page

Presentation primitives shared with the other CariCOOS hubs (THEME_CSS, the
EN/ES machinery, the UTC/AST toggle, atomic writes) are vendored in hublib.py.
Maritime-only additions live HERE rather than in hublib, so that file stays
byte-identical to buoylib.py and tools/check_hublib_drift.py stays quiet.
"""
import os

import hublib as H
from hublib import atomic_write_parquet, atomic_write_text, bi, es_note  # noqa: F401

BASE = os.environ.get("MARITIME_BASE", os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(BASE, "config")
DATA = os.path.join(BASE, "data")
STATE = os.path.join(BASE, "state")
LOGS = os.path.join(BASE, "logs")
WEBOUT = os.path.join(BASE, "web", "out")

SITE_FIELDS = ["site_id", "kind", "active", "name_en", "name_es", "lat", "lon",
               "zone_lat", "zone_lon", "exposure", "depth_m", "zone", "obs_wave",
               "obs_wind", "obs_current", "tide", "classes", "group", "embed", "notes"]
SOURCE_FIELDS = ["src_id", "provider", "kind", "active", "lat", "lon", "name_en",
                 "name_es", "vars", "endpoint", "cadence_min", "max_age_h", "link", "notes",
                 "api_slug"]
ROUTE_FIELDS = ["route_id", "active", "name_en", "name_es", "from_site", "to_site",
                "from_lat", "from_lon", "to_lat", "to_lon", "bearing_deg", "distance_nm",
                "service_kt", "vessel_class", "roll_period_s", "zone", "obs_wave",
                "obs_wind", "operator", "notes"]

#: every vessel class the policy in config/thresholds.tsv covers
CLASSES = ("ship", "ferry", "small", "rec")

#: the classes the board actually shows. Kept separate from CLASSES on purpose:
#: the ship and ferry limits are real policy and the Phase 2 ferry-route and port
#: pages are built on them, so narrowing the board must not delete them. Add a
#: class back here and it reappears everywhere, with no other change.
BOARD_CLASSES = ("small", "rec")
CLASS_BI = {"ship": ("Commercial ship", "Buque comercial"),
            "ferry": ("Ferry / passenger", "Ferry / pasajeros"),
            "small": ("Small craft", "Embarcación pequeña"),
            "rec": ("Recreational", "Recreativa")}
GROUP_BI = {"North": ("North coast", "Costa norte"),
            "East": ("East coast", "Costa este"),
            "Vieques-Culebra": ("Vieques & Culebra", "Vieques y Culebra"),
            "South": ("South coast", "Costa sur"),
            "West/Mona": ("West coast & Mona Passage", "Costa oeste y Canal de la Mona"),
            "USVI": ("U.S. Virgin Islands", "Islas Vírgenes de EE.UU.")}
GROUP_ORDER = ["North", "East", "Vieques-Culebra", "South", "West/Mona", "USVI"]
DOWN_WORDS = ("stale", "offline", "retired", "closed", "inactive")


# --------------------------------------------------------------------------
# TSV loading
# --------------------------------------------------------------------------
def _rows(name, fields):
    path = os.path.join(CONFIG, name)
    out = []
    for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
        if not line.strip() or line.startswith("#"):
            continue
        f = line.rstrip("\n").split("\t")
        if f[0] == fields[0]:            # header row
            continue
        if len(f) != len(fields):
            raise SystemExit(f"{name}:{lineno}: expected {len(fields)} fields, got {len(f)}")
        out.append(dict(zip(fields, f)))
    if not out:
        raise SystemExit(f"{name}: no rows")
    return out


def _num(v, default=None):
    if v in ("", "-", None):
        return default
    return float(v)


def _list(v):
    if v in ("", "-", None):
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


def load_sites(active_only=True):
    out = []
    for r in _rows("sites.tsv", SITE_FIELDS):
        r["active"] = r["active"] == "1"
        for k in ("lat", "lon", "zone_lat", "zone_lon"):
            r[k] = _num(r[k])
        r["depth_m"] = _num(r["depth_m"])
        for k in ("obs_wave", "obs_wind", "obs_current", "classes"):
            r[k] = _list(r[k])
        r["tide"] = None if r["tide"] in ("", "-") else r["tide"]
        r["down"] = any(w in r["notes"].lower() for w in DOWN_WORDS)
        if active_only and not r["active"]:
            continue
        out.append(r)
    return out


def load_sources(active_only=True):
    out = {}
    for r in _rows("sources.tsv", SOURCE_FIELDS):
        r["active"] = r["active"] == "1"
        r["lat"], r["lon"] = _num(r["lat"]), _num(r["lon"])
        r["cadence_min"] = int(_num(r["cadence_min"], 60))
        r["max_age_h"] = _num(r["max_age_h"], 6)
        r["vars"] = _list(r["vars"])
        r["down"] = any(w in r["notes"].lower() for w in DOWN_WORDS)
        r["api_slug"] = None if r.get("api_slug") in ("", "-", None) else r["api_slug"]
        if active_only and not r["active"]:
            continue
        out[r["src_id"]] = r
    return out


def load_routes(active_only=True):
    out = []
    for r in _rows("routes.tsv", ROUTE_FIELDS):
        r["active"] = r["active"] == "1"
        for k in ("from_lat", "from_lon", "to_lat", "to_lon", "bearing_deg",
                  "distance_nm", "service_kt", "roll_period_s"):
            r[k] = _num(r[k])
        for k in ("obs_wave", "obs_wind"):
            r[k] = _list(r[k])
        if active_only and not r["active"]:
            continue
        out.append(r)
    return out


def site_maps():
    """(NAME_EN, NAME_ES, GROUP, ZONE, DOWN, ORDER) keyed by site_id."""
    sites = load_sites()
    order = sorted(sites, key=lambda s: (GROUP_ORDER.index(s["group"])
                                         if s["group"] in GROUP_ORDER else 99, s["name_en"]))
    return ({s["site_id"]: s["name_en"] for s in sites},
            {s["site_id"]: s["name_es"] for s in sites},
            {s["site_id"]: s["group"] for s in sites},
            {s["site_id"]: s["zone"] for s in sites},
            {s["site_id"]: s["down"] for s in sites},
            [s["site_id"] for s in order])


def validate():
    """Cross-check the TSVs. Returns a list of problem strings (empty = clean).

    Run by every fetcher and generator at startup: a site pointing at a station
    that does not exist should fail loudly at 03:00 in the log, not quietly render
    an empty column on a page a captain is reading.
    """
    problems = []
    sites = load_sites(active_only=False)
    srcs = load_sources(active_only=False)
    routes = load_routes(active_only=False)
    ids = set(srcs)

    seen = set()
    for s in sites:
        sid = s["site_id"]
        if sid in seen:
            problems.append(f"sites.tsv: duplicate site_id {sid}")
        seen.add(sid)
        for col in ("obs_wave", "obs_wind", "obs_current"):
            for ref in s[col]:
                if ref not in ids:
                    problems.append(f"sites.tsv: {sid}.{col} -> unknown source {ref!r}")
        if s["tide"] and s["tide"] not in ids:
            problems.append(f"sites.tsv: {sid}.tide -> unknown source {s['tide']!r}")
        if not s["zone"].startswith("AMZ"):
            problems.append(f"sites.tsv: {sid}.zone {s['zone']!r} is not an AMZ marine zone")
        for c in s["classes"]:
            if c not in CLASSES:
                problems.append(f"sites.tsv: {sid} unknown vessel class {c!r}")
        if s["group"] not in GROUP_ORDER:
            problems.append(f"sites.tsv: {sid} unknown group {s['group']!r}")
        if s["zone_lat"] is None or s["zone_lon"] is None:
            problems.append(f"sites.tsv: {sid} needs zone_lat/zone_lon for the NWS zone lookup")

    for r in routes:
        for col in ("from_site", "to_site"):
            ref = r[col]
            if ref not in ("", "-") and ref not in seen:
                problems.append(f"routes.tsv: {r['route_id']}.{col} -> unknown site {ref!r}")
        for ref in r["obs_wave"] + r["obs_wind"]:
            if ref not in ids:
                problems.append(f"routes.tsv: {r['route_id']} -> unknown source {ref!r}")
    return problems


# --------------------------------------------------------------------------
# units: metric / marine  (NOT 'imperial' - mariners here work in kt, ft, nmi)
# --------------------------------------------------------------------------
# A separate localStorage key from the buoys hub on purpose: the unit KINDS and
# the DEFAULT both differ. The language key is deliberately shared - see hublib.
UNITS_JS = (
    "const UNITS={"
    "m:{metric:['m',v=>v],marine:['ft',v=>v/0.3048]},"
    "kt:{metric:['m/s',v=>v/1.9438444924406046],marine:['kt',v=>v]},"
    "cms:{metric:['cm/s',v=>v],marine:['kt',v=>v*0.0194384]},"
    "nm:{metric:['km',v=>v*1.852],marine:['nmi',v=>v]},"
    "degC:{metric:['\\u00b0C',v=>v],marine:['\\u00b0F',v=>v*9/5+32]},"
    "s:{metric:['s',v=>v],marine:['s',v=>v]},"
    "deg:{metric:['\\u00b0',v=>v],marine:['\\u00b0',v=>v]},"
    "'-':{metric:['',v=>v],marine:['',v=>v]}};\n"
    "const UKEY='maritime_units';\n"
    "let U='marine';try{U=localStorage.getItem(UKEY)||'marine';}catch(e){}\n"
    "function setUnits(u){U=u;try{localStorage.setItem(UKEY,u);}catch(e){}"
    "document.querySelectorAll('.unitbtn').forEach(b=>{b.textContent=U==='marine'?'kt/ft':'m/s\\u00b7m';});"
    "if(typeof onUnits==='function')onUnits();}\n"
    "function cu(kind,v){return v==null?null:UNITS[kind||'-'][U][1](v);}\n"
    "function ul(kind){return UNITS[kind||'-'][U][0];}\n"
    "function fv(kind,v,dp){if(v==null)return '\\u2013';const x=cu(kind,v);"
    "const d=dp==null?(Math.abs(x)>=100?0:(Math.abs(x)>=10?0:1)):dp;"
    "const u=ul(kind);return x.toFixed(d)+(u?'\\u202f'+u:'');}\n"
    "document.querySelectorAll('.unitbtn').forEach(b=>{b.textContent=U==='marine'?'kt/ft':'m/s\\u00b7m';"
    "b.onclick=()=>setUnits(U==='marine'?'metric':'marine');});\n")

UNIT_BTN = ('<button class="unitbtn" type="button" '
            'title="knots &amp; feet / metric">kt/ft</button>')

# --------------------------------------------------------------------------
# suitability palette - a maritime extension on top of the vendored hub tokens
# --------------------------------------------------------------------------
# --ok and --flag already exist in hublib.THEME_CSS. --warn and --nodata are new
# and must be declared in all THREE theme blocks to match that file's structure.
# Never colour alone: every cell carries a colour, a glyph and a text label, so
# the board still reads correctly in greyscale and to a colour-blind mariner.
STATUS_CSS = r"""
:root{--warn:#c77700; --warn-ink:#ffffff; --nodata:#8496a4;}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --warn:#e09b2d; --warn-ink:#1a1206; --nodata:#6d8291;}}
:root[data-theme="dark"]{--warn:#e09b2d; --warn-ink:#1a1206; --nodata:#6d8291;}

.chip{display:inline-flex;align-items:center;gap:.36em;font:600 .82rem "Source Sans 3",sans-serif;
  padding:.16rem .55rem;border-radius:999px;white-space:nowrap;border:1px solid transparent}
.chip .g{font-size:.9em;line-height:1}
.chip.favorable{background:var(--ok);color:#fff}
.chip.marginal{background:var(--warn);color:var(--warn-ink)}
.chip.unfavorable{background:var(--flag);color:#fff}
.chip.nodata{background:var(--btn);color:var(--ink2);border-color:var(--line)}
.chip.notrated{background:transparent;color:var(--ink2);border-color:var(--line);border-style:dashed}

.cell{display:flex;align-items:center;justify-content:center;min-height:1.6rem;
  border-radius:3px;font:600 .7rem "Source Sans 3",sans-serif}
.cell.favorable{background:var(--ok);color:#fff}
.cell.marginal{background:var(--warn);color:var(--warn-ink)}
.cell.unfavorable{background:var(--flag);color:#fff}
.cell.nodata{background:var(--btn);color:var(--ink2);border:1px dashed var(--line)}
.cell.notrated{background:transparent;color:var(--ink2);border:1px dotted var(--line)}

/* NWS products sit in their own panel, visually distinct from anything we compute */
.nws{border:2px solid var(--s2);border-radius:8px;background:var(--panel);padding:.85rem 1rem;margin:1rem 0}
.nws h3{margin:0 0 .4rem;font:700 .95rem "Archivo",sans-serif;letter-spacing:.04em;
  text-transform:uppercase;color:var(--s2)}
.nws .prod{margin:.5rem 0;padding-left:.7rem;border-left:3px solid var(--s2)}
.nws .prod b{font:700 .95rem "Source Sans 3",sans-serif}
.nws .meta{font:400 .8rem "Source Sans 3",sans-serif;color:var(--ink2)}
.nws pre{white-space:pre-wrap;font:400 .82rem "JetBrains Mono",monospace;margin:.4rem 0 0}
.nws .attrib{font:400 .78rem "Source Sans 3",sans-serif;color:var(--ink2);margin-top:.5rem}
.nws .coastal{margin-top:.7rem;padding-top:.6rem;border-top:1px dashed var(--line)}
.nws .coastal .ch{font:700 .72rem "Archivo",sans-serif;letter-spacing:.06em;
  text-transform:uppercase;color:var(--s2);margin-bottom:.3rem}
.nws pre.desc{font:400 .84rem "Source Sans 3",sans-serif;color:var(--ink);margin-top:.35rem}

.disclaimer{border-top:1px solid var(--line);margin-top:1.6rem;padding-top:.8rem;
  font:400 .82rem "Source Sans 3",sans-serif;color:var(--ink2)}
.disclaimer b{color:var(--flag)}
.agebadge{font:600 .72rem "Source Sans 3",sans-serif;padding:.05rem .4rem;border-radius:3px;
  background:var(--btn);color:var(--ink2)}
.agebadge.stale{background:var(--flag);color:#fff}

.legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:.4rem .9rem;
  background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:.7rem .9rem;margin:.2rem 0 1rem}
.legend .lg{display:flex;align-items:baseline;gap:.5rem}
.legend .lgt{font-size:.86rem;color:var(--ink2);line-height:1.35}
"""

STATUS_GLYPH = {"favorable": "\u25cf", "marginal": "\u25b2",
                "unfavorable": "\u25a0", "nodata": "\u2013", "notrated": "\u00b7"}
STATUS_BI = {"favorable": ("Favorable", "Favorable"),
             "marginal": ("Marginal", "Marginal"),
             "unfavorable": ("Unfavorable", "Desfavorable"),
             "nodata": ("No data", "Sin datos"),
             "notrated": ("Not rated here", "No evaluado aquí")}


LEGEND_BI = {
    "favorable": ("Within all published limits for this vessel class.",
                  "Dentro de todos los límites publicados para esta clase."),
    "marginal": ("At least one limit reached. Passable with care and experience.",
                 "Al menos un límite alcanzado. Transitable con cuidado y experiencia."),
    "unfavorable": ("At least one limit exceeded. Not recommended for this class.",
                    "Al menos un límite excedido. No recomendado para esta clase."),
    "nodata": ("No usable observation or forecast for this location right now.",
               "No hay observación ni pronóstico utilizable para este lugar ahora."),
    "notrated": ("This vessel class is not assessed at this kind of location.",
                 "Esta clase de embarcación no se evalúa en este tipo de lugar."),
}


def legend(statuses=("favorable", "marginal", "unfavorable", "notrated")):
    """The key, shown on the page rather than hidden in a tooltip.

    A colour-coded board that only explains itself on hover is unusable on a phone
    and unreadable to anyone who does not already know the scheme.
    """
    items = "".join(
        f'<div class="lg"><span class="chip {s}">'
        f'<span class="g" aria-hidden="true">{STATUS_GLYPH.get(s, "")}</span>'
        f'{bi(*STATUS_BI[s])}</span><span class="lgt">{bi(*LEGEND_BI[s])}</span></div>'
        for s in statuses)
    return f'<div class="legend">{items}</div>'


def status_chip(status, label=None):
    en, es = STATUS_BI.get(status, STATUS_BI["nodata"])
    txt = label if label is not None else bi(en, es)
    return (f'<span class="chip {status}"><span class="g" aria-hidden="true">'
            f'{STATUS_GLYPH.get(status, "-")}</span>{txt}</span>')


# --------------------------------------------------------------------------
# the wording that must appear on every page
# --------------------------------------------------------------------------
# The user's constraint, and it is not negotiable: 'advisory', 'warning' and
# 'watch' are official National Weather Service product names. What WE compute is
# called Operational Suitability and never borrows those words. Verified by the
# terminology grep in docs/VERIFY.md before every release.
PRODUCT_EN = "Operational Suitability"
PRODUCT_ES = "Idoneidad Operacional"

DISCLAIMER_EN = (
    "<b>NOT FOR NAVIGATION.</b> This board reports instrument observations from the CariCOOS "
    "buoys and weather stations, falling back to the National Weather Service zone forecast "
    "where no recent instrument covers a location; each value is labelled with its source and "
    "time. Instruments fail and readings can be wrong. Official marine products are issued "
    "solely by the National Weather Service and are reproduced here verbatim and unaltered. "
    "Always consult the NWS and exercise your own judgement as master of the vessel.")
DISCLAIMER_ES = (
    "<b>NO APTO PARA LA NAVEGACIÓN.</b> Este tablero muestra observaciones de los instrumentos "
    "de las boyas y estaciones de CariCOOS, y recurre al pronóstico de zona del Servicio "
    "Nacional de Meteorología cuando ningún instrumento reciente cubre un lugar; cada valor "
    "lleva su fuente y su hora. Los instrumentos fallan y las lecturas pueden ser erróneas. "
    "Los productos marinos oficiales los emite únicamente el NWS y aquí se reproducen "
    "literalmente y sin alterar. Consulte siempre al NWS y ejerza su propio criterio como "
    "capitán.")


def disclaimer():
    return f'<div class="disclaimer">{bi(DISCLAIMER_EN, DISCLAIMER_ES)}</div>'


# --------------------------------------------------------------------------
# page shell
# --------------------------------------------------------------------------
# The live site is deliberately three pages. The full seven-page build (overview,
# planner, methods, status) is kept under versions/v1-full-7pages/ - see its
# README-VERSION.md for how to bring a page back.
CHAT_CSS = r"""
.askbtn{position:fixed;right:1rem;bottom:1rem;z-index:60;display:flex;align-items:center;
  gap:.45rem;background:var(--navy);color:var(--navy-ink);border:1px solid rgba(255,255,255,.25);
  border-radius:999px;padding:.6rem 1.05rem;font:600 .92rem "Source Sans 3",sans-serif;
  cursor:pointer;box-shadow:0 3px 14px rgba(0,0,0,.28)}
.askbtn:hover{background:var(--teal)}
.chatwrap{position:fixed;right:1rem;bottom:1rem;z-index:61;width:min(400px,calc(100vw - 2rem));
  max-height:min(620px,calc(100vh - 2rem));display:none;flex-direction:column;
  background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden;
  box-shadow:0 6px 28px rgba(0,0,0,.32)}
.chatwrap.on{display:flex}
.chathead{display:flex;align-items:center;justify-content:space-between;gap:.5rem;
  padding:.6rem .85rem;background:var(--navy);color:var(--navy-ink)}
.chathead b{font:700 .95rem "Archivo",sans-serif}
.chathead .x{background:transparent;border:0;color:var(--navy-ink);font-size:1.3rem;
  line-height:1;cursor:pointer;padding:0 .2rem}
.chatlog{flex:1;overflow-y:auto;padding:.8rem;display:flex;flex-direction:column;gap:.6rem}
.msg{max-width:92%;padding:.5rem .7rem;border-radius:9px;font-size:.92rem;line-height:1.45;
  white-space:pre-wrap;word-wrap:break-word}
.msg.me{align-self:flex-end;background:var(--btn-on);color:var(--btn-on-ink)}
.msg.bot{align-self:flex-start;background:var(--surface);border:1px solid var(--line)}
.msg.err{align-self:flex-start;background:var(--flag);color:#fff}
.msg.think{align-self:flex-start;color:var(--ink2);font-style:italic}
.msg.bot a{color:var(--s1);text-decoration:underline;word-break:break-word}
.msg.bot a:hover{color:var(--teal)}
.chatfoot{border-top:1px solid var(--line);padding:.55rem;display:flex;gap:.4rem}
.chatfoot input{flex:1;min-width:0;border:1px solid var(--line);border-radius:7px;
  padding:.5rem .6rem;font:400 .93rem "Source Sans 3",sans-serif;background:var(--surface);
  color:var(--ink)}
.chatfoot button{background:var(--btn-on);color:var(--btn-on-ink);border:0;border-radius:7px;
  padding:.5rem .9rem;font:600 .9rem "Source Sans 3",sans-serif;cursor:pointer}
.chatfoot button:disabled{opacity:.5;cursor:default}
.chatnote{padding:.5rem .85rem;font-size:.8rem;color:var(--ink2);border-top:1px solid var(--line)}
.keyform{padding:.6rem .8rem;border-top:1px solid var(--line);background:var(--surface)}
.keyform .kf-t{font-size:.86rem;margin-bottom:.4rem;line-height:1.4}
.keyform .kf-r{display:flex;gap:.4rem}
.keyform input{flex:1;min-width:0;border:1px solid var(--line);border-radius:7px;
  padding:.45rem .55rem;font:400 .9rem "Source Sans 3",sans-serif;background:var(--panel);
  color:var(--ink)}
.keyform button{background:var(--btn-on);color:var(--btn-on-ink);border:0;border-radius:7px;
  padding:.45rem .85rem;font:600 .88rem "Source Sans 3",sans-serif;cursor:pointer}
.chips{display:flex;gap:.35rem;flex-wrap:wrap;padding:0 .8rem .3rem}
.chips button{background:var(--btn);border:1px solid var(--line);color:var(--ink);
  border-radius:999px;padding:.25rem .6rem;font:600 .8rem "Source Sans 3",sans-serif;cursor:pointer}
.chips button:hover{background:var(--sel)}
@media (max-width:520px){.chatwrap{right:.5rem;left:.5rem;bottom:.5rem;width:auto;
  max-height:calc(100vh - 1rem)}.askbtn{right:.7rem;bottom:.7rem}}
"""


def chat_widget(env):
    """The Ask panel. Renders nothing at all when no Worker is configured, so the
    dashboard is never broken by a chatbot that has not been deployed."""
    url = (env.get("CHAT_WORKER_URL") or "").strip()
    if not url:
        return "", ""
    html = f"""
<button class="askbtn" id="askbtn" type="button">&#128172; {bi("Ask", "Preguntar")}</button>
<div class="chatwrap" id="chatwrap" role="dialog" aria-label="CariCOOS Maritime assistant">
  <div class="chathead"><b>{bi("Ask about conditions", "Pregunta sobre las condiciones")}</b>
    <button class="x" id="chatx" type="button" aria-label="close">&times;</button></div>
  <div class="chatlog" id="chatlog"></div>
  <div class="keyform" id="chatkey" hidden>
    <div class="kf-t" id="chatkeymsg"></div>
    <div class="kf-r"><input id="chatkeyin" type="password" autocomplete="off">
      <button id="chatkeyok" type="button">{bi("Save", "Guardar")}</button></div>
  </div>
  <div class="chips" id="chatchips"></div>
  <div class="chatfoot">
    <input id="chatin" autocomplete="off">
    <button id="chatsend" type="button">{bi("Send", "Enviar")}</button>
  </div>
  <div class="chatnote">{bi(
    "Answers come from the measurements on this board. Not for navigation.",
    "Las respuestas salen de las mediciones de este tablero. No apto para la navegación.")}</div>
</div>"""
    js = r"""
(function(){
  const URL_=%s;
  const KEY='maritime_chat_key', HIST=[];
  const wrap=document.getElementById('chatwrap'), log=document.getElementById('chatlog'),
        inp=document.getElementById('chatin'), send=document.getElementById('chatsend'),
        chips=document.getElementById('chatchips');
  const T2=(en,es)=>L==='es'?es:en;
  /* Set from JS, not from a placeholder attribute: bi() emits <span> markup,
     which renders as raw text inside an attribute. Anything bilingual in an
     attribute has to come through here. */
  function labels(){
    inp.placeholder=T2('How is Fajardo right now?','¿Cómo está Fajardo ahora?');
  }

  /* Turn URLs in the assistant's text into real links.

     The answer text is NEVER inserted as markup. It goes in through textContent
     first, which escapes everything the model wrote, and only then are anchors
     spliced into the already-escaped string. So a model that emitted a <script>
     tag - or was talked into emitting one - still renders as visible text.
     Bare hosts are matched too, because the closing line reads
     "weather.gov/sju" with no scheme. */
  const URLRE=/((?:https?:\/\/|www\.)[^\s<]+|(?:[a-z0-9-]+\.)+(?:gov|org|com|net|edu|io)(?:\/[^\s<]*)?)/gi;
  function linkify(el,text){
    el.textContent=text;
    el.innerHTML=el.innerHTML.replace(URLRE,function(m){
      const tail=m.match(/[.,;:!?)\]}'"]+$/);       // keep trailing punctuation out of the href
      const url=tail?m.slice(0,-tail[0].length):m;
      if(!url) return m;
      const href=/^https?:\/\//i.test(url)?url:'https://'+url;
      return '<a href="'+href+'" target="_blank" rel="noopener noreferrer">'+url+'</a>'+
             (tail?tail[0]:'');
    });
  }
  function add(text,cls){
    const d=document.createElement('div'); d.className='msg '+cls;
    if(cls==='bot') linkify(d,text); else d.textContent=text;
    log.appendChild(d); log.scrollTop=log.scrollHeight; return d;
  }
  /* The access key is asked for per person and kept in their browser. Baking it
     into the page would publish it to everyone who can load the page, which is
     the opposite of what "internal only" means.

     This used to call prompt(). That failed SILENTLY: dismiss the dialog and
     Send did nothing at all - no message, no hint, nothing to click. An in-panel
     form can explain itself, and can say what the key is when this is obviously
     a local dev server. */
  const kf=document.getElementById('chatkey'), kfin=document.getElementById('chatkeyin'),
        kfmsg=document.getElementById('chatkeymsg');
  const isLocal=/^https?:\/\/(127\.0\.0\.1|localhost)[:\/]/.test(URL_);
  let pendingQ=null;

  function storedKey(){ try{return localStorage.getItem(KEY);}catch(e){return null;} }
  function askForKey(msg){
    kfmsg.innerHTML = msg || (isLocal
      ? T2('Local development server. Type <b>local</b> \u2014 this is the access key, <b>not</b> your Anthropic API key.',
           'Servidor local de desarrollo. Escribe <b>local</b> \u2014 esta es la clave de acceso, <b>no</b> tu clave de API de Anthropic.')
      : T2('Enter the access key for the CariCOOS assistant \u2014 not an Anthropic API key. Ask your CariCOOS contact if you do not have it.',
           'Introduce la clave de acceso del asistente CariCOOS \u2014 no una clave de API de Anthropic. Pídesela a tu contacto en CariCOOS si no la tienes.'));
    kf.hidden=false; kfin.value=''; kfin.focus();
  }
  function saveKey(){
    const k=(kfin.value||'').trim();
    if(!k){ kfin.focus(); return; }
    if(/^sk-ant-/.test(k)){
      kfmsg.innerHTML=T2('That is an Anthropic API key. It belongs on the server, not here. '+
                         (isLocal?'Type <b>local</b> instead.':'Ask your CariCOOS contact for the access key.'),
                         'Esa es una clave de API de Anthropic. Va en el servidor, no aquí. '+
                         (isLocal?'Escribe <b>local</b> en su lugar.':'Pide la clave de acceso a tu contacto en CariCOOS.'));
      kfin.value=''; kfin.focus(); return;
    }
    try{localStorage.setItem(KEY,k);}catch(e){}
    kf.hidden=true;
    if(pendingQ){ const q=pendingQ; pendingQ=null; inp.value=q; ask(); }
  }
  document.getElementById('chatkeyok').onclick=saveKey;
  kfin.addEventListener('keydown',e=>{if(e.key==='Enter')saveKey();});
  function suggestions(){
    chips.innerHTML='';
    const qs = L==='es'
      ? ['¿Cómo está San Juan ahora?','¿Dónde hay menos oleaje?','¿Qué dice el NWS para Vieques?']
      : ['How is San Juan right now?','Where are the smallest seas?','What does NWS say for Vieques?'];
    qs.forEach(q=>{const b=document.createElement('button');b.type='button';b.textContent=q;
      b.onclick=()=>{inp.value=q;ask();};chips.appendChild(b);});
  }
  async function ask(){
    const q=(inp.value||'').trim(); if(!q) return;
    const k=storedKey();
    if(!k){ pendingQ=q; inp.value=''; askForKey(); return; }
    inp.value=''; chips.innerHTML=''; add(q,'me');
    send.disabled=true;
    const pending=add(T2('Checking the data\u2026','Consultando los datos\u2026'),'think');
    try{
      const r=await fetch(URL_,{method:'POST',
        headers:{'content-type':'application/json','x-chat-token':k},
        body:JSON.stringify({question:q,history:HIST.slice(-8)})});
      const d=await r.json().catch(()=>({}));
      pending.remove();
      if(r.status===401){
        try{localStorage.removeItem(KEY);}catch(e){}
        pendingQ=q;
        askForKey(T2('That key was not accepted. Try another one.',
                     'Esa clave no fue aceptada. Prueba con otra.'));
      }
      else if(!r.ok){
        add(d.error||T2('Something went wrong.','Algo salió mal.'),'err'); }
      else {
        add(d.answer,'bot');
        HIST.push({role:'user',content:q},{role:'assistant',content:d.answer});
      }
    }catch(e){
      pending.remove();
      add(T2('Could not reach the assistant.','No se pudo contactar al asistente.'),'err');
    }
    send.disabled=false; inp.focus();
  }
  function greeting(){
    return T2('Ask me about the conditions on this board. I answer from the measurements shown here and say which station each number came from.',
              'Pregúntame sobre las condiciones de este tablero. Respondo con las mediciones que ves aquí y digo de qué estación viene cada número.');
  }
  document.getElementById('askbtn').onclick=()=>{
    wrap.classList.add('on');
    if(!log.childElementCount){ add(greeting(),'bot'); suggestions(); }
    inp.focus();
  };
  document.getElementById('chatx').onclick=()=>wrap.classList.remove('on');
  labels();
  /* follow the page language toggle */
  const prevOnLang = typeof onLang==='function' ? onLang : null;
  window.onLang=function(){
    if(prevOnLang)prevOnLang();
    labels();
    if(chips.childElementCount)suggestions();
    /* Re-render the greeting only while it stands alone. Once a conversation has
       started, past messages are left exactly as they were said - rewriting what
       the assistant already answered would be worse than a mixed-language log. */
    if(log.childElementCount===1 && log.firstChild.classList.contains('bot'))
      log.firstChild.textContent=greeting();
  };
  send.onclick=ask;
  inp.addEventListener('keydown',e=>{if(e.key==='Enter')ask();});
})();
""" % (_json.dumps(url),)
    return html, js


NAV = [("index.html", "Conditions now", "Condiciones ahora"),
       ("marine_zones.html", "NWS forecast", "Pronóstico NWS"),
       ("tools.html", "Tools", "Herramientas")]

SHELL_CSS = r"""
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--ink);
  font:400 1rem/1.5 "Source Sans 3",system-ui,sans-serif}
header{background:var(--navy);color:var(--navy-ink)}
.hwrap{max-width:1180px;margin:0 auto;padding:.9rem 1rem}
.brandrow{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.brandwrap{display:flex;align-items:center;gap:.85rem;min-width:0}
.brand{display:flex;align-items:center;gap:.55rem;text-decoration:none;flex:0 0 auto}
.brand .mark{height:38px;width:auto;display:block}
.brand .word{height:19px;width:auto;display:block}
.titles{min-width:0;border-left:1px solid rgba(255,255,255,.28);padding-left:.85rem}
@media (max-width:640px){
  .brand .word{display:none}
  .titles{border-left:0;padding-left:0}
  .brandwrap{gap:.55rem}
}
h1{margin:.2rem 0 0;font:700 1.5rem "Archivo",sans-serif;letter-spacing:.01em}
.sub{color:var(--navy-sub);font-size:.92rem;margin-top:.15rem}
.ctrls{display:flex;gap:.4rem;align-items:center;flex-wrap:wrap}
.unitbtn,.tzbtn,.langbtn{font:600 .78rem "Archivo",sans-serif;letter-spacing:.06em;
  border:1px solid rgba(255,255,255,.45);background:transparent;color:var(--navy-ink);
  padding:.22rem .7rem;border-radius:999px;cursor:pointer}
.unitbtn:hover,.tzbtn:hover{background:rgba(255,255,255,.12)}
nav.tabs{background:var(--navy);border-top:1px solid rgba(255,255,255,.14)}
nav.tabs .hwrap{padding:0 1rem;display:flex;gap:.2rem;overflow-x:auto}
nav.tabs a{color:var(--navy-sub);text-decoration:none;padding:.55rem .8rem;white-space:nowrap;
  font:600 .88rem "Source Sans 3",sans-serif;border-bottom:3px solid transparent}
nav.tabs a:hover{color:var(--navy-ink)}
nav.tabs a[aria-current="page"]{color:var(--navy-ink);border-bottom-color:var(--teal)}
main{max-width:1180px;margin:0 auto;padding:1.2rem 1rem 2.5rem}
h2{font:700 1.15rem "Archivo",sans-serif;margin:1.6rem 0 .6rem}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:1rem}
footer{max-width:1180px;margin:0 auto;padding:0 1rem 2rem;color:var(--ink2);font-size:.85rem}
a{color:var(--s1)}
@media (max-width:720px){h1{font-size:1.25rem}.hwrap{padding:.7rem .8rem}main{padding:.9rem .8rem 2rem}}
"""

_ASSETS_DONE = False


def ensure_assets():
    """Copy web/assets/* into the published folder.

    The CARICOOS logos are vendored rather than hot-linked from caricoos.org: a
    board someone opens on a phone offshore should not need that host to be up,
    and a page that silently loses its branding when a third-party asset 404s is
    worse than one that carries its own. Called from page_shell so a new
    generator cannot forget it; runs once per process.
    """
    global _ASSETS_DONE
    if _ASSETS_DONE:
        return
    src = os.path.join(BASE, "web", "assets")
    dst = os.path.join(WEBOUT, "assets")
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        import shutil
        for name in os.listdir(src):
            s, d = os.path.join(src, name), os.path.join(dst, name)
            if os.path.isfile(s):
                shutil.copyfile(s, d)
    _ASSETS_DONE = True


LOGO_SVG = (
    '<svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="11" fill="none" stroke="currentColor" stroke-width="1.6"/>'
    '<path d="M1.6 13.2c2.1 0 2.1 1.6 4.2 1.6s2.1-1.6 4.2-1.6 2.1 1.6 4.2 1.6 2.1-1.6 4.2-1.6 '
    '2.1 1.6 4.2 1.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
    '<path d="M12 3.2v7.2M9.2 5.6h5.6" fill="none" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round"/></svg>')


def cf_analytics(env):
    """Cloudflare Web Analytics beacon, or nothing at all.

    Page views only - Cloudflare's FAQ is explicit that custom events are "not
    yet" supported - so this cannot answer "which locations do people open".
    That is what track() below is for. No cookies, and `defer` keeps it off the
    critical path: if Cloudflare is slow or blocked the board still paints.
    """
    token = (env.get("CF_ANALYTICS_TOKEN") or "").strip()
    if not token:
        return ""
    return ('<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
            f"data-cf-beacon='{{\"token\": \"{token}\"}}'></script>")


def analytics_js(env, slug):
    """Count in-page interactions, with no identity attached.

    What is sent: the page, the event name, and a short label (a site id, a tool
    name, a language code). No cookies, no visitor id, no session, no free text,
    and never anything a person typed. sendBeacon so it costs the user nothing
    and cannot delay a click.

    Sends nothing when ANALYTICS_URL is unset, which is the default.
    """
    url = (env.get("ANALYTICS_URL") or "").strip()
    if not url:
        return ""
    # The usage page does not count itself. An operator reading the numbers would
    # otherwise show up in them, and "Usage" would climb the "pages people open"
    # chart purely because someone kept checking the chart.
    if slug == "analytics.html":
        return ""
    return """
(function(){
  const U=%s, PAGE=%s;
  function track(event,label){
    try{
      const body=JSON.stringify({page:PAGE,event:event,label:label||null,
                                 lang:document.documentElement.getAttribute('data-lang')||'en',
                                 ts:new Date().toISOString()});
      /* text/plain, not application/json, and it matters: application/json makes
         this a non-simple CORS request, which needs a preflight - and sendBeacon
         cannot preflight, so the browser drops it silently cross-origin. The body
         is still JSON; the server parses it regardless of the declared type. */
      const blob=new Blob([body],{type:'text/plain;charset=UTF-8'});
      if(!(navigator.sendBeacon&&navigator.sendBeacon(U,blob)))
        fetch(U,{method:'POST',body:body,headers:{'content-type':'text/plain'},keepalive:true})
          .catch(function(){});
    }catch(e){/* analytics must never break the page */}
  }
  window.track=track;
  track('page_view');
  /* Which location someone opens is the whole question this answers, and it is
     only visible in-page: every site lives on one URL, so no server log can see it. */
  document.addEventListener('click',function(ev){
    const row=ev.target.closest('tr.site');
    if(row&&row.dataset.t){
      /* This listener runs in the CAPTURE phase, so the row's own handler has
         not toggled the drawer yet - reading .hidden here reports the state
         BEFORE the click and never logged an open. Read it on the next tick,
         once the toggle has run, and only count openings, not closings. */
      setTimeout(function(){
        const d=document.getElementById('d_'+row.dataset.t);
        if(d&&!d.hidden) track('location_open',row.dataset.t);
      },0);
      return;
    }
    const load=ev.target.closest('[data-load],[data-embed]');
    if(load){ track('tool_embed',load.dataset.load||load.dataset.embed); return; }
    const ext=ev.target.closest('.tool .bar a, .embedbox a');
    if(ext){ track('tool_open_tab',(ext.getAttribute('href')||'').slice(0,60)); return; }
    if(ev.target.closest('.langbtn')) track('toggle_lang');
    else if(ev.target.closest('.unitbtn')) track('toggle_units');
    else if(ev.target.closest('.tzbtn')) track('toggle_tz');
  },true);
})();
""" % (_json.dumps(url), _json.dumps(slug))


def page_shell(slug, title_en, title_es, sub_en, sub_es, body, extra_css="",
               extra_head="", scripts="", generated="", i18n=""):
    """The bilingual frame every generated page renders into."""
    env = load_env()
    ensure_assets()
    chat_html, chat_js = chat_widget(env)
    cf_beacon = cf_analytics(env)
    track_js = analytics_js(env, slug)
    tabs = "".join(
        f'<a href="{href}"{" aria-current=\"page\"" if href.startswith(slug) else ""}>'
        f'{bi(en, es)}</a>' for href, en, es in NAV)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, must-revalidate">
<title>{title_en} &middot; CariCOOS Maritime</title>
{H.FONTS_LINK}
{extra_head}
{cf_beacon}
<style>{H.THEME_CSS}{H.LANG_CSS}{STATUS_CSS}{SHELL_CSS}{CHAT_CSS}{extra_css}</style>
</head>
<body>
{H.LANG_BOOT_JS}
<header><div class="hwrap">
  <div class="brandrow">
    <div class="brandwrap">
      <a class="brand" href="https://www.caricoos.org" target="_blank" rel="noopener"
         title="CARICOOS">
        <img class="mark" src="assets/logo_isologo.svg" alt="CARICOOS" width="108" height="100">
        <img class="word" src="assets/logo_caricoos.svg" alt="" aria-hidden="true"
             width="365" height="100">
      </a>
      <div class="titles"><h1>{bi(title_en, title_es)}</h1>
      <div class="sub">{bi(sub_en, sub_es)}</div></div>
    </div>
    <div class="ctrls">{UNIT_BTN}{H.TZ_BTN}{H.LANG_BTN}</div>
  </div>
</div></header>
<nav class="tabs"><div class="hwrap">{tabs}</div></nav>
<main>
{body}
{disclaimer()}
</main>
{chat_html}
<footer>{generated}</footer>
<script>
{UNITS_JS}
{H.TZ_JS}
/* ORDER MATTERS, and it bit us twice.
   1. LANG_JS must come BEFORE the page script, because page scripts call render()
      at load and render() reads L and T(), which LANG_JS declares with let/function.
      Page script first => L is in its temporal dead zone => ReferenceError before a
      single row is drawn, and the table just renders empty with nothing on screen
      to say why.
   2. The page's I18N dictionary must come BEFORE LANG_JS, because LANG_JS's
      applyI18n() runs at load and guards with `typeof I18N !== 'undefined'`.
      That guard is NOT safe here: typeof only tolerates *undeclared* names, and a
      `const I18N` declared further down the same scope is declared-but-uninitialised,
      so typeof throws too. Hence its own slot, emitted first. */
{i18n}
{H.LANG_JS}
{scripts}
{chat_js}
{track_js}
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# environment, HTTP and the fetch manifest
# --------------------------------------------------------------------------
import datetime as _dt          # noqa: E402
import json as _json            # noqa: E402
import re as _re                # noqa: E402
import urllib.error as _uerr    # noqa: E402
import urllib.request as _ureq  # noqa: E402

DEFAULT_ENV = {
    "CHAT_WORKER_URL": "",
    "CF_ANALYTICS_TOKEN": "",
    "ANALYTICS_URL": "",
    "THREDDS_BASE": "https://dm1.caricoos.org/thredds",
    "NWS_API": "https://api.weather.gov",
    "NWS_USER_AGENT": "CariCOOS Maritime Dashboard (dm2.caricoos.org; ops@caricoos.org)",
    "NWS_CWF_OFFICE": "SJU",
    "COOPS_API": "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
    "NDBC_LATEST": "https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt",
    "DASHBOARD_WEBROOT": "",
    # Sibling project roots, for climatology. Empty = no climatology at all and
    # the chatbot says it has no historical data, which must keep working.
    # Local files are preferred on every machine including dm2: the HTTP
    # fallback below serves only the day-of-year bands, because the monthly
    # tables, the records and the period of record live in files the hubs do
    # not publish.
    "BUOYS_OPS_DIR": "",
    "MESONET_OPS_DIR": "",
    "BUOYS_CLIMATE_URL": "https://dm2.caricoos.org/Ocean_Buoys/plots/station_climate.html",
    "MESONET_CLIMATE_URL": "https://dm2.caricoos.org/Wind_Stations/plots/station_climate.html",
    "HUB_URL": "https://dm2.caricoos.org/Maritime_Dashboard",
    # absolute https for all four - see config/machine.env.example for why
    "BUOYS_HUB_URL": "https://dm2.caricoos.org/Ocean_Buoys/",
    "MESONET_HUB_URL": "https://dm2.caricoos.org/Wind_Stations/",
    "MODVIEWER_URL": "https://modviewer.caricoos.org/",
    # HTTP on purpose. The classic viewer pulls its model imagery from the S3
    # *website* endpoint (caricoos-web.s3-website-us-east-1.amazonaws.com), which
    # only speaks HTTP - over HTTPS those requests reset and the maps come up
    # blank. Verified 2026-09-28: 3 of 3 images load over http, 1 of 3 over https.
    # A browser will still refuse to EMBED it inside an https page (mixed
    # content), which is why the tools page offers it as a link there instead.
    "CLASSIC_VIEWER_URL": "http://dm2.caricoos.org/Model_Viewer_v1/",
}
_ENVLINE = _re.compile(r'^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$')


def load_env():
    """config/machine.env (falling back to machine.env.example, then defaults).

    Shell-style KEY="value"; only simple assignments are honoured, which is all the
    wrappers use. Real environment variables win, so a run can be overridden inline.
    """
    env = dict(DEFAULT_ENV)
    for name in ("machine.env", "machine.env.example"):
        path = os.path.join(CONFIG, name)
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = _ENVLINE.match(line)
            if not m:
                continue
            k, v = m.group(1), m.group(2)
            if v[:1] in ('"', "'") and v[-1:] == v[:1]:
                v = v[1:-1]
            env[k] = v
        break
    for k in list(env):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def utcnow():
    return _dt.datetime.now(_dt.timezone.utc)


# 20 s, not 60: these APIs answer in well under two seconds when healthy, and an
# endpoint that HANGS (rather than refusing) would otherwise stall the whole cron
# cycle for minutes. Measured in the failure drill: a dead port hangs, it does not
# refuse, so the timeout is the only thing bounding a bad cycle.
HTTP_TIMEOUT = 20


def http_json(url, ua, timeout=HTTP_TIMEOUT, accept="application/geo+json"):
    req = _ureq.Request(url, headers={"User-Agent": ua, "Accept": accept})
    with _ureq.urlopen(req, timeout=timeout) as r:
        return _json.load(r)


def http_text(url, ua, timeout=HTTP_TIMEOUT):
    req = _ureq.Request(url, headers={"User-Agent": ua})
    with _ureq.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def manifest_path():
    return os.path.join(STATE, "manifest.json")


def read_manifest():
    try:
        return _json.load(open(manifest_path(), encoding="utf-8"))
    except Exception:
        return {}


def record(key, url, ok, bytes_=0, error="", extra=None):
    """Append one fetch outcome to state/manifest.json.

    status.html is built entirely from this, so a source that quietly stopped
    updating is visible on a page rather than only in a log nobody opens.
    """
    m = read_manifest()
    m[key] = {"url": url, "fetched_utc": utcnow().isoformat(), "ok": bool(ok),
              "bytes": int(bytes_), "error": str(error or "")}
    if extra:
        m[key].update(extra)
    os.makedirs(STATE, exist_ok=True)
    atomic_write_text(_json.dumps(m, indent=1, sort_keys=True, ensure_ascii=False),
                      manifest_path())
    return m[key]


def write_json(obj, *parts):
    """Atomically write a payload under data/."""
    path = os.path.join(DATA, *parts)
    atomic_write_text(_json.dumps(obj, ensure_ascii=False, separators=(",", ":")), path)
    return path


def read_json(*parts, default=None):
    """Read a cached payload; missing or corrupt returns `default`.

    Generators use this and NEVER touch the network, so a failed fetch degrades to
    yesterday's numbers with a visible age badge rather than an empty page.
    """
    try:
        return _json.load(open(os.path.join(DATA, *parts), encoding="utf-8"))
    except Exception:
        return default


def epoch_to_iso(epoch):
    """Unix seconds -> aware UTC ISO string."""
    return _dt.datetime.fromtimestamp(float(epoch), _dt.timezone.utc).isoformat()


def parts_to_iso(y, mo, d, h, mi):
    """NDBC's separate YYYY MM DD hh mm columns -> aware UTC ISO string."""
    return _dt.datetime(int(y), int(mo), int(d), int(h), int(mi),
                        tzinfo=_dt.timezone.utc).isoformat()


def read_json_path(path, default=None):
    """Read a JSON file by absolute path (read_json is relative to data/)."""
    try:
        return _json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def age_minutes(iso):
    if not iso:
        return None
    try:
        t = _dt.datetime.fromisoformat(iso)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return (utcnow() - t).total_seconds() / 60.0
