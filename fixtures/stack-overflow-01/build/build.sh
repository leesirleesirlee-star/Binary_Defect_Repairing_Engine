#!/bin/sh
# Exact MVP2 fixture recipe. Must run on Linux x86-64 with gcc and ld.
set -eu
cd "$(dirname "$0")"

gcc -O0 -g0 -fno-stack-protector -fno-pie -no-pie -fno-builtin \
    -m64 -Wall -Wextra -Wl,-z,noexecstack -Wl,--build-id=none \
    -o ../vuln.elf vuln.c

# Keep the generated PLT stubs name-resolvable for readelf/objdump. This adds
# symbol-table aliases only; it does not add code or change a byte in .text.
tmp=../.vuln.elf.symbols
objcopy --add-symbol 'strcpy@plt=.plt.sec:0x0' \
        --add-symbol 'puts@plt=.plt.sec:0x10' \
        ../vuln.elf "$tmp"
mv "$tmp" ../vuln.elf
chmod +x ../vuln.elf 2>/dev/null || true
