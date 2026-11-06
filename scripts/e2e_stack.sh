#!/usr/bin/env bash
# Local end-to-end stack: real Postgres + pgvector, API, worker, Next.js production build.
# Clerk and Gemini are replaced by the HTTP test doubles in scripts/dev_stubs (see their docstrings).
# Usage: PG=127.0.0.1:54329 PY=/opt/venvs/api/bin/python scripts/e2e_stack.sh up|down
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PG=${PG:-127.0.0.1:54329}
PY=${PY:-python}
RUN=${E2E_DIR:-/tmp/evalai-e2e}
mkdir -p "$RUN"

down() {
  for f in "$RUN"/*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; done
  pkill -f "uvicorn app.main:app --port 8000" 2>/dev/null || true
  pkill -f "app.worker" 2>/dev/null || true
  pkill -f "next start -p 3000" 2>/dev/null || true; pkill -f "next-server" 2>/dev/null || true
  pkill -f "dev_stubs/(gemini_stub|test_identity)" 2>/dev/null || true
  sleep 1
}

if [ "${1:-up}" = "down" ]; then down; exit 0; fi
down
psql -h "${PG%:*}" -p "${PG#*:}" -U postgres -qc "DROP DATABASE IF EXISTS evalai_e2e WITH (FORCE)" -c "CREATE DATABASE evalai_e2e" >/dev/null
export ENVIRONMENT=development
export MIGRATION_DATABASE_URL="postgresql://postgres@$PG/evalai_e2e"
export DATABASE_URL="$MIGRATION_DATABASE_URL"
(cd "$ROOT/apps/api" && $PY -m alembic upgrade head >/dev/null)
psql -h "${PG%:*}" -p "${PG#*:}" -U postgres -d evalai_e2e -qc "ALTER ROLE evalai_app LOGIN PASSWORD 'e2e'" >/dev/null
export DATABASE_URL="postgresql://evalai_app:e2e@$PG/evalai_e2e"
export CLERK_ISSUER=https://evalai-test-identity.local CLERK_JWKS_URL=http://127.0.0.1:8788/jwks
export STORAGE_PROVIDER=local LOCAL_STORAGE_DIR="$RUN/storage" PUBLIC_API_URL=http://127.0.0.1:8000 APP_SIGNING_SECRET=e2e-secret
export GEMINI_API_KEY=e2e GEMINI_MODEL=stub-model GEMINI_EMBEDDING_MODEL=stub-embed GEMINI_BASE_URL=http://127.0.0.1:8787 AI_MAX_RETRIES=1
export CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000 WORKER_POLL_SECONDS=0.5 AI_RATE_LIMIT_PER_MINUTE=100
cd "$ROOT"
nohup $PY scripts/dev_stubs/test_identity.py serve --key "$RUN/key.pem" --port 8788 >"$RUN/identity.log" 2>&1 & echo $! >"$RUN/identity.pid"
nohup $PY scripts/dev_stubs/gemini_stub.py --port 8787 >"$RUN/gemini.log" 2>&1 & echo $! >"$RUN/gemini.pid"
(cd apps/api && nohup $PY -m uvicorn app.main:app --port 8000 >"$RUN/api.log" 2>&1 & echo $! >"$RUN/api.pid")
(cd apps/api && nohup $PY -m app.worker >"$RUN/worker.log" 2>&1 & echo $! >"$RUN/worker.pid")
(cd apps/web && nohup npx next start -p 3000 -H 127.0.0.1 >"$RUN/web.log" 2>&1 & echo $! >"$RUN/web.pid")
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/health >/dev/null && curl -sf http://127.0.0.1:3000 >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8000/health && echo " stack up in $RUN"
