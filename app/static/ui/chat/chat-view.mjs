import {animateDetails} from '../shared/details-anim.mjs?v=20261120au';
import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261125o';
import {stepCard} from './chat-steps.mjs?v=20261125o';

export function fileDropZone({label, hint, accept = '', multiple = false, onFiles}) {
  const input = el('input', {type: 'file', hidden: true, accept, multiple,
    onchange: () => {
      const files = [...input.files];
      input.value = '';
      if (files.length) onFiles(files);
    }});
  const zone = el('div', {class: 'drop-zone', role: 'button', tabindex: '0',
    'aria-label': label},
    el('span', {class: 'drop-zone-icon'}, icon('file', 20)),
    el('strong', {}, label),
    el('span', {class: 'drop-zone-hint'}, hint),
    input);
  const open = () => input.click();
  zone.addEventListener('click', open);
  zone.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      open();
    }
  });
  zone.addEventListener('dragover', event => {
    event.preventDefault();
    zone.classList.add('dragging');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragging'));
  zone.addEventListener('drop', event => {
    event.preventDefault();
    zone.classList.remove('dragging');
    const files = [...event.dataTransfer.files];
    if (files.length) onFiles(multiple ? files : files.slice(0, 1));
  });
  return zone;
}

export function control(text, onClick, {glyph, compact = false, tone = '', ...attrs} = {}) {
  return el('button', {type: 'button', class: 'control ' + tone + (compact ? ' icon-only' : ''),
    onclick: onClick, 'aria-label': compact ? text : null, title: compact ? text : null, ...attrs},
  glyph ? icon(glyph, 17) : null, compact ? null : text);
}

export function transcript() {
  const items = new Map();
  const commands = new Map();
  const checks = new Map();
  const evaluations = new Map();
  let cursor = 0;
  let active = null;
  const put = (key, event, extra = {}) => items.set(key, {...event, ...extra, key});

  function apply(events) {
    while (cursor < events.length) {
      const event = events[cursor++];
      const {type, payload: p, run_id: run, step_id: step} = event;
      switch (type) {
        case 'user_message': put(p.message_id, event); break;
        case 'message_dispatched': {
          const previous = items.get(p.message_id);
          if (previous) put(p.message_id, previous, {payload: {...previous.payload, delivery: 'accepted'}});
          break;
        }
        case 'assistant_delta': {
          const old = items.get(p.message_id);
          put(p.message_id, old ?? event, {text: (old?.text ?? '') + p.append});
          break;
        }
        case 'assistant_end': {
          const old = items.get(p.message_id);
          if (old) put(p.message_id, old, {finished: p.status});
          break;
        }
        case 'thinking': put(run + ':think:' + step, event); break;
        case 'plan_update': put(run + ':plan', event); break;
        case 'tool_call': put(p.call_id, event); break;
        case 'tool_result': {
          const call = items.get(p.call_id);
          if (call) put(p.call_id, call, {result: p});
          break;
        }
        case 'command': {
          const old = commands.get(p.command_id) ?? {output: '', lines: []};
          const next = p.phase === 'started' ? {...old, ...p, event} :
            p.phase === 'output' ? {...old, output: old.output + p.append, lines: [...old.lines, p]} :
              {...old, ...p};
          commands.set(p.command_id, next);
          if (next.event) put(p.command_id, next.event, {command: next});
          break;
        }
        case 'file_change': put(p.change_id, event); break;
        case 'awaiting_user': put(p.request_id, event); active = p.request_id; break;
        case 'user_response': {
          const old = items.get(p.request_id);
          if (old) put(p.request_id, old, {decision: p.decision ?? 'answered'});
          active = null;
          break;
        }
        case 'error': put(run + ':error:' + event.seq, event); break;
        case 'verification':
          if (p.kind === 'check') checks.set(run, [...(checks.get(run) ?? []), p]);
          else evaluations.set(run, p);
          put(run + ':verification', event, {checks: checks.get(run) ?? [], evaluation: evaluations.get(run)});
          break;
        case 'g4_analysis': put(run + ':analysis', event); break;
        case 'g4_g2': put(run + ':g2', event); break;
        case 'g4_progress': put(p.id, event); break;
        case 'assistant_reply': put(p.message_id, event); break;
        case 'g4_live_audit': put(p.id, event); break;
        case 'binary_ready': put(p.id, event); break;
        case 'case_prompt': put(p.id, event); break;
        case 'case_received': put(p.id, event); break;
        case 'g4_downloads': put(p.id, event); break;
        case 'g4_actions': put(p.id, event); break;
        case 'run_end': {
          if (active && items.get(active)?.run_id === run) {
            put(active, items.get(active), {decision: p.execution});
            active = null;
          }
          for (const [key, item] of items) {
            if (item.run_id === run && (
              (item.type === 'thinking' && item.payload.phase === 'started') ||
              (item.type === 'tool_call' && !item.result) ||
              (item.type === 'command' && item.command.duration_ms == null))) {
              put(key, item, {ended: p.execution});
            }
          }
          const evaluation = evaluations.get(run);
          if (p.kind === 'repair' || p.execution !== 'completed' || p.evaluation_id) {
            put(run + ':summary', event, {evaluation: evaluation?.evaluation_id === p.evaluation_id ? evaluation : null,
              checks: checks.get(run) ?? []});
          }
          break;
        }
      }
    }
    return items.values();
  }
  return {apply};
}

const controlRow = (...children) => el('div', {class: 'controls-row'}, children);
const detail = (summary, ...children) =>
  animateDetails(el('details', {class: 'disclosure'},
    el('summary', {}, icon('chevron', 14), summary),
    el('div', {class: 'detail-body'}, children)));
const seconds = ms => (ms / 1000).toFixed(ms < 10_000 ? 1 : 0) + ' s';
const time = (value, locale) => el('time', {datetime: value},
  new Intl.DateTimeFormat(locale, {hour: '2-digit', minute: '2-digit', second: '2-digit'}).format(new Date(value)));
const meta = (...children) => el('span', {class: 'event-meta'}, children);
const chips = (text, mood) => el('span', {class: 'chip', 'data-mood': mood}, text);
const checkRows = (checks, t) => checks.map(check =>
  el('div', {class: 'check-row'}, t(check.route) + ' · ' + check.level, chips(t(check.status), check.status)));

function output(text, t, {diff = false, reveal = false, lines = null, terminal = false} = {}) {
  const copy = control(t('copy'), async event => {
    const button = event.currentTarget;
    try {
      await navigator.clipboard.writeText(text);
      if (button.isConnected) button.textContent = t('copied');
    } catch {
      // Clipboard availability is browser controlled.
    }
  });
  function code(value) {
    if (diff) return el('pre', {tabindex: '0'}, value.split('\n').map(line =>
      el('span', {class: 'diff-line ' + (line.startsWith('+') ? 'addition' : line.startsWith('-') ? 'removal' : '')}, line)));
    if (lines && !reveal) return el('pre', {tabindex: '0'}, lines.map(line =>
      el('span', {class: line.channel === 'stderr' ? 'stderr' : ''}, line.append)));
    return el('pre', {tabindex: '0'}, value);
  }
  return el('div', {class: 'output' + (terminal ? ' terminal-output' : '')},
    el('div', {class: 'output-head'}, t('output'), copy), code(reveal ? text.slice(0, 310) + '…' : text),
    reveal ? detail(t('showMore'), code(text)) : null);
}

function approval(item, ctx) {
  // Revision 2.2: the contract/case details stay hidden. The user confirms
  // through inline chat chips; the backend still enforces the binding digest.
  const {t, chat, engine, locale} = ctx;
  const p = item.payload;
  const status = item.decision;
  if (p.kind === 'repair_plan') {
    // There is no signed-plan choice in the product: plans come only from the
    // live AI audit card. Historical events keep this short truth note.
    return el('p', {class: 'inline-note'}, t('livePlanFirst'));
  }
  const complete = Boolean(chat.contract?.review_binding_digest &&
    chat.contract?.review_binding?.original_sha256 && chat.contract?.review_binding?.test_manifest_sha256);
  if (status === 'approve') {
    const activeRun = chat.execution?.run_id && chat.execution?.terminal !== true;
    const canStart = chat.startReady && !activeRun && !chat.execution?.run_id && item === ctx.latestApproval;
    return el('div', {class: 'inline-actions'}, icon('check', 15),
      el('span', {}, t('approved') + (chat.reviewer ? ' · ' + chat.reviewer : '')),
      canStart ? control(t('start'), () => engine.start(chat, locale), {tone: 'primary'}) : null);
  }
  if (status) {
    const label = status === 'deny' ? t('denied') : status === 'edit' ? t('saveReview') : t(status);
    return el('div', {class: 'inline-actions'}, el('span', {}, label),
      status === 'deny' && engine.reopen
        ? control(t('reviewAgain'), () => engine.reopen(chat)) : null);
  }
  return el('div', {class: 'inline-actions', role: 'group', 'aria-label': t('approval')},
    control(t('approve'), () => {
      chat.reviewer = chat.reviewer || 'M2';
      engine.decide(chat, p.request_id, 'approve', null, chat.reviewer);
    }, {tone: 'primary', disabled: !complete}),
    control(t('deny'), () => engine.decide(chat, p.request_id, 'deny')),
    complete ? null : el('span', {class: 'muted'}, t('bindingMissing')));
}

function summary(item, t, chat, engine) {
  // One final assistant message with the verdict and the download/evidence
  // entries; the score tables stay in the evidence bundle.
  const {payload: p, evaluation} = item;
  const result = evaluation?.verdict?.outcome;
  const archive = chat.jobId ? el('a', {class: 'control', href: '/ui/#task/' + encodeURIComponent(chat.jobId)},
    icon('tasks', 16), t('openArchive')) : null;
  const refresh = !evaluation && chat.jobId && engine.refresh
    ? control(t('refresh'), () => engine.refresh(chat)) : null;
  const line = result ? t(result) : (p.execution === 'cancelled' ? t('cancelled') : t('noVerdict'));
  return el('article', {class: 'message assistant'}, el('div', {class: 'reply-body'},
    el('strong', {}, line),
    p.execution === 'failed' && !result ? el('p', {}, t('reason')) : null,
    el('div', {class: 'inline-actions'}, archive, refresh)));
}

const STEP_KEYS = {
  collect: 'stepCollect', freeze: 'stepFreeze', analyze: 'stepAnalyze', audit: 'stepAudit',
  decision: 'stepDecision', repair: 'stepRepair', verify: 'stepVerify', export: 'stepExport',
};

function activityStep(item, t) {
  return t(STEP_KEYS[item.step_id] ?? 'activity');
}

// Revision 2.2 keeps command/file/verification rows out of the conversation;
// they are now rendered from the task's persisted journal in the right-side
// execution log, so the operator can follow every real runner step.
function activityRow(item, t) {
  const p = item.payload || {};
  const step = activityStep(item, t);
  if (item.type === 'command') {
    const command = item.command || {};
    const status = command.phase === 'started' ? t('commandStarted')
      : command.exit_code != null ? t('commandFinished') : t('commandRunning');
    const output = typeof command.output === 'string' ? command.output.trim() : '';
    return el('details', {class: 'activity-row'},
      el('summary', {},
        el('span', {class: 'activity-kind'}, step),
        el('span', {class: 'activity-status'}, status)),
      output ? el('pre', {class: 'activity-output'},
        output.length > 4000 ? output.slice(-4000) : output) : null);
  }
  if (item.type === 'journal_error') {
    return el('p', {class: 'activity-row activity-error'},
      icon('info', 13), el('span', {}, step + (p.code ? ' · ' + p.code : '')));
  }
  if (item.type === 'file_change') {
    const files = (p.files || []).map(file => file.display_path).filter(Boolean);
    return el('p', {class: 'activity-row'},
      icon('file', 13), el('span', {}, step + (files.length ? ' · ' + files.join(', ') : '')));
  }
  const verdict = p.verdict || p.kind || '';
  return el('p', {class: 'activity-row'},
    icon('check', 13), el('span', {}, step + (verdict ? ' · ' + verdict : '')));
}

const CHAT_STEP_KEYS = {
  collect: 'stepCollect', freeze: 'stepFreeze', analyze: 'stepAnalyze', audit: 'stepAudit',
  decision: 'stepDecision', repair: 'stepRepair', verify: 'stepVerify', export: 'stepExport',
};
const stepLabel = (code, t) => t(CHAT_STEP_KEYS[code] ?? code);
const shortSha = value => value ? String(value).slice(0, 16) + '…' : '—';

function statusMood(label) {
  const text = String(label ?? '').toLowerCase();
  if (!text) return 'neutral';
  if (/运行中|进行中|running|in.?progress|progress/.test(text)) return 'running';
  if (/失败|错误|拒绝|未通过|failed|failure|error|rejected|unverified|unsupported/.test(text)) return 'failed';
  if (/完成|成功|通过|有效|completed|complete|success|passed|proceed|verified|valid/.test(text)) return 'success';
  return 'neutral';
}

function runningDots() {
  return el('span', {class: 'running-dots', 'aria-hidden': 'true'},
    el('i'), el('i'), el('i'));
}

function statusBadge(label) {
  const mood = statusMood(label);
  return el('span', {class: 'gen-badge', 'data-mood': mood}, label,
    mood === 'running' ? runningDots() : null);
}

function genCard(kind, glyph, title, badge, ...children) {
  return el('article', {class: 'message assistant gen-card gen-' + kind},
    el('header', {class: 'gen-head'},
      el('span', {class: 'gen-mark'}, icon(glyph, 17)),
      el('strong', {}, title),
      badge ? statusBadge(badge) : null),
    el('div', {class: 'gen-body'}, ...children));
}

function genRows(rows) {
  return el('div', {class: 'gen-rows'}, rows.map(([name, value]) =>
    el('div', {class: 'gen-row'}, el('span', {}, name), el('strong', {}, value ?? '—'))));
}

function genAnalysis(p, t) {
  return genCard('analysis', 'file', t('analysisTitle'), p.cwe,
    genRows([
      [t('analysisFunction'), p.function],
      [t('analysisAddress'), p.address],
      [t('analysisInstruction'), p.instruction],
      [t('analysisCases'), (p.counts?.valid ?? 0) + ' valid · ' + (p.counts?.poc ?? 0) + ' PoC'],
    ]),
    el('p', {class: 'gen-note'}, t('caseScopeNote')));
}

function genG2(p, t) {
  return genCard('g2', 'info', t('g2Record'), p.decision,
    genRows([
      [t('g2Audit'), p.report_id + ' · ' + p.runs + ' runs · schema ' + (p.schema_valid ? 'valid' : 'invalid')
        + ' · M1 ' + (p.score_m1 ?? '—')],
      [t('g2Decision'), p.decision + ' · signed ' + shortSha(p.record_sha256)],
      [t('g2Plan'), p.plan_id + ' · ' + p.strategy + ' · contract ' + shortSha(p.contract_sha256)],
    ]),
    el('p', {class: 'gen-note'}, t('bindingNote')));
}

function genProgress(p, t) {
  const steps = p.steps || [];
  const done = steps.filter(step => step.status === 'completed').length;
  return genCard('progress', 'terminal', t('repairRun'),
    p.execution ? t(p.execution) : t('running'),
    el('div', {class: 'gen-progress-meta'}, el('strong', {}, done + ' / ' + steps.length)),
    el('ol', {class: 'gen-steps'}, steps.map(step =>
      el('li', {'data-status': step.status},
        el('span', {class: 'gen-step-dot'}),
        el('span', {}, stepLabel(step.label_code, t)),
        el('span', {class: 'gen-step-state'}, t(step.status) + ' · ' + step.status)))));
}

function genOutcome(p, t) {
  const links = [p.candidate, p.manifest, p.verdict_file].filter(Boolean);
  const rejected = ['rejected', 'unverified', 'unsupported', 'error'].includes(p.verdict_word);
  const children = [];
  if (p.candidate_sha256) {
    children.push(el('p', {class: 'gen-note mono'},
      'candidate ' + shortSha(p.candidate_sha256)));
  }
  if (rejected && (p.verdict_reason || (p.failed_criteria || []).length)) {
    children.push(el('p', {class: 'gen-note verdict-reason'},
      t('verdictRejectedReason') + ' ' + (p.verdict_reason || (p.failed_criteria || []).join(' · '))));
  }
  children.push(el('div', {class: 'gen-downloads'}, links.map(link =>
    el('a', {class: 'gen-download', href: link.href, download: '',
      title: link.sha256 ? 'sha256: ' + link.sha256 : null},
    icon('download', 16), el('span', {}, link.label)))));
  return genCard('outcome', 'check', rejected ? t('repairNotAccepted') : t('repairComplete'),
    p.verdict_word || t('noVerdict'), ...children);
}

const ASSISTANT_ACTION_KEYS = {
  attach: 'attachBinary', start: 'start', continue: 'continue', rerun: 'rerun',
  change_scope: 'change_scope', download: 'download', evidence: 'evidence', retry: 'retry',
};

function assistantActionLabel(action, t) {
  if (action.label) return action.label;
  const code = String(action.label_code || action.kind || '').replace(/^action\./, '');
  const key = ASSISTANT_ACTION_KEYS[action.kind] || code;
  const localized = t(key);
  return localized === key ? (code || key) : localized;
}

function planReasonLabel(code, t) {
  const raw = String(code || 'plan_not_allowed');
  if (raw.startsWith('edit_kind_not_allowed:')) {
    return t('liveReasonEditKind') + ' (' + raw.split(':')[1] + ')';
  }
  const labels = {
    redirect_size_invalid: t('liveReasonRedirectSize'),
    redirect_count_invalid: t('liveReasonRedirectCount'),
    code_budget_exceeded: t('liveReasonCodeBudget'),
    data_budget_exceeded: t('liveReasonDataBudget'),
    edit_address_invalid: t('liveReasonAddress'),
    plan_fixture_mismatch: t('liveReasonFixture'),
    plan_contract_mismatch: t('liveReasonContract'),
    plan_not_allowed: t('liveReasonPlan'),
  };
  return labels[raw] || raw;
}

function decodeBase64Text(value) {
  try {
    const bytes = Uint8Array.from(atob(String(value || '')), c => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return '';
  }
}

function showAttachment(chat, id, t) {
  const file = chat.attachmentFiles?.get(id);
  if (!file) return;
  const close = control(t('close'), () => popup.close(), {glyph: 'x', compact: true});
  let body;
  if (file.kind === 'case') {
    const text = decodeBase64Text(file.base64);
    body = el('pre', {class: 'attachment-text'}, text || t('previewUnavailable'));
  } else {
    const bytes = (() => {
      try { return Uint8Array.from(atob(String(file.base64 || '')), c => c.charCodeAt(0)); }
      catch { return new Uint8Array(); }
    })();
    const preview = [...bytes.slice(0, 256)].map(byte => byte.toString(16).padStart(2, '0')).join(' ');
    const href = file.base64 ? 'data:application/octet-stream;base64,' + file.base64 : null;
    body = el('div', {class: 'attachment-binary'},
      el('p', {class: 'gen-note'}, `${bytes.length} bytes · ${t('binaryPreview')}`),
      el('pre', {class: 'attachment-text'}, preview || t('previewUnavailable')),
      href ? el('a', {class: 'control', href, download: file.name}, icon('download', 16), t('download')) : null);
  }
  const popup = el('dialog', {class: 'popup attachment-preview', 'aria-label': file.name},
    el('header', {}, el('h2', {}, file.name), close),
    el('div', {class: 'attachment-preview-body'}, body));
  popup.addEventListener('close', () => popup.remove());
  document.body.append(popup);
  popup.showModal();
}

function genLiveAudit(p, ctx, t) {
  const {engine, chat} = ctx;
  const audit = p.live_audit || {status: 'idle', runs: []};
  const selected = p.selected_plan;
  const runs = audit.runs || [];
  const status = audit.status || 'idle';
  const statusLabel = t(status === 'idle' ? 'liveAuditIdle' : status === 'running'
    ? 'liveAuditRunning' : status === 'completed' ? 'liveAuditCompleted' : 'liveAuditFailed');
  const children = [];
  children.push(el('p', {class: 'gen-note'}, t('liveAuditOnlyPath')));
  if (status === 'idle') {
    children.push(control(t('liveAuditStart'), () => engine.startLiveAudit?.(chat),
      {tone: 'primary', glyph: 'arrow'}));
  }
  if (status !== 'idle') {
    children.push(el('p', {class: 'gen-note'},
      `${t('liveAuditRuns')}: ${runs.length} / 3` + (audit.error ? ` · ${audit.error}` : '')));
  }
  if (status === 'running' && !runs.length) {
    children.push(el('p', {class: 'muted live-audit-hint'}, t('liveAuditStarted')));
  }
  if (status === 'completed' && runs.length) {
    const cards = runs.map(run => {
      const picked = selected && Number(selected.run_index) === Number(run.run_index);
      const row = [
        el('div', {class: 'live-plan-head'},
          el('strong', {}, 'run ' + run.run_index),
          statusBadge(run.schema_valid ? t('liveAuditSchemaOk') : t('liveAuditSchemaBad'))),
        el('p', {class: 'gen-note mono'},
          'canonical ' + shortSha(run.canonical_sha256 || run.plan_sha256)),
      ];
      if ((run.critical_errors || []).length) {
        row.push(el('p', {class: 'gen-note'}, run.critical_errors.join(' · ')));
      }
      if (run.selectable === false) {
        row.push(el('p', {class: 'gen-note plan-unavailable'}, t('livePlanUnavailable')
          .replace('{reason}', planReasonLabel(run.select_reason, t))));
      } else {
        row.push(control(picked ? t('liveAuditSelected') : t('liveAuditSelect'),
          () => engine.selectLivePlan?.(chat, run.run_index),
          {tone: picked ? '' : 'primary'}));
      }
      return el('div', {class: 'live-plan' + (picked ? ' selected' : '')}, ...row);
    });
    children.push(el('div', {class: 'live-plans'}, cards));
  }
  if (selected) {
    if (p.guest_available === false) {
      children.push(el('p', {class: 'gen-note verdict-reason'}, t('liveGuestRequired')));
    }
    children.push(el('div', {class: 'live-guest'},
      el('label', {},
        el('input', {type: 'checkbox', checked: p.live_guest,
          disabled: p.guest_available === false,
          onchange: event => engine.setLiveGuest?.(chat, event.target.checked)}),
        ' ' + t('liveAuditGuest')),
      p.guest_available === false
        ? el('p', {class: 'gen-note'}, t('liveGuestUnavailable')) : null));
    children.push(control(t('liveAuditStart'), () => engine.startLivePlan?.(chat),
      {tone: 'primary', glyph: 'arrow'}));
  }
  if (audit.error || p.error) {
    children.push(el('p', {class: 'gen-note'}, t('liveAuditFallback')));
  }
  return genCard('live', 'terminal', t('liveAuditTitle'), statusLabel, ...children);
}

export function renderItem(item, ctx) {
  const {t, locale, chat, engine} = ctx;
  const {payload: p, type, ts} = item;
  const stamp = time(ts, locale);
  const card = (glyph, title, status, milliseconds, ...children) => stepCard({
    glyph, title, status, statusLabel: status ? t(status) : null, time: stamp,
    duration: typeof milliseconds === 'number' ? seconds(milliseconds) : milliseconds, children,
  });
  switch (type) {
    case 'user_message':
      return el('article', {class: 'message user', 'aria-label': t('you')}, el('p', {class: 'message-body'}, p.text),
        p.attachment_ids.map(id => el('button', {type: 'button', class: 'message-file',
          onclick: () => showAttachment(chat, id, t), title: t('previewFile')},
        icon('file', 14), chat.attachmentNames.get(id) ?? id)),
        p.delivery === 'queued' ? chips(t('queued')) : null);
    case 'assistant_delta':
      return el('article', {class: 'message assistant', 'aria-label': t('assistant')},
        el('div', {class: 'reply-body'}, item.text, !item.finished ? el('span', {class: 'caret', 'aria-hidden': 'true'}) : null));
    case 'thinking':
      // Revision 2.2: progress lives in the right-side panels; the chat column
      // keeps conversation text only.
      return null;
    case 'plan_update': {
      const steps = p.steps || [];
      const done = steps.filter(step => step.status === 'completed').length;
      return el('p', {class: 'inline-note'}, t('stepCount') + ' ' + done + ' / ' + steps.length);
    }
    case 'file_change':
    case 'command':
    case 'verification':
    case 'journal_error':
      return activityRow(item, t);
    case 'tool_call':
      // Tool rows stay in the evidence bundle; they never render as chat cards.
      return null;
    case 'awaiting_user': return approval(item, ctx);
    case 'error':
      return el('p', {class: 'inline-error'}, icon('info', 14), t('error') + ' · ',
        el('code', {}, p.code),
        p.retry.kind === 'manual' && chat.phase === 'failed' && chat.run === item.run_id
          ? control(t('retry'), () => engine.start(chat, locale, true)) : null);
    case 'g4_live_audit': return genLiveAudit(p, ctx, t);
    case 'binary_ready': {
      const f = p.finding || {};
      return el('article', {class: 'message assistant binary-ready'},
        el('div', {class: 'binary-ready-head'}, icon('check', 16),
          el('strong', {}, t('binaryRecognized')),
          el('span', {class: 'muted'}, p.binary_name)),
        el('p', {class: 'message-body'}, p.supported
          ? t('binarySupported').replace('{function}', f.function || '—')
            .replace('{address}', f.address || '—').replace('{cwe}', f.cwe || '—')
          : t('binaryUnsupported')),
        el('code', {class: 'sha-line'}, (p.binary_sha256 || '').slice(0, 24) + '…'));
    }
    case 'case_prompt':
      if (!chat.pendingBinary) return el('p', {class: 'inline-note'}, t('casesAccepted'));
      return el('div', {class: 'message assistant case-ready'},
        el('p', {class: 'inline-note'}, t('addCasesNow')),
        fileDropZone({label: t('caseDrop'), hint: t('caseDropHint'),
          accept: '.json', multiple: true,
          onFiles: files => engine.submitCases?.(chat, files, chat.locale)}));
    case 'case_received': return el('p', {class: 'inline-note'},
      t('casesReceived').replace('{count}', String(p.count || 0)));
    case 'assistant_reply': {
      const mode = p.mode === 'llm' ? t('assistantModeLlm')
        : p.mode === 'llm (not wired)' ? t('assistantModeNotWired')
          : t('assistantModeDeterministic');
      return el('article', {class: 'message assistant assistant-reply'},
        el('div', {class: 'assistant-reply-head'},
          el('span', {class: 'assistant-avatar'}, icon('info', 14)),
          el('strong', {}, t('assistant')),
          el('span', {class: 'assistant-mode-pill', 'data-mode': p.mode || 'deterministic'}, mode)),
        el('p', {class: 'message-body'}, p.reply),
        (p.actions || []).length ? el('div', {class: 'assistant-actions'},
          (p.actions || []).map(action => el('span', {class: 'assistant-chip',
            'data-kind': action.kind}, assistantActionLabel(action, t)))) : null);
    }
    case 'g4_analysis': return genAnalysis(p, t);
    case 'g4_g2': return genG2(p, t);
    case 'g4_progress': return genProgress(p, t);
    case 'g4_downloads': return genOutcome(p, t);
    case 'g4_actions': {
      const actions = p.actions ?? [];
      return el('article', {class: 'message assistant'}, el('div', {class: 'reply-body'},
        el('div', {class: 'inline-actions'}, actions.map(action =>
          control(action.label, () => engine.sendFixture?.(chat, chat.locale),
            {tone: 'primary', glyph: 'arrow'})))));
    }
    case 'run_end': return summary(item, t, chat, engine);
  }
}

export function displayTitle(chat, t) {
  return chat.titleKey ? t(chat.titleKey) : chat.title || t('new');
}
