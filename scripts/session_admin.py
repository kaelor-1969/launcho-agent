"""Offline restore and online backup/cleanup. Never print database contents."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.session_store import SessionStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore', 'cleanup', 'check'])
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--file', type=Path)
    args = parser.parse_args()
    if args.action == 'restore':
        if not args.file or not args.file.is_file() or args.db.exists():
            parser.error('Stop the service, choose a new database path and an existing --file backup.')
        with closing(sqlite3.connect(f'{args.file.resolve().as_uri()}?mode=ro', uri=True)) as source:
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed.')
            args.db.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(args.db)) as target:
                source.backup(target)
        print('Restore complete. Configure the new path before starting the service.')
        return
    if not args.db.is_file():
        parser.error('Database does not exist.')
    if args.action == 'check':
        with closing(sqlite3.connect(f'{args.db.resolve().as_uri()}?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database integrity check failed.')
        print('Integrity check passed.')
        return
    store = SessionStore(args.db)
    if args.action == 'backup':
        if not args.file:
            parser.error('--file is required.')
        store.backup(args.file)
        print('Backup integrity verified.')
    else:
        print(f'Expired sessions removed: {store.cleanup()}')


if __name__ == '__main__':
    main()
