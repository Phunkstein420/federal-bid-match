# federal-bid-match

Daily collector for **public** U.S. federal contract opportunities published by SAM.gov Data Services.

It downloads the official Contract Opportunities CSV, upserts Solicitation / Combined Synopsis / Presolicitation / Sources Sought notices into existing Supabase tables (`public.sam_notices`, `public.sam_ingest_runs`), and exposes a small query path filtered by NAICS + set-aside (+ optional place-of-performance state).

## Legal source

**Ingest uses only** the public SAM.gov Data Services Contract Opportunities extract:

`GET` (not `HEAD`; follows `303` to object storage):

https://sam.gov/api/prod/fileextractservices/v1/api/download/Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv?privacy=Public

This job does **not** scrape SAM.gov HTML or search, Login.gov, website bots, Entity Management / D&B, or FOUO / sensitive APIs.

CSV ingest does **not** require `SAM_API_KEY`. A later optional path is the GSA public Get Opportunities API (`https://api.sam.gov/opportunities/v2/search`); if used, that key is read only from env `SAM_API_KEY`.

Never commit, log, or print secret values (`DATABASE_URL`, `SAM_API_KEY`, `API_KEY`).

## What gets stored

Existing tables in the already-provisioned Supabase project (do not mash into `public.events`; do not create a second schema):

- `public.sam_notices` — upsert on `notice_id`
- `public.sam_ingest_runs` — one row per ingest, `source='csv'`

Ingest writes notice types **o / k / p / r** only (skips award notices and other types):

| Code | CSV `Type` |
|------|------------|
| o | Solicitation |
| k | Combined Synopsis/Solicitation |
| p | Presolicitation |
| r | Sources Sought |

The official public notice URL is always `https://sam.gov/opp/{NoticeId}/view`. CSV `Link` and GSA `uiLink` are not stored (unauthenticated 404s).

## Customer query filter

Default query is **not** “whatever is `Active=Yes` in the extract.” It is:

1. Types `o` / `k` / `p` / `r`
2. Latest row per `solicitation_number` (`posted_date` desc, then `collected_at`) so amendments are not four bids
3. `posted_date` within a rolling last **90 days** so stale leftovers are not customer-ready
4. Default proof slice: `naics_code='541511'` AND `set_aside_code='SBA'` (optional `pop_state`)

Blank solicitation numbers are not collapsed together (each `notice_id` stays its own group).

## Environment variables (names only)

Copy `.env.example` to `.env` and set values locally. Do not put real values in git.

| Name | Required | Used by |
|------|----------|---------|
| `DATABASE_URL` | Ingest and query | Postgres URI as-is: direct host `:5432` or pooler host `:6543`. Connections prefer IPv4 (`hostaddr` / A records) and do not rewrite the URI. |
| `API_KEY` | Query HTTP API | `X-Api-Key` on `GET /notices` |
| `SAM_API_KEY` | No | Optional GSA API only; unused by CSV ingest |

`GET /` is the public product page (HTML). Send `Accept: application/json` for the small API index. `/health` stays public. `GET /notices` requires `X-Api-Key` matching `API_KEY`.

## Install

Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run ingest

Requires `DATABASE_URL` at runtime. Streams the ~250MB CSV; retries `303` / `5xx` with backoff; batch upserts with `INSERT … ON CONFLICT (notice_id)`. Existing proof rows are updated in place, not deleted.

```bash
python -m app.ingest
```

Successful runs insert/update `public.sam_ingest_runs` with `source='csv'` and `status='ok'`.

## Run query

CLI (same 90-day + latest-per-solicitation filter; default proof NAICS / set-aside):

```bash
python -m app.query
python -m app.query --naics 541511 --set-aside SBA --pop-state WA
```

HTTP API (bind `0.0.0.0` and `$PORT` on hosted web services):

```bash
uvicorn app.api:app --host 0.0.0.0 --port "${PORT:-8000}"
```

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS -H "X-Api-Key: <API_KEY>" \
  "http://127.0.0.1:8000/notices?naics=541511&set_aside=SBA"
```

This repository does not create a hosted service. Env names only.

## Tests

```bash
pytest
```

Coverage includes CSV parsing, type filtering (skip awards), solicitation-number dedup, and the 90-day window. Tests do not need `DATABASE_URL`.
