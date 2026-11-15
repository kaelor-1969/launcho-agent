"""Verified online SQLite backup with redacted failure reporting."""
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import urllib.request


def utc_now():
    return datetime.now(timezone.utc)


def check(connection, foreign=False):
    if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise RuntimeError()
    if foreign and connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise RuntimeError()


def alert(payload):
    url = os.environ.get('ALERT_WEBHOOK_URL')
    if not url:
        return
    try:
        request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=5):
            pass
    except Exception as error:
        print(json.dumps({'status': 'alert_failed', 'timestamp': payload['timestamp'],
                          'error': type(error).__name__}), file=sys.stderr)


def main(source='/app/data/sessions.sqlite3', directory='/app/data/daily-backups'):
    phase = 'prepare'
    pending = None
    timestamp = utc_now()
    previous_umask = os.umask(0o077)
    try:
        directory = Path(directory)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with ExitStack() as stack:
            phase = 'open'
            origin = sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
            stack.callback(origin.close)
            with tempfile.NamedTemporaryFile(dir=directory, prefix='.pending-', delete=False) as temporary:
                pending = Path(temporary.name)
            target = sqlite3.connect(pending)
            stack.callback(target.close)
            phase = 'backup'
            origin.backup(target)
            phase = 'integrity_check'
            check(target)
            phase = 'foreign_key_check'
            if target.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise RuntimeError()
            phase = 'restore'
            restored = sqlite3.connect(':memory:')
            stack.callback(restored.close)
            target.backup(restored)
            phase = 'restore_check'
            check(restored, foreign=True)
        phase = 'replace'
        os.replace(pending, directory / ('day-' + str(timestamp.weekday()) + '.sqlite3'))
        pending = None
        print(json.dumps({'status': 'ok', 'timestamp': timestamp.isoformat()}))
        return 0
    except Exception as error:
        payload = {'status': 'failed', 'phase': phase, 'timestamp': timestamp.isoformat()}
        print(json.dumps(dict(payload, error=type(error).__name__)), file=sys.stderr)
        alert(payload)
        return 1
    finally:
        if pending is not None:
            try:
                pending.unlink(missing_ok=True)
            except OSError:
                pass
        os.umask(previous_umask)


if __name__ == '__main__':
    sys.exit(main())
