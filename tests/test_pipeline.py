"""End-to-end offline: Statstidende + cvrapi + regnskabsindeks + EJF via FakeHttp."""
import json
from pathlib import Path

from propscreener.config import Settings
from propscreener.demo import cvr_number, generate
from propscreener.export import build_dataset, build_site, load_cases, write_csv, write_json
from propscreener.http import FakeHttp
from propscreener.pipeline import Pipeline

FIX = Path(__file__).parent / "fixtures"
DEKRET = (FIX / "dekret_demo.txt").read_text(encoding="utf-8")
XBRL = (FIX / "aarsrapport_demo.xml").read_text(encoding="utf-8")


def _fake_http() -> FakeHttp:
    DEKRET_PK = "14a1d71df21558e5ade0214f90482cdc"

    def fg(name, **fields):
        return {"name": name, "fields": [{"name": k, "value": v} for k, v in fields.items()]}

    messages = {
        "m1": {"messageNumber": "m1", "publicationDate": "2026-08-26T00:00:00", "sectionName": "Konkursboer",
               "messageTypeName": "Dekret", "title": "Fjord Ejendomme ApS",
               "document": json.dumps({"fieldgroups": [
                   fg("Skyldner", Navn="Fjord Ejendomme ApS", **{"CVR-nummer": "12345678"}, Adresse="Vestergade 12",
                      Postnummer="8000", By="Aarhus C"),
                   fg("Dekret", Dekretdato="2026-08-25", Fristdag="2026-08-10", Skifteret="Skifteretten i Aarhus",
                      Sagsnummer="SKS 41-1234/2026"),
                   fg("Kurator", Navn="Peter Hansen", Firma="Advokatfirmaet Nordlys", Adresse="Åboulevarden 1",
                      Postnummer="8000", By="Aarhus C", Telefon="86 12 34 56", **{"E-mail": "ph@nordlys-demo.dk"}),
               ]})},
        "m2": {"messageNumber": "m2", "publicationDate": "2026-08-27T00:00:00", "sectionName": "Konkursboer",
               "messageTypeName": "Dekret", "document": json.dumps({"fieldgroups": [fg("Meddelelse", Tekst=(
                   "Ved dekret afsagt den 27.08.2026 af Retten i Roskilde er Byens Pizzaria ApS, CVR-nr. 99887766, "
                   "Algade 1, 4000 Roskilde, taget under konkursbehandling. Kurator: advokat Mette Jensen, "
                   "Bystrøm Advokater, Torvet 3, 4000 Roskilde."))]})},
        "m3": {"messageNumber": "m3", "publicationDate": "2026-08-27T00:00:00", "sectionName": "Konkursboer",
               "messageTypeName": "Dekret", "document": json.dumps({"fieldgroups": [fg("Meddelelse", Tekst=(
                   "Konkursdekret over Hans Hansen, født 01.01.1970, Ukendt vej 1."))]})},  # personlig konkurs
        "a1": {"messageNumber": "a1", "publicationDate": "2026-08-30T00:00:00", "sectionName": "Tvangsauktioner",
               "messageTypeName": "Fast ejendom", "document": json.dumps({"fieldgroups": [fg("Ejendom", Tekst=(
                   "Tvangsauktion over ejendommen matr. nr. 12 a, beliggende Vestergade 12, 8000 Aarhus C, "
                   "tilhørende Fjord Ejendomme ApS, CVR-nr. 12345678. Ejendomsværdi: kr. 9.000.000. "
                   "Auktionen afholdes den 15.10.2026."))]})},
    }

    def statstidende(url: str):
        if "/api/messagesearch?" in url:
            ids = ["m1", "m2", "m3"] if f"m={DEKRET_PK}" in url else ["a1"]
            return {"pageCount": 1, "results": [{"messageNumber": i, "publicationDate": messages[i]["publicationDate"]}
                                                for i in ids]}
        for num, body in messages.items():
            if url.endswith(f"/api/message/{num}"):
                return body
        return {"pageCount": 0, "results": []}

    def cvrapi(url: str):
        if "vat=12345678" in url:
            return {"vat": 12345678, "name": "Fjord Ejendomme ApS", "address": "Vestergade 12", "zipcode": "8000",
                    "city": "Aarhus C", "cityname": "Aarhus", "industrycode": 682040,
                    "industrydesc": "Udlejning af erhvervsejendomme", "companydesc": "Anpartsselskab",
                    "startdate": "01/03 - 2015", "status": "UNDER KONKURS", "employees": "2",
                    "owners": [{"name": "Anders Andersen"}]}
        if "vat=99887766" in url:
            return {"vat": 99887766, "name": "Byens Pizzaria ApS", "zipcode": "4000", "city": "Roskilde",
                    "industrycode": 561010, "industrydesc": "Restauranter", "companydesc": "Anpartsselskab"}
        return {"error": "NOT_FOUND"}

    def regnskab(url: str, body):
        if body["query"]["bool"]["must"][0]["term"]["cvrNummer"] != 12345678:
            return {"hits": {"hits": []}}
        return {"hits": {"hits": [{"_source": {"cvrNummer": 12345678, "offentliggoerelsesTidspunkt": "2026-05-01",
                                               "regnskab": {"regnskabsperiode": {"slutDato": "2025-12-31"}},
                                               "dokumenter": [
                                                   {"dokumentMimeType": "application/pdf", "dokumentUrl": "https://regnskaber.virk.dk/x.pdf"},
                                                   {"dokumentMimeType": "application/xml", "dokumentUrl": "https://regnskaber.virk.dk/x.xml"},
                                               ]}}]}}

    def ejf(url: str):
        if "CVRnr=12345678" in url:
            return {"features": [{"properties": {"bestemtFastEjendomBFENr": 1234567, "ejerandel_taeller": 1,
                                                 "ejerandel_naevner": 1, "ejendomstype": "Samlet fast ejendom"}}]}
        return {"features": []}

    def dawa(url: str):
        if "bfe=1234567" in url:
            return [{"betegnelse": "Vestergade 12, 8000 Aarhus C", "postnr": "8000", "postnrnavn": "Aarhus C",
                     "kommunenavn": "Aarhus", "x": 10.2039, "y": 56.1572}]
        return []

    return FakeHttp({
        "https://www.statstidende.dk/api": statstidende,
        "https://cvrapi.dk/api": cvrapi,
        "http://distribution.virk.dk/offentliggoerelser/_search": regnskab,
        "https://regnskaber.virk.dk/x.xml": XBRL,
        "https://services.datafordeler.dk/EJERFORTEGNELSE": ejf,
        "https://services.datafordeler.dk/VUR": lambda u: [{"ejendomsvaerdi": 9_400_000}],
        "https://api.dataforsyningen.dk/adresser": dawa,
    })


def _settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.cache_dir = tmp_path / "cache"
    s.datafordeler_user, s.datafordeler_password = "u", "p"
    s.request_delay_s = 0
    return s


def test_pipeline_end_to_end(tmp_path: Path):
    pipe = Pipeline(_settings(tmp_path), http=_fake_http())  # type: ignore[arg-type]
    cases, stats = pipe.run(days_back=30, min_score=0)

    assert stats.dekreter == 2  # personlig konkurs uden CVR/selskab filtreret fra
    by_cvr = {c.selskab.cvr: c for c in cases}
    fjord = by_cvr["12345678"]
    assert fjord.selskab.branchekode == "682040"
    assert fjord.selskab.region == "Midtjylland"
    assert fjord.regnskab.investeringsejendomme == 48_500_000
    assert fjord.regnskab.ltv_pct == round(100 * 41_000_000 / 48_500_000, 1)
    ejf_prop = next(p for p in fjord.ejendomme if p.kilde == "ejerfortegnelsen")
    auk_prop = next(p for p in fjord.ejendomme if p.kilde == "tvangsauktion")
    assert ejf_prop.bfe_nummer == "1234567"
    assert ejf_prop.adresse == "Vestergade 12, 8000 Aarhus C"
    assert ejf_prop.offentlig_vurdering == 9_400_000
    assert ejf_prop.lat == 56.1572
    assert auk_prop.tvangsauktion_dato == "2026-10-15" and auk_prop.offentlig_vurdering == 9_000_000
    assert stats.tvangsauktioner == 1
    assert "tvangsauktion" in fjord.kilder
    assert fjord.score == 100 and fjord.konfidens == "høj"
    assert "ejerfortegnelsen" in fjord.kilder and "regnskab-xbrl" in fjord.kilder and "cvrapi" in fjord.kilder
    assert fjord.links["aarsrapport"].endswith(".pdf")
    assert fjord.kurator.email == "ph@nordlys-demo.dk"

    pizza = by_cvr["99887766"]
    assert pizza.score == 0 and pizza.konfidens == "lav"
    assert cases[0] is fjord  # sorteret efter score

    # filtrering
    pipe2 = Pipeline(_settings(tmp_path), http=_fake_http())  # type: ignore[arg-type]
    selected, _ = pipe2.run(days_back=30, min_score=40)
    assert [c.selskab.cvr for c in selected] == ["12345678"]


def test_export_roundtrip_and_site(tmp_path: Path):
    cases, stats = generate(n=12, seed=1)
    ds = build_dataset(cases, stats, demo=True)
    write_json(ds, tmp_path / "cases.json")
    write_csv(cases, tmp_path / "cases.csv")
    loaded, meta = load_cases(tmp_path / "cases.json")
    assert meta["demo"] is True and meta["antal"] == 12
    assert [c.id for c in loaded] == [c.id for c in cases]
    assert loaded[0].to_dict() == cases[0].to_dict()
    csv_text = (tmp_path / "cases.csv").read_text(encoding="utf-8-sig")
    assert csv_text.splitlines()[0].startswith("score;konfidens;cvr;navn")
    assert len(csv_text.splitlines()) == 13

    out = build_site(ds, tmp_path / "site" / "index.html")
    html = out.read_text(encoding="utf-8")
    assert "/*__PROPSCREENER_DATA__*/null" not in html
    assert json.dumps(cases[0].selskab.navn, ensure_ascii=False) in html


def test_demo_is_deterministic_and_cvr_valid():
    a, _ = generate(n=20, seed=7)
    b, _ = generate(n=20, seed=7)
    assert [c.id for c in a] == [c.id for c in b]
    weights = [2, 7, 6, 5, 4, 3, 2, 1]
    for _ in range(50):
        n = cvr_number(__import__("random").Random(_))
        assert sum(int(d) * w for d, w in zip(n, weights, strict=True)) % 11 == 0
    assert any(c.score >= 60 for c in a) and any(c.score < 40 for c in a)


def test_merge_with_existing_keeps_recent_unseen(tmp_path: Path):
    from propscreener.export import merge_with_existing
    old, stats = generate(n=6, seed=3)
    write_json(build_dataset(old, stats, demo=True), tmp_path / "cases.json")
    new, _ = generate(n=3, seed=3)          # samme tre første id'er som `old`
    new[0].score = 99
    merged, kept = merge_with_existing(new, tmp_path / "cases.json", retention_days=365)
    assert kept == 3 and len(merged) == 6
    assert next(c for c in merged if c.id == new[0].id).score == 99   # ny version vinder
    merged2, kept2 = merge_with_existing(new, tmp_path / "cases.json", retention_days=0)
    assert kept2 == 0 and len(merged2) == 3                            # uden retention: kun nye


def test_apicvr_mcp_lookup_parses_sse():
    from propscreener.sources.cvr import ApiCvrMcp
    calls = []

    def mcp(url, body):
        calls.append(body["method"])
        if body["method"] == "initialize":
            return 'event: message\ndata: {"result":{"protocolVersion":"2025-03-26"},"jsonrpc":"2.0","id":1}\n'
        return ('event: message\ndata: {"result":{"content":[{"type":"text","text":"{\\"vat\\":12345678,'
                '\\"name\\":\\"Fjord Ejendomme ApS\\",\\"industrycode\\":682040,\\"zipcode\\":\\"8000\\"}"}]},"jsonrpc":"2.0","id":2}\n')

    s = Settings()
    client = ApiCvrMcp(s, FakeHttp({"https://mcp.apicvr.dk/mcp": mcp}))  # type: ignore[arg-type]
    data = client.lookup("12345678")
    assert data["name"] == "Fjord Ejendomme ApS" and calls == ["initialize", "tools/call"]
    from propscreener.models import Company
    c = ApiCvrMcp.apply(Company(cvr="12345678"), data)
    assert c.branchekode == "682040" and c.region == "Midtjylland"
