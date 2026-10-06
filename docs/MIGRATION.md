# Moving the Maritime Dashboard to another server

A runbook for standing this up on a machine it has never run on. Every step below
was executed end to end on 2026-09-30 by restoring a bundle into a clean directory
and running the whole pipeline against the real upstream APIs — the gotchas in the
last section are things that actually happened during that rehearsal, not things
someone imagined.

Budget about **an hour** for the dashboard, plus half an hour if the chatbot Worker
goes up at the same time.

---

## 1. What this thing is, in one paragraph

A Python batch pipeline that writes static HTML. Cron runs fetchers, which cache
JSON under `data/`; cron runs generators, which read that cache and render
`web/out/`; a wrapper `rsync`s `web/out/` into the web server's document root.
There is no application server, no database, no build step and no npm. **The web
server only ever serves files from a directory.** If the target can serve a folder
over HTTPS and run cron, it can host this.

The chatbot is the one piece that is *not* static. It is a Cloudflare Worker, which
lives nowhere near the dashboard host — see §7.

---

## 2. What has to move, and what regenerates

| | | |
|---|---|---|
| **Must move** | the source tree | code, the config TSVs, the wrappers, docs |
| | `logs/events.jsonl` | **the only irreplaceable file.** Usage analytics history. Nothing regenerates it, and losing it loses the record of what people have used. |
| | `data/climo/climatology.json` | carried on purpose — see §6, this is what keeps the chatbot's historical answers working on a host that does not have the sibling hub checkouts |
| | `data/nws/`, `data/tides/` | seed caches, so the first page build has something to render before the first fetch lands |
| **Recreate by hand** | `config/machine.env` | paths, the webroot, the sibling directories. Different on every machine — that is the entire point of the file. |
| | `chatbot/.env` | the Anthropic API key. Never travels in a bundle. |
| **Regenerates itself** | `web/out/` | one pipeline run |
| | `state/manifest.json` | fetch bookkeeping. Deliberately *not* carried: a manifest from the old host reports fetch ages that never happened on the new one. |
| | `chatbot/.venv/` | platform-specific; `chatbot/run_local.sh` rebuilds it |
| | `chatbot/rules.generated.ts` | `node chatbot/build-rules.mjs` |
| | `__pycache__/` | compiled for a different interpreter |

`tools/make_migration_bundle.sh` encodes exactly this split. It produced a **252 KB**
tarball from a 44 MB working tree — almost all of the difference is `chatbot/.venv`,
which must not travel.

---

## 3. What the target machine needs

**Verified working set** (this is what the rehearsal ran on; older is probably fine,
but these are the versions with evidence behind them):

| | |
|---|---|
| Python | **3.12.3** |
| `netCDF4` | 1.7.4 |
| `numpy` | 2.3.5 |
| `shapely` | 2.1.2 |

That is the whole dependency list. Everything else is the standard library — all
HTTP goes through `urllib`, so there is no `requests`. `pandas` and `pyarrow` are
**not** needed; an earlier `requirements.txt` listed them and was wrong, which
would have meant installing two heavy packages for a function nothing calls.

**Shell tools the wrappers use:** `flock`, `rsync`, `find`, `date`, `mkdir`, `cp`.
`flock` is the one worth checking — it is what stops two cron cycles colliding, and
it is missing from some minimal container images.

**Outbound network.** The host must be able to reach these. If it sits behind a
proxy or an egress firewall, this is the list to get allowed:

| host | what for | breaks what if blocked |
|---|---|---|
| `dm1.caricoos.org` | THREDDS/OPeNDAP | every instrument reading; the board falls back to forecast everywhere |
| `api.weather.gov` | CWF, alerts, Surf Zone Forecast, zones | the whole NWS forecast page and the products panel |
| `api.tidesandcurrents.noaa.gov` | CO-OPS tides | the tide column |
| `www.ndbc.noaa.gov` | NDBC fallback | a fallback only |
| `dm2.caricoos.org` | climatology over HTTP (§6) | historical answers degrade |

`api.weather.gov` **requires a descriptive `User-Agent`** or it returns 403. It is
set as `NWS_USER_AGENT` in `machine.env`; do not blank it.

**Inbound:** only whatever serves the webroot over HTTPS. Nothing listens on a port.

---

## 4. The procedure

### 4.1 On the machine you are leaving

```bash
cd /path/to/Maritime_Dashboard
./tools/make_migration_bundle.sh ~          # writes ~/maritime-dashboard-<stamp>.tar.gz
```

It prints what it carried and what it deliberately left out. Read that output — if
it says `NO  logs/events.jsonl`, stop and find out why before continuing.

Copy the tarball across however you normally move files (`scp`, `rsync`, a shared
drive). It is small enough to email.

### 4.2 On the new machine

```bash
sudo mkdir -p /srv/maritime            # or wherever this project will live
sudo chown "$USER" /srv/maritime
tar -xzf maritime-dashboard-<stamp>.tar.gz -C /srv/maritime
cd /srv/maritime
```

Python environment — its **own** venv, not one another project owns:

```bash
python3 -m venv .mar_env
./.mar_env/bin/pip install -r requirements.txt
./.mar_env/bin/python -c "import netCDF4, numpy, shapely; print('deps OK')"
```

> Sharing a venv with a neighbouring project is how a dependency bump in one cron
> job breaks another at 03:00. If the target already has a scientific venv and you
> are tempted to reuse it, at least confirm nobody else upgrades it.

### 4.3 Write `config/machine.env`

```bash
cp config/machine.env.example config/machine.env
```

Then edit. These are the ones that are wrong by default on every new machine:

| key | set it to |
|---|---|
| `BASE_DIR` | the absolute path of this checkout, e.g. `/srv/maritime` |
| `PYTHON` | `/srv/maritime/.mar_env/bin/python` |
| `DASHBOARD_WEBROOT` | the web server's document root for this site. **Empty disables publishing** — leave it empty for a first dry run. |
| `HUB_URL` | the public URL the dashboard will answer on |
| `BUOYS_OPS_DIR`, `MESONET_OPS_DIR` | the sibling hub checkouts if they are on this machine; **empty if not** (see §6) |
| `CHAT_WORKER_URL` | the deployed Worker URL, or empty — empty means the Ask button is never drawn |
| `ANALYTICS_URL` | where `/event` is served, or empty for no analytics |

Leave the four `*_HUB_URL` / `*_VIEWER_URL` tool links as absolute `https://`
URLs. They are absolute on purpose: relative ones only resolve when this hub sits
beside the others on dm2, and they 404 silently anywhere else.

### 4.4 Dry run with publishing off

With `DASHBOARD_WEBROOT=""`:

```bash
./run_fetch.sh   && tail -20 logs/run_fetch_$(date +%Y%m%d).log
./run_daily.sh   && tail -20 logs/run_daily_$(date +%Y%m%d).log
./run_pages_now.sh
./run_pages_forecast.sh
grep -h WARN logs/run_*_$(date +%Y%m%d).log     # expect nothing
```

Then run the self-tests — they need no network and no data:

```bash
./.mar_env/bin/python tools/check_ratings.py
./.mar_env/bin/python tools/check_srf.py
./.mar_env/bin/python tools/check_climatology.py
./.mar_env/bin/python tools/check_hublib_drift.py
```

`check_hublib_drift` reports "sibling absent" rather than failing when the Ocean
Buoys Hub is not on this machine. That is correct.

### 4.5 Turn publishing on

Set `DASHBOARD_WEBROOT` to the real document root, re-run `./run_pages_now.sh`,
and confirm the webroot contains `index.html`, `marine_zones.html`, `tools.html`,
`board.json`, `chat_context.json`, `assets/` — **and does not contain
`analytics.html` or `analytics.json`.** Those are excluded on purpose; see §8.

### 4.6 Install cron

```cron
*/10 * * * *        cd /srv/maritime && ./run_fetch.sh
2-59/10 * * * *     cd /srv/maritime && ./run_pages_now.sh
5,35 * * * *        cd /srv/maritime && ./run_pages_forecast.sh
35 3 * * *          cd /srv/maritime && ./run_daily.sh
```

Pages run two minutes behind the fetch that feeds them. Each wrapper holds its own
`flock`, so an overlapping start skips that cycle instead of two runs fighting over
the same output — that is by design and a skipped cycle in the log is not a fault.

**Check the server's timezone.** The wrappers are timezone-agnostic, but `35 3 * * *`
means something different on a UTC box than on an AST one. Nothing breaks either
way; you just want to know when the daily job actually runs.

### 4.7 Web server

Serve the directory. Nothing else. Two things worth setting:

- **`Cache-Control: no-cache`** on `*.html` and `*.json`. The pages carry a
  `<meta http-equiv="Cache-Control">` as a fallback, but a real header is better.
  Note that on dm2 the shipped `.htaccess` is inert — nginx serves the statics
  directly and never reads it — so do not assume the file is doing anything.
- **HTTPS.** The classic Model Viewer is linked over `http://` on purpose (its S3
  imagery only answers over HTTP), and `tools.html` already detects mixed content
  and offers it as a link instead of an iframe. That is handled; do not "fix" it.

---

## 5. Target-specific values — the CARIBE server

### 5.1 Two constraints that will bite before anything else

**Do not add an nginx `server` block.** Caribe's port 80 is owned by
`/etc/nginx/sites-available/caricoos` with `server_name "_"` as the
`default_server`. A second block with an exact `server_name` — *including a
literal IP* — always beats `default_server` and **silently steals that site's
traffic**. This is written down in
`CARICOOS_ASSETS_DASHBOARD/deploy/nginx/caricoos-dashboard.conf`, which hit it.
The Maritime Dashboard goes in as a `location` inside the existing site file:

The live site is one `server` block: `listen 80 default_server`, `server_name _`,
`root …/V2/data`, a server-level `try_files $uri @frontend` that sends every
unmatched path into the Model Viewer's SPA, plus `location @frontend` and
`location /db_monitor/`. A prefix `location` is matched before that server-level
`try_files`, so this slots in cleanly:

```nginx
# inside the existing server { ... } in /etc/nginx/sites-available/caricoos
location /Maritime_Dashboard/ {
    alias /raid/ecruz/maritime_web/;
    index index.html;
    try_files $uri $uri/ =404;
    add_header Cache-Control "no-cache, must-revalidate";
}
```

**Both trailing slashes are load-bearing** — `location /Maritime_Dashboard/` and
`alias …/maritime_web/`. Drop either and the paths concatenate wrongly and every
request 404s. No nested regex `location` inside an `alias` block; a flat
`add_header` on the whole location is simpler and avoids a known nginx quirk.

Verified after reload: all pages 200, `analytics.html` **404**, the header
present, title `Conditions now · CariCOOS Maritime` — and, the check that
matters, `/` still served the Model Viewer and `/db_monitor/` still answered 200.

Getting this wrong takes the Model Viewer down, not just this dashboard.

**The box can run out of memory.** From
`CARICOOS_Model-dashboard_V2/etl/scripts/run_model_etl.sh`: *"SWAN and FVCOM must
never run at the same time on this box - real OOM/swap risk, confirmed live in a
2026-08-13 investigation"*. Our pipeline is far lighter — a few OPeNDAP tail-reads
and some string formatting, no model grids — but it runs **every 10 minutes**, so
it will overlap those ETL jobs regularly. Two consequences: keep our cron minutes
off the `*/15` and `*/30` marks the ETL uses, and if anything here ever grows a
heavy step, that box is the wrong place for it.

### 5.2 CARIBE — surveyed on the box, 2026-09-30

| | value |
|---|---|
| Host | `caribe`, `136.145.116.150` (UPR/UPRM) |
| Login | `ecruz`, username + password (no key on the WSL box) |
| OS | **Ubuntu 20.04.6 LTS**, kernel 5.4 |
| System Python | **3.8.10 — too old, see 5.3** |
| Timezone | `America/Puerto_Rico` — **cron runs in AST** |
| Web server | nginx 1.18.0; one enabled site, `caricoos` |
| Model Viewer v2 | **confirmed here**: `/raid/ecruz/CARICOOS_Model_Viewer/CARICOOS_Model-dashboard_V2` |
| nginx roots in that site | `…/V2/data`, then `…/V2/dist`, then `/var/www/html` |
| Storage convention | `/raid/<user>/` — `ecruz`, `hxu`, `jtorres`, … |
| Tools | `flock`, `rsync`, `curl`, `tar`, `crontab`, `git`, `node` — all present |
| Outbound | **all five upstreams reachable.** No firewall blocker. |
| Disk | `/` 88% used (12 G free) · `/raid` 99% used (**194 G free of 11 T**) |

Suggested placement, following the box's own convention:

| | |
|---|---|
| Checkout | `/raid/ecruz/Maritime_Dashboard` |
| venv | `/raid/ecruz/Maritime_Dashboard/.mar_env` |
| Webroot | `/raid/ecruz/maritime_web` (rsync target, served by an nginx `location`) |
| Public path | `/Maritime_Dashboard/` on caribe's existing site |

**Do not put it on `/`** — 12 G free there, and this writes logs daily.

### 5.2b Run everything as `ecruz` — and why that is not optional

`uv` and its Python 3.12 live in `/home/ecruz`, which is mode `drwxr-x---`. No
other account can even traverse it. A venv created there is a symlink into that
tree, so **it only works for `ecruz`**, whatever the permissions on the project
directory say.

Two consequences, both of which cost time on 2026-10-01:

- **Install the crontab as `ecruz`.** Installed as anyone else it fails every ten
  minutes with `uv: command not found`, and nothing in that message hints at
  permissions.
- **Check who extracted the bundle.** `/raid/ecruz` is owned by **`hxu`**, not by
  `ecruz` despite the name, so a transfer and extraction done while logged in as
  `hxu` leaves the whole tree owned by `hxu` and `ecruz` cannot write to it.
  Fix with:

  ```bash
  sudo chown -R ecruz:ecruz /raid/ecruz/Maritime_Dashboard
  ```

  (`ecruz` is in the `sudo` group.) Shared ownership — `chown ecruz:hxu` plus
  `chmod -R g+w` plus `chmod g+s` on the directories plus `umask 002` — does work,
  but it does not let `hxu` *run* anything, for the reason above, and it fails
  quietly the first time someone creates a file under a different umask. One
  owner is the simpler contract.

Symptom guide: `ls -ld` showing `hxu hxu` on the project tree while you are
`ecruz` means the extraction ran under the wrong account. `find /home ... -name uv`
returning nothing while `uv` demonstrably worked yesterday means you are a
different user today — the permission errors are swallowed by `2>/dev/null`.

### 5.3 Python 3.8 is the one real blocker

The system interpreter is 3.8.10, from Ubuntu 20.04. The code itself is fine —
every file parses against 3.8 syntax, and no timestamp we parse carries the `Z`
suffix that 3.8's `fromisoformat` cannot read. **The libraries are the problem.**
Checked against PyPI on 2026-09-30:

| | latest | requires | newest that still builds for 3.8 |
|---|---|---|---|
| `numpy` | 2.5.3 | ≥3.12 | 1.24.4 *(2023)* |
| `netCDF4` | 1.7.4 | ≥3.10 | 1.7.2 |
| `shapely` | 2.1.2 | ≥3.10 | 2.0.7 |

So 3.8 would pin all three to old releases, in a combination nobody has tested
this project against. **Do not fight it — use `uv`, which is how the neighbouring
ETL on the same box already gets Python 3.12.** `CARICOOS_Model-dashboard_V2/etl`
pins `3.12` in `.python-version` and `requires-python = ">=3.12"`.

```bash
command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"          # cron does NOT have this
cd /raid/ecruz/Maritime_Dashboard
uv venv --python 3.12 .mar_env
uv pip install --python .mar_env/bin/python -r requirements.txt
```

uv downloads its own interpreter. No root, no system package, nothing else on the
box changes.

**`~/.local/bin` is not on cron's PATH.** The V2 ETL scripts export it explicitly
and say so in a comment — *"confirmed live this is missing from cron's minimal
environment"*. Our wrappers take `PYTHON` as an absolute path from `machine.env`,
so they sidestep it, but keep it in mind if anything ever shells out to `uv`.

### 5.4 Cron: stay out of the neighbour's way

Caribe's actual crontab (not what V2's SETUP.md documents):

```cron
45 02 * * *            run_model_etl.sh swan
25 10 * * *            run_model_etl.sh fvcom
01 6,11,16,22 * * *    run_wrf_etl.sh
*/15 * * * *           update_stations.sh
```

SWAN and FVCOM are already 8 hours apart, which matters because **they must never
overlap on this box — real OOM risk, documented from a live 2026-08-13
investigation.** Our pipeline is far lighter, but it runs every 10 minutes and
would otherwise land on `update_stations` at :00, :15, :30 and :45. Offset it:

```cron
3-59/10 * * * *     cd /raid/ecruz/Maritime_Dashboard && ./run_fetch.sh
5-59/10 * * * *     cd /raid/ecruz/Maritime_Dashboard && ./run_pages_now.sh
7,37 * * * *        cd /raid/ecruz/Maritime_Dashboard && ./run_pages_forecast.sh
40 3 * * *          cd /raid/ecruz/Maritime_Dashboard && ./run_daily.sh
```

Nothing collides with `*/15`, and the daily job at 03:40 AST sits between SWAN
(02:45) and WRF (06:01).

### 5.4b Deployed 2026-10-01 — the values that actually worked

| | |
|---|---|
| Checkout | `/raid/ecruz/Maritime_Dashboard`, owned `ecruz:ecruz` |
| venv | `.mar_env`, CPython 3.12.13 via `uv` |
| Libraries | netCDF4 1.7.4, numpy 2.5.3, shapely 2.1.2 |
| Webroot | `/raid/ecruz/maritime_web` (created with `sudo`, chowned to `ecruz`) |
| Public path | `http://<caribe>/Maritime_Dashboard/` |
| First run | 14 of 14 sites measured, 11/11 tide gauges, CWF 10 zones, SRF 12 beach zones |
| Climatology | **46 stations** with no sibling checkouts — bands over HTTP, monthly tables and records from the carried cache, exactly as designed |

**`/raid/ecruz` is owned by `hxu`,** so `ecruz` cannot create new directories in
it. The webroot needs one `sudo mkdir` + `chown`; the project directory only
needed a `chown` because it already existed.

**`sudo` does not work inside a pasted multi-line block.** The remaining pasted
lines become stdin, so `sudo` reads the next line as the password, fails, and
swallows the rest — with no prompt and no visible error. Every `sudo` step here
runs as its own single line. This cost a full round trip on 2026-10-01.

### 5.4c CARIBE IS NOT REACHABLE FROM THE INTERNET

Found 2026-10-01, after everything else was working. **Port 80 on
136.145.116.150 is blocked inbound from outside UPR.** The dashboard serves
perfectly to anyone on the university network and is invisible to everyone else.

It took a while to see because every test was made from inside: the dev laptop's
own public IP is `136.145.58.148` — the same `136.145.0.0/16` as caribe. The
browser worked, `curl` worked, and both were inside. **The first request that
genuinely came from outside was the Cloudflare Worker's, and it failed** with
`conditions data unavailable`, which is how this surfaced at all.

The decisive test costs ten seconds and needs no tooling: open the URL on a phone
**with Wi-Fi off**, on mobile data. Do that before believing any deployment on a
university or corporate network is public.

**CARICOOS already has a house pattern for this.** Verified the same day:

| | |
|---|---|
| `dm2.caricoos.org/Model_Viewer_v2/` | 200 |
| `dm2.caricoos.org/Ocean_Buoys/` | 200 |
| `dm2.caricoos.org/Wind_Stations/` | 200 |

`modviewer.caricoos.org` and `dm2.caricoos.org` resolve to the same AWS load
balancer. The Model Viewer computes on caribe and **mirrors to dm2**, which is
what its `npm run build:subpath` target exists for. Compute inside, serve outside.

Three ways forward, in the order they were considered:

1. **Open 80 and 443 inbound to caribe** — chosen 2026-10-01, pending the
   university's network team. Keeps everything where it already runs. Ask for
   both ports at once. **Caveat:** opening port 80 exposes everything that nginx
   serves on that box, including `/db_monitor/`, an internal Streamlit panel.
   Restrict it first with `allow 136.145.0.0/16; deny all;` inside its location.
2. **Mirror the published output to dm2** — the house pattern, and where the
   original plan put this hub. dm2 was heavily loaded at the time, which is why
   it was deferred. The established direction is **dm2 pulling from caribe** over
   rsync+ssh, as it already does for Sargassum data.
3. **A Cloudflare Tunnel** on caribe — outbound-only, no firewall change, free
   TLS. Cleanest technically, but a stable hostname needs a domain managed in
   Cloudflare, and `caricoos.org` is on AWS.

**Until one of these lands, the chatbot Worker cannot work**, because it runs on
Cloudflare and cannot reach `CONTEXT_URL`. Everything else about it is deployed
and correct.

### 5.5 nginx — a `location`, never a `server`

Confirmed on the box: one enabled site, `caricoos`, and it is the Model Viewer.
Add to that file, inside its existing `server { … }`:

```nginx
location /Maritime_Dashboard/ {
    alias /raid/ecruz/maritime_web/;
    try_files $uri $uri/ =404;
    location ~* \.(html|json)$ { add_header Cache-Control "no-cache"; }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

A second `server` block with an exact `server_name` — even a literal IP — beats
`default_server` and would silently take the Model Viewer's traffic.

### 5.4 How to collect it

Two scripts, both read-only, neither prints a secret:

| | |
|---|---|
| `tools/survey_target.sh` | the full survey. Run it over ssh with `ssh user@host 'bash -s' < tools/survey_target.sh` |
| `tools/survey_target_paste.sh` | 18 lines, for pasting straight into a PuTTY session when there is no easy file transfer |

**Both must run from a real terminal, not through an automation harness.** With
password authentication ssh reads the password from `/dev/tty`; with no
controlling terminal it falls back to `ssh-askpass`, which is usually not
installed, and the run dies with `ssh_askpass: No such file or directory`
followed by `Host key verification failed` — the same missing TTY also prevents
accepting the host key. On a first connection, ssh in interactively once to
accept the key, then the redirect form works.

---

## 6. Climatology when the sibling hubs are not on the target

The chatbot answers *is this normal?*, *what is January like?* and *what is the
record?* from data the Ocean Buoys Hub and the Wind Stations Hub compute. On a host
where those checkouts are **absent**, `fetch_climatology.py` falls back to HTTP —
and HTTP gives only **one of the four blocks**, because the hubs publish their
day-of-year bands inside a page but do not publish the monthly tables, the records,
or the period of record.

**This is why the bundle carries `data/climo/climatology.json`.** The fetcher merges
per block. With the cache present, the new host gets:

| block | source | freshness |
|---|---|---|
| day-of-year bands | HTTP from dm2, daily | current |
| monthly tables | the carried cache | as of the bundle |
| all-time records | the carried cache | as of the bundle |
| period of record | the carried cache | as of the bundle |

Verified on the rehearsal host: 46 stations, 43 monthly tables, 44 record sets,
`buoy:PR1` still carrying its 17-year record and the 8.16 m Hurricane María wave.

The three cached blocks are *historical* — a monthly mean over 17 years does not
move — so ageing is not a real problem. Refresh them by re-running
`fetch_climatology.py` on a machine that does have the checkouts and copying
`data/climo/climatology.json` across. Once a year is plenty.

If you delete that file on a host with no checkouts, the chatbot loses monthly
tables and records permanently and keeps only "is today normal". It will say so
rather than guess.

---

## 7. The chatbot Worker

The Worker is independent of the dashboard host: Cloudflare runs it, and it reads
the dashboard's published `chat_context.json` over HTTPS. Moving the dashboard does
**not** move the Worker — but it does change the URL the Worker reads.

```bash
cd chatbot
npm install
node build-rules.mjs                      # bakes system_prompt.md into rules.generated.ts
npx wrangler login
npx wrangler secret put ANTHROPIC_API_KEY  # a fresh key, not one that has been in a chat
npx wrangler secret put CHAT_ACCESS_TOKEN  # the shared gate; pick something long
npx wrangler deploy
```

**Then update `CONTEXT_URL` in `wrangler.toml`** to the new host's
`.../chat_context.json` and deploy again. It currently points at dm2; if the
dashboard moves and this does not, the chatbot answers confidently from whatever
snapshot is still sitting at the old URL, which is the worst failure mode available
— stale data with no symptom.

Finally set `CHAT_WORKER_URL` in `machine.env` to the deployed Worker URL and
rebuild the pages, or the Ask button will not appear.

**Before it is public**, two things are still open, and both are noted in
`chatbot/README.md`: the access token is a gate, not authentication, and there is
no per-IP rate limit, so anyone holding the token can spend the API budget. CORS is
`*`. Fine for an internal tool; not fine for a public one.

Cost, measured rather than estimated: the snapshot is **58,219 tokens**, a cold
question costs about **$0.15**, roughly **$27/month** at ~20 questions a day. If
that needs trimming, the largest single lever is the monthly climatology for wind
stations that feed no board site.

---

## 8. Gotchas found while rehearsing this

Each of these bit during the 2026-09-30 dry run and is fixed in the code — they are
recorded so a future migration does not rediscover them.

**`rsync` failed on the very first run.** On a fresh host `web/out/` does not exist
until a generator has run, and `rsync` errors on a missing source directory. The
first thing a new operator saw was a red error that meant nothing. All four
wrappers now `mkdir -p "$BASE_DIR/web/out"` before publishing.

**`analytics.html` leaked to the public webroot.** The `--exclude` was on
`run_pages_now.sh` only, and the other three wrappers publish too — so the operator
page reached the webroot anyway, by a path nobody looked at. All four now carry the
excludes. **If you add a publishing wrapper, add the excludes to it.**

**`requirements.txt` was wrong in both directions.** It listed `pandas` and
`pyarrow`, which nothing imports, and omitted `shapely`, which `fetch_zonegeo.py`
needs — so a by-the-book install produced a working-looking environment where the
zone map silently failed. The file is now derived from the actual import set.

**Two dev tools had absolute WSL paths baked in.** `tools/vendor_hublib.py` and
`tools/check_climatology.py` pointed at `/mnt/c/...` and `/mnt/d/...`, so they were
no-ops anywhere else. Both now read `BUOYS_OPS_DIR` / `MESONET_OPS_DIR` from
`machine.env` and say so plainly when it is unset.

**A test asserted a stricter threshold than the code it tested.** `check_climatology`
required an 80% band rate while the fetcher's real floor is 70%. An overnight
rebuild upstream moved the number to 79.7% and the test failed on healthy data. It
now asserts the fetcher's own constant. *Never let a test invent its own threshold
for live upstream data.*

**This project is not under version control.** There is a `.gitignore` but no `.git`,
so a migration is a file copy and there is no history to carry. Worth fixing —
`git init` and a first commit would make the next migration a `clone`.

---

## 9. Verifying it actually works

Server-side checks pass while pages render blank — that has happened on this project
before. **Open it in a browser.**

```bash
for p in index marine_zones tools; do
  curl -o /dev/null -s -w "$p %{http_code}\n" "https://<host>/<path>/$p.html"; done
curl -sI "https://<host>/<path>/" | grep -i cache-control
curl -s "https://<host>/<path>/board.json" | head -c 200
grep -h WARN logs/run_*_$(date +%Y%m%d).log        # expect none
```

Then in a browser, on the real URL:

- [ ] The board shows rows with real numbers, not dashes, and the provenance bar is green rather than amber
- [ ] Every cell says `medido · <station>` or `pronóstico NWS`
- [ ] EN ⇄ ES flips **everything**, including table cells built by JavaScript
- [ ] Units kt/ft ⇄ metric changes values *and* the limits inside tooltips
- [ ] UTC ⇄ AST shifts the times
- [ ] The NWS forecast page shows the zones, the Surf Zone Forecast panel and the map
- [ ] All four tools load on the tools page; the classic viewer appears as a link, not a broken frame
- [ ] `NOT FOR NAVIGATION / NO PARA LA NAVEGACIÓN` is visible in both languages on every page
- [ ] Terminology gate: `grep -riE 'advisor|warning|watch|aviso|advertencia|vigilancia' web/out/` — every hit must be inside a verbatim NWS quote, the NWS panel, a statement that no product is in effect, or a statement that our content is *not* one
- [ ] `analytics.html` is **not** reachable at the public URL
- [ ] If the chatbot is up: ask it something, and ask it *"is the data updated?"*

Leave it a full day, then check that the provenance bar has kept moving. A pipeline
that works once and then stops is the normal cron failure, and nothing on the page
shouts about it except that bar going amber.

---

## 10. If it goes wrong

Nothing here is destructive. The old host is untouched by any of this, so the
rollback is: point DNS or the web server back at the old document root, and turn the
new host's cron off.

The one thing that is not recoverable by re-running is `logs/events.jsonl`. Keep the
bundle until the new host has been up long enough that you would not miss it.
