from pathlib import Path

from propscreener.http import Http


class _Resp:
    def __init__(self, body):
        self._body, self.status_code, self.text = body, 200, "x"

    def json(self):
        return self._body


def test_cache_if_skips_error_bodies(tmp_path: Path, monkeypatch):
    h = Http("ua", tmp_path, delay_s=0)
    answers = iter([{"error": "QUOTA_EXCEEDED"}, {"vat": 1}])
    monkeypatch.setattr(h.session, "request", lambda *a, **k: _Resp(next(answers)))
    ok = lambda b: not b.get("error")  # noqa: E731
    assert h.get_json("https://x/api", params={"vat": 1}, cache_if=ok)["error"] == "QUOTA_EXCEEDED"
    assert h.get_json("https://x/api", params={"vat": 1}, cache_if=ok) == {"vat": 1}   # ikke serveret fra cache
    assert h.get_json("https://x/api", params={"vat": 1}, cache_if=ok) == {"vat": 1}   # nu fra cache
