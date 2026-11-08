import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager


class CoreError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(code)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class SessionStore:
    def __init__(self, path, ttl=86400):
        self.path, self.ttl = str(path), ttl
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, expires REAL NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0, prefs TEXT NOT NULL,
                    history TEXT NOT NULL DEFAULT '[]', review_id TEXT, chat_until REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL, token_hash TEXT NOT NULL, expires REAL NOT NULL,
                    payload TEXT NOT NULL, idem TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
                    started REAL NOT NULL DEFAULT 0, result TEXT
                );
                CREATE INDEX IF NOT EXISTS review_owner ON reviews(session_id);
            ''')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            if db.in_transaction:
                db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def authenticate(self, db, session_id, token):
        row = db.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
        if not row or not token or not hmac.compare_digest(row['token_hash'], digest(token)):
            raise CoreError(404, 'session_not_found', 'جلسه معتبر پیدا نشد.')
        if row['expires'] <= time.time():
            raise CoreError(410, 'session_expired', 'جلسه منقضی شده؛ گفتگوی تازه شروع کنید.')
        return dict(row)

    def create(self):
        sid, token = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        expires = time.time() + self.ttl
        with self.transaction() as db:
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions(id,token_hash,expires,prefs) VALUES(?,?,?,?)',
                       (sid, digest(token), expires, json.dumps({'kind':'shop'})))
        return sid, token

    def get(self, sid, token):
        with self.transaction() as db:
            return self.authenticate(db, sid, token)

    def resume(self, ref, token):
        if not token:
            raise CoreError(404, 'session_not_found', 'جلسه معتبر پیدا نشد.')
        with self.transaction() as db:
            rows = db.execute("SELECT session_id,result FROM reviews WHERE status='completed'").fetchall()
            for row in rows:
                if json.loads(row['result'] or '{}').get('ref') == ref:
                    return self.authenticate(db, row['session_id'], token)
        raise CoreError(404, 'session_not_found', 'جلسه معتبر پیدا نشد.')
