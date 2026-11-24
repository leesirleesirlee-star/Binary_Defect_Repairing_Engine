import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261120au';
import {control} from './chat-view.mjs?v=20261124d';
import {createProgress} from './chat-progress.mjs?v=20261124d';
import {createStepGroups, disclosure} from './chat-steps.mjs?v=20261121j';
import {motionReduced} from '../shared/motion.mjs?v=20261120au';

// Task mode renders the runner's own journal; the legacy v1.2.2 preview keeps
// its synthetic route lanes and milestone card.
export const activityTypes = new Set(['thinking', 'plan_update', 'tool_call', 'file_change',
  'command', 'verification', 'journal_error']);

const fmtTime = seconds => Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
const phases = {
  running: 'executing', awaiting_user: 'awaiting_user', cancel_requested: 'cancel_requested',
  waiting_for_executor: 'waiting_for_executor',
};
const stepKeys = {
  collect: 'stepCollect', freeze: 'stepFreeze', analyze: 'stepAnalyze', audit: 'stepAudit',
  decision: 'stepDecision', repair: 'stepRepair', verify: 'stepVerify', export: 'stepExport',
};
const runnerSteps = ['collect', 'freeze', 'analyze', 'audit', 'decision', 'repair', 'verify', 'export'];
const stepName = (code, t) => t(stepKeys[code] ?? code);
const names = ['route_a', 'route_b'];
const branchSteps = {
  route_a: ['scopeReview', 'manifestRead', 'evidenceCheck'],
  route_b: ['scopeReview', 'rebuildEvidence', 'evidenceCheck'],
};

function journalSummary(record) {
  const p = record.payload || {};
  if (record.type === 'plan_update') {
    const steps = p.steps || [];
    return steps.filter(step => step.status === 'completed').length + '/' + steps.length + ' completed';
  }
  if (record.type === 'run_state') return p.status || 'state';
  if (record.type === 'command') {
    return `${p.phase || '—'} ${p.label_code || ''}${p.exit_code != null ? ' · exit ' + p.exit_code : ''}`;
  }
  if (record.type === 'file_change') {
    return `${p.stage || '—'} · ${(p.files || []).map(file => file.display_path).join(', ')}`;
  }
  if (record.type === 'verification') return p.verdict || p.kind || 'verification';
  if (record.type === 'audit_runs') return `${(p.runs || []).length} run(s)`;
  if (record.type === 'error') return p.code || 'error';
  if (record.type === 'run_end') {
    return `${p.execution || '—'} · ${p.steps_taken ?? '?'} steps`;
  }
  if (record.type === 'corpus_update') return `${p.total ?? '—'} cases`;
  return p.summary || record.type;
}

function journalRow(record) {
  const step = record.step_id ? stepName(record.step_id, key => key) : '—';
  return el('details', {class: 'journal-row', 'data-type': record.type},
    el('summary', {},
      el('span', {class: 'journal-seq'}, '#' + record.seq),
      el('strong', {}, record.type),
      el('span', {class: 'journal-step'}, step),
      el('span', {class: 'journal-summary'}, journalSummary(record)),
      el('span', {class: 'journal-source'}, record.source || '—')),
    el('pre', {class: 'journal-raw'}, JSON.stringify(record.payload || {}, null, 2)));
}

export function createExecution(t, showConversation, taskMode = false) {
  const count = el('strong');
  const phase = el('strong');
  const clock = el('strong');
  const metrics = el('div', {class: 'run-metrics'},
    ...[[t('phase'), phase], [t('stepCount'), count], [t('elapsed'), clock]].map(([name, value]) =>
      el('div', {class: 'run-metric'}, el('span', {}, name), value)));

  // Legacy preview panel (unchanged for ?preview=1).
  const scope = el('p');
  const slots = names.map(() => el('div', {class: 'route-slot'}));
  const branches = el('section', {class: 'route-overview', 'aria-label': t('routes')},
    el('div', {class: 'route-scope'}, el('span', {}, t('executionOverview')),
      el('h3', {}, icon('branch', 16), t('reviewedScope')), scope),
    el('div', {class: 'route-connectors', 'aria-hidden': 'true'}), slots);
  const log = el('div', {class: 'trace-log', 'aria-label': t('activity')});
  const groups = createStepGroups(log, t);
  const empty = el('p', {class: 'trace-empty'}, icon('terminal', 19), t('noActivity'));
  const legacyScroll = el('div', {class: 'execution-scroll', tabindex: '0'},
    branches,
    el('section', {class: 'trace'}, el('h3', {}, t('activity')), empty, log));

  // Task mode: signed G2 record + the runner's own eight-step checklist + journal.
  const g2Rows = el('div', {class: 'g2-rows'});
  const g2Card = el('section', {class: 'g2-card', 'aria-label': t('g2Record')},
    el('h3', {}, t('g2Record')), g2Rows);
  const checklist = el('ol', {class: 'runner-steps'});
  const journal = el('div', {class: 'journal-log'});
  const taskScroll = el('div', {class: 'execution-scroll task-execution', tabindex: '0'},
    g2Card,
    el('section', {class: 'runner-section'}, el('h3', {}, t('runnerChecklist')), checklist),
    el('section', {class: 'journal-section'}, el('h3', {}, t('journalLog')), journal));

  const progress = createProgress(t);
  progress.panel.hidden = taskMode;
  const scroll = taskMode ? taskScroll : legacyScroll;
  let g2Stamp;
  let stepStamp;
  let journalStamp;

  function updateG2(chat) {
    const stamp = chat.g2 ? [chat.g2.audit_sha256, chat.g2.record_sha256, chat.g2.plan_sha256].join(':') : '';
    if (stamp === g2Stamp) return;
    g2Stamp = stamp;
    if (!chat.g2) {
      g2Rows.replaceChildren(el('p', {class: 'muted'}, t('g2Pending')));
      return;
    }
    const audit = chat.g2.audit || {};
    const runs = audit.runs || [];
    const selected = audit.selected_plan || {};
    const schemas = runs.length ? runs.every(run => run.schema_valid) : false;
    const scores = (audit.reviewer_scores || {});
    const row = (name, value) => el('div', {class: 'g2-row'},
      el('span', {}, name), el('strong', {}, value));
    g2Rows.replaceChildren(
      row(t('g2Audit'),
        `${audit.report_id || '—'} · ${runs.length} run(s) · schema ${schemas ? 'valid' : 'invalid'}`
        + ` · selected run ${selected.run_index ?? '—'}`
        + (scores.m1 != null ? ` · M1 ${scores.m1}` : '')),
      row(t('g2Decision'),
        `${audit.decision || '—'} · signed record ${g2Hash(chat.g2.record_sha256)}`),
      row(t('g2Plan'),
        `${chat.g2.plan?.plan_id || '—'} · ${chat.g2.plan?.strategy || '—'}`
        + ` · contract ${g2Hash(chat.g2.contract_sha256)}`));
  }

  function updateChecklist(chat) {
    const stamp = [chat.plan?.revision, chat.journal.length, chat.plan ? 'plan' : ''].join(':');
    if (stamp === stepStamp) return;
    stepStamp = stamp;
    const steps = chat.plan?.steps || [];
    const byStep = Object.fromEntries(steps.map(step => [step.step_id, step]));
    const errors = chat.journal.filter(record => record.type === 'error');
    checklist.replaceChildren(...runnerSteps.map(id => {
      const step = byStep[id] || {step_id: id, label_code: id, status: 'pending'};
      const error = errors.find(record => record.step_id === id);
      const reason = error?.payload?.code || step.reason || '';
      return el('li', {'data-status': step.status},
        el('span', {class: 'runner-dot'}, icon('circle', 10)),
        el('span', {class: 'runner-name'}, stepName(step.label_code || id, t)),
        el('span', {class: 'runner-state'}, t(step.status) + (reason ? ' · ' + reason : '')));
    }));
  }

  function updateJournal(chat) {
    const last = chat.journal[chat.journal.length - 1];
    const stamp = `${chat.journal.length}:${last?.seq ?? 0}`;
    if (stamp === journalStamp) return;
    journalStamp = stamp;
    if (!chat.journal.length) {
      journal.replaceChildren(el('p', {class: 'muted'}, t('journalPending')));
      return;
    }
    journal.replaceChildren(...chat.journal.map(journalRow));
  }

  const inspect = control(t('details'), () => toggleInspect(),
    {tone: 'inspect-before-run-button', 'aria-controls': 'execution-content', 'aria-expanded': 'false'});
  function toggleInspect() {
    const workspace = panel.closest('.workspace');
    if (!workspace) return;
    const expanded = !workspace.classList.contains('inspect-before-run');
    const settle = value => {
      workspace.classList.toggle('inspect-before-run', value);
      inspect.setAttribute('aria-expanded', String(value));
    };
    if (motionReduced()) { settle(expanded); return; }
    const ease = 'cubic-bezier(.42, 0, .58, 1)';
    const gridBefore = getComputedStyle(workspace).gridTemplateColumns;
    if (expanded) {
      settle(true);
      const height = scroll.getBoundingClientRect().height;
      const gridAfter = getComputedStyle(workspace).gridTemplateColumns;
      workspace.animate([{gridTemplateColumns: gridBefore}, {gridTemplateColumns: gridAfter}],
        {duration: 460, easing: ease});
      scroll.style.overflow = 'hidden';
      const animation = scroll.animate([
        {height: '0px', opacity: 0},
        {height: `${height}px`, opacity: 1},
      ], {duration: 460, easing: ease});
      animation.onfinish = animation.oncancel = () => { scroll.style.overflow = ''; };
    } else {
      const height = scroll.getBoundingClientRect().height;
      scroll.style.overflow = 'hidden';
      const animation = scroll.animate([
        {height: `${height}px`, opacity: 1},
        {height: '0px', opacity: 0},
      ], {duration: 340, easing: ease});
      animation.onfinish = animation.oncancel = () => {
        scroll.style.overflow = '';
        settle(false);
        const gridAfter = getComputedStyle(workspace).gridTemplateColumns;
        workspace.animate([{gridTemplateColumns: gridBefore}, {gridTemplateColumns: gridAfter}],
          {duration: 460, easing: ease});
      };
    }
  }
  scroll.id = 'execution-content';
  const panel = el('section', {class: 'execution-pane glass', id: 'execution-pane', 'aria-labelledby': 'execution-heading'},
    el('header', {class: 'execution-head'}, el('div', {class: 'panel-heading'},
      icon('terminal', 18), el('h2', {id: 'execution-heading'}, t('execution'))),
    inspect, control(t('conversation'), showConversation, {glyph: 'chat', tone: 'compact-only'})),
    progress.panel, scroll);

  let stamp;
  function update(chat, items) {
    const plan = chat.plan;
    const steps = plan?.steps;
    const activeStep = steps?.find(step => step.status === 'in_progress');
    const runEnd = chat.runEnd;
    phase.textContent = taskMode
      ? (runEnd?.execution ? t(runEnd.execution)
        : activeStep ? stepName(activeStep.label_code, t)
          : t(chat.phase === 'idle' ? 'noRun' : chat.phase))
      : t(chat.phase === 'running' && activeStep ? stepName(activeStep.label_code, t)
        : chat.phase === 'idle' ? 'noRun' : (phases[chat.phase] ?? chat.phase));
    count.textContent = steps
      ? steps.filter(step => step.status === 'completed').length + ' / ' + steps.length : '—';
    clock.dataset.runStarted = chat.started ?? '';
    clock.dataset.runEnded = chat.ended ?? '';
    clock.textContent = elapsed(clock);

    if (taskMode) {
      updateG2(chat);
      updateChecklist(chat);
      updateJournal(chat);
      return;
    }

    progress.update(chat);
    empty.hidden = items.some(item => activityTypes.has(item.type));
    groups.sync(items.filter(item => activityTypes.has(item.type)));
    const scopeText = chat.reviewed && chat.scope ? chat.scope : t('scopePending');
    if (scope.textContent !== scopeText) scope.textContent = scopeText;

    const routes = chat.routes ?? {};
    const key = JSON.stringify([chat.id, routes, chat.routeNotes]);
    if (key === stamp) return;
    stamp = key;
    names.forEach((route, index) => {
      const states = routes[route] ?? ['pending', 'pending', 'pending'];
      const status = states.includes('in_progress') ? 'in_progress' : states.includes('failed') ? 'failed' :
        states.every(state => state === 'completed') ? 'completed' : states.includes('not_run') ? 'not_run' : 'pending';
      const lastRoute = slots[index].firstElementChild;
      const heading = el('span', {class: 'route-heading'}, el('span', {class: 'route-letter'}, index ? 'B' : 'A'),
        el('span', {class: 'route-name'}, t(route)),
        el('span', {class: 'route-status'}, el('span', {class: 'route-marker', 'aria-hidden': 'true'}), t(status)));
      const node = disclosure({className: 'route-lane', heading, open: lastRoute?.open ?? false},
        el('strong', {}, t(index ? 'routeBMethod' : 'routeAMethod')),
        el('ol', {}, branchSteps[route].map((step, position) => {
          const state = states[position];
          const glyph = state === 'completed' ? 'check' : state === 'failed' ? 'x' :
            state === 'not_run' ? 'slash' : 'circle';
          return el('li', {'data-state': state}, el('span', {class: 'step-dot'}, icon(glyph, 13)),
            el('span', {}, t(step)), el('span', {class: 'visually-hidden'}, t(state)));
        })),
        el('p', {class: 'route-note'}, t(chat.routeNotes?.[route] ?? 'routeNoReason')));
      node.dataset.status = status;
      const restoreFocus = lastRoute?.contains(document.activeElement);
      slots[index].replaceChildren(node);
      if (restoreFocus) node.querySelector('summary').focus({preventScroll: true});
    });
  }
  return {panel, metrics, log, groups, scroll, update, clock, inspect};
}

function g2Hash(value) {
  return value ? String(value).slice(0, 12) + '…' : '—';
}

export function elapsed(node) {
  const start = Number(node.dataset.runStarted);
  if (!start) return '—';
  const end = Number(node.dataset.runEnded) || Date.now();
  return fmtTime(Math.max(0, Math.floor((end - start) / 1000)));
}
