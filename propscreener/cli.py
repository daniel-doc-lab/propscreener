"""Kommandolinje: `propscreener run | demo | build-site | probe | show`."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .config import Settings
from .export import build_dataset, build_site, load_cases, merge_with_existing, write_csv, write_json
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
    p_run.add_argument("--no-merge", action="store_true", help="Overskriv eksisterende data i stedet for at flette")
    p_run.add_argument("--retention", type=int, default=180, help="Behold boer fra tidligere kørsler i N dage (default 180)")
    _common_out(p_run)

    p_re = sub.add_parser("rescore", help="Kør scoring og klassificering igen på eksisterende data/cases.json")
    p_re.add_argument("--min-score", type=int, default=0)
    _common_out(p_re)

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

    p_idx = sub.add_parser("build-index", help="Byg lokale indekser fra Datafordelerens fildownload (EJF/VUR/EBR)")
    p_idx.add_argument("--index-dir", default=None)
    p_idx.add_argument("--work-dir", default=".cache/files")
    p_idx.add_argument("--only", default="", help="Kommasepareret: ejf,vur,ebr (default alle tilgængelige)")
    p_idx.add_argument("--vur-entity", default=r"^Ejendomsvurdering$", help="Regex for VUR-entitet")
    p_idx.add_argument("--ebr-entity", default=r"^Ejendomsbeliggenhed$")
    p_idx.add_argument("--ejf-entity", default=r"^Ejerskab$")
    p_idx.add_argument("--force-vur", action="store_true",
                       help="Byg VUR-indeks selv uden EJF-indeks (2+ GB download, kun til fejlsøgning)")
    p_pf = sub.add_parser("probe-files", help="Vis hvilke entiteter Datafordeleren udstiller til fildownload (EJF/VUR/EBR/BBR/MAT)")
    p_pf.add_argument("--headers", nargs="*", default=[], metavar="REGISTER:ENTITET",
                      help="Hent mindste fil (delta) for entiteten og vis kolonnenavne, fx VUR:^Ejendomsvurdering$")
    p_pf.add_argument("--work-dir", default=".cache/files")

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
        if not a.no_merge:
            cases, kept = merge_with_existing(cases, Path(a.out) / "cases.json", a.retention, min_score)
            stats.bevaret_fra_tidligere = kept
        return _write(cases, stats, a, demo=False)

    if a.cmd == "rescore":
        from .detect import score_case
        from .pipeline import RunStats, add_investor_links
        cases, meta = load_cases(Path(a.out) / "cases.json")
        for c in cases:
            score_case(c)
            add_investor_links(c)
        cases = [c for c in cases if c.score >= a.min_score]
        cases.sort(key=lambda c: (-c.score, c.dekretdato or ""))
        stats = meta.get("stats") or RunStats()
        return _write(cases, stats, a, demo=bool(meta.get("demo")))

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

    if a.cmd == "probe-files":
        import json as _json

        from .sources.datafordeler_files import DatafordelerFiles
        http = Http(settings.user_agent, None, settings.request_delay_s, 120)
        df = DatafordelerFiles(settings, http)
        for reg in ("EJF", "VUR", "EBR", "BBR", "MAT"):
            try:
                print(f"== {reg} ==")
                print(_json.dumps(df.entities(reg), ensure_ascii=False, indent=1))
            except Exception as e:  # noqa: BLE001
                print(f"  fejl: {e}")
        for spec in a.headers:
            reg, _, pat = spec.partition(":")
            print(f"== kolonner {reg} {pat} ==")
            try:
                print(_json.dumps(df.peek_headers(reg.upper(), pat or ".", Path(a.work_dir)), ensure_ascii=False, indent=1))
            except Exception as e:  # noqa: BLE001
                print(f"  fejl: {e}")
        return 0

    if a.cmd == "build-index":
        from .sources.datafordeler_files import (
            DatafordelerFiles,
            build_bfe_xref,
            build_ebr_index,
            build_ejf_index,
            build_vur_index,
            save_index,
        )
        http = Http(settings.user_agent, None, settings.request_delay_s, 120)
        df = DatafordelerFiles(settings, http)
        index_dir = Path(a.index_dir) if a.index_dir else settings.index_dir
        work = Path(a.work_dir)
        only = {x.strip() for x in a.only.split(",") if x.strip()} or {"ejf", "vur", "ebr"}
        meta: dict = {"bygget": datetime.now(UTC).isoformat(timespec="seconds"), "filer": {}}
        wanted: set[int] | None = None
        if "ejf" in only:
            info = df.latest_total("EJF", a.ejf_entity, "csv")
            if info is None:
                print("EJF: ingen tilgængelige fildownloads (mangler godkendt anmodning/OAuth) – springer over")
            else:
                zp = df.download(info, work / info.file_name)
                idx = build_ejf_index(df.iter_csv_rows(zp))
                save_index({"cvr": idx}, index_dir / "ejf_cvr_bfe.json.gz")
                meta["filer"]["ejf"] = info.file_name
                wanted = {e["bfe"] for lst in idx.values() for e in lst}
                print(f"EJF: {len(idx)} virksomheder, {sum(len(v) for v in idx.values())} ejerskaber")
        for key, pat, builder, name in (("vur", a.vur_entity, build_vur_index, "vur_bfe.json.gz"),
                                        ("ebr", a.ebr_entity, build_ebr_index, "ebr_bfe.json.gz")):
            if key not in only:
                continue
            if key == "vur" and wanted is None and not a.force_vur:
                print("VUR: springes over – vurderinger giver først mening når EJF-indekset (CVR -> BFE) findes "
                      "(brug --force-vur for at tvinge; ~4 GB download)")
                continue
            info = df.latest_total(key.upper(), pat, "csv")
            if info is None:
                print(f"{key.upper()}: ingen total-download matcher '{pat}' – kør `propscreener probe-files`")
                continue
            zp = df.download(info, work / info.file_name)
            if key == "vur":
                xref: dict[str, int] = {}
                xinfo = df.latest_total("VUR", r"^BFEKrydsreference$", "csv")
                if xinfo is not None:
                    xref = build_bfe_xref(df.iter_csv_rows(df.download(xinfo, work / xinfo.file_name)))
                    print(f"VUR: {len(xref)} krydsreferencer vurderingsejendom -> BFE")
                idx = build_vur_index(df.iter_csv_rows(zp), wanted, xref)
            else:
                idx = builder(df.iter_csv_rows(zp), wanted)
            save_index({"bfe": idx}, index_dir / name)
            meta["filer"][key] = info.file_name
            print(f"{key.upper()}: {len(idx)} ejendomme indekseret fra {info.file_name}")
        save_index(meta, index_dir / "meta.json.gz")
        print(f"indekser skrevet til {index_dir}")
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
