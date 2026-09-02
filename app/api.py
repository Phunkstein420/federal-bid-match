"""Minimal FastAPI query path. / is the public product page; /health is public; /notices requires X-Api-Key."""

from __future__ import annotations

import logging
import secrets
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

import psycopg

from app.config import MissingEnvError, Settings
from app.constants import DEFAULT_NAICS, DEFAULT_SET_ASIDE_CODE
from app.homepage import render_homepage
from app.query import query_homepage_notices, query_notices
from app.redact import exception_log_name, redact_db_error_text

log = logging.getLogger(__name__)

app = FastAPI(title="federal-bid-match", version="0.1.0")

ROOT_JSON = {
    "name": "federal-bid-match",
    "health": "/health",
    "notices": "/notices requires X-Api-Key",
}


def _settings() -> Settings:
    return Settings.from_env()


def _require_api_key(provided: str | None, expected: str | None) -> None:
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _wants_json(accept: str | None) -> bool:
    """API clients that ask for JSON without HTML. Browsers send text/html."""
    value = (accept or "").lower()
    return "application/json" in value and "text/html" not in value


def _homepage_sample_notices() -> list[dict[str, Any]]:
    """Live 541511 SBA rows, or empty if the database is missing or fails."""
    try:
        return query_homepage_notices(settings=_settings())
    except MissingEnvError:
        return []
    except (psycopg.Error, OSError) as exc:
        log.warning(
            "%s: %s",
            exception_log_name(exc),
            redact_db_error_text(str(exc)),
        )
        return []


@app.get("/", response_model=None)
def root(request: Request):
    if _wants_json(request.headers.get("accept")):
        return JSONResponse(ROOT_JSON)
    return HTMLResponse(render_homepage(_homepage_sample_notices()))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/notices")
def get_notices(
    naics: Annotated[str, Query()] = DEFAULT_NAICS,
    set_aside: Annotated[str, Query()] = DEFAULT_SET_ASIDE_CODE,
    pop_state: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    settings = _settings()
    _require_api_key(x_api_key, settings.api_key)
    try:
        rows: list[dict[str, Any]] = query_notices(
            naics=naics,
            set_aside=set_aside,
            pop_state=pop_state,
            settings=settings,
        )
    except MissingEnvError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (psycopg.Error, OSError) as exc:
        log.warning(
            "%s: %s",
            exception_log_name(exc),
            redact_db_error_text(str(exc)),
        )
        raise HTTPException(status_code=503, detail="database unavailable") from None
    return JSONResponse(content=jsonable_encoder(rows))
