"""Linux process and filesystem boundaries shared by the panel helpers."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import time

OUTPUT_LIMIT = 131072  # Combined stdout/stderr bytes, before decoding.
TOOLS = {name: '/usr/bin/' + name for name in
         ('python3', 'ip', 'mmcli', 'nmcli', 'curl', 'wl-copy', 'systemd-run',
          'systemctl', 'systemd-analyze', 'modprobe')}


def verified_tool(name):
    """Allow only packaged paths under root-owned, non-writable ancestry.

    Resolve distro symlinks (e.g. python3 -> python3.14), then validate both
    spellings. A root administrator changing /usr is outside this boundary.
    """
    path = Path(TOOLS[name])
    for spelling in (path, path.resolve(strict=True)):
        for item in (*reversed(spelling.parents), spelling):
            st = item.stat()
            if st.st_uid != 0 or st.st_mode & 0o022:
                raise RuntimeError(f'Untrusted system tool path: {item}')
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or not st.st_mode & 0o111:
        raise RuntimeError(f'Not an executable system tool: {path}')
    return str(path)


def clean_environment():
    result = {'PATH': '/usr/bin', 'LC_ALL': 'C', 'LANG': 'C'}
    for key in ('XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'WAYLAND_DISPLAY'):
        if os.environ.get(key):
            result[key] = os.environ[key]
    return result


def _kill_group(pid, sig):
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def bounded_run(args, timeout=20, input=None, limit=OUTPUT_LIMIT, cancelled=lambda: False):
    """Drain both pipes incrementally; bound bytes, wall time, and process groups.

    Panel invocations additionally live in systemd cgroups, which also catch
    descendants that deliberately detach from this POSIX process group.
    """
    payload = (input or '').encode()
    if len(payload) > limit:
        raise RuntimeError('Command input exceeds byte limit')
    proc = subprocess.Popen(args, stdin=subprocess.PIPE if payload else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=clean_environment(), start_new_session=True)
    selector = selectors.DefaultSelector()
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    total = 0
    deadline = time.monotonic() + timeout
    for stream, name in ((proc.stdout, 'stdout'), (proc.stderr, 'stderr')):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    if payload:
        os.set_blocking(proc.stdin.fileno(), False)
        selector.register(proc.stdin, selectors.EVENT_WRITE, 'stdin')
    try:
        while selector.get_map() or proc.poll() is None:
            if cancelled():
                raise RuntimeError('Command cancelled')
            if time.monotonic() >= deadline:
                raise RuntimeError('Command timed out')
            for key, _ in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                if key.data == 'stdin':
                    try:
                        sent = os.write(key.fd, payload[:4096])
                        payload = payload[sent:]
                    except BrokenPipeError:
                        payload = b''
                    if not payload:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                    continue
                chunk = os.read(key.fd, min(8192, limit - total + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                total += len(chunk)
                if total > limit:
                    raise RuntimeError('Command output exceeds byte limit')
                buffers[key.data].extend(chunk)
        out, err = (buffers[name].decode('utf-8', errors='replace') for name in ('stdout', 'stderr'))
        return subprocess.CompletedProcess(args, proc.returncode, out, err)
    finally:
        # Also clean children left behind after a successful parent exit.
        _kill_group(proc.pid, signal.SIGTERM)
        until = time.monotonic() + 0.5
        while time.monotonic() < until:
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        _kill_group(proc.pid, signal.SIGKILL)
        proc.wait(timeout=2)
        selector.close()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream and not stream.closed:
                stream.close()


def command(args, timeout=20, **kwargs):
    args = [verified_tool(args[0]), *args[1:]]
    result = bounded_run(args, timeout=timeout, **kwargs)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'Command failed').strip()[:600])
    return result.stdout.strip()


def private_runtime_fd():
    """Open the canonical logind runtime via descriptors, never a /tmp fallback."""
    uid = os.getuid()
    expected = f'/run/user/{uid}'
    if os.environ.get('XDG_RUNTIME_DIR', expected) != expected:
        raise RuntimeError('XDG_RUNTIME_DIR must name the private logind runtime directory')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in ('run', 'user', str(uid)):
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            st = os.fstat(fd)
            if part == str(uid):
                if st.st_uid != uid or stat.S_IMODE(st.st_mode) != 0o700:
                    raise RuntimeError('Runtime directory must be owned by this user with mode 0700')
            elif st.st_uid != 0 or st.st_mode & 0o022:
                raise RuntimeError('Unsafe runtime directory ancestry')
        return os.dup(fd)
    finally:
        os.close(fd)


@contextmanager
def lock_at(directory_fd):
    name = 'omarchy-modem.lock'
    flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
    except FileExistsError:
        fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1):
            raise RuntimeError('Unsafe modem lock file')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another modem action is already running.') from None
        yield
    finally:
        os.close(fd)


@contextmanager
def action_lock():
    fd = private_runtime_fd()
    try:
        with lock_at(fd):
            yield
    finally:
        os.close(fd)
