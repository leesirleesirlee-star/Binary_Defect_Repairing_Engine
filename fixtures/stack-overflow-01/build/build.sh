#!/bin/sh
# Canonical fixture build: produces the exact freestanding ELF32 artifact.
# Needs only Python 3; no cross-compiler and no libc.
set -eu
cd "$(dirname "$0")"
python3 build_elf.py
chmod +x ../vuln.elf 2>/dev/null || true
