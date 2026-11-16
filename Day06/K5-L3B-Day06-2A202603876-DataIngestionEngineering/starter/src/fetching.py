"""Bounded typed snapshots; persistent worker sessions and per-origin pacing."""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import random
import threading
import time
from urllib.parse import parse_qsl, urlsplit

from .runtime import RuntimeConfig, atomic_json, atomic_write


CONTENT_EXTENSIONS = {'text/html': 'html', 'application/json': 'json',
                      'application/pdf': 'pdf', 'text/plain': 'txt'}
WORLD_BANK_QUERY_KEYS = {'format', 'qterm', 'rows', 'os', 'fl', 'sort', 'order', 'guid'}


def validate_source_url(url: str, content_type: str) -> None:
    """Only the documented public World Bank search API accepts query strings."""
    parts = urlsplit(url)
    if (parts.scheme != 'https' or not parts.hostname or parts.username is not None or parts.password is not None
        or parts.fragment or parts.port not in (None, 443)):
        raise ValueError('Source URLs must be public HTTPS URLs without credentials or fragments')
    if parts.query:
        if (content_type != 'application/json' or parts.hostname != 'search.worldbank.org'
            or parts.path not in {'/api/v2/wds', '/api/v3/wds'}):
            raise ValueError('Query strings are allowed only for the explicit public World Bank JSON API')
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        values = dict(pairs)
        if (len(values) != len(pairs) or set(values) - WORLD_BANK_QUERY_KEYS
            or values.get('format') != 'json'
            or any(not value or len(value) > 1000 for value in values.values())):
            raise ValueError('World Bank API query has unsupported, duplicate, empty or oversized parameters')
        for name, maximum in (('rows', 1000), ('os', 1000000)):
            if name in values and (not values[name].isascii() or not values[name].isdigit()
                                   or not 0 <= int(values[name]) <= maximum
                                   or (name == 'rows' and int(values[name]) == 0)):
                raise ValueError(f'World Bank API {name} is outside the bounded discovery budget')


def validate_snapshot_body(data, content_type: str) -> None:
    """Reject invalid typed bodies before publishing their cache checkpoint."""
    if not data:
        raise ValueError('Empty source response')
    if content_type == 'application/pdf':
        if not data.startswith(b'%PDF-'):
            raise ValueError('Response does not have a PDF signature')
    elif content_type == 'application/json':
        def invalid_constant(value):
            raise ValueError(f'Invalid JSON constant: {value}')
        value = json.loads(data, parse_constant=invalid_constant)
        if not isinstance(value, (dict, list)):
            raise ValueError('Expected a JSON object or array')
    elif content_type == 'text/plain':
        if '\x00' in data.decode('utf-8-sig'):
            raise ValueError('Text response contains NUL bytes')


class OriginPacer:
    def __init__(self, rate: float, clock=time.monotonic, sleep=time.sleep):
        self.interval = 1.0 / rate
        self.clock, self.sleep = clock, sleep
        self.next = {}
        self.lock = threading.Lock()

    def wait(self, origin):
        # Recheck after sleep: a concurrent 429 may extend the shared cooldown.
        while True:
            with self.lock:
                now = self.clock()
                delay = self.next.get(origin, 0) - now
                if delay <= 0:
                    self.next[origin] = now + self.interval
                    return
            self.sleep(delay)

    def cooldown(self, origin, seconds):
        with self.lock:
            self.next[origin] = max(self.next.get(origin, 0), self.clock() + seconds)


def retry_delay(value, attempt):
    if value:
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                seconds = 0
        if seconds > 60:
            raise RuntimeError('Retry-After exceeds 60-second retry budget; retry this source later')
        if seconds > 0:
            return seconds
    return min(30, 2 ** attempt + random.uniform(0, 0.5))


def bounded_map(function, items, workers, max_inflight):
    """Ordered output and at most max_inflight outstanding results, even if consumer is slow."""
    iterator = iter(items)
    pending = deque()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='http-fetch') as pool:
        try:
            for _ in range(max_inflight):
                item = next(iterator, None)
                if item is None:
                    break
                pending.append(pool.submit(function, item))
            while pending:
                yield pending.popleft().result()
                item = next(iterator, None)
                if item is not None:
                    pending.append(pool.submit(function, item))
        finally:
            for future in pending:
                future.cancel()


class SnapshotFetcher:
    def __init__(self, cache: Path, runtime: RuntimeConfig, session_factory=None):
        if session_factory is None:
            from requests import Session
            session_factory = Session
        self.factory, self.cache, self.runtime = session_factory, cache, runtime
        self.local = threading.local()
        self.sessions = []
        self.lock = threading.Lock()
        self.pacer = OriginPacer(runtime.requests_per_second)

    def _session(self):
        if not hasattr(self.local, 'session'):
            self.local.session = self.factory()
            self.local.session.headers.update({'User-Agent': 'Day06-ingestion-lab/1.0', 'Accept': 'text/html'})
            with self.lock:
                self.sessions.append(self.local.session)
        return self.local.session

    def fetch(self, url: str, refresh=False, content_type='text/html') -> dict:
        if content_type not in CONTENT_EXTENSIONS:
            raise ValueError('Unsupported explicit source content type')
        validate_source_url(url, content_type)
        parts = urlsplit(url)
        key = hashlib.sha256(json.dumps(['typed-snapshot-v1', content_type, url],
                                        separators=(',', ':')).encode()).hexdigest()
        extension = CONTENT_EXTENSIONS[content_type]
        index = self.cache / f'{key}.json'
        cached = None
        if index.exists():
            try:
                if index.stat().st_size > 65536:
                    raise ValueError('Snapshot checkpoint exceeds metadata budget')
                cached = json.loads(index.read_text())
                if not isinstance(cached, dict):
                    raise ValueError('Invalid snapshot checkpoint')
                digest = cached['sha256']
                if (not isinstance(digest, str) or len(digest) != 64
                    or any(c not in '0123456789abcdef' for c in digest)
                    or type(cached.get('bytes')) is not int
                    or any(cached.get(key) is not None and not isinstance(cached[key], str)
                           for key in ('etag', 'last_modified'))):
                    raise ValueError('Invalid snapshot digest')
                body = self.cache / f'{digest}.{extension}'
                if body.stat().st_size > self.runtime.max_response_bytes:
                    raise ValueError('Cached body exceeds budget')
                self.runtime.guard('http-cache')
                data = body.read_bytes()
                if (hashlib.sha256(data).hexdigest() != digest or cached['url'] != url
                    or cached['content_type'] != content_type or cached['bytes'] != len(data)):
                    raise ValueError('Snapshot checksum mismatch')
                validate_snapshot_body(data, content_type)
                del data
            except (OSError, ValueError, KeyError):
                cached = None
        if cached and not refresh:
            return {**cached, 'cache_hit': True, 'body_path': str(body)}
        headers = {}
        if cached:
            if cached.get('etag'):
                headers['If-None-Match'] = cached['etag']
            if cached.get('last_modified'):
                headers['If-Modified-Since'] = cached['last_modified']
        origin = f'{parts.hostname}:443'
        from requests import RequestException
        for attempt in range(3):
            self.runtime.guard('fetch')
            self.pacer.wait(origin)
            try:
                session = self._session()
                session.headers['Accept'] = content_type
                with session.get(url, headers=headers, stream=True, timeout=(5, 30), allow_redirects=False) as response:
                    status = response.status_code
                    if status == 304 and cached:
                        return {**cached, 'cache_hit': True, 'body_path': str(body), 'revalidated': True}
                    if status == 429 or 500 <= status <= 599:
                        if attempt == 2:
                            raise RuntimeError(f'HTTP {status}: retry budget exhausted for {url}')
                        self.pacer.cooldown(origin, retry_delay(response.headers.get('Retry-After'), attempt))
                        continue
                    if status != 200:
                        raise RuntimeError(f'HTTP {status} for {url}; not retried')
                    actual_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
                    if actual_type != content_type:
                        raise ValueError(f'Expected {content_type}, received {actual_type or "missing Content-Type"}')
                    data = bytearray()
                    deadline = time.monotonic() + 60
                    for block in response.iter_content(chunk_size=65536):
                        if time.monotonic() > deadline:
                            raise RuntimeError(f'Source stream exceeded 60-second processing deadline: {url}')
                        if len(data) + len(block) > self.runtime.max_response_bytes:
                            raise ValueError(f'Decoded source exceeds response budget: {url}')
                        data.extend(block)
                    validate_snapshot_body(data, content_type)
                    digest = hashlib.sha256(data).hexdigest()
                    body = self.cache / f'{digest}.{extension}'
                    atomic_write(body, data)
                    snapshot = {'url': url, 'content_type': content_type, 'sha256': digest, 'bytes': len(data),
                                'fetched_at': datetime.now(timezone.utc).isoformat(),
                                'etag': response.headers.get('ETag'),
                                'last_modified': response.headers.get('Last-Modified'), 'attempts': attempt + 1}
                    atomic_json(index, snapshot)
                    return {**snapshot, 'cache_hit': False, 'body_path': str(body)}
            except RequestException as exc:
                if attempt == 2:
                    raise RuntimeError(f'Network retry budget exhausted for {url}') from exc
                self.pacer.cooldown(origin, retry_delay(None, attempt))
        raise RuntimeError(f'Fetch failed: {url}')

    def close(self):
        for session in self.sessions:
            session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
