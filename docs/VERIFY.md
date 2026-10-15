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

The two hubs load over HTTPS inside `tools.html` behind the click-to-load poster;
the Model Viewer loads eagerly on `model_viewer.html`, because a reader who opened
that tab has already asked for it. Every "Open in new tab" link resolves. None of
the four sends `X-Frame-Options` or a `frame-ancestors` CSP (verified), but
re-check if a page ever fails to frame.

The classic Model Viewer is `http://` only and therefore a link, never a frame,
on any https deployment. It sits under the Model Viewer tab rather than under
Data Analysis: both are model viewers.

`model_viewer.html` carries **no Ask panel** - no button, no markup, no script,
no CSS (`page_shell(..., chat=False)`). Check that the floating button is absent
there and still present on the other four, and that walking through that tab with
the panel open does not close it on the way back.

## 9. Locking and determinism

```bash
./run_pages_now.sh & ./run_pages_now.sh     # the second logs "skipping", exits 0
./tools/check_determinism.sh conditions:index zones:marine_zones \
    surf:surf_zone tools:tools modviewer:model_viewer
```
The determinism check masks the run timestamp, which appears **both** as footer
prose and as the `generated_utc` key inside the injected JSON payload. That
payload is one very long line, so masking only the footer makes every
payload-bearing page look non-deterministic when it is not.

**That mask is why the "Data as of" stamp writes the build time once, under that
exact key.** The stamp's `gen: true` row reads it back at render time instead of
carrying its own copy. A second, differently-named timestamp in the same payload
is not masked, and the page then differs on every run — this check caught exactly
that on the first pass when the stamp was added to the two NWS pages.

## 9b. The "Data as of" stamp

On the board, the NWS Marine Forecast and the NWS Surf Zone. Check on each:

- The issue line carries **day, month and year**, not just a time. Its absence was
  the original complaint: you had to scroll to the footer to learn whether what you
  were reading was from today.
- It follows the **UTC ⇄ AST** button and the **EN ⇄ ES** switch. A stamp frozen in
  UTC while the rest of the page reads AST is worse than no stamp.
- Past 45 minutes without a rebuild the frame turns amber and a warning appears
  under it. Force it with a generator run whose `utcnow()` is shifted back 3 hours.

The component is `marlib.STAMP_CSS` / `STAMP_HTML` / `stamp_js()`, shared by the
three pages. Its whole body sits inside an IIFE exposing only `paintStamp`,
because the board declares its own `hm12`, `fullDate`, `MON` and `ago` in the same
`<script>`: a second declaration of any of those is a `SyntaxError` that blanks
the page with nothing on screen to say why.

## 10. Mobile

Sweep **1440, 1024, 820, 768, 600, 480, 390, 360 and 320 px** on all five pages.
At every one of them `document.documentElement.scrollWidth` must equal
`clientWidth`: the page itself never slides sideways. A box that scrolls *inside
itself* is fine and is how the beach table survives 320 px.

- **820 px** is where the board stops being a table and becomes stacked cards.
  It used to be 760, which left 761&ndash;820 &mdash; a tablet held upright, a
  half-screen window &mdash; with a six-column table running off the right edge.
- In the stacked card the **place name comes first**, then the date. The row's
  own order is name-second, so this is a flex `order` on the phone only.
- **`tr` must NOT be in the `display:block` list.** It was, and it also unfolded
  the provenance drawers, which hide by being bare `tr`s. Every one of the 14 sat
  open from load; tapping still worked, so there was no symptom beyond a page
  that measured 9634 px instead of 5201. Check: at load, zero drawers have a
  height; one tap opens exactly one.
- The three header buttons are **44 px tall** below 720 px. They were 23.
- The tab bar carries scroll shadows that appear only on the side with more to
  see. Scroll it fully left and fully right and check the shadow swaps.
- On a **touch** profile (`hover:none`) the map legend must read "Board location"
  with no "hover for its name" &mdash; there is no cursor to hover with.

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
