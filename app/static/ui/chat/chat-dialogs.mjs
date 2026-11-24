import {assistantKey} from '../shared/assistant-key.mjs?v=20261120au';
import {LANGUAGES} from '../shared/languages.mjs?v=20261120au';
import {openSettingsDialog} from '../shared/settings-dialog.mjs?v=20261124b';
import {modelLabel, modelPicker} from '../shared/model-picker.mjs?v=20261120au';
import {enableDialogCloseMotion} from '../shared/dialog-motion.mjs?v=20261120au';
import {el} from '../shared/dom.mjs?v=20261120au';
import {control, displayTitle} from './chat-view.mjs?v=20261124x';

function dialog(title, content, t) {
  const trigger = document.activeElement;
  const popup = el('dialog', {class: 'popup', 'aria-label': title},
    el('header', {}, el('h2', {}, title), control(t('close'), () => popup.close(), {glyph: 'x', compact: true})), content);
  popup.addEventListener('close', () => {
    popup.remove();
    if (trigger?.isConnected) trigger.focus();
  });
  document.body.append(popup);
  enableDialogCloseMotion(popup);
  popup.showModal();
  return popup;
}

export function openSettings({t, locale, theme, preference, getTheme, getModel, setModel, clearDrafts, openModel, initialSection}) {
  return openSettingsDialog({
    locale,
    initialSection,
    getTheme: getTheme || (() => theme),
    setTheme: value => preference('theme', value),
    setLanguage: value => preference('language', value),
    getModel,
    setModel,
    clearDrafts,
    openModel,
  });
}

export function openSearch({t, engine, select}) {
  const matches = el('div', {class: 'search-results'});
  const input = el('input', {type: 'search', placeholder: t('search'), 'aria-label': t('search'),
    oninput: () => update()});
  function update() {
    const query = input.value.trim().toLowerCase();
    const results = [...engine.chats.values()].reverse().filter(chat => chat.events.length &&
      displayTitle(chat, t).toLowerCase().includes(query));
    matches.replaceChildren(...results.map(chat => control(displayTitle(chat, t), () => {
      popup.close();
      select(chat);
    }, {glyph: 'chat'})));
    if (!results.length) matches.append(el('p', {class: 'muted'}, t('noMatch')));
  }
  const popup = dialog(t('search'), el('div', {}, input, matches), t);
  update();
  input.focus();
}

export function openModel({t, model, preference}) {
  let selectedModel = model;
  const picker = modelPicker({value: model, defaultLabel: t('managedModel'),
    ariaLabel: t('modelChoice'), onChange: value => {
      selectedModel = value;
      preference('model', value);
    }});

  const status = el('output', {class: 'provider-status'}, t('managedKey'));
  const input = el('input', {type: 'password', id: 'assistant-key-input', class: 'key-input',
    autocomplete: 'off', spellcheck: 'false', placeholder: 'sk-…', 'aria-label': t('apiKey')});
  const result = el('p', {class: 'key-result muted', role: 'status'});
  const save = control(t('keySave'), () => saveKey(), {tone: 'primary'});
  const test = control(t('keyTest'), () => testKey());
  const clear = control(t('keyClear'), () => clearKey());
  const help = el('p', {class: 'muted model-help'}, t('keySetup'));
  const editor = el('div', {class: 'key-editor'}, input,
    el('div', {class: 'key-actions'}, save, test, clear));

  function testResult(outcome) {
    if (!outcome?.ok) return t('keyFailed').replace('{detail}', outcome?.error || 'unknown');
    const requestedId = selectedModel === 'default' ? null : selectedModel;
    const requested = requestedId ? modelLabel(requestedId, t('managedModel')) : null;
    const actual = typeof outcome.model === 'string' ? outcome.model : '';
    if (requestedId && actual && actual.toLowerCase() !== requestedId.toLowerCase()) {
      return t('keyPassed') + ' · ' + requested + ' → ' + actual
        + (t('keyAliasSuffix') || ' (provider-returned model)');
    }
    return t('keyPassed') + ' · ' + (requested || actual || '—');
  }

  function render(payload) {
    const key = payload?.key ?? payload ?? {};
    status.textContent = t('keyCurrent').replace('{status}',
      key.configured
        ? (key.source === 'environment' ? t('managedKey') : (key.masked || '•••'))
        : t('keyNotConfigured'));
    const environment = key.source === 'environment';
    editor.style.display = environment ? 'none' : '';
    help.hidden = Boolean(key.configured);
    clear.disabled = !key.can_clear;
    if (environment) result.textContent = t('managedKey');
  }

  async function refresh() {
    try { render(await assistantKey.status()); }
    catch { result.textContent = t('keyReadFailed'); }
  }

  async function saveKey() {
    const value = input.value.trim();
    if (!value) { result.textContent = t('keyRequired'); input.focus(); return; }
    save.disabled = true;
    test.disabled = true;
    result.textContent = t('keyTesting');
    try {
      const saved = await assistantKey.save(value);
      input.value = '';
      render(saved);
      result.textContent = t('keySaved');
      const outcome = await assistantKey.test(selectedModel === 'default' ? null : selectedModel);
      result.textContent = testResult(outcome);
      await refresh();
    } catch (error) {
      result.textContent = t('keyFailed').replace('{detail}', error.message);
    } finally {
      save.disabled = false;
      test.disabled = false;
    }
  }

  async function testKey() {
    test.disabled = true;
    result.textContent = t('keyTesting');
    try {
      const outcome = await assistantKey.test(selectedModel === 'default' ? null : selectedModel);
      result.textContent = testResult(outcome);
      await refresh();
    } catch (error) {
      result.textContent = t('keyFailed').replace('{detail}', error.message);
    } finally {
      test.disabled = false;
    }
  }

  async function clearKey() {
    clear.disabled = true;
    try {
      render(await assistantKey.clear());
      result.textContent = t('keyCleared');
    } catch (error) {
      result.textContent = t('keyFailed').replace('{detail}', error.message);
    } finally {
      clear.disabled = false;
    }
  }

  const modal = dialog(t('modelConfig'), el('div', {class: 'model-form'},
    el('section', {class: 'model-key'},
      el('div', {}, el('p', {class: 'model-label'}, t('apiKey')), status),
      editor, result, help),
    el('p', {class: 'model-label'}, t('modelChoice')),
    picker,
    el('p', {class: 'muted model-help'}, t('previewModel'))), t);
  refresh();
  return modal;
}

export function openLanguage({t, locale, choose}) {
  const field = el('fieldset', {},
    el('div', {class: 'segments'}, LANGUAGES.map(({code, native}) =>
      el('label', {}, el('input', {type: 'radio', name: 'language-picker', value: code,
        checked: code === locale,
        onchange: () => {
          popup.close();
          choose(code);
        }}), el('span', {}, native)))));
  const popup = dialog(t('language'), el('div', {class: 'settings'}, field), t);
}
