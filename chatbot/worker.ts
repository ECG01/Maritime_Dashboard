/**
 * CariCOOS Maritime chatbot - Cloudflare Worker.
 *
 * The dashboard is static files on dm2 and must stay that way, so the API key
 * lives here instead: the browser talks to this Worker, the Worker talks to
 * Claude. The key never reaches a page.
 *
 * It reads ONE file - web/out/chat_context.json, published beside the board -
 * which is a curated snapshot, not the project's internal data files. Every
 * value in it arrives with its provenance (station, age, measured or forecast),
 * and the system prompt below requires that provenance be quoted back. That
 * pairing is the main defence against the failure that actually matters here:
 * a confident, invented sea state.
 */
import Anthropic from "@anthropic-ai/sdk";
// Generated from system_prompt.md - the single copy of the wording, shared with
// the local dev server. Run `node build-rules.mjs` after editing that file.
import { RULES } from "./rules.generated";

export interface Env {
  ANTHROPIC_API_KEY: string;
  /** Shared secret while the bot is internal to CARICOOS. */
  CHAT_ACCESS_TOKEN: string;
  /** Where chat_context.json is published. */
  CONTEXT_URL: string;
}

// Sonnet 5, chosen 2026-09-25 after testing the real questions on it locally -
// not a default. Roughly 60% cheaper per question than Opus 5 and the answers
// held up on the cases that matter here: provenance quoting, refusing to invent
// a sea state, and not sliding into a safety verdict. Revisit with the eval
// questions in smoke_test.sh before assuming it still holds after a prompt change.
const MODEL = "claude-sonnet-5";
/** Chat answers are short by design; this is a deliberate cost ceiling, not a guess. */
// Los tokens de RAZONAMIENTO cuentan contra max_tokens, tambien con
// effort "low". Con el tope en 2000 una respuesta se corto a media frase el
// 2026-10-06: el modelo gasto el presupuesto pensando y se quedo sin espacio
// para escribir. Subir el tope no encarece nada por si solo - solo se paga lo
// que de verdad se genera, y una respuesta tipica son ~200 tokens.
const MAX_TOKENS = 16000;
/** Re-fetch the snapshot at most this often. The pipeline rebuilds it every 10 min. */
const CONTEXT_TTL_S = 120;
const MAX_QUESTION_CHARS = 600;
const MAX_HISTORY_TURNS = 8;


interface Body {
  question?: string;
  history?: { role: "user" | "assistant"; content: string }[];
}

let cached: { at: number; text: string } | null = null;

async function loadContext(env: Env): Promise<string> {
  const now = Date.now();
  if (cached && now - cached.at < CONTEXT_TTL_S * 1000) return cached.text;
  const r = await fetch(env.CONTEXT_URL, { cf: { cacheTtl: CONTEXT_TTL_S } });
  if (!r.ok) throw new Error(`context ${r.status}`);
  const text = await r.text();
  cached = { at: now, text };
  return text;
}

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type,x-chat-token",
  "Access-Control-Allow-Methods": "POST,OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...CORS },
  });

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (request.method !== "POST") return json({ error: "POST only" }, 405);

    // Internal-only for now: a shared secret, not a login. Swap this for real
    // auth before the bot is exposed publicly.
    if (request.headers.get("x-chat-token") !== env.CHAT_ACCESS_TOKEN) {
      return json({ error: "unauthorized" }, 401);
    }

    let body: Body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "bad json" }, 400);
    }
    const question = (body.question ?? "").trim();
    if (!question) return json({ error: "empty question" }, 400);
    if (question.length > MAX_QUESTION_CHARS) {
      return json({ error: "question too long" }, 400);
    }

    let context: string;
    try {
      context = await loadContext(env);
    } catch (e) {
      // Log the real cause. Swallowing it meant a CONTEXT_URL that was
      // unreachable, 404ing, or blocked by the origin's firewall all looked
      // identical from the outside - and the one thing you need in order to
      // fix it was the one thing thrown away. `wrangler tail` shows this.
      console.error("loadContext failed", env.CONTEXT_URL, String(e));
      return json({ error: "conditions data unavailable" }, 503);
    }

    const history = (body.history ?? []).slice(-MAX_HISTORY_TURNS);
    const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY });

    try {
      const response = await client.messages.create({
        model: MODEL,
        max_tokens: MAX_TOKENS,
        // Lookups and comparisons over a small structured snapshot - this does not
        // need deep reasoning, and effort is the first cost lever. Raise to
        // "medium" if answers start missing the point.
        output_config: { effort: "low" },
        system: [
          {
            type: "text",
            // Rules and data cached together: the snapshot only changes when the
            // pipeline rebuilds it, so questions asked within the same data
            // window reuse the whole prefix.
            text: `${RULES}\n\nCONDITIONS SNAPSHOT (JSON):\n${context}`,
            cache_control: { type: "ephemeral" },
          },
          // AFTER the cache breakpoint on purpose: this changes every request,
          // and inside the cached block it would invalidate the whole prefix
          // each time. It is what lets the assistant say how old a reading is.
          { type: "text", text: `Current time: ${new Date().toISOString()} (UTC).` },
        ],
        messages: [...history, { role: "user", content: question }],
      });

      const answer = response.content
        .filter((b): b is Anthropic.TextBlock => b.type === "text")
        .map((b) => b.text)
        .join("")
        .trim();

      if (response.stop_reason === "refusal") {
        return json({ error: "the assistant declined this request" }, 422);
      }

      return json({
        answer,
        usage: {
          input: response.usage.input_tokens,
          output: response.usage.output_tokens,
          cache_read: response.usage.cache_read_input_tokens ?? 0,
          cache_write: response.usage.cache_creation_input_tokens ?? 0,
        },
      });
    } catch (error) {
      if (error instanceof Anthropic.RateLimitError) {
        return json({ error: "busy, try again in a moment" }, 429);
      }
      if (error instanceof Anthropic.AuthenticationError) {
        return json({ error: "server misconfigured" }, 500);
      }
      if (error instanceof Anthropic.APIError) {
        return json({ error: `upstream error ${error.status}` }, 502);
      }
      return json({ error: "unexpected error" }, 500);
    }
  },
};
