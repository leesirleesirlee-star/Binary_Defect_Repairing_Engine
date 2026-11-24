import {motionReduced} from './motion.mjs?v=20261125c';

/**
 * Fade-scale close motion for modal <dialog> elements.
 *
 * Presentation only: dialogs still open and close exactly as before; only the
 * closing frame is animated. Reduced-motion users keep the instant close.
 */

const EASE = 'cubic-bezier(.42, 0, .58, 1)';
const CLOSE_MS = 200;

export function enableDialogCloseMotion(dialog) {
  if (!dialog || dialog.dataset.motionBound === 'true') return dialog;
  dialog.dataset.motionBound = 'true';
  const nativeClose = dialog.close.bind(dialog);
  dialog.close = () => {
    if (!dialog.open || dialog.dataset.closing === 'true') return;
    if (motionReduced()) {
      nativeClose();
      return;
    }
    dialog.dataset.closing = 'true';
    // Release the CSS open animation so the closing fade fully owns the element.
    for (const running of dialog.getAnimations()) {
      if (running instanceof CSSAnimation) running.cancel();
    }
    const animation = dialog.animate([
      {opacity: 1, transform: 'none'},
      {opacity: 0, transform: 'scale(.985) translateY(4px)'},
    ], {duration: CLOSE_MS, easing: EASE});
    animation.onfinish = animation.oncancel = () => {
      delete dialog.dataset.closing;
      nativeClose();
    };
  };
  return dialog;
}
