/**
 * Shared UI language catalogue for the welcome / conversation / archive pages.
 * Codes follow BCP 47; `native` is what the picker shows, `short` is used in
 * tight headers.
 */
export const LANGUAGES = [
  {code: 'en', native: 'English', short: 'EN'},
  {code: 'zh-Hans', native: '简体中文', short: '简'},
  {code: 'zh-Hant', native: '繁體中文', short: '繁'},
  {code: 'fr', native: 'Français', short: 'FR'},
  {code: 'de', native: 'Deutsch', short: 'DE'},
  {code: 'es', native: 'Español', short: 'ES'},
  {code: 'pt', native: 'Português', short: 'PT'},
  {code: 'ja', native: '日本語', short: 'JA'},
  {code: 'ko', native: '한국어', short: 'KO'},
];

export const LANGUAGE_CODES = LANGUAGES.map(language => language.code);

export function isLanguage(code) {
  return LANGUAGE_CODES.includes(code);
}

export function languageName(code) {
  return LANGUAGES.find(language => language.code === code)?.native ?? 'English';
}

export function languageShort(code) {
  return LANGUAGES.find(language => language.code === code)?.short ?? 'EN';
}

/** Best-effort match of the browser language to a supported UI language. */
export function detectLanguage() {
  const tags = typeof navigator === 'undefined'
    ? []
    : (navigator.languages?.length ? navigator.languages : [navigator.language]);
  for (const tag of tags) {
    const lower = String(tag || '').toLowerCase();
    if (!lower) continue;
    if (lower.startsWith('zh')) {
      return /hant|tw|hk|mo/.test(lower) ? 'zh-Hant' : 'zh-Hans';
    }
    const base = lower.split('-')[0];
    if (LANGUAGE_CODES.includes(base)) return base;
  }
  return 'en';
}
