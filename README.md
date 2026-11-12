<div align="center">

# EvalAI

**Understand. Evaluate. Improve.**

An AI examination platform that writes question papers from your course material, reads handwritten answer sheets,
marks them criterion by criterion against a teacher-approved rubric, and hands every mark back to the teacher before
a student sees it.

![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/Postgres-16%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white)
![Gemini](https://img.shields.io/badge/AI-Gemini-8E75B2?logo=googlegemini&logoColor=white)
![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C)

</div>

![EvalAI landing page](docs/images/landing.png)

---

## Contents

- [Why EvalAI](#why-evalai)
- [Features](#features)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Running tests](#running-tests)
- [Deployment](#deployment)
- [Project structure](#project-structure)
- [Security and grading integrity](#security-and-grading-integrity)
- [Project status](#project-status)
- [Documentation](#documentation)

## Why EvalAI

Students still think best with a pen. What slows exams down is everything after the pen: reading hundreds of pages,
applying one rubric the same way to every student, explaining each mark, and handling disputes fairly.

EvalAI keeps the notebook and automates the rest, with one rule throughout: **the AI proposes, the teacher decides.**
It marks meaning rather than keywords, so a correct explanation in the student's own words earns the same credit as
the textbook phrasing.

## Features

**For teachers**
- Upload textbooks, lecture notes and past papers (PDF, TXT, DOCX). They are split into sections, embedded and indexed per subject.
- Generate a paper with a wizard: topics, reference documents, total marks, mark distribution (2, 3, 5, 8, 10, 15 or custom), difficulty mix and eight subjective question types.
- Every question comes with a model answer, expected concepts, a marking rubric whose criteria add up exactly to its marks, and the pages it was written from.
- Edit, delete, regenerate or add questions, recalculate totals, then publish. Nothing reaches students without that step.
- Review each answer sheet beside the original scan: corrected transcriptions, per-criterion marks, covered, partial and missing concepts, flagged answers, and a full version history.
- Calibrate with strong, average and weak reference answers, and get an exam-level consistency report (outliers, similar answers with different marks, systematic over- or under-grading).
- Resolve challenges with an AI recommendation, optionally adding the accepted alternative to the rubric as a new version.
- Class analytics: score distribution, question averages, topic performance, commonly missed concepts, misconceptions and re-evaluation statistics.

**For students**
- See published papers for enrolled subjects and download a printable PDF.
- Upload a scanned or photographed answer booklet as one PDF, with progress, page previews and a confirmation step.
- Track processing, then read results question by question: the answer as recognised, the original page, marks per criterion, concepts covered or missed, and a suggested stronger answer.
- Topic mastery, performance trend against the class average, and recommendations that separate *not understanding a concept* from *not explaining it well*.
- Challenge a specific criterion with reasoning and evidence, and follow it to a decision.

**For administrators**
- Invite teachers, students and administrators by email; manage access, subjects and courses.
- Institution statistics, evaluation quality (confidence, flagged answers, teacher changes), background job status and an append-only audit log.
- Platform administrators can create institutions, each fully isolated from the others.

## How it works

```mermaid
flowchart LR
    A[Teacher uploads<br/>course material] --> B[Index: chunk, embed,<br/>store in pgvector]
    B --> C[Generate paper,<br/>answer key, rubric]
    C --> D{Teacher reviews<br/>and publishes}
    D --> E[Student writes on paper,<br/>uploads PDF]
    E --> F[Read handwriting<br/>page by page]
    F --> G[12-step rubric<br/>evaluation]
    G --> H{Teacher reviews<br/>flagged answers, approves}
    H --> I[Student sees result<br/>and feedback]
    I --> J[Student challenges<br/>a mark]
    J --> K[AI recommendation]
    K --> L{Teacher decides}
    L --> I
```

### The evaluation graph

Marking is a sequence of separate, typed judgements run as a [LangGraph](https://github.com/langchain-ai/langgraph) workflow, not a single prompt that returns a number.

| # | Step | What it does |
|---|---|---|
| 1 | Answer extraction | Loads the recognised answer and its page references |
| 2 | Question understanding | What the question asks and the outcomes it tests; cached so every student is marked against the same reading |
| 3 | Rubric retrieval | Approved rubric, model answer, expected concepts and relevant course material |
| 4 | Concept identification | Concepts the answer actually demonstrates |
| 5 | Coverage | Covered, partially covered, missing, and valid alternatives outside the key |
| 6 | Correctness | Wrong facts, contradictions, misused terms, bad equations; quotes are checked against the answer and invented ones dropped |
| 7 | Relevance | Whether the answer addresses the question at all |
| 8 | Diagrams and equations | Assessed from the original page images, not only the transcription |
| 9 | Rubric scoring | Marks per criterion in 0.25 steps, each deduction explained |
| 10 | Consistency validation | Bounds, double counting, unexplained deductions, high marks for off-topic answers; one corrective re-score |
| 11 | Confidence | A review signal from recognition quality, evidence, rubric clarity and agreement |
| 12 | Feedback | Student-facing strengths and improvements that cannot change the marks |

Illegible or missing text is treated as a gap in the reading, not as missing knowledge: those answers go to the teacher instead of being scored low. Details are in [docs/AI_EVALUATION.md](docs/AI_EVALUATION.md).

## Architecture

A modular monolith: one web app, one API, one background worker and one database.

```mermaid
flowchart TB
    U[Browser] -- Clerk session --> W[Next.js on Vercel]
    W -- Bearer token --> API[FastAPI on Render]
    U -- short-lived signed URLs --> S[(Supabase Storage<br/>private bucket)]
    API -- verify JWT via JWKS --> CK[Clerk]
    API --> DB[(Postgres + pgvector<br/>row-level security)]
    API -- enqueue --> DB
    WK[Worker on Render] -- claim jobs --> DB
    WK --> S
    WK -- LangGraph workflows --> G[Google Gemini]
```

- **Tenancy:** every institution-owned row is protected by Postgres row-level security, and the API connects as a role that cannot bypass it. Queries filter explicitly as well.
- **Identity:** Clerk handles sign-in. The API trusts only a verified token's subject and verified email; roles live in the database.
- **Background jobs:** long AI work runs in a separate worker that claims jobs with `SELECT … FOR UPDATE SKIP LOCKED`. Jobs survive restarts, retry with backoff, are idempotent, and evaluation commits per question so a retry resumes instead of re-marking.
- **Replaceable parts:** the AI provider, storage provider and retrieval search are interfaces; changing the model is an environment variable.

More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, Radix UI (shadcn-style components), TanStack Query, React Hook Form + Zod, Recharts, Framer Motion, Lucide |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Uvicorn |
| Database | PostgreSQL 16 with pgvector (Supabase), HNSW cosine index |
| Auth | Clerk, JWT verification against JWKS, role-based access in the API |
| AI | Google Gemini (structured JSON output, vision, embeddings), LangGraph, LlamaIndex |
| Documents | PyMuPDF, python-docx, OpenCV, Pillow, ReportLab |
| Storage | Supabase Storage, private bucket, signed upload and download URLs |
| Testing | Pytest, HTTPX, Vitest, Testing Library, Playwright, ESLint, `tsc` |
| Deployment | Vercel (web), Render (API and worker), Supabase (database and storage) |

## Getting started

### Prerequisites

- Node.js 20+
- Python 3.11+
- PostgreSQL 16 with the `pgvector` extension (the included `docker-compose.yml` provides one)
- Accounts for [Clerk](https://clerk.com) and [Google AI Studio](https://aistudio.google.com/apikey) (and [Supabase](https://supabase.com) for storage outside local development)

### 1. Clone and start the database

```bash
git clone <your-repository-url> evalai
cd evalai
docker compose up -d db          # Postgres 16 + pgvector on localhost:54329
```

### 2. API and worker

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../../.env.example .env       # fill in the values, see Configuration

alembic upgrade head             # runs as the database owner (MIGRATION_DATABASE_URL)
psql "postgresql://postgres:postgres@localhost:54329/postgres" \
  -c "ALTER ROLE evalai_app LOGIN PASSWORD 'dev'"   # the least-privilege runtime role

uvicorn app.main:app --reload    # http://localhost:8000, Swagger UI at /docs
python -m app.worker             # in a second terminal: processes documents, papers and answer sheets
```

For local development `STORAGE_PROVIDER=local` stores files on disk with the same signed-URL behaviour as Supabase.

### 3. Web app

```bash
cd apps/web
npm install
cp .env.example .env.local       # Clerk keys and NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                      # http://localhost:3000
```

### 4. First sign-in

1. Put your email in `BOOTSTRAP_ADMIN_EMAILS` and sign up. You can then create an institution.
2. Invite teachers and students from **Admin → People**. They join by signing up with the invited email.
3. Optional demo data (one institution, three subjects, a teacher and five students with sample results):
   ```bash
   cd apps/api && python ../../scripts/seed.py
   ```
   Seeded records are labelled **Sample data** in the interface and were not produced by the AI.

## Configuration

All settings are environment variables. The full list with comments is in [`.env.example`](.env.example).

| Variable | Where | Purpose |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | web | Clerk sign-in |
| `NEXT_PUBLIC_API_URL` | web | API base URL |
| `DATABASE_URL` | API, worker | Connection as `evalai_app` (cannot bypass row-level security) |
| `MIGRATION_DATABASE_URL` | migrations | Connection as the schema owner |
| `CLERK_ISSUER`, `CLERK_JWKS_URL`, `CLERK_AUTHORIZED_PARTIES` | API | Token verification |
| `CLERK_SECRET_KEY` | API | Reads the verified email on first sign-in |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET` | API, worker | Private file storage (never set on the frontend) |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL` | API, worker | Model access; pick current ids from [ai.google.dev/models](https://ai.google.dev/models) |
| `APP_SIGNING_SECRET` | API | Signs upload tokens (`openssl rand -hex 32`) |
| `CORS_ORIGINS` | API | Allowed web origins |
| `BOOTSTRAP_ADMIN_EMAILS` | API | Accounts allowed to create institutions |
| `MAX_UPLOAD_SIZE_MB`, `MAX_ANSWER_SHEET_PAGES`, `AI_RATE_LIMIT_PER_MINUTE`, `OCR_REVIEW_THRESHOLD`, `EVALUATION_REVIEW_THRESHOLD` | API | Limits and review thresholds |

If an integration is not configured, the API answers with HTTP 503 and names the missing variable instead of pretending to succeed. **Admin → Overview** shows which integrations are configured, without revealing secrets.

## Running tests

```bash
# Backend: real Postgres with pgvector, connecting as the restricted application role
cd apps/api && pytest                     # TEST_PG=host:port if not localhost:54329

# Frontend
cd apps/web && npm test && npm run typecheck && npm run lint

# Full browser acceptance run (teacher → student → teacher → student → challenge → admin audit)
bash scripts/e2e_stack.sh up
cd apps/web && npm run e2e
bash scripts/e2e_stack.sh down
```

The automated suites replace Clerk and Gemini with small, clearly labelled HTTP test doubles in [`scripts/dev_stubs`](scripts/dev_stubs), so they run offline. They prove integration and integrity rules, not marking quality. To measure marking quality with a real model:

```bash
cd apps/api && python ../../scripts/run_benchmark.py
```

It grades the answers in [`benchmarks/evaluation_set.json`](benchmarks/evaluation_set.json) (complete, reworded, partial, incorrect, contradictory, off-topic, prompt-injection, empty and illegible) and reports mean absolute error. Have a teacher confirm the expected marks in that file before quoting the results.

## Deployment

| Component | Platform | Notes |
|---|---|---|
| Web | Vercel | Root directory `apps/web` |
| API | Render web service | Runs `alembic upgrade head` before each deploy; health check `/health` |
| Worker | Render background worker | Must be running for documents and answer sheets to be processed |
| Database | Supabase Postgres | Enable `vector`; runtime connects as `evalai_app` |
| Files | Supabase Storage | Create the private bucket with `scripts/setup_supabase.py` |

[`render.yaml`](render.yaml) defines the API, the worker and their shared environment group. Step-by-step instructions are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Project structure

```
evalai/
├── apps/
│   ├── web/                  Next.js app: landing page, teacher, student and admin workspaces
│   │   ├── app/              routes (App Router)
│   │   ├── components/       UI primitives, charts, editors, page viewer
│   │   ├── lib/              API client, auth bridge, utilities
│   │   └── e2e/              Playwright acceptance test
│   └── api/                  FastAPI service
│       ├── app/
│       │   ├── api/v1/       REST routers
│       │   ├── core/         config, auth, database, storage, errors
│       │   ├── models/       SQLAlchemy models
│       │   ├── schemas/      request validation
│       │   ├── services/     domain logic (ingest, exams, extraction, grading, challenges)
│       │   └── worker.py     persistent job worker
│       ├── alembic/          migrations (schema, RLS, append-only history)
│       └── tests/
├── ai_engine/                provider interface, ingestion, retrieval, question generation,
│                             rubrics, handwriting, evaluation, challenges, analytics, workflows
├── benchmarks/               evaluation benchmark set
├── scripts/                  seed, Supabase setup, benchmark runner, e2e stack, test doubles
├── docs/                     architecture, API, schema, AI evaluation, deployment, build log
├── docker-compose.yml
└── render.yaml
```

## Security and grading integrity

- **No unverified marks reach students.** Every result needs teacher approval of the answer sheet and an explicit results publication. Provisional marks and AI internals are never returned to student accounts.
- **Marks are bounded in code and in the database.** Totals are summed from criterion scores; check constraints reject anything outside `0..max`.
- **History cannot be rewritten.** Evaluation versions, challenge decisions and the audit log are append-only, enforced by triggers and revoked privileges.
- **One approved rubric per question.** Approved rubrics are immutable; changes create a new version, and every evaluation records the version it used.
- **Identity and roles come from the server.** Roles, owner ids and marks sent by the client are never trusted.
- **Tenant isolation** through row-level security plus explicit filtering; a record belonging to someone else returns 404, the same as a missing one.
- **Private files.** One private bucket, server-generated object paths sealed in signed tokens, short-lived signed URLs, and content-based file type checks.
- **Prompt-injection resistance.** Uploaded documents and student answers are passed to the model as delimited untrusted data that carries no authority.
- **Blind grading.** The grading model never receives student identity.
- **Rate limits** on expensive AI endpoints.

## Project status

All modules in the specification are implemented, and the complete workflow passes end to end in the automated browser test.

Not yet verified against live services, because the build environment could not reach them: real Gemini output quality, real Clerk sign-in, Supabase Storage signed URLs, and the Render and Vercel deployments. No marking accuracy figure has been measured yet.

Known limitations:
- Scanned textbooks without a text layer are rejected at indexing (answer sheets are handwriting-read; reference material is not OCR'd).
- Answer regions are model-reported descriptions rather than pixel bounding boxes.
- Platform settings are shown read-only in the admin dashboard and changed through environment variables.

See [docs/BUILD_PROGRESS.md](docs/BUILD_PROGRESS.md) for the detailed record.

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, tenancy, identity, jobs, storage, integrity decisions |
| [AI_EVALUATION.md](docs/AI_EVALUATION.md) | Indexing, paper generation, handwriting, the evaluation graph, confidence, consistency, challenges |
| [API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) | Conventions, every endpoint, key flows ([OpenAPI spec](docs/openapi.json)) |
| [DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | Every table and the database-level security |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Supabase, Clerk, Gemini, Render, Vercel and local setup |
| [BUILD_PROGRESS.md](docs/BUILD_PROGRESS.md) | What is done, what was tested and how, what is open |

## License

No license has been chosen yet. Until one is added, all rights are reserved by the author.
