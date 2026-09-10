#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
install -d -m 755 /usr/local/libexec
install -o root -g root -m 755 recover.py /usr/local/libexec/xmm7360-recover
install -o root -g root -m 644 xmm7360-recover.service xmm7360-resume.service /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/xmm7360-recover.service /etc/systemd/system/xmm7360-resume.service
systemctl daemon-reload
systemctl enable xmm7360-resume.service
systemctl start --no-block xmm7360-recover.service
