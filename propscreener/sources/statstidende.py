"""Statstidende – konkursdekreter og tvangsauktioner.

Statstidende (Civilstyrelsen) er den *autoritative* kilde: et konkursdekret
har først retsvirkning over for tredjemand når det er bekendtgjort her.

To adgangsveje:

  mode="api"  Officiel REST-webservice på https://api.statstidende.dk.
              Kræver aftale med Civilstyrelsen og OCES3-virksomhedscertifikat
              (mutual TLS). Dokumentation: https://api.statstidende.dk/docs/index.html
              (kun tilgængelig med certifikat).

  mode="web"  Den offentlige søgning på https://www.statstidende.dk. Sitet er en
              React-SPA der henter JSON fra et internt, åbent API (verificeret
              4. september 2026 fra GitHub Actions):

                GET /api/section                         rubrik-katalog (publicKey pr. rubrik)
                GET /api/messagesearch?m=<pk>&s=8&fromDate=YYYY-MM-DD&toDate=YYYY-MM-DD&page=0&ps=100
                GET /api/messagesearch/messagetypecount?…  antal pr. rubrik
                GET /api/message/{messageNumber}         hele meddelelsen (feltgrupper)
                GET /api/Publication/GetLatestPublication  dagens udgave (fileId -> …/pdf)

              `m` er rubrikkens publicKey uden bindestreger (kan gentages), `s=8`
              er tilstanden "kundgjort". Se docs/DATA_SOURCES.md.

Uanset adgangsvej normaliseres svaret til `RawMessage`, og dekretteksten
parses med `parse_dekret_text`, som er den del der er dækket af tests.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from ..config import Settings
from ..http import Http, HttpError
from ..models import BankruptcyCase, Kurator, Property, Skifteret

log = logging.getLogger(__name__)

# Meddelelsestyper i Statstidende (kategori -> undertype). Bruges til filtrering.
# (sektion, rubrik, publicKey). Nøglerne stammer fra GET /api/section (4. sep. 2026).
MESSAGE_TYPES: dict[str, tuple[str, str, str]] = {
    "konkurs_dekret": ("Konkursboer", "Dekret", "14a1d71d-f215-58e5-ade0-214f90482cdc"),
    "konkurs_ophaevelse": ("Konkursboer", "Ophævelse af dekret", "383f1800-1b39-5f39-8250-61a5c0798fad"),
    "konkurs_afslutning": ("Konkursboer", "Regnskab og boafslutning", "018d0141-0efb-5472-a698-9328817df00a"),
    "tvangsauktion_fast_ejendom": ("Tvangsauktioner", "Fast ejendom", "2aa7d6a1-b250-51a8-88a6-3f6c18574526"),
    "tvangsauktion_andelsbolig": ("Tvangsauktioner", "Andelsbolig", "84aba03b-79ab-48ca-b318-8f8d90f0b095"),
}
SECTION_KONKURSBOER = "c245eeb3-4c82-5e36-8bbb-7a3f098ee1a8"
SECTION_TVANGSAUKTIONER = "be95960b-a673-5f46-8bf0-f78b29af21f7"

WEB_SEARCH_PATH = "/api/messagesearch"
WEB_MESSAGE_PATH = "/api/message/{messageNumber}"
WEB_SECTION_PATH = "/api/section"
WEB_STATE_PUBLISHED = 8          # parameter `s` i søgningen: kundgjorte meddelelser
API_SEARCH_PATH = "/v1/messages"  # officielt API (certifikat)


@dataclass
class RawMessage:
    id: str
    url: str
    kategori: str
    undertype: str
    offentliggjort: str | None
    overskrift: str | None
    tekst: str
    felter: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- parsing

DATE_RE = r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})"
MONTHS = {m: i + 1 for i, m in enumerate(
    ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
     "november", "december"])}


def parse_date(text: str | None) -> str | None:
    """'25.08.2026', '25/8-2026', '25. august 2026', '2026-08-25' -> '2026-08-25'."""
    if not text:
        return None
    t = text.strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(DATE_RE, t)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\.?\s+([a-zæøå]+)\s+(\d{4})", t, re.IGNORECASE)
    if m and m.group(2).lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


CVR_RE = re.compile(r"CVR[-\s]?(?:nr\.?|nummer)?[:\s]*(\d{2}\s?\d{2}\s?\d{2}\s?\d{2})", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:tlf\.?|telefon|tel\.?)[:\s]*((?:\+45\s?)?(?:\d{2}\s?){4})", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
POSTNR_BY_RE = re.compile(r"\b(\d{4})\s+([A-ZÆØÅ][\wÆØÅæøå.\- ]+?)(?=[,.;\n]|$| tlf| telefon| e-mail| mail)", re.IGNORECASE)
SAGSNR_RE = re.compile(r"\b((?:SKS|SKA|BS|KS|K)\s?[\w-]*\d+[-/]\d{2,4}(?:[-/]\d+)?)", re.IGNORECASE)
SKIFTERET_RE = re.compile(
    r"(Sø-\s?og\s?Handelsrettens?\s?skifteret(?:safdeling)?|Skifteretten\s+(?:i|på)\s+[A-ZÆØÅ][\wæøå]+(?:\s[A-ZÆØÅ][\wæøå]+)?|"
    r"Retten\s+(?:i|på)\s+[A-ZÆØÅ][\wæøå]+(?:\s[A-ZÆØÅ][\wæøå]+)?)")
DATE_ANY = r"(\d{1,2}\.?\s+[a-zæøå]+\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})"
DEKRET_RE = re.compile(r"(?:dekret|konkursdekret)\s+(?:er\s+)?afsagt\s+(?:den\s+)?" + DATE_ANY,
                       re.IGNORECASE)
FRISTDAG_RE = re.compile(r"fristdag(?:en)?[:\s]*(?:er\s+)?(?:den\s+)?" + DATE_ANY, re.IGNORECASE)
SKIFTESAMLING_RE = re.compile(r"skiftesamling[^\n]*?(?:den\s+)?" + DATE_ANY, re.IGNORECASE)
KURATOR_RE = re.compile(
    r"(?:kurator(?:er)?|bobestyrer)\s*(?:er|:)?\s*(?:advokat(?:erne)?\s+)?(.+?)(?=\.\s+(?:[A-ZÆØÅ]|$)|\n\s*\n|$)",
    re.IGNORECASE | re.DOTALL)
NAME_ON_OWN_LINE_RE = re.compile(r"^\s*(.+?(?:ApS|A/S|K/S|P/S|I/S|IVS|S\.M\.B\.A|AMBA|A\.M\.B\.A\.))\s*$", re.MULTILINE | re.IGNORECASE)
COMPANY_FORM_RE = re.compile(r"\b(ApS|A/S|K/S|P/S|I/S|IVS|S\.M\.B\.A\.?|A\.M\.B\.A\.?|AMBA)\b", re.IGNORECASE)


def _clean(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip(" ,.;:")
    return s or None


def parse_kurator(fragment: str) -> Kurator:
    """'Advokat Peter Hansen, Advokatfirmaet X, Åboulevarden 1, 8000 Aarhus C, tlf. 86 12 34 56, e-mail ph@x.dk'"""
    k = Kurator()
    frag = re.sub(r"\s+", " ", fragment).strip()
    email = EMAIL_RE.search(frag)
    if email:
        k.email = email.group(0).rstrip(".")
        frag = frag.replace(email.group(0), "")
    phone = PHONE_RE.search(frag)
    if phone:
        k.telefon = re.sub(r"\s+", " ", phone.group(1)).strip()
        frag = frag[: phone.start()] + frag[phone.end():]
    frag = re.sub(r"(?:e-?mail|mail)[:\s]*", "", frag, flags=re.IGNORECASE)
    parts = [p.strip() for p in re.split(r",|\n", frag) if p.strip()]
    if not parts:
        return k
    k.navn = _clean(re.sub(r"^advokat(?:erne)?\s+", "", parts[0], flags=re.IGNORECASE))
    rest = parts[1:]
    for p in rest:
        m = re.match(r"^(\d{4})\s+(.+)$", p)
        if m:
            k.postnr, k.by = m.group(1), _clean(m.group(2))
        elif re.search(r"\d", p) and not k.adresse:
            k.adresse = _clean(p)
        elif not k.firma and re.search(r"advokat|law|legal|partner|kammer|firma", p, re.IGNORECASE):
            k.firma = _clean(p)
        elif not k.firma and not k.adresse:
            k.firma = _clean(p)
    if k.navn:
        q = k.navn.replace(" ", "+")
        k.advokatsamfundet_url = f"https://www.advokatsamfundet.dk/find-advokat/?q={q}"
    return k


def parse_dekret_text(text: str) -> dict[str, Any]:
    """Udtræk strukturerede felter fra et konkursdekret (fritekst). Returnerer dict med
    keys: cvr, navn, selskabsform, adresse, postnr, by, dekretdato, fristdag, skifteret,
    sagsnummer, skiftesamling, kurator (Kurator)."""
    t = text.replace("\r", "")
    out: dict[str, Any] = {}

    m = CVR_RE.search(t)
    out["cvr"] = re.sub(r"\s", "", m.group(1)) if m else None

    m = NAME_ON_OWN_LINE_RE.search(t)
    if m:
        out["navn"] = _clean(m.group(1))
    else:
        # "... er Demo Ejendomme ApS, CVR-nr. ..." / "Demo Ejendomme ApS under konkurs"
        m = re.search(r"\b(?:er|for|vedrørende|vedr\.)\s+([A-ZÆØÅ0-9][^\n,]*?(?:ApS|A/S|K/S|P/S|I/S|IVS))\b", t)
        out["navn"] = _clean(m.group(1)) if m else None
    if out.get("navn"):
        fm = COMPANY_FORM_RE.search(out["navn"])
        out["selskabsform"] = fm.group(1).upper().replace("APS", "ApS").replace("IVS", "IVS") if fm else None

    m = DEKRET_RE.search(t)
    out["dekretdato"] = parse_date(m.group(1)) if m else None
    m = FRISTDAG_RE.search(t)
    out["fristdag"] = parse_date(m.group(1)) if m else None
    m = SKIFTERET_RE.search(t)
    out["skifteret"] = _clean(m.group(1)) if m else None
    m = SAGSNR_RE.search(t)
    out["sagsnummer"] = _clean(m.group(1)) if m else None
    m = SKIFTESAMLING_RE.search(t)
    out["skiftesamling"] = parse_date(m.group(1)) if m else None

    # skyldners adresse: linjer mellem CVR og "taget under konkurs"
    addr_block = None
    m = re.search(r"CVR[^\n]*\n(.+?)(?:\n\s*(?:er\s+)?(?:taget|blev|erklæret)|\n\s*\n)", t, re.IGNORECASE | re.DOTALL)
    if m:
        addr_block = [ln.strip() for ln in m.group(1).split("\n") if ln.strip()]
    if addr_block:
        pb = None
        for ln in addr_block:
            pm = re.match(r"^(\d{4})\s+(.+)$", ln)
            if pm:
                pb = pm
        if pb:
            out["postnr"], out["by"] = pb.group(1), _clean(pb.group(2))
        street = [ln for ln in addr_block if not re.match(r"^\d{4}\s", ln)]
        out["adresse"] = _clean(", ".join(street)) if street else None

    m = KURATOR_RE.search(t)
    out["kurator"] = parse_kurator(m.group(1)) if m else Kurator()
    return out


# ----------------------------------------------------------------------- normalisering

_KEY_ALIASES = {
    "id": ("messageNumber", "id", "messageId", "meddelelsesId", "uuid"),
    "offentliggjort": ("publicationDate", "publishedDate", "published", "offentliggoerelsesDato", "offentliggjort",
                       "publicationTime"),
    "overskrift": ("title", "heading", "overskrift", "headline", "summary"),
    "tekst": ("text", "body", "content", "tekst", "meddelelsestekst", "plainText", "bodyText"),
    "kategori": ("category", "messageCategory", "kategori", "messageTypeCategory", "type"),
    "undertype": ("messageType", "subType", "undertype", "meddelelsestype", "messageTypeName"),
}


def _pick(d: dict[str, Any], key: str) -> Any:
    lower = {k.lower(): v for k, v in d.items()}
    for alias in _KEY_ALIASES[key]:
        if alias.lower() in lower and lower[alias.lower()] not in (None, ""):
            return lower[alias.lower()]
    return None


def _stringify(v: Any) -> str:
    if isinstance(v, dict):
        return "\n".join(f"{k}: {_stringify(x)}" for k, x in v.items())
    if isinstance(v, list):
        return "\n".join(_stringify(x) for x in v)
    return str(v)


def _strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def normalize_message(raw: dict[str, Any], web_base: str) -> RawMessage:
    """Konvertér et vilkårligt Statstidende-JSON-objekt til RawMessage."""
    mid = str(_pick(raw, "id") or "")
    kat = _stringify(_pick(raw, "kategori") or "")
    und = _stringify(_pick(raw, "undertype") or "")
    tekst = _pick(raw, "tekst") or ""
    if not isinstance(tekst, str):
        tekst = _stringify(tekst)
    # strukturerede felter (nyt Statstidende gemmer formularfelter separat)
    felter = raw.get("fields") or raw.get("felter") or raw.get("formData") or {}
    if isinstance(felter, list):
        felter = {str(f.get("name") or f.get("label") or i): f.get("value") for i, f in enumerate(felter)
                  if isinstance(f, dict)}
    full_text = _strip_html(tekst)
    if felter:
        full_text = (full_text + "\n\n" + _stringify(felter)).strip()
    return RawMessage(
        id=mid,
        url=f"{web_base}/messages/{mid}" if mid else web_base,
        kategori=kat,
        undertype=und,
        offentliggjort=parse_date(str(_pick(raw, "offentliggjort") or "")),
        overskrift=_pick(raw, "overskrift"),
        tekst=full_text,
        felter=felter if isinstance(felter, dict) else {},
    )


def _extract_list(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if isinstance(body, dict):
        for key in ("messages", "items", "results", "data", "hits", "meddelelser", "content"):
            v = body.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict) and isinstance(v.get("hits"), list):
                return [h.get("_source", h) for h in v["hits"]]
    return []


# ---------------------------------------------------------------------------- klient

def flatten_fieldgroups(groups: Any) -> tuple[dict[str, str], str]:
    """Statstidendes meddelelser består af feltgrupper -> felter. Returnerer
    (felter, tekst) hvor felter har nøglerne "gruppe/felt" og "felt", og tekst er
    en læsbar gengivelse "Gruppe\nFelt: værdi" som regex-parseren kan arbejde på."""
    felter: dict[str, str] = {}
    lines: list[str] = []
    if isinstance(groups, dict):
        groups = groups.get("fieldgroups") or groups.get("fieldGroups") or []
    for g in groups or []:
        if not isinstance(g, dict):
            continue
        gname = str(g.get("name") or g.get("label") or g.get("publicKey") or "").strip()
        fields = g.get("fields") or g.get("felter") or []
        if gname:
            lines.append(gname)
        for f in fields or []:
            if not isinstance(f, dict):
                continue
            fname = str(f.get("name") or f.get("label") or f.get("publicKey") or "").strip()
            val = f.get("value")
            if val in (None, "", [], {}):
                continue
            if isinstance(val, (dict, list)):
                val = _stringify(val)
            val = _strip_html(str(val))
            felter[f"{gname}/{fname}".lower()] = val
            felter.setdefault(fname.lower(), val)
            lines.append(f"{fname}: {val}" if fname else val)
        lines.append("")
    return felter, "\n".join(lines).strip()


def web_message_to_raw(body: dict[str, Any], web_base: str) -> RawMessage:
    """GET /api/message/{messageNumber} -> RawMessage."""
    number = str(body.get("messageNumber") or body.get("id") or "")
    doc = body.get("document")
    groups: Any = None
    if isinstance(doc, str):
        try:
            groups = json.loads(doc)
        except json.JSONDecodeError:
            groups = None
    elif isinstance(doc, dict):
        groups = doc
    if groups is None:
        groups = body.get("fieldGroups") or body.get("fieldgroups") or []
    felter, tekst = flatten_fieldgroups(groups)
    summary = body.get("summaryFields")
    if isinstance(summary, list):
        for it in summary:
            if isinstance(it, dict) and it.get("value") not in (None, ""):
                felter.setdefault(str(it.get("name") or it.get("label") or "").lower(), str(it["value"]))
    title = body.get("title")
    if title:
        tekst = f"{title}\n{tekst}"
    return RawMessage(
        id=number,
        url=f"{web_base}/messages/{number}" if number else web_base,
        kategori=str(body.get("sectionName") or ""),
        undertype=str(body.get("messageTypeName") or ""),
        offentliggjort=parse_date(str(body.get("publicationDate") or "")),
        overskrift=title,
        tekst=tekst,
        felter=felter,
    )


class StatstidendeClient:
    def __init__(self, settings: Settings, http: Http):
        self.s = settings
        self.http = http
        self.web_base = settings.statstidende_web_base
        self.api_base = settings.statstidende_api_base
        self.mode = settings.statstidende_mode

    # -- katalog ---------------------------------------------------------------
    def sections(self) -> list[dict[str, Any]]:
        body = self.http.get_json(self.web_base + WEB_SECTION_PATH, cache_ttl_s=7 * 24 * 3600)
        return body if isinstance(body, list) else []

    def probe(self) -> list[tuple[str, str, str]]:
        """Tjek at søgning og katalog svarer. Returnerer [(method, url, status)]."""
        out: list[tuple[str, str, str]] = []
        try:
            secs = self.sections()
            names = [f"{x.get('name')}({x.get('id')})" for x in secs]
            out.append(("GET", self.web_base + WEB_SECTION_PATH, f"OK – {len(secs)} sektioner: {', '.join(names)[:200]}"))
        except Exception as e:  # noqa: BLE001
            out.append(("GET", self.web_base + WEB_SECTION_PATH, f"fejl: {e}"))
        try:
            d1 = date.today()
            body = self._search_page("konkurs_dekret", d1 - timedelta(days=7), d1, 0, 5)
            items = _extract_list(body)
            keys = list(body.keys())[:12] if isinstance(body, dict) else []
            out.append(("GET", self.web_base + WEB_SEARCH_PATH,
                        f"OK – {len(items)} af pageCount={body.get('pageCount') if isinstance(body, dict) else '?'}; nøgler {keys}"))
        except Exception as e:  # noqa: BLE001
            out.append(("GET", self.web_base + WEB_SEARCH_PATH, f"fejl: {e}"))
        return out

    # -- søgning --------------------------------------------------------------
    def search(self, type_key: str, date_from: date, date_to: date | None = None,
               page_size: int = 100) -> Iterable[RawMessage]:
        date_to = date_to or date.today()
        if self.mode == "api":
            yield from self._search_api(type_key, date_from, date_to, page_size)
        else:
            yield from self._search_web(type_key, date_from, date_to, page_size)

    def _search_api(self, type_key: str, d0: date, d1: date, page_size: int) -> Iterable[RawMessage]:
        _, _, public_key = MESSAGE_TYPES[type_key]
        d = d0
        while d <= d1:  # det officielle API henter pr. kundgørelsesdato
            body = self.http.get_json(self.api_base + API_SEARCH_PATH,
                                      params={"publicationdate": d.isoformat(), "messagetypes": public_key},
                                      cache_ttl_s=24 * 3600)
            for it in _extract_list(body):
                yield normalize_message(it, self.web_base)
            d += timedelta(days=1)

    def _search_page(self, type_key: str, d0: date, d1: date, page: int, page_size: int) -> Any:
        _, _, public_key = MESSAGE_TYPES[type_key]
        params: list[tuple[str, Any]] = [
            ("m", public_key.replace("-", "")), ("s", WEB_STATE_PUBLISHED),
            ("fromDate", d0.isoformat()), ("toDate", d1.isoformat()),
            ("page", page), ("ps", page_size),
        ]
        return self.http.get_json(self.web_base + WEB_SEARCH_PATH, params=dict(params), cache_ttl_s=3600)

    def _search_web(self, type_key: str, d0: date, d1: date, page_size: int) -> Iterable[RawMessage]:
        page = 0
        seen: set[str] = set()
        while True:
            body = self._search_page(type_key, d0, d1, page, page_size)
            items = _extract_list(body)
            if not items:
                return
            for it in items:
                number = str(_pick(it, "id") or "")
                if not number or number in seen:
                    continue
                seen.add(number)
                msg = self.fetch_message(number)
                if msg is None:
                    msg = normalize_message(it, self.web_base)
                if not msg.offentliggjort:
                    msg.offentliggjort = parse_date(str(_pick(it, "offentliggjort") or ""))
                yield msg
            page_count = body.get("pageCount") if isinstance(body, dict) else None
            if page_count is not None and page + 1 >= int(page_count):
                return
            if page_count is None and len(items) < page_size:
                return
            page += 1

    def fetch_message(self, message_number: str) -> RawMessage | None:
        url = self.web_base + WEB_MESSAGE_PATH.format(messageNumber=message_number)
        try:
            body = self.http.get_json(url, cache_ttl_s=30 * 24 * 3600)
        except HttpError as e:
            log.warning("meddelelse %s: %s", message_number, e)
            return None
        if not isinstance(body, dict):
            return None
        return web_message_to_raw(body, self.web_base)

    def debug_dump(self, type_key: str = "konkurs_dekret", days: int = 3) -> dict[str, Any]:
        """Rå svar fra søgning + første meddelelse – til at verificere feltnavne."""
        d1 = date.today()
        body = self._search_page(type_key, d1 - timedelta(days=days), d1, 0, 3)
        items = _extract_list(body)
        first = None
        if items:
            number = str(_pick(items[0], "id") or "")
            url = self.web_base + WEB_MESSAGE_PATH.format(messageNumber=number)
            first = self.http.get_json(url, cache_ttl_s=None)
        return {"search": body, "first_message": first}


# ---------------------------------------------------------------- dekret -> BankruptcyCase

def _group_fields(f: dict[str, str], *group_words: str) -> dict[str, str]:
    """Felter i feltgrupper hvis navn indeholder et af ordene: {"navn": ..., "postnummer": ...}."""
    out: dict[str, str] = {}
    for k, v in f.items():
        if "/" not in k:
            continue
        g, name = k.split("/", 1)
        if any(w in g for w in group_words):
            out.setdefault(name, v)
    return out


def _kurator_from_fields(kf: dict[str, str]) -> Kurator | None:
    if not kf:
        return None

    def g(*names: str) -> str | None:
        for n in names:
            for k, v in kf.items():
                if k == n or k.startswith(n):
                    return _clean(v)
        return None

    k = Kurator(
        navn=g("navn", "kurator", "advokat"),
        firma=g("firma", "advokatfirma", "virksomhed", "selskab"),
        adresse=g("adresse", "vej", "gade"),
        postnr=g("postnummer", "postnr"),
        by=g("by", "bynavn"),
        telefon=g("telefon", "tlf"),
        email=g("e-mail", "email", "mail"),
    )
    if k.postnr and not k.postnr.isdigit():
        m = re.match(r"(\d{4})\s*(.*)", k.postnr)
        if m:
            k.postnr, k.by = m.group(1), k.by or _clean(m.group(2))
    if not any((k.navn, k.firma, k.email, k.telefon)):
        return None
    if k.navn:
        k.advokatsamfundet_url = "https://www.advokatsamfundet.dk/find-advokat/?q=" + k.navn.replace(" ", "+")
    return k


def message_to_case(msg: RawMessage) -> BankruptcyCase:
    parsed = parse_dekret_text(msg.tekst)
    # strukturerede felter vinder over regex hvis de findes
    f = {k.lower(): v for k, v in msg.felter.items()}
    skyldner = _group_fields(f, "skyldner", "virksomhed", "selskab", "konkurs")

    def fld(*names: str) -> str | None:
        for n in names:
            for src in (skyldner, f):
                v = src.get(n.lower())
                if v:
                    return _stringify(v)
        return None

    cvr = re.sub(r"\D", "", fld("cvr", "cvr-nummer", "cvrnummer", "cvr-nr", "cvrnr", "cvr nr") or "") or parsed.get("cvr")
    if cvr and len(cvr) != 8:
        cvr = parsed.get("cvr") or (cvr if len(cvr) == 8 else None)
    navn = fld("navn", "skyldner", "virksomhedsnavn", "selskabsnavn", "selskab") or parsed.get("navn")
    kurator = _kurator_from_fields(_group_fields(f, "kurator", "bobestyrer"))
    if kurator is None:
        kurator = parse_kurator(fld("kurator")) if fld("kurator") else parsed.get("kurator", Kurator())
    case = BankruptcyCase(
        id=cvr or f"st-{msg.id}",
        statstidende_id=msg.id or None,
        statstidende_url=msg.url,
        meddelelsestype="Konkursdekret",
        offentliggjort=msg.offentliggjort,
        dekretdato=parse_date(fld("dekretdato", "dekret afsagt", "dato for dekret", "dekretets dato", "dato"))
        or parsed.get("dekretdato"),
        fristdag=parse_date(fld("fristdag")) or parsed.get("fristdag"),
        skiftesamling=parse_date(fld("skiftesamling")) or parsed.get("skiftesamling"),
        skifteret=Skifteret(navn=fld("skifteret", "retten", "ret") or parsed.get("skifteret"),
                            sagsnummer=fld("sagsnummer", "sagsnr", "sags nr", "sag") or parsed.get("sagsnummer")),
        kurator=kurator,
        raa_tekst=msg.tekst,
        kilder=["statstidende"],
    )
    case.selskab.cvr = cvr
    case.selskab.navn = navn
    fm = COMPANY_FORM_RE.search(navn or "")
    case.selskab.selskabsform = (fm.group(1).upper().replace("APS", "ApS") if fm else None) or parsed.get("selskabsform")
    case.selskab.adresse = fld("adresse", "vejnavn", "vej") or parsed.get("adresse")
    postnr = fld("postnummer", "postnr")
    if postnr and not postnr.strip().isdigit():
        m = re.match(r"\s*(\d{4})\s*(.*)", postnr)
        postnr, by = (m.group(1), _clean(m.group(2))) if m else (None, None)
    else:
        by = None
    case.selskab.postnr = postnr or parsed.get("postnr")
    case.selskab.by = fld("by", "bynavn") or by or parsed.get("by")
    case.selskab.status = "UNDER KONKURS"
    base = case.offentliggjort or case.dekretdato
    if base:
        case.anmeldelsesfrist = (datetime.fromisoformat(base) + timedelta(weeks=4)).date().isoformat()
    if cvr:
        case.links["cvr"] = f"https://datacvr.virk.dk/enhed/virksomhed/{cvr}"
    case.links["statstidende"] = msg.url
    return case


# ----------------------------------------------------------------------- tvangsauktion

EJENDOMSVAERDI_RE = re.compile(r"ejendomsværdi[:\s]*(?:kr\.?\s*)?([\d.]+)", re.IGNORECASE)
MATRIKEL_RE = re.compile(r"matr\.?\s*nr\.?\s*([\w\s,]+?)(?:,|\n|beliggende)", re.IGNORECASE)
AUKTION_DATO_RE = re.compile(r"auktion(?:en)?\s+(?:afholdes\s+)?(?:den\s+)?" + DATE_ANY, re.IGNORECASE)
BELIGGENDE_RE = re.compile(r"beliggende\s+([^\n,]+?,\s*\d{4}\s+[^\n,.]+)", re.IGNORECASE)


def parse_tvangsauktion(msg: RawMessage) -> Property:
    t = msg.tekst
    p = Property(kilde="tvangsauktion", tvangsauktion_url=msg.url)
    m = BELIGGENDE_RE.search(t)
    if m:
        addr = m.group(1)
        pm = re.search(r"(.+?),\s*(\d{4})\s+(.+)$", addr)
        if pm:
            p.adresse, p.postnr, p.by = _clean(pm.group(1)), pm.group(2), _clean(pm.group(3))
        else:
            p.adresse = _clean(addr)
    m = MATRIKEL_RE.search(t)
    p.matrikel = _clean(m.group(1)) if m else None
    m = EJENDOMSVAERDI_RE.search(t)
    if m:
        try:
            p.offentlig_vurdering = int(m.group(1).replace(".", ""))
        except ValueError:
            pass
    m = AUKTION_DATO_RE.search(t)
    p.tvangsauktion_dato = parse_date(m.group(1)) if m else None
    if re.search(r"ejerlejlighed", t, re.IGNORECASE):
        p.ejendomstype = "Ejerlejlighed"
    elif re.search(r"erhverv|kontor|lager|butik", t, re.IGNORECASE):
        p.ejendomstype = "Erhvervsejendom"
    else:
        p.ejendomstype = "Samlet fast ejendom"
    return p


def auction_debtor_keys(msg: RawMessage) -> tuple[str | None, str | None]:
    """(cvr, navn) på skyldner/ejer i en tvangsauktionsmeddelelse."""
    m = CVR_RE.search(msg.tekst)
    cvr = re.sub(r"\s", "", m.group(1)) if m else None
    m = re.search(r"(?:tilhørende|ejer|skyldner|rekvisitus)[:\s]+([^\n,]+?(?:ApS|A/S|K/S|P/S|I/S|IVS))", msg.tekst,
                  re.IGNORECASE)
    navn = _clean(m.group(1)) if m else None
    return cvr, navn
