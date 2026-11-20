import {assistantKey} from './assistant-key.mjs?v=20261120as';
import {enableDialogCloseMotion} from './dialog-motion.mjs?v=20261120as';
import {el} from './dom.mjs?v=20261120as';
import {icon} from './icons.mjs?v=20261120as';
import {LANGUAGES} from './languages.mjs?v=20261120as';
import {modelPicker} from './model-picker.mjs?v=20261120as';
import {settingsCopy} from './settings-copy.mjs?v=20261120as';
import {
  getSetting, getSettings, importSettings, resetSettings, setSetting,
} from './settings-preferences.mjs?v=20261120as';

const BUILD = new URL(import.meta.url).searchParams.get('v') || 'dev';

function st(locale, key) {
  return settingsCopy[locale]?.[key] ?? settingsCopy.en[key] ?? key;
}

function row(title, description, control) {
  return el('div', {class: 'settings-row'},
    el('div', {class: 'settings-row-copy'},
      el('p', {class: 'settings-row-title'}, title),
      description ? el('p', {class: 'settings-row-desc'}, description) : null),
    el('div', {class: 'settings-row-control'}, control));
}

function segmented(options, current, onPick, label) {
  const buttons = options.map(([value, title]) => {
    const button = el('button', {type: 'button', class: 'settings-choice',
      'aria-pressed': String(value === current)}, title);
    button.addEventListener('click', () => {
      for (const other of buttons) other.setAttribute('aria-pressed', String(other === button));
      onPick(value);
    });
    return button;
  });
  return el('div', {class: 'settings-segmented', role: 'group', 'aria-label': label || ''}, buttons);
}

function switchControl(checked, onChange, label) {
  const button = el('button', {type: 'button', class: 'settings-switch', role: 'switch',
    'aria-checked': String(checked), 'aria-label': label},
  el('span', {class: 'settings-switch-thumb'}));
  button.addEventListener('click', () => {
    const next = button.getAttribute('aria-checked') !== 'true';
    button.setAttribute('aria-checked', String(next));
    onChange(next);
  });
  return button;
}

export function openSettingsDialog(adapter = {}) {
  const locale = adapter.locale || 'en';
  const t = key => st(locale, key);
  const trigger = document.activeElement;
  let active = adapter.initialSection || 'general';

  const nav = el('nav', {class: 'settings-nav', 'aria-label': t('settingsTitle')});
  const content = el('div', {class: 'settings-content', tabindex: '-1'});
  const navButtons = new Map();
  let modal;

  function close() {
    if (!modal?.open) return;
    modal.close();
  }

  function activate(id) {
    active = id;
    for (const [key, button] of navButtons) {
      button.classList.toggle('active', key === id);
      if (key === id) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    }
    for (const section of content.children) section.hidden = section.id !== 'settings-' + id;
    const heading = content.querySelector('.settings-section:not([hidden]) h2');
    heading?.setAttribute('tabindex', '-1');
    heading?.focus({preventScroll: true});
  }

  function generalSection() {
    const languageGrid = el('div', {class: 'settings-language-grid'}, LANGUAGES.map(({code, native}) => {
      const option = el('button', {type: 'button', class: 'settings-language-option', lang: code,
        'aria-pressed': String(code === locale)}, native);
      option.addEventListener('click', () => {
        if (code === locale) return;
        close();
        setTimeout(() => adapter.setLanguage?.(code), 140);
      });
      return option;
    }));
    return el('section', {class: 'settings-section', id: 'settings-general'},
      el('h2', {}, t('navGeneral')),
      el('h3', {}, t('generalLanguage')),
      el('p', {class: 'settings-help'}, t('generalLanguageDesc')),
      languageGrid,
      row(t('generalMotion'), t('generalMotionDesc'),
        segmented([
          ['system', t('motionSystem')],
          ['reduce', t('motionReduce')],
        ], getSetting('motion'), value => setSetting('motion', value), t('generalMotion'))));
  }

  function appearanceSection() {
    const theme = adapter.getTheme?.() || 'system';
    return el('section', {class: 'settings-section', id: 'settings-appearance', hidden: true},
      el('h2', {}, t('navAppearance')),
      row(t('appearanceTheme'), t('appearanceThemeDesc'),
        segmented([
          ['system', t('themeSystem')],
          ['light', t('themeLight')],
          ['dark', t('themeDark')],
        ], theme, value => adapter.setTheme?.(value), t('appearanceTheme'))),
      row(t('appearanceDensity'), t('appearanceDensityDesc'),
        segmented([
          ['comfortable', t('densityComfortable')],
          ['compact', t('densityCompact')],
        ], getSetting('density'), value => setSetting('density', value), t('appearanceDensity'))),
      row(t('appearanceFont'), t('appearanceFontDesc'),
        segmented([
          ['small', t('fontSmall')],
          ['default', t('fontDefault')],
          ['large', t('fontLarge')],
        ], getSetting('fontSize'), value => setSetting('fontSize', value), t('appearanceFont'))));
  }

  function chatSection() {
    return el('section', {class: 'settings-section', id: 'settings-chat', hidden: true},
      el('h2', {}, t('navChat')),
      row(t('chatEnter'), t('chatEnterDesc'),
        segmented([
          [true, t('chatEnterSend')],
          [false, t('chatEnterModifier')],
        ], getSetting('enterToSend'), value => setSetting('enterToSend', value), t('chatEnter'))),
      row(t('chatAutoScroll'), t('chatAutoScrollDesc'),
        switchControl(getSetting('autoScroll'), value => setSetting('autoScroll', value), t('chatAutoScroll'))),
      row(t('chatTimestamps'), t('chatTimestampsDesc'),
        switchControl(getSetting('timestamps'), value => setSetting('timestamps', value), t('chatTimestamps'))));
  }

  function modelSection() {
    const keyState = el('span', {class: 'settings-badge', 'data-state': 'unknown'}, '—');
    const provider = el('span', {class: 'settings-value'}, '—');
    const model = el('span', {class: 'settings-value'}, '—');
    const picker = modelPicker({value: adapter.getModel?.() || 'default', defaultLabel: t('modelDefault'),
      ariaLabel: t('modelPreferred'), onChange: value => adapter.setModel?.(value)});
    const openConfig = el('button', {type: 'button', class: 'settings-button'},
      icon(adapter.openModel ? 'model' : 'arrow', 16),
      adapter.openModel ? t('modelOpenConfig') : t('modelConfigArchive'));
    openConfig.addEventListener('click', () => {
      if (adapter.openModel) {
        close();
        setTimeout(() => adapter.openModel(), 160);
      } else {
        location.assign('/ui/chat/');
      }
    });

    async function load() {
      try {
        const payload = await assistantKey.status();
        const key = payload.key || payload;
        const assistant = payload.assistant || {};
        keyState.textContent = key.configured
          ? t('modelKeyConfigured') + (key.masked ? ' · ' + key.masked : '')
          : t('modelKeyMissing');
        keyState.dataset.state = key.configured ? 'on' : 'off';
        provider.textContent = key.configured ? 'DeepSeek' : (assistant.mode === 'llm' ? 'DeepSeek' : '—');
        model.textContent = key.model || assistant.model || '—';
      } catch {
        keyState.textContent = '—';
        keyState.dataset.state = 'unknown';
      }
    }
    load();

    return el('section', {class: 'settings-section', id: 'settings-model', hidden: true},
      el('h2', {}, t('modelTitle')),
      el('h3', {}, t('modelPreferred')),
      el('p', {class: 'settings-help'}, t('modelPreferredDesc')),
      picker,
      row(t('modelKeyStatus'), null, keyState),
      row(t('modelProvider'), null, provider),
      row(t('modelCurrentModel'), null, model),
      openConfig);
  }
  function dataSection() {
    const status = el('p', {class: 'settings-status', role: 'status'});
    const file = el('input', {type: 'file', accept: 'application/json,.json', hidden: true});
    file.addEventListener('change', async () => {
      const picked = file.files?.[0];
      file.value = '';
      if (!picked) return;
      try {
        const payload = JSON.parse(await picked.text());
        const imported = payload?.settings ? importSettings(payload.settings) : false;
        if (payload?.theme) adapter.setTheme?.(payload.theme);
        if (payload?.model) adapter.setModel?.(payload.model);
        if (!imported && !payload?.settings) {
          status.textContent = t('dataImportInvalid');
          status.dataset.state = 'bad';
          return;
        }
        status.textContent = t('dataImportDone');
        status.dataset.state = 'good';
        if (payload?.language && payload.language !== locale) {
          close();
          setTimeout(() => adapter.setLanguage?.(payload.language), 160);
        }
      } catch {
        status.textContent = t('dataImportInvalid');
        status.dataset.state = 'bad';
      }
    });

    const exportButton = el('button', {type: 'button', class: 'settings-button'}, icon('download', 16), t('dataExportAction'));
    exportButton.addEventListener('click', () => {
      const payload = {
        version: 1,
        settings: getSettings(),
        theme: adapter.getTheme?.() || 'system',
        language: locale,
        model: adapter.getModel?.() || 'default',
      };
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json'}));
      const link = el('a', {href: url, download: 'binaryrepair-settings.json'});
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = t('dataExportDone');
      status.dataset.state = 'good';
    });

    const importButton = el('button', {type: 'button', class: 'settings-button'}, icon('file', 16), t('dataImportAction'));
    importButton.addEventListener('click', () => file.click());

    const resetButton = el('button', {type: 'button', class: 'settings-button'},
      icon('refresh', 16), t('dataResetAction'));
    resetButton.addEventListener('click', () => {
      resetSettings();
      adapter.setTheme?.('system');
      adapter.setModel?.('default');
      renderSections();
      const fresh = content.querySelector('#settings-data .settings-status');
      if (fresh) {
        fresh.textContent = t('dataResetDone');
        fresh.dataset.state = 'good';
      }
    });

    const clearButton = el('button', {type: 'button', class: 'settings-button'},
      icon('terminal', 16), t('dataClearDraftsAction'));
    clearButton.addEventListener('click', () => {
      try { sessionStorage.removeItem('binaryrepair.welcome.draft'); } catch { /* Ignore. */ }
      adapter.clearDrafts?.();
      status.textContent = t('dataDraftsCleared');
      status.dataset.state = 'good';
    });

    return el('section', {class: 'settings-section', id: 'settings-data', hidden: true},
      el('h2', {}, t('navData')),
      row(t('dataExport'), t('dataExportDesc'), exportButton),
      row(t('dataImport'), t('dataImportDesc'), importButton),
      row(t('dataReset'), t('dataResetDesc'), resetButton),
      row(t('dataClearDrafts'), t('dataClearDraftsDesc'), clearButton),
      el('p', {class: 'settings-note'}, t('dataNote')),
      file,
      status);
  }

  function shortcutsSection() {
    const sendKeys = getSetting('enterToSend') ? 'Enter' : 'Ctrl/⌘ + Enter';
    const newlineKeys = getSetting('enterToSend') ? 'Shift + Enter' : 'Enter';
    const shortcut = (title, description, keys) => row(title, description, el('kbd', {}, keys));
    return el('section', {class: 'settings-section', id: 'settings-shortcuts', hidden: true},
      el('h2', {}, t('navShortcuts')),
      shortcut(t('shortcutSearch'), t('shortcutSearchDesc'), 'Ctrl/⌘ + K'),
      shortcut(t('shortcutSend'), t('shortcutSendDesc'), sendKeys),
      shortcut(t('shortcutNewline'), t('shortcutNewlineDesc'), newlineKeys),
      shortcut(t('shortcutClose'), t('shortcutCloseDesc'), 'Esc'));
  }

  function aboutSection() {
    const backend = el('span', {class: 'settings-value'}, '—');
    const provider = el('span', {class: 'settings-value'}, '—');
    const model = el('span', {class: 'settings-value'}, '—');
    const status = el('p', {class: 'settings-status', role: 'status'});

    fetch('/healthz', {credentials: 'same-origin', cache: 'no-store'})
      .then(response => response.json())
      .then(body => { backend.textContent = body.backend || '—'; })
      .catch(() => { backend.textContent = '—'; });
    assistantKey.status().then(body => {
      const assistant = body.assistant || {};
      provider.textContent = body.key?.configured ? 'DeepSeek' : (assistant.mode === 'llm' ? 'DeepSeek' : '—');
      model.textContent = body.key?.model || assistant.model || '—';
    }).catch(() => {});

    const copy = el('button', {type: 'button', class: 'settings-button'}, icon('file', 16), t('aboutCopy'));
    copy.addEventListener('click', async () => {
      const diagnostics = {
        app: 'BinaryRepair', build: BUILD, href: location.href,
        settings: getSettings(), theme: adapter.getTheme?.() || 'system',
        language: locale, model: adapter.getModel?.() || 'default',
        backend: backend.textContent, provider: provider.textContent,
        serviceModel: model.textContent, userAgent: navigator.userAgent,
      };
      try {
        await navigator.clipboard.writeText(JSON.stringify(diagnostics, null, 2));
        status.textContent = t('aboutCopied');
        status.dataset.state = 'good';
      } catch {
        status.textContent = '—';
      }
    });

    return el('section', {class: 'settings-section', id: 'settings-about', hidden: true},
      el('h2', {}, t('navAbout')),
      row(t('aboutVersion'), null, el('span', {class: 'settings-value'}, 'BinaryRepair')),
      row(t('aboutBuild'), null, el('span', {class: 'settings-value'}, BUILD)),
      row(t('aboutBackend'), null, backend),
      row(t('aboutSession'), null, el('span', {class: 'settings-value'}, t('sessionLocal'))),
      row(t('aboutProvider'), null, provider),
      row(t('aboutModel'), null, model),
      el('div', {class: 'settings-links'},
        el('a', {class: 'settings-button', href: '/welcome'}, t('aboutWelcome')),
        el('a', {class: 'settings-button', href: '/guide'}, t('aboutGuide')),
        el('a', {class: 'settings-button', href: '/ui/chat/'}, t('aboutConversation')),
        el('a', {class: 'settings-button', href: '/ui/'}, t('aboutArchive'))),
      el('div', {class: 'settings-actions'}, copy),
      status,
      el('p', {class: 'settings-note'}, t('aboutLocalOnly')));
  }

  function renderSections() {
    const definitions = [
      ['general', 'settings', 'navGeneral', () => generalSection()],
      ['appearance', 'layers', 'navAppearance', () => appearanceSection()],
      ['chat', 'chat', 'navChat', () => chatSection()],
      ['model', 'model', 'modelTitle', () => modelSection()],
      ['data', 'tasks', 'navData', () => dataSection()],
      ['shortcuts', 'tool', 'navShortcuts', () => shortcutsSection()],
      ['about', 'info', 'navAbout', () => aboutSection()],
    ];
    nav.replaceChildren();
    navButtons.clear();
    for (const [id, glyph, labelKey] of definitions) {
      const button = el('button', {type: 'button', class: 'settings-nav-item'}, icon(glyph, 17),
        el('span', {}, t(labelKey)));
      button.addEventListener('click', () => activate(id));
      nav.append(button);
      navButtons.set(id, button);
    }
    content.replaceChildren(...definitions.map(([, , , build]) => build()));
    activate(active);
  }

  const closeButton = el('button', {type: 'button', class: 'settings-close settings-close-arrow',
    'aria-label': t('close'), title: t('close')}, icon('back', 18));
  closeButton.addEventListener('click', close);
  const done = el('button', {type: 'button', class: 'settings-button primary'}, t('done'));
  done.addEventListener('click', close);

  modal = el('dialog', {class: 'settings-dialog', 'aria-label': t('settingsTitle')},
    el('header', {class: 'settings-head'},
      el('div', {}, el('h2', {}, t('settingsTitle')), el('p', {}, t('settingsSubtitle'))),
      closeButton),
    el('div', {class: 'settings-body'}, nav, content),
    el('footer', {class: 'settings-foot'},
      el('span', {class: 'settings-foot-note'}, t('aboutLocalOnly')), done));
  modal.addEventListener('close', () => {
    modal.remove();
    if (trigger?.isConnected) trigger.focus();
  });
  document.body.append(modal);
  enableDialogCloseMotion(modal);
  renderSections();
  modal.showModal();
  return modal;
}
