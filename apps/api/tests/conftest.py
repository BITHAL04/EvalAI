"""Test harness: a real Postgres (with RLS, connecting as the least-privilege role), real JWT
verification against a local JWKS, local signed-URL storage, and the Gemini HTTP test double."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

PG = os.environ.get("TEST_PG", "127.0.0.1:54329")
OWNER_URL = f"postgresql+psycopg://postgres@{PG}/evalai_test"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KID = "test-key"
ISSUER = "https://test.clerk.local"


class _JWKS(BaseHTTPRequestHandler):
    def do_GET(self):
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
        body = json.dumps({"keys": [{**jwk, "kid": KID, "use": "sig", "alg": "RS256"}]}).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


_jwks = HTTPServer(("127.0.0.1", 0), _JWKS)
threading.Thread(target=_jwks.serve_forever, daemon=True).start()
from scripts.dev_stubs.gemini_stub import serve as serve_stub  # noqa: E402

_stub = serve_stub(0)
_storage = tempfile.mkdtemp(prefix="evalai-storage-")
os.environ.update({
    "ENVIRONMENT": "test", "DATABASE_URL": f"postgresql://evalai_app:test@{PG}/evalai_test", "MIGRATION_DATABASE_URL": OWNER_URL,
    "CLERK_ISSUER": ISSUER, "CLERK_JWKS_URL": f"http://127.0.0.1:{_jwks.server_port}/jwks", "CLERK_SECRET_KEY": "",
    "STORAGE_PROVIDER": "local", "LOCAL_STORAGE_DIR": _storage, "PUBLIC_API_URL": "http://testserver", "APP_SIGNING_SECRET": "test-secret",
    "GEMINI_API_KEY": "test", "GEMINI_MODEL": "stub-model", "GEMINI_EMBEDDING_MODEL": "stub-embed", "GEMINI_BASE_URL": f"http://127.0.0.1:{_stub.server_port}",
    "AI_MAX_RETRIES": "1", "AI_RATE_LIMIT_PER_MINUTE": "1000", "CORS_ORIGINS": "http://localhost:3000", "BOOTSTRAP_ADMIN_EMAILS": "root@evalai.test",
})

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

owner = create_engine(OWNER_URL, isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="session", autouse=True)
def database():
    with owner.connect() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        c.execute(text("DROP ROLE IF EXISTS evalai_app_dummy"))
    cfg = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "apps" / "api" / "alembic"))
    command.upgrade(cfg, "head")
    with owner.connect() as c:
        c.execute(text("ALTER ROLE evalai_app LOGIN PASSWORD 'test'"))
    yield


TABLES = None


@pytest.fixture(autouse=True)
def clean(database):
    global TABLES
    with owner.connect() as c:
        if TABLES is None:
            TABLES = [r[0] for r in c.execute(text("select tablename from pg_tables where schemaname='public' and tablename not in ('roles','alembic_version')"))]
        c.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
    yield


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


def token(sub: str, email: str | None = None, *, exp: int = 600, key=None, extra: dict | None = None) -> str:
    now = int(time.time())
    claims = {"sub": sub, "iss": ISSUER, "iat": now, "nbf": now, "exp": now + exp, "azp": "http://localhost:3000", **(extra or {})}
    if email:
        claims |= {"email": email, "email_verified": True}
    return jwt.encode(claims, key or KEY, algorithm="RS256", headers={"kid": KID})


class Actor:
    def __init__(self, client, sub: str, email: str):
        self.client, self.sub, self.email = client, sub, email
        self.headers = {"Authorization": f"Bearer {token(sub, email)}"}

    def __getattr__(self, method):
        def call(path, **kw):
            kw.setdefault("headers", {}).update(self.headers)
            return getattr(self.client, method)(f"/api/v1{path}", **kw)
        return call


def make_institution(name: str = "Demo University") -> uuid.UUID:
    iid = uuid.uuid4()
    with owner.connect() as c:
        c.execute(text("insert into institutions (id, name, slug, settings, is_active, is_demo) values (:i, :n, :s, '{}', true, false)"),
                  {"i": iid, "n": name, "s": f"inst-{iid.hex[:8]}"})
    return iid


def make_user(client, institution_id: uuid.UUID, role: str, name: str) -> Actor:
    sub, email = f"user_{uuid.uuid4().hex[:10]}", f"{name.lower().replace(' ', '.')}.{uuid.uuid4().hex[:4]}@evalai.test"
    with owner.connect() as c:
        c.execute(text("insert into invitations (id, institution_id, email, role, full_name) values (gen_random_uuid(), :i, :e, :r, :n)"),
                  {"i": institution_id, "e": email, "r": role, "n": name})
    a = Actor(client, sub, email)
    r = a.post("/users/sync")
    assert r.status_code == 200, r.text
    a.id = r.json()["id"]
    return a


@pytest.fixture
def world(client):
    inst = make_institution()
    t = make_user(client, inst, "teacher", "Tara Teacher")
    s1 = make_user(client, inst, "student", "Sam Student")
    s2 = make_user(client, inst, "student", "Riya Student")
    adm = make_user(client, inst, "admin", "Ada Admin")
    return type("World", (), {"inst": inst, "teacher": t, "s1": s1, "s2": s2, "admin": adm})


def text_pdf(pages: list[str]) -> bytes:
    import fitz
    doc = fitz.open()
    for body in pages:
        p = doc.new_page()
        p.insert_textbox(fitz.Rect(50, 50, 545, 800), body, fontsize=11)
    return doc.tobytes()


def handwritten_pdf(pages: list[str]) -> bytes:
    """A scanned-looking answer booklet: text drawn into a noisy, slightly rotated photo."""
    import fitz
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    font = None
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
        if os.path.exists(path):
            font = ImageFont.truetype(path, 30)
    font = font or ImageFont.load_default(size=30)
    doc = fitz.open()
    for body in pages:
        img = Image.new("RGB", (1240, 1754), (250, 248, 240))
        d = ImageDraw.Draw(img)
        y = 80
        for line in body.splitlines():
            d.text((90, y), line, fill=(20, 30, 120), font=font)
            y += 52
        img = img.rotate(1.2, fillcolor=(250, 248, 240)).filter(ImageFilter.GaussianBlur(0.6))
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=85)
        p = doc.new_page(width=595, height=842)
        p.insert_image(p.rect, stream=buf.getvalue())
    return doc.tobytes()


def upload(client, info: dict, data: bytes) -> None:
    r = client.request(info["method"], info["upload_url"].replace("http://testserver", ""), content=data, headers=info["headers"])
    assert r.status_code == 200, r.text


def drain() -> int:
    from app.worker import run_pending
    return run_pending()
