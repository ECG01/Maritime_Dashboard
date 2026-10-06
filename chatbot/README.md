# CariCOOS Maritime chatbot

A Cloudflare Worker that answers questions about current marine conditions, so the
dashboard itself can stay static files on dm2. The browser talks to the Worker; the
Worker holds the API key and talks to Claude.

## What it can see

Exactly one file: `chat_context.json`, published beside the board and rebuilt by
`run_pages_now.sh` every cycle. It is a **curated snapshot**, not the project's
internal data - `data/nws/`, `data/obs/` and `data/tides/` never leave dm2.

Every value in it carries its provenance: which station, how many minutes old,
measured or forecast. The system prompt requires that provenance be quoted back in
every answer. That pairing is the point - the failure that matters here is not the
bot refusing to answer, it is the bot answering with a plausible sea state nobody
measured.

Currently ~28 KB (~7,700 tokens). Its size is a direct per-question cost, so keep it
lean; `PERIODS` in `pages/make_chat_context.py` is the biggest lever.

## Deploy

```bash
cd chatbot
npm install
npx wrangler secret put ANTHROPIC_API_KEY     # from console.anthropic.com
npx wrangler secret put CHAT_ACCESS_TOKEN     # any long random string
npx wrangler deploy
```

Secrets are set through `wrangler secret`, never in `wrangler.toml` - that file is
version-controlled.

Then point the page at the deployed URL. Test it:

```bash
curl -X POST https://caricoos-maritime-chat.<subdomain>.workers.dev \
  -H 'content-type: application/json' \
  -H 'x-chat-token: <CHAT_ACCESS_TOKEN>' \
  -d '{"question":"¿Cómo está Fajardo ahora mismo?"}'
```

## Access

While the bot is internal, the gate is a shared secret header (`x-chat-token`) -
that is a gate, not authentication. **Before this is public**, add real auth and a
per-IP rate limit; right now anyone holding the token can spend the API budget.

## Cost

Measured on `claude-sonnet-5`, from the `cache_creation_input_tokens` the API
reports on a real cold question:

| | tokens | cost |
|---|---|---|
| Full prompt (rules + snapshot), 2026-09-25 | 32,632 | |
| Full prompt, 2026-09-29 (+ Surf Zone Forecast, + daily rollup) | 43,785 | |
| Full prompt, **2026-09-29 (+ climatology)** | **58,219** | |
| Question on a **warm** cache | | ~$0.015 |
| Question that **writes** the cache | | **~$0.15** |

The snapshot grew 34% on 2026-09-29, when the Surf Zone Forecast and the
per-day forecast rollup were added. That is a deliberate trade: both exist
because questions that matter were unanswerable without them ("is there a rip
current risk?", "which day is calmest?"), and both were trimmed before shipping -
the outlook days' verbatim weather was cut because the Coastal Waters Forecast
already carries it, which alone saved 7k characters.

**The climatology cost 33%, not the 14% a character count predicted.** Dense
numeric JSON tokenises far worse than prose - digits, brackets and colons are
mostly one token each - so `chars/3.5` under-counts it badly. Measure with the
API's own `cache_creation_input_tokens`; do not estimate from file size. If the
bill needs trimming, the biggest single lever is the monthly table for the
wind stations that feed no board site.

The cache-write row is the one that decides the bill. The snapshot is rebuilt
every 10 minutes and the ephemeral cache lives 5, so a question arriving cold -
the normal case when someone opens the panel occasionally - pays roughly ten
times the warm price. Around 20 questions a day across 5 sessions is **roughly
$27/month** at the current size.

Do not quote the warm number on its own; it describes a burst, not typical use.
(An earlier version of this file did, and was wrong by 10x.)

Where the 32k goes:

```
forecast   19,054  62%   10 zones x 10 periods, with the NWS wording verbatim
sites       7,209  24%
stations    3,898  13%
tools etc     471   1%
```

Of the forecast, 7,436 tokens (24% of everything) are the four zones with no
board location: AMZ711, AMZ716, AMZ723, AMZ745. **Kept deliberately** (decided
2026-09-25) so the bot can still answer about the Anegada Passage and the
southwest coast, where CariCOOS has no site but people do ask.

The 10-minute rebuild cadence is also deliberate: the chatbot sees exactly what
the board sees. Slowing it to 30 minutes would raise the cache hit rate, at the
cost of the bot being behind the board on a page called "conditions now".

Levers if the bill ever matters: drop the four unused zones (-24%), drop the
verbatim NWS text for days 4-5 (-10%), or raise the snapshot interval. Sonnet was
chosen on 2026-09-25 after running the real questions on it; `claude-opus-5`
remains the fallback if answer quality regresses - change `MODEL` in both
`worker.ts` and `local_server.py` together.

`output_config.effort` is `"low"`. These are lookups over a small structured
snapshot, which is what low effort is for. Raise to `"medium"` if answers start
missing the point.

Watch `usage.cache_read` in the response. If it is 0 across repeated questions
within one data window, the prefix is being invalidated and even the warm figure
does not hold.

## Not yet tested

The Worker has never been run: this machine has no Anthropic credentials, no SDK
installed and no Cloudflare account configured. The data side is verified; the
Worker is reviewed code, not working code. Expect to iterate on the first deploy.
