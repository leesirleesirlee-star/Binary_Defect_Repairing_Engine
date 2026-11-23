import {animateDetails} from '../shared/details-anim.mjs?v=20261120au';
import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261120au';
import {stepCard} from './chat-steps.mjs?v=20261121j';

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
    const options = p.options ?? [];
    if (status) {
      const chosen = options.find(option => option.id === status);
      return el('div', {class: 'inline-actions'}, icon('check', 15),
        el('span', {}, t('planChosen') + (chosen ? ' · ' + chosen.title : '')));
    }
    return el('div', {class: 'plan-choices', role: 'group', 'aria-label': t('approval')},
      options.map(option => el('div', {class: 'plan-choice'},
        el('strong', {}, option.title),
        el('p', {}, option.summary),
        option.feasible
          ? control(t('selectPlan'), () => engine.decide(chat, p.request_id, option.id),
            {tone: 'primary'})
          : el('span', {class: 'muted'}, option.reason || t('planUnavailable')))));
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
        p.attachment_ids.map(id => el('span', {class: 'message-file'}, icon('file', 14), chat.attachmentNames.get(id) ?? id)),
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
    case 'tool_call':
    case 'file_change':
    case 'command':
    case 'verification':
      // Tool, command, file-change and verification rows stay in the event log
      // and the evidence bundle; they never render as chat cards.
      return null;
    case 'awaiting_user': return approval(item, ctx);
    case 'error':
      return el('p', {class: 'inline-error'}, icon('info', 14), t('error') + ' · ',
        el('code', {}, p.code),
        p.retry.kind === 'manual' && chat.phase === 'failed' && chat.run === item.run_id
          ? control(t('retry'), () => engine.start(chat, locale, true)) : null);
    case 'g4_actions': {
      const actions = p.actions ?? [];
      return el('article', {class: 'message assistant'}, el('div', {class: 'reply-body'},
        el('div', {class: 'inline-actions'}, actions.map(action =>
          control(action.label, () => engine.sendFixture?.(chat, chat.locale),
            {tone: 'primary', glyph: 'arrow'})))));
    }
    case 'g4_downloads': {
      const links = [p.candidate, p.manifest, p.verdict].filter(Boolean);
      return el('article', {class: 'message assistant'}, el('div', {class: 'reply-body'},
        el('div', {class: 'inline-actions'}, links.map(link =>
          el('a', {class: 'control', href: link.href, download: '',
            title: link.sha256 ? 'sha256: ' + link.sha256 : null},
          icon('file', 16), link.label)))));
    }
    case 'run_end': return summary(item, t, chat, engine);
  }
}

export function displayTitle(chat, t) {
  return chat.titleKey ? t(chat.titleKey) : chat.title || t('new');
}
