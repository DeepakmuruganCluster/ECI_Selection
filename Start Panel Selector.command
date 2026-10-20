#!/bin/zsh
# Double-click to start Panel Selector v2. It opens in your web browser.
# Leave this window open while you use it; close it (or press Ctrl+C) to stop.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "First start: setting up (needs internet, about a minute)…"
  python3 -m venv .venv && .venv/bin/pip install -q pyyaml pdfplumber pypdfium2 pytest || { echo "Setup failed."; read; exit 1; }
fi
PORT=8000
while lsof -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; do PORT=$((PORT + 1)); done
(sleep 1.5; open "http://127.0.0.1:$PORT/?tab=review") &
echo "Panel Selector v2 is running at http://127.0.0.1:$PORT — keep this window open."
.venv/bin/python webapp/server.py --port $PORT
