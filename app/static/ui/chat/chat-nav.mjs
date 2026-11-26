import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261126b';
import {settingsCopy} from '../shared/settings-copy.mjs?v=20261124b';
import {control, displayTitle} from './chat-view.mjs?v=20261128c';

function settingsLabel(key) {
  let stored = null;
  try { stored = localStorage.getItem('binaryrepair.chat.language'); } catch { /* storage may be unavailable */ }
  const candidates = [document.documentElement.lang, stored, 'en'];
  const locale = candidates.find(code => typeof code === 'string' && settingsCopy[code]) || 'en';
  return settingsCopy[locale]?.[key] ?? settingsCopy.en?.[key] ?? key;
}

export function appMark(className) {
  return el('span', {class: className, 'aria-hidden': 'true'},
    el('img', {class: 'mark-light', src: './assets/mark-light.svg', alt: ''}),
    el('img', {class: 'mark-dark', src: './assets/mark-dark.svg', alt: ''}));
}

export function sidebar({t, list, mobile, conversation, newChat, search, settings, model, archive, close}) {
  const toggle = control(t('pinSidebar'), null, {glyph: 'sidebar', compact: true,
    tone: 'pin-sidebar', 'aria-expanded': 'false', 'aria-pressed': 'false'});
  const navButton = (key, glyph, click, extraClass = '') =>
    el('button', {type: 'button', class: 'control nav-control ' + extraClass,
      'aria-label': t(key), title: t(key), 'aria-current': key === 'conversation' ? 'page' : null, onclick: click}, icon(glyph, 17), el('span', {}, t(key)),
    key === 'search' ? el('kbd', {}, 'Ctrl K') : null);
  const body = el('div', {class: 'source-list'},
    el('header', {class: 'source-head'},
      el('a', {class: 'brand-home', href: '/welcome'}, appMark('brand-icon'), el('strong', {}, 'BinaryRepair')),
      mobile ? control(t('close'), close, {glyph: 'x', compact: true}) : toggle),
    el('div', {class: 'source-actions'},
      navButton('conversation', 'chat', conversation),
      navButton('archive', 'tasks', archive),
      navButton('new', 'plus', newChat, 'new-chat'),
      navButton('search', 'search', search, 'search-button')),
    el('nav', {'aria-label': t('chats')}, el('div', {class: 'source-label'}, t('recent')), list),
    el('footer', {},
      (() => {
        const entry = navButton('settings', 'settings', settings, 'settings-entry');
        entry.dataset.settingsTrigger = 'true';
        return entry;
      })()));
  return {body, toggle};
}

export function paintSidebar({chats, selected, lists, navStamp, t, select, actions}) {
  const all = [...chats.values()].filter(chat => chat.events.length).reverse();
  const active = all.filter(chat => !chat.archived);
  const archived = all.filter(chat => chat.archived);
  active.sort((a, b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)));
  const stamp = JSON.stringify([selected.id,
    all.map(chat => [chat.id, chat.phase, chat.title, chat.pinned, chat.archived])]);
  if (navStamp === stamp) return stamp;
  const row = chat => el('div', {class: 'source-row' + (chat.archived ? ' archived' : '')},
    el('button', {type: 'button', class: 'source-item',
      'aria-current': chat === selected ? 'page' : null,
      title: displayTitle(chat, t) + ' · ' + t(chat.phase),
      onclick: () => select(chat)},
    icon('chat', 16),
    el('span', {class: 'source-title'}, displayTitle(chat, t)),
    chat.pinned ? el('span', {class: 'source-pin', title: t('pinnedChat')},
      icon('pin', 12)) : null,
    el('span', {class: 'source-status', 'data-phase': chat.phase, 'aria-label': t(chat.phase)},
      el('span', {class: 'status-dot', 'aria-hidden': 'true'}),
      ['awaiting_user', 'waiting_for_executor', 'cancel_requested'].includes(chat.phase)
        ? t('waiting') : t(chat.phase))),
    actions?.menu ? el('button', {type: 'button', class: 'source-menu',
      'aria-label': t('conversationMenu'), title: t('conversationMenu'),
      onclick: event => { event.stopPropagation(); actions.menu(chat, event.currentTarget); }},
    icon('more', 15)) : null);
  for (const list of lists) {
    const nodes = active.map(row);
    if (archived.length) {
      nodes.push(el('div', {class: 'source-label archived-label'}, t('archivedChats')));
      nodes.push(...archived.map(row));
    }
    list.replaceChildren(...nodes);
  }
  return stamp;
}
