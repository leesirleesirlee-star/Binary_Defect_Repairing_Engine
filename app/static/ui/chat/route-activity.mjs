/**
 * Route A live repair-run monitor.
 *
 * The framework is sample-agnostic: tasks are discovered from /api/tasks and
 * each task is followed through its own SSE journal. No fixture, contract,
 * input or verdict data is hard-coded here; this module only renders the run
 * framework and the persisted events returned by the browser API.
 *
 * All chrome copy comes from the shared chat catalogue (`chat-copy.mjs`), so the
 * monitor reads in the same locale as the rest of the chat page. The locale is
 * taken from the document (`lang`), then the stored chat preference, then `en`.
 */
import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261120au';
import {LANGUAGE_CODES} from '../shared/languages.mjs?v=20261120au';
import {label as translate} from './chat-copy.mjs?v=20261123e';
import {disclosure} from './chat-steps.mjs?v=20261121j';

const STEPS = ['collect', 'freeze', 'analyze', 'audit', 'decision', 'repair', 'verify', 'export'];
const PHASE_KEYS = {
  draft: 'draft', not_started: 'notStarted', screening: 'screening', analyzing: 'analyzing',
  repair: 'stepRepair', verification: 'stepVerify', done: 'completed', finished: 'completed',
  started: 'started',
};
const STEP_KEYS = {
  collect: 'stepCollect', freeze: 'stepFreeze', analyze: 'stepAnalyze', audit: 'stepAudit',
  decision: 'stepDecision', repair: 'stepRepair', verify: 'stepVerify', export: 'stepExport',
};
const EVENT_TYPES = [
  'run_state', 'plan_update', 'corpus_update', 'command', 'file_change',
  'verification', 'audit_runs', 'awaiting_user', 'error', 'run_end',
  'user_message', 'message_dispatched', 'assistant_delta', 'assistant_end',
  'thinking', 'tool_call', 'tool_result', 'user_response',
];
const FALLBACK_LOCALE = 'en';
// Follow live event streams only for tasks that can still emit events. A task
// that is draft/finished/failed keeps no stream open; otherwise a dozen idle
// SSE connections exhaust the browser's per-origin connection budget and every
// other page on this host (the archive) stalls while loading.
const LIVE_PHASES = new Set(['queued', 'waiting_for_executor', 'running', 'cancelling']);
const state = {monitor: null, logA: null, logB: null, cards: new Map(), timer: null, mounted: false,
  generation: 0, locale: null};

function storedLocale() {
  try { return localStorage.getItem('binaryrepair.chat.language'); } catch { return null; }
}

function chatLocale() {
  const candidates = [document.documentElement.lang, storedLocale(), FALLBACK_LOCALE];
  return candidates.find(code => typeof code === 'string' && LANGUAGE_CODES.includes(code)) ?? FALLBACK_LOCALE;
}

const t = (key, count) => translate(chatLocale(), key, count);
const fill = (template, values) => Object.entries(values)
  .reduce((text, [name, value]) => text.split('{' + name + '}').join(String(value)), template);
const runCount = count => t('runCount', count);
const runLabel = ordinal => t('runLabel', ordinal);
const stateLabel = value => (value === undefined || value === null || value === ''
  ? '—' : t(PHASE_KEYS[value] || String(value)));
const short = (value, head = 14, tail = 8) => {
  const text = String(value ?? '');
  return text.length > head + tail + 1 ? text.slice(0, head) + '…' + text.slice(-tail) : text;
};
const chip = (text, tone = '') => el('span', {class: 'ra-chip', 'data-tone': tone}, text);

async function session() {
  const response = await fetch('/api/session', {credentials: 'same-origin', cache: 'no-store'});
  if (!response.ok) throw new Error('session unavailable');
  return response.json();
}

async function tasks() {
  const response = await fetch('/api/tasks?limit=50', {credentials: 'same-origin', cache: 'no-store'});
  if (!response.ok) throw new Error('task list unavailable');
  const data = await response.json();
  return Array.isArray(data.tasks) ? data.tasks : [];
}

function buildEventLog(route, empty = t('noRunEvents')) {
  const count = el('span', {class: 'ra-count'}, runCount(0));
  const body = el('div', {class: 'ra-log-body'}, el('p', {class: 'ra-muted'}, empty));
  const heading = el('span', {class: 'ra-heading'},
    el('span', {class: 'ra-title'}, icon('terminal', 15), t(route) + ' · ' + t('activity')), count);
  const panel = disclosure({className: 'ra-monitor ra-event-log', heading, open: true}, body);
  return {panel, body, count, groups: 0};
}

function taskCard(task, index) {
  const id = task.id;
  const labelText = runLabel(index + 1);
  const steps = el('div', {class: 'ra-steps'});
  const status = el('span', {class: 'ra-status'}, t('connecting'));
  const artifacts = el('div', {class: 'ra-artifacts', hidden: true});
  const target = el('span', {class: 'ra-target'},
    fill(t('phaseValue'), {value: stateLabel(task.phase || 'unknown')}));
  const card = el('article', {class: 'ra-task'},
    el('header', {class: 'ra-task-head'},
      el('div', {}, el('strong', {}, labelText), target),
      el('div', {class: 'ra-task-state'}, el('span', {class: 'ra-dot'}), status)),
    steps,
    artifacts);
  const logRows = el('div', {class: 'ra-log-rows'}, el('p', {class: 'ra-muted'}, t('noRunEvents')));
  const logStatus = el('span', {class: 'ra-log-status'}, t('connecting'));
  const logHeading = el('span', {class: 'ra-log-heading'}, el('strong', {}, labelText), logStatus);
  const logGroup = disclosure({className: 'ra-log-run', heading: logHeading, open: true}, logRows);
  if (state.logA) {
    // Only the single placeholder row belongs to the log itself; per-run rows
    // also contain `.ra-muted` placeholders, so scope the reset to the log root.
    if (state.logA.groups === 0) state.logA.body.replaceChildren();
    state.logA.body.append(logGroup);
    state.logA.groups += 1;
    state.logA.count.textContent = runCount(state.logA.groups);
  }
  const api = {task, card, logGroup, logRows, logStatus, steps, status, artifacts, target,
    labelText, phase: task.phase, live: LIVE_PHASES.has(task.phase), lastSeq: 0, source: null, ended: false};
  state.cards.set(id, api);
  connect(api);
  return card;
}

function eventSummary(record) {
  const p = record.payload || {};
  if (record.type === 'run_state') return p.status;
  if (record.type === 'plan_update') return (p.steps || []).map(step => `${step.step_id}:${step.status}`).join(' · ');
  if (record.type === 'corpus_update') return `cases ${p.total ?? '—'} · ${JSON.stringify(p.counts || {})}`;
  if (record.type === 'command') return `${p.phase || '—'} ${p.label_code || ''}${p.exit_code != null ? ' · exit ' + p.exit_code : ''}`;
  if (record.type === 'file_change') return `${p.stage || '—'} · ${(p.files || []).map(file => file.display_path).join(', ')}`;
  if (record.type === 'verification' && p.kind === 'check') return `${p.level || ''} ${p.status || 'not_run'} ${p.obligation_id || ''}`;
  if (record.type === 'verification') return p.verdict ? p.verdict.outcome : t('verdictNull');
  if (record.type === 'audit_runs') return runCount((p.runs || []).length);
  if (record.type === 'awaiting_user') return `${p.kind || 'decision'} · ${(p.allowed || []).join(' / ')}`;
  if (record.type === 'error') return p.code || 'error';
  if (record.type === 'run_end') return p.execution || 'ended';
  return p.summary || record.type;
}

function applyPlan(api, steps) {
  const byStep = Object.fromEntries((steps || []).map(step => [step.step_id, step]));
  api.steps.replaceChildren(...STEPS.map(id => {
    const status = byStep[id]?.status || 'pending';
    return el('span', {class: 'ra-step', 'data-status': status},
      el('span', {class: 'ra-step-name'}, t(STEP_KEYS[id] || id)),
      el('span', {class: 'ra-step-state'}, stateLabel(status)));
  }));
}

function appendEvent(api, record) {
  if (record.seq <= api.lastSeq) return;
  api.lastSeq = record.seq;
  // Each rendered event row nests its own `.ra-muted` raw-time span, so scope
  // the placeholder reset to the log root or every event wipes the previous rows.
  if (api.logRows.querySelector(':scope > .ra-muted')) api.logRows.replaceChildren();
  if (record.type === 'plan_update') applyPlan(api, record.payload?.steps);
  if (record.type === 'run_state') {
    api.status.textContent = stateLabel(record.payload?.status);
    api.logStatus.textContent = stateLabel(record.payload?.status);
  }
  if (record.type === 'run_end') {
    api.status.textContent = stateLabel(record.payload?.execution);
    api.logStatus.textContent = stateLabel(record.payload?.execution);
    api.ended = true;
    api.source?.close();
    loadArtifacts(api);
  }
  const row = el('details', {class: 'ra-event', 'data-type': record.type},
    el('summary', {},
      el('span', {class: 'ra-seq'}, '#' + record.seq),
      el('strong', {}, record.type),
      chip(record.source === 'synthetic' ? t('preview') : record.source, record.source === 'synthetic' ? 'warn' : ''),
      el('span', {class: 'ra-event-summary'}, eventSummary(record))),
    el('div', {class: 'ra-raw'},
      el('span', {class: 'ra-muted'}, `${record.step_id || '—'} · ${record.ts || ''}`),
      el('pre', {}, JSON.stringify({...record, conversation_id: t('hiddenRunId')}, null, 2))));
  api.logRows.append(row);
}

function connect(api) {
  const id = api.task.id;
  if (api.source) return;
  api.ended = false;
  api.status.textContent = t('connecting');
  api.logStatus.textContent = t('connecting');
  try {
    const source = new EventSource('/api/tasks/' + encodeURIComponent(id) + '/events');
    api.source = source;
    const handler = event => {
      try {
        appendEvent(api, JSON.parse(event.data));
      } catch { /* malformed lines are ignored; the server closes on gaps. */ }
    };
    EVENT_TYPES.forEach(type => source.addEventListener(type, handler));
    source.addEventListener('journal_gap', () => {
      api.status.textContent = t('journalGap');
      api.ended = true;
      source.close();
    });
    source.onerror = () => {
      if (api.ended) return;
      if (!api.live) {
        // Terminal/draft journals replay once and then end. Close instead of
        // letting EventSource reconnect forever and exhaust the browser's
        // per-origin connection budget.
        api.ended = true;
        source.close();
        api.status.textContent = stateLabel(api.phase);
        api.logStatus.textContent = stateLabel(api.phase);
      } else if (source.readyState === EventSource.CLOSED) {
        api.status.textContent = t('connectionClosed');
      }
    };
  } catch {
    api.status.textContent = t('cannotConnect');
  }
}

async function loadArtifacts(api) {
  try {
    const response = await fetch('/api/tasks/' + encodeURIComponent(api.task.id) + '/artifacts',
      {credentials: 'same-origin', cache: 'no-store'});
    if (!response.ok) return;
    const data = await response.json();
    if (!(data.artifacts || []).length) return;
    api.artifacts.hidden = false;
    api.artifacts.replaceChildren(el('span', {class: 'ra-muted'}, t('artifactsPrefix')),
      ...data.artifacts.map(item => el('a', {
        class: 'ra-artifact', href: item.download_url, download: item.display_path,
      }, icon('download', 12), item.display_path)));
  } catch { /* no artifacts until the runner writes them */ }
}

function buildMonitor() {
  const count = el('span', {class: 'ra-count'}, runCount(0));
  const list = el('div', {class: 'ra-task-list'}, el('p', {class: 'ra-muted'}, t('loadingRuns')));
  const refresh = el('button', {type: 'button', class: 'ra-refresh', title: t('refresh')},
    icon('refresh', 14), t('refresh'));
  refresh.addEventListener('click', event => {
    event.stopPropagation();
    refreshTasks(list, count);
  });
  const heading = el('span', {class: 'ra-heading'},
    el('span', {class: 'ra-title'}, icon('terminal', 15), t('route_a') + ' · ' + t('runMonitor')),
    el('span', {class: 'ra-live'}, el('span', {class: 'ra-dot'}), t('live')),
    count,
    refresh);
  const monitor = disclosure({className: 'ra-monitor', heading, open: true},
    el('div', {class: 'ra-body'}, list));
  state.monitor = monitor;
  if (!state.logA) state.logA = buildEventLog('route_a');
  refreshTasks(list, count);
  return monitor;
}

function clearCards() {
  for (const api of state.cards.values()) {
    api.source?.close();
    api.logGroup?.remove();
    api.card.remove();
  }
  state.cards.clear();
  if (state.logA) {
    state.logA.body.replaceChildren(el('p', {class: 'ra-muted'}, t('noRunEvents')));
    state.logA.groups = 0;
    state.logA.count.textContent = runCount(0);
  }
}

async function refreshTasks(list, count) {
  const generation = state.generation;
  try {
    await session();
    const all = await tasks();
    if (generation !== state.generation) return;
    const candidates = all.filter(task => !task.demo && task.phase !== 'preview');
    const visible = candidates.slice(0, 12);
    count.textContent = runCount(visible.length);
    if (!visible.length) {
      list.replaceChildren(el('p', {class: 'ra-muted'}, t('noRuns')));
      return;
    }
    if (list.querySelector('.ra-error') ||
        (list.querySelector('.ra-muted') && !list.querySelector('.ra-task'))) list.replaceChildren();
    visible.forEach((task, index) => {
      if (state.cards.has(task.id)) return;
      list.append(taskCard(task, index));
    });
    for (const task of visible) {
      const card = state.cards.get(task.id);
      if (!card) continue;
      const phaseChanged = task.phase !== card.phase;
      if (card.source?.readyState === EventSource.CLOSED) card.source = null;
      card.phase = task.phase;
      card.live = LIVE_PHASES.has(task.phase);
      if (card.target) {
        card.target.textContent = fill(t('phaseValue'), {value: stateLabel(task.phase || 'unknown')});
      }
      // Re-arm a stream that was closed during a draft/terminal replay. Also
      // replay once when a task changes phase, so a fast draft→start→failed
      // transition cannot leave the card without its journal rows.
      if (!card.source && (card.live || phaseChanged)) {
        card.ended = false;
        connect(card);
      } else if (!card.live && card.source) {
        card.source.close();
        card.source = null;
        card.ended = true;
        card.status.textContent = stateLabel(task.phase);
        card.logStatus.textContent = stateLabel(task.phase);
      } else if (!card.source) {
        // No stream (terminal/draft): keep the overview phase current without
        // reconnecting a task that already completed its replay.
        card.status.textContent = stateLabel(task.phase);
        card.logStatus.textContent = stateLabel(task.phase);
      }
    }
    const currentIds = new Set(all.map(task => task.id));
    for (const [id, card] of state.cards) {
      if (currentIds.has(id)) continue;
      card.source?.close();
      card.logGroup?.remove();
      card.card.remove();
      state.cards.delete(id);
      if (state.logA) {
        state.logA.groups = Math.max(0, state.logA.groups - 1);
        state.logA.count.textContent = runCount(state.logA.groups);
      }
    }
  } catch (error) {
    if (generation !== state.generation) return;
    clearCards();
    list.replaceChildren(el('p', {class: 'ra-error'},
      fill(t('taskListError'), {detail: error.message})));
  }
}

function routeBLog() {
  if (!state.logB) state.logB = buildEventLog('route_b', t('routeBNoRuns'));
  return state.logB.panel;
}

function resetForLocale() {
  state.generation += 1;
  for (const api of state.cards.values()) {
    api.source?.close();
    api.logGroup?.remove();
    api.card.remove();
  }
  state.cards.clear();
  state.monitor?.remove();
  state.monitor = null;
  state.logA?.panel.remove();
  state.logA = null;
  state.logB?.panel.remove();
  state.logB = null;
}

function mount() {
  const locale = chatLocale();
  if (locale !== state.locale) {
    state.locale = locale;
    if (state.monitor || state.logA || state.logB || state.cards.size) resetForLocale();
  }
  const lanes = document.querySelectorAll('.route-slot .route-lane');
  const lane = lanes[0];
  if (!lane) return;
  if (!state.monitor) state.monitor = buildMonitor();
  const contentA = lane.querySelector('.step-panel > .step-content') || lane;
  if (state.monitor.parentElement !== contentA) contentA.append(state.monitor);
  if (state.logA && state.logA.panel.parentElement !== contentA) contentA.append(state.logA.panel);
  const laneB = lanes[1];
  const contentB = laneB?.querySelector('.step-panel > .step-content') || laneB;
  if (contentB && state.logB?.panel.parentElement !== contentB) contentB.append(routeBLog());
  if (!state.mounted) {
    state.mounted = true;
    state.timer = setInterval(() => {
      const list = state.monitor?.querySelector('.ra-task-list');
      const count = state.monitor?.querySelector('.ra-count');
      if (list && count) refreshTasks(list, count);
    }, 5000);
  }
}

const observer = new MutationObserver(() => mount());
observer.observe(document.getElementById('app') || document.body, {childList: true, subtree: true});
mount();
