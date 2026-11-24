import {el, isAscii} from '../shared/dom.mjs?v=20261120au';
import {saveLanguage, takeDraft} from '../shared/handoff.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261120au';
import {LANGUAGE_CODES, languageName} from '../shared/languages.mjs?v=20261120au';
import {slideTo} from '../shared/page-slide.mjs?v=20261120au';
import {getSetting} from '../shared/settings-preferences.mjs?v=20261120au';
import {bindSettingsFlyout} from '../shared/settings-flyout.mjs?v=20261124b';
import {getTheme, setTheme} from '../shared/theme.mjs?v=20261120au';
import {label} from './chat-copy.mjs?v=20261124n';
import {chatPreview} from './chat-stream.mjs?v=20261124n';
import {chatTask} from './chat-task.mjs?v=20261124n';
import {openLanguage, openModel, openSearch, openSettings} from './chat-dialogs.mjs?v=20261121z';
import {appMark, paintSidebar, sidebar} from './chat-nav.mjs?v=20261124b';
import {bindSidebarSpring} from './chat-spring.mjs?v=20261120au';
import {refreshStepCard} from './chat-steps.mjs?v=20261121j';
import {control, displayTitle, renderItem, transcript} from './chat-view.mjs?v=20261124n';
import {activityTypes, createExecution, elapsed} from './chat-workspace.mjs?v=20261124n';

const root = document.documentElement;
const app = document.querySelector('#app');
const live = el('div', {class: 'visually-hidden', role: 'status', 'aria-atomic': 'true'});
app.after(live);

function readPreference(key, allowed, fallback) {
  try {
    const saved = localStorage.getItem('binaryrepair.chat.' + key);
    if (allowed.includes(saved)) return saved;
  } catch { /* Use the session default. */ }
  return fallback;
}

let locale = readPreference('language', LANGUAGE_CODES, 'en');
let model = readPreference('model', ['default', 'deepseek-flash', 'deepseek-v4-pro'], 'default');
let stopSpring = () => {};
let stopFlyout = () => {};
const t = (key, count) => label(locale, key, count);
const projections = new Map();
const drafts = new Map();
let selected;
let frame = 0;
let nodes;
let selectionChanged = false;
let navStamp;

const params = new URLSearchParams(location.search);

function announce(chat, event) {
  if (chat === selected && event && ['run_state', 'run_end', 'assistant_end'].includes(event.type)) {
    const status = event.payload.status ?? event.payload.execution;
    if (event.type === 'assistant_end') {
      const text = chat.events.filter(item => item.type === 'assistant_delta' &&
        item.payload.message_id === event.payload.message_id).map(item => item.payload.append).join('');
      if (text) live.textContent = text;
    } else {
      live.textContent = t(status);
    }
  }
  if (nodes) requestPaint();
}

// Revision 2.2: the shipped console is the deterministic assistant. The live
// task bridge still targets the legacy v1.2.2 job endpoints and is not wired in
// this build, so defaulting to it dead-ends every action; the honest fallback
// keeps the conversation complete and the badge tells the truth.
const previewMode = params.get('preview') === '1';
const engine = previewMode ? chatPreview({notify: announce}) : chatTask({notify: announce});
const requestedJob = params.get('job');
Promise.resolve(engine.seed(locale)).then(() => {
  if (!requestedJob) return;
  const target = [...engine.chats.values()].find(chat => chat.jobId === requestedJob);
  if (target) select(target);
});
selected = engine.create();
if (!requestedJob) {
  const text = takeDraft();
  if (text) drafts.set(selected.id, {text, attachment: '', file: null, cases: []});
}
const media = matchMedia('(max-width: 720px)');

const currentDraft = () => drafts.get(selected.id) ?? {text: '', attachment: '', file: null, cases: []};
const setDraft = updates => drafts.set(selected.id, {...currentDraft(), ...updates});
const busy = chat => ['running', 'awaiting_user', 'cancel_requested', 'queued', 'waiting_for_executor'].includes(chat.phase);
const atEnd = () => nodes.scroll.scrollHeight - nodes.scroll.scrollTop - nodes.scroll.clientHeight < 60;
function jump() {
  nodes.scroll.scrollTop = nodes.scroll.scrollHeight;
  nodes.latest.hidden = true;
}

function requestPaint() {
  if (!frame) frame = requestAnimationFrame(() => {
    frame = 0;
    paint();
  });
}

function select(chat, focusInput = false) {
  const changed = selected !== chat;
  if (changed) engine.deactivate?.();
  selected = chat;
  selectionChanged ||= changed;
  nodes.navDialog.close();
  if (changed) {
    nodes.input.value = currentDraft().text;
    nodes.composerFeedback.textContent = '';
    nodes.rows.clear();
    nodes.log.replaceChildren();
    nodes.execution.groups.clear();
    nodes.hero.hidden = true;
    paint();
    resize();
    if (chat.jobId) void engine.activate?.(chat);
  }
  if (focusInput) nodes.input.focus();
  else if (changed) nodes.scroll.focus({preventScroll: true});
}

function newChat() {
  const pending = currentDraft();
  if (selected.events.length === 0 && !pending.text && !pending.attachment &&
      !pending.cases?.length) return select(selected, true);
  select(engine.create(), true);
}

function send(text) {
  const draft = currentDraft();
  const hasFiles = Boolean(draft.file && (draft.cases?.length ?? 0));
  if ((!text.trim() && !hasFiles) || busy(selected)) return;
  const {attachment, file, cases} = draft;
  if (engine.live && !engine.taskMode && !selected.jobId && (!file || !isAscii(text.trim()))) {
    nodes.composerFeedback.textContent = t('needFile');
    return;
  }
  if (engine.taskMode && !file) {
    nodes.composerFeedback.textContent = t('needFile');
    return;
  }
  nodes.composerFeedback.textContent = '';
  engine.send(selected, text, locale, attachment, file, cases ?? []);
  setDraft({text: '', attachment: '', file: null, cases: []});
  nodes.input.value = '';
  resize();
  paint();
  jump();
  nodes.input.focus({preventScroll: true});
}

function resize() {
  const {input} = nodes;
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 148) + 'px';
}

function preference(key, value) {
  if (key === 'theme') {
    setTheme(value);
    return;
  }
  try { localStorage.setItem('binaryrepair.chat.' + key, value); } catch { /* Retain the selection in this tab. */ }
  if (key === 'model') {
    model = value;
    return;
  }
  locale = value;
  saveLanguage(value);
  engine.setLocale?.(value);
  mount();
  nodes.language.focus();
}

function mount() {
  root.lang = locale;
  document.title = 'BinaryRepair · ' + t('conversation');
  stopFlyout();
  stopSpring();
  document.querySelector('#skip').textContent = t('skip');
  const previousScroll = nodes?.scroll.scrollTop;
  const list = el('div', {class: 'conversation-list'});
  const mobileList = el('div', {class: 'conversation-list'});
  const settingsArgs = () => ({t, locale, theme: getTheme(), preference, getTheme,
    getModel: () => model, setModel: value => preference('model', value),
    clearDrafts: () => drafts.clear(),
    openModel: () => openModel({t, model, preference})});
  const openSettingsAt = section => openSettings({...settingsArgs(), initialSection: section});
  function navArgs(list, mobile) {
    const open = callback => () => {
      if (mobile) nodes.navDialog.close();
      callback();
    };
    return {list, mobile, t, newChat: open(newChat), conversation: open(() => nodes.input.focus()), search: open(() => openSearch({t, engine, select})),
      settings: open(() => openSettings(settingsArgs())),
      model: open(() => openModel({t, model, preference})),
      archive: open(() => { slideTo('/ui/', 'forward'); }),
      close: () => nodes.navDialog.close()};
  }
  const nav = sidebar(navArgs(list, false));
  const navDialog = el('dialog', {class: 'mobile-nav glass', id: 'mobile-conversations', 'aria-label': t('chats')},
    sidebar(navArgs(mobileList, true)).body);
  const openNav = control(t('openNav'), () => {
    navDialog.showModal();
    openNav.setAttribute('aria-expanded', 'true');
  }, {glyph: 'sidebar', compact: true, tone: 'mobile-only', 'aria-expanded': 'false', 'aria-controls': 'mobile-conversations'});
  navDialog.addEventListener('close', () => {
    openNav.setAttribute('aria-expanded', 'false');
    if (media.matches && document.activeElement === document.body) openNav.focus();
  });
  const language = control(languageName(locale),
    () => openLanguage({t, locale, choose: value => preference('language', value)}),
    {lang: locale, 'aria-label': t('language') + ': ' + languageName(locale)});
  const title = el('h1', {class: 'chat-title'});
  const openExecution = control(t('execution'), () => changePane(true), {glyph: 'terminal', tone: 'compact-only',
    'aria-controls': 'execution-pane'});
  const execution = createExecution(t, () => changePane(false), Boolean(engine.taskMode));
  const header = el('header', {class: 'chat-header'}, openNav, title,
    el('span', {class: 'preview-label'}, el('span', {'aria-hidden': 'true'}),
      t(engine.live ? 'liveLabel' : 'preview')), openExecution, language);
  const heroAttach = control(t('attachBinary'), () => file.click(),
    {glyph: 'file', tone: 'primary hero-attach'});
  const heroCases = control(t('attachCases'), () => casesInput.click(),
    {glyph: 'file', tone: 'sample hero-cases'});
  const hero = el('section', {class: 'empty-chat'},
    appMark('hero-mark'), el('h2', {}, t('empty')),
    el('div', {class: 'hero-actions'}, heroAttach, heroCases,
      engine.sendFixture
        ? control(t('useFixture'), () => engine.sendFixture(selected, locale),
          {glyph: 'arrow', tone: 'sample', title: t('fixtureHelp')})
        : control(t('sample'), () => send(t('samplePrompt')), {glyph: 'arrow', tone: 'sample'})));
  const log = el('div', {class: 'transcript', role: 'log', 'aria-live': 'off', 'aria-label': t('chats')});
  const scroll = el('div', {class: 'chat-scroll', tabindex: '0', onscroll: () => {
    if (nodes) nodes.latest.hidden = atEnd();
  }}, hero, log);
  const composerFeedback = el('p', {class: 'composer-feedback', role: 'status'});
  const input = el('textarea', {rows: '1', value: currentDraft().text, maxlength: '4000',
    'aria-label': t('composer'), oninput: () => {
      setDraft({text: input.value});
      composerFeedback.textContent = '';
      resize();
      paintComposer();
    }, onkeydown: event => {
      if (event.key !== 'Enter' || event.isComposing || event.keyCode === 229) return;
      const modifier = event.ctrlKey || event.metaKey;
      const send = getSetting('enterToSend') ? !event.shiftKey && !modifier : modifier;
      if (send) {
        event.preventDefault();
        input.form.requestSubmit();
      }
    }});
  const file = el('input', {type: 'file', hidden: true, onchange: () => {
    const picked = file.files[0] ?? null;
    setDraft({attachment: picked?.name ?? '', file: picked});
    file.value = '';
    composerFeedback.textContent = picked && !currentDraft().cases?.length ? t('needCases') : '';
    maybeAutoSend();
    paintComposer();
    if (picked) input.focus({preventScroll: true});
  }});
  const casesInput = el('input', {type: 'file', hidden: true, multiple: true,
    accept: '.json,.txt,.case,.csv', onchange: () => {
      const picked = [...casesInput.files];
      setDraft({cases: picked});
      casesInput.value = '';
      composerFeedback.textContent = picked.length && !currentDraft().file ? t('needFile') : '';
      maybeAutoSend();
      paintComposer();
      input.focus({preventScroll: true});
    }});
  function maybeAutoSend() {
    const draft = currentDraft();
    if (draft.file && draft.cases?.length && !selected.events.length &&
        !['running', 'awaiting_user', 'cancel_requested'].includes(selected.phase)) {
      queueMicrotask(() => send(t('autoRepairPrompt')));
    }
  }
  const attached = el('div', {class: 'attached', hidden: true});
  const attach = control(t('attachBinary'), () => file.click(), {glyph: 'plus'});
  const casesControl = control(t('attachCases'), () => casesInput.click(), {glyph: 'plus'});
  const stop = control(t('stop'), () => engine.stop(selected), {glyph: 'stop', tone: 'stop'});
  const sendButton = control(t('send'), null, {type: 'submit', glyph: 'up', compact: true, tone: 'primary send-button'});
  const queue = control(t('queue'), null, {type: 'submit', tone: 'queue'});
  const latest = control(t('latest'), jump, {glyph: 'down', tone: 'latest', hidden: true});
  const composer = el('form', {class: 'composer', onsubmit: event => {
    event.preventDefault();
    send(input.value);
  }}, attached, input, composerFeedback, el('div', {class: 'composer-tools'}, file, casesInput, attach, casesControl, el('span', {class: 'spacer'}), stop, queue, sendButton));

  const left = el('section', {class: 'chat-main glass'}, el('div', {}, header, execution.metrics), scroll,
    el('footer', {class: 'composer-wrap'}, latest, composer));
  const workspace = el('main', {id: 'conversation', tabindex: '-1', class: 'workspace'}, left, execution.panel);
  function changePane(open) {
    workspace.classList.toggle('show-execution', open);
    (open ? execution.scroll : openExecution).focus({preventScroll: true});
  }
  const rail = el('aside', {class: 'desktop-nav glass'}, nav.body);
  app.replaceChildren(el('div', {class: 'chat-shell'}, rail, workspace, navDialog));
  stopSpring = bindSidebarSpring(rail, nav.toggle);
  stopFlyout = bindSettingsFlyout(rail.querySelector('[data-settings-trigger]'), {
    locale, sidebar: rail,
    adapter: {
      getTheme: () => getTheme(),
      setTheme: value => preference('theme', value),
      setLanguage: value => preference('language', value),
      getModel: () => model,
      setModel: value => preference('model', value),
      openModel: () => openModel({t, model, preference}),
      clearDrafts: () => drafts.clear(),
      openSection: openSettingsAt,
    },
  });
  nodes = {rows: new Map(), list, mobileList, title, hero, heroAttach, heroCases, log, scroll, input, composerFeedback,
    latest, attach, casesControl, attached, stop, sendButton, queue, language, navDialog, execution};
  nodes.workspace = workspace;
  navStamp = null;
  paint();
  resize();
  if (previousScroll != null) scroll.scrollTop = previousScroll;
}

function paintComposer() {
  const {input, stop, sendButton, queue, hero, heroAttach, heroCases, attach, casesControl, attached} = nodes;
  const active = busy(selected);
  const live = Boolean(selected.live);
  const {attachment, file, cases = []} = currentDraft();
  input.placeholder = t(selected.phase === 'awaiting_user' ? 'approvalTurn' :
    active ? 'waitingTurn' : selected.events.length ? 'followup' : 'placeholder');
  input.readOnly = active && live;
  stop.hidden = !active || !selected.run;
  stop.disabled = selected.phase === 'cancel_requested';
  sendButton.hidden = active;
  sendButton.disabled = !(input.value.trim() || (file && cases.length)) ||
    (live && !selected.jobId && !file);
  queue.hidden = !active || live;
  queue.disabled = !input.value.trim();
  const showHeroAttach = !hero.hidden && !file && !selected.jobId;
  if (heroAttach) heroAttach.hidden = !showHeroAttach;
  if (heroCases) heroCases.hidden = !showHeroAttach;
  attach.hidden = showHeroAttach || (live && Boolean(selected.jobId));
  casesControl.hidden = showHeroAttach || (live && Boolean(selected.jobId));
  const casesKey = cases.map(item => item.name).join('|');
  if (attached.dataset.filename !== attachment + '#' + casesKey) {
    attached.dataset.filename = attachment + '#' + casesKey;
    attached.replaceChildren(
      attachment ? el('span', {}, icon('file', 15), attachment) : null,
      cases.length ? el('span', {}, icon('file', 15), t('casesAttached', cases.length)) : null,
      (attachment || cases.length) ? control(t('remove'), () => {
        setDraft({attachment: '', file: null, cases: []});
        paintComposer();
        (heroAttach && !heroAttach.hidden ? heroAttach : input).focus();
      }, {glyph: 'x', compact: true}) : null);
  }
  attached.hidden = !attachment && !cases.length;
}

function paint() {
  const stick = getSetting('autoScroll') && (selectionChanged || atEnd());
  const trace = nodes.execution.scroll;
  const stickTrace = selectionChanged || trace.scrollHeight - trace.scrollTop - trace.clientHeight < 60;
  selectionChanged = false;
  navStamp = paintSidebar({chats: engine.chats, selected, lists: [nodes.list, nodes.mobileList], navStamp, t, select});
  nodes.title.textContent = displayTitle(selected, t);
  nodes.hero.hidden = selected.events.length > 0;
  const beforeRun = selected.live ? !selected.execution?.run_id : selected.kind !== 'repair';
  nodes.workspace.classList.toggle('before-run', beforeRun);
  if (nodes.workspace.dataset.chat !== selected.id || !beforeRun) {
    nodes.workspace.classList.remove('inspect-before-run');
    nodes.execution.inspect.setAttribute('aria-expanded', 'false');
    nodes.workspace.dataset.chat = selected.id;
  }
  if (!projections.has(selected.id)) projections.set(selected.id, transcript());
  const items = [...projections.get(selected.id).apply(selected.events)];
  nodes.execution.update(selected, items);
  const latestApproval = items.findLast(item => item.type === 'awaiting_user' && item.decision === 'approve');
  for (const item of items) {
    const previous = nodes.rows.get(item.key);
    const flags = item.type === 'awaiting_user' && item.decision === 'approve' ? selected.phase + selected.startReady :
      item.type === 'error' ? selected.phase + selected.run : '';
    if (previous?.item === item && previous.flags === flags) continue;
    const row = renderItem(item, {t, locale, chat: selected, engine, latestApproval});
    if (!row) continue;
    row.dataset.event = item.type;
    if (previous && refreshStepCard(previous.row, row)) {
      nodes.rows.set(item.key, {row: previous.row, item, flags});
      continue;
    }
    if (previous) {
      const oldDetails = previous.row.matches('details') ? [previous.row] : [];
      oldDetails.push(...previous.row.querySelectorAll('details'));
      const newDetails = row.matches('details') ? [row] : [];
      newDetails.push(...row.querySelectorAll('details'));
      for (const [index, detail] of newDetails.entries()) detail.open = oldDetails[index]?.open ?? false;
      const focused = previous.row.contains(document.activeElement);
      previous.row.replaceWith(row);
      if (focused) (row.querySelector('summary,button') ?? nodes.input).focus({preventScroll: true});
    } else {
      if (item.type === 'plan_update') row.open = true;
      if (activityTypes.has(item.type)) {
        if (!engine.taskMode) nodes.execution.groups.target(item, selected.run).append(row);
      } else {
        nodes.log.append(row);
      }
    }
    nodes.rows.set(item.key, {row, item, flags});
  }
  if (stick) jump();
  else nodes.latest.hidden = atEnd();
  if (stickTrace) trace.scrollTop = trace.scrollHeight;
  paintComposer();
}

media.addEventListener('change', () => {
  if (!media.matches && nodes.navDialog.open) nodes.navDialog.close();
});

document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) {
    event.preventDefault();
    openSearch({t, engine, select});
  }
});

setInterval(() => {
  nodes.execution.clock.textContent = elapsed(nodes.execution.clock);
  for (const timer of nodes.execution.log.querySelectorAll('[data-elapsed]')) {
    timer.textContent = Math.max(0, Math.floor((Date.now() - Date.parse(timer.dataset.elapsed)) / 1000)) + ' s';
  }
}, 250);

mount();
