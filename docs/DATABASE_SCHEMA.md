# Database schema

Postgres 16 with `pgvector`. Source of truth: `apps/api/app/models/entities.py` and the Alembic migrations. All ids are UUIDs; most tables have `created_at`/`updated_at`.

## Identity and organisation
| Table | Purpose |
|---|---|
| `institutions` | Tenants. |
| `users` | One row per person; `clerk_user_id` links to Clerk. `is_platform_admin` can create institutions. |
| `user_profiles` | Name, roll number, department. |
| `roles` | `admin`, `teacher`, `student`. |
| `institution_memberships` | user × institution × role. The only source of a role. Unique per user and institution. |
| `invitations` | Pending email invitations, claimed on first verified sign-in. |
| `courses`, `subjects` | Unique code per institution. |
| `enrollments` | Student × subject. Controls which papers a student sees. |

## Academic documents
| Table | Purpose |
|---|---|
| `study_materials` | Uploaded file metadata, status `uploaded/processing/indexed/failed`, error, SHA-256 (unique per subject). |
| `document_chunks` | Text sections with page range, chapter, `vector(768)` embedding (HNSW cosine index) and embedding model. |
| `document_processing_jobs` | Per-attempt indexing status and stage. |

## Examinations
| Table | Purpose |
|---|---|
| `question_bank` | Reusable questions with answer, concepts, rubric, source references. |
| `examinations` | Paper settings, generation config, status `draft/generating/review/published/closed/results_published`, PDF path, duplicate policy, deadline. |
| `examination_questions` | Numbered questions (deferrable unique number), marks > 0, sources, cached question understanding. |
| `examination_topics` | Topics covered. |
| `rubrics` | Versioned per question; `draft/approved/superseded`; snapshot of model answer and concepts. |
| `rubric_criteria` | Criterion, category, max marks > 0, expected evidence. |

## Submissions
| Table | Purpose |
|---|---|
| `submissions` | Student × exam × version; partial unique index allows one current version. |
| `submission_files` | Original PDF path, hash, page count, rendered page image paths. |
| `extraction_jobs` | Pages done, page failures, warnings, model. |
| `extracted_answers` | Per question (0 = unassigned): recognised text, teacher correction, confidence, diagram/equation flags, verification reasons. |
| `answer_page_references` | Pages and regions an answer came from. |

## Evaluation
| Table | Purpose |
|---|---|
| `evaluations` | Current state per submission × question; `marks_awarded` NULL means not yet markable; CHECK `0 ≤ marks ≤ max`. Status `provisional/needs_review/teacher_reviewed/approved`. Full report JSON. |
| `criterion_scores` | Current criterion marks, CHECK within bounds, unique per criterion. |
| `evaluation_evidence` | Quotes and page references supporting the marks. |
| `evaluation_versions` | **Append-only** history: every AI run, teacher change and challenge decision with snapshot, actor and reason. |
| `benchmark_answers` | Teacher reference answers (strong/average/weak) with expected and latest AI marks. |
| `consistency_reports` | Exam-level findings: outliers, divergent similar answers, benchmark drift. |

## Results and analytics
`results` (one per submission, `approved/published`), `topic_performance` (per result × topic), `student_performance_snapshots` (history for trends).

## Challenges
`challenges` (one open per evaluation via partial unique index; original/revised marks and rubric versions), `challenge_evidence`, `challenge_reviews` (AI recommendation, confidence, escalation), `challenge_decisions` (**append-only**).

## Platform
`notifications`, `audit_logs` (**append-only**), `background_jobs` (queue with idempotency key), `rate_limit_hits`.

## Security in the database
- Role `evalai_app` (no superuser, no BYPASSRLS) is what the API and worker use.
- RLS on every table. Tenant tables: `institution_id = current_setting('app.institution_id')` (or `app.platform = 'on'` for the worker). Shared identity tables are readable by `evalai_app` only; Supabase `anon`/`authenticated` roles have no table privileges.
- UPDATE/DELETE on history tables raise and are revoked.
