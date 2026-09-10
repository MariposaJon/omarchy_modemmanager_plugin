# Mobile Broadband for Omarchy

A native, theme-aware Omarchy bar panel for ModemManager and NetworkManager.
Plugin ID: `jon.modem`. Licensed under MIT.

- Four-bar cellular indicator; click for controls, right-click to toggle radio.
- Power off disables NetworkManager WWAN (preventing autoconnect), disables the modem, and enters low power. Power on restores the radio; saved autoconnect settings apply.
- Connect/disconnect data separately from radio power, choose a saved GSM profile, toggle autoconnect.
- Carrier, SIM provider, roaming, signal freshness, IP, APN, preferred default route, and live transfer rates.
- Interface byte counters are totals since the interface was created/reset, **not billing or monthly usage**.
- Manual HTTPS test bound to the cellular interface. Uses a small request to https://1.1.1.1/ only when clicked; no periodic internet tests.
- Copy local diagnostic status without IMEI, IMSI, ICCID, or credentials. It includes local profile UUIDs, addresses, and traffic counters.
- Keyboard: arrows/j/k select controls; Enter/Space activate; P power, C connection, T test, R refresh, Escape close. Tab switches shell panels. Profile dropdown has its own keyboard navigation.

Requires Omarchy's Quickshell shell, `python`, `python-dbus`, `modemmanager`, `networkmanager`, `iproute2`, `curl`, and `wl-clipboard`. The panel uses ordinary user D-Bus/Polkit permissions; installing the panel adds no privileged helper or authorization rules. The optional Intel recovery service is documented separately below. It reports authorization errors instead of silently escalating.

Status refreshes every 10 seconds in the background and 3 seconds with the panel open. The background interval can be changed in the widget settings. The panel does not guess SIM PINs or reset modem hardware. On multi-modem systems it selects the most active modem; explicit device selection is not implemented.

## Install / update

With the dependencies above installed and ModemManager and NetworkManager running:

```bash
git clone https://github.com/MariposaJon/omarchy_modemmanager_plugin.git
cd omarchy_modemmanager_plugin
mkdir -p ~/.config/omarchy/plugins/jon.modem
cp manifest.json Panel.qml Service.qml SignalIcon.qml modem.py README.md LICENSE ~/.config/omarchy/plugins/jon.modem/
omarchy plugin validate ~/.config/omarchy/plugins/jon.modem
omarchy-shell shell rescanPlugins
omarchy plugin enable jon.modem --section right --before omarchy.network
```

For updates, run `git pull --ff-only` from your checkout, then repeat the copy,
validation, and rescan commands. Open the panel with `omarchy-shell jon.modem open`.
Create your cellular connection profile in NetworkManager first; this panel
selects existing compatible GSM profiles.

## Remove

```bash
omarchy plugin disable jon.modem
rm -r ~/.config/omarchy/plugins/jon.modem
omarchy-shell shell rescanPlugins
```

This removes the panel; saved NetworkManager connections remain available.
If you separately installed the optional recovery service, remove it using
the instructions in [recovery/README.md](recovery/README.md).

## Compatibility and validation

Requires the Omarchy Quickshell plugin API (`qs.Ui`, `qs.Commons` and bar-widget
support). Tested on a Fibocom L850 / Intel XMM7360 with a locally patched
ModemManager 1.25.95-2 and an Onomondo SIM. Other modem models and stock
ModemManager versions have not been verified. The panel uses ModemManager's
public D-Bus interface; it does not include modem drivers or the patched
ModemManager build. Your hardware must already be supported by ModemManager.

Verified controls include radio off/on, data disconnect/reconnect, autoconnect,
and cellular-bound HTTPS with Wi-Fi remaining preferred. The power-on action
waits for registration and makes one explicit connection attempt when the
selected profile has autoconnect enabled. It preserves that preference.

From the repository root:

```bash
python -m unittest discover -s . -p test_modem.py -v
python -m unittest discover -s recovery -v
omarchy plugin validate .
```

The six panel backend tests cover profile selection, SIM matching, power
sequencing, hardware blocks, autoconnect, and interface-bound connectivity
testing. Five recovery tests cover hardware guards and failure handling.

## Intel modem unavailable after sleep

The panel distinguishes an Intel PCI modem that is visible but unavailable to
ModemManager from absent hardware. On the tested XMM7360, the iosm driver can
return `PORT open refused, phase A-CD_READY` after sleep and leave ModemManager
with no usable modem.

An optional, hardware-specific recovery workaround is in [recovery/](recovery/README.md).
It requires administrator installation and is not installed by the panel setup.
It targets Intel 8086:7360 at PCI address `0000:02:00.0` only.
