#!/usr/bin/python3 -I
"""Bounded recovery for this machine's XMM7360 after resume."""
import json
from pathlib import Path
import time
import runpy

runtime_path = Path(__file__).with_name('secure_runtime.py')
if not runtime_path.exists():
    runtime_path = Path(__file__).parent.parent / 'secure_runtime.py'
runtime = runpy.run_path(str(runtime_path))

PCI = Path('/sys/bus/pci/devices/0000:02:00.0')
DRIVER = Path('/sys/bus/pci/drivers/iosm')


def run(*args):
    # The public run signature retains the absolute identities used at each call site.
    return runtime['command']([Path(args[0]).name, *args[1:]], timeout=30)


def guarded_device():
    try:
        return (PCI.joinpath('vendor').read_text().strip() == '0x8086'
                and PCI.joinpath('device').read_text().strip() == '0x7360'
                and PCI.joinpath('driver').resolve() == DRIVER
                and PCI.joinpath('reset').exists()
                and list(DRIVER.glob('????:??:??.?')) == [DRIVER / PCI.name])
    except OSError:
        return False


def detected():
    # Errors are fatal: a failed D-Bus query must never trigger a hardware reset.
    data = json.loads(run('/usr/bin/mmcli', '--list-modems', '--output-json'))
    modems = data['modem-list']
    if not isinstance(modems, list):
        raise ValueError('Unexpected modem list')
    return bool(modems)


def wait_detected(seconds):
    deadline = time.monotonic() + seconds
    while True:
        if detected():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(3)


def main():
    run('/usr/bin/systemctl', 'is-active', '--quiet', 'ModemManager.service')
    if not guarded_device():
        print('Skipping recovery: expected sole iosm XMM7360 device not found.', flush=True)
        return
    if wait_detected(45):
        print('Modem detected; no recovery needed.', flush=True)
        return
    if not guarded_device():
        raise RuntimeError('Device changed while waiting; refusing reset')
    print('No modem after grace period; resetting Intel XMM7360 once.', flush=True)
    run('/usr/bin/systemctl', 'stop', 'ModemManager.service')
    try:
        run('/usr/bin/modprobe', '-r', 'iosm')
        PCI.joinpath('reset').write_text('1\n')
    finally:
        try:
            run('/usr/bin/modprobe', 'iosm')
        finally:
            run('/usr/bin/systemctl', 'start', 'ModemManager.service')
    if not wait_detected(90):
        raise RuntimeError('Modem still unavailable after one recovery; see kernel journal')
    print('Modem detection restored. NetworkManager retains the radio and autoconnect settings.', flush=True)


if __name__ == '__main__':
    main()
