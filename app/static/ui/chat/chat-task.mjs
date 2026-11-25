// G4 conversation engine: upload -> analysis -> repair contracts -> repaired output.
//
// The browser never computes a verdict and never executes the uploaded ELF. It
// uploads the binary and its case files to the console API, lets the user pick
// one repair contract from the analyzed options, then follows the real runner
// journal and renders the persisted VerdictV1 and the artifact download links.
import {label} from './chat-copy.mjs?v=20261126b';

const newId = () => crypto.randomUUID();
const autoTitle = (chat, value) => {
  const title = String(value || '').trim();
  if (title && !chat.titleIsCustom) {
    chat.title = title.slice(0, 120);
    chat.titleKey = null;
  }
};
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const t = (locale, zh, en) => locale === 'zh-Hans' ? zh : en;

export function chatTask({notify = () => {}} = {}) {
  const chats = new Map();
  let sessionPromise = null;
  // Active tool calls per chat; sizes the pet's busy level (SPEC section 6).
  const toolCounts = new Map();

  function create() {
    const chat = {
      id: newId(), events: [], phase: 'idle', title: '', queue: [],
      attachmentNames: new Map(), reviewScopes: new Map(),
      jobId: null, task: null, g4: null, options: [], request: null,
      run: null, started: null, ended: null, epoch: 0, locale: 'en',
      journal: [], journalSeq: 0, plan: null, runEnd: null, auditRuns: null, g2: null,
      live: true, taskMode: true, requireAscii: false, timer: null, assistantMode: null,
      pendingBinary: null, attachmentFiles: new Map(),
    };
    chats.set(chat.id, chat);
    return chat;
  }

  function announceTask(taskId) {
    if (!taskId) return;
    globalThis.__binaryRepairTaskId = taskId;
    try {
      document.dispatchEvent(new CustomEvent('binaryrepair:task', {detail: {taskId}}));
    } catch { /* no DOM in unit contexts */ }
  }

  // Feed the optional Clawd pet contract. The pet is decorative, so every call
  // is optional-chained and guarded: a pet failure can never break the chat.
  function petSignal(patch) {
    if (!patch) return;
    try { globalThis.BinaryRepairPet?.signal?.(patch); } catch { /* pet is decorative */ }
  }

  function toolCount(chat) {
    return Math.max(0, Number(toolCounts.get(chat.id)) || 0);
  }

  // Map this engine's events onto one pet snapshot patch (see SPEC section 6).
  // Returns null when the event should not move the pet.
  function petPatch(chat, type, payload) {
    const p = payload || {};
    if (type === 'run_state') {
      const status = p.status;
      if (status === 'running' || status === 'cancelling') {
        return {activity: 'thinking', awaiting: false, busy: 0};
      }
      if (status === 'queued' || status === 'waiting_for_executor') {
        return {activity: 'thinking', awaiting: false};
      }
      if (status === 'awaiting_user') return {awaiting: true, activity: 'idle'};
      if (status === 'completed') {
        toolCounts.delete(chat.id);
        return {activity: 'idle', awaiting: false, moment: 'attention'};
      }
      if (status === 'failed' || status === 'cancelled' || status === 'unsupported') {
        // `unsupported` is the read-only analysis outcome written by finish();
        // it is terminal like a failure, so the pet settles the same way.
        toolCounts.delete(chat.id);
        return {activity: 'idle', awaiting: false, moment: 'error'};
      }
      return null;
    }
    if (type === 'assistant_delta') {
      return {activity: 'working', busy: Math.max(1, toolCount(chat) + 1)};
    }
    if (type === 'assistant_reply') return {activity: 'working', busy: 1};
    if (type === 'assistant_end') return {activity: 'thinking'};
    if (type === 'thinking') {
      return p.phase === 'started' ? {activity: 'thinking'} : null;
    }
    if (type === 'error') return {moment: 'error'};
    if (type === 'awaiting_user') return {awaiting: true};
    if (type === 'tool_call' || type === 'tool_result') {
      const next = Math.max(0, toolCount(chat) + (type === 'tool_call' ? 1 : -1));
      toolCounts.set(chat.id, next);
      return {activity: 'working', busy: Math.max(1, next)};
    }
    if (type === 'g4_live_audit') {
      const live = p.live_audit?.status;
      if (live === 'running') return {activity: 'working', busy: 1};
      if (live === 'completed') return {moment: 'attention'};
      if (live === 'failed') return {moment: 'error'};
      return null;
    }
    if (type === 'g4_progress') return {activity: 'working', busy: 1};
    if (type === 'user_message' || type === 'user_response') {
      return {activity: 'thinking', awaiting: false};
    }
    return null;
  }

  function event(chat, type, payload, step = null, run = chat.run) {
    const entry = {
      version: 1, type, conversation_id: chat.id, seq: String(chat.events.length + 1),
      run_id: run ?? null, step_id: step, ts: new Date().toISOString(), source: 'gui', payload,
    };
    chat.events.push(entry);
    notify(chat, entry);
    try {
      let pet = null;
      if (type === 'run_state') {
        const status = payload?.status;
        pet = status === 'running' || status === 'cancelling' ? 'running'
          : status === 'completed' ? 'happy'
            : status === 'failed' || status === 'cancelled' ? 'error'
              : status === 'queued' || status === 'waiting_for_executor' ? 'waiting' : null;
      } else if (type === 'error') pet = 'error';
      else if (type === 'assistant_reply') pet = 'happy';
      else if (type === 'assistant_delta') pet = 'thinking';
      else if (type === 'thinking' && payload?.phase === 'started') pet = 'thinking';
      else if (type === 'g4_live_audit') {
        const live = payload?.live_audit?.status;
        pet = live === 'running' ? 'thinking' : live === 'completed' ? 'happy'
          : live === 'failed' ? 'error' : null;
      }
      if (pet) {
        window.dispatchEvent(new CustomEvent('binaryrepair:pet-state',
          {detail: {state: pet}}));
      }
    } catch { /* pet is decorative */ }
    // Additive wiring: the Clawd pet also accepts explicit snapshot patches.
    try { petSignal(petPatch(chat, type, payload)); } catch { /* pet is decorative */ }
    return entry;
  }

  function say(chat, text) {
    const id = newId();
    event(chat, 'assistant_delta', {message_id: id, append: text});
    event(chat, 'assistant_end', {message_id: id, status: 'complete'});
  }

  function state(chat, status) {
    chat.phase = status;
    event(chat, 'run_state', {status, message_id: null});
  }

  async function session() {
    if (!sessionPromise) {
      sessionPromise = fetch('/api/session', {credentials: 'same-origin', cache: 'no-store'})
        .then(response => {
          if (!response.ok) throw new Error('session_unavailable');
          return response.json();
        });
    }
    return sessionPromise;
  }

  async function api(path, {method = 'GET', body, headers = {}} = {}) {
    const current = await session();
    const requestHeaders = {'x-csrf-token': current.csrf_token, ...headers};
    if (body !== undefined && !(body instanceof FormData)) {
      requestHeaders['content-type'] = 'application/json';
    }
    let response;
    try {
      response = await fetch(path, {
        method, headers: requestHeaders, credentials: 'same-origin', cache: 'no-store',
        body: body === undefined ? undefined : (body instanceof FormData ? body : JSON.stringify(body)),
      });
    } catch (error) {
      throw new Error(t('zh-Hans', '本地服务不可达', 'The local service is unreachable'));
    }
    let data = null;
    try { data = await response.json(); } catch { /* empty body */ }
    if (!response.ok) {
      const detail = data?.detail;
      const message = typeof detail === 'string' ? detail : detail?.code ?? ('HTTP ' + response.status);
      const error = new Error(message);
      error.status = response.status;
      error.detail = detail;
      throw error;
    }
    return data;
  }

  function readBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function send(chat, text, locale, attachment, file, cases = []) {
    chat.locale = locale;
    if (file) {
      await probeBinary(chat, file, locale);
      if (cases.length) await submitCases(chat, cases, locale);
      return;
    }
    if (chat.pendingBinary) {
      if (cases.length) {
        await submitCases(chat, cases, locale);
      } else {
        say(chat, t(locale,
          '已识别二进制文件。请再添加正确用例与错误用例（PoC）文件，或直接拖入下方的用例拖拽区域。',
          'Binary recognized. Add the valid and PoC case files, or drop them into the case '
          + 'area below.'));
      }
      return;
    }
    if (chat.jobId && String(text || '').trim()) {
      await assistantTurn(chat, String(text).trim(), locale);
      return;
    }
    say(chat, t(locale,
      '请先添加需要修复的 .elf 二进制漏洞文件；识别成功后再添加用例文件。',
      'Add the vulnerable .elf binary first; case files are requested after it is recognized.'));
  }

  async function probeBinary(chat, file, locale) {
    if (['running', 'awaiting_user', 'cancel_requested'].includes(chat.phase)) return;
    chat.locale = locale;
    autoTitle(chat, file.name);
    const messageId = newId();
    const attachmentId = newId();
    chat.attachmentNames.set(attachmentId, file.name);
    chat.attachmentFiles.set(attachmentId, {
      name: file.name, kind: 'binary', size: file.size, base64: await readBase64(file),
    });
    event(chat, 'user_message', {
      message_id: messageId,
      text: t(locale, `添加二进制漏洞文件：${file.name}`, `Vulnerable binary: ${file.name}`),
      attachment_ids: [attachmentId], delivery: 'accepted',
    }, null, null);
    try {
      const binaryBase64 = await readBase64(file);
      const data = await api('/api/tasks/probe', {
        method: 'POST',
        body: {binary_name: file.name, binary_base64: binaryBase64},
      });
      const supported = Boolean(data.supported);
      chat.pendingBinary = supported ? {name: file.name, base64: binaryBase64, probe: data} : null;
      autoTitle(chat, data.binary_name || file.name);
      chat.kind = 'repair';
      event(chat, 'binary_ready', {
        id: 'binary-' + newId(),
        binary_name: data.binary_name || file.name,
        binary_sha256: data.binary_sha256 || '',
        supported,
        analysis_status: data.analysis_status || 'ok',
        finding: data.finding || {},
        unsupported_detail: data.unsupported_detail || null,
      }, 'collect');
      if (!supported) {
        // The MVP2 repair scope is the frozen stack-overflow-01 pattern. An
        // unsupported ELF is analyzed read-only and never reaches case intake
        // or the repair runner.
        say(chat, t(locale,
          '当前修复范围仅支持包含 MVP2 栈溢出模式（strcpy 调用点）的 ELF。'
          + '该文件只完成了只读分析，不会进入用例上传或修复流程。',
          'Repair is scoped to the MVP2 stack-overflow pattern (a strcpy call site). '
          + 'This ELF was analyzed read-only and will not enter case intake or repair.'));
        state(chat, 'unsupported');
        return;
      }
      event(chat, 'case_prompt', {
        id: 'cases-' + newId(),
        binary_name: data.binary_name || file.name,
      }, 'collect');
      state(chat, 'awaiting_cases');
    } catch (error) {
      const problems = error.detail?.problems;
      const detail = Array.isArray(problems) && problems.length
        ? '\n' + problems.map(item => '• ' + item).join('\n') : '';
      say(chat, t(locale,
        `文件不符合修复要求：${error.detail?.code || error.message}${detail}`,
        `The file does not meet the repair requirements: ${error.detail?.code || error.message}${detail}`));
      state(chat, 'failed');
    }
  }

  async function submitCases(chat, cases, locale) {
    if (!chat.pendingBinary) {
      say(chat, t(locale, '请先添加二进制漏洞文件。', 'Add the vulnerable binary first.'));
      return;
    }
    if (!cases.length) {
      say(chat, t(locale, '请选择正确用例与错误用例文件。',
        'Choose the valid and PoC case files.'));
      return;
    }
    const payload = {
      binaryName: chat.pendingBinary.name,
      binaryBase64: chat.pendingBinary.base64,
      caseFiles: [],
    };
    for (const item of cases) {
      payload.caseFiles.push({name: item.name, content_base64: await readBase64(item)});
    }
    event(chat, 'case_received', {
      id: 'cases-done-' + newId(), count: cases.length,
      names: cases.map(item => item.name),
    }, 'collect');
    chat.pendingBinary = null;
    await submitPayload(chat, payload,
      t(locale, '用例已就绪，请分析并生成修复方案', 'Cases ready; analyze and propose repair plans'),
      locale);
  }


  function assistantAction(chat, action) {
    const kind = String(action?.kind || '');
    if (kind === 'download' || kind === 'evidence') {
      if (chat.jobId) {
        window.location.href = '/ui/#task/' + encodeURIComponent(chat.jobId);
      } else {
        say(chat, t(chat.locale, '当前还没有可打开的持久化证据。',
          'No persisted evidence is available yet.'));
      }
      return;
    }
    if (kind === 'rerun' || kind === 'retry') {
      if (!chat.jobId) return;
      say(chat, t(chat.locale, '正在重新启动 AI 现场审计；完成后请重新选择方案。',
        'Restarting the live AI audit; choose a plan again when it finishes.'));
      window.dispatchEvent(new CustomEvent('binaryrepair:assistant-focus',
        {detail: {chatId: chat.id}}));
      void startLiveAudit(chat, 0, true);
      return;
    }
    if (kind === 'change_scope') {
      say(chat, t(chat.locale,
        '冻结契约不能在原任务上修改；已为你新建一个修复对话，请在新对话上传新的二进制和用例。',
        'A frozen contract cannot be changed in place; a new repair conversation is ready for a new binary and cases.'));
      window.dispatchEvent(new CustomEvent('binaryrepair:new-chat'));
      return;
    }
    if (kind === 'attach') {
      document.querySelector('input[type="file"]')?.click();
      return;
    }
    window.dispatchEvent(new CustomEvent('binaryrepair:assistant-focus',
      {detail: {chatId: chat.id}}));
  }

  async function assistantTurn(chat, text, locale, model = null) {
    if (!chat.jobId) return;
    chat.locale = locale;
    chat.assistantMode = chat.assistantMode ?? 'deterministic';
    const messageId = newId();
    event(chat, 'user_message', {message_id: messageId, text, attachment_ids: [],
      delivery: 'accepted'}, null, null);
    // The provider can take tens of seconds; show that the grounded evidence
    // is being read instead of leaving the user with a silent bubble.
    const waiting = setTimeout(() => {
      say(chat, t(locale, '正在读取 verdict、manifest、journal 与候选产物…',
        'Reading the verdict, manifest, journal and candidate artifacts…'));
    }, 900);
    try {
      const data = await api(`/api/tasks/${chat.jobId}/assistant`, {
        method: 'POST',
        body: {message: text, locale, model: model || undefined},
      });
      clearTimeout(waiting);
      chat.assistantMode = data.mode || 'deterministic';
      event(chat, 'assistant_reply', {
        message_id: newId(),
        reply: data.reply || '',
        actions: Array.isArray(data.actions) ? data.actions : [],
        mode: chat.assistantMode,
        fallback_code: data.fallback_code || null,
      }, null, null);
    } catch {
      clearTimeout(waiting);
      chat.assistantMode = 'deterministic';
      say(chat, t(locale,
        'AI 助手暂时不可用，已使用本地确定性回复；任务状态仍以持久化 journal 为准。',
        'The AI assistant is unavailable; the local deterministic reply is used. Task state '
        + 'still comes only from the persisted journal.'));
    }
  }

  async function sendFixture(chat, locale = chat.locale) {
    if (['running', 'awaiting_user', 'cancel_requested'].includes(chat.phase)) return;
    chat.locale = locale;
    try {
      const payload = await api('/api/g4/fixture');
      await submitPayload(chat, {
        binaryName: payload.binary_name,
        binaryBase64: payload.binary_base64,
        caseFiles: payload.case_files || [],
      }, t(locale, '试用冻结示例：分析并演示修复流程',
        'Demo the frozen fixture: analyze and show the repair flow'), locale);
    } catch (error) {
      say(chat, t(locale, `无法加载示例：${error.message}。`, `Could not load the demo: ${error.message}.`));
    }
  }

  async function submitPayload(chat, payload, text, locale) {
    const cases = payload.caseFiles || [];
    const clean = String(text || '').trim() ||
      t(locale, '请修复这个二进制文件', 'Repair this binary');
    const messageId = newId();
    const attachmentIds = [newId(), ...cases.map(() => newId())];
    chat.attachmentNames.set(attachmentIds[0], payload.binaryName);
    chat.attachmentFiles.set(attachmentIds[0], {
      name: payload.binaryName, kind: 'binary', base64: payload.binaryBase64 || '',
    });
    cases.forEach((item, index) => {
      chat.attachmentNames.set(attachmentIds[index + 1], item.name);
      chat.attachmentFiles.set(attachmentIds[index + 1], {
        name: item.name, kind: 'case', base64: item.content_base64 || '',
      });
    });
    event(chat, 'user_message', {
      message_id: messageId, text: clean, attachment_ids: attachmentIds, delivery: 'accepted',
    }, null, null);
    autoTitle(chat, payload.binaryName);
    chat.kind = 'repair';
    chat.started = Date.now();
    chat.ended = null;
    state(chat, 'running');
    event(chat, 'thinking', {phase: 'started'}, 'collect');
    try {
      const data = await api('/api/tasks/upload', {
        method: 'POST',
        body: {
          binary_name: payload.binaryName,
          binary_base64: payload.binaryBase64,
          case_files: payload.caseFiles || [],
          defect: clean,
        },
      });
      chat.jobId = data.task.id;
      announceTask(chat.jobId);
      chat.task = data.task;
      chat.g4 = data.task.g4;
      chat.options = data.plans || [];
      event(chat, 'thinking', {phase: 'finished', duration_ms: 0, summary_code: 'analysis',
        description: 'analysis'}, 'collect');
      const finding = data.analysis || {};
      const counts = data.task.g4?.cases?.counts || {};
      const status = data.analysis_status || data.task.g4?.analysis_status || 'ok';
      if (status === 'no_supported_finding' || !data.supported) {
        if (status === 'no_supported_finding') {
          say(chat, t(locale,
            '分析器已完成反汇编，但没有识别到 MVP2 支持的栈溢出模式（strcpy 调用点）。'
            + '这个 ELF 不在冻结 fixture 的签名修复范围内，因此不会写入修复补丁。'
            + '该文件只保留为只读分析证据；不会进入修复流程。',
            'The analyzer disassembled the ELF but did not find the MVP2-supported stack '
            + 'overflow pattern (the strcpy call site). The file remains read-only analysis '
            + 'evidence and does not enter repair.'));
        } else {
          say(chat, t(locale,
            `这个 ELF 的 SHA-256 不是冻结 fixture（${data.task.g4?.binary_sha256?.slice(0, 12) ?? '?'}）。`
            + 'MVP2 只对签名 fixture 写补丁；当前已完成只读分析，不会伪造修复输出。',
            `This ELF is not the frozen fixture (sha256 ${data.task.g4?.binary_sha256?.slice(0, 12) ?? '?'}). `
            + 'MVP2 only patches the signed fixture; the analysis is read-only and no repair '
            + 'output is fabricated.'));
        }
        finish(chat, 'unsupported');
        return;
      }
      event(chat, 'g4_analysis', {
        function: finding.function || '?',
        address: finding.address || '?',
        instruction: finding.instruction || '?',
        cwe: finding.cwe || 'CWE-121',
        counts: {valid: counts.valid ?? 0, poc: counts.poc ?? 0},
      }, 'analyze');
      try {
        const g2 = await api('/api/g4/g2');
        chat.g2 = g2;
        const audit = g2.audit || {};
        const selected = audit.selected_plan || {};
        const runs = audit.runs || [];
        const schemas = runs.length > 0 && runs.every(run => run.schema_valid);
        const scores = audit.reviewer_scores || {};
        event(chat, 'g4_g2', {
          report_id: audit.report_id || '—',
          runs: runs.length,
          schema_valid: schemas,
          score_m1: scores.m1 ?? null,
          decision: audit.decision || '—',
          selected_run: selected.run_index ?? null,
          plan_id: g2.plan?.plan_id || '—',
          strategy: g2.plan?.strategy || '—',
          record_sha256: g2.record_sha256 || null,
          contract_sha256: g2.contract_sha256 || null,
        }, 'report');
      } catch { chat.g2 = null; }
      try {
        const audit = await api(`/api/tasks/${chat.jobId}/audit`);
        chat.audit = audit;
        // Only the live AI audit may generate a plan. The signed replay is
        // retained server-side for archival acceptance but is not offered here.
        chat.auditMode = 'live';
        chat.liveGuest = Boolean(audit.live_guest);
        chat.guestAvailable = audit.guest_available !== false;
        emitLiveAudit(chat);
      } catch { chat.audit = null; }
      chat.request = {
        kind: 'repair_plan',
        request_id: newId(),
        options: chat.options.map(option => ({
          id: option.id,
          title: locale === 'zh-Hans' ? option.title_zh : option.title_en,
          summary: locale === 'zh-Hans' ? option.summary_zh : option.summary_en,
          reason: locale === 'zh-Hans' ? (option.reason_zh || option.reason_en)
            : (option.reason_en || option.reason_zh),
          feasible: option.feasible,
        })),
        note: t(locale, '方案由 AI 现场审计生成；请选择现场方案。',
          'Plans are generated by the live AI audit; choose a live plan.'),
      };
      event(chat, 'awaiting_user', chat.request, 'report');
      state(chat, 'awaiting_user');
      void startLiveAudit(chat);
    } catch (error) {
      event(chat, 'thinking', {phase: 'finished', duration_ms: 0, summary_code: 'analysis'},
        'collect');
      const code = error.detail?.code || error.message;
      let reason;
      const problems = Array.isArray(error.detail?.problems) ? error.detail.problems : [];
      if (code === 'invalid_cases' || code === 'cases_incomplete'
          || code === 'cases_not_utf8' || code === 'invalid_case_file_type') {
        reason = t(locale,
          '用例文件不符合要求：需要 UTF-8 JSON，且每个文件必须包含非空 valid 和/或 '
          + 'invalid/poc 列表；整体必须同时提供正确用例和错误用例。',
          'Case files do not meet the requirements: UTF-8 JSON with non-empty valid '
          + 'and/or invalid/poc lists; both valid and invalid cases are required overall.');
        if (problems.length) reason += '\n' + problems.map(item => '• ' + item).join('\n');
      } else if (error.status === 422) {
        reason = t(locale,
          '只支持冻结 stack-overflow-01 fixture 中可识别的栈溢出 ELF；本次只读分析未进入修复。',
          'Only the known stack-overflow pattern in the frozen stack-overflow-01 fixture is '
          + 'repairable; this upload was analyzed read-only and did not enter repair.');
      } else {
        reason = t(locale, `上传或分析失败：${error.message}。`,
          `Upload or analysis failed: ${error.message}.`);
      }
      say(chat, reason);
      finish(chat, 'failed');
    }
  }

  function emitLiveAudit(chat, extra = {}) {
    const audit = chat.audit || {};
    event(chat, 'g4_live_audit', {
      id: 'g4-live-' + chat.jobId,
      mode: chat.auditMode || 'signed',
      live_audit: audit.live_audit || {status: 'idle', runs: []},
      selected_plan: audit.selected_plan || null,
      live_guest: Boolean(chat.liveGuest),
      guest_available: chat.guestAvailable !== false,
      ...extra,
    }, 'audit');
  }

  async function setLiveMode(chat, mode) {
    const target = mode === 'live' ? 'live' : 'signed';
    const current = chat.audit?.audit_mode || chat.auditMode || 'signed';
    if (target === 'signed' && current === 'live' && chat.jobId) {
      try {
        await api(`/api/tasks/${chat.jobId}/audit/signed`, {method: 'POST', body: {}});
        const audit = await api(`/api/tasks/${chat.jobId}/audit`);
        chat.audit = audit;
        chat.auditMode = audit.audit_mode || 'signed';
        chat.liveGuest = Boolean(audit.live_guest);
        chat.liveRunning = false;
        emitLiveAudit(chat);
        return;
      } catch (error) {
        say(chat, t(chat.locale,
          `无法切回回放已签 G2：${error.detail?.code || error.message}。`,
          `Could not switch back to the signed G2 replay: ${error.detail?.code || error.message}.`));
        return;
      }
    }
    chat.auditMode = target;
    emitLiveAudit(chat);
  }

  async function setLiveGuest(chat, value) {
    const next = Boolean(value);
    const previous = Boolean(chat.liveGuest);
    chat.liveGuest = next;
    emitLiveAudit(chat);
    if (!chat.jobId) return;
    try {
      const data = await api(`/api/tasks/${chat.jobId}/audit/guest`, {
        method: 'POST', body: {enabled: next},
      });
      chat.liveGuest = Boolean(data.live_guest);
      chat.guestAvailable = data.guest_available !== false;
      emitLiveAudit(chat);
    } catch (error) {
      chat.liveGuest = previous;
      emitLiveAudit(chat);
      say(chat, t(chat.locale,
        `现场 guest 设置未保存：${error.detail?.code || error.message}。`,
        `Live guest setting was not saved: ${error.detail?.code || error.message}.`));
    }
  }

  function settleLiveAudit(chat) {
    if (chat.liveFailureNotified) return;
    const live = chat.audit?.live_audit || {};
    const runs = Array.isArray(live.runs) ? live.runs : [];
    if (live.status === 'completed' && runs.length && runs.every(run => run.selectable === false)) {
      chat.liveFailureNotified = true;
      const reasons = [...new Set(runs.map(run => run.select_reason).filter(Boolean))];
      const detail = reasons.length ? reasons.join(' · ') : 'no_selectable_plan';
      say(chat, t(chat.locale,
        `AI 现场审计结束：${runs.length} 个方案全部无法选择，修复失败。原因：${detail}`,
        `Live AI audit finished: all ${runs.length} plans are unselectable, so repair failed. `
        + `Reason: ${detail}`));
      finish(chat, 'failed');
      scheduleSave();
      return;
    }
    if (live.status === 'failed' && !chat.runEnd) {
      chat.liveFailureNotified = true;
      say(chat, t(chat.locale,
        `AI 现场审计失败：${live.error || 'audit_failed'}；没有生成可修复方案。`,
        `Live AI audit failed: ${live.error || 'audit_failed'}; no repair plan was generated.`));
      finish(chat, 'failed');
      scheduleSave();
    }
  }

  async function startLiveAudit(chat, retry = 0, rerun = false) {
    if (!chat.jobId || chat.liveRunning) return;
    chat.auditMode = 'live';
    chat.ended = null;
    if (rerun) { chat.audit = null; chat.verdict = null; chat.runEnd = null; }
    chat.liveGuest = false;
    chat.guestAvailable = chat.audit?.guest_available !== false;
    chat.liveRunning = true;
    chat.liveFailureNotified = false;
    emitLiveAudit(chat);
    try {
      await api(`/api/tasks/${chat.jobId}/audit/live`, {method: 'POST', body: {rerun}});
    } catch (error) {
      const code = error.detail?.code || error.message || 'audit_failed';
      emitLiveAudit(chat, {error: code});
      chat.liveRunning = false;
      if (retry < 1) {
        say(chat, t(chat.locale, 'AI 现场审计启动失败，正在自动重试一次…',
          'Live AI audit did not start; retrying once automatically…'));
        await sleep(1200);
        return startLiveAudit(chat, retry + 1);
      }
      say(chat, t(chat.locale,
        `AI 现场审计未启动（${code}）；没有可用的方案生成路径。`,
        `Live AI audit did not start (${code}); no plan-generation path is available.`));
      return;
    }
    const deadline = Date.now() + 600000;
    while (Date.now() < deadline) {
      await sleep(800);
      try {
        const data = await api(`/api/tasks/${chat.jobId}/audit`);
        const before = JSON.stringify(chat.audit?.live_audit || null);
        chat.audit = data;
        if (JSON.stringify(data.live_audit || null) !== before) emitLiveAudit(chat);
        const status = data.live_audit?.status;
        if (data.audit_mode === 'signed') break;
        if (status === 'completed' || status === 'failed') break;
      } catch { break; }
    }
    chat.liveRunning = false;
    const live = chat.audit?.live_audit || {};
    const runs = Array.isArray(live.runs) ? live.runs : [];
    if ((live.status === 'failed' || (live.status === 'completed' && runs.length !== 3))
        && retry < 1) {
      say(chat, t(chat.locale, 'AI 现场审计未完成，正在自动重试一次…',
        'The live AI audit did not finish; retrying once automatically…'));
      emitLiveAudit(chat, {error: 'retrying'});
      await sleep(1200);
      chat.liveFailureNotified = false;
      return startLiveAudit(chat, retry + 1);
    }
    settleLiveAudit(chat);
  }

  async function resumeLiveAudit(chat) {
    const deadline = Date.now() + 600000;
    while (Date.now() < deadline) {
      await sleep(800);
      try {
        const data = await api(`/api/tasks/${chat.jobId}/audit`);
        const before = JSON.stringify(chat.audit?.live_audit || null);
        chat.audit = data;
        chat.auditMode = data.audit_mode || chat.auditMode || 'live';
        chat.liveGuest = Boolean(data.live_guest);
        chat.guestAvailable = data.guest_available !== false;
        if (JSON.stringify(data.live_audit || null) !== before) emitLiveAudit(chat);
        if (data.audit_mode === 'signed') break;
        const status = data.live_audit?.status;
        if (status === 'completed' || status === 'failed') break;
      } catch { break; }
    }
    chat.liveRunning = false;
    settleLiveAudit(chat);
  }

  async function selectLivePlan(chat, runIndex) {
    try {
      const data = await api(`/api/tasks/${chat.jobId}/plan`, {
        method: 'POST', body: {run_index: runIndex, live_guest: chat.liveGuest},
      });
      const audit = await api(`/api/tasks/${chat.jobId}/audit`);
      chat.audit = audit;
      emitLiveAudit(chat);
      say(chat, t(chat.locale,
        `已记录现场方案 run ${runIndex}，plan ${String(data.selected_plan?.canonical_sha256 || '').slice(0, 12)}…；`
        + '确认后按该计划启动修复与现场 guest 验证。',
        `Live plan run ${runIndex} recorded (plan ${String(data.selected_plan?.canonical_sha256 || '').slice(0, 12)}…); `
        + 'confirm to start the repair and live guest verification.'));
    } catch (error) {
      say(chat, t(chat.locale,
        `现场方案选择失败：${error.detail?.code || error.message}。`,
        `Live plan selection failed: ${error.detail?.code || error.message}.`));
    }
  }

  async function startLivePlan(chat) {
    if (!chat.jobId || !chat.audit?.selected_plan) return;
    state(chat, 'running');
    // Keep chat.started at the binary-input moment: the flow duration covers
    // analysis, audit, repair selection and the terminal verdict/export.
    chat.ended = null;
    chat.auditMode = 'live';
    event(chat, 'thinking', {phase: 'started'}, 'repair');
    try {
      const task = await api(`/api/tasks/${chat.jobId}`);
      const digest = task.review_binding_digest;
      await api(`/api/tasks/${chat.jobId}/approve`, {
        method: 'POST', body: {expected_review_binding_digest: digest,
          expected_plan_sha256: chat.audit.selected_plan.canonical_sha256,
          reviewer_label: 'M2-G4.1'},
      });
      const started = await api(`/api/tasks/${chat.jobId}/start`, {
        method: 'POST', headers: {'Idempotency-Key': 'g4-live-' + chat.jobId},
        body: {expected_review_binding_digest: digest},
      });
      chat.run = started.run_id;
      chat.execution = {run_id: started.run_id, terminal: false, status: 'queued'};
      chat.journal = [];
      chat.journalSeq = 0;
      chat.plan = null;
      chat.runEnd = null;
      chat.auditRuns = null;
      void follow(chat);
    } catch (error) {
      event(chat, 'thinking', {phase: 'finished', duration_ms: 0, summary_code: 'repair'},
        'repair');
      say(chat, t(chat.locale,
        `现场修复启动失败：${error.detail?.code || error.message}。`,
        `Live repair could not start: ${error.detail?.code || error.message}.`));
      finish(chat, 'failed');
    }
  }

  async function decide(chat, requestId, action) {
    const request = chat.request;
    if (!request || request.request_id !== requestId) return;
    if (chat.auditMode === 'live') {
      say(chat, t(chat.locale, '当前处于 AI 现场审计模式；请选择现场审计方案，或切回回放已签 G2。',
        'Live audit mode is active; select a live plan or switch back to the signed G2 replay.'));
      return;
    }
    const option = chat.options.find(item => item.id === action);
    if (!option || !option.feasible) return;
    chat.request = null;
    chat.bound = {id: option.id, title_zh: option.title_zh, title_en: option.title_en,
      scope_zh: option.scope_zh, scope_en: option.scope_en};
    event(chat, 'user_response', {request_id: requestId, decision: action}, 'report');
    state(chat, 'running');
    chat.ended = null;
    event(chat, 'thinking', {phase: 'started'}, 'repair');
    say(chat, t(chat.locale,
      `已绑定已签 G2 决策：${option.title_zh || option.title_en}。不重跑审计，不重新投票；`
      + '下面启动按该决策修复。',
      `Bound the signed G2 decision: ${option.title_en || option.title_zh}. The audit is not `
      + 're-run and no new vote is taken; starting the repair under that decision.'));
    try {
      const selected = await api(`/api/tasks/${chat.jobId}/g4/select`, {
        method: 'POST', body: {option_id: action},
      });
      chat.task = selected.task;
      announceTask(chat.jobId);
      const digest = selected.task.review_binding_digest;
      await api(`/api/tasks/${chat.jobId}/approve`, {
        method: 'POST',
        body: {expected_review_binding_digest: digest, reviewer_label: 'M2-G4'},
      });
      await api(`/api/tasks/${chat.jobId}/decision`, {
        method: 'POST', body: {request_id: 'g4-plan', decision: 'proceed'},
      });
      const started = await api(`/api/tasks/${chat.jobId}/start`, {
        method: 'POST',
        headers: {'Idempotency-Key': 'g4-' + chat.jobId},
        body: {expected_review_binding_digest: digest},
      });
      chat.run = started.run_id;
      chat.execution = {run_id: started.run_id, terminal: false, status: 'queued'};
      chat.journal = [];
      chat.journalSeq = 0;
      chat.plan = null;
      chat.runEnd = null;
      chat.auditRuns = null;
      void follow(chat);
    } catch (error) {
      event(chat, 'thinking', {phase: 'finished', duration_ms: 0, summary_code: 'repair'},
        'repair');
      say(chat, t(chat.locale,
        `修复启动失败：${error.message}。`,
        `Repair could not start: ${error.message}.`));
      finish(chat, 'failed');
    }
  }

  async function collectJournal(chat) {
    if (!chat.run) return;
    let records = [];
    try {
      const data = await api(`/api/tasks/${chat.jobId}/journal?after_seq=${chat.journalSeq ?? 0}`);
      records = Array.isArray(data.records) ? data.records : [];
    } catch { return; }
    for (const record of records) {
      chat.journal.push(record);
      const seq = Number(record.seq) || 0;
      if (seq > (chat.journalSeq ?? 0)) chat.journalSeq = seq;
      const payload = record.payload || {};
      if (record.type === 'plan_update') {
        chat.plan = payload;
        event(chat, 'g4_progress', {
          id: 'g4-progress-' + (chat.run || 'run'),
          steps: payload.steps || [],
          revision: payload.revision ?? null,
          execution: chat.runEnd?.execution ?? null,
        }, 'report');
      }
      else if (record.type === 'audit_runs') chat.auditRuns = payload;
      else if (record.type === 'run_end') chat.runEnd = payload;
    }
  }

  async function follow(chat) {
    const deadline = Date.now() + 180_000;
    while (Date.now() < deadline && !chat.runEnd) {
      await collectJournal(chat);
      if (chat.runEnd) break;
      await sleep(500);
    }
    // One last replay catches a terminal record appended between polls.
    await collectJournal(chat);
    let verdict = null;
    let artifacts = [];
    try { verdict = await api(`/api/tasks/${chat.jobId}/verdict`); } catch { verdict = null; }
    try {
      const listed = await api(`/api/tasks/${chat.jobId}/artifacts`);
      artifacts = listed.artifacts || [];
    } catch { artifacts = []; }
    for (let attempt = 0; attempt < 5 && !verdict?.finalized; attempt += 1) {
      await sleep(300);
      try { verdict = await api(`/api/tasks/${chat.jobId}/verdict`); } catch { break; }
    }
    const word = verdict?.available && verdict?.finalized ? verdict.verdict : null;
    chat.verdict = verdict;
    event(chat, 'g4_progress', {
      id: 'g4-progress-' + (chat.run || 'run'),
      steps: chat.plan?.steps || [],
      revision: chat.plan?.revision ?? null,
      execution: chat.runEnd?.execution ?? null,
    }, 'report');
    const executionStatus = chat.runEnd?.execution || chat.phase;
    sendDownloads(chat, chat.jobId, artifacts, chat.locale, word, verdict, executionStatus);
    const execution = chat.runEnd?.execution === 'completed' ? 'completed'
      : chat.runEnd?.execution === 'cancelled' ? 'cancelled' : 'failed';
    finish(chat, execution);
  }

  function sendDownloads(chat, taskId, artifacts, locale, verdictWord, verdictPayload, executionStatus = null) {
    if (!artifacts.length) return;
    const byName = new Map(artifacts.map(item => [item.display_path, item]));
    const link = name => {
      const artifact = byName.get(name);
      if (!artifact) return null;
      return {label: name, href: `/api/artifacts/${artifact.artifact_id}/download`,
        sha256: artifact.sha256};
    };
    const candidate = link('candidate.elf');
    const manifest = link('edit-manifest.json');
    const verdictFile = link('verdict.json');
    event(chat, 'g4_downloads', {
      id: 'g4-downloads-' + taskId,
      execution: executionStatus,
      verdict_word: verdictWord || null,
      verdict_reason: (verdictPayload?.limitations || []).find(line =>
        /fail|not_run|missing|unavailable/i.test(String(line))) || null,
      failed_criteria: (verdictPayload?.criteria || []).filter(item =>
        item.required && ['fail', 'not_run'].includes(item.status)).map(item => item.id),
      candidate_sha256: verdictPayload?.candidate_sha256 ?? null,
      candidate: candidate && {...candidate, label: t(locale, '下载修复后的程序 (.elf)',
        'Download repaired program (.elf)')},
      manifest: manifest && {...manifest, label: t(locale, '下载补丁清单',
        'Download repair manifest')},
      verdict_file: verdictFile && {...verdictFile, label: t(locale, '下载验证结论 (verdict.json)',
        'Download verdict (verdict.json)')},
    }, 'export');
  }

  function finish(chat, execution) {
    chat.phase = execution;
    if (!chat.started) {
      const first = chat.events.find(item => item.ts);
      chat.started = Date.parse(chat.task?.created_at || '') || Date.parse(first?.ts || '') || Date.now();
    }
    if (!chat.ended) chat.ended = Date.now();
    if (chat.execution) chat.execution = {...chat.execution, terminal: true,
      status: execution};
    event(chat, 'run_state', {status: execution, message_id: null});
  }

  async function stop(chat) {
    if (!chat.jobId) return;
    try {
      const task = await api(`/api/tasks/${chat.jobId}`);
      await api(`/api/tasks/${chat.jobId}/cancel`, {
        method: 'POST', body: {run_id: task.execution?.run_id ?? chat.run},
      });
      say(chat, t(chat.locale, '已请求停止。', 'Stop requested.'));
    } catch { /* the run may already be terminal */ }
  }

  function seed(locale = 'en') {
    const chat = create();
    chat.locale = locale;
    say(chat, t(locale,
      '上传 .elf 二进制、正确用例与错误用例（PoC）文件后，我会分析漏洞并给出多种修复契约。',
      'Upload an .elf binary plus its valid and PoC case files; I will analyze the defect and '
      + 'offer several repair contracts.'));
    return chat;
  }

  const HISTORY_FIELDS = [
    'phase', 'title', 'titleKey', 'jobId', 'locale', 'kind', 'run', 'started', 'ended',
    'execution', 'journalSeq', 'plan', 'runEnd', 'auditRuns', 'g2', 'request', 'options',
    'g4', 'task', 'contract', 'startReady', 'reviewer', 'auditMode', 'liveGuest',
    'guestAvailable', 'bound', 'verdict', 'assistantMode', 'pendingBinary',
    'pinned', 'archived', 'titleIsCustom',
  ];

  function clip(value, depth = 0) {
    if (typeof value === 'string') return value.length > 4000
      ? value.slice(0, 4000) + '…' : value;
    if (depth > 8 || value === null || typeof value !== 'object') return value;
    if (value instanceof Map) return [...value.entries()];
    if (Array.isArray(value)) return value.slice(-500).map(item => clip(item, depth + 1));
    const out = {};
    for (const [key, item] of Object.entries(value)) {
      if (key === 'attachmentFiles' || key === 'timer' || key === 'epoch') continue;
      out[key] = clip(item, depth + 1);
    }
    return out;
  }

  function serialize() {
    return [...chats.values()].map(chat => {
      const out = {id: chat.id, events: clip(chat.events.slice(-500)),
        attachmentNames: [...chat.attachmentNames.entries()],
        attachmentFiles: chat.jobId ? [] : [...chat.attachmentFiles.entries()]};
      for (const field of HISTORY_FIELDS) {
        if (chat[field] !== undefined && chat[field] !== null) out[field] = clip(chat[field]);
      }
      return out;
    });
  }

  function restoreHistory(items) {
    if (!Array.isArray(items)) return;
    const seen = new Set();
    for (const item of items) {
      if (!item || typeof item !== 'object' || !Array.isArray(item.events)) continue;
      if (item.id && seen.has(item.id)) continue;
      const chat = create();
      const generatedId = chat.id;
      const savedId = item.id;
      Object.assign(chat, item);
      chat.id = savedId || generatedId;
      chat.events = item.events;
      chat.attachmentNames = new Map(item.attachmentNames || []);
      chat.attachmentFiles = new Map(item.attachmentFiles || []);
      chat.phase = item.phase || 'idle';
      if (generatedId !== chat.id) chats.delete(generatedId);
      chats.set(chat.id, chat);
      if (item.id) seen.add(item.id);
    }
  }

  async function activate(chat) {
    if (!chat?.jobId) return;
    if (['completed', 'failed', 'cancelled'].includes(chat.phase)) {
      // Older transcripts may predate the flow timer. Backfill from the
      // persisted task so a finished conversation never collapses to 0:00.
      if (!chat.started || !chat.ended) {
        try {
          const task = await api(`/api/tasks/${chat.jobId}`);
          const execution = task.execution || {};
          chat.started = chat.started || Date.parse(execution.started_at || task.created_at || '') || null;
          chat.ended = chat.ended || Date.parse(execution.finished_at || task.updated_at || '') || null;
        } catch { /* keep the stored transcript */ }
      }
      return;
    }
    try {
      const task = await api(`/api/tasks/${chat.jobId}`);
      chat.task = task;
      chat.execution = task.execution || chat.execution;
      if (chat.execution?.run_id) chat.run = chat.execution.run_id;
      let audit = null;
      try { audit = await api(`/api/tasks/${chat.jobId}/audit`); } catch { /* no live state */ }
      if (audit && audit.audit_mode === 'live' && audit.live_audit?.status === 'running') {
        chat.audit = audit;
        chat.auditMode = 'live';
        chat.liveRunning = true;
        emitLiveAudit(chat);
        void resumeLiveAudit(chat);
        return;
      }
      if (audit) {
        chat.audit = audit;
        chat.auditMode = 'live';
        chat.liveGuest = Boolean(audit.live_guest);
        chat.guestAvailable = audit.guest_available !== false;
        emitLiveAudit(chat);
        if (audit.live_audit?.status === 'completed' || audit.live_audit?.status === 'failed') {
          settleLiveAudit(chat);
        }
      }
      if (!chat.runEnd && !chat.events.some(item => item.type === 'run_end')) {
        await collectJournal(chat);
        if (chat.runEnd || task.execution?.run_id) await follow(chat);
      }
    } catch { /* keep the restored transcript; a missing task is shown as-is */ }
  }


  function deactivate() {}

  return {chats, live: true, taskMode: true, create, send, sendFixture, decide, assistantTurn, assistantAction,
    probeBinary, submitCases, serialize, restoreHistory, activate,
    startLiveAudit, selectLivePlan, startLivePlan, setLiveMode, setLiveGuest,
    start: async () => {}, stop, seed, activate, deactivate};
}
