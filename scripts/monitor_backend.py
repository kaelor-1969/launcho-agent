"""Probe backend health and create verified session backups without logging data."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.session_store import SessionStore


def probe(url):
    for endpoint in ('live', 'ready'):
        with urlopen(f'{url.rstrip("/")}/health/{endpoint}', timeout=5) as response:
            result = json.load(response)
        expected = 'ok' if endpoint == 'live' else 'ready'
        if result.get('status') != expected:
            raise RuntimeError('Unexpected health response.')


def backup_and_verify(database, directory):
    if not database.is_file():
        raise FileNotFoundError('Session database is missing.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = directory / f'sessions-{stamp}.sqlite3'
    SessionStore(database).backup(destination)
    # Exercise a restored copy and check relational integrity as well as pages.
    with tempfile.TemporaryDirectory(prefix='launcho-restore-') as temp:
        restored = Path(temp) / 'restored.sqlite3'
        shutil.copyfile(destination, restored)
        with closing(sqlite3.connect(restored)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Restored database integrity failed.')
            if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise RuntimeError('Restored database references failed.')
            db.execute('SELECT id FROM sessions LIMIT 1').fetchone()
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--backup-interval', type=int, default=86400)
    parser.add_argument('--min-free-mb', type=int, default=256)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if min(args.interval, args.backup_interval, args.min_free_mb) <= 0:
        parser.error('Intervals and minimum free space must be positive.')
    args.backup_dir.mkdir(parents=True, exist_ok=True)
    next_backup = 0
    while True:
        healthy = True
        events = []
        try:
            probe(args.url)
            events.append('health_ok')
        except Exception:
            healthy = False
            events.append('health_failed')
        try:
            if shutil.disk_usage(args.db.resolve().parent).free < args.min_free_mb * 1024**2:
                raise RuntimeError('Low disk space.')
            events.append('disk_ok')
        except Exception:
            healthy = False
            events.append('disk_failed')
        if time.monotonic() >= next_backup:
            try:
                backup_and_verify(args.db, args.backup_dir)
                next_backup = time.monotonic() + args.backup_interval
                events.append('backup_restore_ok')
            except Exception:
                healthy = False
                events.append('backup_restore_failed')
        print(json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                          'healthy': healthy, 'events': events}), flush=True)
        if args.once:
            return 0 if healthy else 1
        time.sleep(args.interval)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
