from propscreener.models import BankruptcyCase, Company, Kurator
from propscreener.relations import compute_relations, name_stem


def _case(id_, navn, adresse="", postnr="", kurator="", dekret="2026-08-01", ejere=(), score=0):
    return BankruptcyCase(id=id_, dekretdato=dekret, score=score, kurator=Kurator(navn=kurator or None),
                          selskab=Company(cvr=id_, navn=navn, adresse=adresse or None, postnr=postnr or None,
                                          ejere=list(ejere)))


def test_name_stem_skips_generic_words():
    assert name_stem("Kystparken Ejendomme ApS under konkurs") == "kystparken"
    assert name_stem("Dansk Holding A/S") is None
    assert name_stem("Ejendomsselskabet af 1. maj 2020 ApS") is None
    assert name_stem("Bakkehuset Invest K/S") == "bakkehuset"


def test_compute_relations_groups_by_address_stem_and_owner():
    a = _case("1", "Kystparken Holding ApS", "Havnegade 3", "8000", "Anders Advokat", score=60)
    b = _case("2", "Kystparken Ejendomme ApS", "Havnegade 3", "8000", "Anders Advokat", score=10)
    c = _case("3", "Bakkehuset Invest K/S", "Søvej 1", "9000", "Birthe Advokat", ejere=["Jens Jensen"], score=50)
    d = _case("4", "Grøn Energi ApS", "Enghavevej 9", "9000", "Carl Advokat", ejere=["Jens Jensen"], dekret="2026-09-01")
    e = _case("5", "Kystparken Byg ApS", "Andet Sted 1", "2100", "Ukendt", dekret="2026-05-01")  # kun stamme -> ingen
    n = compute_relations([a, b, c, d, e], min_score=40)
    assert n == 4
    rel_a = {r["id"]: r for r in a.relationer}
    assert set(rel_a) == {"2"}
    assert "samme hjemstedsadresse" in rel_a["2"]["grund"] and "samme kurator og dekret samme dage" in rel_a["2"]["grund"]
    assert any("navnestamme" in g for g in rel_a["2"]["grund"])
    assert rel_a["2"]["i_registret"] is False and rel_a["2"]["score"] == 10
    assert {r["id"] for r in c.relationer} == {"4"} and c.relationer[0]["grund"] == ["samme ejer/ledelse (Jens Jensen)"]
    assert d.relationer[0]["i_registret"] is True
    assert e.relationer == []
