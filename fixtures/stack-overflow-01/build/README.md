# BUILD-ONLY

This directory holds `vuln.c` and `build.sh`. It exists so the binary can be
rebuilt and its provenance checked.

Analysis, AI, audit and repair code **must not read this directory**. The
disassembly view and the prompt contain no source path and no source text. A test
enforces the boundary.

Do not move the source next to the analysis code. Do not paste it into a prompt.
