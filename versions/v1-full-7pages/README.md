# CariCOOS Maritime Dashboard

Every other CARICOOS product answers *"what is the ocean doing?"*. This one
answers the next question: **"can I go, and if not now, when?"**

A bilingual (EN/ES) static hub for `dm2.caricoos.org/Maritime_Dashboard/`, sibling
to the [Ocean Buoys Hub](https://dm2.caricoos.org/Buoys_Dashboard/) and the
[Wind Stations Hub](https://dm2.caricoos.org/Mesonet_Dashboard/). It turns
observations and the official NWS marine forecast into a per-site, per-vessel-class
**Operational Suitability** read, and embeds the four existing CARICOOS tools for
drill-down.

Audience: commercial shipping and ports, ferries and passenger vessels, fishers
and small commercial craft, recreational boating.

## The rule this product is built around

**"Advisory", "warning" and "watch" are official National Weather Service product
names.** Nothing CariCOOS computes ever borrows them.

- **Ours** is **Operational Suitability** / *Idoneidad Operacional*, with the
  levels Favorable, Marginal, Unfavorable, No data, and Not rated here.
- **NWS products** appear in their own panel, verbatim, in English, attributed,
  with a link — never reworded, never machine-translated.
- **NWS products do not feed the scoring.** Suitability is computed from
  observations and forecast numbers alone. A site can read Favorable beside an
  active Small Craft Advisory; the panel makes the official product impossible to
  miss, and the two are never conflated.
- Every page carries **NOT FOR NAVIGATION / NO APTO PARA LA NAVEGACIÓN**.

`docs/VERIFY.md` has a terminology grep that gates every release.

## How it works

A Python batch pipeline that generates static HTML — same shape as `buoys-ops`.
No Flask, Dash, Streamlit, React or npm; cron runs the fetchers and generators,
and the wrappers `rsync` `web/out/` into the webroot.

```
config/*.tsv     the policy and the site list; code holds no thresholds
fetch/           network in  -> data/ (atomic writes + state/manifest.json)
engine/          pure logic  -> no I/O, so it can be proven by tools/check_ratings.py
pages/           data/ in    -> web/out/*.html ; generators NEVER touch the network
hublib.py        presentation layer vendored from buoys-ops/buoylib.py
marlib.py        maritime loaders, marine units, suitability palette, page shell
```

### Phase 1 needs no model data

The NWS Coastal Waters Forecast (`CWFSJU`) carries, per marine zone, a five-day
forecast with wind, gusts, seas, and a `Wave Detail:` clause giving wave
direction, height and **period**. Measured live: **10 zones, 100 periods, 100%
wind and sea-height coverage, 60% wave detail** (NWS publishes wave detail for
the first ~3 days only). That is Hs, Tp and Dp per zone out to five days, so the
suitability board and the planner both work before any WRF, WW3, SWAN or FVCOM
code exists. Those are a Phase 2 *nearshore resolution* upgrade, not a dependency.

### Thresholds are policy, not code

`config/thresholds.tsv` holds every limit with its citation. `methods.html`
renders that file verbatim, including the `source` column, so the published
methodology cannot drift from what the code does. Numbers not yet confirmed carry
`- VERIFY` in `source`, which stays visible on the published page until someone
checks them.

## Install

```bash
$PY -m pip install -r requirements.txt     # numpy pandas pyarrow netCDF4
cp config/machine.env.example config/machine.env
```

Phase 1 adds **no** dependency beyond what the Ocean Buoys Hub already installs,
so it deploys to dm2 without touching the venv `mesonet-ops` owns. All HTTP goes
through the standard library. Phase 2 (SWAN `.mat` parsing) needs `scipy`+`h5py`
and gets its own `.mar_env`.

On a dev machine set `DASHBOARD_WEBROOT=""` to disable publishing.

## Run

```bash
$PYTHON fetch/fetch_nws.py --zones     # CWF + active marine products + zone check
$PYTHON tools/check_ratings.py         # golden vectors, no network
$PYTHON tools/check_hublib_drift.py    # vendored code still matches buoylib
```

`--zones` re-confirms every site's marine zone against the API. Harbour
coordinates fall outside the marine polygons — Cruz Bay and Salinas both resolve
to *no* zone — which is what the `zone_lat`/`zone_lon` columns in `sites.tsv`
exist for.

## Editing the configuration

Everything a non-programmer needs to change lives in `config/`:

| file | what it controls |
|---|---|
| `sites.tsv` | the decision points on the board, their zone, feeding stations, embedded tool |
| `thresholds.tsv` | **the policy** — every Marginal / Unfavorable limit, with its citation |
| `sources.tsv` | station registry, including `max_age_h` staleness fallback |
| `routes.tsv` | ferry routes (Phase 2). Operators, speeds and roll periods are **estimates** |

`obs_*` columns are comma lists in **priority order**: the first source fresher
than its `max_age_h` wins, and the page names whichever one it used.

## Status

Phase 1 core complete and verified against live data: config layer, vendored
presentation layer, physics, rating engine, CWF parser, NWS fetcher. Pages,
observation fetchers and the cron wrappers are next — see `docs/VERIFY.md` for the
release gates and the plan for sequencing.
