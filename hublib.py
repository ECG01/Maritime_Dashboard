# -*- coding: utf-8 -*-
"""Vendored presentation layer of the CariCOOS hub family.

  source : buoys-ops/buoylib.py  (sha256:a92504beb92affb6, 430 lines)
  copied : 2026-09-30
  by     : tools/../scratchpad/vendor_hublib.py  (re-run to re-vendor)

The bodies below are BYTE-IDENTICAL to buoylib.py so the Ocean Buoys Hub, the Wind
Stations Hub and this Maritime Dashboard read as one family. Do not edit them here.
Maritime-only additions (the suitability palette, the marine unit system, the page
shell) live in marlib.py instead, so tools/check_hublib_drift.py stays clean.

Why vendored and not imported: on dm2 these are independent folders with independent
crons sharing a venv a fourth project owns. A sys.path hack into another clone means a
buoylib refactor silently breaks the maritime cron at 03:00, with no test and no owner.

!! localStorage is per-ORIGIN, not per-path. dm2.caricoos.org/Buoys_Dashboard/ and
!! dm2.caricoos.org/Maritime_Dashboard/ share one store, so the key below is
!! deliberately still 'buoys_lang': a user who picked Spanish on the Buoys Hub arrives
!! here already in Spanish. That is a feature. Do not "clean up" the name.
"""
import os

THEME_CSS = r""":root{color-scheme:light;
  --surface:#d9e5ed; --panel:#f1f6f9; --ink:#122a3a; --ink2:#51677a; --grid:#dbe6ec;
  --line:#c0d2dc; --s1:#2a78d6; --s2:#eb6834; --tip-bg:#f1f6f9; --tip-edge:#a9bfcc;
  --btn:#dfeaf1; --btn-on:#0b3a5c; --btn-on-ink:#ffffff; --sel:rgba(0,150,180,.15);
  --navy:#0b3a5c; --navy-ink:#ffffff; --navy-sub:#9fc3d9; --teal:#0096b4;
  --controls:#e7f0f5; --flag:#c0392b; --flag2:#7c3aed; --ok:#1e8e5a;}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){color-scheme:dark;
    --surface:#101c26; --panel:#162733; --ink:#e8eef3; --ink2:#9db2c2; --grid:#25384633;
    --line:#2b4152; --s1:#3987e5; --s2:#d95926; --tip-bg:#1c2e3c; --tip-edge:#3c566a;
    --btn:#1c2e3c; --btn-on:#3ba7c4; --btn-on-ink:#08131b; --sel:rgba(59,167,196,.25);
    --navy:#092c46; --navy-ink:#e8eef3; --navy-sub:#7fa6bf; --teal:#3ba7c4;
    --controls:#14232e; --flag:#ff6f61; --flag2:#b794f6; --ok:#4cc38a;}}
:root[data-theme="dark"]{color-scheme:dark;
  --surface:#101c26; --panel:#162733; --ink:#e8eef3; --ink2:#9db2c2; --grid:#25384633;
  --line:#2b4152; --s1:#3987e5; --s2:#d95926; --tip-bg:#1c2e3c; --tip-edge:#3c566a;
  --btn:#1c2e3c; --btn-on:#3ba7c4; --btn-on-ink:#08131b; --sel:rgba(59,167,196,.25);
  --navy:#092c46; --navy-ink:#e8eef3; --navy-sub:#7fa6bf; --teal:#3ba7c4;
  --controls:#14232e; --flag:#ff6f61; --flag2:#b794f6; --ok:#4cc38a;}
"""


LANG_CSS = r"""html[data-lang="es"] .lang-en{display:none !important}
html:not([data-lang="es"]) .lang-es{display:none !important}
.langbtn{font:600 .78rem "Archivo",sans-serif; letter-spacing:.06em; border:1px solid rgba(255,255,255,.45);
  background:transparent; color:var(--navy-ink,#fff); padding:.22rem .7rem; border-radius:999px; cursor:pointer}
.langbtn:hover{background:rgba(255,255,255,.12)}
"""


LANG_BOOT_JS = ("<script>(function(){var l='en';try{l=localStorage.getItem('buoys_lang')||"
                "((navigator.language||'').toLowerCase().indexOf('es')===0?'es':'en');}catch(e){}"
                "document.documentElement.setAttribute('data-lang',l);document.documentElement.lang=l;})();</script>")


LANG_JS = r"""
const LKEY='buoys_lang';
let L=document.documentElement.getAttribute('data-lang')||'en';
function T(k){const d=(typeof I18N!=='undefined')&&I18N[k];return d?(d[L]||d.en||k):k;}
function applyI18n(){
  document.querySelectorAll('[data-i18n]').forEach(e=>{const k=e.dataset.i18n;if(typeof I18N!=='undefined'&&I18N[k])e.innerHTML=T(k);});
  document.querySelectorAll('[data-i18n-title]').forEach(e=>{e.title=T(e.dataset.i18nTitle);});
  document.querySelectorAll('.langbtn').forEach(b=>{b.textContent=L==='es'?'English':'Español';});
  document.title=T('title')==='title'?document.title:T('title');
}
const NOTE_ES=[["stale since","sin datos desde"],["redeploy pending","redespliegue pendiente"],["off station","fuera de estación"],["offline since","fuera de línea desde"],["retired","retirada"],["inactive","inactiva"]];
function noteT(n){if(L!=='es'||!n)return n;for(const [a,b] of NOTE_ES)n=n.split(a).join(b);return n;}
function setLang(l){L=l;try{localStorage.setItem(LKEY,l);}catch(e){}
  document.documentElement.setAttribute('data-lang',l);document.documentElement.lang=l;
  applyI18n();if(typeof onLang==='function')onLang();}
document.querySelectorAll('.langbtn').forEach(b=>b.onclick=()=>setLang(L==='es'?'en':'es'));
applyI18n();
"""


LANG_BTN = '<button class="langbtn" type="button" title="English / Español">Español</button>'


TZ_JS = r"""
const ZKEY='buoys_tz';
let Z='UTC';try{Z=localStorage.getItem(ZKEY)||'UTC';}catch(e){}
const TZOFF=()=>Z==='AST'?-4*3600:0;
function fmtTZ(epoch,withY){const d=new Date((epoch+TZOFF())*1000).toISOString();return (withY?d.slice(0,10):d.slice(5,10))+' '+d.slice(11,16);}
function tzShiftStr(s){ /* 'YYYY-MM-DD HH:MM' (UTC) -> same in the active zone; date-only strings untouched */
  if(!s||s.length<16||Z==='UTC')return s;const t=Date.UTC(+s.slice(0,4),+s.slice(5,7)-1,+s.slice(8,10),+s.slice(11,13),+s.slice(14,16))/1000;return fmtTZ(t,true);}
function tzLabel(){return Z==='AST'?'AST (UTC−4)':'UTC';}
function setTZ(z){Z=z;try{localStorage.setItem(ZKEY,z);}catch(e){}
  document.querySelectorAll('.tzbtn').forEach(b=>{b.textContent=Z;});if(typeof onTZ==='function')onTZ();}
document.querySelectorAll('.tzbtn').forEach(b=>{b.textContent=Z;b.onclick=()=>setTZ(Z==='UTC'?'AST':'UTC');});
"""


TZ_BTN = '<button class="tzbtn" type="button" title="UTC / AST (UTC−4)">UTC</button>'


NOTE_ES = [("stale since", "sin datos desde"), ("redeploy pending", "redespliegue pendiente"),
           ("off station", "fuera de estación"), ("offline since", "fuera de línea desde"),
           ("retired", "retirada"), ("inactive", "inactiva")]


FONTS_LINK = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700'
              '&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400&display=swap">')


def bi(en, es):
    """both languages of a static text; CSS shows the active one."""
    return f'<span class="lang-en">{en}</span><span class="lang-es">{es}</span>'


def es_note(n):
    """Spanish version of an operator status note from buoys.tsv."""
    for a, b in NOTE_ES:
        n = n.replace(a, b)
    return n


def atomic_write_parquet(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    df.to_parquet(tmp, engine="pyarrow", compression="zstd")
    os.replace(tmp, path)


def atomic_write_text(text, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
