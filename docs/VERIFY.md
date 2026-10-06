# Release checklist

Run every item before publishing. Items marked **GATE** block a release.

## 1. Config integrity

```bash
$PYTHON -c "import marlib as M; p=M.validate(); print(p or 'CLEAN')"
```
Must print `CLEAN`. Every `obs_*`/`tide` reference must name a real row in
`sources.tsv`, every zone must be an `AMZ7xx`, every site must carry
`zone_lat`/`zone_lon`.

## 2. Rating core

```bash
$PYTHON tools/check_ratings.py        # exits 1 on any mismatch
$PYTHON tools/check_srf.py            # Surf Zone Forecast parser, exits 1 on any mismatch
$PYTHON tools/check_climatology.py    # embedded-payload reader, exits 1 on any mismatch
```
No network, no fixtures. If this fails, nothing else matters.

## 3. Vendored presentation layer

```bash
$PYTHON tools/check_hublib_drift.py
```
Drift means `buoylib.py` moved and the hubs will look different from each other.
Re-run `tools/vendor_hublib.py`, then re-check the pages.

## 4. **GATE** — terminology audit

The single rule this product is built around: **"advisory", "warning" and
"watch" are official National Weather Service product names.** What CariCOOS
computes is called **Operational Suitability** and never borrows those words.

```bash
grep -rniE 'advisor|warning|watch|aviso|advertencia|vigilancia' web/out/ \
  | grep -viE 'class="nws|nws-verbatim|NOT an official|no es un pron'
```
Every surviving hit must fall into one of exactly three legitimate categories:

1. **The verbatim NWS panel** — official product names, as issued.
2. **The disclaimer** — which uses the words in order to *deny* they apply to us
   ("It is **not** an official forecast, advisory or warning").
3. **The `source` column on `methods.html`** — where an NWS product is *cited as
   the origin of one of our thresholds* ("NWS SJU Small Craft Advisory band").
   Citing a product as a source is not claiming to be one.

Anything else is a release blocker, in either language.

## 5. **GATE** — the failure drill

A dashboard that blanks out when one API hiccups is worse than useless to
someone deciding whether to leave the dock.

```bash
cp config/machine.env /tmp/env.bak
sed -i 's#^NWS_API=.*#NWS_API="http://127.0.0.1:1"#' config/machine.env
./run_fetch.sh ; ./run_pages_now.sh
# every page must still build, showing the cached payload with a visible age badge
cp /tmp/env.bak config/machine.env
```
Repeat with `THREDDS_BASE`. **Any generator that raises on a missing source is a
bug**, not an acceptable failure mode.

## 6. Stale-source behaviour

`VI1` has been genuinely stale since 2026-07 and is first in `obs_wave` for
`CHAR_AM`, `CRUZ_BAY` and `STX_CHR`. Correct behaviour: those sites show a
"no recent wave observation" badge naming VI1, fall through to the CWF zone
forecast, and still rate wind from the mesonet. **Not** a blank row, and **not**
a stale Hs presented as current.

## 7. Toggles, on every page

- EN ⇄ ES flips static text, JS-built grid cells, tooltips and the best-window text.
- metric ⇄ marine changes the values **and the threshold limits printed in
  tooltips** — "limit 33 kt" must not read "limit 17.0 m/s" beside a knots value.
- UTC ⇄ AST shifts planner column headers and window text.
- First visit is Spanish when `navigator.language` starts with `es`.
- Language is shared with the Buoys Hub (same origin, key `buoys_lang`); units
  are not (key `maritime_units`, default `marine`).

## 8. Embedded tools

All four load over HTTPS inside `tools.html`, the click-to-load poster defers
them, and every "Open in new tab" link resolves. None of the four sends
`X-Frame-Options` or a `frame-ancestors` CSP (verified), but re-check if a page
ever fails to frame.

## 9. Locking and determinism

```bash
./run_pages_now.sh & ./run_pages_now.sh     # the second logs "skipping", exits 0
./tools/check_determinism.sh conditions:index zones:marine_zones tools:tools
```
The determinism check masks the run timestamp, which appears **both** as footer
prose and as the `generated_utc` key inside the injected JSON payload. That
payload is one very long line, so masking only the footer makes every
payload-bearing page look non-deterministic when it is not.

## 10. Mobile

390 px: the grid becomes a horizontal scroller with sticky row labels; chips stay
legible; the control bar un-pins.

## 11. Post-deploy smoke

```bash
for p in index marine_zones tools; do
  curl -o /dev/null -s -w "$p %{http_code}\n" \
    "https://dm2.caricoos.org/Maritime_Dashboard/$p.html"; done
curl -sI https://dm2.caricoos.org/Maritime_Dashboard/ | grep -i cache-control
grep -h WARN logs/run_*_$(date +%Y%m%d).log      # expect none
```

Note on caching: dm2 serves statics through nginx and the live Buoys Hub returns
**no** `Cache-Control` header despite shipping an `.htaccess` that sets one — so
`.htaccess` appears to be inert there. The pages therefore carry their own
`<meta http-equiv="Cache-Control">` and build-stamped asset query strings. If the
header is still absent after deploy, ask whoever runs dm2 for an nginx `location`
block rather than assuming the `.htaccess` took.

## 12. **GATE** — before first launch only

CARICOOS review of `methods.html` and the disclaimer wording, and confirmation of
every threshold still marked `- VERIFY` in `config/thresholds.tsv` (notably the
NWS San Juan Small Craft Advisory wind and sea criteria). Those numbers are
published on `methods.html` with their `VERIFY` tag visible until someone checks
them, which is deliberate.
