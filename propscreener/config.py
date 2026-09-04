"""Konfiguration via miljøvariabler (12-factor). Se .env.example."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env-indlæser (ingen ekstern afhængighed). Overskriver ikke eksisterende env."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


@dataclass
class Settings:
    # Statstidende
    statstidende_mode: str = "web"
    statstidende_api_base: str = "https://api.statstidende.dk"
    statstidende_web_base: str = "https://www.statstidende.dk"
    statstidende_cert_file: str = ""
    statstidende_key_file: str = ""

    # CVR
    cvrapi_base: str = "https://cvrapi.dk/api"
    cvrapi_user_agent: str = "propscreener/0.1 (https://github.com/daniel-doc-lab/propscreener)"
    cvr_es_base: str = "http://distribution.virk.dk/cvr-permanent/virksomhed/_search"
    cvr_es_user: str = ""
    cvr_es_password: str = ""
    apicvr_mcp_url: str = "https://mcp.apicvr.dk/mcp"   # gratis CVR-opslag (MCP, ingen login)

    # Regnskaber (offentlig, ingen login)
    regnskab_es_base: str = "http://distribution.virk.dk/offentliggoerelser/_search"

    # Datafordeler
    datafordeler_base: str = "https://services.datafordeler.dk"
    datafordeler_user: str = ""
    datafordeler_password: str = ""
    datafordeler_api_key: str = ""          # ny administration (2026): API-Key til frie data
    datafordeler_api_key_param: str = "apikey"

    # DAWA (adresser, gratis)
    dawa_base: str = "https://api.dataforsyningen.dk"

    # Pipeline
    days_back: int = 90
    min_score: int = 40
    cache_dir: Path = field(default_factory=lambda: Path(".cache"))
    request_delay_s: float = 0.5
    timeout_s: float = 30.0
    user_agent: str = "propscreener/0.1 (+https://github.com/daniel-doc-lab/propscreener)"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        s = cls()
        s.statstidende_mode = _env("STATSTIDENDE_MODE", s.statstidende_mode)
        s.statstidende_api_base = _env("STATSTIDENDE_API_BASE", s.statstidende_api_base).rstrip("/")
        s.statstidende_web_base = _env("STATSTIDENDE_WEB_BASE", s.statstidende_web_base).rstrip("/")
        s.statstidende_cert_file = _env("STATSTIDENDE_CERT_FILE")
        s.statstidende_key_file = _env("STATSTIDENDE_KEY_FILE")
        s.cvrapi_user_agent = _env("CVRAPI_USER_AGENT", s.cvrapi_user_agent)
        s.apicvr_mcp_url = _env("APICVR_MCP_URL", s.apicvr_mcp_url)
        s.cvr_es_user = _env("CVR_ES_USER")
        s.cvr_es_password = _env("CVR_ES_PASSWORD")
        s.datafordeler_user = _env("DATAFORDELER_USER")
        s.datafordeler_password = _env("DATAFORDELER_PASSWORD")
        s.datafordeler_api_key = _env("DATAFORDELER_API_KEY")
        s.datafordeler_api_key_param = _env("DATAFORDELER_API_KEY_PARAM", s.datafordeler_api_key_param)
        s.datafordeler_base = _env("DATAFORDELER_BASE", s.datafordeler_base).rstrip("/")
        s.days_back = int(_env("PROPSCREENER_DAYS_BACK", str(s.days_back)))
        s.min_score = int(_env("PROPSCREENER_MIN_SCORE", str(s.min_score)))
        s.cache_dir = Path(_env("PROPSCREENER_CACHE_DIR", str(s.cache_dir)))
        return s

    @property
    def has_datafordeler(self) -> bool:
        return bool(self.datafordeler_api_key or (self.datafordeler_user and self.datafordeler_password))

    @property
    def has_cvr_es(self) -> bool:
        return bool(self.cvr_es_user and self.cvr_es_password)

    @property
    def has_statstidende_cert(self) -> bool:
        return bool(self.statstidende_cert_file)
