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
./run_fetch.sh            # NWS forecast + instrument observations + tides
./run_pages_now.sh        # rebuild the board
./run_pages_forecast.sh   # rebuild the NWS forecast page
./run_daily.sh            # zone outlines, tools page, zone re-check

$PYTHON tools/check_ratings.py         # golden vectors, no network
$PYTHON tools/check_hublib_drift.py    # vendored code still matches buoylib
$PYTHON tools/check_determinism.sh conditions:index zones:marine_zones tools:tools
```

## How often things update

```cron
*/10 * * * *        run_fetch.sh            # instruments (mesonet is ~5-minutely), tides, CWF
2-59/10 * * * *     run_pages_now.sh        # board, two minutes behind each fetch
5,35 * * * *        run_pages_forecast.sh   # NWS forecast page (CWF issues ~4x/day + amendments)
35 3 * * *          run_daily.sh            # zone outlines, tools page, zone re-check
```

The board also refreshes **itself**. A page left open polls `board.json` every three
minutes and swaps in new data without a reload, so an open tab is never more than a
few minutes behind the last build. It keeps an open row expanded across the refresh,
and it will not redraw while an embedded CARICOOS tool is loaded, because that would
tear down the map the user is looking at. If the poll fails, the page keeps the data
it has and says so; the provenance bar keeps ageing and turns amber on its own.

A cron entry is not required for any of this — without cron the pages are simply as
old as the last manual run, which the provenance bar states plainly.

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

## Usage analytics

`web/out/analytics.html` answers "which parts of the dashboard do people
actually open" — locations, tools and pages, ranked, with a 7 / 30 / all-days
filter and a table under every chart.

It runs on `logs/events.jsonl`, appended to by the `/event` endpoint. The pages
send an event only when `ANALYTICS_URL` is set in `config/machine.env`; unset —
the default — and they send nothing at all and the page says so. What is sent is
the page, the interaction name, a short label (a site id, a tool key, an href)
and the language. **No cookie, no visitor id, no session, no typed text.** The
usage page does not count itself.

Rebuilt by `run_pages_now.sh` alongside the board. It is deliberately **not in
the navigation** and **excluded from the publish rsync** — it is an operator
page and the log that feeds it lives on this machine. To publish it, drop the
two `--exclude` lines in `run_pages_now.sh`.

Locally: <http://127.0.0.1:8777/analytics.html>.

## The Surf Zone Forecast — and why it is here

`marine_zones.html` carries the NWS **Surf Zone Forecast** (SRF): rip current
risk and surf height for the 12 beach zones of Puerto Rico and the USVI, with
the risk categories quoted in the NWS's own words.

It has its own panel because **the alerts feed cannot show it.** A Low or
Moderate rip current risk is never issued as a product, so "no NWS products in
effect" can be perfectly true on a day when a Moderate risk — *life-threatening
rip currents are possible in the surf zone*, in the NWS's wording — is forecast
for every beach on the north coast. Only a **High** risk becomes a Rip Current
Statement, and that one does reach the alerts feed.

It is a **forecast, not an advisory**, and every surface says so: the panel, the
chat snapshot's `note`, and the assistant's rules. The terminology rule cuts both
ways — calling a forecast an advisory overstates it just as badly as calling our
own rating one.

Fetched by `fetch/fetch_nws.py` into `data/nws/srf.json`, parsed by
`engine/srf_parse.py`, covered by `tools/check_srf.py`. Like the CWF, a thin
parse (under 8 zones, or under 75% of zones with a day-one category) keeps the
cache rather than publishing a broken table.

## Climatology — read the hubs' numbers, never re-derive them

The chatbot can answer *is this normal?*, *what is January like?* and *what is the
record?* because `fetch/fetch_climatology.py` reads what the two sibling hubs have
already computed: day-of-year percentile bands, monthly tables, all-time records and
the period of record behind each. Buoys go back to 2009 (PR1, 17 years); wind
stations likewise, across 38 sites.

**It reads their outputs and never recomputes from the archives.** Both hubs apply
masking, outage windows and window rules this project does not implement, so
recomputing here would produce numbers that disagree with the published hubs by a
little — which is worse than having none, because a mariner who checks would find
CariCOOS contradicting CariCOOS.

Configured by `BUOYS_OPS_DIR` and `MESONET_OPS_DIR`, empty by default: with neither
set, no climatology block is emitted and the chatbot says it has no historical data.
Local files are preferred on every machine including dm2, because the HTTP fallback
serves only the day-of-year bands — the monthly tables, the records and the period
of record live in files the hubs do not publish.

Two things it will not do, on purpose: it holds **no history queryable by date** (ask
about 3 March 2024 and it points you at the Ocean Buoys Hub), and it labels every
retired or short-record station before quoting it — XAMA stopped reporting in 2015
and its climatology is still perfectly valid, but quoting it silently would mislead.

The fragile part is `engine/embedded_json.py`: the bands exist only inside another
project's generated HTML. It brace-balances the payload, asserts station counts, band
lengths and `p10 <= p50 <= p90`, and refuses anything else — a payload that parses but
means something else is far more dangerous than one that fails outright. Covered by
`tools/check_climatology.py`; a bad read keeps the previous cache and records the
failure in `state/manifest.json`.

Runs from `run_daily.sh`, not the 10-minute cycle.

## Moving this to another server

`docs/MIGRATION.md` is the runbook, and it was rehearsed rather than imagined: the
whole procedure was executed on 2026-09-30 by restoring a bundle into a clean
directory and running the pipeline against the real upstream APIs. Three bugs fell
out of that rehearsal and are fixed — `rsync` failing on a fresh host, the operator
analytics page leaking to the public webroot through three of the four wrappers,
and a `requirements.txt` that listed two packages nothing imports while omitting one
that `fetch_zonegeo.py` needs.

```bash
./tools/make_migration_bundle.sh ~      # ~250 KB; excludes secrets and the venv
```

The bundle carries `logs/events.jsonl` (the only irreplaceable file) and
`data/climo/climatology.json` (which keeps the chatbot's historical answers working
on a host that does not have the sibling hub checkouts). It deliberately leaves out
`config/machine.env` and `chatbot/.env`.
