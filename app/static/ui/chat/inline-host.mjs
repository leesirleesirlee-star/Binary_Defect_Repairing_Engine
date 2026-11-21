/** Render the existing review and event dialogs inline in execution details. */
function pane() {
  return document.querySelector('#execution-pane');
}
function scroll() {
  return document.querySelector('#execution-pane .execution-scroll');
}
function place(dialog) {
  const panel = pane(); const area = scroll();
  if (!panel || !area || dialog.dataset.inline === '1') return;
  dialog.dataset.inline = '1';
  panel.closest('.workspace')?.classList.add('inspect-before-run', 'xr-inline-mode');
  dialog.classList.add('xr-inline');
  dialog.removeAttribute('open');
  area.append(dialog);
  dialog.setAttribute('open', '');
}
const original = HTMLDialogElement.prototype.showModal;
HTMLDialogElement.prototype.showModal = function () {
  if (this.matches('.guided-dialog, .ev-dialog')) {
    requestAnimationFrame(() => place(this));
    return;
  }
  return original.call(this);
};
async function boot() {
  if (!pane()) {
    const observer = new MutationObserver(() => { if (pane()) { observer.disconnect(); boot(); } });
    observer.observe(document.getElementById('app') || document.body, {childList: true, subtree: true});
    return;
  }
  scroll()?.closest('.workspace')?.classList.add('inspect-before-run');
  try {
    await import('./guided-intake.mjs?v=20261120aw');
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      const card = document.querySelector('.guided-launch');
      if (card) {
        clearInterval(timer);
        card.querySelector('button')?.click();
        card.replaceChildren();
      } else if (attempts > 40) clearInterval(timer);
    }, 100);
  } catch (error) {
    console.error('inline review unavailable', error);
  }
}
boot();
