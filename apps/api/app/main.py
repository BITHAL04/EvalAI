from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # ai_engine lives at the repository root

from fastapi import APIRouter, Depends, FastAPI, Request, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.v1 import academics, admin, analytics, challenges, evaluations, examinations, submissions, users  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.errors import DomainError, install_handlers  # noqa: E402
from app.core.storage import LocalStorage, StorageError, get_storage  # noqa: E402
from app.services.platform import healthcheck  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()
app = FastAPI(title="EvalAI API", version="1.0.0", description="Examination and handwritten answer evaluation platform.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"], allow_credentials=False)
install_handlers(app)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
    return response


api = APIRouter(prefix="/api/v1")
for module in (users, academics, examinations, submissions, evaluations, challenges, analytics, admin):
    api.include_router(module.router)


if settings.storage_provider == "local":
    @api.put("/local-storage/{token}", include_in_schema=False)
    async def local_put(token: str, request: Request):
        store = get_storage()
        assert isinstance(store, LocalStorage)
        try:
            path = store.verify(token, "put")
        except Exception as exc:
            raise DomainError(403, "forbidden", "Upload link is invalid or expired") from exc
        body = await request.body()
        if len(body) > settings.max_upload_size_mb * 1024 * 1024:
            raise DomainError(413, "file_too_large", "File too large")
        store.write(path, body, request.headers.get("content-type", ""))
        return {"ok": True}

    @api.get("/local-storage/{token}", include_in_schema=False)
    def local_get(token: str):
        store = get_storage()
        assert isinstance(store, LocalStorage)
        try:
            path = store.verify(token, "get")
            data = store.read(path)
        except StorageError as exc:
            raise DomainError(404, "not_found", "File not found") from exc
        except Exception as exc:
            raise DomainError(403, "forbidden", "Link is invalid or expired") from exc
        kind = "application/pdf" if path.endswith(".pdf") else "image/jpeg" if path.endswith(".jpg") else "application/octet-stream"
        return Response(data, media_type=kind)

app.include_router(api)


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    healthcheck(db)
    return {"status": "ok"}
