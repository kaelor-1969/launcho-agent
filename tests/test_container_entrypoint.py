"""Verify permission setup and privilege dropping without changing host permissions."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class EntrypointTests(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location('volume_entrypoint',
            Path(__file__).resolve().parents[1] / 'scripts/container_entrypoint.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'pwd': SimpleNamespace(getpwnam=Mock(return_value=
                SimpleNamespace(pw_uid=10001, pw_gid=10001, pw_dir='/home/appuser')))}):
            spec.loader.exec_module(module)
        return module

    def test_root_prepares_volume_before_dropping_privileges_and_exec(self):
        module = self.load()
        directory = Mock()
        directory.is_symlink.return_value = False
        file = Mock()
        file.name = 'sessions.sqlite3'
        file.is_file.return_value = True
        file.is_symlink.return_value = False
        directory.iterdir.return_value = [file]
        events = Mock()
        with patch.object(module, 'Path', return_value=directory), \
                patch.object(module.os, 'geteuid', return_value=0, create=True), \
                patch.object(module.os, 'chown', events.chown, create=True), \
                patch.object(module.os, 'chmod', events.chmod), \
                patch.object(module.os, 'setgroups', events.setgroups, create=True), \
                patch.object(module.os, 'setgid', events.setgid, create=True), \
                patch.object(module.os, 'setuid', events.setuid, create=True), \
                patch.object(module.os, 'execvp', events.execvp), \
                patch.object(sys, 'argv', ['entrypoint', 'uvicorn', 'app.main:app']), \
                patch.dict(module.os.environ):
            module.main()
        self.assertEqual([call[0] for call in events.mock_calls],
                         ['chown', 'chmod', 'chown', 'chmod', 'setgroups', 'setgid', 'setuid', 'execvp'])
        events.chown.assert_any_call(directory, 10001, 10001)
        events.chmod.assert_any_call(directory, 0o700)
        events.setgroups.assert_called_once_with([])
        events.setgid.assert_called_once_with(10001)
        events.setuid.assert_called_once_with(10001)
        events.execvp.assert_called_once_with('uvicorn', ['uvicorn', 'app.main:app'])

    def test_existing_nonroot_execution_preserves_identity(self):
        module = self.load()
        with patch.object(module.os, 'geteuid', return_value=10001, create=True), \
                patch.object(module.os, 'execvp') as execute, \
                patch.object(module, 'Path') as directory, \
                patch.object(sys, 'argv', ['entrypoint', 'python', '--version']):
            module.main()
        directory.assert_not_called()
        execute.assert_called_once_with('python', ['python', '--version'])

    def test_symlink_volume_is_rejected_before_chown(self):
        module = self.load()
        directory = Mock()
        directory.is_symlink.return_value = True
        with patch.object(module, 'Path', return_value=directory), \
                patch.object(module.os, 'geteuid', return_value=0, create=True), \
                patch.object(module.os, 'chown', create=True) as chown:
            with self.assertRaises(RuntimeError):
                module.main()
        chown.assert_not_called()
