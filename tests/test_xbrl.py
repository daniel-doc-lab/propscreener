from pathlib import Path

from propscreener.models import Financials
from propscreener.sources.regnskab import derive_ratios
from propscreener.xbrl import _parse_number, parse_xbrl

FIX = Path(__file__).parent / "fixtures"


def test_parse_classic_xbrl_picks_latest_instant_and_ignores_dimensions():
    facts = parse_xbrl((FIX / "aarsrapport_demo.xml").read_bytes())
    assert facts.entity_name == "Fjord Ejendomme ApS"
    assert facts.values["InvestmentProperty"] == 48_500_000
    assert facts.values["Assets"] == 51_200_000
    assert facts.values["Equity"] == 3_100_000
    assert facts.values["LongtermMortgageDebt"] == 41_000_000
    assert facts.values["ProfitLoss"] == -1_250_000     # dimensionel kontekst (-999) ignoreres
    assert facts.values["AverageNumberOfEmployees"] == 2
    assert facts.period_end == "2025-12-31"


def test_parse_inline_xbrl_with_scale_and_sign():
    facts = parse_xbrl((FIX / "aarsrapport_inline_demo.xhtml").read_text(encoding="utf-8"))
    assert facts.values["LandAndBuildings"] == 12_750_000
    assert facts.values["Assets"] == 14_100_000
    assert facts.values["Equity"] == -820_000
    assert facts.values["ProfitLoss"] == -2_310_000
    assert facts.period_end == "2025-06-30"


def test_parse_number_formats():
    assert _parse_number("1.234.567", None, None, None) == 1_234_567
    assert _parse_number("1.234,50", None, None, None) == 1234  # afrundet
    assert _parse_number("1,234,567", None, None, None) == 1_234_567
    assert _parse_number("12.750", "3", None, "ixt:numcommadecimal") == 12_750_000
    assert _parse_number("12,750.5", "3", None, "ixt:num-dot-decimal") == 12_750_500
    assert _parse_number("500", None, "-", None) == -500
    assert _parse_number("-", None, None, None) == 0
    assert _parse_number("abc", None, None, None) is None


def test_derive_ratios():
    f = derive_ratios(Financials(aktiver=50_000_000, egenkapital=5_000_000, investeringsejendomme=45_000_000,
                                 realkreditgaeld=36_000_000, langfristet_gaeld=38_000_000, kortfristet_gaeld=7_000_000))
    assert f.ejendomsvaerdi_bogfoert == 45_000_000
    assert f.ejendomsandel_pct == 90.0
    assert f.soliditet_pct == 10.0
    assert f.ltv_pct == 80.0
    assert f.samlet_gaeld == 45_000_000


def test_derive_ratios_fallback_debt():
    f = derive_ratios(Financials(aktiver=10, egenkapital=-4))
    assert f.samlet_gaeld == 14
    assert f.ejendomsvaerdi_bogfoert is None
