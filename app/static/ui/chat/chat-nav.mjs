import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261120au';
import {settingsCopy} from '../shared/settings-copy.mjs?v=20261124b';
import {control, displayTitle} from './chat-view.mjs?v=20261124i';

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

export function paintSidebar({chats, selected, lists, navStamp, t, select}) {
  const entries = [...chats.values()].filter(chat => chat.events.length).reverse();
  const stamp = JSON.stringify([selected.id, entries.map(chat => [chat.id, chat.phase])]);
  if (navStamp === stamp) return stamp;
  for (const list of lists) {
    list.replaceChildren(...entries.map(chat => {
      const status = t(chat.phase);
      const waiting = ['awaiting_user', 'waiting_for_executor', 'cancel_requested'].includes(chat.phase);
      return el('button', {type: 'button', class: 'source-item', 'aria-current': chat === selected ? 'page' : null,
        title: displayTitle(chat, t) + ' · ' + status, onclick: () => select(chat)},
      icon('chat', 16), el('span', {class: 'source-title'}, displayTitle(chat, t)),
      el('span', {class: 'source-status', 'data-phase': chat.phase, 'aria-label': status},
        el('span', {class: 'status-dot', 'aria-hidden': 'true'}), waiting ? t('waiting') : status));
    }));
  }
  return stamp;
}
