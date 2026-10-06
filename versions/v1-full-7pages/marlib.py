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
                 "name_es", "vars", "endpoint", "cadence_min", "max_age_h", "link", "notes"]
ROUTE_FIELDS = ["route_id", "active", "name_en", "name_es", "from_site", "to_site",
                "from_lat", "from_lon", "to_lat", "to_lon", "bearing_deg", "distance_nm",
                "service_kt", "vessel_class", "roll_period_s", "zone", "obs_wave",
                "obs_wind", "operator", "notes"]

CLASSES = ("ship", "ferry", "small", "rec")
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
    "<b>NOT FOR NAVIGATION.</b> Operational Suitability is computed by CariCOOS from "
    "observations and forecast data using the published thresholds. It is <b>not</b> an "
    "official forecast, advisory or warning. Official marine products are issued solely by "
    "the National Weather Service and are reproduced here verbatim and unaltered. "
    "Always consult the NWS and exercise your own judgement as master of the vessel.")
DISCLAIMER_ES = (
    "<b>NO APTO PARA LA NAVEGACIÓN.</b> La Idoneidad Operacional es calculada por CariCOOS "
    "a partir de observaciones y pronósticos usando los umbrales publicados. <b>No</b> es un "
    "pronóstico, aviso ni advertencia oficial. Los productos marinos oficiales los emite "
    "únicamente el Servicio Nacional de Meteorología (NWS) y aquí se reproducen literalmente "
    "y sin alterar. Consulte siempre al NWS y ejerza su propio criterio como capitán.")


def disclaimer():
    return f'<div class="disclaimer">{bi(DISCLAIMER_EN, DISCLAIMER_ES)}</div>'


# --------------------------------------------------------------------------
# page shell
# --------------------------------------------------------------------------
NAV = [("index.html", "Overview", "Resumen"),
       ("conditions_now.html", "Conditions now", "Condiciones ahora"),
       ("planner.html", "Planner", "Planificador"),
       ("marine_zones.html", "NWS marine zones", "Zonas marinas NWS"),
       ("tools.html", "Tools", "Herramientas"),
       ("methods.html", "Methods", "Métodos"),
       ("status.html", "Data status", "Estado de datos")]

SHELL_CSS = r"""
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--ink);
  font:400 1rem/1.5 "Source Sans 3",system-ui,sans-serif}
header{background:var(--navy);color:var(--navy-ink)}
.hwrap{max-width:1180px;margin:0 auto;padding:.9rem 1rem}
.brandrow{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
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

LOGO_SVG = (
    '<svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="11" fill="none" stroke="currentColor" stroke-width="1.6"/>'
    '<path d="M1.6 13.2c2.1 0 2.1 1.6 4.2 1.6s2.1-1.6 4.2-1.6 2.1 1.6 4.2 1.6 2.1-1.6 4.2-1.6 '
    '2.1 1.6 4.2 1.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
    '<path d="M12 3.2v7.2M9.2 5.6h5.6" fill="none" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round"/></svg>')


def page_shell(slug, title_en, title_es, sub_en, sub_es, body, extra_css="",
               extra_head="", scripts="", generated="", i18n=""):
    """The bilingual frame every generated page renders into."""
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
<style>{H.THEME_CSS}{H.LANG_CSS}{STATUS_CSS}{SHELL_CSS}{extra_css}</style>
</head>
<body>
{H.LANG_BOOT_JS}
<header><div class="hwrap">
  <div class="brandrow">
    <div style="display:flex;align-items:center;gap:.6rem">{LOGO_SVG}
      <div><h1>{bi(title_en, title_es)}</h1>
      <div class="sub">{bi(sub_en, sub_es)}</div></div></div>
    <div class="ctrls">{UNIT_BTN}{H.TZ_BTN}{H.LANG_BTN}</div>
  </div>
</div></header>
<nav class="tabs"><div class="hwrap">{tabs}</div></nav>
<main>
{body}
{disclaimer()}
</main>
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
    "THREDDS_BASE": "https://dm1.caricoos.org/thredds",
    "NWS_API": "https://api.weather.gov",
    "NWS_USER_AGENT": "CariCOOS Maritime Dashboard (dm2.caricoos.org; ops@caricoos.org)",
    "NWS_CWF_OFFICE": "SJU",
    "COOPS_API": "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
    "NDBC_LATEST": "https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt",
    "DASHBOARD_WEBROOT": "",
    "HUB_URL": "https://dm2.caricoos.org/Maritime_Dashboard",
    "BUOYS_HUB_URL": "../Buoys_Dashboard/",
    "MESONET_HUB_URL": "../Mesonet_Dashboard/",
    "MODVIEWER_URL": "https://modviewer.caricoos.org/",
    "CLASSIC_VIEWER_URL": "../Model_Viewer_v1/",
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
