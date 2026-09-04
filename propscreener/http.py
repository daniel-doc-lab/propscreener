"""HTTP-klient med disk-cache, rate-limit og retry.

Alle kilder går gennem denne klasse så vi kan
  * være høflige (delay mellem kald, tydelig User-Agent)
  * køre pipelinen igen uden at ramme kilderne (cache)
  * teste offline via `FakeHttp` (samme interface).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")
        self.status = status
        self.url = url


class Http:
    def __init__(
        self,
        user_agent: str,
        cache_dir: Path | None = None,
        delay_s: float = 0.5,
        timeout_s: float = 30.0,
        retries: int = 3,
        cert: tuple[str, str] | None = None,
    ):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.session.headers["Accept"] = "application/json, text/html;q=0.8, */*;q=0.5"
        if cert:
            self.session.cert = cert
        self.cache_dir = cache_dir
        self.delay_s = delay_s
        self.timeout_s = timeout_s
        self.retries = retries
        self._last_call = 0.0
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ cache
    def _cache_path(self, key: str) -> Path | None:
        if not self.cache_dir:
            return None
        h = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.cache_dir / f"{h}.json"

    def _cache_get(self, key: str, max_age_s: float | None) -> Any | None:
        p = self._cache_path(key)
        if not p or not p.exists():
            return None
        if max_age_s is not None and (time.time() - p.stat().st_mtime) > max_age_s:
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _cache_put(self, key: str, value: Any) -> None:
        p = self._cache_path(key)
        if p:
            p.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    # --------------------------------------------------------------- requests
    def _throttle(self) -> None:
        wait = self.delay_s - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        cache_ttl_s: float | None = 6 * 3600,
        as_json: bool = True,
        cache_if: Callable[[Any], bool] | None = None,
    ) -> Any:
        key = json.dumps([method, url, params, json_body, bool(auth)], sort_keys=True, default=str)
        cached = self._cache_get(key, cache_ttl_s) if cache_ttl_s else None
        if cached is not None:
            return cached["body"]

        last_exc: Exception | None = None
        for attempt in range(self.retries):
            self._throttle()
            try:
                r = self.session.request(
                    method, url, params=params, json=json_body, headers=headers, auth=auth,
                    timeout=self.timeout_s,
                )
                if r.status_code == 429 or r.status_code >= 500:
                    raise HttpError(r.status_code, url, r.text)
                if r.status_code >= 400:
                    raise HttpError(r.status_code, url, r.text)
                body: Any = r.json() if as_json else r.text
                if cache_ttl_s and (cache_if is None or cache_if(body)):
                    self._cache_put(key, {"body": body})
                return body
            except (requests.RequestException, HttpError) as exc:  # noqa: PERF203
                last_exc = exc
                status = getattr(exc, "status", None)
                if status and 400 <= status < 500 and status != 429:
                    raise
                sleep = 2 ** attempt
                log.warning("%s %s fejlede (%s) – forsøg %d/%d, venter %ss", method, url, exc, attempt + 1,
                            self.retries, sleep)
                time.sleep(sleep)
        assert last_exc is not None
        raise last_exc

    def get_json(self, url: str, **kw: Any) -> Any:
        return self.request("GET", url, **kw)

    def get_text(self, url: str, **kw: Any) -> str:
        return self.request("GET", url, as_json=False, **kw)

    def post_json(self, url: str, json_body: Any, **kw: Any) -> Any:
        return self.request("POST", url, json_body=json_body, **kw)


class FakeHttp:
    """Offline-erstatning til tests: svarer fra en dict {url_prefix: body}."""

    def __init__(self, responses: dict[str, Any]):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def _lookup(self, method: str, url: str, params: dict[str, Any] | None = None, json_body: Any = None) -> Any:
        import inspect
        if params:
            from urllib.parse import urlencode
            url = url + ("&" if "?" in url else "?") + urlencode(params)
        self.calls.append((method, url))
        for prefix, body in self.responses.items():
            if url.startswith(prefix):
                if callable(body):
                    n = len(inspect.signature(body).parameters)
                    return body(url, json_body) if n >= 2 else body(url)
                return body
        raise HttpError(404, url, "no fake response")

    def request(self, method: str, url: str, **kw: Any) -> Any:
        return self._lookup(method, url, kw.get("params"), kw.get("json_body"))

    def get_json(self, url: str, **kw: Any) -> Any:
        return self._lookup("GET", url, kw.get("params"))

    def get_text(self, url: str, **kw: Any) -> str:
        return self._lookup("GET", url, kw.get("params"))

    def post_json(self, url: str, json_body: Any, **kw: Any) -> Any:
        return self._lookup("POST", url, kw.get("params"), json_body)
