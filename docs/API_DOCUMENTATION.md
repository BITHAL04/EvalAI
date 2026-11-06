# API

Interactive docs: `/docs` (Swagger UI) and `/redoc` on any running API. The full machine-readable spec is in [openapi.json](openapi.json).

## Conventions

- Base path `/api/v1`. JSON in and out.
- **Authentication:** `Authorization: Bearer <Clerk session token>`. The API verifies the signature against `CLERK_JWKS_URL`, plus issuer, expiry and (if set) `azp`. Nothing about identity or role is read from the request body or from token claims other than `sub` and the verified email.
- **Roles** come from `institution_memberships` only. `X-Institution-Id` picks among a user's memberships; it is validated, never trusted.
- **First sign-in:** the client calls `POST /users/sync`. A verified email that matches an invitation becomes a membership.
- **Errors:** `{"detail": {"code": "...", "message": "...", "errors": [{"field", "message"}]?}}`. A missing record and a record belonging to someone else both return 404. Missing configuration returns 503 `not_configured` with setup instructions. Expensive AI endpoints return 429 `rate_limited`.
- **Pagination:** list endpoints accept `limit` and `offset` and return `{items, total}`.
- **Uploads** never pass through the API: request a signed URL, `PUT` the file to storage, then confirm. The confirm step re-reads the object and validates type, size and page count.
- **Long work** (indexing, generation, extraction, evaluation, challenge review) is queued as a persistent job; poll the resource's status or `GET /jobs/{id}`.

## Endpoints

| Method | Path | Area |
|---|---|---|
| `GET` | `/api/v1/admin/audit-logs` | admin |
| `GET` | `/api/v1/admin/institutions` | admin |
| `POST` | `/api/v1/admin/institutions` | admin |
| `GET` | `/api/v1/admin/overview` | admin |
| `GET` | `/api/v1/analytics/class/{subject_id}` | analytics |
| `GET` | `/api/v1/analytics/examination/{exam_id}` | analytics |
| `GET` | `/api/v1/analytics/jobs` | analytics |
| `GET` | `/api/v1/analytics/student` | analytics |
| `GET` | `/api/v1/analytics/student/topics` | analytics |
| `GET` | `/api/v1/analytics/teacher/overview` | analytics |
| `POST` | `/api/v1/challenges` | challenges |
| `GET` | `/api/v1/challenges` | challenges |
| `GET` | `/api/v1/challenges/{cid}` | challenges |
| `POST` | `/api/v1/challenges/{cid}/decision` | challenges |
| `POST` | `/api/v1/challenges/{cid}/finalize` | challenges |
| `POST` | `/api/v1/challenges/{cid}/review` | challenges |
| `GET` | `/api/v1/courses` | subjects |
| `POST` | `/api/v1/courses` | subjects |
| `POST` | `/api/v1/documents` | documents |
| `GET` | `/api/v1/documents` | documents |
| `POST` | `/api/v1/documents/upload-url` | documents |
| `GET` | `/api/v1/documents/{doc_id}` | documents |
| `DELETE` | `/api/v1/documents/{doc_id}` | documents |
| `POST` | `/api/v1/documents/{doc_id}/process` | documents |
| `POST` | `/api/v1/documents/{doc_id}/retry` | documents |
| `POST` | `/api/v1/evaluations/submission/{submission_id}/approve` | evaluations |
| `GET` | `/api/v1/evaluations/{eid}` | evaluations |
| `POST` | `/api/v1/evaluations/{eid}/approve` | evaluations |
| `GET` | `/api/v1/evaluations/{eid}/history` | evaluations |
| `GET` | `/api/v1/evaluations/{eid}/report` | evaluations |
| `PUT` | `/api/v1/evaluations/{eid}/teacher-review` | evaluations |
| `POST` | `/api/v1/evaluations/{submission_id}/start` | evaluations |
| `PUT` | `/api/v1/examination-questions/{question_id}` | examinations |
| `DELETE` | `/api/v1/examination-questions/{question_id}` | examinations |
| `GET` | `/api/v1/examination-questions/{question_id}/benchmarks` | examinations |
| `POST` | `/api/v1/examination-questions/{question_id}/benchmarks` | examinations |
| `POST` | `/api/v1/examination-questions/{question_id}/regenerate` | examinations |
| `GET` | `/api/v1/examinations` | examinations |
| `POST` | `/api/v1/examinations` | examinations |
| `GET` | `/api/v1/examinations/{exam_id}` | examinations |
| `PUT` | `/api/v1/examinations/{exam_id}` | examinations |
| `DELETE` | `/api/v1/examinations/{exam_id}` | examinations |
| `POST` | `/api/v1/examinations/{exam_id}/calibrate` | examinations |
| `POST` | `/api/v1/examinations/{exam_id}/close` | examinations |
| `POST` | `/api/v1/examinations/{exam_id}/generate` | examinations |
| `POST` | `/api/v1/examinations/{exam_id}/generate-paper` | examinations |
| `GET` | `/api/v1/examinations/{exam_id}/paper` | examinations |
| `POST` | `/api/v1/examinations/{exam_id}/publish` | examinations |
| `POST` | `/api/v1/examinations/{exam_id}/publish-results` | examinations |
| `POST` | `/api/v1/examinations/{exam_id}/questions` | examinations |
| `POST` | `/api/v1/examinations/{exam_id}/recalculate` | examinations |
| `GET` | `/api/v1/examinations/{exam_id}/submissions` | examinations |
| `PUT` | `/api/v1/extracted-answers/{aid}` | submissions |
| `GET` | `/api/v1/invitations` | users |
| `POST` | `/api/v1/invitations` | users |
| `DELETE` | `/api/v1/invitations/{invitation_id}` | users |
| `GET` | `/api/v1/jobs/{job_id}` | examinations |
| `GET` | `/api/v1/notifications` | users |
| `POST` | `/api/v1/notifications/read-all` | users |
| `GET` | `/api/v1/questions` | questions |
| `POST` | `/api/v1/questions` | questions |
| `POST` | `/api/v1/questions/generate` | questions |
| `PUT` | `/api/v1/questions/{question_id}` | questions |
| `DELETE` | `/api/v1/questions/{question_id}` | questions |
| `GET` | `/api/v1/results` | evaluations |
| `GET` | `/api/v1/results/{exam_id}` | evaluations |
| `GET` | `/api/v1/subjects` | subjects |
| `POST` | `/api/v1/subjects` | subjects |
| `GET` | `/api/v1/subjects/{subject_id}` | subjects |
| `PUT` | `/api/v1/subjects/{subject_id}` | subjects |
| `DELETE` | `/api/v1/subjects/{subject_id}` | subjects |
| `GET` | `/api/v1/subjects/{subject_id}/enrollments` | subjects |
| `POST` | `/api/v1/subjects/{subject_id}/enrollments` | subjects |
| `DELETE` | `/api/v1/subjects/{subject_id}/enrollments/{user_id}` | subjects |
| `GET` | `/api/v1/subjects/{subject_id}/topics` | documents |
| `POST` | `/api/v1/submissions` | submissions |
| `GET` | `/api/v1/submissions` | submissions |
| `GET` | `/api/v1/submissions/{sid}` | submissions |
| `GET` | `/api/v1/submissions/{sid}/file` | submissions |
| `GET` | `/api/v1/submissions/{sid}/pages` | submissions |
| `POST` | `/api/v1/submissions/{sid}/process` | submissions |
| `POST` | `/api/v1/submissions/{sid}/reevaluate` | submissions |
| `GET` | `/api/v1/submissions/{sid}/status` | submissions |
| `POST` | `/api/v1/submissions/{sid}/upload` | submissions |
| `GET` | `/api/v1/users` | users |
| `GET` | `/api/v1/users/me` | users |
| `POST` | `/api/v1/users/sync` | users |
| `PUT` | `/api/v1/users/{user_id}/membership` | users |
| `GET` | `/health` | health |

## Key flows

**Document:** `POST /documents/upload-url` → `PUT upload_url` → `POST /documents {upload_token, title, kind}` → status `uploaded → processing → indexed | failed` → `POST /documents/{id}/retry`.

**Paper:** `POST /examinations` → `POST /examinations/{id}/generate` (status `generating → review`) → edit with `PUT /examination-questions/{id}`, `POST .../regenerate`, `DELETE`, `POST /examinations/{id}/questions`, `POST /examinations/{id}/recalculate` → `POST /examinations/{id}/publish` (the only way a paper becomes visible; approves the rubrics and renders the PDF).

**Answer sheet:** `POST /submissions` → `PUT upload_url` → `POST /submissions/{id}/upload` (validates, renders previews) → `GET /submissions/{id}/pages` → `POST /submissions/{id}/process` (final submission) → `extracting → extracted → evaluating → evaluated`.

**Marking:** `PUT /extracted-answers/{id}` (fix transcription) → `POST /submissions/{id}/reevaluate` → `PUT /evaluations/{id}/teacher-review` → `POST /evaluations/submission/{id}/approve` → `POST /examinations/{id}/publish-results`.

**Challenge:** `POST /challenges` (published results only) → AI review job → `POST /challenges/{id}/decision` → `POST /challenges/{id}/finalize`.
