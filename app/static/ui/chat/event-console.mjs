/**
 * S3 event-journal console.
 *
 * Reads only the SSE journal served by /api/tasks/{id}/events and renders the
 * persisted payloads. Preview tasks are explicitly synthetic and demo-only.
 * It never derives a verdict or converts not_run into success.
 */
import {el} from '../shared/dom.mjs?v=20261120as';
import {icon} from '../shared/icons.mjs?v=20261120as';

const LABELS = {
  collect: '收集', freeze: '冻结', analyze: '分析', audit: '审计', decision: '决策',
  repair: '修复', verify: '验收', export: '导出', review: '审阅', inspect: '检查', summarize: '汇总',
  started: '开始', output: '输出', finished: '结束', proposed: '提案', applied: '已应用',
  running: '运行中', failed: '失败', cancelled: '已取消', completed: '已完成',
  queued: '排队', idle: '空闲', preview: '合成预览', synthetic: '合成', runner: 'runner',
  verifier: 'verifier', gui: 'GUI', not_run: 'not_run', passed: 'passed', failed_check: 'failed',
};

const label = value => LABELS[value] || value || '—';
const text = value => typeof value === 'string' ? value : JSON.stringify(value);

function badge(value, tone = 'neutral') {
  return el('span', {class: 'ev-badge', 'data-tone': tone}, label(value));
}

function row(key, value) {
  return el('div', {class: 'ev-row'}, el('span', {}, key), el('code', {}, text(value)));
}

async function apiSession() {
  const response = await fetch('/api/session', {credentials: 'same-origin', cache: 'no-store'});
  if (!response.ok) throw new Error('session failed');
  return response.json();
}

async function createPreviewTask() {
  const session = await apiSession();
  const response = await fetch('/api/tasks', {
    method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'x-csrf-token': session.csrf_token},
    body: JSON.stringify({preview: true}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail?.code || 'task create failed');
  return payload;
}

function eventBody(event) {
  const payload = event.payload || {};
  if (event.type === 'plan_update') {
    return el('div', {class: 'ev-steps'}, (payload.steps || []).map(step =>
      el('div', {class: 'ev-step', 'data-status': step.status},
        el('span', {}, label(step.step_id)), badge(step.status))));
  }
  if (event.type === 'corpus_update') {
    return el('div', {class: 'ev-grid'}, row('fixture_id', payload.fixture_id),
      row('total', payload.total), row('counts', payload.counts), row('cases_sha256', payload.cases_sha256));
  }
  if (event.type === 'command') {
    return el('div', {class: 'ev-grid'}, row('phase', payload.phase), row('label', label(payload.label_code)),
      row('cwd', payload.display_cwd), payload.exit_code != null ? row('exit_code', payload.exit_code) : null,
      payload.append ? el('pre', {class: 'ev-pre'}, payload.append) : null);
  }
  if (event.type === 'file_change') {
    return el('div', {}, el('div', {class: 'ev-grid'}, row('stage', payload.stage)),
      (payload.files || []).map(file => el('div', {class: 'ev-file'},
        row('path', file.display_path), el('pre', {class: 'ev-pre'}, file.diff?.text || ''))));
  }
  if (event.type === 'verification' && payload.kind === 'check') {
    return el('div', {class: 'ev-grid'}, row('level', payload.level), row('obligation', payload.obligation_id),
      el('div', {class: 'ev-row'}, el('span', {}, 'status'), badge(payload.status, payload.status === 'not_run' ? 'warn' : 'neutral')),
      payload.reason_code ? row('reason_code', payload.reason_code) : null);
  }
  if (event.type === 'verification' && payload.kind === 'evaluation') {
    return el('div', {class: 'ev-grid'}, row('evaluation_id', payload.evaluation_id),
      el('div', {class: 'ev-row'}, el('span', {}, 'verdict'),
        badge(payload.verdict ? payload.verdict.outcome : '未最终确定', 'warn')));
  }
  if (event.type === 'audit_runs') {
    return el('div', {}, row('report_sha256', payload.report_sha256),
      payload.runs?.length ? el('div', {class: 'ev-runs'}, payload.runs.map(run =>
        el('div', {class: 'ev-grid'}, row('run', run.run_id), row('schema_valid', run.schema_valid),
          row('score', run.score), row('usable', run.usable)))) : el('p', {class: 'ev-muted'}, '尚无真实审计运行（preview 不伪造）。'));
  }
  if (event.type === 'error') {
    return el('div', {class: 'ev-grid'}, row('code', payload.code), row('correlation', payload.correlation_id),
      el('p', {class: 'ev-muted'}, '错误原样展示；不推断原因。'));
  }
  if (event.type === 'run_end') {
    return el('div', {class: 'ev-grid'}, row('execution', payload.execution),
      row('evaluation', payload.evaluation_id || '—'), row('ai', payload.ai));
  }
  return el('pre', {class: 'ev-pre'}, JSON.stringify(payload, null, 2));
}

function eventRow(event) {
  const source = event.source || 'unknown';
  return el('article', {class: 'ev-row-item', 'data-type': event.type, 'data-source': source},
    el('header', {}, el('span', {class: 'ev-seq'}, '#' + event.seq),
      el('strong', {}, event.type), badge(source, source === 'synthetic' ? 'warn' : 'neutral'),
      event.step_id ? el('span', {class: 'ev-muted'}, label(event.step_id)) : null),
    eventBody(event),
    el('details', {class: 'ev-raw'}, el('summary', {}, '完整记录'),
      el('pre', {}, JSON.stringify(event, null, 2))));
}

export async function openEventConsole() {
  const dialog = el('dialog', {class: 'ev-dialog', 'aria-label': 'S3 事件流'},
    el('header', {class: 'ev-head'},
      el('div', {}, el('h2', {}, 'S3 · 事件流'),
        el('p', {}, '只渲染事件日志；合成预览不产生成功结论。')),
      el('button', {type: 'button', class: 'button icon-only subtle', 'aria-label': '关闭'}, icon('x', 17))));
  const close = dialog.querySelector('header button');
  const body = el('div', {class: 'ev-body'});
  const status = el('p', {class: 'ev-status'}, '正在创建合成预览任务…');
  body.append(status);
  dialog.append(body);
  document.body.append(dialog);
  close.addEventListener('click', () => dialog.close());
  let source = null;
  dialog.addEventListener('close', () => { source?.close(); dialog.remove(); });
  dialog.showModal();
  try {
    const task = await createPreviewTask();
    status.textContent = '任务 ' + task.id + ' · 等待事件…';
    source = new EventSource('/api/tasks/' + encodeURIComponent(task.id) + '/events');
    source.addEventListener('run_state', event => { body.append(eventRow(JSON.parse(event.data)));});
    const handle = event => {
      const record = JSON.parse(event.data);
      body.append(eventRow(record));
      status.textContent = '收到 #' + record.seq + ' · ' + record.type;
      if (record.type === 'run_end') {
        source.close();
        status.textContent = '事件流结束 · ' + (record.payload?.execution || 'unknown');
      }
    };
    for (const type of ['corpus_update', 'plan_update', 'command', 'file_change', 'verification',
      'audit_runs', 'error', 'run_end', 'user_message', 'assistant_delta', 'assistant_end',
      'thinking', 'tool_call', 'tool_result', 'awaiting_user', 'user_response']) {
      source.addEventListener(type, handle);
    }
    source.addEventListener('journal_gap', event => {
      status.textContent = '日志缺口：' + (event.data || 'journal_gap');
      status.dataset.state = 'bad';
      source.close();
    });
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) return;
      status.textContent = '事件流连接中断';
      status.dataset.state = 'bad';
    };
  } catch (error) {
    status.textContent = '无法打开事件流：' + error.message;
    status.dataset.state = 'bad';
  }
}
