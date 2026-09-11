# Runtime and privileged installation boundaries

Version 1.1.0 addresses the four findings on the marketplace's reviewed
`fee75e2b80a1c12495d6084eadbba8b246bd1364` commit. These measures constrain helper
execution; the plugin itself still runs with the user's Omarchy permissions.

## System tool identities and environment

QML invokes `/usr/bin/python3 -I`, clears inherited environment variables, and
passes only PATH=/usr/bin, LC_ALL=C, and the three required session variables
(XDG_RUNTIME_DIR, DBUS_SESSION_BUS_ADDRESS, WAYLAND_DISPLAY). Isolated Python
ignores Python environment overrides, the working directory, and user site packages.
Only explicit sibling files in this reviewed plugin are loaded as local modules.

`secure_runtime.py` selects executables from an allowlist of absolute `/usr/bin`
paths. Both the original and resolved paths and their ancestors must be
root-owned and not writable by group/others, and the target must be an executable
regular file. Distro-managed symlinks such as python3 -> python3.14 are supported.
Child processes receive a fresh allowlisted environment. Curl's first argument
is `--disable` so a user curlrc cannot add commands/options to the connectivity test.

The trust anchor is the root-maintained system installation and the reviewed
plugin checkout. These checks are not package signature verification and do not
defend against a compromised root administrator or edits by the same user who
owns and can replace the plugin. No additional privilege is granted to the panel.

## Private action lock

The runtime must be the canonical `/run/user/UID`. Every path component is opened
relative to its parent descriptor with O_DIRECTORY|O_NOFOLLOW; ancestors must be
root-owned and non-writable, and the final directory must belong to the user with
mode 0700. A conflicting XDG_RUNTIME_DIR is rejected. No directory is created in
/tmp, and a missing logind runtime is an error.

The lock is created using O_CREAT|O_EXCL|O_NOFOLLOW, mode 0600, relative to that
descriptor. An existing lock is opened without O_TRUNC, with O_NOFOLLOW and
O_NONBLOCK, then checked using fstat. It must be a singly linked regular file
owned by the user with mode 0600. Non-blocking flock provides mutual exclusion.
Lock files are not unlinked on release, avoiding replacement-inode races.

## Deadlines, descendants, and output caps

`launcher.py` creates a unique transient systemd **user service**, not a scope,
for each status/action. It uses Type=exec, TimeoutStartSec=5s, RuntimeMaxSec=20s
for status or 180s for actions, KillMode=control-group, TimeoutStopSec=2s,
SendSIGKILL=yes, and FinalKillSignal=SIGKILL. TasksMax=32, MemoryMax=128M, and
NoNewPrivileges=yes further constrain the worker. No installed user service or
privileged authorization helper is needed. An unavailable user manager is an error.

The relay monitors cancellation and drains stdout/stderr incrementally. Their
**combined raw byte limit is 131072**, before decoding. Exceeding it or the relay
deadline (worker limit plus 8 seconds) stops the unit. The JSON sent to QML is
also capped, including its newline. QML collectors therefore receive bounded
relay output. Each nested command has the same combined byte cap plus its own
timeout, and POSIX process-group TERM/KILL cleanup even after normal parent exit.

The cgroup boundary handles descendants that detach with setsid; it is
independent of the relay and remains active if the relay is killed. Cancellation
requests stop the unit; systemd owns the two-second escalation. QML's secondary
watchdogs send TERM at 30/190 seconds and KILL at 35/195 seconds if the relay has
not exited. They are not the primary cleanup mechanism.

Clipboard copying uses `wl-copy --foreground --paste-once` with a 60-second
deadline, so no daemon is intentionally left outside the action's lifetime.
Paste once within that time. Displayed diagnostics may contain local profile
IDs and addresses but exclude SIM identifiers and credentials.

## Optional root recovery installation

The ambient shell installer has been removed. Run the reviewed installer with
`/usr/bin/sudo /usr/bin/python3 -I recovery/install.py`; it requires isolated
Python and administrator privileges. Sources must be singly linked regular
files in non-symlink directories owned by root or the invoking sudo/pkexec user,
without group/other write access. No-follow descriptors snapshot the bounded
source contents before installation. The installer then clears its environment.

All privileged tool paths are checked before changes. There is no `install`,
shell, dirname, or PATH-based subprocess lookup. Destination directories are
opened one component at a time with O_DIRECTORY|O_NOFOLLOW and checked for root
ownership and non-writable permissions. Existing destination files must be
singly linked, root-owned regular files. Files are written to exclusive random
temporary names relative to the destination descriptor, fsynced, assigned their
mode, and atomically replaced with descriptor-relative rename. A racing final
symlink is replaced itself rather than followed. The fixed sleep-target symlink
is created and replaced relative to a validated directory descriptor as well.

Installed files live in `/usr/local/libexec/omarchy-modem-recovery/` and
`/etc/systemd/system/`. Recovery uses isolated Python and the same verified,
bounded subprocess runner. The system service also has cgroup cleanup and a
two-second escalation timeout. Hardware guards and one-reset limits remain in
place. Adding/updating the panel never installs this root component automatically.

## Regression tests

`MODEM_SYSTEMD_TESTS=1 bash scripts/validate.sh` runs the complete tests on an
Omarchy session. The security tests use disposable files and dummy processes;
they do not change modem state or install root services. Tests exercise hostile
PATH/environment values, unsafe runtime permissions, lock path attacks and
content preservation, output floods, cancellation, SIGTERM-resistant children,
detached descendants, killed clients, and installer symlink/race handling.

The marketplace maintainer must review the new exact commit. Passing these
tests does not itself constitute marketplace security approval.
