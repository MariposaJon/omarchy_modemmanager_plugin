import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import secure_runtime as runtime
import launcher

spec = importlib.util.spec_from_file_location('recovery_installer', Path(__file__).parent / 'recovery/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RuntimeSecurity(unittest.TestCase):
    def test_shadow_path_and_python_environment_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            shadow = Path(tmp) / 'python3'
            shadow.write_text('#!/bin/sh\necho SHADOW\n')
            shadow.chmod(0o755)
            with patch.dict(os.environ, {'PATH': tmp, 'PYTHONPATH': tmp, 'LD_PRELOAD': '/bogus'}):
                result = runtime.command(['python3', '-I', '-c', 'print("packaged")'])
                self.assertEqual(result, 'packaged')
                self.assertNotIn('LD_PRELOAD', runtime.clean_environment())
                self.assertNotIn('PYTHONPATH', runtime.clean_environment())

    def test_untrusted_executable_and_unknown_command_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / 'ip'
            tool.write_text('fake')
            tool.chmod(0o755)
            with patch.dict(runtime.TOOLS, {'ip': str(tool)}):
                with self.assertRaises(RuntimeError):
                    runtime.verified_tool('ip')
        with self.assertRaises(KeyError):
            runtime.command(['arbitrary-command'])

    def test_output_cap_on_stdout_and_stderr(self):
        for stream in (1, 2):
            with self.subTest(stream=stream), self.assertRaisesRegex(RuntimeError, 'byte limit'):
                runtime.bounded_run(['/usr/bin/python3', '-I', '-c',
                                     f'import os; os.write({stream}, b"x" * 20000)'], limit=4096)

    def test_timeout_kills_sigterm_ignoring_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / 'pid'
            code = ('import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                    'pid=os.fork(); '
                    f'open({str(pidfile)!r},"w").write(str(os.getpid())) if pid == 0 else None; '
                    'time.sleep(60)')
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                runtime.bounded_run(['/usr/bin/python3', '-I', '-c', code], timeout=.4)
            assert_stopped(self, int(pidfile.read_text()))

    def test_success_also_cleans_lingering_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / 'pid'
            code = f'''import os, signal, time
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.close(1); os.close(2)
    open({str(pidfile)!r}, 'w').write(str(os.getpid()))
    time.sleep(60)
else:
    time.sleep(.1)
'''
            result = runtime.bounded_run(['/usr/bin/python3', '-I', '-c', code])
            self.assertEqual(result.returncode, 0)
            assert_stopped(self, int(pidfile.read_text()))

    def test_cancellation(self):
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            runtime.bounded_run(['/usr/bin/sleep', '60'], cancelled=lambda: True)

    def test_input_limit(self):
        with self.assertRaisesRegex(RuntimeError, 'input exceeds'):
            runtime.bounded_run(['/usr/bin/cat'], input='x' * 20, limit=10)

    def test_runtime_rejects_noncanonical_tmp_and_symlink_paths(self):
        for value in ('/tmp/omarchy-modem-' + str(os.getuid()), '/run/user/../user/' + str(os.getuid())):
            with patch.dict(os.environ, {'XDG_RUNTIME_DIR': value}), self.assertRaises(RuntimeError):
                runtime.private_runtime_fd()

    def test_runtime_rejects_wrong_owner_or_permissions(self):
        good = os.stat_result((0o40755, 1, 1, 1, 0, 0, 0, 0, 0, 0))
        for bad in (os.stat_result((0o40777, 1, 1, 1, os.getuid(), 0, 0, 0, 0, 0)),
                    os.stat_result((0o40700, 1, 1, 1, os.getuid() + 1, 0, 0, 0, 0, 0))):
            with patch.dict(os.environ, {'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}'}), \
                    patch.object(runtime.os, 'fstat', side_effect=[good, good, bad]), \
                    self.assertRaises(RuntimeError):
                runtime.private_runtime_fd()

    def test_lock_symlink_hardlink_fifo_and_permissions_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'valuable'
            target.write_text('unchanged')
            lock = Path(tmp) / 'omarchy-modem.lock'
            fd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY)
            try:
                for kind in ('symlink', 'hardlink', 'fifo', 'public'):
                    if kind == 'symlink':
                        lock.symlink_to(target)
                    elif kind == 'hardlink':
                        os.link(target, lock)
                    elif kind == 'fifo':
                        os.mkfifo(lock)
                    else:
                        lock.write_text('existing')
                        lock.chmod(0o666)
                    with self.subTest(kind=kind), self.assertRaises((OSError, RuntimeError)):
                        with runtime.lock_at(fd):
                            self.fail('Unsafe lock acquired')
                    lock.unlink()
                    self.assertEqual(target.read_text(), 'unchanged')
            finally:
                os.close(fd)

    def test_lock_is_exclusive_and_never_truncates(self):
        with tempfile.TemporaryDirectory() as tmp:
            fd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with runtime.lock_at(fd):
                    lock = Path(tmp) / 'omarchy-modem.lock'
                    lock.write_text('keep this')
                    with self.assertRaisesRegex(RuntimeError, 'already running'):
                        with runtime.lock_at(fd):
                            pass
                with runtime.lock_at(fd):
                    self.assertEqual(lock.read_text(), 'keep this')
            finally:
                os.close(fd)


def assert_stopped(test, pid):
    for _ in range(100):
        try:
            state = Path(f'/proc/{pid}/stat').read_text().split(') ')[1].split()[0]
            if state in ('Z', 'X'):
                return
        except (FileNotFoundError, ProcessLookupError):
            return
        time.sleep(.02)
    test.fail(f'Process {pid} survived cleanup')


class InstallerSecurity(unittest.TestCase):
    def test_destination_symlink_and_hardlink_do_not_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = Path(tmp) / 'victim'
            victim.write_bytes(b'keep')
            fd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY)
            try:
                for link in ('symlink', 'hardlink'):
                    dest = Path(tmp) / 'dest'
                    dest.symlink_to(victim) if link == 'symlink' else os.link(victim, dest)
                    with self.assertRaises(RuntimeError):
                        installer.atomic_file(fd, 'dest', b'replace', owners=(os.getuid(),))
                    self.assertEqual(victim.read_bytes(), b'keep')
                    dest.unlink()
            finally:
                os.close(fd)

    def test_atomic_install_preserves_old_open_descriptor_and_sets_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            fd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY)
            try:
                installer.atomic_file(fd, 'dest', b'old', owners=(os.getuid(),))
                with (Path(tmp) / 'dest').open('rb') as old:
                    installer.atomic_file(fd, 'dest', b'new', owners=(os.getuid(),))
                    self.assertEqual(old.read(), b'old')
                self.assertEqual((Path(tmp) / 'dest').read_bytes(), b'new')
                self.assertEqual((Path(tmp) / 'dest').stat().st_mode & 0o777, 0o644)
                self.assertEqual(sorted(os.listdir(tmp)), ['dest'])
            finally:
                os.close(fd)

    def test_destination_parent_symlink_and_writable_directory_rejected(self):
        # /tmp is intentionally forbidden for privileged destination traversal.
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root = Path(tmp)
            (root / 'real').mkdir()
            (root / 'link').symlink_to(root / 'real')
            with self.assertRaises(OSError):
                with installer.directory(root / 'link', owners=(0, os.getuid())):
                    pass
            (root / 'real').chmod(0o777)
            with self.assertRaises(RuntimeError):
                with installer.directory(root / 'real', owners=(0, os.getuid())):
                    pass

    def test_source_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'real').write_text('source')
            (root / 'link').symlink_to(root / 'real')
            fd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(OSError):
                    installer.read_source(fd, 'link', (os.getuid(),))
            finally:
                os.close(fd)

    def test_destination_swapped_for_symlink_during_write_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            victim = root / 'victim'
            victim.write_bytes(b'keep')
            fd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY)
            replace = os.replace
            def race(source, dest, **kwargs):
                (root / dest).symlink_to(victim)
                return replace(source, dest, **kwargs)
            try:
                with patch.object(installer.os, 'replace', side_effect=race):
                    installer.atomic_file(fd, 'dest', b'new', owners=(os.getuid(),))
                self.assertEqual(victim.read_bytes(), b'keep')
                self.assertEqual((root / 'dest').read_bytes(), b'new')
                self.assertFalse((root / 'dest').is_symlink())
            finally:
                os.close(fd)


@unittest.skipUnless(os.environ.get('MODEM_SYSTEMD_TESTS') == '1', 'opt-in live systemd cgroup tests')
class SystemdBoundary(unittest.TestCase):
    def test_service_deadline_survives_client_sigkill(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / 'pid'
            code = ('import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                    f'open({str(pidfile)!r},"w").write(str(os.getpid())); time.sleep(60)')
            unit = 'omarchy-modem-test-' + launcher.uuid.uuid4().hex + '.service'
            args = launcher.service_command(unit, 1, [])
            args = args[:args.index('--') + 1] + ['/usr/bin/python3', '-I', '-c', code]
            client = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, env=runtime.clean_environment())
            try:
                deadline = time.monotonic() + 5
                while not pidfile.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                pid = int(pidfile.read_text())
                client.kill()
                client.wait(timeout=2)
                time.sleep(3.2)  # 1s runtime plus the cgroup's 2s escalation deadline.
                assert_stopped(self, pid)
            finally:
                if client.poll() is None:
                    client.kill()
                    client.wait(timeout=2)
                runtime.bounded_run(['/usr/bin/systemctl', '--user', 'stop', unit], timeout=5)

    def test_detached_sigterm_ignoring_descendant_is_killed(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / 'pid'
            code = f'''import os, signal, time
pid = os.fork()
if pid == 0:
    os.setsid()
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    open({str(pidfile)!r}, 'w').write(str(os.getpid()))
time.sleep(60)
'''
            unit = 'omarchy-modem-test-' + launcher.uuid.uuid4().hex + '.service'
            args = launcher.service_command(unit, 1, [])
            args = args[:args.index('--') + 1] + ['/usr/bin/python3', '-I', '-c', code]
            try:
                result = runtime.bounded_run(args, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                assert_stopped(self, int(pidfile.read_text()))
            finally:
                runtime.bounded_run(['/usr/bin/systemctl', '--user', 'stop', unit], timeout=5)


if __name__ == '__main__':
    unittest.main()
