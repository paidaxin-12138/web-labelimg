#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$ROOT/backend/.env" ] && [ -f "$ROOT/.env" ]; then
  cp "$ROOT/.env" "$ROOT/backend/.env"
fi
if [ ! -f "$ROOT/backend/.env" ] && [ -f "$ROOT/.env.example" ]; then
  cp "$ROOT/.env.example" "$ROOT/backend/.env"
fi

if command -v docker >/dev/null && [ "${USE_DOCKER:-}" = "1" ]; then
  docker compose up -d --build
  echo "Stack started. Open http://localhost"
  exit 0
fi

cd "$ROOT/backend"
python3 -m pip install -r requirements.txt -q
mkdir -p data/storage
PYTHONPATH=. python3 scripts/seed.py
PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

cd "$ROOT/frontend"
if [ ! -d node_modules ]; then npm install; fi
npm run dev &
WEB_PID=$!

echo "API: http://localhost:8000/docs"
echo "Web: http://localhost:5173"
echo "Default admin: admin@example.com / admin123"
wait $API_PID $WEB_PID
