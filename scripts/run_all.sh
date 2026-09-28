#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# DeciTrace AI — one-command local launch.
# Seeds the database, starts the API on :8000 and the UI on :5173.
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> DeciTrace AI — Evidence-Grounded Business Decision Engine"
echo

# --- environment ------------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    created .env from .env.example (no API key required)"
fi

# --- backend ----------------------------------------------------------------
cd backend
if [ ! -d .venv ]; then
  echo "==> Creating virtual environment"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing backend dependencies"
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "==> Seeding the synthetic database"
python -m app.data.seed

echo "==> Starting FastAPI on http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

# --- frontend ---------------------------------------------------------------
cd ../frontend
if [ ! -d node_modules ]; then
  echo "==> Installing frontend dependencies"
  npm install
fi

cleanup() {
  echo
  echo "==> Shutting down"
  kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo
echo "  API      http://127.0.0.1:8000"
echo "  API docs http://127.0.0.1:8000/docs"
echo "  App      http://127.0.0.1:5173"
echo
echo "==> Starting Vite dev server"
npm run dev
