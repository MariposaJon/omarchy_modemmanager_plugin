#!/usr/bin/python3 -I
"""Explicit root installer; all destination traversal uses checked directory fds.

Run with /usr/bin/python3 -I. No shell, PATH lookup, or pathname-based writes.
The reviewed checkout is trusted input; user-writable destinations are not.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import sys
import uuid

FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


@contextmanager
def directory(path, *, owners=(0,), create=False):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise RuntimeError('Expected an absolute path without parent traversal')
    fd = os.open('/', FLAGS)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o755, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
            st = os.fstat(fd)
            if st.st_uid not in owners or st.st_mode & 0o022:
                raise RuntimeError(f'Unsafe directory ownership or permissions: {path}')
        yield fd
    finally:
        os.close(fd)


def existing_regular(fd, name, owners=(0,)):
    try:
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (not stat.S_ISREG(st.st_mode) or st.st_uid not in owners
            or st.st_mode & 0o022 or st.st_nlink != 1):
        raise RuntimeError(f'Unsafe existing file: {name}')


def read_source(fd, name, owners):
    source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
    try:
        st = os.fstat(source)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid not in owners or st.st_mode & 0o022
                or st.st_nlink != 1 or st.st_size > 262144):
            raise RuntimeError(f'Unsafe source file: {name}')
        with os.fdopen(os.dup(source), 'rb') as stream:
            data = stream.read(262145)
        if len(data) > 262144:
            raise RuntimeError('Source file exceeds size limit')
        return data
    finally:
        os.close(source)


def atomic_file(fd, name, data, mode=0o644, owners=(0,)):
    if '/' in name or name in ('.', '..'):
        raise RuntimeError('Destination must be a basename')
    existing_regular(fd, name, owners)
    temporary = '.' + name + '.' + uuid.uuid4().hex
    out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                  0o600, dir_fd=fd)
    try:
        with os.fdopen(os.dup(out), 'wb') as stream:
            stream.write(data)
            stream.flush()
        os.fchmod(out, mode)
        os.fsync(out)
        # renameat never follows a symlink at the destination; a racing link
        # can only itself be replaced, never redirect this write to its target.
        os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(out)
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass


def enable_link(fd):
    name = 'xmm7360-resume.service'
    target = '../' + name
    try:
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        st = None
    if st is not None and (not stat.S_ISLNK(st.st_mode) or st.st_uid != 0
                          or os.readlink(name, dir_fd=fd) not in (target, '/etc/systemd/system/' + name)):
        raise RuntimeError('Unexpected existing resume enablement entry')
    temporary = '.' + name + '.' + uuid.uuid4().hex
    os.symlink(target, temporary, dir_fd=fd)
    try:
        os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass


def main():
    if not sys.flags.isolated:
        raise RuntimeError('Run /usr/bin/python3 -I recovery/install.py')
    if os.geteuid() != 0:
        raise RuntimeError('Administrator installation required')
    if len(sys.argv) != 1:
        raise RuntimeError('This installer takes no arguments')
    os.umask(0o077)
    caller = int(os.environ.get('SUDO_UID', os.environ.get('PKEXEC_UID', '0')))
    owners = (0, caller)
    checkout = Path(__file__).absolute().parent
    # Snapshot all reviewed sources using no-follow descriptors before mutation.
    with directory(checkout, owners=owners) as source:
        files = {name: read_source(source, name, owners) for name in
                 ('recover.py', 'xmm7360-recover.service', 'xmm7360-resume.service')}
    with directory(checkout.parent, owners=owners) as source:
        files['secure_runtime.py'] = read_source(source, 'secure_runtime.py', owners)
    runtime = {'__name__': 'installer_runtime'}
    exec(compile(files['secure_runtime.py'], 'secure_runtime.py', 'exec'), runtime)
    for name in ('python3', 'systemctl', 'systemd-analyze', 'modprobe', 'mmcli'):
        runtime['verified_tool'](name)
    # Preserve only the minimal fixed environment for subprocesses.
    os.environ.clear()
    os.environ.update({'PATH': '/usr/bin', 'LC_ALL': 'C'})
    with directory('/usr/local/libexec/omarchy-modem-recovery', create=True) as destination:
        for name in ('recover.py', 'secure_runtime.py'):
            atomic_file(destination, name, files[name])
    with directory('/etc/systemd/system') as destination:
        for name in ('xmm7360-recover.service', 'xmm7360-resume.service'):
            atomic_file(destination, name, files[name])
    runtime['command'](['systemd-analyze', 'verify', '/etc/systemd/system/xmm7360-recover.service',
                        '/etc/systemd/system/xmm7360-resume.service'])
    with directory('/etc/systemd/system/sleep.target.wants', create=True) as destination:
        enable_link(destination)
    runtime['command'](['systemctl', 'daemon-reload'])
    runtime['command'](['systemctl', 'start', '--no-block', 'xmm7360-recover.service'])
    print('Installed and enabled guarded modem recovery; immediate health check scheduled.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        sys.exit(str(exc))
