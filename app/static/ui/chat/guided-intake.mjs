/**
 * S2 guided intake: frozen G1 fixture, corpus, contract and approval card.
 *
 * Read-only display of persisted fixture data. This module never computes a
 * verdict, score or success label; the approval binding is computed by the
 * server, and Start remains disabled until a later-stage runner exists.
 */
import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261125p';

const state = {snapshot: null, promise: null, approved: false, denied: false, dialog: null};
const wired = new WeakSet();

function short(value, head = 12, tail = 8) {
  const text = String(value ?? '');
  return text.length > head + tail + 1 ? text.slice(0, head) + '…' + text.slice(-tail) : text;
}

function badge(text, tone = 'neutral') {
  return el('span', {class: 'guided-badge', 'data-tone': tone}, text);
}

function field(label, value, className = '') {
  return el('div', {class: 'guided-field ' + className},
    el('span', {class: 'guided-label'}, label),
    typeof value === 'string' ? el('code', {}, value) : value);
}

function section(title, ...children) {
  return el('section', {class: 'guided-section'}, el('h3', {}, title), ...children);
}

async function load() {
  if (state.promise) return state.promise;
  state.promise = fetch('/api/fixture', {credentials: 'same-origin', cache: 'no-store'})
    .then(response => {
      if (!response.ok) throw new Error('fixture unavailable');
      return response.json();
    })
    .then(value => { state.snapshot = value; return value; })
    .catch(error => { state.error = error; throw error; });
  return state.promise;
}

async function session() {
  const response = await fetch('/api/session', {credentials: 'same-origin', cache: 'no-store'});
  if (!response.ok) throw new Error('session unavailable');
  return response.json();
}

async function ensureTask() {
  if (state.taskId) return state.taskId;
  if (!state.taskPromise) {
    state.taskPromise = (async () => {
      const current = await session();
      const response = await fetch('/api/tasks', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'x-csrf-token': current.csrf_token},
        body: JSON.stringify({}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail?.code || 'task creation failed');
      state.taskId = payload.id;
      return payload.id;
    })();
  }
  return state.taskPromise;
}

function caseText(item) {
  const argv = (item.argv || []).map(part => part === '' ? '""' : JSON.stringify(part)).join(' ');
  return item.kind === 'valid' ? `argv: ${argv}` : `${argv}`;
}

function contractBlock(data) {
  const contract = data.contract;
  const criteria = contract.stated_criteria || {};
  const hypothesis = contract.diagnostic_hypothesis || {};
  const allowed = contract.allowed_edits || {};
  const rows = el('div', {class: 'guided-facts'},
    field('capacity_bytes', String(criteria.capacity_bytes)),
    field('max_valid_input_bytes', String(criteria.max_valid_input_bytes)),
    field('valid_behavior', criteria.valid_behavior),
    field('forbidden_behavior', criteria.forbidden_behavior),
    field('invalid_response', criteria.invalid_response));
  const facts = el('details', {class: 'guided-details'},
    el('summary', {}, '查看完整 ContractV1'),
    el('pre', {class: 'guided-json'}, JSON.stringify(contract, null, 2)));
  return section('契约 ContractV1 · 冻结',
    el('div', {class: 'guided-badges'}, badge('只读', 'warn'), badge('criteria_source: ' + contract.criteria_source, 'neutral'),
      badge('revision ' + data.contract_revision, 'neutral')),
    el('p', {class: 'guided-help'}, 'G1 已冻结；修改契约会创建新任务，不允许原地编辑。'),
    rows,
    el('div', {class: 'guided-hypothesis'},
      el('strong', {}, '诊断假设 '),
      el('span', {}, hypothesis.statement || '—'),
      el('div', {class: 'guided-muted'}, '状态：' + (hypothesis.status || '—') + ' · 假设不是验收标准')),
    field('allowed_edits', JSON.stringify(allowed)),
    facts);
}

function dialogMarkup(data) {
  const corpus = data.corpus;
  const binary = data.binary;
  const elf = data.elf || {};
  const valid = corpus.cases.filter(item => item.kind === 'valid');
  const invalid = corpus.cases.filter(item => item.kind === 'invalid');
  const poc = corpus.poc || {};

  const fixture = section('二进制 Fixture · 只读',
    field('fixture_id', data.fixture_id),
    field('binary', binary.path),
    field('sha256', binary.sha256),
    field('size', String(binary.size)),
    field('ELF', `${elf.class || ''} / ${elf.machine || ''} / ${elf.type || ''}`),
    field('entry', elf.entry || '—'),
    field('reserved R-X', `${data.reserved_range?.start_vaddr || '—'}–${data.reserved_range?.end_vaddr || '—'} (${data.reserved_range?.size || 0} bytes)`),
    el('p', {class: 'guided-help'}, '冻结二进制已绑定；任意上传属于 L1，不在 MVP2 范围。'));

  const intake = section('输入 Intake',
    el('p', {class: 'guided-help'}, '缺陷描述（ASCII，冻结样例只读）'),
    el('pre', {class: 'guided-defect'}, data.defect || '(none)'),
    el('div', {class: 'guided-case-head'}, el('strong', {}, '正常输入'), badge(String(valid.length) + ' valid', 'on')),
    el('ul', {class: 'guided-list'}, valid.map(item => el('li', {}, el('code', {}, item.id), ' · ', caseText(item)))),
    el('div', {class: 'guided-case-head'}, el('strong', {}, '崩溃输入 / PoC'), badge('crash_or_undefined', 'warn')),
    el('pre', {class: 'guided-poc'}, short(poc.text || '', 180, 20)),
    el('div', {class: 'guided-muted'}, 'poc.txt · sha256 ' + short(poc.sha256 || '', 14, 10)),
    el('div', {class: 'guided-case-head'}, el('strong', {}, '无效输入'), badge(String(invalid.length) + ' invalid', 'bad')),
    el('ul', {class: 'guided-list'}, invalid.map(item => el('li', {}, el('code', {}, item.id), ' · ', caseText(item)))));

  const corpusSection = section('语料 CaseSetV1',
    el('div', {class: 'guided-badges'},
      badge('总 ' + corpus.total + ' 例', 'neutral'),
      badge('valid ' + corpus.counts.valid, 'on'),
      badge('invalid ' + corpus.counts.invalid, 'bad'),
      badge('poc ' + corpus.counts.poc, 'warn')),
    field('cases_sha256', corpus.cases_sha256));

  const approval = section('审批 Approval',
    field('review binding', data.review_binding_digest),
    el('div', {class: 'guided-badges'},
      field('contract_sha256', short(data.hashes.contract_sha256, 16, 10)),
      field('corpus_sha256', short(data.hashes.corpus_sha256, 16, 10)),
      field('binary_sha256', short(data.hashes.binary_sha256, 16, 10))),
    el('p', {class: 'guided-help'}, '批准会绑定契约、语料和二进制三个摘要；任一变化即为 stale approval。'),
    el('div', {class: 'guided-actions'},
      el('button', {type: 'button', class: 'button primary', id: 'guided-approve'}, icon('check', 16), '批准契约'),
      el('button', {type: 'button', class: 'button subtle', id: 'guided-deny'}, '拒绝'),
      el('button', {type: 'button', class: 'button subtle', id: 'guided-edit'}, '尝试编辑冻结契约')),
    el('p', {class: 'guided-status', id: 'guided-approval-status', role: 'status'}),
    el('button', {type: 'button', class: 'button primary', id: 'guided-start', disabled: true},
      icon('arrow', 16), '开始修复'));

  return el('div', {class: 'guided-body'},
    el('div', {class: 'guided-grid'}, fixture, intake),
    el('div', {class: 'guided-grid'}, corpusSection, contractBlock(data)),
    approval);
}

function openDialog(data) {
  state.dialog?.remove();
  const close = el('button', {type: 'button', class: 'button icon-only subtle', 'aria-label': '关闭'}, icon('x', 17));
  const dialog = el('dialog', {class: 'guided-dialog', 'aria-label': 'S2 · 冻结样例审阅'},
    el('header', {class: 'guided-head'},
      el('div', {}, el('h2', {}, '冻结样例 · ' + data.fixture_id),
        el('p', {}, 'G1 冻结的二进制、语料与契约；只读审阅后批准。')),
      close),
    dialogMarkup(data));
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { dialog.remove(); if (state.dialog === dialog) state.dialog = null; });
  document.body.append(dialog);
  state.dialog = dialog;
  dialog.showModal();

  const status = dialog.querySelector('#guided-approval-status');
  const approve = dialog.querySelector('#guided-approve');
  const deny = dialog.querySelector('#guided-deny');
  const edit = dialog.querySelector('#guided-edit');
  const start = dialog.querySelector('#guided-start');

  approve.addEventListener('click', async () => {
    approve.disabled = true;
    status.textContent = '正在创建任务并提交审批…';
    status.dataset.state = 'pending';
    try {
      const taskId = await ensureTask();
      const current = await session();
      const response = await fetch('/api/tasks/' + encodeURIComponent(taskId) + '/approve', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'x-csrf-token': current.csrf_token},
        body: JSON.stringify({expected_review_binding_digest: data.review_binding_digest,
          reviewer_label: 'M2 console user'}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        status.textContent = '审批失败：' + JSON.stringify(payload.detail || payload);
        status.dataset.state = 'bad';
        approve.disabled = false;
        return;
      }
      state.approved = true;
      status.textContent = '已批准 · ' + payload.approved_at + ' · task ' + taskId +
        ' · binding ' + short(payload.binding_digest, 16, 8);
      status.dataset.state = 'good';
      deny.disabled = true;
      start.disabled = false;
    } catch (error) {
      status.textContent = '审批失败：' + error.message;
      status.dataset.state = 'bad';
      approve.disabled = false;
    }
  });
  start.addEventListener('click', async () => {
    start.disabled = true;
    status.textContent = '正在启动真实 runner…';
    status.dataset.state = 'pending';
    try {
      const taskId = await ensureTask();
      const current = await session();
      const key = crypto.randomUUID();
      const response = await fetch('/api/tasks/' + encodeURIComponent(taskId) + '/start', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'x-csrf-token': current.csrf_token,
          'Idempotency-Key': key},
        body: JSON.stringify({expected_review_binding_digest: data.review_binding_digest}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        status.textContent = '启动失败：' + (payload.detail?.code || response.status);
        status.dataset.state = 'bad';
        start.disabled = false;
        return;
      }
      status.textContent = '已启动 · ' + payload.run_id + ' · 正在读取真实事件…';
      const module = await import('./event-console.mjs?v=20261125f');
      await module.openEventConsole({taskId});
    } catch (error) {
      status.textContent = '启动失败：' + error.message;
      status.dataset.state = 'bad';
      start.disabled = false;
    }
  });
  deny.addEventListener('click', () => {
    state.denied = true;
    status.textContent = '已拒绝（本地决定；不会启动运行）';
    status.dataset.state = 'bad';
    approve.disabled = true;
    start.disabled = true;
  });
  edit.addEventListener('click', async () => {
    status.textContent = '正在验证冻结契约拒绝语义…';
    try {
      const taskId = await ensureTask();
      const current = await session();
      const response = await fetch('/api/tasks/' + encodeURIComponent(taskId) + '/contract', {
        method: 'PUT', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'x-csrf-token': current.csrf_token},
        body: JSON.stringify({expected_revision: data.contract_revision, contract: {}}),
      });
      const payload = await response.json().catch(() => ({}));
      status.textContent = response.status === 409
        ? '已拒绝编辑：' + (payload.detail?.code || 'frozen_contract') + '（冻结契约只能新建 freeze）'
        : '意外状态：' + response.status;
      status.dataset.state = response.status === 409 ? 'good' : 'bad';
    } catch (error) {
      status.textContent = '验证失败：' + error.message;
      status.dataset.state = 'bad';
    }
  });
}

function launchCard(data) {
  const card = el('div', {class: 'guided-launch'},
    el('div', {}, el('strong', {}, 'S2 · 冻结样例已就绪'),
      el('p', {}, `${data.fixture_id} · ${data.corpus.total} cases · ${data.binary.sha256.slice(0, 12)}…`)),
    el('div', {class: 'guided-launch-actions'},
      el('button', {type: 'button', class: 'button primary', onclick: () => openDialog(data)},
        icon('file', 15), '审阅语料与契约'),
      el('button', {type: 'button', class: 'button subtle', onclick: async () => {
        const module = await import('./event-console.mjs?v=20261125f');
        await module.openEventConsole();
      }}, icon('terminal', 15), 'S3 事件流')));
  return card;
}

function attach() {
  const hero = document.querySelector('.empty-chat');
  if (!hero || hero.querySelector('.guided-launch')) return;
  load().then(data => {
    if (!hero.isConnected || hero.querySelector('.guided-launch')) return;
    hero.append(launchCard(data));
  }).catch(error => {
    const card = el('div', {class: 'guided-launch guided-error'},
      el('strong', {}, '冻结样例不可用'), el('p', {}, error.message));
    hero.append(card);
  });
}

const observer = new MutationObserver(() => attach());
observer.observe(document.getElementById('app') || document.body, {childList: true, subtree: true});
attach();
