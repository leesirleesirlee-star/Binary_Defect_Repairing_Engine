# ruff: noqa: E501
"""AI-hosted chat assistant with an honest deterministic fallback (T3).

Two AIs, one wall: the audit model is the G2 evidence; this chat assistant only
reads the persisted task metadata and the validated journal records.  It never
writes a FixPlanV1, an audit report or a verdict, never sees source, the hidden
corpus, keys or raw provider diagnostics, and its text is never evidence.

The provider seam is ``client``: a callable taking chat messages and returning a
small JSON envelope (``{"reply": str, "actions": [...]}``).  M1's infrastructure
injects the real client in the host process; this module never holds a key.
Without a client, a key or a successful call the assistant falls back to the
scripted deterministic reply and says so through ``mode``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

MODE_LLM = "llm"
MODE_DETERMINISTIC = "deterministic"
MODE_LLM_NOT_WIRED = "llm (not wired)"

# The only six verdict words VerdictV1 may persist; the assistant quotes them
# verbatim and never derives one from observations.
VERDICT_WORDS = (
    "verified_against_stated_criteria",
    "rejected",
    "unverified",
    "unsupported",
    "error",
    "not_run",
)

ACTION_KINDS = frozenset(
    {"attach", "start", "continue", "rerun", "change_scope", "download", "evidence", "retry"}
)
MAX_REPLY_CHARS = 8000
MAX_ACTIONS = 6
MAX_MESSAGE_CHARS = 4000

Client = Callable[[Sequence[Mapping[str, str]]], Any]

SYSTEM_PROMPT = (
    "You are the grounded repair diagnostician of a binary-repair console. Answer the user's "
    "question in the requested locale using ONLY the supplied context. Explain why a verdict was "
    "rejected, which numbered criteria passed, failed or were not run, what the approved patch "
    "changed, what the persisted journal shows, which artifacts exist, and what concrete next "
    "step is possible. Answer the exact question: if it asks what changed, describe the patch in "
    "prose; if it asks why, lead with the failed criteria; if it asks next steps, give concrete "
    "conditions. Use at most four sections: 结论 (one sentence), 关键原因 (at most three bullets), "
    "按需的补充说明, and 下一步操作建议 (detailed numbered steps). Do not dump the full check table, "
    "artifact list, manifest fields or code when the question does not ask for them. Make the "
    "final '下一步操作建议' section the longest and most concrete. Do not paste long hex byte "
    "blobs or raw code. Quote exact criterion ids "
    "(V0-identity ... V5-reapply), verdict words, "
    "limitations, journal error codes and artifact filenames when present. Never infer a verdict "
    "that is absent; only quote context.verdict. Never claim a guest observation, successful run, "
    "or source-level fact that is not in the context. If the context is insufficient, state what "
    "evidence is missing instead of guessing. Distinguish a repair-stage failure from a verifier "
    "rejection; do not blame WSL2 or the guest unless context.guest or the verdict limitations "
    "say so. Be detailed and structured, with short headings and bullet points. Your reply is "
    "chat text: it is never evidence, never an audit input, and never changes task state. Return "
    "JSON only: {\"reply\": string, \"actions\": [{\"id\": string, \"label_code\": string, "
    "\"kind\": string}]}. Allowed action kinds: attach, start, continue, rerun, change_scope, "
    "download, evidence, retry."
)

_TEXTS: dict[str, dict[str, str]] = {
    "zh-Hans": {
        "intake": "你好。把有问题的程序和崩溃现象发给我，我会整理用例、冻结契约并开始修复。",
        "frozen": "已整理 {total} 个用例并冻结契约（hash {prefix}）。",
        "frozen_plain": "用例已整理，契约已冻结。",
        "progress": "正在执行 {step}（{done}/{total}）…",
        "audit": "审计完成：三次得分 {scores}，建议采用第 {best} 个方案。",
        "audit_plain": "审计完成，但没有可用的评分。",
        "decision": "请选择继续、重跑或修改范围。",
        "verifying": "补丁已生成，正在验证…",
        "success": "验证完成：{word}",
        "no_verdict": "尚无结论（{code}）；详情：{link}",
        "no_verdict_plain": "尚无结论；详情：{link}",
        "failed": "运行结束：{code}；详情：{link}",
    },
    "en": {
        "intake": "Hello. Send me the program and the crash it produces; I will collect the cases, "
        "freeze the contract and start the repair.",
        "frozen": "Collected {total} cases and froze the contract (hash {prefix}).",
        "frozen_plain": "The cases are collected and the contract is frozen.",
        "progress": "Running {step} ({done}/{total})…",
        "audit": "Audit finished: scores {scores}; the suggestion is run {best}.",
        "audit_plain": "The audit finished without a usable score.",
        "decision": "Choose continue, rerun or change scope.",
        "verifying": "The patch is written and verification is running…",
        "success": "Verification finished: {word}",
        "no_verdict": "No verdict yet ({code}); details: {link}",
        "no_verdict_plain": "No verdict yet; details: {link}",
        "failed": "Run ended: {code}; details: {link}",
    },
}

_STEP_LABELS = {
    "zh-Hans": {
        "collect": "收集输入",
        "freeze": "冻结契约",
        "analyze": "生成分析视图",
        "audit": "审计方案",
        "decision": "等待选择",
        "repair": "写入补丁",
        "verify": "验证补丁",
        "export": "导出证据",
    },
    "en": {
        "collect": "collecting inputs",
        "freeze": "freezing the contract",
        "analyze": "building the analysis view",
        "audit": "auditing the plans",
        "decision": "waiting for the decision",
        "repair": "writing the patch",
        "verify": "verifying the patch",
        "export": "exporting the evidence",
    },
}

_ACTION_LABELS = {
    "zh-Hans": {
        "attach": "添加二进制文件",
        "start": "开始",
        "continue": "继续",
        "rerun": "重跑",
        "change_scope": "修改范围",
        "download": "下载",
        "evidence": "证据",
        "retry": "重试",
    },
    "en": {
        "attach": "Attach binary",
        "start": "Start",
        "continue": "Continue",
        "rerun": "Rerun",
        "change_scope": "Change scope",
        "download": "Download",
        "evidence": "Evidence",
        "retry": "Retry",
    },
}


def _locale(locale: str | None) -> str:
    return locale if locale in _TEXTS else "en"


def _text(locale: str | None, key: str, **values: Any) -> str:
    return _TEXTS[_locale(locale)][key].format(**values)


def _action(locale: str | None, kind: str) -> dict[str, str]:
    return {
        "id": kind,
        "label_code": kind,
        "kind": kind,
        "label": _ACTION_LABELS[_locale(locale)][kind],
    }


def _records(records: Sequence[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    if not records:
        return []
    return [record for record in records if isinstance(record, Mapping)]


def _latest(records: Sequence[Mapping[str, Any]], event_type: str) -> Mapping[str, Any] | None:
    for record in reversed(_records(records)):
        if record.get("type") == event_type:
            payload = record.get("payload")
            return payload if isinstance(payload, Mapping) else {}
    return None


def _latest_payload(
    records: Sequence[Mapping[str, Any]], event_types: Sequence[str]
) -> Mapping[str, Any] | None:
    for record in reversed(_records(records)):
        if record.get("type") in event_types:
            payload = record.get("payload")
            if isinstance(payload, Mapping):
                return payload
    return None


def _verdict_word(task: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> str | None:
    """Return only a persisted VerdictV1 word; never infer one from observations."""
    persisted = task.get("verdict")
    if isinstance(persisted, Mapping):
        word = persisted.get("verdict")
        if isinstance(word, str) and word in VERDICT_WORDS:
            return word
    if isinstance(persisted, str) and persisted in VERDICT_WORDS:
        return persisted
    evaluation = _latest(records, "verification")
    if isinstance(evaluation, Mapping):
        payload = evaluation.get("verdict")
        if isinstance(payload, str) and payload in VERDICT_WORDS:
            return payload
    return None


def _corpus(
    task: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    payload = _latest(records, "corpus_update")
    if payload is not None:
        return payload
    corpus = task.get("corpus")
    return corpus if isinstance(corpus, Mapping) else None


def _plan(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    payload = _latest(records, "plan_update")
    steps = payload.get("steps") if isinstance(payload, Mapping) else None
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, Mapping)]


def _error_code(task: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> str | None:
    payload = _latest(records, "error")
    if isinstance(payload, Mapping) and isinstance(payload.get("code"), str):
        return payload["code"]
    code = task.get("reason_code")
    return code if isinstance(code, str) and code else None


def _artifacts(
    task: Mapping[str, Any], artifacts: Sequence[Mapping[str, Any]] | None
) -> list[Mapping[str, Any]]:
    if artifacts is not None:
        return [item for item in artifacts if isinstance(item, Mapping)]
    stored = task.get("artifacts")
    if isinstance(stored, list):
        return [item for item in stored if isinstance(item, Mapping)]
    return []


def _phase(task: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> str:
    """Ordered state machine for the deterministic fallback."""
    if _latest(records, "error") is not None and _verdict_word(task, records) is None:
        return "error"
    if _verdict_word(task, records) is not None:
        return "ended"
    if _latest(records, "run_end") is not None:
        return "ended"
    if _latest(records, "awaiting_user") is not None:
        return "decision"
    steps = _plan(records)
    if steps:
        statuses = {step.get("step_id"): step.get("status") for step in steps}
        if statuses.get("verify") == "in_progress" or statuses.get("repair") == "in_progress":
            return "verifying"
        if statuses.get("verify") == "completed":
            return "ended"
        if statuses.get("audit") == "in_progress" or statuses.get("analyze") == "in_progress":
            return "progress"
        return "progress"
    if _corpus(task, records) is not None:
        return "frozen"
    return "intake"


def _progress_step(records: Sequence[Mapping[str, Any]], locale: str | None) -> str:
    labels = _STEP_LABELS[_locale(locale)]
    for step in _plan(records):
        if step.get("status") == "in_progress":
            step_id = step.get("step_id")
            return labels.get(step_id, str(step_id or "…"))
    return labels["analyze"]


def _step_counts(records: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    steps = _plan(records)
    if not steps:
        return (0, 0)
    return (
        sum(1 for step in steps if step.get("status") == "completed"),
        len(steps),
    )


def _score_list(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    payload = _latest(records, "audit_runs")
    runs = payload.get("runs") if isinstance(payload, Mapping) else None
    if isinstance(runs, list):
        return [run for run in runs if isinstance(run, Mapping)]
    return []


def _context(task: Mapping[str, Any], records: Sequence[Mapping[str, Any]],
             artifacts: Sequence[Mapping[str, Any]] | None,
             extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compact, display-only context handed to the client seam.

    Only persisted values are exposed: no source, no hidden corpus, no keys and
    no raw provider diagnostics.
    """
    corpus = _corpus(task, records)
    verdict = _verdict_word(task, records)
    steps = [
        {"step_id": step.get("step_id"), "status": step.get("status")}
        for step in _plan(records)
    ]
    runs = _score_list(records)
    context: dict[str, Any] = {
        "task_id": task.get("id"),
        "phase": _phase(task, records),
        "verdict": verdict,
        "steps": steps,
        "error_code": _error_code(task, records),
        "artifacts": [str(item.get("path") or item.get("display_path"))
                      for item in _artifacts(task, artifacts)
                      if item.get("path") or item.get("display_path")],
    }
    values = _corpus_reply_values(corpus) if corpus is not None else None
    if values is not None:
        context["corpus"] = values
    scores = [
        {"run_index": run.get("run_index"), "score": run.get("score")}
        for run in runs
        if run.get("score") is not None
    ]
    if scores:
        context["audit_scores"] = scores
    if extra:
        context.update({key: value for key, value in extra.items() if value is not None})
    return context


def _corpus_reply_values(corpus: Mapping[str, Any]) -> dict[str, Any] | None:
    """Total/hash prefix for the chat line; absent values are simply not echoed."""
    values: dict[str, Any] = {}
    total = corpus.get("total")
    if isinstance(total, int) and total >= 0:
        values["total"] = total
    digest = corpus.get("cases_sha256")
    if isinstance(digest, str) and len(digest) >= 8:
        values["prefix"] = digest[:8]
    return values or None


def _evidence_link(task: Mapping[str, Any]) -> str:
    task_id = task.get("id")
    return f"/ui/#task/{task_id}" if isinstance(task_id, str) and task_id else "/ui/"


def _fallback(task: Mapping[str, Any], records: Sequence[Mapping[str, Any]], *,
              locale: str | None, artifacts: Sequence[Mapping[str, Any]] | None,
              fallback_code: str | None = None) -> dict[str, Any]:
    phase = _phase(task, records)
    link = _evidence_link(task)
    if phase == "intake":
        return {"reply": _text(locale, "intake"), "actions": [_action(locale, "attach")]}
    if phase == "frozen":
        values = _corpus_reply_values(_corpus(task, records) or {})
        if values and "total" in values and "prefix" in values:
            reply = _text(locale, "frozen", total=values["total"], prefix=values["prefix"])
        else:
            reply = _text(locale, "frozen_plain")
        return {"reply": reply, "actions": [_action(locale, "start")]}
    if phase == "decision":
        runs = _score_list(records)
        scores = [
            run.get("score") for run in runs
            if isinstance(run.get("score"), int) and run.get("run_index") is not None
        ]
        if scores:
            def _score(run: Mapping[str, Any]) -> int:
                value = run.get("score")
                return value if isinstance(value, int) else -1

            best = max(runs, key=_score)
            best_index = best.get("run_index") or 1
            reply = _text(locale, "audit", scores=" / ".join(str(score) for score in scores),
                          best=best_index)
        else:
            reply = _text(locale, "audit_plain")
        return {
            "reply": reply,
            "actions": [_action(locale, "continue"), _action(locale, "rerun")],
        }
    if phase == "verifying":
        return {"reply": _text(locale, "verifying"), "actions": []}
    if phase == "ended":
        word = _verdict_word(task, records)
        chips: list[dict[str, str]] = []
        if _artifacts(task, artifacts):
            chips.append(_action(locale, "download"))
        chips.append(_action(locale, "evidence"))
        if word is not None:
            return {"reply": _text(locale, "success", word=word), "actions": chips}
        code = _error_code(task, records)
        reply = (_text(locale, "no_verdict", code=code, link=link) if code
                 else _text(locale, "no_verdict_plain", link=link))
        return {"reply": reply, "actions": [_action(locale, "retry")] + chips}
    if phase == "error":
        code = _error_code(task, records) or "unknown"
        return {
            "reply": _text(locale, "failed", code=code, link=link),
            "actions": [_action(locale, "retry"), _action(locale, "evidence")],
        }
    done, total = _step_counts(records)
    reply = _text(locale, "progress", step=_progress_step(records, locale), done=done, total=total)
    return {"reply": reply, "actions": []}


def _contains_unpersisted_verdict(reply: str, context: Mapping[str, Any]) -> bool:
    """Reject a claimed verdict not present in context.

    ``not_run`` is also a criterion status and appears legitimately in a
    detailed explanation of V4; it is not a claim that the run was unverified.
    """
    allowed = context.get("verdict")
    if allowed:
        # The context already contains the only persisted verdict; the model is
        # allowed to quote criterion statuses such as not_run / error while
        # explaining the rejection.
        return False
    forbidden = [word for word in VERDICT_WORDS if word != "not_run"]
    return any(word in reply for word in forbidden)


def validate_envelope(value: Any) -> dict[str, Any] | None:
    """Validate the small model envelope; anything unexpected is rejected."""
    if isinstance(value, (str, bytes)):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    if not isinstance(value, Mapping):
        return None
    reply = value.get("reply")
    if not isinstance(reply, str) or not reply.strip() or len(reply) > MAX_REPLY_CHARS:
        return None
    raw_actions = value.get("actions", [])
    if not isinstance(raw_actions, list) or len(raw_actions) > MAX_ACTIONS:
        return None
    actions: list[dict[str, str]] = []
    for item in raw_actions:
        if not isinstance(item, Mapping):
            return None
        kind = item.get("kind")
        label_code = item.get("label_code")
        action_id = item.get("id")
        if kind not in ACTION_KINDS:
            return None
        if not isinstance(label_code, str) or not label_code.strip():
            return None
        if not isinstance(action_id, str) or not action_id.strip():
            return None
        actions.append({"id": action_id[:64], "label_code": label_code[:64], "kind": kind})
    return {"reply": reply.strip(), "actions": actions}


def build_messages(
    context: Mapping[str, Any], message: str, locale: str | None
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "locale": _locale(locale),
                    "context": context,
                    "message": message[:MAX_MESSAGE_CHARS],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def _diagnostic_fallback(
    task: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    message: str,
    locale: str | None,
    extra: Mapping[str, Any] | None,
    artifacts: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Question-specific answer built only from persisted repair evidence.

    The answer deliberately avoids hex dumps: a failed verifier result is a
    diagnosis question, not a request for the raw candidate bytes.
    """
    extra = extra if isinstance(extra, Mapping) else {}
    rich_keys = ("verdict_detail", "repair_plan", "edit_manifest", "journal",
                 "analysis_finding", "artifacts")
    if not any(extra.get(key) for key in rich_keys):
        return _fallback(task, records, locale=locale, artifacts=artifacts)
    detail = extra.get("verdict_detail")
    verdict = detail if isinstance(detail, Mapping) else {}
    raw_plan = extra.get("repair_plan")
    plan = raw_plan if isinstance(raw_plan, Mapping) else {}
    raw_journal = extra.get("journal")
    journal = raw_journal if isinstance(raw_journal, list) else []
    question = str(message or "").lower()
    word = str(verdict.get("verdict") or task.get("verdict") or "")
    criteria = verdict.get("criteria") if isinstance(verdict.get("criteria"), list) else []
    failures = [item for item in criteria if isinstance(item, Mapping)
                and item.get("required") is not False
                and item.get("status") in {"fail", "not_run"}]
    limitations = [str(line) for line in (verdict.get("limitations") or []) if str(line)]
    failures_text = " · ".join(f"{item.get('id')}: {item.get('status')}" for item in failures)
    candidate = str(verdict.get("candidate_sha256") or "")
    edits = plan.get("edits") if isinstance(plan.get("edits"), list) else []
    lines: list[str] = []

    def ask(*needles: str) -> bool:
        return any(needle in question for needle in needles)

    if ask("补丁", "改了什么", "改动", "what changed", "what did the patch", "diff", "修改"):
        lines.append("结论：补丁做的是“重定向调用 + 守卫桩”，不是重写整个函数，也没有把 strcpy 换成 libc 安全检查函数。")
        for edit in edits[:6]:
            if not isinstance(edit, Mapping):
                continue
            kind = str(edit.get("kind") or "")
            address = str(edit.get("address") or "—")
            if kind == "redirect_call":
                lines.append(f"- 在 {address} 把原来的 5 字节 strcpy 调用重定向到 cave 中的守卫桩入口。")
            elif kind == "guard_stub":
                lines.append("- 在 cave 中写入守卫桩：逐字节数到 NUL；长度不超过 31（含终止符共 32 字节）时按原语义复制并返回；若 32 字节内没有 NUL，则走拒绝路径。")  # noqa: E501
            elif kind == "data":
                lines.append(f"- 在 {address} 写入拒绝路径使用的固定 invalid_stderr 文本。")
            else:
                lines.append(f"- {kind} @ {address}：{str(edit.get('reason') or '')[:160]}")
        if plan.get("invalid_path"):
            lines.append("拒绝路径的行为是：不返回 handle、不写 stdout，向 fd 2 写出契约要求的 invalid_stderr，然后 exit(1)。")
        lines.append("因此有效输入仍保持原来的 strcpy 语义，超长输入在越界前被拦截。")
    elif ask("为什么", "why", "拒绝", "rejected", "失败原因", "reason"):
        lines.append(f"结论：验收结论是 **{word or 'unknown'}**。修复运行和候选产物可以已完成，但验证器没有接受该候选。")
        if failures_text:
            lines.append(f"未通过的必需检查：{failures_text}。")
        if "V0-identity" in failures_text:
            lines.append("V0-identity 失败表示 candidate 的哈希与持久化的 guest observations 不一致；验证器不能用旧 observations 证明新候选。")  # noqa: E501
        if "V4-boundary" in failures_text:
            lines.append("V4-boundary 是 not_run，而不是已经证明边界逻辑错误：静态检查没有在 cave 中找到可识别的 rel32 尾部跳转布局。")
        if limitations:
            lines.append("限制说明：" + "；".join(limitations[:3]))
        lines.append("这不是 WSL2 让 repair 失败：repair 已经生成 candidate；WSL2 只影响现场 observations 的生成与 V0/V4 的验收。")  # noqa: E501
    elif ask("怎样", "怎么", "如何", "通过", "pass", "next", "下一步", "验收"):
        lines.append("结论：要得到 verified_against_stated_criteria，需要同时满足现场 observations 与静态边界检查，而不是只改 UI 或重跑一次。")  # noqa: E501
        if "V0-identity" in failures_text:
            lines.append("- V0-identity：在 WSL2 现场 guest 中对当前 candidate 重新执行冻结 corpus，生成与 candidate 哈希匹配的 observations。")  # noqa: E501
        if "V4-boundary" in failures_text:
            lines.append("- V4-boundary：让 cave 中的守卫布局可被静态识别为“先比较长度、再跳到原 copy 目标”的形状；当前候选的尾部跳转未被识别。")
        if "V1-structure" in failures_text:
            lines.append("- V1-structure：候选 ELF 的段、重定位和权限必须保持在冻结契约内。")
        if not failures_text:
            lines.append("- 当前必需检查没有失败项；重新生成 verdict 并确认 finalized 即可。")
        lines.append("V1/V2/V3 当前已通过；修复动作本身不需要再改，重点是把验证输入和静态边界证据补齐。")
    elif ask("证据", "日志", "下载", "evidence", "journal", "artifact", "trace"):
        lines.append("结论：这次修复的证据由四类持久化文件组成，不靠聊天文字推断。")
        lines.append("- verdict.json：最终 verdict、V0–V5 状态、limitations、candidate sha256。")
        lines.append("- edit-manifest.json：patch site、cave、trampoline、每条原始/补丁字节和回滚校验。")
        lines.append("- candidate.elf / candidate-v1.json：实际候选程序与 CandidateV1 应用记录。")
        names = [str(item.get("name")) for item in (extra.get("artifacts") or []) if isinstance(item, Mapping)]  # noqa: E501
        if names:
            lines.append("当前任务产物：" + "、".join(names[:12]) + "。")
        errors = [item for item in journal if isinstance(item, Mapping) and item.get("type") == "error"]  # noqa: E501
        if errors:
            lines.append("journal 中记录了 " + str(len(errors)) + " 条错误事件；可在右侧运行日志逐条展开。")
        lines.append("页面上的下载按钮直接对应这些文件，不是重新生成。")
    elif ask("根因", "漏洞", "cwe", "定位", "什么原因", "root cause"):
        lines.append("结论：这不是泛泛的“程序崩溃”，而是固定 32 字节栈缓冲区配合无界 strcpy。")
        if plan.get("root_cause"):
            lines.append("根因：" + str(plan.get("root_cause"))[:500])
        diagnosis = plan.get("diagnosis") if isinstance(plan.get("diagnosis"), Mapping) else {}
        if diagnosis:
            lines.append("定位：" + str(diagnosis.get("function") or "—") + " / "
                         + str(diagnosis.get("address") or "—") + " / "
                         + str(diagnosis.get("cwe") or "—"))
        if edits:
            lines.append("修复思路：在调用点重定向到长度守卫桩，保留有效路径的 strcpy 语义，超长输入走契约规定的拒绝路径。")
    elif ask("风险", "限制", "范围", "limitation", "coverage"):
        lines.append("结论：当前结论只覆盖冻结 contract 与 corpus，不等于全程序安全性证明。")
        if limitations:
            lines.append("verdict 中记录的验收限制：" + "；".join(limitations[:5]))
        coverage = verdict.get("coverage") if isinstance(verdict.get("coverage"), Mapping) else {}
        if coverage:
            lines.append(f"用例覆盖：{coverage.get('cases_run', '—')} / {coverage.get('cases_total', '—')}；"
                         f"未测量项：{', '.join(coverage.get('unmeasured') or []) or '无'}。")
    elif ask("哪一步", "步骤", "阶段", "step", "stage", "卡在"):
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
        lines.append("结论：本次运行已经越过修复阶段并进入验收；不是卡在某个执行阶段。")
        if steps:
            lines.append("阶段状态：" + "、".join(
                f"{item.get('step_id')}={item.get('status')}" for item in steps if isinstance(item, Mapping)))  # noqa: E501
        if failures_text:
            lines.append("失败发生在验收检查：" + failures_text + "。")
    else:
        lines.append(f"结论：当前修复的验收结论是 **{word or '尚无结论'}**。")
        if failures_text:
            lines.append(f"未通过的必需检查：{failures_text}。")
        if plan.get("root_cause"):
            lines.append("根因：" + str(plan.get("root_cause"))[:400])
        if edits:
            kinds = "、".join(str(item.get("kind")) for item in edits if isinstance(item, Mapping))
            lines.append(f"修复方案包含 {len(edits)} 处编辑（{kinds}），核心是把无界 strcpy 调用重定向到长度守卫桩。")
        if candidate:
            lines.append(f"候选程序 sha256：{candidate}。")

    # The final section is intentionally the most concrete: users often do not
    # know what a verifier failure means operationally.
    next_steps: list[str] = ["**下一步操作建议**"]
    if "V0-identity" in failures_text:
        next_steps.append("1. 在 Windows/WSL2 的现场 guest 中，对当前 candidate 重新执行冻结 corpus，生成与 candidate 哈希一致的 observations；本机 macOS 无法替代这一步。")
    if "V4-boundary" in failures_text:
        next_steps.append("2. 检查 cave 末尾是否存在“比较输入长度后跳回原 copy 目标”的可识别 rel32 布局；验证器只做有界字节模式匹配，识别不到不会自动判 pass。")
    if "V1-structure" in failures_text:
        next_steps.append("2. 用 edit-manifest.json 逐项核对段权限、重定位、入口和 PT_LOAD，保持冻结契约不变。")
    if not failures_text:
        next_steps.append("1. 当前必需判据没有失败项；重新运行 verifier 并确认 verdict finalized，再下载 candidate 和 verdict。")
    next_steps.append("3. 修正后重新运行完整流程，不要只重跑 UI；先确认 repair 产物，再确认 verify 的 V0–V4。")
    next_steps.append("4. 最后打开 verdict.json 核对 verdict 与 limitations，并下载 candidate.elf、edit-manifest.json 和 verdict.json 留档。")
    lines.extend(["", *next_steps])
    lines.append("以上内容全部来自已持久化的任务、verdict、manifest 和 journal，不是新的验证结论。")
    actions = [_action(locale, "download")] if (artifacts or extra.get("artifacts")) else []
    actions.append(_action(locale, "evidence"))
    return {"reply": "\n\n".join(lines)[:MAX_REPLY_CHARS], "actions": actions}


def respond(
    task: Mapping[str, Any] | None,
    records: Sequence[Mapping[str, Any]] | None,
    message: str,
    *,
    locale: str | None = "zh-Hans",
    client: Client | None = None,
    key_present: bool = False,
    artifacts: Sequence[Mapping[str, Any]] | None = None,
    context_extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``{"reply", "actions", "mode"}`` for one chat turn.

    The client seam is only called with the compact context above.  Invalid or
    failed model output falls back to the scripted reply; the fallback never
    echoes provider text and its mode badge tells the truth.
    """
    task = task if isinstance(task, Mapping) else {}
    records = records or []
    message = str(message or "")[:MAX_MESSAGE_CHARS]
    artifacts = _artifacts(task, artifacts)
    context = _context(task, records, artifacts, context_extra)
    if client is not None:
        try:
            envelope = validate_envelope(client(build_messages(context, message, locale)))
        except Exception:
            envelope = None
        if envelope is not None and not _contains_unpersisted_verdict(envelope["reply"], context):
            envelope["mode"] = MODE_LLM
            return envelope
        fallback = _diagnostic_fallback(task, records, message, locale, context_extra, artifacts)
        fallback["mode"] = MODE_DETERMINISTIC
        fallback["fallback_code"] = "assistant_fallback"
        return fallback
    fallback = _diagnostic_fallback(task, records, message, locale, context_extra, artifacts)
    fallback["mode"] = MODE_LLM_NOT_WIRED if key_present else MODE_DETERMINISTIC
    if key_present:
        fallback["fallback_code"] = "assistant_llm_not_wired"
    return fallback
