#!/usr/bin/env bash
# Start the local chatbot dev server.
#
#   1. Put your key in chatbot/.env   (ANTHROPIC_API_KEY=sk-ant-...)
#   2. ./chatbot/run_local.sh
#
# .env is gitignored. The key is never written into code, a page, or a log.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/.." || exit 1

[ -f "$HERE/.env" ] && set -a && . "$HERE/.env" && set +a

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ANTHROPIC_API_KEY is not set."
  echo "Create one at https://console.anthropic.com -> API Keys, then:"
  echo "  echo 'ANTHROPIC_API_KEY=sk-ant-...' > chatbot/.env"
  exit 1
fi
[ -f web/out/chat_context.json ] || { echo "No snapshot yet - running the pipeline."; ./run_pages_now.sh; }

exec "$HERE/.venv/bin/python" "$HERE/local_server.py"
