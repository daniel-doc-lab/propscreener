# Bidrag

1. Fork og opret en branch fra `main`.
2. `pip install -e ".[dev]"` og kør `pytest -q` + `ruff check .` før du committer.
3. Nye parsere skal have en fixture i `tests/fixtures/` (anonymiseret – ingen rigtige CVR-numre
   eller personnavne) og en test.
4. Ændringer i scoring skal opdatere `docs/PROPERTY_DETECTION.md` og `tests/test_detect.py`.
5. Kald aldrig eksterne kilder i tests – brug `FakeHttp`.
6. Hold kildernes vilkår: rimelig frekvens, beskrivende User-Agent, ingen CPR-data.

Fejl og idéer: opret et issue med kørselslog (`propscreener -v run …`) og gerne det rå
meddelelses-JSON der fejlede (anonymiseret).
