#!/usr/bin/python3 -I
"""Small, unprivileged ModemManager/NetworkManager bridge for the Omarchy panel."""
import argparse
import runpy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import dbus

MM = 'org.freedesktop.ModemManager1'
NM = 'org.freedesktop.NetworkManager'
MI = MM + '.Modem'
NI = NM
STATES = {-1: 'Failed', 0: 'Starting', 1: 'Starting', 2: 'SIM locked',
          3: 'Radio disabled', 4: 'Disabling', 5: 'Enabling', 6: 'Ready',
          7: 'Searching', 8: 'Registered', 9: 'Disconnecting', 10: 'Connecting', 11: 'Connected'}


_runtime = runpy.run_path(str(Path(__file__).with_name('secure_runtime.py')))
run = _runtime['command']


def props(bus, service, path, interface):
    return dict(dbus.Interface(bus.get_object(service, path),
                              'org.freedesktop.DBus.Properties').GetAll(interface, timeout=5))


def modem_objects(bus):
    return dbus.Interface(bus.get_object(MM, '/org/freedesktop/ModemManager1'),
                          'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=5)


def compatible(gsm, sim):
    """Never automatically choose a profile bound to a different SIM/operator."""
    return (not gsm.get('sim-id') or gsm['sim-id'] == sim.get('SimIdentifier')) and (
        not gsm.get('sim-operator-id') or gsm['sim-operator-id'] == sim.get('OperatorIdentifier'))


def intel_modem_present():
    for device in Path('/sys/bus/pci/devices').glob('*'):
        try:
            if (device.joinpath('vendor').read_text().strip() == '0x8086' and
                    device.joinpath('device').read_text().strip() == '0x7360'):
                return True
        except OSError:
            continue
    return False


def snapshot():
    bus = dbus.SystemBus()
    nm = props(bus, NM, '/org/freedesktop/NetworkManager', NI)
    result = {'ok': True, 'present': False, 'radio': bool(nm.get('WwanEnabled')),
              'radioEnabled': bool(nm.get('WwanEnabled')),
              'hardwareEnabled': bool(nm.get('WwanHardwareEnabled', True)),
              'connected': False, 'status': 'No modem detected', 'profiles': [],
              'timestamp': time.time()}
    try:
        objects = modem_objects(bus)
    except dbus.DBusException as exc:
        result.update(ok=False, status='ModemManager unavailable', error=str(exc))
        return result
    modems = [(str(p), v) for p, v in objects.items() if MI in v]
    if not modems:
        if intel_modem_present():
            result.update(status='Modem hardware detected · unavailable',
                          hint='The Intel modem is visible, but ModemManager has no usable modem. It may still be starting or need recovery after sleep.')
        else:
            result['hint'] = 'ModemManager has no usable modem. Check the device and cellular settings.'
        return result
    path, interfaces = sorted(modems, key=lambda item: -int(item[1][MI].get('State', 0)))[0]
    m = interfaces[MI]
    g = interfaces.get(MI + '.Modem3gpp', {})
    # The 3GPP interface is Modem.Modem3gpp on ModemManager's object.
    sim = objects.get(m.get('Sim'), {}).get(MM + '.Sim', {})
    if not sim and str(m.get('Sim', '/')) != '/':
        try:
            sim = props(bus, MM, m['Sim'], MM + '.Sim')
        except dbus.DBusException:
            pass
    state = int(m.get('State', 0))
    power = int(m.get('PowerState', 0))
    quality = m.get('SignalQuality', (0, False))
    tech = int(m.get('AccessTechnologies', 0))
    result.update(present=True, modem=path, state=state, power=power,
                  radio=result['radio'] and power == 3,
                  connected=state == 11,
                  status=STATES.get(state, 'Unknown'),
                  model=str(m.get('Model', 'Modem')).split('","')[0],
                  carrier=str(g.get('OperatorName', '')),
                  provider=str(sim.get('OperatorName', '')),
                  registration=int(g.get('RegistrationState', 0)),
                  roaming=int(g.get('RegistrationState', 0)) in (5, 7, 10),
                  signal=int(quality[0]), signalRecent=bool(quality[1]),
                  technology='5G' if tech & (1 << 15) else '4G' if tech & (1 << 14) else '3G' if tech else '',
                  device=str(m.get('PrimaryPort', '')),
                  interface=next((str(p[0]) for p in m.get('Ports', []) if int(p[1]) == 2), ''), ip='',
                  apn=str(g.get('InitialEpsBearerSettings', {}).get('apn', '')),
                  rx=0, tx=0, duration=0, profile='', profileName='', autoconnect=False)
    if not result['radio']:
        result['status'] = 'Radio off'
    if state == 2:
        result['status'] = 'SIM locked — unlock in network settings'
    for bearer_path in m.get('Bearers', []):
        b = objects.get(bearer_path, {}).get(MM + '.Bearer', {})
        if not b:
            b = props(bus, MM, bearer_path, MM + '.Bearer')
        if b.get('Connected'):
            stats = b.get('Stats', {})
            result.update(interface=str(b.get('Interface', '')), ip=str(b.get('Ip4Config', {}).get('address', '')),
                          duration=int(stats.get('duration', 0)))
            break
    active_uuid = ''
    for apath in nm.get('ActiveConnections', []):
        a = props(bus, NM, apath, NI + '.Connection.Active')
        if a.get('Type') == 'gsm':
            for device_path in a.get('Devices', []):
                d = props(bus, NM, device_path, NI + '.Device')
                if str(d.get('Udi', '')) == path or d.get('Interface') == result['device']:
                    active_uuid = str(a['Uuid'])
                    result['interface'] = str(d.get('IpInterface') or result['interface'])
    connections = dbus.Interface(bus.get_object(NM, '/org/freedesktop/NetworkManager/Settings'),
                                  NI + '.Settings').ListConnections(timeout=5)
    for cpath in connections:
        settings = dbus.Interface(bus.get_object(NM, cpath), NI + '.Settings.Connection').GetSettings(timeout=5)
        c = settings.get('connection', {})
        gsm = settings.get('gsm', {})
        if c.get('type') != 'gsm' or not compatible(gsm, sim):
            continue
        result['profiles'].append({'uuid': str(c['uuid']), 'name': str(c['id']),
            'apn': str(gsm.get('apn', '')), 'autoconnect': bool(c.get('autoconnect', True)),
            'active': str(c['uuid']) == active_uuid})
    result['profiles'].sort(key=lambda p: (not p['active'], p['apn'] != result['apn'], p['name']))
    if result['profiles']:
        selected = result['profiles'][0]
        result.update(profile=selected['uuid'], profileName=selected['name'],
                      autoconnect=selected['autoconnect'], apn=selected['apn'])
    iface = result['interface']
    if iface and '/' not in iface:
        for key, filename in [('rx', 'rx_bytes'), ('tx', 'tx_bytes')]:
            try:
                result[key] = int(Path('/sys/class/net', iface, 'statistics', filename).read_text())
            except (OSError, ValueError):
                pass
    try:
        routes = json.loads(run(['ip', '-j', '-4', 'route', 'show', 'default'], timeout=3))
        best = min(routes, key=lambda r: r.get('metric', 0)) if routes else {}
        result['route'] = 'Cellular preferred' if iface and best.get('dev') == iface else 'Other connection preferred'
        if str(best.get('dev', '')).startswith('wl'):
            result['route'] = 'Wi-Fi preferred'
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        result['route'] = 'Route unavailable'
    return result


def action(name, selected=''):
    s = snapshot()
    if not s.get('ok'):
        raise RuntimeError(s.get('status', 'Modem unavailable'))
    if name == 'power-on':
        if not s['hardwareEnabled']:
            raise RuntimeError('Cellular is blocked by a hardware switch or airplane mode.')
        if s.get('present') and s.get('power') != 3:
            run(['mmcli', '-m', s['modem'], '--set-power-state-on', '--timeout=30'], timeout=35)
        run(['nmcli', 'radio', 'wwan', 'on'])
        automatic = next((p for p in s.get('profiles', [])
                          if p['uuid'] == (selected or s.get('profile')) and p['autoconnect']), None)
        if automatic:
            # This Intel modem can exhaust NM's early autoconnect retries before
            # registration completes. Make one deliberate attempt once ready.
            seen_radio_enabled = False
            for _ in range(45):
                current = snapshot()
                if current.get('connected'):
                    return 'Radio enabled · cellular connected'
                if not current.get('radioEnabled'):
                    if seen_radio_enabled:
                        raise RuntimeError('Cellular radio was switched off while waiting.')
                    time.sleep(1)
                    continue
                seen_radio_enabled = True
                if current.get('registration') in (1, 5):
                    run(['nmcli', '--wait', '45', 'connection', 'up', 'uuid', automatic['uuid'],
                         'ifname', current['device']], timeout=50)
                    return 'Radio enabled · cellular connected'
                time.sleep(1)
            return 'Radio enabled · waiting for network; use Connect once registered'
        return 'Cellular radio enabled'
    if name == 'power-off':
        run(['nmcli', 'radio', 'wwan', 'off'])
        if s.get('present'):
            # NM disables the modem asynchronously; allow that transition to settle.
            for _ in range(20):
                current = snapshot()
                if not current.get('present') or current.get('state') == 3:
                    break
                time.sleep(.5)
            if current.get('present'):
                run(['mmcli', '-m', current['modem'], '--disable', '--timeout=20'], timeout=25)
                run(['mmcli', '-m', current['modem'], '--set-power-state-low', '--timeout=20'], timeout=25)
        return 'Cellular radio off · low power'
    if not s.get('present'):
        raise RuntimeError('No modem detected')
    profile = selected or s.get('profile')
    valid = {p['uuid'] for p in s['profiles']}
    if name in ('connect', 'auto-on', 'auto-off') and profile not in valid:
        raise RuntimeError('Select a compatible mobile broadband profile in network settings.')
    if name == 'connect':
        if not s['radio']:
            raise RuntimeError('Turn on the cellular radio first.')
        run(['nmcli', '--wait', '60', 'connection', 'up', 'uuid', profile, 'ifname', s['device']], timeout=65)
        return 'Connected'
    if name == 'disconnect':
        run(['nmcli', '--wait', '20', 'device', 'disconnect', s['device']], timeout=25)
        return 'Disconnected · radio remains on'
    if name in ('auto-on', 'auto-off'):
        run(['nmcli', 'connection', 'modify', 'uuid', profile, 'connection.autoconnect', 'yes' if name == 'auto-on' else 'no'])
        return 'Automatic connection ' + ('enabled' if name == 'auto-on' else 'disabled')
    if name == 'test':
        if not s['connected'] or not s['interface']:
            raise RuntimeError('Connect cellular data before testing.')
        result = run(['curl', '--disable', '--interface', s['interface'], '--noproxy', '*', '--max-time', '12',
                      '-sS', '-o', '/dev/null', '-w', '%{http_code} %{time_total}', 'https://1.1.1.1/'], timeout=15)
        code, elapsed = result.split()
        if not 200 <= int(code) < 400:
            raise RuntimeError('Cellular test returned HTTP ' + code)
        return f'Cellular HTTPS passed · {round(float(elapsed)*1000)} ms'
    if name == 'copy':
        # snapshot intentionally excludes IMSI, full ICCID, IMEI, and credentials.
        run(['wl-copy', '--foreground', '--paste-once'], input=json.dumps(s, indent=2), timeout=60)
        return 'Diagnostics pasted (no SIM identifiers or credentials)'
    raise RuntimeError('Unknown action')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'power-on', 'power-off', 'connect', 'disconnect', 'auto-on', 'auto-off', 'test', 'copy'])
    parser.add_argument('--profile', default='')
    args = parser.parse_args()
    try:
        if args.action == 'status':
            result = snapshot()
        else:
            with _runtime['action_lock']():
                result = {'ok': True, 'message': action(args.action, args.profile)}
        print(json.dumps(result))
        return 0 if result.get('ok') else 1
    except (dbus.DBusException, RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)[:600]}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
