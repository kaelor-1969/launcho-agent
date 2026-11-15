"""Exercise image rebuild and container replacement with an isolated volume."""
import subprocess
from uuid import uuid4


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True, text=True).stdout.strip()


def main():
    name = 'backup-redeploy-' + uuid4().hex[:12]
    image = name + ':rebuilt'
    try:
        docker('volume', 'create', name)
        docker('run', '--rm', '-v', name + ':/app/data', 'launcho-agent:ci',
               'python', '-c', 'import sqlite3; '
               'c=sqlite3.connect("/app/data/sessions.sqlite3"); '
               'c.execute("CREATE TABLE marker(value)"); '
               'c.execute("INSERT INTO marker VALUES (42)"); c.commit(); c.close()')
        docker('run', '--rm', '-v', name + ':/app/data', 'launcho-agent:ci',
               'python', '/app/scripts/daily_backup.py')
        snapshot = ('import hashlib,json; from pathlib import Path; '
                    'print(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() '
                    'for p in Path("/app/data/daily-backups").glob("day-*.sqlite3")},sort_keys=True))')
        before = docker('run', '--rm', '-v', name + ':/app/data', 'launcho-agent:ci', 'python', '-c', snapshot)
        assert before != '{}'
        docker('build', '-t', image, '.')
        after = docker('run', '--rm', '-v', name + ':/app/data', image, 'python', '-c', snapshot)
        assert before == after, 'Backup inventory changed after image rebuild'
        docker('run', '--rm', '-v', name + ':/app/data', image, 'python', '-c',
               'import os,sqlite3; from pathlib import Path; '
               'assert os.getuid()==10001; '
               'd=Path("/app/data/daily-backups"); '
               'p=d/"write-probe"; p.write_text("ok"); p.unlink(); '
               'c=sqlite3.connect(next(d.glob("day-*.sqlite3"))); '
               'assert c.execute("SELECT value FROM marker").fetchall()==[(42,)]; c.close()')
        print('PASS: rebuilt image preserves backup hashes and appuser write access; provider cron not tested')
    finally:
        subprocess.run(['docker', 'volume', 'rm', name], capture_output=True)
        subprocess.run(['docker', 'image', 'rm', image], capture_output=True)


if __name__ == '__main__':
    main()
