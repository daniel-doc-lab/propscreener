import json
from datetime import date
from pathlib import Path

from propscreener.sources.statstidende import (
    RawMessage,
    _extract_list,
    auction_debtor_keys,
    message_to_case,
    normalize_message,
    parse_date,
    parse_dekret_text,
    parse_kurator,
    parse_tvangsauktion,
    web_message_to_raw,
)

FIX = Path(__file__).parent / "fixtures"


def test_parse_date_variants():
    assert parse_date("25.08.2026") == "2026-08-25"
    assert parse_date("25/8-2026") == "2026-08-25"
    assert parse_date("22. september 2026") == "2026-09-22"
    assert parse_date("2026-08-25T10:00:00Z") == "2026-08-25"
    assert parse_date("31.02.2026") is None
    assert parse_date(None) is None


def test_parse_dekret_text_full():
    d = parse_dekret_text((FIX / "dekret_demo.txt").read_text(encoding="utf-8"))
    assert d["cvr"] == "12345678"
    assert d["navn"] == "Fjord Ejendomme ApS"
    assert d["selskabsform"] == "ApS"
    assert d["dekretdato"] == "2026-08-25"
    assert d["fristdag"] == "2026-08-10"
    assert d["skifteret"] == "Skifteretten i Aarhus"
    assert d["sagsnummer"] == "SKS 41-1234/2026"
    assert d["skiftesamling"] == "2026-09-22"
    assert d["adresse"] == "Vestergade 12, 2. th"
    assert d["postnr"] == "8000"
    assert d["by"] == "Aarhus C"
    k = d["kurator"]
    assert k.navn == "Peter Hansen"
    assert k.firma == "Advokatfirmaet Nordlys"
    assert k.adresse == "Åboulevarden 1"
    assert k.postnr == "8000" and k.by == "Aarhus C"
    assert k.telefon == "86 12 34 56"
    assert k.email == "ph@nordlys-demo.dk"
    assert "advokatsamfundet" in k.advokatsamfundet_url


def test_parse_kurator_minimal():
    k = parse_kurator("advokat Mette Jensen, Bystrøm Advokater, Torvet 3, 5000 Odense C")
    assert k.navn == "Mette Jensen"
    assert k.firma == "Bystrøm Advokater"
    assert k.postnr == "5000"
    assert k.email is None


def test_parse_dekret_inline_name():
    text = ("Ved dekret afsagt den 1. september 2026 af Sø- og Handelsrettens skifteret er Kyst Invest A/S, "
            "CVR-nr. 87654321, Havnegade 3, 1058 København K, taget under konkursbehandling. Fristdag er den 20.08.2026. "
            "Kurator: advokat Lars Olsen, Lex Danica, Bredgade 9, 1260 København K.")
    d = parse_dekret_text(text)
    assert d["navn"] == "Kyst Invest A/S"
    assert d["selskabsform"] == "A/S"
    assert d["cvr"] == "87654321"
    assert d["dekretdato"] == "2026-09-01"
    assert d["fristdag"] == "2026-08-20"
    assert d["skifteret"].startswith("Sø- og Handelsrettens")
    assert d["kurator"].navn == "Lars Olsen"


def test_message_to_case_sets_deadline_and_links():
    msg = RawMessage(id="abc", url="https://www.statstidende.dk/messages/abc", kategori="Konkursboer", undertype="Dekret",
                     offentliggjort="2026-08-26", overskrift=None,
                     tekst=(FIX / "dekret_demo.txt").read_text(encoding="utf-8"))
    case = message_to_case(msg)
    assert case.id == "12345678"
    assert case.selskab.navn == "Fjord Ejendomme ApS"
    assert case.anmeldelsesfrist == "2026-09-23"  # 4 uger efter offentliggørelse
    assert case.links["cvr"].endswith("12345678")
    assert case.kurator.email == "ph@nordlys-demo.dk"
    assert case.kilder == ["statstidende"]


def test_normalize_message_tolerates_shapes():
    raw = {"messageId": "x1", "publicationDate": "2026-08-01T00:00:00", "messageCategory": "Konkursboer",
           "messageType": {"name": "Dekret"}, "body": "<p>Konkursdekret<br>CVR-nr. 11223344</p>",
           "fields": [{"name": "Kurator", "value": "advokat A B, Firma, Vej 1, 8000 Aarhus C"}]}
    m = normalize_message(raw, "https://www.statstidende.dk")
    assert m.id == "x1"
    assert m.offentliggjort == "2026-08-01"
    assert m.url.endswith("/messages/x1")
    assert "CVR-nr. 11223344" in m.tekst
    assert m.felter["Kurator"].startswith("advokat")
    case = message_to_case(m)
    assert case.kurator.navn == "A B"


def test_extract_list_shapes():
    assert _extract_list([{"a": 1}]) == [{"a": 1}]
    assert _extract_list({"items": [{"a": 1}]}) == [{"a": 1}]
    assert _extract_list({"hits": {"hits": [{"_source": {"a": 1}}]}}) == [{"a": 1}]
    assert _extract_list({"nope": 1}) == []


def test_tvangsauktion_parse():
    msg = RawMessage(id="auk1", url="https://www.statstidende.dk/messages/auk1", kategori="Tvangsauktioner",
                     undertype="Fast ejendom", offentliggjort="2026-08-20", overskrift=None,
                     tekst=("Tvangsauktion over ejendommen matr. nr. 12 a Aarhus Markjorder, beliggende Vestergade 12, "
                            "8000 Aarhus C, tilhørende Fjord Ejendomme ApS, CVR-nr. 12345678. Ejendomsværdi: kr. 9.400.000. "
                            "Auktionen afholdes den 15.10.2026 kl. 9.00. Ejerlejlighed nr. 4."))
    p = parse_tvangsauktion(msg)
    assert p.adresse == "Vestergade 12" and p.postnr == "8000" and p.by == "Aarhus C"
    assert p.matrikel == "12 a Aarhus Markjorder"
    assert p.offentlig_vurdering == 9_400_000
    assert p.tvangsauktion_dato == "2026-10-15"
    assert p.ejendomstype == "Ejerlejlighed"
    assert auction_debtor_keys(msg) == ("12345678", "Fjord Ejendomme ApS")


def test_date_today_is_iso():
    assert date.today().isoformat().count("-") == 2


def test_web_message_real_format():
    """Format som statstidende.dk's /api/message/{nr} leverer det (verificeret 4. sep. 2026, anonymiseret)."""
    body = json.loads((FIX / "web_message_dekret.json").read_text(encoding="utf-8"))
    raw = web_message_to_raw(body, "https://www.statstidende.dk")
    assert raw.id == "S02092026-87"
    assert raw.offentliggjort == "2026-09-04"
    assert raw.felter["cvr-nr"] == "12345678"
    assert raw.felter["kurator/#1"] == "Advokat Boris K. Frederiksen"
    case = message_to_case(raw)
    assert case.selskab.cvr == "12345678"
    assert case.selskab.navn == "Eksempel Ejendomme A/S"
    assert case.selskab.selskabsform == "A/S"
    assert case.selskab.adresse == "Trindsøvej 6, 1"
    assert (case.selskab.postnr, case.selskab.by, case.selskab.region) == ("8000", "Århus C", "Midtjylland")
    assert case.dekretdato == "2026-09-02"
    assert case.fristdag == "2026-08-24"
    assert case.anmeldelsesfrist == "2026-10-02"
    assert case.skifteret.navn == "Retten i Aarhus"
    assert case.skifteret.sagsnummer == "SKS 41-20428/2026"
    assert case.kurator.navn == "Boris K. Frederiksen"
    assert case.kurator.adresse == "Kalvebod Brygge 32"
    assert (case.kurator.postnr, case.kurator.by) == ("1560", "København V")
    assert any("tvangsopløsning" in n for n in case.noter)
    assert case.statstidende_url.endswith("/messages/S02092026-87")


def test_tvangsauktion_from_search_summary():
    msg = RawMessage(id="S31082026-202", url="https://www.statstidende.dk/messages/S31082026-202", kategori="Tvangsauktioner",
                     undertype="Fast ejendom", offentliggjort="2026-09-04", overskrift="2. auktion - Søbrovej 40, 5683 Haarby",
                     tekst="Rekvirent: Realkredit Danmark. Ejer: Demo Ejendomme ApS, CVR-nr. 12345678.",
                     felter={"summary/dato": "29.09.2026", "summary/ejendomsværdi": "461.000", "summary/grundværdi": "108.000",
                             "summary/retskreds": "Retten i Odense"})
    p = parse_tvangsauktion(msg)
    assert (p.adresse, p.postnr, p.by) == ("Søbrovej 40", "5683", "Haarby")
    assert p.tvangsauktion_dato == "2026-09-29"
    assert p.offentlig_vurdering == 461_000
    assert auction_debtor_keys(msg) == ("12345678", "Demo Ejendomme ApS")
