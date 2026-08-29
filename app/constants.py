"""Legal source, type codes, and customer-facing query defaults."""

from __future__ import annotations

# Official public Data Services extract (GET; follows 303 to S3).
# Do not scrape SAM HTML/search, Login.gov, Entity Management, or FOUO APIs.
CSV_DOWNLOAD_URL = (
    "https://sam.gov/api/prod/fileextractservices/v1/api/download/"
    "Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv"
    "?privacy=Public"
)

# Optional later path. CSV ingest must not require this key.
GSA_OPPORTUNITIES_SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"

USER_AGENT = (
    "federal-bid-match/0.1 "
    "(public SAM.gov Data Services CSV collector; GET extract only)"
)

# Official notice page. Do not use CSV Link or GSA uiLink (unauthenticated 404s).
OFFICIAL_NOTICE_URL_TEMPLATE = "https://sam.gov/opp/{notice_id}/view"

INGEST_NOTICE_TYPES = frozenset({"o", "k", "p", "r"})

# CSV Type is a full name; API ptype is a letter. Accept both.
TYPE_NAME_TO_CODE: dict[str, str] = {
    "o": "o",
    "solicitation": "o",
    "k": "k",
    "combined synopsis/solicitation": "k",
    "combined synopsis / solicitation": "k",
    "p": "p",
    "presolicitation": "p",
    "pre-solicitation": "p",
    "pre solicitation": "p",
    "r": "r",
    "sources sought": "r",
}

WINDOW_DAYS = 90

DEFAULT_NAICS = "541511"
DEFAULT_SET_ASIDE_CODE = "SBA"

INGEST_SOURCE_CSV = "csv"
