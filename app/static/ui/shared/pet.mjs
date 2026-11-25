// Interactive pixel companion shared by every BinaryRepair page.
// It is deliberately self-contained: no network, no task data, no verdict logic.
const MESSAGES = {
  idle: ['我在这里陪你看修复。', '点我可以摸摸头。', '有疑问可以点下面的问题按钮。'],
  waiting: ['正在等你上传二进制和用例。', '把有问题的 ELF 交给我吧。'],
  thinking: ['我在读 verdict、manifest 和 journal…', '正在核对证据，请稍候。'],
  running: ['修复流程正在跑，我会盯着。', '先别走开，马上就有结果。'],
  happy: ['这一步完成了！', '有进展了，继续看证据吧。', '我帮你把重点记下来了。'],
  error: ['这一步失败了，先看原因。', '别急，失败信息也能帮我们定位问题。'],
  sleeping: ['Zzz… 有任务时叫醒我。'],
};
const state = {dock: null, bubble: null, pet: null, label: null, timer: 0, hideTimer: 0,
  clickCount: 0, dragging: false, moved: false, startX: 0, startY: 0, originX: 0,
  originY: 0, sleepTimer: 0, current: 'idle'};

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'class') node.className = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  node.append(...children.flat().filter(value => value !== null && value !== undefined && value !== false));
  return node;
}

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  node.append(...children.flat().filter(value => value !== null && value !== undefined && value !== false));
  return node;
}

function pixelPet() {
  const eye = (x) => svg('g', {class: 'pet-eye', transform: `translate(${x} 27)`},
    svg('rect', {x: 0, y: 0, width: 6, height: 6, rx: 1, class: 'pet-eye-core'}),
    svg('rect', {x: 0, y: 0, width: 2, height: 6, class: 'pet-eye-shine'}));
  return svg('svg', {class: 'pet-svg', viewBox: '0 0 64 64', 'aria-hidden': 'true',
    role: 'img'},
    svg('g', {class: 'pet-tail'}, svg('rect', {x: 49, y: 37, width: 11, height: 6, rx: 2})),
    svg('g', {class: 'pet-legs'},
      svg('rect', {x: 16, y: 45, width: 7, height: 13, rx: 2}),
      svg('rect', {x: 27, y: 45, width: 7, height: 13, rx: 2}),
      svg('rect', {x: 39, y: 45, width: 7, height: 13, rx: 2}),
      svg('rect', {x: 49, y: 45, width: 7, height: 13, rx: 2})),
    svg('rect', {x: 9, y: 12, width: 9, height: 16, rx: 3, class: 'pet-ear'}),
    svg('rect', {x: 46, y: 12, width: 9, height: 16, rx: 3, class: 'pet-ear'}),
    svg('rect', {x: 10, y: 19, width: 44, height: 31, rx: 7, class: 'pet-body'}),
    svg('rect', {x: 17, y: 20, width: 30, height: 8, rx: 3, class: 'pet-head-highlight'}),
    svg('g', {class: 'pet-eyes'}, eye(21), eye(37)),
    svg('rect', {x: 29, y: 37, width: 8, height: 3, rx: 1.5, class: 'pet-mouth'}),
    svg('rect', {x: 24, y: 18, width: 4, height: 3, rx: 1, class: 'pet-blush'}),
    svg('rect', {x: 38, y: 18, width: 4, height: 3, rx: 1, class: 'pet-blush'}));
}

function ensureDock() {
  if (state.dock && document.body.contains(state.dock)) return state.dock;
  const bubbles = el('div', {class: 'pet-bubble', role: 'status', 'aria-live': 'polite'});
  const hearts = el('div', {class: 'pet-hearts', 'aria-hidden': 'true'});
  const label = el('span', {class: 'pet-label'});
  const pet = el('button', {class: 'pet-toggle', type: 'button',
    'aria-label': 'BinaryRepair 互动小宠物'}, pixelPet());
  const dock = el('section', {class: 'pet-dock', 'data-state': 'idle', 'data-page':
    location.pathname.includes('/ui/') && !location.pathname.includes('/chat') ? 'workbench' : 'chat'},
    bubbles, el('div', {class: 'pet-stand'}, pet), hearts, label);
  document.body.append(dock);
  state.dock = dock; state.bubble = bubbles; state.pet = pet; state.label = label;
  state.hearts = hearts;
  bind(pet, dock);
  return dock;
}

function speak(text, duration = 4200) {
  if (!state.bubble) return;
  state.bubble.textContent = text;
  state.bubble.classList.add('show');
  clearTimeout(state.hideTimer);
  state.hideTimer = setTimeout(() => state.bubble?.classList.remove('show'), duration);
}

function setState(next, message = '') {
  const dock = ensureDock();
  const value = ['idle', 'waiting', 'thinking', 'running', 'happy', 'error', 'sleeping'].includes(next)
    ? next : 'idle';
  state.current = value;
  dock.dataset.state = value;
  const texts = MESSAGES[value] || MESSAGES.idle;
  const text = message || texts[Math.floor(Math.random() * texts.length)];
  state.label.textContent = text;
  if (value !== 'sleeping') speak(text, 4800);
  if (value === 'happy') hearts(4);
  clearTimeout(state.sleepTimer);
  if (value === 'idle') {
    state.sleepTimer = setTimeout(() => setState('sleeping'), 90000);
  }
}

function hearts(count = 3) {
  if (!state.hearts) return;
  for (let index = 0; index < count; index += 1) {
    const heart = el('span', {class: 'pet-heart'}, '♥');
    heart.style.setProperty('--pet-heart-x', (Math.random() * 32 - 16).toFixed(0) + 'px');
    heart.style.animationDelay = (index * 90) + 'ms';
    state.hearts.append(heart);
    setTimeout(() => heart.remove(), 1300);
  }
}

function bind(pet, dock) {
  pet.addEventListener('click', () => {
    if (state.moved) { state.moved = false; return; }
    state.clickCount += 1;
    if (state.clickCount % 5 === 0) {
      speak('摸摸头，继续加油！', 3600);
      hearts(6);
      setState('happy', '被你摸到了！');
    } else {
      setState('happy');
    }
  });
  pet.addEventListener('pointerenter', () => {
    if (state.current === 'idle') speak('需要我解释哪一部分？', 2600);
  });
  pet.addEventListener('pointerleave', () => {
    clearTimeout(state.hideTimer);
    state.hideTimer = setTimeout(() => state.bubble?.classList.remove('show'), 1200);
  });
  pet.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    state.dragging = true;
    state.moved = false;
    state.startX = event.clientX;
    state.startY = event.clientY;
    const rect = dock.getBoundingClientRect();
    state.originX = rect.left;
    state.originY = rect.top;
    dock.style.left = rect.left + 'px';
    dock.style.top = rect.top + 'px';
    dock.style.right = 'auto';
    dock.style.bottom = 'auto';
    pet.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  });
  pet.addEventListener('pointermove', event => {
    if (!state.dragging) return;
    const dx = event.clientX - state.startX;
    const dy = event.clientY - state.startY;
    if (Math.hypot(dx, dy) > 4) state.moved = true;
    const width = dock.offsetWidth;
    const height = dock.offsetHeight;
    const left = Math.max(8, Math.min(window.innerWidth - width - 8, state.originX + dx));
    const top = Math.max(8, Math.min(window.innerHeight - height - 8, state.originY + dy));
    dock.style.left = left + 'px';
    dock.style.top = top + 'px';
  });
  pet.addEventListener('pointerup', event => {
    if (!state.dragging) return;
    state.dragging = false;
    pet.releasePointerCapture?.(event.pointerId);
    if (state.moved) {
      try {
        localStorage.setItem('binaryrepair.pet.position', JSON.stringify({
          left: dock.style.left, top: dock.style.top,
        }));
      } catch { /* private mode */ }
    }
  });
  window.addEventListener('mousemove', event => {
    if (!state.pet) return;
    const rect = state.pet.getBoundingClientRect();
    const x = Math.max(-1, Math.min(1, (event.clientX - (rect.left + rect.width / 2)) / 90));
    const y = Math.max(-1, Math.min(1, (event.clientY - (rect.top + rect.height / 2)) / 90));
    state.pet.style.setProperty('--pet-look-x', (x * 2).toFixed(1) + 'px');
    state.pet.style.setProperty('--pet-look-y', (y * 1.5).toFixed(1) + 'px');
  }, {passive: true});
  window.addEventListener('binaryrepair:pet-state', event => {
    const detail = event.detail || {};
    setState(detail.state || 'idle', detail.message || '');
  });
  try {
    const saved = JSON.parse(localStorage.getItem('binaryrepair.pet.position') || 'null');
    if (saved?.left && saved?.top) {
      dock.style.left = saved.left;
      dock.style.top = saved.top;
      dock.style.right = 'auto';
      dock.style.bottom = 'auto';
    }
  } catch { /* ignore */ }
}

function detectFromDom() {
  if (state.dock?.dataset.page === 'workbench') {
    const rows = [...document.querySelectorAll('.task-row .badge')].map(node =>
      (node.textContent || '').toLowerCase());
    if (rows.some(text => /运行|执行中|running|queued/.test(text))) return 'running';
    return 'idle';
  }
  const current = document.querySelector('.repair-progress li[aria-current="step"]');
  if (current) return 'running';
  const badge = [...document.querySelectorAll('.badge, .assistant-mode-pill, [data-status]')]
    .map(node => (node.textContent || '').toLowerCase()).join(' ');
  if (/error|failed|rejected|失败|拒绝/.test(badge)) return 'error';
  if (/completed|verified|已结束|通过/.test(badge)) return 'happy';
  const phase = document.querySelector('.run-metric strong')?.textContent || '';
  if (/running|运行|执行中/.test(phase)) return 'running';
  if (/queued|等待|waiting/.test(phase)) return 'waiting';
  return 'idle';
}

export function mountPet() {
  if (typeof document === 'undefined') return () => {};
  ensureDock();
  setState('idle');
  let scheduled = false;
  const observer = new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      const detected = detectFromDom();
      if (detected !== state.current && !state.dragging &&
          !(state.current === 'sleeping' && detected === 'idle')) setState(detected);
    });
  });
  observer.observe(document.body, {childList: true, subtree: true, characterData: true});
  setInterval(() => {
    const detected = detectFromDom();
    if (detected !== state.current && !state.dragging) setState(detected);
  }, 5000);
  window.BinaryRepairPet = {setState, speak, hearts, mount: mountPet};
  return () => observer.disconnect();
}
