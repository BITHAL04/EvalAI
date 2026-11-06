# Build progress

Last updated: 7 November 2026.

## Status in one paragraph

Every module in the specification is implemented and wired together. The complete acceptance workflow (18 steps, from teacher sign-in to a resolved challenge with updated results and audit history) passes through the real UI, API, worker, Postgres/pgvector database and storage in an automated browser test. **Two external services could not be reached from the build environment, so they were replaced by local HTTP test doubles during testing:** Clerk (sign-in UI and JWKS) and Google Gemini. The real integrations are implemented and the Gemini SDK's actual request and response format is exercised, but no real Gemini model has been called and no real Clerk sign-in has been performed. Supabase Storage was not reachable either; the same signed-URL contract was tested with the local storage provider.

## What was verified, and how

| Check | Result |
|---|---|
| Backend tests (`apps/api`, pytest, real Postgres 16 + pgvector, connecting as the least-privilege `evalai_app` role) | **34 passed**: JWT verification (bad signature, expiry, forged role claims), invitations, institution isolation in API *and* raw SQL under RLS, append-only history, CRUD, upload validation, document indexing and retry, generation, publishing, multi-page handwriting extraction, evaluation bounds, teacher review, approval gates, result visibility, challenges, analytics, resubmission policy and deadlines |
| AI engine tests (pytest, scripted provider) | Mark clamping and re-scoring, double counting, unexplained deductions, alternative wording, partial and missing concepts, invented error quotes discarded, low OCR flagged rather than penalised, diagram questions use page images, challenge marks capped and escalated, page assembly across continuations and failed pages, blueprint and rubric arithmetic, consistency checks |
| Frontend unit tests (Vitest) | **7 passed** |
| Type checking / lint | `tsc --noEmit` clean; ESLint 0 errors (2 warnings) |
| Production build | `next build` succeeds in Clerk mode and in test-auth mode |
| Browser acceptance (Playwright, `apps/web/e2e/acceptance.spec.ts`) | **6/6 passed**, covering all 18 acceptance steps through the UI |
| Migrations | `alembic upgrade head` on an empty database; downgrade paths written but not exercised |
| Seed | `scripts/seed.py` runs and is idempotent |

## Not verified (needs your credentials)

1. **Gemini quality.** Generation, transcription and marking quality are unknown until run with a real key. `scripts/run_benchmark.py` measures marking against `benchmarks/evaluation_set.json`, whose expected marks still need a teacher's review. No accuracy figure has been measured and none should be quoted.
2. **Gemini API details.** `response_json_schema` is sent through `google-genai` 3.0, which defaults to the `v1` endpoint. If the chosen model rejects JSON-schema output there, set `GEMINI_BASE_URL`/API version or switch models; failures surface as job errors, never as fake results.
3. **Clerk** sign-in, sign-up and the `proxy.ts` route protection with real keys.
4. **Supabase Storage** signed upload and download URLs (`app/core/storage.py:SupabaseStorage`) against a live project; run `scripts/setup_supabase.py`.
5. **Render and Vercel** deployments themselves.

## Modules

Done: authentication and RBAC, institutions and invitations, subjects, courses, enrolment, document ingestion (PDF, TXT, DOCX), RAG retrieval with source references, question bank, AI question/answer key/rubric generation with teacher review, exam PDF, publishing, student submission with previews and versioning, handwriting extraction, question mapping, 12-node evaluation, confidence, teacher review and approval, results publication, question and topic analysis, recommendations, consistency engine with reference-answer calibration, challenges with AI assessment and teacher decisions, notifications, persistent jobs, audit log, admin dashboards, landing page.

## Known limitations

- Scanned textbooks with no text layer are rejected at indexing with an explanation (no OCR fallback for reference material).
- Answer regions are model-reported descriptions, not pixel bounding boxes.
- Platform configuration is read-only in the admin UI; values are environment variables.
- Rate limiting is a per-user fixed window in Postgres.
- Supabase `anon`/`authenticated` roles are revoked from all tables; nothing in EvalAI uses Supabase client-side access.

## Environment requirements
See [DEPLOYMENT.md](DEPLOYMENT.md) and `.env.example`. Python 3.11+ (tested on 3.12), Node 20+ (tested on 22), Postgres 16 with pgvector.

## Deployment status
Configuration is ready (`render.yaml`, Vercel settings, Supabase scripts). Nothing has been deployed.
