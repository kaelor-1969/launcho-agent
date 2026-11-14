"""Deployment policy and bounded, process-local admission control."""
from collections import OrderedDict
import os
from threading import Lock
import time
from urllib.parse import urlsplit


class RuntimePolicy:
    def __init__(self):
        self.production = os.getenv('LAUNCHO_ENV', 'development') == 'production'
        self.origins = self.urls('LAUNCHO_CORS_ORIGINS')
        self.parents = self.urls('LAUNCHO_FRAME_ANCESTORS')
        self.limit = int(os.getenv('LAUNCHO_REQUESTS_PER_MINUTE', '120'))
        self.max_body = int(os.getenv('LAUNCHO_MAX_BODY_BYTES', '32768'))
        if not 1 <= self.limit <= 10000 or not 1024 <= self.max_body <= 1048576:
            raise RuntimeError('Invalid request limits.')
        if self.production:
            if not self.parents:
                raise RuntimeError('Production requires explicit frame ancestors.')
            if os.getenv('LAUNCHO_MOCK_URL', '').strip():
                raise RuntimeError('Local mock is forbidden in production.')
            path = os.getenv('LAUNCHO_SESSION_DB', '')
            if not path or not os.path.isabs(path):
                raise RuntimeError('Production requires an absolute persistent session database path.')
        self.buckets = OrderedDict()
        self.lock = Lock()

    @staticmethod
    def urls(name):
        values = [value.strip().rstrip('/') for value in os.getenv(name, '').split(',') if value.strip()]
        for value in values:
            url = urlsplit(value)
            if (url.scheme not in {'https', 'http'} or not url.hostname or url.username or url.password
                    or url.path or url.query or url.fragment):
                raise RuntimeError(f'{name} requires comma-separated origins without paths.')
        return values

    def admit(self, peer):
        now = time.monotonic()
        with self.lock:
            while self.buckets and next(iter(self.buckets.values()))[0] <= now - 60:
                self.buckets.popitem(last=False)
            start, count = self.buckets.get(peer, (now, 0))
            if count >= self.limit:
                return False
            if peer not in self.buckets and len(self.buckets) >= 10000:
                return False
            self.buckets[peer] = (start, count + 1)
            return True
