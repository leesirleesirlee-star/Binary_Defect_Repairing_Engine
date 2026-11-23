"""G4 end-to-end console flow: upload -> analysis -> repair contracts -> repair.

The GUI never imports a pipeline module: analysis and the repair stages run in
child processes through the same CLIs the runner uses, and this module only keeps
persisted task metadata and journal-backed facts.  It never computes a verdict
and never executes the uploaded ELF on this host.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app import fixture as fixture_snapshot_module
from app import tasks

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = ROOT / "var" / "uploads"
ARTIFACT_ROOT = ROOT / "var" / "artifacts"
TASK_ROOT = ROOT / "var" / "tasks"

FROZEN_FIXTURE_ID = "stack-overflow-01"
FROZEN_BINARY_SHA = "705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26"
FROZEN_PLAN = "docs/audit/fix-plan-v1.json"
OBSERVATIONS_EVIDENCE = "docs/plan/evidence/g3/observations-candidate-wsl2.json"

MAX_BINARY_BYTES = 32 * 1024 * 1024
MAX_CASE_FILES = 8
MAX_CASES = 200
ANALYSIS_TIMEOUT_S = 60


class G4Error(Exception):
    """A stable, displayable failure for the console; never a verdict."""

    def __init__(self, status: int, code: str, **extra: Any) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.extra = extra


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(value: Any, fallback: str) -> str:
    name = str(value or "").strip()
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(char for char in name if char.isprintable() and char not in {'"', "'"})
    return name[:120] or fallback


def _decode_files(raw: Any) -> list[dict[str, Any]]:
    """Validate uploaded case files from the browser (base64 JSON text files)."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_CASE_FILES:
        raise G4Error(422, "invalid_cases")
    files: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise G4Error(422, "invalid_cases")
        name = _safe_name(item.get("name"), "cases.txt")
        try:
            content = base64.b64decode(str(item.get("content_base64") or ""), validate=True)
        except (binascii.Error, ValueError) as error:
            raise G4Error(422, "invalid_cases") from error
        if len(content) > 1024 * 1024:
            raise G4Error(422, "cases_too_large")
        files.append({"name": name, "bytes": content, "sha256": _sha256_bytes(content)})
    return files


def _collect_cases(files: list[dict[str, Any]], defect: str) -> dict[str, Any]:
    valid: list[Any] = []
    poc: list[Any] = []
    for item in files:
        try:
            text = item["bytes"].decode("utf-8")
        except UnicodeDecodeError as error:
            raise G4Error(422, "cases_not_utf8") from error
        stem = item["name"].lower()
        parsed: Any = None
        if text.lstrip().startswith("{"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        if isinstance(parsed, dict):
            valid.extend(
                _case_list(parsed.get("valid") or parsed.get("regression") or parsed.get("correct"))
            )
            poc.extend(
                _case_list(
                    parsed.get("invalid")
                    or parsed.get("poc")
                    or parsed.get("crash")
                    or parsed.get("error")
                )
            )
        else:
            bucket = (
                poc if any(word in stem for word in ("poc", "invalid", "crash", "error")) else valid
            )
            bucket.extend(line for line in text.splitlines() if line.strip())
    valid = valid[:MAX_CASES]
    poc = poc[:MAX_CASES]
    return {
        "valid": valid,
        "poc": poc,
        "counts": {"valid": len(valid), "poc": len(poc), "total": len(valid) + len(poc)},
        "defect": defect[:500],
        "files": [
            {"name": item["name"], "sha256": item["sha256"], "bytes": len(item["bytes"])}
            for item in files
        ],
    }


def _case_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [
            item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, sort_keys=True)
            for item in value
        ][:MAX_CASES]
    return [str(value)]


def _decode_binary(raw: Any, name: Any) -> tuple[bytes, str]:
    try:
        data = base64.b64decode(str(raw or ""), validate=True)
    except (binascii.Error, ValueError) as error:
        raise G4Error(422, "invalid_binary") from error
    if not data:
        raise G4Error(422, "invalid_binary")
    if len(data) > MAX_BINARY_BYTES:
        raise G4Error(413, "binary_too_large")
    if data[:4] != b"\x7fELF":
        raise G4Error(422, "not_an_elf")
    return data, _safe_name(name, "uploaded.elf")


def analyze_binary(binary: Path, out_dir: Path) -> dict[str, Any]:
    """Run the deterministic analysis CLI in a child process (no import here)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pipeline.analyze",
        "--elf",
        str(binary),
        "--out-dir",
        str(out_dir),
    ]
    try:
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, timeout=ANALYSIS_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise G4Error(422, "analysis_failed", detail=error.__class__.__name__) from error
    if result.returncode != 0:
        raise G4Error(422, "analysis_failed", detail=result.returncode)
    finding_path = out_dir / "finding.json"
    view_path = out_dir / "disassembly.json"
    if not finding_path.is_file() or not view_path.is_file():
        raise G4Error(422, "analysis_failed", detail="missing artifacts")
    try:
        finding = json.loads(finding_path.read_text(encoding="utf-8"))
        view = json.loads(view_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise G4Error(422, "analysis_failed", detail="unreadable artifacts") from error
    return {
        "finding": finding,
        "view": view,
        "finding_sha256": _sha256_bytes(finding_path.read_bytes()),
        "view_sha256": _sha256_bytes(view_path.read_bytes()),
    }


def _frame_buffer_bytes(finding: dict[str, Any]) -> int | None:
    frame = finding.get("frame")
    if not isinstance(frame, dict):
        return None
    offset = frame.get("buf_rbp_offset")
    try:
        value = int(str(offset), 16)
    except (TypeError, ValueError):
        return None
    return abs(value) if value else None


def build_plans(finding: dict[str, Any], supported: bool) -> list[dict[str, Any]]:
    """Derive the selectable repair contracts from the deterministic finding."""
    function = str(finding.get("function") or "target")
    address = str(finding.get("address") or "?")
    instruction = str(finding.get("instruction") or "the vulnerable call")
    cwe = str(finding.get("cwe") or "CWE-121")
    buffer_bytes = _frame_buffer_bytes(finding)
    evidence = [str(item) for item in (finding.get("evidence") or [])][:3]
    facts = {
        "function": function,
        "address": address,
        "instruction": instruction,
        "cwe": cwe,
        "buffer_bytes": buffer_bytes,
        "evidence": evidence,
    }
    unsupported = not supported
    return [
        {
            "id": "guard_trampoline",
            "strategy": "trampoline_guard",
            "title_zh": "方案 A · 尾部守卫跳板（推荐）",
            "title_en": "Plan A · trampoline guard (recommended)",
            "summary_zh": (
                f"把 {function} 中 {address} 的 {instruction} 重定向到保留代码尾部的守卫桩："
                f"长度 ≤ {buffer_bytes or '缓冲'} 字节且为可打印 ASCII 时原样放行，"
                "否则输出固定错误并以状态 1 退出。"
            ),
            "summary_en": (
                f"Redirect the {instruction} at {address} in {function} to a guard stub in "
                f"the reserved code tail: pass through valid input up to "
                f"{buffer_bytes or 'the buffer'} bytes, otherwise write the fixed error "
                "and exit 1."
            ),
            "scope_zh": "仅替换该调用点的 5 字节 rel32 调用，不移动既有函数体；"
            "守卫桩位于预留可执行尾部。",
            "scope_en": "Only the 5-byte rel32 call at the site is redirected; the stub lives "
            "in the reserved executable tail.",
            "feasible": not unsupported,
            "reason_code": "unsupported_binary_scope" if unsupported else None,
            "reason_zh": (
                "当前构建的修复器只对冻结 fixture（SHA-256 "
                f"{FROZEN_BINARY_SHA[:8]}…）签名应用；其他二进制先只做分析，不写入补丁。"
                if unsupported
                else None
            ),
            "reason_en": (
                "This build only applies signed repairs to the frozen fixture "
                f"(SHA-256 {FROZEN_BINARY_SHA[:8]}…); other binaries are analyzed only."
                if unsupported
                else None
            ),
            "plan_path": FROZEN_PLAN if not unsupported else None,
            "facts": facts,
        },
        {
            "id": "inline_length_check",
            "strategy": "inline_length_check",
            "title_zh": "方案 B · 调用点内联长度检查",
            "title_en": "Plan B · inline length check at the call site",
            "summary_zh": (
                f"在 {address} 前插入长度比较与分支；但该调用点前没有足够空闲字节容纳检查代码，"
                "需要移动既有指令，超出允许的编辑范围。"
            ),
            "summary_en": (
                f"Insert a length test before the call at {address}; the site has no spare "
                "bytes for the check without moving existing instructions, outside the "
                "allowed edit region."
            ),
            "scope_zh": "内联重写调用点前指令序列（未获批准的可编辑区）。",
            "scope_en": "Inline rewrite of the instruction sequence before the call (outside the "
            "approved editable region).",
            "feasible": False,
            "reason_code": "insufficient_code_space",
            "reason_zh": "调用点空间不足，需重排代码，超出 MVP2 的可编辑范围。",
            "reason_en": "No spare bytes at the call site; rewiring exceeds the MVP2 edit budget.",
            "plan_path": None,
            "facts": facts,
        },
        {
            "id": "entry_reject",
            "strategy": "entry_reject",
            "title_zh": "方案 C · 入口处提前拒绝超长输入",
            "title_en": "Plan C · reject overlong input at entry",
            "summary_zh": (
                f"在 {function} 入口检查 argv 输入长度并提前退出；这需要搬移参数解析逻辑，"
                "且会改变现有合法用例的行为，契约风险高。"
            ),
            "summary_en": (
                f"Reject overlong argv input at {function}'s entry; this requires relocating "
                "argument parsing and changes currently valid behaviour, a high contract "
                "risk."
            ),
            "scope_zh": "函数入口重写与参数解析搬移（未批准）。",
            "scope_en": "Entry rewrite and argument-parsing relocation (not approved).",
            "feasible": False,
            "reason_code": "behaviour_change_risk",
            "reason_zh": "会改变合法输入行为，可能引入回归，不能作为本契约的修复方案。",
            "reason_en": "Changes valid-input behaviour and risks regressions; not applicable "
            "to this contract.",
            "plan_path": None,
            "facts": facts,
        },
    ]


def create_task(
    *, binary_name: Any, binary_base64: Any, case_files: Any, defect: Any = ""
) -> dict[str, Any]:
    """Store the uploads, analyze the ELF, and persist the task with its contracts."""
    data, name = _decode_binary(binary_base64, binary_name)
    files = _decode_files(case_files)
    cases = _collect_cases(files, str(defect or ""))
    binary_sha = _sha256_bytes(data)
    supported = binary_sha == FROZEN_BINARY_SHA
    task_id = "tsk_" + hashlib.sha256((binary_sha + str(time.time())).encode()).hexdigest()[:24]
    upload_dir = UPLOAD_ROOT / task_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    binary_path = upload_dir / "binary.elf"
    binary_path.write_bytes(data)
    cases_path = upload_dir / "cases.json"
    cases_path.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    analysis = analyze_binary(binary_path, upload_dir / "analysis")
    plans = build_plans(analysis["finding"], supported)

    if supported:
        frozen = fixture_snapshot_module.snapshot()
        task: dict[str, Any] = {
            "id": task_id,
            "fixture_id": FROZEN_FIXTURE_ID,
            "phase": "plans_ready",
            "demo": False,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "contract": frozen["contract"],
            "contract_revision": frozen["contract_revision"],
            "contract_sha256": frozen["contract_sha256"],
            "corpus": frozen["corpus"],
            # The uploaded bytes match the frozen fixture by SHA-256 above, so the
            # runner resolves the signed fixture path; the upload is kept as evidence.
            "binary": frozen["binary"],
            "review_binding_digest": frozen["review_binding_digest"],
            "approval": {"approved": False},
            "execution": {"run_id": None, "status": "idle", "terminal": False, "reason_code": None},
            "idempotency": {},
            "plan": None,
            "g4": {
                "supported": True,
                "binary_name": name,
                "binary_sha256": binary_sha,
                "cases": {key: cases[key] for key in ("counts", "defect", "files")},
                "finding": analysis["finding"],
                "finding_sha256": analysis["finding_sha256"],
                "view_sha256": analysis["view_sha256"],
                "options": plans,
                "selected_option": None,
            },
        }
        # Stage M3's guest observations before the run; the runner never executes
        # the ELF and verify only reads this persisted observation file.
        observations_src = ROOT / OBSERVATIONS_EVIDENCE
        if observations_src.is_file():
            artifact_dir = ARTIFACT_ROOT / task_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "observations-candidate.json").write_bytes(
                observations_src.read_bytes()
            )
    else:
        task = {
            "id": task_id,
            "fixture_id": f"upload-{binary_sha[:8]}",
            "phase": "unsupported",
            "demo": False,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "contract": {},
            "contract_revision": 0,
            "contract_sha256": None,
            "corpus": {},
            "binary": {
                "path": binary_path.relative_to(ROOT).as_posix(),
                "sha256": binary_sha,
                "size": len(data),
            },
            "review_binding_digest": hashlib.sha256(
                (binary_sha + cases_path.read_text(encoding="utf-8")).encode()
            ).hexdigest(),
            "approval": {"approved": False},
            "execution": {"run_id": None, "status": "idle", "terminal": False, "reason_code": None},
            "idempotency": {},
            "plan": None,
            "g4": {
                "supported": False,
                "binary_name": name,
                "binary_sha256": binary_sha,
                "cases": {key: cases[key] for key in ("counts", "defect", "files")},
                "finding": analysis["finding"],
                "finding_sha256": analysis["finding_sha256"],
                "view_sha256": analysis["view_sha256"],
                "options": plans,
                "selected_option": None,
            },
        }
    tasks.update(task)
    return {
        "task": _public_task(task),
        "analysis": analysis["finding"],
        "plans": plans,
        "supported": supported,
    }


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in task.items() if key not in {"idempotency"}}


def get_task_g4(task_id: str) -> dict[str, Any]:
    task = _task(task_id)
    g4 = task.get("g4") or {}
    return {
        "task_id": task_id,
        "fixture_id": task.get("fixture_id"),
        "phase": task.get("phase"),
        "supported": bool(g4.get("supported")),
        "binary_name": g4.get("binary_name"),
        "binary_sha256": g4.get("binary_sha256"),
        "cases": g4.get("cases") or {},
        "finding": g4.get("finding") or {},
        "options": g4.get("options") or [],
        "selected_option": g4.get("selected_option"),
    }


def select_option(task_id: str, option_id: Any) -> dict[str, Any]:
    task = _task(task_id)
    g4 = task.get("g4") or {}
    options = g4.get("options") or []
    option = next((item for item in options if item.get("id") == str(option_id or "")), None)
    if option is None:
        raise G4Error(422, "unknown_option")
    if not option.get("feasible"):
        raise G4Error(
            409,
            "option_not_implementable",
            reason_code=option.get("reason_code") or "not_implementable",
            reason_zh=option.get("reason_zh"),
            reason_en=option.get("reason_en"),
        )
    if not g4.get("supported"):
        raise G4Error(409, "unsupported_binary_scope")
    g4["selected_option"] = option["id"]
    task["g4"] = g4
    task["phase"] = "plan_selected"
    task["plan"] = option.get("plan_path") or FROZEN_PLAN
    tasks.update(task)
    return {"task": _public_task(task), "option": option}


def _task(task_id: str) -> dict[str, Any]:
    try:
        return tasks.get(task_id)
    except KeyError as error:
        raise G4Error(404, "task_not_found") from error
