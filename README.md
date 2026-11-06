# EvalAI

**Understand. Evaluate. Improve.**

EvalAI runs the examination lifecycle end to end: teachers upload course material and generate subjective papers with answer keys and rubrics; students write on paper and upload a scan; EvalAI reads the handwriting, marks each answer criterion by criterion against the approved rubric, and hands provisional marks to the teacher. After approval students see question- and topic-level feedback and can challenge a mark, which the teacher resolves with an AI recommendation and a full audit trail.

| | |
|---|---|
| Web | Next.js 16, React 19, TypeScript, Tailwind 4, Radix/shadcn-style components, TanStack Query, React Hook Form + Zod, Recharts, Framer Motion |
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, persistent Postgres job worker |
| Data | Supabase Postgres + pgvector with row-level security, Supabase Storage (private, signed URLs) |
| Auth | Clerk (JWT verified against JWKS in the API; roles stored in our DB) |
| AI | Gemini (structured JSON output, vision, embeddings), LangGraph workflows, LlamaIndex chunking and retrieval, PyMuPDF, OpenCV |

## Start here
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): set up Supabase, Clerk, Gemini, Render and Vercel; local development.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how the pieces fit and why.
- [docs/AI_EVALUATION.md](docs/AI_EVALUATION.md): generation, handwriting and the 12-step evaluation graph; how accuracy should be measured.
- [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md), [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md)
- [docs/BUILD_PROGRESS.md](docs/BUILD_PROGRESS.md): what is done, what was verified and how, and what is still open.

## Repository
```
apps/web        Next.js app (landing, teacher, student, admin)
apps/api        FastAPI app, models, migrations, worker, tests
ai_engine       provider interface, ingestion, retrieval, generation, handwriting, evaluation, challenges, analytics
scripts         seed, Supabase bucket setup, benchmark runner, e2e stack, test doubles (dev_stubs)
benchmarks      evaluation benchmark set (expected marks awaiting teacher review)
docs            documentation and openapi.json
```
