# Release validation

Version 1.0.2 follows the [Omarchy authoring guide](https://plugins.omarchy.org/develop.html)
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
The official manifest validator, six panel backend tests, five recovery tests,
installer shell syntax, and QML lint pass.

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
