#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Local dev server for the maritime chatbot - the Worker, on your machine.

Same contract as chatbot/worker.ts: POST JSON {question, history}, an
`x-chat-token` header, and it answers from web/out/chat_context.json. It reads
the system prompt from chatbot/system_prompt.md, which the Worker also builds
from, so testing here tests the wording that will ship.

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    chatbot/.venv/bin/python chatbot/local_server.py

Then set CHAT_WORKER_URL="http://127.0.0.1:8788" in config/machine.env and
rebuild the pages. The access token defaults to "local" here - it exists so the
local path exercises the same auth code the deployed one will.

This is a development server on 127.0.0.1. It is single-threaded, has no rate
limiting, and must not be exposed to a network.
"""
import datetime as dt
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


def _now():
    """Current UTC, from the standard library. This file deliberately does not
    import marlib - it is meant to run standalone."""
    return dt.datetime.now(dt.timezone.utc).isoformat()

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# Sonnet 5, matching the deployed Worker since 2026-09-25. Keep these two in step:
# testing locally on a different model than production tests the wrong thing.
MODEL = os.environ.get("CHAT_MODEL", "claude-sonnet-5")
EFFORT = os.environ.get("CHAT_EFFORT", "low")
MAX_TOKENS = 2000
MAX_QUESTION_CHARS = 600
MAX_HISTORY_TURNS = 8
TOKEN = os.environ.get("CHAT_ACCESS_TOKEN", "local")
PORT = int(os.environ.get("CHAT_PORT", "8788"))

CONTEXT = os.path.join(ROOT, "web", "out", "chat_context.json")
PROMPT = os.path.join(HERE, "system_prompt.md")

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "content-type,x-chat-token",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def rules():
    return open(PROMPT, encoding="utf-8").read().strip()


def context():
    """Re-read every request. The pipeline rewrites this file every cycle, and a
    dev server that answers from a snapshot it loaded at startup would quietly
    test stale data."""
    return open(CONTEXT, encoding="utf-8").read()


class Handler(BaseHTTPRequestHandler):
    server_version = "CariCOOSChatDev/1.0"

    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        for k, v in CORS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in CORS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        # a health check, so you can tell "server not running" from "server unhappy"
        if self.path.rstrip("/") in ("", "/health"):
            ok = os.path.exists(CONTEXT)
            return self._send({"ok": ok, "model": MODEL, "effort": EFFORT,
                               "context": CONTEXT if ok else "MISSING",
                               "has_key": bool(os.environ.get("ANTHROPIC_API_KEY"))})
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.rstrip("/") == "/event":
            return self._event()
        if self.headers.get("x-chat-token") != TOKEN:
            return self._send({"error": "unauthorized"}, 401)
        try:
            n = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send({"error": "bad json"}, 400)

        question = (body.get("question") or "").strip()
        if not question:
            return self._send({"error": "empty question"}, 400)
        if len(question) > MAX_QUESTION_CHARS:
            return self._send({"error": "question too long"}, 400)

        try:
            snapshot = context()
        except OSError:
            return self._send({"error": "conditions data unavailable "
                                        "- run ./run_pages_now.sh first"}, 503)

        try:
            import anthropic
        except ImportError:
            return self._send({"error": "anthropic SDK not installed in this venv"}, 500)

        history = (body.get("history") or [])[-MAX_HISTORY_TURNS:]
        client = anthropic.Anthropic()
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                output_config={"effort": EFFORT},
                system=[
                    {
                        "type": "text",
                        "text": f"{rules()}\n\nCONDITIONS SNAPSHOT (JSON):\n{snapshot}",
                        "cache_control": {"type": "ephemeral"},
                    },
                    # AFTER the cache breakpoint on purpose: this changes every
                    # request, and putting it inside the cached block would
                    # invalidate the whole prefix every single time. It is what
                    # lets the assistant say how old a reading actually is.
                    {"type": "text",
                     "text": f"Current time: {_now()} (UTC)."},
                ],
                messages=history + [{"role": "user", "content": question}],
            )
        except anthropic.AuthenticationError:
            return self._send({"error": "ANTHROPIC_API_KEY missing or invalid"}, 500)
        except anthropic.RateLimitError:
            return self._send({"error": "rate limited, try again shortly"}, 429)
        except anthropic.APIError as e:
            # A dead API key comes back as 503 "credential validation failed",
            # NOT the 401 you would expect - so a plain "upstream error 503"
            # reads like an Anthropic outage and sends you looking in the wrong
            # place. Say what it actually is.
            detail = str(getattr(e, "message", "") or e)
            if "credential" in detail.lower():
                print(f"  ! API key rejected: {detail}")
                return self._send(
                    {"error": "the API key in chatbot/.env is not valid any more "
                              "- replace it from console.anthropic.com"}, 500)
            print(f"  ! upstream {e.status_code}: {detail[:200]}")
            return self._send({"error": f"upstream error {e.status_code}"}, 502)

        if resp.stop_reason == "refusal":
            return self._send({"error": "the assistant declined this request"}, 422)

        answer = "".join(b.text for b in resp.content if b.type == "text").strip()
        u = resp.usage
        # Printed per request so you can watch what a question actually costs
        # while you are tuning the prompt.
        print(f"  in={u.input_tokens} out={u.output_tokens} "
              f"cache_read={getattr(u, 'cache_read_input_tokens', 0)} "
              f"cache_write={getattr(u, 'cache_creation_input_tokens', 0)}", flush=True)
        self._send({"answer": answer, "usage": {
            "input": u.input_tokens, "output": u.output_tokens,
            "cache_read": getattr(u, "cache_read_input_tokens", 0),
            "cache_write": getattr(u, "cache_creation_input_tokens", 0)}})

    def _event(self):
        """Append one usage event to logs/events.jsonl.

        No auth on purpose: this is a counter, and requiring a token would mean
        putting one in the page where anyone could read it. Nothing here
        identifies a person - page, event name, a short label, language, time.
        Anything longer than a label is truncated rather than stored, so a bug
        upstream cannot start writing free text into this file.
        """
        try:
            n = int(self.headers.get("content-length", "0"))
            if n > 2000:
                return self._send({"ok": False}, 413)
            ev = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send({"ok": False}, 400)
        row = {"received_utc": _now(),
               "page": str(ev.get("page") or "")[:40],
               "event": str(ev.get("event") or "")[:40],
               "label": (str(ev["label"])[:80] if ev.get("label") else None),
               "lang": str(ev.get("lang") or "")[:5]}
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        with open(os.path.join(ROOT, "logs", "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  event {row['event']:16s} {row['label'] or ''}", flush=True)
        # 204 so sendBeacon does not keep a body around
        self.send_response(204)
        for k, v in CORS.items():
            self.send_header(k, v)
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    if not os.path.exists(CONTEXT):
        print(f"WARNING: {CONTEXT} missing - run ./run_pages_now.sh first", flush=True)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY is not set - requests will fail", flush=True)
    print(f"maritime chat dev server on http://127.0.0.1:{PORT}  "
          f"model={MODEL} effort={EFFORT} token={TOKEN!r}", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
