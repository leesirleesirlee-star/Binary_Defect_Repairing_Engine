#!/bin/sh
# Exact MVP2 fixture recipe. Must run on Linux x86-64 with gcc and ld.
set -eu
cd "$(dirname "$0")"

gcc -O0 -g0 -fno-stack-protector -fno-pie -no-pie -fno-builtin \
    -m64 -Wall -Wextra -Wl,-z,noexecstack -Wl,--build-id=none \
    -o ../vuln.elf vuln.c

chmod +x ../vuln.elf 2>/dev/null || true
