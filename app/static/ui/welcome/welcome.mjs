import {enableDialogCloseMotion} from '../shared/dialog-motion.mjs?v=20261120as';
import '../shared/settings-preferences.mjs?v=20261120as';
import {saveDraft, saveLanguage} from '../shared/handoff.mjs?v=20261120as';
import {LANGUAGES, LANGUAGE_CODES, detectLanguage, isLanguage, languageName} from '../shared/languages.mjs?v=20261120as';
import '../shared/theme.mjs?v=20261120as';
import {welcomeCopy} from './welcome-copy.mjs?v=20261120as';

const form = document.querySelector('.composer-card');
const draft = document.querySelector('#draft');
const root = document.documentElement;
const button = document.querySelector('#language');
const KEY = 'binaryrepair.welcome.language';
const SUPPORTED = new Set(LANGUAGE_CODES);

function copy(language, key, fallback = '') {
  return welcomeCopy[language]?.[key] ?? welcomeCopy.en?.[key] ?? fallback;
}

function read() {
  try {
    const saved = localStorage.getItem(KEY) ||
      localStorage.getItem('binaryrepair.chat.language') ||
      localStorage.getItem('binaryrepair.ui.language');
    if (isLanguage(saved)) return saved;
  } catch {
    // Browser storage can be unavailable; fall back to the best match.
  }
  return detectLanguage();
}

function apply(language) {
  root.lang = language;
  for (const node of document.querySelectorAll('[data-i18n]')) {
    node.textContent = copy(language, node.dataset.i18n, node.dataset.en ?? node.textContent);
  }
  button.textContent = languageName(language);
  button.setAttribute('aria-label', copy(language, 'welcome.languageButton', 'Switch language'));
  draft.placeholder = copy(language, 'welcome.placeholder', 'Describe the defect…');
  draft.setAttribute('aria-label', draft.placeholder);
  document.title = copy(language, 'welcome.title', 'BinaryRepair · Verifiable binary repair');
  saveLanguage(language);
}

function openLanguageMenu() {
  if (document.querySelector('dialog.language-menu')) return;
  const modal = document.createElement('dialog');
  modal.className = 'language-menu';
  modal.setAttribute('aria-label', copy(language, 'welcome.languageButton', 'Switch language'));
  const list = document.createElement('div');
  list.className = 'language-list';
  for (const {code, native} of LANGUAGES) {
    const option = document.createElement('button');
    option.type = 'button';
    option.className = 'language-option' + (code === language ? ' current' : '');
    option.lang = code;
    option.textContent = native;
    option.setAttribute('aria-pressed', String(code === language));
    option.addEventListener('click', () => {
      language = code;
      apply(language);
      modal.close();
      button.focus();
    });
    list.append(option);
  }
  modal.append(list);
  modal.addEventListener('close', () => modal.remove());
  document.body.append(modal);
  enableDialogCloseMotion(modal);
  modal.showModal();
  list.querySelector('.current')?.focus();
}

let language = read();
apply(language);
button.addEventListener('click', openLanguageMenu);

form.addEventListener('submit', event => {
  event.preventDefault();
  try {
    saveDraft(draft.value);
  } catch {
    if (draft.value) {
      const error = document.querySelector('#draft-error');
      error.textContent = copy(language, 'welcome.storageError',
        'Copy your draft before continuing. Browser storage is unavailable.');
      error.hidden = false;
      return;
    }
  }
  location.assign(form.action);
});
draft.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    form.requestSubmit();
  }
});
