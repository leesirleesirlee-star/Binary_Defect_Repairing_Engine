import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261120au';
import {control} from './chat-view.mjs?v=20261125e';
import {createProgress} from './chat-progress.mjs?v=20261125e';
import {createStepGroups, disclosure} from './chat-steps.mjs?v=20261125e';
import {motionReduced} from '../shared/motion.mjs?v=20261120au';

// Revision 2.4: keep the v1.2.2 execution pane architecture (milestones +
// overview + Route A/B lanes + their run monitors) and fill it from the runner
// journal.  Task-mode never invents a status; preview mode keeps the synthetic
// data for the sealed preview.
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
  route_a: ['routeStepBind', 'routeStepRun', 'routeStepEvidence'],
  route_b: ['routeStepBind', 'routeStepRun', 'routeStepEvidence'],
};

const shortHash = value => value ? String(value).slice(0, 12) + '…' : '—';
const laneStatus = states => states.includes('in_progress') ? 'in_progress'
  : states.includes('failed') ? 'failed'
    : states.every(state => state === 'completed') ? 'completed'
      : states.includes('not_run') ? 'not_run' : 'pending';
const stateGlyph = state => state === 'completed' ? 'check' : state === 'failed' ? 'x'
  : state === 'not_run' ? 'slash' : 'circle';

function g2Stamp(chat) {
  return chat.g2 ? [chat.g2.audit_sha256, chat.g2.record_sha256, chat.g2.plan_sha256].join(':') : '';
}

function taskLaneStates(chat) {
  const a = [
    chat.bound ? 'completed' : chat.request ? 'in_progress' : 'pending',
    chat.run ? (chat.runEnd ? 'completed' : 'in_progress') : (chat.bound ? 'in_progress' : 'pending'),
    chat.verdict?.available && chat.verdict?.finalized ? 'completed'
      : chat.runEnd ? (chat.runEnd.execution === 'completed' ? 'in_progress' : 'failed') : 'pending',
  ];
  return {route_a: a, route_b: ['not_run', 'not_run', 'not_run']};
}

export function createExecution(t, showConversation, taskMode = false) {
  const count = el('strong');
  const phase = el('strong');
  const clock = el('strong');
  const metrics = el('div', {class: 'run-metrics'},
    ...[[t('phase'), phase], [t('stepCount'), count], [t('elapsed'), clock]].map(([name, value]) =>
      el('div', {class: 'run-metric'}, el('span', {}, name), value)));

  const scope = el('p');
  const g2Rows = el('div', {class: 'g2-summary', hidden: !taskMode});
  const scopeCard = el('div', {class: 'route-scope'}, el('span', {}, t('executionOverview')),
    el('h3', {}, icon('branch', 16), t('reviewedScope')), scope, g2Rows);
  const slots = names.map(() => el('div', {class: 'route-slot'}));
  const branches = el('section', {class: 'route-overview', 'aria-label': t('routes')},
    scopeCard, el('div', {class: 'route-connectors', 'aria-hidden': 'true'}), slots);
  const log = el('div', {class: 'trace-log', 'aria-label': t('activity')});
  const groups = createStepGroups(log, t);
  const empty = el('p', {class: 'trace-empty'}, icon('terminal', 19), t('noActivity'));
  const scroll = el('div', {class: 'execution-scroll', tabindex: '0'},
    branches,
    el('section', {class: 'trace'}, el('h3', {}, t('activity')), empty, log));

  const progress = createProgress(t);
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

  let g2Shown = '';
  let laneStamp = '';
  let legacyStamp;

  function updateG2(chat) {
    const stamp = g2Stamp(chat);
    if (stamp === g2Shown) return;
    g2Shown = stamp;
    if (!chat.g2) {
      g2Rows.replaceChildren(el('p', {class: 'muted'}, t('g2Pending')));
      return;
    }
    const audit = chat.g2.audit || {};
    const runs = audit.runs || [];
    const selected = audit.selected_plan || {};
    const schemaValid = runs.length > 0 && runs.every(run => run.schema_valid);
    const scores = audit.reviewer_scores || {};
    const values = [
      [t('g2Audit'), audit.report_id + ' · ' + runs.length + ' run(s) · schema '
        + (schemaValid ? 'valid' : 'invalid') + ' · selected run ' + selected.run_index
        + ' · M1 ' + scores.m1],
      [t('g2Decision'), (audit.decision || '—') + ' · signed ' + shortHash(chat.g2.record_sha256)],
      [t('g2Plan'), (chat.g2.plan?.plan_id || '—') + ' · ' + (chat.g2.plan?.strategy || '—')
        + ' · contract ' + shortHash(chat.g2.contract_sha256)],
    ];
    g2Rows.replaceChildren(...values.map(([name, value]) => el('div', {class: 'g2-row'},
      el('span', {}, name), el('strong', {}, String(value ?? '—')))));
  }

  function updateTaskLanes(chat) {
    const states = taskLaneStates(chat);
    const selectedTitle = chat.bound
      ? (chat.locale === 'zh-Hans' ? chat.bound.title_zh : chat.bound.title_en) : '';
    const stamp = JSON.stringify([chat.id, states, selectedTitle, chat.plan?.revision,
      chat.verdict?.finalized, chat.runEnd?.execution, chat.journal.length]);
    if (stamp === laneStamp) return;
    laneStamp = stamp;
    names.forEach((route, index) => {
      const laneStates = states[route];
      const status = laneStatus(laneStates);
      const last = slots[index].firstElementChild;
      const heading = el('span', {class: 'route-heading'}, el('span', {class: 'route-letter'}, index ? 'B' : 'A'),
        el('span', {class: 'route-name'}, t(route)),
        el('span', {class: 'route-status'}, el('span', {class: 'route-marker', 'aria-hidden': 'true'}), t(status)));
      const title = index === 0
        ? (selectedTitle || t('routeAMethod'))
        : t('routeBMethod');
      const note = index === 0 ? t(chat.bound ? 'routeASelected' : 'routeNoReason')
        : t('routeBNotSelected');
      const node = disclosure({className: 'route-lane', heading, open: index === 0},
        el('strong', {class: 'route-contract'}, title),
        el('ol', {}, branchSteps[route].map((step, position) => {
          const state = laneStates[position];
          return el('li', {'data-state': state}, el('span', {class: 'step-dot'}, icon(stateGlyph(state), 13)),
            el('span', {}, t(step)), el('span', {class: 'visually-hidden'}, t(state)));
        })),
        el('p', {class: 'route-note'}, note));
      node.dataset.status = status;
      const restoreFocus = last?.contains(document.activeElement);
      slots[index].replaceChildren(node);
      if (restoreFocus) node.querySelector('summary').focus({preventScroll: true});
    });
  }

  function update(chat, items) {
    const steps = chat.plan?.steps;
    const activeStep = steps?.find(step => step.status === 'in_progress');
    const runEnd = chat.runEnd;
    phase.textContent = taskMode
      ? (runEnd?.execution ? t(runEnd.execution) + ' · ' + runEnd.execution
        : activeStep ? stepName(activeStep.label_code, t)
          : t(chat.phase === 'idle' ? 'noRun' : chat.phase))
      : t(chat.phase === 'running' && activeStep ? stepName(activeStep.label_code, t)
        : chat.phase === 'idle' ? 'noRun' : (phases[chat.phase] ?? chat.phase));
    count.textContent = steps
      ? steps.filter(step => step.status === 'completed').length + ' / ' + steps.length : '—';
    clock.dataset.runStarted = chat.started ?? '';
    clock.dataset.runEnded = chat.ended ?? '';
    clock.textContent = elapsed(clock);
    progress.update(chat);

    if (taskMode) {
      const scopeText = chat.bound
        ? (chat.locale === 'zh-Hans' ? chat.bound.scope_zh : chat.bound.scope_en) || t('scopePending')
        : t('scopePending');
      if (scope.textContent !== scopeText) scope.textContent = scopeText;
      updateG2(chat);
      updateTaskLanes(chat);
      return;
    }

    empty.hidden = items.some(item => activityTypes.has(item.type));
    groups.sync(items.filter(item => activityTypes.has(item.type)));
    const scopeText = chat.reviewed && chat.scope ? chat.scope : t('scopePending');
    if (scope.textContent !== scopeText) scope.textContent = scopeText;
    const routes = chat.routes ?? {};
    const key = JSON.stringify([chat.id, routes, chat.routeNotes]);
    if (key === legacyStamp) return;
    legacyStamp = key;
    names.forEach((route, index) => {
      const states = routes[route] ?? ['pending', 'pending', 'pending'];
      const status = laneStatus(states);
      const last = slots[index].firstElementChild;
      const heading = el('span', {class: 'route-heading'}, el('span', {class: 'route-letter'}, index ? 'B' : 'A'),
        el('span', {class: 'route-name'}, t(route)),
        el('span', {class: 'route-status'}, el('span', {class: 'route-marker', 'aria-hidden': 'true'}), t(status)));
      const node = disclosure({className: 'route-lane', heading, open: last?.open ?? false},
        el('strong', {}, t(index ? 'routeBMethod' : 'routeAMethod')),
        el('ol', {}, branchSteps[route].map((step, position) => {
          const state = states[position];
          return el('li', {'data-state': state}, el('span', {class: 'step-dot'}, icon(stateGlyph(state), 13)),
            el('span', {}, t(step)), el('span', {class: 'visually-hidden'}, t(state)));
        })),
        el('p', {class: 'route-note'}, t(chat.routeNotes?.[route] ?? 'routeNoReason')));
      node.dataset.status = status;
      const restoreFocus = last?.contains(document.activeElement);
      slots[index].replaceChildren(node);
      if (restoreFocus) node.querySelector('summary').focus({preventScroll: true});
    });
  }
  return {panel, metrics, log, groups, scroll, update, clock, inspect};
}

export function elapsed(node) {
  const start = Number(node.dataset.runStarted);
  if (!start) return '—';
  const end = Number(node.dataset.runEnded) || Date.now();
  return fmtTime(Math.max(0, Math.floor((end - start) / 1000)));
}
