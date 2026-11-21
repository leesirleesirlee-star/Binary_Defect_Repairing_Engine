/**
 * Route A live repair-run monitor.
 *
 * The framework is sample-agnostic: tasks are discovered from /api/tasks and
 * each task is followed through its own SSE journal. No fixture, contract,
 * input or verdict data is hard-coded here; this module only renders the run
 * framework and the persisted events returned by the browser API.
 */
import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261120au';

const STEPS = ['collect', 'freeze', 'analyze', 'audit', 'decision', 'repair', 'verify', 'export'];
const LABELS = {
  collect: '收集', freeze: '冻结', analyze: '分析', audit: '审计', decision: '决策',
  repair: '修复', verify: '验收', export: '导出',
  pending: '等待', in_progress: '进行中', completed: '完成', failed: '失败', skipped: '跳过',
  running: '运行中', queued: '排队', cancelled: '已取消', blocked: '阻塞',
  passed: '通过', not_run: 'not_run', proposed: '提案', applied: '已应用',
  started: '开始', finished: '完成', output: '输出',
  synthetic: '合成预览', runner: 'runner', verifier: 'verifier', gui: 'GUI',
};
const EVENT_TYPES = [
  'run_state', 'plan_update', 'corpus_update', 'command', 'file_change',
  'verification', 'audit_runs', 'awaiting_user', 'error', 'run_end',
  'user_message', 'message_dispatched', 'assistant_delta', 'assistant_end',
  'thinking', 'tool_call', 'tool_result', 'user_response',
];
const state = {monitor: null, logA: null, logB: null, cards: new Map(), timer: null, mounted: false};

const label = value => LABELS[value] ?? value ?? '—';
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

function buildEventLog(route) {
  const count = el('span', {class: 'ra-count'}, '0 个运行');
  const body = el('div', {class: 'ra-log-body'}, el('p', {class: 'ra-muted'}, '等待运行事件…'));
  const panel = el('details', {class: 'ra-monitor ra-event-log', open: true},
    el('summary', {class: 'ra-summary'},
      el('span', {class: 'ra-title'}, icon('terminal', 15), route + ' · 事件日志'),
      count),
    body);
  return {panel, body, count, groups: 0};
}

function taskCard(task, index) {
  const id = task.id;
  const labelText = '修复运行 #' + String(index + 1).padStart(2, '0');
  const steps = el('div', {class: 'ra-steps'});
  const status = el('span', {class: 'ra-status'}, '连接中');
  const artifacts = el('div', {class: 'ra-artifacts', hidden: true});
  const card = el('article', {class: 'ra-task'},
    el('header', {class: 'ra-task-head'},
      el('div', {}, el('strong', {}, labelText),
        el('span', {class: 'ra-target'}, '阶段：' + label(task.phase || 'unknown'))),
      el('div', {class: 'ra-task-state'}, el('span', {class: 'ra-dot'}), status)),
    steps,
    artifacts);
  const logRows = el('div', {class: 'ra-log-rows'}, el('p', {class: 'ra-muted'}, '等待运行事件…'));
  const logStatus = el('span', {class: 'ra-log-status'}, '连接中');
  const logGroup = el('details', {class: 'ra-log-run', open: true},
    el('summary', {}, el('strong', {}, labelText), logStatus),
    logRows);
  if (state.logA) {
    state.logA.body.append(logGroup);
    state.logA.groups += 1;
    state.logA.count.textContent = state.logA.groups + ' 个运行';
  }
  const api = {task, card, logGroup, logRows, logStatus, steps, status, artifacts,
    labelText, lastSeq: 0, source: null, ended: false};
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
  if (record.type === 'verification') return p.verdict ? p.verdict.outcome : '未最终确定 (verdict=null)';
  if (record.type === 'audit_runs') return `${(p.runs || []).length} runs`;
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
      el('span', {class: 'ra-step-name'}, LABELS[id] || id),
      el('span', {class: 'ra-step-state'}, label(status)));
  }));
}

function appendEvent(api, record) {
  if (record.seq <= api.lastSeq) return;
  api.lastSeq = record.seq;
  if (api.logRows.querySelector('.ra-muted')) api.logRows.replaceChildren();
  if (record.type === 'plan_update') applyPlan(api, record.payload?.steps);
  if (record.type === 'run_state') {
    api.status.textContent = label(record.payload?.status);
    api.logStatus.textContent = label(record.payload?.status);
  }
  if (record.type === 'run_end') {
    api.status.textContent = label(record.payload?.execution);
    api.logStatus.textContent = label(record.payload?.execution);
    api.ended = true;
    api.source?.close();
    loadArtifacts(api);
  }
  const row = el('details', {class: 'ra-event', 'data-type': record.type},
    el('summary', {},
      el('span', {class: 'ra-seq'}, '#' + record.seq),
      el('strong', {}, record.type),
      chip(record.source === 'synthetic' ? '合成预览' : record.source, record.source === 'synthetic' ? 'warn' : ''),
      el('span', {class: 'ra-event-summary'}, eventSummary(record))),
    el('div', {class: 'ra-raw'},
      el('span', {class: 'ra-muted'}, `${record.step_id || '—'} · ${record.ts || ''}`),
      el('pre', {}, JSON.stringify({...record, conversation_id: '运行标识已隐藏'}, null, 2))));
  api.logRows.append(row);
}

function connect(api) {
  const id = api.task.id;
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
      api.status.textContent = '日志缺口';
      source.close();
    });
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED && !api.ended) api.status.textContent = '连接关闭';
    };
  } catch {
    api.status.textContent = '无法连接';
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
    api.artifacts.replaceChildren(el('span', {class: 'ra-muted'}, '工件：'),
      ...data.artifacts.map(item => el('a', {
        class: 'ra-artifact', href: item.download_url, download: item.display_path,
      }, icon('download', 12), item.display_path)));
  } catch { /* no artifacts until the runner writes them */ }
}

function buildMonitor() {
  const count = el('span', {class: 'ra-count'}, '0 个任务');
  const list = el('div', {class: 'ra-task-list'}, el('p', {class: 'ra-muted'}, '正在读取任务…'));
  const refresh = el('button', {type: 'button', class: 'ra-refresh', title: '刷新任务'},
    icon('refresh', 14), '刷新');
  refresh.addEventListener('click', () => refreshTasks(list, count));
  const monitor = el('details', {class: 'ra-monitor', open: true},
    el('summary', {class: 'ra-summary'},
      el('span', {class: 'ra-title'}, icon('terminal', 15), 'Route A · 修复运行监视'),
      el('span', {class: 'ra-live'}, el('span', {class: 'ra-dot'}), '实时'),
      count,
      refresh),
    el('div', {class: 'ra-body'}, list));
  state.monitor = monitor;
  if (!state.logA) state.logA = buildEventLog('Route A');
  refreshTasks(list, count);
  return monitor;
}

async function refreshTasks(list, count) {
  try {
    await session();
    const all = await tasks();
    const candidates = all.filter(task => !task.demo && task.phase !== 'preview');
    const visible = candidates.slice(0, 12);
    count.textContent = visible.length + ' 个运行';
    if (!visible.length) {
      list.replaceChildren(el('p', {class: 'ra-muted'}, '暂无运行任务。给定漏洞文件的任务会自动出现在这里。'));
      return;
    }
    if (list.querySelector('.ra-muted') && !list.querySelector('.ra-task')) list.replaceChildren();
    visible.forEach((task, index) => {
      if (state.cards.has(task.id)) return;
      list.append(taskCard(task, index));
    });
    const currentIds = new Set(all.map(task => task.id));
    for (const [id, card] of state.cards) {
      if (!currentIds.has(id) && card.card.parentElement) card.card.remove();
    }
  } catch (error) {
    list.replaceChildren(el('p', {class: 'ra-error'}, '任务列表不可用：' + error.message));
  }
}

function routeBLog() {
  if (!state.logB) state.logB = buildEventLog('Route B');
  return state.logB.panel;
}

function mount() {
  const lanes = document.querySelectorAll('.route-slot .route-lane');
  const lane = lanes[0];
  if (!lane) return;
  if (!state.monitor) state.monitor = buildMonitor();
  if (state.monitor.parentElement !== lane) lane.append(state.monitor);
  if (state.logA && state.logA.panel.parentElement !== lane) lane.append(state.logA.panel);
  const laneB = lanes[1];
  if (laneB && state.logB?.panel.parentElement !== laneB) laneB.append(routeBLog());
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
