/**
 * Page-slide transitions between the conversation page and the archive.
 *
 * Presentation only: navigation still happens normally, it is just wrapped in
 * a PowerPoint-style horizontal push. Chat → archive slides left, archive →
 * chat slides right. The destination page reads a one-shot sessionStorage flag
 * and slides in from the matching side.
 */

import {motionReduced} from './motion.mjs?v=20261120as';

const KEY = 'binaryrepair.page-slide';
const EXIT_MS = 320;
const ENTER_MS = 440;
const FRESH_MS = 6000;
const ordered = ['chat', 'archive'];

function pageKind(pathname = location.pathname) {
  const clean = pathname.replace(/\/+$/, '') || '/';
  if (clean === '/ui/chat') return 'chat';
  if (clean === '/ui') return 'archive';
  return null;
}

function directionBetween(from, to) {
  if (!ordered.includes(from) || !ordered.includes(to) || from === to) return null;
  return ordered.indexOf(to) > ordered.indexOf(from) ? 'forward' : 'backward';
}

function reducedMotion() {
  return motionReduced();
}

function readPending() {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || typeof data.ts !== 'number' || !['forward', 'backward'].includes(data.direction)) return null;
    if (!['chat', 'archive'].includes(data.to)) return null;
    if (Date.now() - data.ts > FRESH_MS) return null;
    return data;
  } catch {
    return null;
  }
}

let leaving = false;
let entering = false;
let pending = readPending();
let observer = null;

export function pageSlideActive() {
  const root = document.documentElement;
  return leaving || entering ||
    root.classList.contains('slide-exit-forward') ||
    root.classList.contains('slide-exit-backward') ||
    root.classList.contains('slide-enter-forward') ||
    root.classList.contains('slide-enter-backward');
}

function clearSlideClasses() {
  const root = document.documentElement;
  root.classList.remove('slide-exit-forward', 'slide-exit-backward',
    'slide-enter-forward', 'slide-enter-backward');
}

function playEntrance() {
  if (entering || !pending) return;
  if (reducedMotion()) {
    pending = null;
    try { sessionStorage.removeItem(KEY); } catch { /* one-shot hint only */ }
    return;
  }
  const destination = pageKind();
  if (pending.to !== destination) return;
  if (Date.now() - pending.ts > FRESH_MS) { pending = null; return; }
  const direction = pending.direction;
  pending = null;
  entering = true;
  try { sessionStorage.removeItem(KEY); } catch { /* one-shot hint only */ }
  const root = document.documentElement;
  root.classList.add('slide-enter-' + direction);
  setTimeout(() => {
    root.classList.remove('slide-enter-' + direction);
    entering = false;
  }, ENTER_MS + 120);
}

export function slideTo(href, forcedDirection = null) {
  if (leaving) return;
  const url = new URL(href, location.href);
  if (url.origin !== location.origin) { location.assign(url.href); return; }
  const from = pageKind();
  const to = pageKind(url.pathname);
  const direction = forcedDirection || directionBetween(from, to);
  if (!direction || !to || reducedMotion()) { location.assign(url.href); return; }
  leaving = true;
  try {
    sessionStorage.setItem(KEY, JSON.stringify({direction, to, ts: Date.now()}));
  } catch { /* navigation still works without the entrance hint */ }
  document.documentElement.classList.add('slide-exit-' + direction);
  setTimeout(() => location.assign(url.href), EXIT_MS);
}

function prefetch(url) {
  if (document.querySelector(`link[rel="prefetch"][href="${url}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'prefetch';
  link.href = url;
  document.head.append(link);
}

function installLinkInterception() {
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null;
    if (!anchor) return;
    if (anchor.hasAttribute('download')) return;
    if (anchor.target && anchor.target !== '' && anchor.target !== '_self') return;
    const url = new URL(anchor.getAttribute('href'), location.href);
    if (url.origin !== location.origin) return;
    const direction = directionBetween(pageKind(), pageKind(url.pathname));
    if (!direction) return;
    event.preventDefault();
    slideTo(url.href, direction);
  }, {capture: true});

  const warm = event => {
    const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null;
    if (!anchor) return;
    const url = new URL(anchor.getAttribute('href'), location.href);
    if (url.origin === location.origin && directionBetween(pageKind(), pageKind(url.pathname))) prefetch(url.href);
  };
  document.addEventListener('pointerdown', warm, {passive: true});
  document.addEventListener('focusin', warm, {passive: true});
}

function installEntranceWatcher() {
  const app = document.getElementById('app');
  if (!app) return;
  if (app.firstElementChild) { playEntrance(); return; }
  observer = new MutationObserver(() => {
    if (!app.firstElementChild) return;
    observer.disconnect();
    observer = null;
    playEntrance();
  });
  observer.observe(app, {childList: true});
  setTimeout(() => {
    observer?.disconnect();
    observer = null;
  }, 2500);
}

window.addEventListener('pageshow', event => {
  if (!event.persisted) return;
  leaving = false;
  entering = false;
  clearSlideClasses();
});

installLinkInterception();
installEntranceWatcher();
