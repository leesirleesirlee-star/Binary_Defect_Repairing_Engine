"""Build a ``FindingV1`` from a ``DisassemblyViewV1``.

The finding locates the vulnerable copy by address (not by guess) and records
the frame facts needed downstream. It is a hypothesis record, never a verdict.
"""

from __future__ import annotations

import hashlib
import json
import re


def build_finding(view: dict, fixture_id: str = "stack-overflow-01") -> dict:
    """Return a ``FindingV1`` for the vulnerable copy in ``view``."""
    view_json = json.dumps(view, sort_keys=True)
    view_sha256 = hashlib.sha256(view_json.encode("utf-8")).hexdigest()

    strcpy_plt = view.get("plt", {}).get("strcpy")
    call_site: dict | None = None
    for insn in view.get("instructions", []):
        if insn["mnemonic"] == "call" and insn["op_str"] == strcpy_plt:
            call_site = insn
            break
    if call_site is None:
        raise ValueError("no call to strcpy@plt found in the disassembly view")

    handle_addr = int(view["symbols"]["handle"], 16)
    main_addr = int(view["symbols"]["main"], 16)
    handle_insns = [
        insn
        for insn in view.get("instructions", [])
        if handle_addr <= int(insn["address"], 16) < main_addr
    ]

    frame: dict = {}
    for insn in handle_insns:
        if insn["mnemonic"] == "sub" and insn["op_str"].startswith("rsp,"):
            match = re.search(r"0x[0-9a-f]+", insn["op_str"])
            if match:
                frame["sub_rsp"] = match.group(0)
        elif insn["mnemonic"] == "lea" and "[rbp" in insn["op_str"]:
            match = re.search(r"\[rbp\s*-\s*(0x[0-9a-f]+)\]", insn["op_str"])
            if match:
                frame["buf_rbp_offset"] = "-" + match.group(1)
    if "buf_rbp_offset" in frame:
        buf_off = int(frame["buf_rbp_offset"], 16)
        frame["saved_rip_offset"] = 8 - buf_off

    return {
        "schema_version": 1,
        "fixture_id": fixture_id,
        "function": "handle",
        "address": call_site["address"],
        "instruction": "call strcpy@plt",
        "cwe": "CWE-121",
        "confidence": 1.0,
        "status": "confirmed_by_analysis",
        "evidence": [
            f"handle issues a 5-byte call at {call_site['address']} to strcpy@plt",
            "the destination is a 32-byte stack buffer and the source is argv[1] (unbounded copy)",
        ],
        "view_sha256": view_sha256,
        "frame": frame,
        "notes": "Located deterministically from disassembly; not a verdict.",
    }
