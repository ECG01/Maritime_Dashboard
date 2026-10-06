#!/usr/bin/env bash
# Ask the local server a few real questions and show what came back.
# Each one costs money - this is six questions, not a loop.
set -u
U="${1:-http://127.0.0.1:8788}"
TOK="${CHAT_ACCESS_TOKEN:-local}"
echo "== health =="
curl -sS -m 20 "$U/health" | sed 's/^/  /'; echo
ask(){ echo; echo "== $1"; 
  curl -sS -m 120 -X POST "$U" -H 'content-type: application/json' \
    -H "x-chat-token: $TOK" -d "{\"question\":$(printf '%s' "$1" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}" \
    | python3 -c 'import json,sys
d=json.load(sys.stdin)
if "error" in d: print("  ERROR:", d["error"])
else:
    print("  " + d["answer"].replace("\n","\n  "))
    u=d.get("usage",{}); print(f"  [in={u.get(\"input\")} out={u.get(\"output\")} cache_read={u.get(\"cache_read\")}]")'
}
ask "¿Cómo está Fajardo ahora mismo?"
ask "Where are the smallest seas right now?"
ask "¿De qué estación viene el viento de Arecibo y hace cuánto se midió?"
ask "¿Qué dice el pronóstico del NWS para Vieques hoy?"
ask "¿Cuánto mide el oleaje en Marte?"
ask "Should I take my 22-foot boat out of Fajardo this afternoon?"
# Must scan the WHOLE run, name the mildest days, name the marine zone it used,
# and say the rip current category stops after two days - not call it low.
ask "¿Qué día de la semana es mejor para ir a la playa en el norte?"
# Must say no products are in effect AND still surface the rip current risk,
# in the NWS's own words, without calling the forecast an aviso.
ask "¿Hay algún aviso del NWS ahora?"
# Climatology. Must compare against the p10-p90 band, GIVE the band, and say the
# length of record - a 4-year percentile is a weaker claim than a 17-year one.
ask "¿1.5 m de oleaje es normal para finales de septiembre en Ponce?"
# Must use wind:AROP4, not buoy:, and give the storm with the date.
ask "What is the highest gust ever recorded in Arecibo?"
# Must read the monthly table and not slide into a forecast.
ask "¿Cuál es el mes más calmado del año en Ponce?"
# Must REFUSE: we hold climatology and records, not a history queryable by date.
# Answering this from a monthly average would be a different question.
ask "¿Cómo estuvo el mar el 3 de marzo de 2024 en San Juan?"
# Must lead with "stopped reporting in 2015" before quoting any number.
ask "What is the wind climatology at XAMA?"
