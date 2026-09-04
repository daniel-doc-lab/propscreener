"""Kommandolinje: `propscreener run | demo | build-site | probe | show`."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import Settings
from .export import build_dataset, build_site, load_cases, write_csv, write_json
from .http import Http


def _common_out(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", default="data", help="Output-mappe (default: data)")
    p.add_argument("--site", default="site/index.html", help="Sti til genereret dashboard")
    p.add_argument("--no-site", action="store_true", help="Byg ikke dashboard")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="propscreener",
                                 description="Screener for danske konkursboer med fast ejendom")
    ap.add_argument("--version", action="version", version=f"propscreener {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Hent konkursdekreter, berig og score (kræver netværk)")
    p_run.add_argument("--days", type=int, help="Antal dage tilbage (default fra env, 90)")
    p_run.add_argument("--min-score", type=int, help="Mindste score for at komme med (default 40)")
    p_run.add_argument("--all", action="store_true", help="Medtag alle boer uanset score (min-score=0)")
    _common_out(p_run)

    p_demo = sub.add_parser("demo", help="Generér fiktivt demodatasæt (offline)")
    p_demo.add_argument("-n", type=int, default=60)
    p_demo.add_argument("--seed", type=int, default=2026)
    p_demo.add_argument("--min-score", type=int, default=0)
    _common_out(p_demo)

    p_site = sub.add_parser("build-site", help="Byg dashboard fra eksisterende data/cases.json")
    p_site.add_argument("--data", default="data/cases.json")
    p_site.add_argument("--site", default="site/index.html")

    sub.add_parser("probe", help="Afprøv Statstidende-endpoints og kildernes tilgængelighed")
    p_dbg = sub.add_parser("debug-search", help="Dump rå JSON fra Statstidende-søgning og første meddelelse")
    p_dbg.add_argument("--type", default="konkurs_dekret")
    p_dbg.add_argument("--days", type=int, default=3)

    p_show = sub.add_parser("show", help="Vis et bo fra data/cases.json")
    p_show.add_argument("cvr")
    p_show.add_argument("--data", default="data/cases.json")

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()

    if a.cmd == "run":
        from .pipeline import Pipeline
        pipe = Pipeline(settings)
        min_score = 0 if a.all else a.min_score
        cases, stats = pipe.run(days_back=a.days, min_score=min_score)
        return _write(cases, stats, a, demo=False)

    if a.cmd == "demo":
        from .demo import generate
        cases, stats = generate(n=a.n, seed=a.seed)
        cases = [c for c in cases if c.score >= a.min_score]
        stats.min_score = a.min_score
        cases.sort(key=lambda c: (-c.score, c.dekretdato or ""))
        return _write(cases, stats, a, demo=True)

    if a.cmd == "build-site":
        cases, meta = load_cases(Path(a.data))
        dataset = {"meta": meta, "cases": [c.to_dict() for c in cases]}
        out = build_site(dataset, Path(a.site))
        print(f"dashboard: {out}")
        return 0

    if a.cmd == "probe":
        from .sources.statstidende import StatstidendeClient
        http = Http(settings.user_agent, None, settings.request_delay_s, settings.timeout_s)
        st = StatstidendeClient(settings, http)
        print("Statstidende (web):")
        for method, url, status in st.probe():
            print(f"  {method:4s} {url:60s} {status}")
        for name, url in (("regnskabsindeks", settings.regnskab_es_base), ("cvrapi", settings.cvrapi_base),
                          ("dawa", settings.dawa_base + "/adresser?q=Vestergade%201&per_side=1")):
            try:
                http.request("GET", url, cache_ttl_s=None, as_json=False)
                print(f"  {name:16s} OK")
            except Exception as e:  # noqa: BLE001
                print(f"  {name:16s} {e}")
        print(f"Datafordeler-login: {'sat' if settings.has_datafordeler else 'mangler (Ejerfortegnelsen springes over)'}")
        print(f"CVR system-til-system: {'sat' if settings.has_cvr_es else 'mangler (bruger cvrapi.dk)'}")
        return 0

    if a.cmd == "debug-search":
        import json

        from .sources.statstidende import StatstidendeClient, message_to_case, web_message_to_raw
        http = Http(settings.user_agent, None, settings.request_delay_s, settings.timeout_s)
        st = StatstidendeClient(settings, http)
        dump = st.debug_dump(a.type, a.days)
        print("=== SEARCH (4000 tegn) ===")
        print(json.dumps(dump["search"], ensure_ascii=False)[:4000])
        print("=== FIRST MESSAGE (6000 tegn) ===")
        print(json.dumps(dump["first_message"], ensure_ascii=False)[:6000])
        if isinstance(dump["first_message"], dict):
            raw = web_message_to_raw(dump["first_message"], settings.statstidende_web_base)
            print("=== FELTER ===")
            print(json.dumps(raw.felter, ensure_ascii=False, indent=1)[:4000])
            print("=== TEKST ===")
            print(raw.tekst[:3000])
            print("=== CASE ===")
            c = message_to_case(raw)
            d = c.to_dict()
            d.pop("raa_tekst", None)
            print(json.dumps(d, ensure_ascii=False, indent=1)[:5000])
        return 0

    if a.cmd == "show":
        cases, _ = load_cases(Path(a.data))
        for c in cases:
            if c.selskab.cvr == a.cvr or c.id == a.cvr:
                import json
                print(json.dumps(c.to_dict(), ensure_ascii=False, indent=2))
                return 0
        print("ikke fundet", file=sys.stderr)
        return 1
    return 2


def _write(cases, stats, a, demo: bool) -> int:
    out = Path(a.out)
    dataset = build_dataset(cases, stats, demo=demo)
    write_json(dataset, out / "cases.json")
    write_csv(cases, out / "cases.csv")
    print(f"{len(cases)} boer skrevet til {out}/cases.json og cases.csv")
    if not a.no_site:
        site = build_site(dataset, Path(a.site))
        print(f"dashboard: {site}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
