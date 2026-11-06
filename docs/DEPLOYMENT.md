# Deployment

Frontend on Vercel, API and worker on Render, database and storage on Supabase, sign-in by Clerk, AI by Gemini. Do these in order.

## 1. Supabase

1. Create a project. In **Database → Extensions** enable `vector` (the first migration also runs `CREATE EXTENSION IF NOT EXISTS vector`).
2. Copy the connection string for the **session pooler** (port 5432) or the direct connection. You need it twice:
   - `MIGRATION_DATABASE_URL`: as the `postgres` user. Used only by `alembic upgrade head`.
   - `DATABASE_URL`: as `evalai_app` (created by the migration; it cannot bypass row-level security). After the first migration run:
     ```sql
     ALTER ROLE evalai_app LOGIN PASSWORD '<strong password>';
     ```
     With the Supabase pooler the user name is `evalai_app.<project-ref>`.
   Tenant settings are transaction-local, so the transaction pooler also works, but the session pooler is recommended.
3. Run migrations from your machine or let Render run them (`preDeployCommand`):
   ```bash
   cd apps/api && MIGRATION_DATABASE_URL=... alembic upgrade head
   ```
4. Create the private bucket (and verify it is private):
   ```bash
   SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python scripts/setup_supabase.py
   ```
   The service-role key is used only by the API and worker. It must never be set on Vercel.

## 2. Clerk

1. Create an application with email sign-in and email verification on.
2. Note the **Frontend API URL** (e.g. `https://xxx.clerk.accounts.dev`): this is `CLERK_ISSUER`; `CLERK_JWKS_URL` is `<that>/.well-known/jwks.json`.
3. Set `CLERK_SECRET_KEY` on the API too: on first sign-in the API reads the user's verified primary email from the Clerk Backend API (the default session token has no email). Alternatively add `email` and `email_verified` claims in **Sessions → Customize session token**.
4. Add your Vercel domain to the allowed origins, and set `CLERK_AUTHORIZED_PARTIES` on the API to the same origin(s).

## 3. Gemini

Create a key at https://aistudio.google.com/apikey. Pick current model ids from https://ai.google.dev/models (checked November 2026: `gemini-3.8-flash` for generation and vision, `gemini-embedding-001` for embeddings). Keep `EMBEDDING_DIMENSIONS=768` unless you also change the column in a migration and re-index.

## 4. Render (API + worker)

`render.yaml` defines both services and a shared environment group. **New → Blueprint**, point it at the repository, then fill every `sync: false` value:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `evalai_app` connection string |
| `MIGRATION_DATABASE_URL` | owner connection string |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | from Supabase → Settings → API |
| `CLERK_ISSUER`, `CLERK_JWKS_URL`, `CLERK_SECRET_KEY`, `CLERK_AUTHORIZED_PARTIES` | from step 2 |
| `BOOTSTRAP_ADMIN_EMAILS` | your email; that account can create the first institution |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL` | from step 3 |
| `CORS_ORIGINS` | `https://your-app.vercel.app` |
| `PUBLIC_API_URL` | the API's public URL |

`APP_SIGNING_SECRET` is generated. Health check: `GET /health`. The worker must run: without it documents stay "Uploaded" and answer sheets stay "Submitted". Missing configuration shows up as HTTP 503 with the variable to set, rather than as fake success.

## 5. Vercel (web)

Import the repository with **Root Directory** `apps/web` (framework Next.js). Environment variables:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key |
| `CLERK_SECRET_KEY` | Clerk secret key (used by the route proxy) |
| `NEXT_PUBLIC_API_URL` | Render API URL |

Never set `NEXT_PUBLIC_AUTH_MODE` on Vercel; it exists for local browser tests.

## 6. First run

1. Sign up with an email in `BOOTSTRAP_ADMIN_EMAILS`. You land on "not part of an institution yet".
2. Create an institution: `POST /api/v1/admin/institutions` (or Admin → Overview once a membership exists). The demo seed also creates one.
3. Invite teachers and students from **Admin → People**. They join by signing up with the invited email.
4. Optional demo data: `cd apps/api && DATABASE_URL=<owner url> python ../../scripts/seed.py` (set `DEMO_*_EMAIL` to addresses you can sign up with). Seeded records are labelled "Sample data" and were not produced by AI.

## Local development

```bash
docker compose up -d db                       # or any Postgres 16 with pgvector on :54329
cp .env.example apps/api/.env                 # fill in; STORAGE_PROVIDER=local is fine locally
cd apps/api && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
alembic upgrade head && psql ... -c "ALTER ROLE evalai_app LOGIN PASSWORD 'dev'"
uvicorn app.main:app --reload                 # API on :8000, docs at /docs
python -m app.worker                          # second terminal
cd apps/web && npm install && npm run dev      # web on :3000 with apps/web/.env.local
```

Tests: `cd apps/api && pytest` (needs Postgres with pgvector; `TEST_PG=host:port`), `cd apps/web && npm test`, and the browser acceptance run `bash scripts/e2e_stack.sh up && cd apps/web && npm run e2e` (set `PW_CHROMIUM_PATH` if your Playwright browser build differs).
