/**
 * Short interaction-time performance mode.
 *
 * Adds `html.perf-busy` for a bounded window around input, scrolling and page
 * transitions. `perf.css` then suspends only the expensive live backdrop
 * filters; the idle frosted appearance is restored as soon as the window ends.
 * No DOM content, labels, layout or behaviour is changed.
 */
const root = document.documentElement;
let timer = 0;
let until = 0;

function schedule() {
  if (timer) return;
  const delay = Math.max(0, until - performance.now());
  timer = window.setTimeout(() => {
    timer = 0;
    if (performance.now() < until) { schedule(); return; }
    root.classList.remove('perf-busy');
  }, delay + 16);
}

function busy(milliseconds = 700) {
  root.classList.add('perf-busy');
  until = Math.max(until, performance.now() + milliseconds);
  schedule();
}

const options = {capture: true, passive: true};

document.addEventListener('pointerdown', () => busy(1100), options);
document.addEventListener('keydown', () => busy(800), {capture: true});
document.addEventListener('focusin', () => busy(500), {capture: true});
document.addEventListener('touchstart', () => busy(1100), options);
document.addEventListener('wheel', () => busy(220), options);
// Any pointer travel suspends the large live blurs; when the pointer stops the
// frosted idle appearance returns. This makes hover/scroll feel immediate
// without changing the resting page.
document.addEventListener('pointermove', () => busy(140), options);
document.addEventListener('scroll', () => busy(180), options);

// Hoverable controls: keep the blur suspended for the short hover/active
// transition, then restore it when the pointer stops moving.
document.addEventListener('pointerover', event => {
  if (event.target.closest?.('.button, .control, .pill, .lang, .quiet, .source-item, .task-row, .nav-link, .model-option, .settings-nav-item, .composer textarea')) {
    busy(240);
  }
}, {capture: true, passive: true});

// Sidebar spring expansion is hover-driven, not a click; keep the expensive
// blur off for the duration of its natural opening/closing motion.
document.addEventListener('pointerenter', event => {
  if (event.target.closest?.('.desktop-nav, .rail')) busy(900);
}, {capture: true, passive: true});

// Optional hook for page transitions that remove/replace large surfaces.
window.addEventListener('binaryrepair:perf-busy', () => busy(1000));

// Also make the first paint/initial entry animation cheap.
busy(1200);
