import time

from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, text

from tests.conftest import Actor, make_institution, make_user, token

PDF = b"%PDF-1.4 x"


def test_requests_without_valid_tokens_are_rejected(client):
    assert client.get("/api/v1/users/me").status_code == 401
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for bad in (token("u1", key=other), token("u1", exp=-60), "not-a-jwt"):
        r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401, bad


def test_token_for_unknown_user_must_sync_first(client):
    r = client.get("/api/v1/subjects", headers={"Authorization": f"Bearer {token('nobody', 'x@y.z')}"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_synced"


def test_role_comes_from_the_database_not_the_token(client):
    inst = make_institution()
    s = make_user(client, inst, "student", "Sneaky Student")
    forged = {"Authorization": f"Bearer {token(s.sub, s.email, extra={'role': 'admin', 'public_metadata': {'role': 'teacher'}})}"}
    assert client.post("/api/v1/subjects", json={"name": "Hack", "code": "HK1"}, headers=forged).status_code == 403
    assert client.get("/api/v1/admin/audit-logs", headers=forged).status_code == 403


def test_sync_without_invitation_gives_no_access(client):
    a = Actor(client, "lonely", "lonely@evalai.test")
    assert a.post("/users/sync").json()["memberships"] == []
    assert a.get("/subjects").json()["detail"]["code"] == "no_membership"


def test_unverified_email_cannot_claim_an_invitation(client):
    inst = make_institution()
    make_user(client, inst, "teacher", "Real Teacher")
    h = {"Authorization": f"Bearer {token('imposter', extra={'email': 'someone@evalai.test', 'email_verified': False})}"}
    assert client.post("/api/v1/users/sync", headers=h).status_code in (403, 503)


def test_institutions_are_isolated_in_api_and_database(client):
    a, b = make_institution("A"), make_institution("B")
    ta, tb = make_user(client, a, "teacher", "Teacher A"), make_user(client, b, "teacher", "Teacher B")
    sid = ta.post("/subjects", json={"name": "Machine Learning", "code": "ML101"}).json()["id"]
    assert tb.get(f"/subjects/{sid}").status_code == 404
    assert tb.put(f"/subjects/{sid}", json={"name": "Stolen", "code": "ML101"}).status_code == 404
    assert tb.get("/subjects").json()["total"] == 0
    # Even raw SQL from the application role sees nothing outside the session's tenant.
    eng = create_engine("postgresql+psycopg://evalai_app:test@127.0.0.1:54329/evalai_test")
    with eng.connect() as c:
        c.execute(text("select set_config('app.institution_id', :i, false)"), {"i": str(b)})
        assert c.execute(text("select count(*) from subjects")).scalar() == 0
        c.execute(text("select set_config('app.institution_id', :i, false)"), {"i": str(a)})
        assert c.execute(text("select count(*) from subjects")).scalar() == 1
        c.execute(text("select set_config('app.institution_id', '', false)"))
        assert c.execute(text("select count(*) from subjects")).scalar() == 0


def test_students_cannot_manage_content(world):
    assert world.s1.post("/subjects", json={"name": "X subject", "code": "XX1"}).status_code == 403
    assert world.s1.get("/documents").status_code == 403
    assert world.s1.get("/users").status_code == 403
    assert world.teacher.get("/admin/audit-logs").status_code == 403
    assert world.admin.get("/admin/audit-logs").status_code == 200


def test_subject_crud_and_enrollment(world):
    t = world.teacher
    r = t.post("/subjects", json={"name": "Database Management Systems", "code": "DB201", "semester": "4"})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert t.post("/subjects", json={"name": "Dup", "code": "DB201"}).status_code == 409
    assert t.put(f"/subjects/{sid}", json={"name": "DBMS", "code": "DB201"}).json()["name"] == "DBMS"
    assert world.s1.get("/subjects").json()["total"] == 0
    assert t.post(f"/subjects/{sid}/enrollments", json={"user_ids": [world.s1.id]}).json()["added"] == 1
    assert world.s1.get("/subjects").json()["total"] == 1
    assert world.s2.get(f"/subjects/{sid}").status_code == 404
    assert t.delete(f"/subjects/{sid}").status_code == 204


def test_validation_errors_are_structured(world):
    r = world.teacher.post("/subjects", json={"name": "", "code": "A"})
    assert r.status_code == 422 and {e["field"] for e in r.json()["detail"]["errors"]} == {"name", "code"}


def test_audit_log_is_append_only(world):
    eng = create_engine("postgresql+psycopg://evalai_app:test@127.0.0.1:54329/evalai_test")
    with eng.connect() as c:
        c.execute(text("select set_config('app.platform', 'on', false)"))
        assert c.execute(text("select count(*) from audit_logs")).scalar() > 0
        try:
            c.execute(text("update audit_logs set action = 'x'"))
            raise AssertionError("audit log was modified")
        except Exception as exc:  # noqa: BLE001
            assert "permission denied" in str(exc) or "append-only" in str(exc)


def test_document_upload_rejects_wrong_types_and_bad_tokens(world):
    t = world.teacher
    sid = t.post("/subjects", json={"name": "ML", "code": "ML1"}).json()["id"]
    assert t.post("/documents/upload-url", json={"filename": "x.exe", "size_bytes": 10, "subject_id": sid}).status_code == 400
    assert t.post("/documents/upload-url", json={"filename": "x.pdf", "size_bytes": 10**10, "subject_id": sid}).status_code == 413
    assert t.post("/documents", json={"upload_token": "forged", "title": "Forged"}).status_code == 400
    _ = time.time()
