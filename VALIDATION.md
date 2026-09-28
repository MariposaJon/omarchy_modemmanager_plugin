# Release validation

## Version 1.1.1 — 28 September 2026

Renamed the display name, panel title, tooltip, and README to **Modem Manager**.
Added marketplace artwork with that name and documented the sample UI capture.
The permanent plugin ID remains `jon.modem`. Changes since the listed v1.1.0
snapshot are presentation, assets, and documentation only.

`MODEM_SYSTEMD_TESTS=1 bash scripts/validate.sh` passed: 25 backend/security tests
(including both live systemd cleanup cases), five recovery tests, manifest
validation, installer syntax, and QML lint. `git diff --check` passed. No modem
or network controls were exercised for this presentation update.

## Version 1.1.0

Version 1.1.0 follows the [Omarchy authoring guide](https://plugins.omarchy.org/develop.html)
and [publishing requirements](https://plugins.omarchy.org/publish.html).

## Repository and runtime contract

- Public repository, root manifest, MIT license, and dependency documentation.
- Permanent namespaced ID `jon.modem`; no reserved `omarchy.*` ID or clone metadata.
- `bar-widget` maps to `entryPoints.barWidget` and the existing `Panel.qml`.
  This combined bar button/panel structure also appears in Omarchy's built-in
  network widget. `Ui.Panel` supplies the shell's open/close lifecycle and settings.
- Uses the existing shell process, theme tokens, shared UI controls, keyboard
  panel handling, and bounded helper processes.
- Standard `omarchy plugin add`, `update`, and `remove` installation lifecycle.
- Optional privileged Intel recovery is separately documented and never
  automatically installed by adding the plugin.
- No symlinks, caches, credentials, or local user paths in the tracked files.

## Automated checks

Run `bash scripts/validate.sh` on Omarchy with `qt6-declarative` installed.
The official manifest validator, seven panel backend tests, five recovery tests,
installer Python syntax, and QML lint pass.

QML lint uses a temporary `qs` import alias to resolve the same shell imports
that Quickshell resolves at runtime. Source annotations suppress only known
external metadata gaps at the affected property declarations and handlers:
Omarchy's dynamic host/font members and Quickshell's missing exit-status type.

## Installed lifecycle checks (2026-09-10)

The manually installed panel was backed up through `omarchy plugin remove`,
then installed from this public repository with `omarchy plugin add --enable`.
Disable/re-enable and `omarchy plugin update` passed. After a shell restart,
the shell reported the widget mounted and visible in the right bar section.
Repeated shell summon/hide calls succeeded and Escape was exercised while the
panel was open. No modem-plugin QML errors or duplicate IPC warnings appeared
in the fresh shell log. The panel uses the shell routing APIs rather than
registering a separate IPC handler for each bar instance.

Visual checks on additional monitor layouts and physical click/keyboard
interaction on other machines remain part of broader compatibility testing.

## Hardware coverage

Verified hardware is Fibocom L850 / Intel XMM7360 with a locally patched
ModemManager 1.25.95-2. Radio controls, connection controls, and cellular-bound
HTTPS have passed on that setup. This does not establish support for all modems
or stock ModemManager versions. No driver binaries are included.

The optional recovery helper restored an observed failed modem and skipped a
healthy modem in a separate trigger test. A subsequent real sleep/wake cycle
has not yet been verified. See [recovery/README.md](recovery/README.md).

Marketplace acceptance still requires a separate submission and maintainer
approval; passing these checks is not an approval or security certification.

## Security boundary regression checks (2026-09-11)

Run `MODEM_SYSTEMD_TESTS=1 bash scripts/validate.sh` to include the live cgroup
checks. Without that opt-in, the live systemd cases are explicitly reported as
skipped. The test processes perform no modem, network, or root service changes.

The suite covers command shadowing, environment injection, runtime ownership,
lock symlinks/hardlinks/FIFOs, exclusive non-truncating locks, stdout/stderr
floods, timeouts/cancellation, lingering child cleanup, descriptor-relative
atomic writes, and symlink replacement races. Live systemd cases verify cleanup
of a detached SIGTERM-ignoring descendant and enforcement of the service
deadline after its client is killed with SIGKILL. See [SECURITY.md](SECURITY.md).

On the development laptop, all 30 tests passed with the live cgroup cases
enabled, along with manifest validation and QML lint. A read-only status query
through the new launcher succeeded. NetworkManager reported `yes` for WWAN and
network-control permissions from inside the transient user service. The new
root installer completed successfully, and the installed recovery service
reported a healthy modem and exited without resetting it. Its effective
KillMode is control-group and its stop timeout is two seconds.
