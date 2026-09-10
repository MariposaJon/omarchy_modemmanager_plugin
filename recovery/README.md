# Optional Intel XMM7360 recovery

This workaround targets the tested laptop's Intel 8086:7360 at PCI address
`0000:02:00.0`, using iosm. It is not a general ModemManager requirement.
Installing the Omarchy panel does not install this service.

After sleep, the helper gives ModemManager 45 seconds to detect a modem. If
none appears, it stops ModemManager, unloads iosm, resets the PCI device,
reloads iosm, and starts ModemManager. It makes at most one reset attempt and
waits up to 90 seconds for detection afterward.

The helper requires that exact hardware and PCI address, a reset interface,
and no other iosm devices. Any detected modem prevents resetting. Failed
D-Bus queries abort the check. Driver and service restart are attempted even
if resetting fails. Radio and profile preferences are retained.

## Install

Review the scripts and confirm your hardware matches before installing. From
the repository root in a terminal:

```bash
sudo bash recovery/install.sh
```

This installs root-owned files into `/usr/local/libexec/` and
`/etc/systemd/system/`, enables the after-sleep trigger, and schedules an
immediate health check. A missing modem may therefore be reset during
installation. No additional Polkit authorization rules are installed.

## Inspect

```bash
systemctl is-enabled xmm7360-resume.service
journalctl -u xmm7360-recover.service -u xmm7360-resume.service
```

## Remove

Allow any active recovery to finish before removing the helper:

```bash
sudo systemctl disable xmm7360-resume.service
systemctl status xmm7360-recover.service
```

Once recovery is inactive and the computer is awake:

```bash
sudo systemctl stop xmm7360-resume.service
```

Stopping an armed resume unit may queue one final health check. Wait for
`xmm7360-recover.service` to become inactive again, then:

```bash
sudo rm /etc/systemd/system/xmm7360-resume.service /etc/systemd/system/xmm7360-recover.service
sudo rm /usr/local/libexec/xmm7360-recover
sudo systemctl daemon-reload
```

## Verification and limits

On 2026-09-09, the helper restored modem detection about 40 seconds after the
reset. Exercising the resume trigger without suspending correctly skipped
resetting the healthy modem. The panel's power-on action restored cellular
data and cellular-bound HTTPS passed. The five recovery tests pass.

A subsequent real sleep/wake cycle has not been verified in this release.
This recovers the observed failure rather than fixing the driver or firmware.
It does not guarantee network registration or data reconnection: if
NetworkManager exhausts early retries, use the panel's power-on/Connect action.
