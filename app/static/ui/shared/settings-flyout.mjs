/**
 * Hover flyout for the sidebar Settings entry.
 *
 * - hovering the Settings trigger opens an upward menu of settings sections
 * - hovering a row (especially its right arrow) opens a right-hand preview
 * - the preview's bottom-right expand control opens the existing centered
 *   Settings dialog at that section, preserving every existing control
 * - model configuration and API-key status are part of the Model & API key
 *   preview; the existing model dialog remains available unchanged
 */
import {assistantKey} from './assistant-key.mjs?v=20261120as';
import {el} from './dom.mjs?v=20261120as';
import {icon} from './icons.mjs?v=20261120as';
import {LANGUAGES} from './languages.mjs?v=20261120as';
import {modelPicker} from './model-picker.mjs?v=20261120as';
import {settingsCopy} from './settings-copy.mjs?v=20261120as';
import {
  getSetting, getSettings, importSettings, resetSettings, setSetting,
} from './settings-preferences.mjs?v=20261120as';

const BUILD = new URL(import.meta.url).searchParams.get('v') || 'dev';

const SECTIONS = [
  ['general', 'settings', 'navGeneral'],
  ['appearance', 'layers', 'navAppearance'],
  ['chat', 'chat', 'navChat'],
  ['model', 'model', 'modelTitle'],
  ['data', 'tasks', 'navData'],
  ['shortcuts', 'tool', 'navShortcuts'],
  ['about', 'info', 'navAbout'],
];

function copy(locale, key) {
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

function toggle(checked, onChange, label) {
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

function sectionElement(id, title) {
  return el('section', {class: 'settings-section flyout-section', id: 'flyout-' + id},
    el('h2', {}, title));
}

export function bindSettingsFlyout(trigger, options = {}) {
  if (!trigger) return () => {};
  const locale = options.locale || 'en';
  const adapter = options.adapter || {};
  const sidebar = options.sidebar || trigger.closest('.desktop-nav, .rail');
  const t = key => copy(locale, key);

  trigger.setAttribute('aria-haspopup', 'menu');
  trigger.setAttribute('aria-expanded', 'false');
  trigger.classList.add('settings-trigger');

  const layer = el('div', {class: 'settings-flyout-layer'});
  const menu = el('div', {class: 'settings-menu', role: 'menu', 'aria-label': t('settingsTitle')});
  const preview = el('div', {class: 'settings-preview', role: 'dialog', 'aria-label': t('settingsTitle')});
  layer.append(menu, preview);
  document.body.append(layer);

  let open = false;
  let closeTimer = 0;
  let activeSection = null;
  let activeRow = null;
  let previewBuiltFor = null;
  const rows = new Map();

  function cancelClose() {
    clearTimeout(closeTimer);
    closeTimer = 0;
  }

  function scheduleClose(delay = 180) {
    cancelClose();
    closeTimer = window.setTimeout(() => {
      if (menu.matches(':hover') || preview.matches(':hover') || trigger.matches(':hover')) return;
      hide();
    }, delay);
  }

  function positionMenu() {
    const rect = trigger.getBoundingClientRect();
    menu.style.left = Math.round(rect.left) + 'px';
    menu.style.bottom = Math.round(window.innerHeight - rect.top + 10) + 'px';
    menu.style.top = 'auto';
    // If the menu cannot fit above the trigger, keep it usable below.
    const height = menu.offsetHeight;
    if (rect.top - height - 10 < 8) {
      menu.style.bottom = 'auto';
      menu.style.top = Math.round(rect.bottom + 10) + 'px';
    }
    positionPreview();
  }

  function positionPreview() {
    if (!preview.classList.contains('is-open')) return;
    const menuRect = menu.getBoundingClientRect();
    const rowRect = activeRow?.getBoundingClientRect();
    const width = preview.offsetWidth || 360;
    const height = preview.offsetHeight || 320;
    let left = menuRect.right + 12;
    if (left + width > window.innerWidth - 12) left = menuRect.left - width - 12;
    const top = Math.min(Math.max(8, (rowRect?.top ?? menuRect.top) - 10),
      window.innerHeight - height - 12);
    preview.style.left = Math.round(Math.max(12, left)) + 'px';
    preview.style.top = Math.round(Math.max(8, top)) + 'px';
  }

  function openMenu() {
    if (open) return;
    open = true;
    cancelClose();
    layer.classList.add('is-open');
    trigger.setAttribute('aria-expanded', 'true');
    sidebar?.classList.add('flyout-open');
    positionMenu();
  }

  function hide() {
    cancelClose();
    open = false;
    layer.classList.remove('is-open');
    trigger.setAttribute('aria-expanded', 'false');
    preview.classList.remove('is-open');
    preview.removeAttribute('data-section');
    previewBuiltFor = null;
    activeSection = null;
    activeRow = null;
    for (const row of rows.values()) row.button.classList.remove('active');
    sidebar?.classList.remove('flyout-open');
    if (sidebar && !sidebar.matches(':hover')) {
      sidebar.dispatchEvent(new PointerEvent('pointerleave', {bubbles: false}));
    }
  }

  function openSection(id) {
    const section = SECTIONS.find(item => item[0] === id);
    if (!section) return;
    hide();
    if (adapter.openSection) adapter.openSection(id);
  }

  function previewFooter() {
    const expand = el('button', {type: 'button', class: 'settings-preview-expand',
      'aria-label': t('settingsTitle') + ' · ' + (activeSection ? copy(locale, SECTIONS.find(x => x[0] === activeSection)?.[2]) : ''),
      title: t('settingsTitle')}, icon('expand', 17));
    expand.addEventListener('click', () => openSection(activeSection));
    return el('footer', {class: 'settings-preview-foot'}, expand);
  }

  function buildPreview(id) {
    const title = copy(locale, SECTIONS.find(item => item[0] === id)?.[2]);
    const section = sectionElement(id, title);
    const body = [];

    if (id === 'general') {
      const languageGrid = el('div', {class: 'settings-language-grid'}, LANGUAGES.map(({code, native}) => {
        const option = el('button', {type: 'button', class: 'settings-language-option', lang: code,
          'aria-pressed': String(code === locale)}, native);
        option.addEventListener('click', () => {
          if (code === locale) return;
          hide();
          setTimeout(() => adapter.setLanguage?.(code), 120);
        });
        return option;
      }));
      body.push(el('h3', {}, t('generalLanguage')), el('p', {class: 'settings-help'}, t('generalLanguageDesc')), languageGrid,
        row(t('generalMotion'), t('generalMotionDesc'),
          segmented([['system', t('motionSystem')], ['reduce', t('motionReduce')]],
            getSetting('motion'), value => setSetting('motion', value), t('generalMotion'))));
    } else if (id === 'appearance') {
      body.push(row(t('appearanceTheme'), t('appearanceThemeDesc'),
        segmented([['system', t('themeSystem')], ['light', t('themeLight')], ['dark', t('themeDark')]],
          adapter.getTheme?.() || 'system', value => adapter.setTheme?.(value), t('appearanceTheme'))),
      row(t('appearanceDensity'), t('appearanceDensityDesc'),
        segmented([['comfortable', t('densityComfortable')], ['compact', t('densityCompact')]],
          getSetting('density'), value => setSetting('density', value), t('appearanceDensity'))),
      row(t('appearanceFont'), t('appearanceFontDesc'),
        segmented([['small', t('fontSmall')], ['default', t('fontDefault')], ['large', t('fontLarge')]],
          getSetting('fontSize'), value => setSetting('fontSize', value), t('appearanceFont'))));
    } else if (id === 'chat') {
      body.push(row(t('chatEnter'), t('chatEnterDesc'),
        segmented([[true, t('chatEnterSend')], [false, t('chatEnterModifier')]],
          getSetting('enterToSend'), value => setSetting('enterToSend', value), t('chatEnter'))),
      row(t('chatAutoScroll'), t('chatAutoScrollDesc'),
        toggle(getSetting('autoScroll'), value => setSetting('autoScroll', value), t('chatAutoScroll'))),
      row(t('chatTimestamps'), t('chatTimestampsDesc'),
        toggle(getSetting('timestamps'), value => setSetting('timestamps', value), t('chatTimestamps'))));
    } else if (id === 'model') {
      const keyState = el('span', {class: 'settings-badge', 'data-state': 'unknown'}, '—');
      const provider = el('span', {class: 'settings-value'}, '—');
      const model = el('span', {class: 'settings-value'}, '—');
      const picker = modelPicker({value: adapter.getModel?.() || 'default', defaultLabel: t('modelDefault'),
        ariaLabel: t('modelPreferred'), onChange: value => adapter.setModel?.(value)});
      const config = el('button', {type: 'button', class: 'settings-button'},
        icon(adapter.openModel ? 'model' : 'arrow', 16),
        adapter.openModel ? t('modelOpenConfig') : t('modelConfigArchive'));
      config.addEventListener('click', () => {
        hide();
        if (adapter.openModel) setTimeout(() => adapter.openModel(), 140);
        else location.assign('/ui/chat/');
      });
      assistantKey.status().then(payload => {
        const key = payload.key || payload;
        const assistant = payload.assistant || {};
        keyState.textContent = key.configured
          ? t('modelKeyConfigured') + (key.masked ? ' · ' + key.masked : '')
          : t('modelKeyMissing');
        keyState.dataset.state = key.configured ? 'on' : 'off';
        provider.textContent = key.configured ? 'DeepSeek' : (assistant.mode === 'llm' ? 'DeepSeek' : '—');
        model.textContent = key.model || assistant.model || '—';
      }).catch(() => {});
      body.push(el('h3', {}, t('modelPreferred')), el('p', {class: 'settings-help'}, t('modelPreferredDesc')), picker,
        row(t('modelKeyStatus'), null, keyState),
        row(t('modelProvider'), null, provider),
        row(t('modelCurrentModel'), null, model),
        config);
    } else if (id === 'data') {
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
            hide();
            setTimeout(() => adapter.setLanguage?.(payload.language), 140);
          }
        } catch {
          status.textContent = t('dataImportInvalid');
          status.dataset.state = 'bad';
        }
      });
      const exportButton = el('button', {type: 'button', class: 'settings-button'}, icon('download', 16), t('dataExportAction'));
      exportButton.addEventListener('click', () => {
        const payload = {version: 1, settings: getSettings(), theme: adapter.getTheme?.() || 'system',
          language: locale, model: adapter.getModel?.() || 'default'};
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
      const resetButton = el('button', {type: 'button', class: 'settings-button'}, icon('refresh', 16), t('dataResetAction'));
      resetButton.addEventListener('click', () => {
        resetSettings();
        adapter.setTheme?.('system');
        adapter.setModel?.('default');
        status.textContent = t('dataResetDone');
        status.dataset.state = 'good';
      });
      const clearButton = el('button', {type: 'button', class: 'settings-button'}, icon('terminal', 16), t('dataClearDraftsAction'));
      clearButton.addEventListener('click', () => {
        try { sessionStorage.removeItem('binaryrepair.welcome.draft'); } catch { /* Ignore. */ }
        adapter.clearDrafts?.();
        status.textContent = t('dataDraftsCleared');
        status.dataset.state = 'good';
      });
      body.push(row(t('dataExport'), t('dataExportDesc'), exportButton),
        row(t('dataImport'), t('dataImportDesc'), importButton),
        row(t('dataReset'), t('dataResetDesc'), resetButton),
        row(t('dataClearDrafts'), t('dataClearDraftsDesc'), clearButton),
        el('p', {class: 'settings-note'}, t('dataNote')), file, status);
    } else if (id === 'shortcuts') {
      const sendKeys = getSetting('enterToSend') ? 'Enter' : 'Ctrl/⌘ + Enter';
      const newlineKeys = getSetting('enterToSend') ? 'Shift + Enter' : 'Enter';
      body.push(row(t('shortcutSearch'), t('shortcutSearchDesc'), el('kbd', {}, 'Ctrl/⌘ + K')),
        row(t('shortcutSend'), t('shortcutSendDesc'), el('kbd', {}, sendKeys)),
        row(t('shortcutNewline'), t('shortcutNewlineDesc'), el('kbd', {}, newlineKeys)),
        row(t('shortcutClose'), t('shortcutCloseDesc'), el('kbd', {}, 'Esc')));
    } else if (id === 'about') {
      const backend = el('span', {class: 'settings-value'}, '—');
      const provider = el('span', {class: 'settings-value'}, '—');
      const model = el('span', {class: 'settings-value'}, '—');
      fetch('/healthz', {credentials: 'same-origin', cache: 'no-store'})
        .then(response => response.json()).then(value => { backend.textContent = value.backend || '—'; }).catch(() => {});
      assistantKey.status().then(payload => {
        const assistant = payload.assistant || {};
        provider.textContent = payload.key?.configured ? 'DeepSeek' : (assistant.mode === 'llm' ? 'DeepSeek' : '—');
        model.textContent = payload.key?.model || assistant.model || '—';
      }).catch(() => {});
      body.push(row(t('aboutVersion'), null, el('span', {class: 'settings-value'}, 'BinaryRepair')),
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
        el('p', {class: 'settings-note'}, t('aboutLocalOnly')));
    }

    section.append(...body);
    return section;
  }

  function showPreview(id, rowButton) {
    cancelClose();
    if (!open) openMenu();
    if (activeSection === id && preview.classList.contains('is-open') && previewBuiltFor === id) {
      activeRow = rowButton;
      positionPreview();
      return;
    }
    activeSection = id;
    activeRow = rowButton;
    for (const row of rows.values()) row.button.classList.toggle('active', row.button === rowButton);
    const content = buildPreview(id);
    preview.replaceChildren(content, previewFooter());
    preview.dataset.section = id;
    previewBuiltFor = id;
    preview.classList.add('is-open');
    positionPreview();
  }

  for (const [id, glyph, labelKey] of SECTIONS) {
    const arrow = el('span', {class: 'settings-menu-arrow', 'aria-hidden': 'true'}, icon('chevron', 14));
    const button = el('button', {type: 'button', class: 'settings-menu-item', role: 'menuitem',
      'data-section': id, 'aria-label': copy(locale, labelKey)},
    icon(glyph, 17), el('span', {class: 'settings-menu-label'}, copy(locale, labelKey)), arrow);
    button.addEventListener('pointerenter', () => showPreview(id, button));
    arrow.addEventListener('pointerenter', event => { event.stopPropagation(); showPreview(id, button); });
    button.addEventListener('focus', () => showPreview(id, button));
    button.addEventListener('click', () => openSection(id));
    rows.set(id, {button, arrow});
    menu.append(button);
  }

  trigger.addEventListener('pointerenter', openMenu);
  trigger.addEventListener('pointerleave', () => scheduleClose(220));
  trigger.addEventListener('click', event => {
    event.preventDefault();
    if (open) hide(); else openMenu();
  });
  trigger.addEventListener('keydown', event => {
    if (event.key !== 'ArrowUp') return;
    event.preventDefault();
    openMenu();
    rows.get('general')?.button.focus();
  });
  menu.addEventListener('pointerenter', cancelClose);
  menu.addEventListener('pointerleave', () => scheduleClose(160));
  preview.addEventListener('pointerenter', cancelClose);
  preview.addEventListener('pointerleave', () => scheduleClose(160));

  const outside = event => {
    if (!open) return;
    if (layer.contains(event.target) || trigger.contains(event.target)) return;
    hide();
  };
  const keydown = event => {
    if (event.key === 'Escape' && open) {
      event.preventDefault();
      hide();
      trigger.focus({preventScroll: true});
    }
  };
  const reposition = () => { if (open) positionMenu(); };
  document.addEventListener('pointerdown', outside, true);
  document.addEventListener('keydown', keydown, true);
  window.addEventListener('resize', reposition);
  window.addEventListener('scroll', reposition, true);

  return () => {
    hide();
    layer.remove();
    document.removeEventListener('pointerdown', outside, true);
    document.removeEventListener('keydown', keydown, true);
    window.removeEventListener('resize', reposition);
    window.removeEventListener('scroll', reposition, true);
  };
}
