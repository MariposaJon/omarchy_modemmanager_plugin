#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

omarchy plugin validate .
python -m unittest discover -s . -p test_modem.py -v
python -m unittest discover -s recovery -v
bash -n recovery/install.sh

modem_shell_path="${OMARCHY_PATH:-/usr/share/omarchy}/shell"
[[ -d "$modem_shell_path/Ui" ]] || { echo "Omarchy shell imports not found: $modem_shell_path" >&2; exit 1; }
modem_qmllint=$(command -v qmllint || true)
[[ -n "$modem_qmllint" ]] || modem_qmllint=/usr/lib/qt6/bin/qmllint
[[ -x "$modem_qmllint" ]] || { echo "Install qt6-declarative for qmllint." >&2; exit 1; }
modem_imports=$(mktemp -d)
trap 'rm -rf -- "$modem_imports"' EXIT
ln -s -- "$modem_shell_path" "$modem_imports/qs"
"$modem_qmllint" -I "$modem_imports" Panel.qml Service.qml SignalIcon.qml
echo "Manifest, backend tests, installer syntax, and QML lint passed."
