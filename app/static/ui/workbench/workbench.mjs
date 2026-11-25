import {saveLanguage} from '../shared/handoff.mjs?v=20261126b';
import {LANGUAGE_CODES} from '../shared/languages.mjs?v=20261126b';
import {getTheme, setTheme} from '../shared/theme.mjs?v=20261126b';
import {live, shouldPoll} from './api.mjs?v=20261126b';
import {button, el, notice, taskHref} from '../shared/dom.mjs?v=20261126b';
import {translate} from './labels.mjs?v=20261126b';
import {taskView} from './task.mjs?v=20261126b';
import {g4TaskView} from './g4task.mjs?v=20261126b';
import {pageSlideActive} from '../shared/page-slide.mjs?v=20261126b';
import {motionReduced} from '../shared/motion.mjs?v=20261126b';
import {getSetting} from '../shared/settings-preferences.mjs?v=20261126b';
import {bindSidebarSpring} from '../chat/chat-spring.mjs?v=20261120au';
import {bindSettingsFlyout} from '../shared/settings-flyout.mjs?v=20261126b';
import {createDialog, languageDialog, searchDialog, settingsDialog, shell, tasksView} from './views.mjs?v=20261126b';
import {mountPet} from '../shared/pet.mjs?v=20261126a';

// The archive opens on its synthetic fixture immediately. The legacy live API
// remains available explicitly with ?live=1, but the archive must never present
// an empty "task service unavailable" dead end before showing its content.
const archiveQuery = new URLSearchParams(location.search);
const previewMode = archiveQuery.get('preview') === '1';
const api = previewMode ? (await import('./preview.mjs?v=20261126b')).preview : {...live, lifecycle: false};
const app = document.querySelector('#app');
const preferences = {language: 'zh-Hans', density: 'comfortable'};
const preferenceValues = {language: LANGUAGE_CODES, density: ['comfortable', 'compact']};
for (const [key, choices] of Object.entries(preferenceValues)) {
  try {
    const saved = key === 'language'
      ? (localStorage.getItem('binaryrepair.ui.language') ||
        localStorage.getItem('binaryrepair.chat.language'))
      : localStorage.getItem('binaryrepair.ui.' + key);
    if (choices.includes(saved)) preferences[key] = saved;
  } catch {
    // The UI works if browser storage is unavailable.
  }
}

const t = key => translate(preferences.language, key);
const state = {
  jobs: [], id: null, job: null, data: {}, edits: {}, provider: null, menuOpen: false, navPinned: false,
  filter: 'all', query: '', loading: true, busy: false, listError: null, generation: 0,
};
let timer;
let taskRequestRunning = false;
let failures = 0;
let stopSidebar = null;
let stopFlyout = null;

function readChatModel() {
  try {
    const value = localStorage.getItem('binaryrepair.chat.model');
    return ['default', 'deepseek-flash', 'deepseek-v4-pro'].includes(value) ? value : 'default';
  } catch { return 'default'; }
}

function writeChatModel(value) {
  try { localStorage.setItem('binaryrepair.chat.model', value); } catch { /* Ignore unavailable storage. */ }
}

function setPreference(key, value) {
  if (key === 'theme') {
    setTheme(value);
    return;
  }
  preferences[key] = value;
  try { localStorage.setItem('binaryrepair.ui.' + key, value); } catch { /* Session-only preference. */ }
  if (key === 'language') {
    saveLanguage(value);
    reflectPreferences();
    render();
  } else reflectPreferences();
}

function reflectPreferences() {
  const root = document.documentElement;
  root.lang = preferences.language;
  root.dataset.density = getSetting('density');
  document.title = 'BinaryRepair · ' + t('workspace');
  document.querySelector('#skip').textContent = t('skip');
}

function errorKey(error) {
  const byCode = {
    session_required: 'session',
    request_forbidden: 'permission',
    not_found: 'taskMissing',
    stale_revision: 'conflict',
    stale_approval: 'conflict',
    invalid_transition: 'conflict',
    idempotency_key_conflict: 'conflict',
    plan_transfer_not_authorized: 'permission',
    payload_too_large: 'fileTooLarge',
    invalid_input: 'invalidInput',
    unsupported_contract_version: 'unavailable',
    capability_unavailable: 'unavailable',
    artifact_unavailable: 'artifactUnavailable',
  };
  return byCode[error?.code] ?? ({
    401: 'session', 403: 'permission', 404: 'taskMissing', 409: 'conflict',
    413: 'fileTooLarge', 422: 'invalidInput', 503: 'unavailable',
  })[error?.status] ?? 'unavailable';
}

function navigate(href) {
  if (location.hash !== href) location.hash = href;
  else route();
}

function create() {
  if (api.writable) createDialog({t, api, created: async id => {
    await refreshList();
    navigate(taskHref(id));
  }});
}

function render({focus = false, mainOnly = false} = {}) {
  reflectPreferences();
  const ctx = {
    ...state, api, t, language: preferences.language, act, render, navigate, create, reload: refreshList,
    refresh: () => readTask(state.generation),
    getFilter: () => state.filter,
    setFilter: value => { state.filter = value; },
    setQuery: value => { state.query = value; },
    search: () => searchDialog({t, jobs: state.jobs, navigate}),
    settings: () => settingsDialog({t, preferences: {...preferences, theme: getTheme()}, setPreference, provider: state.provider, getTheme}),
    switchLanguage: () => languageDialog({t, language: preferences.language,
      choose: value => setPreference('language', value)}),
    toggleMenu: () => {
      state.menuOpen = !state.menuOpen;
      const frame = app.querySelector('.shell');
      frame.classList.toggle('nav-open', state.menuOpen);
      frame.querySelector('.mobile-toggle').setAttribute('aria-expanded', String(state.menuOpen));
    },
  };
  ctx.content = !state.id ? tasksView(ctx) : state.job ? el('div', {class: 'page'},
    api.writable ? null : notice(t('readOnly')),
    state.job.kind === 'g4' ? g4TaskView(ctx) : taskView(ctx)) :
    state.error ? el('div', {class: 'page'}, notice(t(state.error), 'error'),
      el('div', {class: 'actions'}, button(t('retry'), () => readTask(state.generation)))) :
      el('p', {role: 'status'}, t('taskLoading'));
  const view = shell(ctx);
  const previousMain = app.querySelector('main');
  if (mainOnly && previousMain) {
    const replacement = view.querySelector('main');
    const currentFocus = document.activeElement;
    // Do not move buttons, forms, or disclosures while someone is using them.
    if (previousMain.contains(currentFocus) && currentFocus !== previousMain) return;
    const details = [...previousMain.querySelectorAll('details')].map(item => item.open);
    replacement.querySelectorAll('details').forEach((item, index) => { item.open = Boolean(details[index]); });
    previousMain.replaceWith(replacement);
    if (currentFocus === previousMain) replacement.focus({preventScroll: true});
  } else {
    // Presentation-only crossfade for user-initiated renders: keep an inert
    // snapshot of the previous shell fading out while the new view fades in.
    // Polling uses the mainOnly path above, so this never replays on refresh.
    const previousShell = app.querySelector('.shell');
    const reduceMotion = motionReduced();
    let ghost = null;
    if (previousShell && !reduceMotion && !pageSlideActive()) {
      ghost = previousShell.cloneNode(true);
      ghost.classList.remove('crossfade-in');
      ghost.classList.add('app-ghost');
      ghost.setAttribute('aria-hidden', 'true');
      ghost.setAttribute('inert', '');
      ghost.style.top = `${-(window.scrollY || 0)}px`;
      view.classList.add('crossfade-in');
    }
    app.replaceChildren(view);
    if (ghost) {
      app.append(ghost);
      setTimeout(() => ghost.remove(), 520);
    }
    stopSidebar?.();
    stopSidebar = null;
    stopFlyout?.();
    stopFlyout = null;
    const rail = app.querySelector('.rail');
    const pin = app.querySelector('.rail .pin-toggle');
    if (rail && pin) {
      stopSidebar = bindSidebarSpring(rail, pin, {
        pinned: state.navPinned,
        onChange: value => { state.navPinned = value; },
      });
      stopFlyout = bindSettingsFlyout(rail.querySelector('[data-settings-trigger]'), {
        locale: preferences.language, sidebar: rail,
        adapter: {
          getTheme: () => getTheme(),
          setTheme: value => setPreference('theme', value),
          setLanguage: value => setPreference('language', value),
          getModel: readChatModel,
          setModel: writeChatModel,
          clearDrafts: () => {
            try { sessionStorage.removeItem('binaryrepair.welcome.draft'); } catch { /* Ignore. */ }
          },
          openSection: section => settingsDialog({
            t, preferences: {...preferences, theme: getTheme()}, setPreference,
            provider: state.provider, getTheme, initialSection: section,
          }),
        },
      });
    }
  }
  if (focus) app.querySelector('main')?.focus({preventScroll: true});
}

async function refreshList() {
  try {
    state.jobs = await api.list();
    state.listError = null;
  } catch (error) {
    state.listError = errorKey(error);
  } finally {
    state.loading = false;
    if (!state.id || !state.job) render();
  }
}

const BACKOFF = [2000, 4000, 8000, 16000, 30000];

function schedule(generation) {
  clearTimeout(timer);
  if (generation !== state.generation || document.hidden || state.busy || !state.id || !shouldPoll(state.job)) return;
  timer = setTimeout(() => readTask(generation, true), BACKOFF[Math.min(failures, BACKOFF.length - 1)]);
}

async function readTask(generation, poll = false) {
  const id = state.id;
  if (!id || generation !== state.generation) return;
  taskRequestRunning = true;
  try {
    const job = await api.job(id);
    if (job.id !== id) throw new Error('Mismatched job identity');
    const runId = job.execution?.run_id ?? null;
    const calls = job.phase === 'draft' ? [] : [
      api.attempts(id), api.evaluation(id, runId), api.artifacts(id), api.comparison(id, runId),
    ];
    const responses = await Promise.allSettled(calls);
    if (generation !== state.generation) return;
    const [attempts, evaluation, artifacts, comparison] = responses.map(result =>
      result.status === 'fulfilled' ? result.value : null);
    const data = {attempts, evaluation, artifacts, comparison};
    const changed = JSON.stringify([job, data]) !== JSON.stringify([state.job, state.data]);
    state.job = job;
    state.data = data;
    if (!poll) state.error = null;
    failures = 0;
    if (!poll || changed || state.pendingRender) {
      state.pendingRender = Boolean(poll && document.activeElement?.matches('main button, main input, main summary, main a'));
      render({mainOnly: poll});
    }
  } catch (error) {
    if (generation !== state.generation) return;
    if (state.job && poll) {
      state.data = {...state.data, connectionError: true, evaluation: null};
      failures = Math.min(3, failures + 1);
    } else {
      state.error = errorKey(error);
    }
    render({mainOnly: poll});
  } finally {
    if (generation === state.generation) {
      taskRequestRunning = false;
      schedule(generation);
    }
  }
}

async function act(operation, options = {}) {
  if (state.busy || !api.writable) return;
  const generation = state.generation;
  state.busy = true;
  state.error = null;
  state.message = null;
  clearTimeout(timer);
  const active = document.activeElement;
  if (active instanceof HTMLButtonElement) active.disabled = true;
  try {
    const response = await operation();
    if (generation !== state.generation) return;
    if (options.clearEdits) state.edits = {};
    if (options.plan) state.plan = response;
    state.message = options.message;
    await readTask(generation);
    void refreshList();
  } catch (error) {
    if (generation !== state.generation) return;
    if (error.status === 409) await readTask(generation);
    if (generation === state.generation) state.error = errorKey(error);
  } finally {
    if (generation === state.generation) {
      state.busy = false;
      render({focus: true});
      schedule(generation);
    }
  }
}

function route() {
  clearTimeout(timer);
  let id = null;
  if (location.hash.startsWith('#task/')) {
    try { id = decodeURIComponent(location.hash.slice(6)); } catch { /* Malformed fragment. */ }
  }
  const generation = ++state.generation;
  Object.assign(state, {id, job: null, data: {}, edits: {}, error: null, message: null,
    plan: null, busy: false, menuOpen: false, pendingRender: false});
  taskRequestRunning = false;
  failures = 0;
  render({focus: true});
  if (id) void readTask(generation);
}

window.addEventListener('hashchange', route);
document.addEventListener('visibilitychange', () => {
  clearTimeout(timer);
  if (!document.hidden && shouldPoll(state.job) && !taskRequestRunning && !state.busy) {
    void readTask(state.generation, true);
  }
});
document.addEventListener('focusout', event => {
  if (state.pendingRender && event.target.closest('main')) {
    setTimeout(() => {
      if (!state.pendingRender || app.querySelector('main')?.contains(document.activeElement)) return;
      state.pendingRender = false;
      render({mainOnly: true});
    }, 0);
  }
});
document.addEventListener('keydown', event => {
  if (document.querySelector('dialog[open]')) return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    searchDialog({t, jobs: state.jobs, navigate});
  }
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey &&
      !event.target.closest('input, textarea, select, [contenteditable]')) {
    event.preventDefault();
    location.href = '/ui/chat/';
  }
});

route();
void refreshList();
try { state.provider = await api.provider(); } catch { /* Keep status unavailable. */ }

mountPet();
