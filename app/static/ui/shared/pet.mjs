/**
 * The composer crab — the interactive pixel companion of the BinaryRepair GUI.
 *
 * This is a faithful port of the mascot "Clawd" from the DSH plugin
 * `dsh-claude-style` v0.19.6 (the orange pixel crab the user asked for), not a
 * look-alike: the sprite sheets in ../assets/mascot/crab/ were copied
 * byte-for-byte out of the installed plugin build, and the frame table, player,
 * priority state machine, idle extras, sleep/wake and pointer reactions below
 * mirror the plugin's mascot chunk one-to-one (only the DSH session signals are
 * replaced by this GUI's signals — see `signal()`).
 *
 * The crab stands on the composer's top edge. On the conversation page it
 * stands inside `pet-runway`, a strip between the transcript and the composer
 * whose top border is the separator line; on the welcome page it stands on the
 * hero input card; on the archive page it sits in a fixed bottom-right layer.
 * It never moves with the pointer: dragging only plays the `drag` clip, exactly
 * like the plugin.
 *
 * Provemance: frames from dsh-claude-style (MIT), drawn by calmly-eating-bugs;
 * the crab is Anthropic's Clawd character. The plugin's third-party notices
 * apply to the sheet art.
 *
 * Public API (kept for the rest of the GUI):
 *   window.BinaryRepairPet = {mount, setState, signal, speak, hearts, __debug}
 *   - signal({activity, busy, awaiting, sweeping, routes, runs, moment})
 *   - setState('idle'|'waiting'|'thinking'|'running'|'happy'|'error'|'sleeping')
 *     (the legacy `binaryrepair:pet-state` event still works)
 */
import {motionReduced} from './motion.mjs?v=20261120au';

// ── The crab's clips (verbatim from dsh-claude-style v0.19.6) ───────────────
// Frames per clip, the crop box [x, y, w, h] in cells, and the still frame
// shown under reduced motion. Sheets hold 8 frames per row, each cropped to
// the box plus one transparent cell of gutter on every side.
const FRAME_MS = 80;
const GUTTER = 1;
const SHEETS = {
  idle: {frames: 24, box: [24, 20, 24, 16], still: 0},
  'idle-look': {frames: 31, box: [24, 20, 24, 16], still: 0},
  'idle-wave': {frames: 12, box: [24, 15, 24, 21], still: 0},
  'idle-laptop': {frames: 43, box: [14, 13, 34, 23], still: 0},
  thinking: {frames: 32, box: [14, 4, 34, 32], still: 18},
  typing: {frames: 6, box: [15, 22, 28, 14], still: 0},
  music: {frames: 16, box: [22, 1, 30, 35], still: 0},
  conducting: {frames: 24, box: [24, 12, 27, 24], still: 0},
  building: {frames: 6, box: [15, 19, 28, 17], still: 0},
  error: {frames: 24, box: [23, 11, 26, 25], still: 4},
  happy: {frames: 32, box: [18, 6, 34, 30], still: 3},
  notification: {frames: 16, box: [24, 8, 24, 28], still: 0},
  compacting: {frames: 20, box: [21, 20, 30, 16], still: 3},
  sleeping: {frames: 32, box: [23, 3, 29, 33], still: 0},
  waking: {frames: 12, box: [24, 4, 24, 32], still: 11},
  'poke-left': {frames: 10, box: [24, 20, 27, 16], still: 0},
  'poke-right': {frames: 10, box: [21, 20, 27, 16], still: 0},
  tickle: {frames: 16, box: [23, 18, 26, 18], still: 0},
  drag: {frames: 8, box: [23, 12, 26, 22], still: 0},
};
const EXTRAS = ['idle-look', 'idle-wave', 'idle-laptop'];
const ASSET_ROOT = new URL('../assets/mascot/crab/', import.meta.url);

// ── Stage clock rules (verbatim from the plugin) ────────────────────────────
const MIN_SHOW_MS = 1000;
const SLEEP_AFTER_MS = 60000;
const EXTRA_MIN_MS = 20000;
const EXTRA_SPAN_MS = 20000;
const TICKLE_GAP_MS = 450;
const TICKLE_CLICKS = 4;
const LIFT_PX = 4;
const REACTION_PRIORITY = 10;
const MOMENTS = {
  error: {state: 'error', animation: 'error', priority: 8, holdMs: 4800},
  attention: {state: 'attention', animation: 'happy', priority: 5, holdMs: 5200},
};

// ── Levels the GUI can show, by priority ───────────────────────────────────
const IDLE = {state: 'idle', animation: 'idle', priority: 1};
const THINKING = {state: 'thinking', animation: 'thinking', priority: 2};
const NOTIFICATION = {state: 'notification', animation: 'notification', priority: 7};
const SWEEPING = {state: 'sweeping', animation: 'compacting', priority: 6};

/** One working animation per crowd size, the way the plugin's tiers pick them. */
function working(busy) {
  return {
    state: 'working',
    animation: busy >= 3 ? 'building' : busy === 2 ? 'music' : 'typing',
    priority: 3,
  };
}

// ── What the crab reads about this GUI ─────────────────────────────────────
// `activity` follows the visible conversation: thinking while the model / a
// run has not produced output, working (with a busy count) while text or tools
// stream. `awaiting`/`sweeping`/`routes`/`runs` carry the GUI's other states;
// `moment` is a one-shot error/attention event. The chat modules feed this
// through window.BinaryRepairPet.signal(); the pet itself adds DOM hints (page
// kind, reduced motion, parallel route lanes on the chat page).
const signals = {
  activity: 'idle',
  busy: 0,
  awaiting: false,
  sweeping: false,
  routes: 0,
  runs: 0,
};
/** Parallel repair lanes visible in this page's execution pane (DOM hint). */
let domRoutes = 0;

/** Routes the GUI is juggling: the chat engine's patch and the visible lanes, whichever is larger. */
function effectiveRoutes() {
  return Math.max(signals.routes | 0, domRoutes | 0);
}

/** The level the GUI is in right now. */
function levelOf(state) {
  if (state.awaiting) return NOTIFICATION;
  if (state.sweeping) return SWEEPING;
  if ((state.routes | 0) >= 2) {
    // The two repair lanes running at once are this GUI's "juggling" moment.
    return {state: 'juggling', animation: 'conducting', priority: 4};
  }
  if (state.activity === 'working') {
    return working(Math.max(1, state.busy | 0, state.runs | 0));
  }
  if (state.activity === 'thinking') return THINKING;
  if ((state.runs | 0) > 0) return working(state.runs | 0);
  return IDLE;
}

// ── Stage: everything the crab is doing on the page it stands on ───────────
function freshStage(now) {
  return {
    sessionId: null,
    level: IDLE,
    moment: null,
    queued: null,
    reaction: null,
    extra: null,
    waking: false,
    asleep: false,
    quietSince: now,
    nextExtraAt: 0,
    current: null,
    animation: null,
    timer: null,
    clicks: [],
    press: null,
  };
}

function startMoment(stage, name, now) {
  const next = MOMENTS[name];
  stage.moment = {state: next.state, animation: next.animation, priority: next.priority, until: now + next.holdMs};
}

/** A moment happened: one that outranks the moment on screen takes over, a lesser one waits. */
function takeMoment(stage, name, now) {
  if (stage.moment !== null && now < stage.moment.until && stage.moment.priority > MOMENTS[name].priority) {
    stage.queued = name;
    return false;
  }
  startMoment(stage, name, now);
  return true;
}

/** What should be on screen now, given the GUI level. Mirrors decideStage. */
function decideStage(stage, now, level, around) {
  if (stage.moment !== null && now >= stage.moment.until) {
    stage.moment = null;
    if (stage.queued !== null) startMoment(stage, stage.queued, now);
    stage.queued = null;
  }
  if (stage.reaction !== null) {
    return {key: stage.reaction.key, mode: stage.reaction.mode, priority: REACTION_PRIORITY};
  }
  const held = stage.moment;
  const pick = held !== null && held.priority >= level.priority ? held : level;
  if (pick.state !== 'idle') {
    stage.asleep = false;
    stage.waking = false;
    stage.extra = null;
    stage.nextExtraAt = 0;
    // Work on screen is no quiet spell: the minute to sleep starts when it ends.
    stage.quietSince = now;
    return {key: pick.animation, mode: 'loop', priority: pick.priority};
  }
  if (!stage.asleep && now - stage.quietSince >= SLEEP_AFTER_MS) {
    stage.asleep = true;
    stage.extra = null;
  }
  if (stage.asleep) return {key: 'sleeping', mode: 'loop', priority: 1};
  if (stage.waking) return {key: 'waking', mode: 'once', priority: 1};
  if (stage.extra === null && around.extrasAllowed) {
    if (stage.nextExtraAt === 0) stage.nextExtraAt = now + EXTRA_MIN_MS + around.random() * EXTRA_SPAN_MS;
    else if (now >= stage.nextExtraAt) stage.extra = around.extras[Math.floor(around.random() * around.extras.length)];
  }
  if (stage.extra !== null) return {key: stage.extra, mode: 'once', priority: 1};
  return {key: 'idle', mode: 'loop', priority: 1};
}

/** A once clip reached its last frame: whoever asked for it lets go. */
function finishStage(stage, key, now, random) {
  if (stage.reaction !== null && stage.reaction.key === key && !stage.reaction.fresh) stage.reaction = null;
  if (stage.extra === key) {
    stage.extra = null;
    stage.nextExtraAt = now + EXTRA_MIN_MS + random() * EXTRA_SPAN_MS;
  }
  if (key === 'waking') stage.waking = false;
}

/** Whether the clip on screen may give way to `next` now. */
function switchSettles(stage, next, now) {
  const current = stage.current;
  return current === null || current.mode !== 'loop' || current.priority === REACTION_PRIORITY ||
    next.priority > current.priority || now - current.start >= MIN_SHOW_MS;
}

/** The next moment a time-based decision can flip, or Infinity. */
function nextDecisionAt(stage, now, waitSettle, playMs) {
  let at = Infinity;
  if (stage.moment !== null) at = Math.min(at, stage.moment.until);
  if (waitSettle && stage.current !== null) at = Math.min(at, stage.current.start + MIN_SHOW_MS);
  if (stage.current !== null && stage.current.mode === 'once' && stage.current.done !== true) {
    at = Math.min(at, stage.current.start + playMs(stage.current.key));
  }
  if (!stage.asleep && stage.level !== null && stage.level.state === 'idle') {
    at = Math.min(at, stage.quietSince + SLEEP_AFTER_MS);
  }
  if (stage.extra === null && stage.nextExtraAt > now) at = Math.min(at, stage.nextExtraAt);
  return at;
}

// ── The page side: sheets, nodes, anchors ──────────────────────────────────
const statusCopy = {
  zh: {
    thinking: '正在思考…',
    typing: '正在写回答…',
    music: '正在运行工具…',
    building: '正在并行处理…',
    conducting: '正在并行修复…',
    compacting: '正在核对证据…',
    notification: '等待你的决定',
    error: '出错了',
    happy: '完成了',
    sleeping: 'Zzz…',
    waking: '…',
  },
  en: {
    thinking: 'Thinking…',
    typing: 'Writing…',
    music: 'Running tools…',
    building: 'Working in parallel…',
    conducting: 'Directing both routes…',
    compacting: 'Checking the evidence…',
    notification: 'Waiting for you',
    error: 'Something went wrong',
    happy: 'Done',
    sleeping: 'Zzz…',
    waking: '…',
  },
};

function language() {
  const lang = (document.documentElement.lang || navigator.language || 'en').toLowerCase();
  return lang.startsWith('zh') ? 'zh' : 'en';
}

function pageKind() {
  const path = location.pathname;
  if (path.includes('/ui/chat')) return 'chat';
  if (path === '/welcome' || path.startsWith('/welcome/')) return 'welcome';
  if (path === '/ui/' || path === '/ui/index.html') return 'archive';
  return 'other';
}

function el(tag, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return node;
}

let root = null;
let sprite = null;
let strip = null;
let activityLabel = null;
let mounted = false;
let page = null;
let stage = freshStage(Date.now());
let labelOverride = null;
let syncTimer = 0;
let signalsFrozen = false;
const stopHooks = [];
const sheetStatus = new Map(); // key -> 'loading' | 'ready' | 'failed'
let sheetsAlive = true;

/** Paint a clip's two sheets on the root: the body art and the ink mask. */
function paint(style, key) {
  style.setProperty('--dsh-claude-crab-sheet', `url("${new URL(`${key}-body.png`, ASSET_ROOT).href}")`);
  style.setProperty('--dsh-claude-crab-ink', `url("${new URL(`${key}-ink.png`, ASSET_ROOT).href}")`);
}

/** Start the first load of one clip's sheets; the caller re-steps when they land. */
function loadSheet(key) {
  const known = sheetStatus.get(key);
  if (known !== undefined) return known === 'ready';
  sheetStatus.set(key, 'loading');
  const body = new Image();
  const ink = new Image();
  body.src = new URL(`${key}-body.png`, ASSET_ROOT).href;
  ink.src = new URL(`${key}-ink.png`, ASSET_ROOT).href;
  Promise.all([body.decode(), ink.decode()]).then(() => {
    if (!sheetsAlive) return;
    sheetStatus.set(key, 'ready');
    if (strip !== null) step();
  }, () => {
    if (!sheetsAlive) return;
    sheetStatus.set(key, 'failed');
  });
  return false;
}

function sheetReady(key) {
  return sheetStatus.get(key) === 'ready' || loadSheet(key);
}

function sheetFailed(key) {
  return sheetStatus.get(key) === 'failed';
}

function playMs(key) {
  return SHEETS[key].frames * FRAME_MS;
}

/** One frame cell of a sheet: the crop box plus the transparent gutter. */
function cellSize(sheet) {
  return [sheet.box[2] + GUTTER * 2, sheet.box[3] + GUTTER * 2];
}

/** The strip translation that puts one frame of a sheet in the window. */
function frameOffset(sheet, frame) {
  const [cellWidth, cellHeight] = cellSize(sheet);
  return `translate(${-((frame % 8) * cellWidth + GUTTER) * 2}px, ${-(Math.floor(frame / 8) * cellHeight + GUTTER) * 2}px)`;
}

/** Whether the reduced-motion choice pins stills instead of playing clips. */
function still() {
  return motionReduced() && stage.reaction === null;
}

/** Build the crab's nodes once per mount. */
function build() {
  const built = el('span', 'dsh-claude-crab');
  built.setAttribute('aria-hidden', 'true');
  sprite = el('span', 'dsh-claude-crab-sprite');
  strip = el('span', 'dsh-claude-crab-strip');
  sprite.appendChild(strip);
  built.appendChild(sprite);
  const hit = el('span', 'dsh-claude-crab-hit');
  hit.addEventListener('pointerdown', onPressStart);
  hit.addEventListener('pointermove', onPressMove);
  hit.addEventListener('pointerup', onPressEnd);
  hit.addEventListener('pointercancel', onPressCancel);
  hit.addEventListener('click', event => { event.stopPropagation(); });
  built.appendChild(hit);
  return built;
}

/** Find (and build) the element the crab stands on for the current page. */
function findStand() {
  if (page === 'chat') {
    const wrap = document.querySelector('.chat-main .composer-wrap');
    const form = wrap?.querySelector(':scope > form.composer');
    if (!wrap || !form) return null;
    let runway = wrap.querySelector(':scope > .pet-runway');
    if (!runway) {
      runway = el('div', 'pet-runway');
      runway.appendChild(el('span', 'pet-activity'));
      wrap.insertBefore(runway, form);
    }
    return {element: runway, place: 'runway'};
  }
  if (page === 'welcome') {
    const card = document.querySelector('main#main form.composer-card');
    if (!card) return null;
    return {element: card, place: 'card'};
  }
  if (page === 'archive') {
    let layer = document.querySelector('.pet-fixed-layer');
    if (!layer) {
      layer = el('div', 'pet-fixed-layer');
      document.body.appendChild(layer);
    }
    return {element: layer, place: 'fixed'};
  }
  return null;
}

/** Read the visible route lanes; returns whether the DOM-derived count changed. */
function readRouteLanes() {
  let next = 0;
  if (page === 'chat') {
    try {
      next = Math.min(2, document.querySelectorAll('.route-lane[data-status="in_progress"]').length);
    } catch { /* detached document during teardown */ }
  }
  if (next === domRoutes) return false;
  domRoutes = next;
  return true;
}

/** Recompute the level from the merged signals and let the stage react. */
function refreshLevel() {
  stage.level = levelOf({...signals, routes: effectiveRoutes()});
  step();
}

/**
 * Watch the execution pane's route lanes: two lanes running at once is the
 * conducting tier, and the lanes change by attribute/child mutation between
 * journal polls, so observe rather than wait for the 800ms anchor tick.
 */
let routeObserver = null;

function watchRouteLanes() {
  if (page !== 'chat' || routeObserver !== null) return;
  let queued = false;
  const read = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      if (readRouteLanes()) refreshLevel();
    });
  };
  routeObserver = new MutationObserver(read);
  routeObserver.observe(document.body, {
    attributes: true,
    attributeFilter: ['data-status'],
    childList: true,
    subtree: true,
  });
}

/** Read the page it stands on and re-anchor when the shell re-renders. */
function sync() {
  if (!mounted) return;
  const stand = findStand();
  if (stand === null) {
    release();
    return;
  }
  if (root === null) root = build();
  if (root.parentNode !== stand.element) stand.element.appendChild(root);
  activityLabel = stand.place === 'runway' ? stand.element.querySelector(':scope > .pet-activity') : null;
  if (!stand.element.hasAttribute('data-dsh-claude-crab-anchor')) {
    stand.element.setAttribute('data-dsh-claude-crab-anchor', stand.place);
  }
  if (readRouteLanes()) {
    refreshLevel();
    return;
  }
  if (stage.current === null && stage.timer === null) step();
}

/** Put a clip on the strip: a WAAPI animation whose keyframes hold each frame. */
function play(key, mode) {
  if (stage.animation !== null) {
    stage.animation.cancel();
    stage.animation = null;
  }
  const sheet = SHEETS[key];
  if (still()) {
    strip.style.transform = frameOffset(sheet, sheet.still);
    return;
  }
  strip.style.transform = '';
  const keyframes = [];
  for (let frame = 0; frame < sheet.frames; frame++) {
    keyframes.push({offset: frame / sheet.frames, transform: frameOffset(sheet, frame), easing: 'steps(1)'});
  }
  keyframes.push({offset: 1, transform: frameOffset(sheet, mode === 'loop' ? 0 : sheet.frames - 1)});
  const playing = strip.animate(keyframes, {
    duration: sheet.frames * FRAME_MS,
    iterations: mode === 'loop' ? Infinity : 1,
    fill: 'forwards',
  });
  stage.animation = playing;
  if (mode !== 'once') return;
  playing.finished.then(() => {
    if (stage.animation !== playing || stage.current === null || stage.current.key !== key || stage.current.done === true) return;
    stage.current.done = true;
    finishStage(stage, key, Date.now(), Math.random);
    step();
  }, () => {
    // A newer clip took the strip; finished rejects on cancel().
  });
}

/** Put one clip on screen: paint its sheets, write the crop vars, play it. */
function show(next, now) {
  const sheet = SHEETS[next.key];
  const [cellWidth, cellHeight] = cellSize(sheet);
  stage.current = {key: next.key, mode: next.mode, priority: next.priority, start: now};
  if (stage.reaction !== null && stage.reaction.key === next.key) stage.reaction.fresh = false;
  const style = root.style;
  paint(style, next.key);
  style.setProperty('--dsh-claude-crab-x', String(sheet.box[0]));
  style.setProperty('--dsh-claude-crab-y', String(sheet.box[1]));
  style.setProperty('--dsh-claude-crab-w', String(sheet.box[2]));
  style.setProperty('--dsh-claude-mascot-h', String(sheet.box[3]));
  style.setProperty('--dsh-claude-crab-cell-w', String(cellWidth));
  style.setProperty('--dsh-claude-crab-strip-h', String(cellHeight * Math.ceil(sheet.frames / 8)));
  root.setAttribute('data-animation', next.key);
  play(next.key, next.mode);
  if (!root.hasAttribute('data-ready')) root.setAttribute('data-ready', '');
  renderStatus();
}

/** Advance the crab: settle what is on screen, then arm the one timer. */
function step() {
  if (root === null || strip === null) return;
  const now = Date.now();
  if (stage.current !== null && stage.current.mode === 'once' && stage.current.done !== true &&
      now - stage.current.start >= playMs(stage.current.key)) {
    stage.current.done = true;
    finishStage(stage, stage.current.key, now, Math.random);
  }
  const next = decideStage(stage, now, stage.level ?? IDLE, {
    extras: EXTRAS,
    extrasAllowed: !motionReduced() && !document.hidden,
    random: Math.random,
  });
  const switching = stage.current === null || next.key !== stage.current.key ||
    (stage.reaction !== null && stage.reaction.fresh);
  const settled = switchSettles(stage, next, now);
  if (switching && settled) {
    if (sheetReady(next.key)) show(next, now);
    else if (next.mode === 'once' && sheetFailed(next.key)) {
      if (stage.reaction !== null) stage.reaction.fresh = false;
      finishStage(stage, next.key, now);
    }
  } else if (!switching && stage.current !== null) {
    if (still() && stage.animation !== null) {
      stage.animation.cancel();
      stage.animation = null;
      strip.style.transform = frameOffset(SHEETS[stage.current.key], SHEETS[stage.current.key].still);
    } else if (!still() && stage.animation === null) {
      play(stage.current.key, stage.current.mode);
      if (stage.animation !== null && stage.current.mode === 'loop') {
        stage.animation.currentTime = (now - stage.current.start) % playMs(stage.current.key);
      }
    }
  }
  renderStatus();
  schedule(now, switching && !settled);
}

/** The one timer, armed at the next moment a time-based decision can flip. */
function schedule(now, waitSettle) {
  if (stage.timer !== null) clearTimeout(stage.timer);
  stage.timer = null;
  const at = nextDecisionAt(stage, now, waitSettle, playMs);
  if (at === Infinity) return;
  stage.timer = setTimeout(() => {
    stage.timer = null;
    step();
  }, Math.max(at - now, 0));
}

/** The left-hand status line of the chat strip, drawn from the clip on screen. */
function renderStatus() {
  if (activityLabel === null) return;
  const key = stage.current === null ? null : stage.current.key;
  const copy = statusCopy[language()];
  const text = labelOverride !== null && Date.now() < labelOverride.until
    ? labelOverride.text
    : (key === null ? '' : (copy[key] || ''));
  if (activityLabel.textContent !== text) activityLabel.textContent = text;
}

/** The reader's hand: a reaction always starts from its first frame. */
function react(key, mode) {
  stage.reaction = {key, mode, fresh: true};
  step();
}

/** Wake a sleeping crab on the reader's activity; a still reader only resets the clock. */
function onActivity() {
  const now = Date.now();
  stage.quietSince = now;
  if (!stage.asleep) return;
  stage.asleep = false;
  stage.waking = !motionReduced();
  step();
}

function onPressStart(event) {
  if (event.button !== 0) return;
  stage.press = {id: event.pointerId, x: event.clientX, y: event.clientY, lifted: false};
  event.currentTarget.setPointerCapture(event.pointerId);
}

function onPressMove(event) {
  if (stage.press === null || stage.press.lifted || event.pointerId !== stage.press.id) return;
  if (Math.hypot(event.clientX - stage.press.x, event.clientY - stage.press.y) < LIFT_PX) return;
  stage.press.lifted = true;
  stage.clicks = [];
  react('drag', 'loop');
}

/** The tracked press is over: returns whether it had lifted, or null when it was not the tracked press. */
function endPress(event) {
  if (stage.press === null || event.pointerId !== stage.press.id) return null;
  const lifted = stage.press.lifted;
  stage.press = null;
  if (lifted) {
    stage.reaction = null;
    step();
  }
  return lifted;
}

/** A press let go without a lift pokes the side it landed on — or tickles, the fourth in a row. */
function onPressEnd(event) {
  if (endPress(event) !== false) return;
  const now = Date.now();
  if (stage.clicks.length > 0 && now - stage.clicks[stage.clicks.length - 1] > TICKLE_GAP_MS) stage.clicks = [];
  stage.clicks.push(now);
  if (stage.clicks.length >= TICKLE_CLICKS) {
    stage.clicks = [];
    react('tickle', 'once');
    return;
  }
  const box = event.currentTarget.getBoundingClientRect();
  react(event.clientX - box.left < box.width / 2 ? 'poke-left' : 'poke-right', 'once');
}

function onPressCancel(event) {
  endPress(event);
}

/** The page shows no stand: the crab leaves it and its reading stops. */
function release() {
  if (stage.timer !== null) clearTimeout(stage.timer);
  if (stage.animation !== null) stage.animation.cancel();
  if (root !== null && root.parentNode !== null) root.parentNode.removeChild(root);
  strip = null;
  sprite = null;
  stage = freshStage(Date.now());
  stage.level = levelOf({...signals, routes: effectiveRoutes()});
  labelOverride = null;
}

/** Feed one patch of GUI state; `moment` is a one-shot. External signals stop while frozen (QA only). */
function setSignals(patch) {
  if (signalsFrozen) return;
  applySignals(patch);
}

/** Merge one signal patch into the snapshot and let the stage react. */
function applySignals(patch) {
  if (patch === null || typeof patch !== 'object') return;
  let changed = false;
  for (const key of ['activity', 'busy', 'awaiting', 'sweeping', 'routes', 'runs']) {
    const value = patch[key];
    if (value === undefined) continue;
    if (key === 'activity') {
      if (!['idle', 'thinking', 'working'].includes(value)) continue;
    } else if (key === 'awaiting' || key === 'sweeping') {
      if (typeof value !== 'boolean') continue;
    } else if (!Number.isFinite(value)) continue;
    if (signals[key] !== value) {
      signals[key] = value;
      changed = true;
    }
  }
  if (patch.moment !== undefined && patch.moment !== null) {
    if (patch.moment === 'error' || patch.moment === 'attention') onMoment(patch.moment);
  }
  if (!changed) {
    if (labelOverride !== null && activityLabel !== null) renderStatus();
    return;
  }
  refreshLevel();
}

function onMoment(name) {
  if (!mounted) return;
  if (takeMoment(stage, name, Date.now())) step();
}

/** The legacy GUI-wide state names, mapped onto the crab's levels. */
function setState(name) {
  switch (name) {
    case 'idle':
      setSignals({activity: 'idle', busy: 0, awaiting: false, sweeping: false});
      break;
    case 'waiting':
      setSignals({awaiting: true});
      break;
    case 'thinking':
      setSignals({activity: 'thinking', busy: 0, awaiting: false});
      break;
    case 'running':
      setSignals({activity: 'working', busy: 1, awaiting: false, sweeping: false});
      break;
    case 'happy':
      setSignals({activity: 'idle', busy: 0, awaiting: false});
      onMoment('attention');
      break;
    case 'error':
      onMoment('error');
      break;
    case 'sleeping':
      stage.asleep = true;
      stage.waking = false;
      stage.extra = null;
      step();
      break;
    case 'waking':
      stage.asleep = false;
      stage.waking = true;
      step();
      break;
    default:
      break;
  }
}

/** Kept from the old companion: a short lived status note in the chat strip. */
function speak(text, duration = 4200) {
  if (typeof text !== 'string' || text === '') return;
  labelOverride = {text, until: Date.now() + duration};
  renderStatus();
  setTimeout(() => {
    if (labelOverride !== null && Date.now() >= labelOverride.until) {
      labelOverride = null;
      renderStatus();
    }
  }, duration + 60);
}

/** Whether one archive task is running right now (same rule as the archive table). */
function archiveRunning(job) {
  const execution = job?.execution ?? null;
  return job?.phase === 'running' || job?.phase === 'queued' ||
    job?.live_audit?.status === 'running' ||
    ['running', 'queued', 'waiting_for_executor'].includes(execution?.status);
}

/** Whether an archive task that stopped running ended badly. */
function archiveFailed(job) {
  const phase = String(job?.phase ?? '');
  const execution = String(job?.execution?.status ?? '');
  return ['failed', 'cancelled', 'error', 'aborted'].includes(phase) ||
    ['failed', 'cancelled', 'error', 'aborted'].includes(execution);
}

/** The archive page's own state (running repairs) without the chat wiring. */
let archiveSeen = null;
let archiveProbe = null;

/**
 * When the archive was opened without a session cookie, its own live calls are
 * rejected before they ask for one. The pet asks for the cookie once and reads
 * the task list itself, so its working tiers still animate on that page; the
 * table keeps its own error surface untouched.
 */
function probeArchiveJobs() {
  if (page !== 'archive' || archiveProbe !== null) return;
  archiveProbe = (async () => {
    try {
      await fetch('/api/session', {credentials: 'same-origin', cache: 'no-store'});
      const response = await fetch('/api/tasks?limit=50', {credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) return;
      const data = await response.json();
      if (!Array.isArray(data.tasks)) return;
      globalThis.__binaryRepairArchiveJobs = data.tasks;
      readArchiveHints();
    } catch { /* The archive table owns its error surface. */ }
  })();
}

function readArchiveHints() {
  if (page !== 'archive') return;
  const jobs = Array.isArray(globalThis.__binaryRepairArchiveJobs) ? globalThis.__binaryRepairArchiveJobs : null;
  if (jobs === null) {
    probeArchiveJobs();
    return;
  }
  let runs = 0;
  const seen = new Map();
  let finished = 0;
  let failed = 0;
  for (const job of jobs) {
    const running = archiveRunning(job);
    seen.set(job?.id, running);
    if (running) runs += 1;
    // A task that was running at the previous read and is not now is a moment;
    // the first read only seeds the table so opening the archive stays quiet.
    if (archiveSeen !== null && archiveSeen.get(job?.id) === true && !running) {
      if (archiveFailed(job)) failed += 1;
      else finished += 1;
    }
  }
  archiveSeen = seen;
  if (signals.runs !== runs) setSignals({runs, activity: 'idle'});
  if (failed > 0) onMoment('error');
  else if (finished > 0) onMoment('attention');
}

/** The legacy GUI-wide state event still drives the same levels. */
function legacyState(event) {
  if (signalsFrozen) return;
  const detail = event.detail || {};
  if (detail.state) setState(detail.state);
}

/** Mount the crab. Idempotent; returns a cleanup that stops its page reads. */
export function mountPet() {
  if (typeof document === 'undefined') return () => {};
  if (mounted) return stop;
  mounted = true;
  page = pageKind();
  stage = freshStage(Date.now());
  stage.level = levelOf({...signals, routes: effectiveRoutes()});
  sheetsAlive = true;
  for (const key of Object.keys(SHEETS)) loadSheet(key);
  if (root === null) root = build();
  sync();
  watchRouteLanes();
  probeArchiveJobs();

  const activityEvents = ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart'];
  const off = [];
  for (const name of activityEvents) {
    document.addEventListener(name, onActivity, name === 'keydown' ? true : {passive: true});
    off.push(() => document.removeEventListener(name, onActivity, name === 'keydown' ? true : {passive: true}));
  }
  const onVisible = () => {
    if (!document.hidden) step();
  };
  const onRepaint = () => step();
  document.addEventListener('visibilitychange', onVisible);
  window.addEventListener('resize', sync, {passive: true});
  window.addEventListener('binaryrepair:settings', onRepaint);
  window.addEventListener('binaryrepair:pet-state', legacyState);
  window.addEventListener('storage', onRepaint);
  off.push(() => document.removeEventListener('visibilitychange', onVisible));
  off.push(() => window.removeEventListener('resize', sync, {passive: true}));
  off.push(() => window.removeEventListener('binaryrepair:settings', onRepaint));
  off.push(() => window.removeEventListener('binaryrepair:pet-state', legacyState));
  off.push(() => window.removeEventListener('storage', onRepaint));
  stopHooks.push(...off);
  syncTimer = window.setInterval(() => {
    sync();
    readArchiveHints();
  }, 800);

  window.BinaryRepairPet = {
    mount: mountPet,
    setState,
    signal: setSignals,
    speak,
    hearts: () => {},
    __debug: {
      snapshot: () => ({
        page,
        level: stage.level,
        current: stage.current === null ? null : {key: stage.current.key, mode: stage.current.mode},
        asleep: stage.asleep,
        waking: stage.waking,
        extra: stage.extra,
        quietMs: Date.now() - stage.quietSince,
        signals: {...signals},
        routes: effectiveRoutes(),
        domRoutes,
        sheets: Object.fromEntries(sheetStatus),
      }),
      setSignal: applySignals,
      setState,
      moment: onMoment,
      react: key => {
        if (!SHEETS[key]) return;
        react(key, key.startsWith('poke') || key === 'tickle' ? 'once' : 'loop');
      },
      freeze: value => { signalsFrozen = Boolean(value); },
      sleepNow: () => {
        stage.quietSince = Date.now() - SLEEP_AFTER_MS - 1;
        step();
      },
      wake: onActivity,
      forceExtra: name => {
        if (!EXTRAS.includes(name)) return;
        stage.extra = name;
        step();
      },
    },
  };
  return stop;
}

function stop() {
  mounted = false;
  sheetsAlive = false;
  if (syncTimer !== 0) window.clearInterval(syncTimer);
  syncTimer = 0;
  if (routeObserver !== null) {
    routeObserver.disconnect();
    routeObserver = null;
  }
  domRoutes = 0;
  archiveSeen = null;
  archiveProbe = null;
  for (const off of stopHooks.splice(0)) off();
  release();
  root = null;
  sprite = null;
  strip = null;
  activityLabel = null;
  if (window.BinaryRepairPet !== undefined) delete window.BinaryRepairPet;
}
