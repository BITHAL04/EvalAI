"""Least-privilege role, row level security, append-only history, reference data.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "evalai_app"
TENANT_TABLES = """invitations courses subjects enrollments study_materials document_chunks document_processing_jobs
question_bank examinations examination_questions examination_topics rubrics rubric_criteria submissions submission_files
extraction_jobs extracted_answers answer_page_references evaluations criterion_scores evaluation_evidence
evaluation_versions benchmark_answers consistency_reports results topic_performance student_performance_snapshots
challenges challenge_evidence challenge_reviews challenge_decisions notifications""".split()
# Needed before a tenant is known (identity lookup) or written across tenants by design.
SHARED_TABLES = "institutions users user_profiles roles institution_memberships background_jobs rate_limit_hits".split()
APPEND_ONLY = ["evaluation_versions", "challenge_decisions", "audit_logs"]
TENANT_CHECK = (
    "current_setting('app.platform', true) = 'on' OR "
    "institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid"
)


def upgrade() -> None:
    op.execute(f"""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
      END IF;
    END $$""")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"REVOKE ALL ON alembic_version FROM {APP_ROLE}")
    # Supabase exposes `public` through PostgREST to these roles. EvalAI never uses them.
    op.execute("""
    DO $$ DECLARE r text; BEGIN
      FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
          EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
        END IF;
      END LOOP;
    END $$""")

    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} TO {APP_ROLE} USING ({TENANT_CHECK}) WITH CHECK ({TENANT_CHECK})")
    for t in SHARED_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY app_access ON {t} TO {APP_ROLE} USING (true) WITH CHECK (true)")
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY audit_read ON audit_logs FOR SELECT TO {APP_ROLE} USING ({TENANT_CHECK})")
    op.execute(f"CREATE POLICY audit_write ON audit_logs FOR INSERT TO {APP_ROLE} WITH CHECK (true)")

    op.execute("""
    CREATE FUNCTION reject_history_change() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
    END $$ LANGUAGE plpgsql""")
    for t in APPEND_ONLY:
        op.execute(f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {t} "
                   "FOR EACH ROW EXECUTE FUNCTION reject_history_change()")
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {t} FROM {APP_ROLE}")

    bind = op.get_bind()
    for name, desc in [("admin", "Institution administrator"), ("teacher", "Teacher / examiner"), ("student", "Student")]:
        bind.execute(sa.text("INSERT INTO roles (id, name, description) VALUES (gen_random_uuid(), :n, :d)"), {"n": name, "d": desc})


def downgrade() -> None:
    for t in APPEND_ONLY:
        op.execute(f"DROP TRIGGER IF EXISTS {t}_append_only ON {t}")
    op.execute("DROP FUNCTION IF EXISTS reject_history_change()")
    for t in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    for t in SHARED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS app_access ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS audit_read ON audit_logs")
    op.execute("DROP POLICY IF EXISTS audit_write ON audit_logs")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")
    op.execute("DELETE FROM roles")
