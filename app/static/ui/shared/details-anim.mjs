/**
 * Smooth open/close motion for native <details> disclosures.
 *
 * Presentation only: the details element keeps its native semantics, keyboard
 * activation and aria state. Height/opacity are animated with the Web Animations
 * API so opening and closing both glide instead of popping. Reduced-motion users
 * get the native instant toggle.
 */

import {motionReduced} from './motion.mjs?v=20261120au';

const EASE = 'cubic-bezier(.42, 0, .58, 1)';
const OPEN_MS = 340;
const CLOSE_MS = 280;

function reducedMotion() {
  return motionReduced();
}

export function animateDetails(details) {
  if (!(details instanceof HTMLDetailsElement) || details.dataset.motionBound === 'true') return details;
  const summary = details.querySelector(':scope > summary');
  const panel = details.querySelector(':scope > .detail-body') ?? details.lastElementChild;
  if (!summary || !panel || panel === summary) return details;
  details.dataset.motionBound = 'true';

  let busy = false;

  summary.addEventListener('click', event => {
    event.preventDefault();
    if (busy) return;
    const opening = !details.open;
    if (reducedMotion()) {
      details.open = opening;
      return;
    }
    const panelStyle = getComputedStyle(panel);
    const from = {
      height: `${panel.getBoundingClientRect().height}px`,
      opacity: panelStyle.opacity,
    };
    const to = {height: '0px', opacity: 0};
    busy = true;
    panel.style.overflow = 'hidden';
    if (opening) {
      details.open = true;
      const height = panel.getBoundingClientRect().height;
      const animation = panel.animate([to, {...from, height: `${height}px`, opacity: 1}],
        {duration: OPEN_MS, easing: EASE});
      animation.onfinish = animation.oncancel = () => {
        busy = false;
        panel.style.overflow = '';
      };
    } else {
      const animation = panel.animate([from, to], {duration: CLOSE_MS, easing: EASE});
      animation.onfinish = animation.oncancel = () => {
        details.open = false;
        busy = false;
        panel.style.overflow = '';
      };
    }
  });

  return details;
}
