// G4 conversation engine: upload -> analysis -> repair contracts -> repaired output.
//
// The browser never computes a verdict and never executes the uploaded ELF. It
// uploads the binary and its case files to the console API, lets the user pick
// one repair contract from the analyzed options, then follows the real runner
// journal and renders the persisted VerdictV1 and the artifact download links.
import {label} from './chat-copy.mjs?v=20261124n';

const newId = () => crypto.randomUUID();
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const t = (locale, zh, en) => locale === 'zh-Hans' ? zh : en;

export function chatTask({notify = () => {}} = {}) {
  const chats = new Map();
  let sessionPromise = null;

  function create() {
    const chat = {
      id: newId(), events: [], phase: 'idle', title: '', queue: [],
      attachmentNames: new Map(), reviewScopes: new Map(),
      jobId: null, task: null, g4: null, options: [], request: null,
      run: null, started: null, ended: null, epoch: 0, locale: 'en',
      journal: [], journalSeq: 0, plan: null, runEnd: null, auditRuns: null, g2: null,
      live: true, taskMode: true, requireAscii: false, timer: null,
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

  function event(chat, type, payload, step = null, run = chat.run) {
    const entry = {
      version: 1, type, conversation_id: chat.id, seq: String(chat.events.length + 1),
      run_id: run ?? null, step_id: step, ts: new Date().toISOString(), source: 'gui', payload,
    };
    chat.events.push(entry);
    notify(chat, entry);
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
    if (!file) {
      say(chat, t(locale,
        '请先添加需要修复的 .elf 二进制文件，以及对应正确用例与错误用例（PoC）文件。',
        'Attach the .elf binary plus its valid and PoC case files first.'));
      return;
    }
    if (!cases.length) {
      say(chat, t(locale,
        '已收到二进制文件。请再添加正确用例与错误用例文件（可多选），我会一起分析并生成修复契约。',
        'Binary received. Add the valid and PoC case files (multi-select) so I can analyze and '
        + 'derive the repair contracts.'));
      return;
    }
    const payload = {
      binaryName: file.name,
      binaryBase64: await readBase64(file),
      caseFiles: [],
    };
    for (const item of cases) {
      payload.caseFiles.push({name: item.name, content_base64: await readBase64(item)});
    }
    await submitPayload(chat, payload, text, locale);
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
    cases.forEach((item, index) => chat.attachmentNames.set(attachmentIds[index + 1], item.name));
    event(chat, 'user_message', {
      message_id: messageId, text: clean, attachment_ids: attachmentIds, delivery: 'accepted',
    }, null, null);
    chat.title ||= payload.binaryName;
    chat.kind = 'repair';
    chat.started = Date.now();
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
            + '可以点下方「试用示例」用冻结 fixture 跑完整演示；你的二进制仍可作为只读分析证据保留。',
            'The analyzer disassembled the ELF but did not find the MVP2-supported stack '
            + 'overflow pattern (the strcpy call site). This binary is outside the frozen '
            + 'fixture scope, so no repair patch is written. Use "Try the demo" below to run '
            + 'the full signed-fixture demo; your binary remains as read-only analysis evidence.'));
        } else {
          say(chat, t(locale,
            `这个 ELF 的 SHA-256 不是冻结 fixture（${data.task.g4?.binary_sha256?.slice(0, 12) ?? '?'}）。`
            + 'MVP2 只对签名 fixture 写补丁；当前已完成只读分析，不会伪造修复输出。',
            `This ELF is not the frozen fixture (sha256 ${data.task.g4?.binary_sha256?.slice(0, 12) ?? '?'}). `
            + 'MVP2 only patches the signed fixture; the analysis is read-only and no repair '
            + 'output is fabricated.'));
        }
        event(chat, 'g4_actions', {
          id: 'g4-actions-' + data.task.id,
          actions: [{id: 'fixture', kind: 'fixture', label: t(locale, '试用示例', 'Try the demo')}],
        }, 'export');
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
        note: t(locale,
          '选择此契约 = 绑定已签 G2 决策；不重跑审计，不重新投票。',
          'Choosing a contract binds the signed G2 decision; no audit re-run, no new vote.'),
      };
      event(chat, 'awaiting_user', chat.request, 'report');
      state(chat, 'awaiting_user');
    } catch (error) {
      event(chat, 'thinking', {phase: 'finished', duration_ms: 0, summary_code: 'analysis'},
        'collect');
      const reason = error.status === 422
        ? t(locale, '分析器无法处理这个 ELF（请确认它是可供分析器读取的 x86-64 ELF）。',
          'The analyzer could not process this ELF (confirm it is a readable x86-64 ELF).')
        : t(locale, `上传或分析失败：${error.message}。`,
          `Upload or analysis failed: ${error.message}.`);
      say(chat, reason);
      finish(chat, 'failed');
    }
  }

  async function decide(chat, requestId, action) {
    const request = chat.request;
    if (!request || request.request_id !== requestId) return;
    const option = chat.options.find(item => item.id === action);
    if (!option || !option.feasible) return;
    chat.request = null;
    chat.bound = {id: option.id, title_zh: option.title_zh, title_en: option.title_en,
      scope_zh: option.scope_zh, scope_en: option.scope_en};
    event(chat, 'user_response', {request_id: requestId, decision: action}, 'report');
    state(chat, 'running');
    chat.started = Date.now();
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
    sendDownloads(chat, chat.jobId, artifacts, chat.locale, word, verdict);
    const execution = chat.runEnd?.execution === 'completed' ? 'completed'
      : chat.runEnd?.execution === 'cancelled' ? 'cancelled' : 'failed';
    finish(chat, execution);
  }

  function sendDownloads(chat, taskId, artifacts, locale, verdictWord, verdictPayload) {
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
      verdict_word: verdictWord || null,
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
    chat.ended = Date.now();
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

  function activate() {}

  function deactivate() {}

  return {chats, live: true, taskMode: true, create, send, sendFixture, decide,
    start: async () => {}, stop, seed, activate, deactivate};
}
