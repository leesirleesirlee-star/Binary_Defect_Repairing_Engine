import {enableDialogCloseMotion} from '../shared/dialog-motion.mjs?v=20261120au';
import '../shared/settings-preferences.mjs?v=20261120au';
import {saveDraft, saveLanguage} from '../shared/handoff.mjs?v=20261120au';
import {LANGUAGES, LANGUAGE_CODES, detectLanguage, isLanguage, languageName} from '../shared/languages.mjs?v=20261120au';
import {getTheme, setTheme} from '../shared/theme.mjs?v=20261120au';
import {playExit} from '../shared/warp.mjs?v=20261121y';
import {welcomeCopy} from './welcome-copy.mjs?v=20261126b';
import {mountPet} from '../shared/pet.mjs?v=20261129d';

const form = document.querySelector('.composer-card');
const draft = document.querySelector('#draft');
const root = document.documentElement;
const button = document.querySelector('#language');
const themeButton = document.querySelector('#theme');
const KEY = 'binaryrepair.welcome.language';
const SUPPORTED = new Set(LANGUAGE_CODES);
const THEME_LABELS = {
  'zh-Hans': ['外观', '跟随系统', '浅色', '深色'],
  'zh-Hant': ['外觀', '跟隨系統', '淺色', '深色'],
  en: ['Theme', 'System', 'Light', 'Dark'],
  fr: ['Thème', 'Système', 'Clair', 'Sombre'],
  de: ['Design', 'System', 'Hell', 'Dunkel'],
  es: ['Tema', 'Sistema', 'Claro', 'Oscuro'],
  pt: ['Tema', 'Sistema', 'Claro', 'Escuro'],
  ja: ['外観', 'システム', 'ライト', 'ダーク'],
  ko: ['테마', '시스템', '라이트', '다크'],
};

function themeLabels() {
  return THEME_LABELS[language] || THEME_LABELS.en;
}

function paintTheme() {
  if (!themeButton) return;
  const [buttonText, system, light, dark] = themeLabels();
  const stored = getTheme();
  const resolved = root.dataset.theme === 'dark' ? dark : light;
  const name = stored === 'system' ? system : stored === 'light' ? light : dark;
  themeButton.textContent = buttonText;
  themeButton.dataset.theme = document.documentElement.dataset.theme || '';
  themeButton.title = buttonText + ': ' + name;
  themeButton.setAttribute('aria-label', buttonText + ': ' + name);
  // Keep the visible control compact; the resolved palette is exposed to CSS
  // through data-theme so the toggle can hint at the current mode.
  themeButton.dataset.mode = stored;
  themeButton.dataset.value = resolved === dark ? 'dark' : 'light';
}

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
  return 'zh-Hans';
}

function apply(language) {
  root.lang = language;
  for (const node of document.querySelectorAll('[data-i18n]')) {
    node.textContent = copy(language, node.dataset.i18n, node.dataset.en ?? node.textContent);
  }
  button.textContent = languageName(language);
  button.setAttribute('aria-label', copy(language, 'welcome.languageButton', 'Switch language'));
  paintTheme();
  draft.placeholder = copy(language, 'welcome.placeholder', 'Add the binary and case files…');
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
  // Clicking the dimmed backdrop (anywhere outside the language frame) closes
  // the picker, just like the native select popover it replaces.
  modal.addEventListener('click', event => {
    if (event.target !== modal) return;
    modal.close();
    button.focus();
  });
  document.body.append(modal);
  enableDialogCloseMotion(modal);
  modal.showModal();
  list.querySelector('.current')?.focus();
}

let language = read();
apply(language);
button.addEventListener('click', openLanguageMenu);
const THEME_ORDER = ['system', 'light', 'dark'];
themeButton?.addEventListener('click', () => {
  const current = getTheme();
  const next = THEME_ORDER[(THEME_ORDER.indexOf(current) + 1) % THEME_ORDER.length];
  setTheme(next);
  paintTheme();
});
window.addEventListener('storage', event => {
  if (event.key === null || event.key === 'binaryrepair.theme') paintTheme();
});
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', paintTheme);

let leaving = false;

form.addEventListener('submit', event => {
  event.preventDefault();
  if (leaving) return;
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
  leaving = true;
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  const enter = () => location.assign(form.action);
  playExit().then(enter, enter);
});
draft.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    form.requestSubmit();
  }
});

// The footer "conversation" shortcut leaves from the same page: keep the
// transition consistent instead of hard-cutting for that one link.
document.addEventListener('click', event => {
  if (leaving) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
  const link = event.target.closest?.('a[href="/ui/chat/"]');
  if (!link) return;
  event.preventDefault();
  leaving = true;
  const enter = () => location.assign(link.getAttribute('href'));
  playExit().then(enter, enter);
});

mountPet();
