#!/usr/bin/python3 -I
"""Finite, byte-capped relay between QML and a transient systemd user service."""
import argparse
import json
import os
from pathlib import Path
import runpy
import signal
import sys
import uuid

runtime = runpy.run_path(str(Path(__file__).with_name('secure_runtime.py')))
cancelled = False


def cancel(_sig, _frame):
    global cancelled
    cancelled = True


def service_command(unit, seconds, helper_args):
    tool = runtime['verified_tool']
    args = [tool('systemd-run'), '--user', '--quiet', '--pipe', '--wait', '--collect',
            '--no-ask-password', '--expand-environment=no', '--service-type=exec',
            '--unit=' + unit,
            '--property=RuntimeMaxSec=' + str(seconds), '--property=TimeoutStartSec=5s',
            '--property=TimeoutStopSec=2s',
            '--property=KillMode=control-group', '--property=SendSIGKILL=yes',
            '--property=FinalKillSignal=SIGKILL', '--property=NoNewPrivileges=yes',
            '--property=TasksMax=32', '--property=MemoryMax=128M',
            '--property=UnsetEnvironment=LD_PRELOAD LD_LIBRARY_PATH PYTHONPATH PYTHONHOME',
            '--setenv=PATH=/usr/bin', '--setenv=LC_ALL=C']
    for key in ('XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'WAYLAND_DISPLAY'):
        if os.environ.get(key):
            args.append('--setenv=' + key + '=' + os.environ[key])
    return [*args, '--', tool('python3'), '-I', str(Path(__file__).with_name('modem.py')), *helper_args]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'power-on', 'power-off', 'connect', 'disconnect',
                                          'auto-on', 'auto-off', 'test', 'copy'])
    parser.add_argument('--profile', default='')
    args = parser.parse_args()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, cancel)
    unit = 'omarchy-modem-' + uuid.uuid4().hex + '.service'
    seconds = 20 if args.action == 'status' else 180
    try:
        # Validate the runtime before contacting the per-user service manager.
        fd = runtime['private_runtime_fd']()
        os.close(fd)
        command = service_command(unit, seconds, [args.action, '--profile', args.profile])
        result = runtime['bounded_run'](command, timeout=seconds + 8, cancelled=lambda: cancelled)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or 'Helper service failed').strip()[:600])
        data = json.loads(result.stdout)
    except (OSError, RuntimeError, ValueError) as exc:
        data = {'ok': False, 'error': str(exc)[:600]}
    finally:
        # Independent cgroup deadlines still apply if this relay is SIGKILLed.
        try:
            runtime['command'](['systemctl', '--user', '--no-block', 'stop', unit], timeout=3)
        except (OSError, RuntimeError):
            pass  # Already collected, or user manager gone; RuntimeMaxSec remains armed.
    encoded = json.dumps(data)
    if len(encoded.encode()) + 1 > runtime['OUTPUT_LIMIT']:
        data = {'ok': False, 'error': 'Status exceeds output byte limit'}
        encoded = json.dumps(data)
    print(encoded)
    return 0 if data.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
