/**
 * Browser-local presentation preferences for the welcome/chat/archive UI.
 * Everything here is cosmetic or client-side behavior; nothing is sent to the
 * backend. Values are validated against their allowed sets before they apply.
 */
const KEY = 'binaryrepair.settings.v1';

export const SETTINGS_DEFAULTS = Object.freeze({
  motion: 'system',       // system | reduce
  density: 'comfortable', // comfortable | compact
  fontSize: 'default',    // small | default | large
  enterToSend: true,
  autoScroll: true,
  timestamps: true,
});

export const SETTINGS_ALLOWED = Object.freeze({
  motion: ['system', 'reduce'],
  density: ['comfortable', 'compact'],
  fontSize: ['small', 'default', 'large'],
  enterToSend: [true, false],
  autoScroll: [true, false],
  timestamps: [true, false],
});

const systemMotion = matchMedia('(prefers-reduced-motion: reduce)');
let settings = read();

function valid(key, value) {
  return SETTINGS_ALLOWED[key]?.includes(value) ?? false;
}

function read() {
  const next = {...SETTINGS_DEFAULTS};
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const saved = JSON.parse(raw);
      if (saved && typeof saved === 'object') {
        for (const key of Object.keys(SETTINGS_DEFAULTS)) {
          if (valid(key, saved[key])) next[key] = saved[key];
        }
      }
    }
    // Migrate the density that the archive page used to keep on its own.
    if (!localStorage.getItem(KEY)) {
      const legacy = localStorage.getItem('binaryrepair.ui.density');
      if (valid('density', legacy)) next.density = legacy;
    }
  } catch { /* Preferences are optional; defaults remain usable. */ }
  return next;
}

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
  } catch { /* Keep the choice for this page only. */ }
}

export function getSettings() {
  return {...settings};
}

export function getSetting(key) {
  return settings[key];
}

export function motionReduced() {
  return settings.motion === 'reduce' || (settings.motion === 'system' && systemMotion.matches);
}

export function applySettings() {
  const root = document.documentElement;
  root.dataset.motion = motionReduced() ? 'reduce' : 'full';
  root.dataset.density = settings.density;
  root.dataset.fontSize = settings.fontSize;
  root.dataset.timestamps = settings.timestamps ? 'on' : 'off';
}

export function setSetting(key, value) {
  if (!valid(key, value) || settings[key] === value) return;
  settings = {...settings, [key]: value};
  persist();
  applySettings();
  window.dispatchEvent(new CustomEvent('binaryrepair:settings', {detail: {key, value}}));
}

export function resetSettings() {
  settings = {...SETTINGS_DEFAULTS};
  try {
    localStorage.removeItem(KEY);
    localStorage.removeItem('binaryrepair.ui.density');
  } catch { /* Ignore unavailable storage. */ }
  applySettings();
  window.dispatchEvent(new CustomEvent('binaryrepair:settings', {detail: {key: null, value: null}}));
}

export function importSettings(payload) {
  if (!payload || typeof payload !== 'object') return false;
  const next = {...settings};
  let changed = false;
  for (const key of Object.keys(SETTINGS_DEFAULTS)) {
    if (valid(key, payload[key])) {
      next[key] = payload[key];
      changed = true;
    }
  }
  if (!changed) return false;
  settings = next;
  persist();
  applySettings();
  window.dispatchEvent(new CustomEvent('binaryrepair:settings', {detail: {key: null, value: null}}));
  return true;
}

systemMotion.addEventListener('change', () => applySettings());
window.addEventListener('storage', event => {
  if (event.key !== KEY) return;
  settings = read();
  applySettings();
  window.dispatchEvent(new CustomEvent('binaryrepair:settings', {detail: {key: null, value: null}}));
});

applySettings();
