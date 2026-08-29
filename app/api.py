"""Minimal FastAPI query path. /health is public; /notices requires X-Api-Key."""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

import psycopg

from app.config import MissingEnvError, Settings
from app.constants import DEFAULT_NAICS, DEFAULT_SET_ASIDE_CODE
from app.query import query_notices

app = FastAPI(title="federal-bid-match", version="0.1.0")


def _settings() -> Settings:
    return Settings.from_env()


def _require_api_key(provided: str | None, expected: str | None) -> None:
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


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
    except (psycopg.Error, OSError):
        raise HTTPException(status_code=503, detail="database unavailable") from None
    return JSONResponse(content=jsonable_encoder(rows))
