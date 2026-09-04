from propscreener.detect import score_case
from propscreener.models import BankruptcyCase, Company, Financials, Property


def _case(**kw) -> BankruptcyCase:
    c = BankruptcyCase(id="x")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_ejf_match_gives_high_confidence():
    c = _case(selskab=Company(navn="Noget Trading ApS", branchekode="461900"),
              ejendomme=[Property(bfe_nummer="1", kilde="ejerfortegnelsen")])
    score_case(c)
    assert c.score >= 60
    assert c.konfidens == "høj"
    assert any(s.kode == "ejf_match" for s in c.signaler)


def test_industry_and_name_only_is_medium_or_low():
    c = _case(selskab=Company(navn="Fjord Ejendomme ApS", branchekode="682040"))
    score_case(c)
    assert {s.kode for s in c.signaler} == {"branche_ejendom", "navn_ejendom"}
    assert c.score == 45
    assert c.konfidens == "middel"
    assert c.ejendomstype_hoved == "Erhverv"


def test_xbrl_investment_property_strong():
    c = _case(selskab=Company(navn="Alfa Holding ApS", branchekode="642020"),
              regnskab=Financials(investeringsejendomme=10_000_000, realkreditgaeld=7_000_000, aktiver=11_000_000))
    score_case(c)
    codes = {s.kode for s in c.signaler}
    assert "xbrl_investeringsejendomme" in codes and "xbrl_realkredit" in codes and "navn_invest" in codes
    assert c.score == 75
    assert c.konfidens == "høj"


def test_unrelated_company_scores_low():
    c = _case(selskab=Company(navn="Byens Pizzaria ApS", branchekode="561010"),
              regnskab=Financials(aktiver=500_000, materielle_anlaeg=100_000))
    score_case(c)
    assert c.score == 0
    assert c.konfidens == "lav"
    assert c.ejendomstype_hoved == "Ukendt"


def test_address_style_name_and_ks_form():
    c = _case(selskab=Company(navn="Søndergade 14 K/S", selskabsform="K/S", branchekode="682030"))
    score_case(c)
    codes = {s.kode for s in c.signaler}
    assert "navn_adresse" in codes and "form_ks" in codes
    assert c.ejendomstype_hoved == "Bolig"


def test_score_capped_at_100():
    c = _case(selskab=Company(navn="Kyst Ejendomme K/S", selskabsform="K/S", branchekode="682010",
                              formaal="at eje fast ejendom"),
              regnskab=Financials(investeringsejendomme=1, grunde_og_bygninger=1, realkreditgaeld=1),
              ejendomme=[Property(kilde="ejerfortegnelsen"), Property(kilde="tvangsauktion")])
    score_case(c)
    assert c.score == 100
