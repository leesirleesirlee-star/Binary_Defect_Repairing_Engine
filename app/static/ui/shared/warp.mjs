/**
 * Cross-fade hand-off between the welcome page and the console.
 *
 * Pure presentation: the welcome page still saves the draft and navigates in the
 * same way. There is no overlay, no scan and no flash - the old page simply
 * fades to its own background and the console fades its content in, which reads
 * as one continuous cross-fade between the two loads. With reduced motion, or
 * without JavaScript, both pages appear immediately.
 */

const KEY = 'binaryrepair.warp';
const FRESH_MS = 8000;
export const EXIT_MS = 220;

function reducedMotion() {
  try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return false; }
}

let leaving = false;

/** Fade the welcome page out; resolves as soon as the fade is done. */
export function playExit() {
  if (leaving || reducedMotion() || typeof document === 'undefined') return Promise.resolve(false);
  leaving = true;
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ts: Date.now()}));
  } catch { /* One-shot hint only; the console still opens without it. */ }
  document.documentElement.classList.add('warp-leaving');
  return new Promise(resolve => {
    setTimeout(() => resolve(true), EXIT_MS);
  });
}

/** Fade the console content in when the previous page left a fresh hint. */
export function arrive() {
  let hint = null;
  try {
    const raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    if (raw) hint = JSON.parse(raw);
  } catch {
    return false;
  }
  if (!hint || typeof hint.ts !== 'number') return false;
  if (Date.now() - hint.ts > FRESH_MS) return false;
  if (reducedMotion()) return false;
  const root = document.documentElement;
  root.classList.add('warp-arriving');
  setTimeout(() => root.classList.remove('warp-arriving'), 340);
  return true;
}
