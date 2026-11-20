import {motionReduced} from '../shared/motion.mjs?v=20261120as';

// Animate the sidebar width and keep the content grid in step with it.
export function bindSidebarSpring(sidebar, toggle, options = {}) {
  const {pinned: initialPinned = false, onChange = null} = options;
  const hover = matchMedia('(hover: hover) and (pointer: fine)');
  const shell = sidebar.parentElement;
  let hoverOpen = false;
  let focusOpen = false;
  let pinned = Boolean(initialPinned);
  let frame = 0;
  let position = pinned ? 1 : 0;
  let velocity = 0;
  let previous = 0;
  let target = position;
  let metrics = null;

  function lengthInPx(value) {
    const text = String(value || '').trim();
    const number = parseFloat(text);
    if (!Number.isFinite(number)) return 0;
    if (text.endsWith('rem')) return number * (parseFloat(getComputedStyle(document.documentElement).fontSize) || 16);
    if (text.endsWith('px')) return number;
    return 0;
  }

  function readMetrics() {
    if (!shell) return;
    const style = getComputedStyle(sidebar);
    metrics = {
      open: lengthInPx(style.getPropertyValue('--open-nav')),
      rail: lengthInPx(style.getPropertyValue('--rail')),
      left: parseFloat(style.left) || 0,
    };
  }

  function draw() {
    // Small overshoot is intentionally clipped at the usable bounds.
    const reveal = Math.max(0, Math.min(1, position));
    sidebar.style.setProperty('--reveal', reveal);
    if (!shell) return;
    if (!metrics) readMetrics();
    const {open, rail, left} = metrics || {};
    if (!open || !rail) return;
    const visible = open - (open - rail + left) * (1 - reveal);
    // Reserve the space the visible panel needs so the page shifts instead of overlapping it.
    shell.style.setProperty('--nav-w', (left + visible).toFixed(2) + 'px');
    shell.style.setProperty('--nav-visible', visible.toFixed(2) + 'px');
  }

  function step(now) {
    const dt = Math.min((now - previous) / 1000, .024);
    previous = now;
    // Original first-version spring: immediate, soft expansion with a hint of overshoot.
    const acceleration = 520 * (target - position) - 36 * velocity;
    velocity += acceleration * dt;
    position += velocity * dt;
    if (Math.abs(target - position) < .003 && Math.abs(velocity) < .025) {
      position = target;
      velocity = 0;
      frame = 0;
    } else frame = requestAnimationFrame(step);
    draw();
  }

  function sync() {
    target = hoverOpen || focusOpen || pinned ? 1 : 0;
    sidebar.dataset.expanded = String(Boolean(target));
    toggle.setAttribute('aria-expanded', String(Boolean(target)));
    toggle.setAttribute('aria-pressed', String(pinned));
    if (motionReduced()) {
      cancelAnimationFrame(frame);
      frame = 0;
      position = target;
      velocity = 0;
      draw();
      return;
    }
    if (position === target && !frame) {
      draw();
      return;
    }
    if (!frame) {
      previous = performance.now();
      frame = requestAnimationFrame(step);
    }
  }

  sidebar.addEventListener('pointerenter', event => {
    if (!hover.matches || event.pointerType === 'touch') return;
    hoverOpen = true;
    sync();
  });
  sidebar.addEventListener('pointerleave', () => {
    if (sidebar.classList.contains('flyout-open')) return;
    hoverOpen = false;
    sync();
  });
  sidebar.addEventListener('focusin', () => {
    if (!sidebar.matches(':focus-within') || !sidebar.querySelector(':focus-visible')) return;
    focusOpen = true;
    sync();
  });
  sidebar.addEventListener('focusout', event => {
    if (sidebar.contains(event.relatedTarget)) return;
    focusOpen = false;
    sync();
  });
  toggle.addEventListener('click', () => {
    pinned = !pinned;
    if (!pinned) {
      hoverOpen = false;
      focusOpen = false;
    }
    onChange?.(pinned);
    sync();
  });
  const owner = new AbortController();
  const refreshMetrics = () => {
    metrics = null;
    sync();
  };
  window.addEventListener('binaryrepair:settings', refreshMetrics);
  window.addEventListener('resize', refreshMetrics);
  sync();
  draw();
  return () => {
    owner.abort();
    window.removeEventListener('binaryrepair:settings', refreshMetrics);
    window.removeEventListener('resize', refreshMetrics);
    cancelAnimationFrame(frame);
  };
}
