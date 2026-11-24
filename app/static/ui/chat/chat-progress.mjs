import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261120au';
import {currentEvaluation} from '../workbench/api.mjs?v=20261124b';

const labels = ['milestoneReview', 'milestoneQueue', 'milestoneRun', 'milestoneVerdict'];

function taskProgress(chat) {
  const states = ['pending', 'pending', 'pending', 'pending'];
  const steps = chat.plan?.steps || [];
  const statusOf = id => steps.find(step => step.step_id === id)?.status;
  const bound = Boolean(chat.g2 && chat.bound);
  const end = chat.runEnd?.execution;
  const repair = statusOf('repair');
  const verify = statusOf('verify');
  const verdict = chat.verdict;
  states[0] = bound ? 'completed' : chat.request ? 'in_progress' : 'pending';
  if (chat.run) states[1] = end ? 'completed' : 'in_progress';
  else if (bound) states[1] = 'in_progress';
  if (repair === 'in_progress' || verify === 'in_progress') states[2] = 'in_progress';
  else if (repair === 'completed' && verify === 'completed') states[2] = 'completed';
  else if (end && (repair === 'failed' || verify === 'failed')) states[2] = 'failed';
  if (verdict?.available && verdict?.finalized) states[3] = 'completed';
  else if (chat.runEnd) states[3] = end === 'completed' ? 'in_progress' : 'failed';
  let detail = '';
  if (chat.g2 && !bound) detail = 'awaitingBinding';
  if (verdict?.available && verdict?.finalized) detail = verdict.verdict;
  else if (chat.runEnd && states[3] !== 'completed') detail = end || 'unknown';
  else if (bound && !chat.runEnd) detail = 'g2Bound';
  return {states, detail};
}

export function repairProgress(chat) {
  if (chat.taskMode) return taskProgress(chat);
  const states = ['pending', 'pending', 'pending', 'pending'];
  const run = chat.live ? chat.execution?.run_id : chat.kind === 'repair' && chat.run;
  if (!run) {
    if (chat.reviewed) states[0] = 'completed';
    else if (chat.contract?.revision || chat.request) states[0] = 'in_progress';
    return {states, detail: chat.reviewed ? 'ready' : ''};
  }

  states[0] = 'completed';
  const status = chat.live ? chat.execution.status : chat.phase;
  let detail = '';
  switch (status) {
    case 'queued':
    case 'waiting_for_executor':
      states[1] = 'in_progress';
      if (status === 'waiting_for_executor') detail = status;
      break;
    case 'running':
      states[1] = 'completed';
      states[2] = 'in_progress';
      break;
    case 'completed':
      states[1] = states[2] = 'completed';
      states[3] = 'in_progress';
      detail = 'awaitingVerdict';
      break;
    default: {
      // A run can be cancelled in the queue. Only mark a stage we observed.
      const last = chat.events.findLast(event => event.run_id === run && event.type === 'run_state' &&
        ['queued', 'waiting_for_executor', 'running'].includes(event.payload.status));
      if (last?.payload.status === 'running') {
        states[1] = 'completed';
        states[2] = 'interrupted';
      } else if (last) states[1] = 'interrupted';
      detail = chat.execution?.reason_code === 'termination_unconfirmed' ? 'termination_unconfirmed' :
        status === 'cancelling' ? 'cancel_requested' : status || 'unknown';
    }
  }

  const persisted = chat.verdict;
  if (chat.execution?.terminal && persisted?.available && persisted?.finalized && persisted.verdict) {
    states[0] = states[1] = states[2] = states[3] = 'completed';
    return {states, detail: persisted.verdict};
  }
  if (chat.execution?.terminal && !persisted?.finalized) {
    states[3] = 'failed';
    return {states, detail: chat.execution.status || 'failed'};
  }
  const evaluation = currentEvaluation({id: chat.jobId, execution: chat.execution}, chat.data?.evaluation);
  const outcome = evaluation?.verdict?.outcome;
  if (chat.execution?.terminal && evaluation?.finalized === true && outcome) {
    states[3] = 'completed';
    const verdict = outcome === 'error' ? 'evaluationError' : outcome;
    if (outcome !== 'success_within_scope' || (evaluation.demo === false && chat.demo === false)) {
      return {states, detail: status === 'completed' || detail === verdict ? '' : detail, verdict};
    }
    detail = 'preview';
  }
  return {states, detail};
}

export function createProgress(t) {
  const steps = labels.map(key => el('li', {},
    el('span', {class: 'milestone-dot', 'aria-hidden': 'true'}, icon('check', 9)),
    el('span', {}, t(key)), el('span', {class: 'visually-hidden'})));
  const note = el('span', {class: 'milestone-note', role: 'status'});
  const panel = el('section', {class: 'repair-progress', 'aria-label': t('repairProgress')},
    el('header', {}, el('h3', {}, t('repairProgress')), note), el('ol', {}, steps));

  function update(chat) {
    const {states, detail, verdict} = repairProgress(chat);
    const message = [detail, verdict].filter(Boolean).map(key => t(key)).join(' · ');
    if (note.textContent !== message) note.textContent = message;
    note.dataset.success = String(verdict === 'success_within_scope');
    for (const [index, step] of steps.entries()) {
      const state = states[index];
      if (step.dataset.state === state) continue;
      step.dataset.state = state;
      step.setAttribute('aria-current', state === 'in_progress' ? 'step' : 'false');
      step.lastChild.textContent = ' (' + t(state) + ')';
    }
  }
  return {panel, update};
}
