from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import ConfigurationError

log = logging.getLogger("evalai")


class DomainError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status, detail={"code": code, "message": message})


def not_found(what: str = "Resource") -> DomainError:
    # Same response for "missing" and "belongs to someone else", so ids cannot be probed.
    return DomainError(404, "not_found", f"{what} not found")


def forbidden(message: str = "You do not have permission to do this") -> DomainError:
    return DomainError(403, "forbidden", message)


def conflict(message: str, code: str = "conflict") -> DomainError:
    return DomainError(409, code, message)


def bad_request(message: str, code: str = "bad_request") -> DomainError:
    return DomainError(400, code, message)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ConfigurationError)
    async def _config(_: Request, exc: ConfigurationError):
        return JSONResponse(status_code=503, content={"detail": {"code": "not_configured", "message": str(exc)}})

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            status_code=422, content={"detail": {"code": "validation_error", "message": "Invalid input", "errors": errors}}
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        log.warning("integrity error: %s", exc.orig)
        return JSONResponse(status_code=409, content={"detail": {"code": "conflict", "message": "Conflicts with existing data"}})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": {"code": "internal_error", "message": "Something went wrong"}})
