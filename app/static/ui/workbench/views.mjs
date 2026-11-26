import {badge, button, date, el, isAscii, notice, taskHref} from '../shared/dom.mjs?v=20261126b';
import {enableDialogCloseMotion} from '../shared/dialog-motion.mjs?v=20261126b';
import {LANGUAGES, languageName} from '../shared/languages.mjs?v=20261126b';
import {openSettingsDialog} from '../shared/settings-dialog.mjs?v=20261126b';
import {icon} from '../shared/icons.mjs?v=20261126b';

export function shell(ctx) {
  const {t, language, api, jobs, id, create, settings, switchLanguage, menuOpen, toggleMenu, search} = ctx;
  const current = active => active ? 'page' : null;
  const pin = button(null, null, {glyph: 'sidebar', className: 'icon subtle pin-toggle',
    'aria-label': t('pinSidebar'), title: t('pinSidebar'), 'aria-expanded': 'false', 'aria-pressed': 'false'});
  const rail = el('aside', {class: 'rail', id: 'task-navigation'},
    el('div', {class: 'rail-top'},
      el('div', {class: 'rail-head'},
        el('a', {class: 'brand', href: '/welcome', title: 'BinaryRepair', 'aria-label': 'BinaryRepair'},
          el('span', {class: 'brand-mark'}, el('img', {class: 'mark-light', src: '/ui/assets/mark-light.svg', alt: ''}),
            el('img', {class: 'mark-dark', src: '/ui/assets/mark-dark.svg', alt: ''})),
          el('span', {class: 'brand-name'}, 'BinaryRepair')),
        pin),
      el('nav', {class: 'workspace-links', 'aria-label': t('workspace')},
        el('a', {class: 'nav-link', href: '/ui/chat/'}, icon('chat', 16), el('span', {}, t('openChat'))),
        el('a', {class: 'nav-link', href: '#tasks', 'aria-current': current(!id)},
        icon('tasks', 16), el('span', {}, t('tasks'))))),
    jobs.length ? el('nav', {class: 'recent', 'aria-label': t('recent')},
      el('p', {class: 'rail-label'}, t('recent')),
      jobs.slice(0, 6).map(job => el('a', {class: 'nav-link', href: taskHref(job.id), title: job.defect,
        'aria-current': current(id === job.id)}, el('span', {}, job.defect || job.id)))) : null,
    el('div', {class: 'rail-footer'}, button(el('span', {}, t('settings')), settings,
      {glyph: 'settings', className: 'subtle settings-entry', 'data-settings-trigger': 'true'})));
  const mobile = button(null, toggleMenu, {glyph: 'menu', className: 'icon subtle mobile-toggle',
    'aria-label': t('collapse'), 'aria-expanded': String(menuOpen), 'aria-controls': 'task-navigation'});
  const top = el('header', {class: 'topbar'},
    el('div', {class: 'top-left'}, mobile, id ?
      el('a', {class: 'button subtle', href: '#tasks'}, icon('back', 16), t('tasks')) :
      el('span', {class: 'muted'}, t('workspace'))),
    el('div', {class: 'top-right'},
      el('a', {class: 'button subtle', href: '/ui/chat/'}, icon('chat', 16), t('openChat')),
      jobs.length ? button(null, search, {glyph: 'search', className: 'icon subtle', 'aria-label': t('search'), title: t('search') + ' (Ctrl+K)'}) : null,
      button(languageName(language), switchLanguage, {className: 'subtle',
        lang: language, 'aria-label': t('language') + ': ' + languageName(language)}),
      button(null, settings, {glyph: 'settings', className: 'icon subtle mobile-toggle', 'aria-label': t('settings')})));
  const main = el('main', {id: 'main', tabindex: '-1'},
    api.demo || ctx.job?.demo ? el('div', {class: 'page'}, notice(t('demo'), 'demo')) : null,
    ctx.content);
  return el('div', {class: 'shell' + (menuOpen ? ' nav-open' : '')}, rail, el('div', {class: 'shell-body'}, top, main));
}

const finished = new Set(['done', 'completed', 'failed', 'cancelled', 'verified', 'unsupported']);
const phase = job => job.execution?.status === 'waiting_for_executor' ? job.execution.status : job.phase;
const isRunning = job => job.phase === 'running' || job.phase === 'queued' ||
  job.live_audit?.status === 'running' ||
  ['running', 'queued', 'waiting_for_executor'].includes(job.execution?.status);
// Rows that were running while the user was watching stay visible after they
// finish, until the archive page is closed and reopened.
const activeSticky = new Map();
const matches = (job, text) =>
  (job.id + ' ' + (job.defect ?? '')).toLowerCase().includes(text.toLowerCase().trim());
const listFilter = (jobs, filter, text) => {
  if (filter === 'active') {
    const byId = new Map(jobs.map(job => [job.id, job]));
    for (const job of jobs) if (isRunning(job)) activeSticky.set(job.id, job);
    for (const [id, old] of activeSticky) {
      byId.set(id, byId.get(id) || old);
      if (byId.get(id)) activeSticky.set(id, byId.get(id));
    }
    return [...byId.values()].filter(job => isRunning(job) || activeSticky.has(job.id))
      .filter(job => matches(job, text));
  }
  return jobs.filter(job => (filter === 'all' || finished.has(job.phase)) && matches(job, text));
};

export function tasksView(ctx) {
  const {t, language, jobs, api, listError, loading, create, filter, query, setFilter, setQuery, reload} = ctx;
  if (loading) return el('p', {role: 'status'}, t('loading'));
  if (listError) {
    const preview = new URL(location.href);
    preview.search = '?preview=1';
    preview.hash = '';
    return el('div', {class: 'page'}, el('h1', {}, t('tasks')), notice(t(listError), 'error'),
      el('div', {class: 'actions'}, button(t('retry'), reload),
        el('a', {class: 'button', href: preview.pathname + preview.search}, t('previewLink'))));
  }

  const heading = el('div', {class: 'heading'}, el('h1', {}, t('tasks')), el('p', {class: 'stat'}, t('archiveIntro')));
  const newRepair = el('a', {class: 'button primary', href: '/ui/chat/'}, icon('plus', 16), t('create'));
  if (!jobs.length) {
    return el('div', {class: 'page'}, heading, el('div', {class: 'card empty', id: 'task-results'},
      el('h2', {}, t('empty')), el('p', {class: 'muted'}, t('emptyHelp')), newRepair));
  }
  const results = el('div', {class: 'card', id: 'task-results'});
  const filterButtons = ['all', 'active', 'finished'].map(value => button(t(value === 'finished' ? 'archived' : value), event => {
    setFilter(value);
    for (const item of filterButtons) item.setAttribute('aria-pressed', String(item === event.currentTarget));
    update();
  }, {class: 'toggle', 'aria-pressed': String(value === filter)}));
  const input = el('input', {type: 'search', id: 'task-filter', value: query, 'aria-label': t('filterLabel'),
    placeholder: t('search'), oninput: event => { setQuery(event.currentTarget.value); update(); }});
  const update = () => {
    const visible = listFilter(jobs, ctx.getFilter(), input.value);
    results.replaceChildren(
      visible.length ? el('div', {class: 'table-head'}, el('span', {}, t('description')),
        el('span', {}, t('status')), el('span', {}, t('updated')), el('span')) :
        el('div', {class: 'empty'}, el('h2', {}, t('noMatches'))),
      ...visible.map(job => el('div', {class: 'task-row-wrap'},
        el('a', {class: 'task-row', href: taskHref(job.id)}, el('span', {class: 'task-title'},
          job.defect || job.id, el('small', {class: 'mono'}, job.id)),
          el('span', {class: 'inline'}, badge(phase(job), t),
            job.outcome ? badge(job.outcome, t) : null),
          date(job.updated_at ?? job.created_at, language),
          el('span', {class: 'arrow', 'aria-hidden': 'true'}, icon('chevron', 16))),
        api.writable ? button('', async event => {
          event.preventDefault();
          event.stopPropagation();
          if (!window.confirm(t('deleteConfirm'))) return;
          try {
            await api.remove(job.id);
            activeSticky.delete(job.id);
            try {
              const key = 'binaryrepair.chat.sessions.v1';
              const saved = JSON.parse(localStorage.getItem(key) || 'null');
              if (saved?.chats) {
                saved.chats = saved.chats.filter(chat => chat.jobId !== job.id);
                localStorage.setItem(key, JSON.stringify(saved));
              }
            } catch { /* browser history is best-effort */ }
            await reload();
          } catch (error) { window.alert(error?.code || error?.message || t('readError')); }
        }, {className: 'delete-task', 'aria-label': t('delete'), glyph: 'x'}) : null)));
  };
  update();
  const refreshButton = button(t('refresh'), event => {
    const target = event.currentTarget;
    target.disabled = true;
    target.setAttribute('aria-busy', 'true');
    target.classList.add('is-spinning');
    void reload();
  }, {glyph: 'refresh', className: 'subtle'});
  return el('div', {class: 'page'},
    el('div', {class: 'section-head'}, heading,
      el('div', {class: 'actions'}, refreshButton, newRepair)),
    el('div', {class: 'controls'},
      el('div', {class: 'segments', role: 'group', 'aria-label': t('filterLabel')}, filterButtons),
      el('div', {class: 'search'}, icon('search', 15), input)),
    results);
}

function dialog(title, t, ...children) {
  document.querySelector('dialog[open]')?.close();
  const opener = document.activeElement;
  const modal = el('dialog', {'aria-labelledby': 'dialog-title'},
    el('div', {class: 'section-head'}, el('h2', {id: 'dialog-title'}, title),
      button(null, () => modal.close(), {glyph: 'x', className: 'icon subtle', 'aria-label': t('close')})),
    ...children);
  modal.addEventListener('close', () => {
    modal.remove();
    if (opener?.isConnected) opener.focus();
  });
  document.body.append(modal);
  enableDialogCloseMotion(modal);
  modal.showModal();
  return modal;
}

export function createDialog({t, api, created}) {
  const defect = el('textarea', {name: 'defect', rows: 4, required: true, autofocus: true, placeholder: t('defectPlaceholder'),
    oninput: event => event.currentTarget.setCustomValidity('')});
  const file = el('input', {name: 'binary', type: 'file', required: true,
    onchange: event => event.currentTarget.setCustomValidity('')});
  const feedback = el('p', {class: 'stat', role: 'status'}, t('demo'));
  const submit = button(t('createDraft'), null, {className: 'primary', type: 'submit'});
  const form = el('form', {onsubmit: async event => {
    event.preventDefault();
    const description = defect.value.trim();
    const binary = file.files[0];
    defect.setCustomValidity(!description ? t('required') : !isAscii(description) ? t('ascii') : '');
    file.setCustomValidity(!binary?.size ? t('fileRequired') : !isAscii(binary.name) ? t('ascii') : '');
    if (!form.reportValidity()) return;
    submit.disabled = true;
    try {
      const id = await api.create({defect: description, file: binary});
      modal.close();
      created(id);
    } catch (error) {
      feedback.textContent = t(error?.code === 'payload_too_large' ? 'fileTooLarge' :
        error?.code === 'invalid_input' ? 'invalidInput' : 'unavailable');
      submit.disabled = false;
    }
  }}, el('label', {class: 'label'}, t('defect'), defect),
    el('label', {class: 'label'}, t('binary'), file), feedback, el('div', {class: 'actions'}, submit));
  const modal = dialog(t('create'), t, form);
  defect.focus();
}

export function settingsDialog({t, preferences, setPreference, provider, getTheme, initialSection}) {
  const readModel = () => {
    try {
      const value = localStorage.getItem('binaryrepair.chat.model');
      return ['default', 'deepseek-flash', 'deepseek-v4-pro'].includes(value) ? value : 'default';
    } catch {
      return 'default';
    }
  };
  const setModel = value => {
    try { localStorage.setItem('binaryrepair.chat.model', value); } catch { /* Ignore unavailable storage. */ }
  };
  return openSettingsDialog({
    initialSection,
    locale: preferences.language,
    getTheme: getTheme || (() => preferences.theme),
    setTheme: value => setPreference('theme', value),
    setLanguage: value => setPreference('language', value),
    getModel: readModel,
    setModel,
    clearDrafts: () => { try { sessionStorage.removeItem('binaryrepair.welcome.draft'); } catch { /* Ignore. */ } },
    provider,
  });
}

export function searchDialog({t, jobs, navigate}) {
  const results = el('div', {class: 'stack'});
  function update(text) {
    const matches = listFilter(jobs, 'all', text).slice(0, 8);
    results.replaceChildren(...matches.map(job => button(job.defect || job.id, () => {
      modal.close();
      navigate(taskHref(job.id));
    }, {className: 'subtle wrap'})), matches.length ? el('span', {hidden: true}) : el('p', {class: 'muted'}, t('noMatches')));
  }
  const search = el('input', {type: 'search', 'aria-label': t('search'), placeholder: t('search'),
    oninput: event => update(event.currentTarget.value)});
  const modal = dialog(t('search'), t, el('div', {class: 'stack'}, search, results));
  update('');
  search.focus();
}

export function languageDialog({t, language, choose}) {
  const choices = el('div', {class: 'language-grid'}, LANGUAGES.map(({code, native}) =>
    button(native, () => {
      modal.close();
      choose(code);
    }, {className: code === language ? 'primary' : 'subtle', lang: code})));
  const modal = dialog(t('language'), t, choices);
}
