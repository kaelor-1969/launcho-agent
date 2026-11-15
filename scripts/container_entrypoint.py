"""Prepare the persistent volume, then execute the application as appuser."""
import os
from pathlib import Path
import pwd
import sys


def main():
    if os.geteuid() == 0:
        account = pwd.getpwnam('appuser')
        directory = Path('/app/data')
        if directory.is_symlink():
            raise RuntimeError('Data directory must not be a symbolic link.')
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, account.pw_uid, account.pw_gid)
        os.chmod(directory, 0o700)
        # Existing SQLite sidecars may have been created by an administrative restore.
        for file in directory.iterdir():
            if file.is_file() and not file.is_symlink() and file.name.startswith('sessions.sqlite3'):
                os.chown(file, account.pw_uid, account.pw_gid)
                os.chmod(file, 0o600)
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
        os.environ['HOME'] = account.pw_dir
    if not sys.argv[1:]:
        raise RuntimeError('Application command is required.')
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    main()
