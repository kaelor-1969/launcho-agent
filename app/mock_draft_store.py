"""Persistent, single-host mock drafts. No official API or session-store dependencies."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from app.services.launcho_contract import normalize_draft
from app.services.catalog import selectable_catalog


class MockDraftError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(code)


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class MockDraftStore:
    def __init__(self, path, catalog, pricing, *, ttl=86400, retention=604800,
                 preview_origin='http://127.0.0.1:8001', clock=time.time):
        if type(ttl) is not int or type(retention) is not int or ttl <= 0 or retention < ttl:
            raise ValueError('Mock retention must be >= positive draft TTL.')
        self.origin = self.validate_origin(preview_origin)
        self.path = Path(path)
        self.catalog, self.pricing = catalog, pricing
        self.ttl, self.retention = ttl, retention
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS mock_drafts (
                key_hash TEXT PRIMARY KEY, ref TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL, result TEXT NOT NULL,
                created REAL NOT NULL, expires REAL NOT NULL, retain_until REAL NOT NULL
            )''')

    @staticmethod
    def validate_origin(preview_origin):
        origin = urlsplit(preview_origin)
        if (origin.scheme != 'http' or origin.hostname not in {'127.0.0.1', '::1'}
                or origin.username or origin.password or origin.query or origin.fragment
                or origin.path not in {'', '/'}):
            raise ValueError('Mock preview origin must be an HTTP loopback origin.')
        # Accessing port also rejects malformed port strings.
        if origin.port == 0:
            raise ValueError('Mock preview port must be nonzero.')
        return preview_origin.rstrip('/')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def validate_key(key):
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
            raise MockDraftError(422, 'invalid_idempotency_key', 'کلید تکرار درخواست معتبر نیست.')

    @staticmethod
    def validate_ref(ref):
        if not re.fullmatch(r'sd_[A-Za-z0-9_-]{4,128}', ref):
            raise MockDraftError(422, 'invalid_reference', 'شناسهٔ پیش‌نویس معتبر نیست.')

    def quote(self, payload):
        try:
            options = selectable_catalog(self.catalog[payload['kind']], payload['kind'], allow_test=True)
        except (ValueError, KeyError, TypeError):
            raise MockDraftError(503, 'catalog_unavailable', 'کاتالوگ معتبر فعلاً در دسترس نیست.') from None
        if options['availability'] == 'unavailable':
            raise MockDraftError(503, 'catalog_unavailable', 'گزینهٔ قابل ثبت معتبر فعلاً موجود نیست.')
        categories = {item['id'] for item in options['businessCategories']}
        templates = {item['id'] for item in options['templates'] if item.get('available') is True}
        plans = {item['months']: item for item in self.pricing['plans']}
        domains = {item['tld']: item for item in self.pricing['domains']}
        if (payload['category'] not in categories or payload['template'] not in templates
                or payload['planMonths'] not in plans):
            raise MockDraftError(422, 'invalid_option', 'صنف، قالب یا دوره در گزینه‌های آزمایشی موجود نیست.')
        template = next(item for item in options['templates'] if item['id'] == payload['template'])
        if template['compatibleCategoryIds'] is not None and payload['category'] not in template['compatibleCategoryIds']:
            raise MockDraftError(422, 'incompatible_template', 'قالب انتخاب‌شده با صنف سازگار نیست.')
        domain = payload['domain']
        if domain.get('ownDomain'):
            return None  # Existing-domain connection charges have no approved fixture amount.
        if domain['tld'] not in domains:
            raise MockDraftError(422, 'invalid_option', 'پسوند دامنه در گزینه‌های آزمایشی موجود نیست.')
        total = (self.pricing['setupFees'][payload['kind']] + plans[payload['planMonths']]['price']
                 + domains[domain['tld']]['annualFee'])
        return {'currency': 'toman', 'total': total, 'isFinal': False}

    def create(self, payload, key):
        self.validate_key(key)
        try:
            normalized = normalize_draft(payload)
        except (ValueError, TypeError, AttributeError):
            raise MockDraftError(422, 'invalid_request', 'اطلاعات پیش‌نویس معتبر نیست.') from None
        canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(key.encode('ascii')).hexdigest()
        with self.transaction() as db:
            now = self.clock()
            db.execute('DELETE FROM mock_drafts WHERE retain_until<=?', (now,))
            previous = db.execute('SELECT * FROM mock_drafts WHERE key_hash=?', (digest,)).fetchone()
            if previous:
                if previous['payload'] != canonical:
                    raise MockDraftError(409, 'idempotency_conflict', 'این کلید قبلاً برای اطلاعات دیگری استفاده شده است.')
                if now >= previous['expires']:
                    raise MockDraftError(410, 'draft_expired', 'پیش‌نویس آزمایشی منقضی شده است.')
                return json.loads(previous['result'])
            quote = self.quote(normalized)
            ref = 'sd_mock_' + secrets.token_urlsafe(24)
            result = {'ref': ref, 'status': 'draft', 'createdAt': stamp(now),
                      'expiresAt': stamp(now + self.ttl), 'retainUntil': stamp(now + self.retention),
                      'confirmUrl': self.origin + '/mock-drafts/' + ref, 'quote': quote}
            db.execute('INSERT INTO mock_drafts VALUES(?,?,?,?,?,?,?)',
                       (digest, ref, canonical, json.dumps(result, ensure_ascii=False),
                        now, now + self.ttl, now + self.retention))
            return result

    def get(self, ref):
        self.validate_ref(ref)
        with self.transaction() as db:
            now = self.clock()
            db.execute('DELETE FROM mock_drafts WHERE retain_until<=?', (now,))
            row = db.execute('SELECT result,expires FROM mock_drafts WHERE ref=?', (ref,)).fetchone()
            result = json.loads(row['result']) if row else None
            if row and now >= row['expires']:
                result['status'] = 'expired'
        if result is None:
            raise MockDraftError(404, 'draft_not_found', 'پیش‌نویس آزمایشی پیدا نشد.')
        return result

    def cleanup(self):
        with self.transaction() as db:
            return db.execute('DELETE FROM mock_drafts WHERE retain_until<=?', (self.clock(),)).rowcount
