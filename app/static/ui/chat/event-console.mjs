/**
 * S3 event-journal console.
 *
 * Reads only the SSE journal served by /api/tasks/{id}/events and renders the
 * persisted payloads. Preview tasks are explicitly synthetic and demo-only.
 * It never derives a verdict or converts not_run into success.
 */
import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261125t';

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
  if (event.type === 'run_state') {
    return el('div', {class: 'ev-grid'}, row('status', payload.status),
      row('message_id', payload.message_id ?? '—'));
  }
  if (event.type === 'awaiting_user') {
    return el('div', {}, el('div', {class: 'ev-grid'},
      row('kind', payload.kind), row('request_id', payload.request_id),
      row('binding', payload.binding)),
    el('div', {class: 'ev-decisions'}, (payload.allowed || []).map(value =>
      el('button', {type: 'button', class: 'ev-decision', disabled: true,
        title: '合成预览不提交真实决策'}, label(value)))),
    el('p', {class: 'ev-muted'}, '合成预览只展示 decision 卡；真实 proceed/iterate/change_scope 需要 S4 API。'));
  }
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
    const manifest = payload.manifest;
    return el('div', {}, el('div', {class: 'ev-grid'}, row('stage', payload.stage)),
      manifest ? el('div', {class: 'ev-grid'},
        row('dry_run', manifest.dry_run), row('candidate_written', manifest.candidate_written),
        row('patch_site', manifest.patch_site), row('cave', manifest.cave)) : null,
      manifest?.edits ? el('pre', {class: 'ev-pre'},
        manifest.edits.map(edit => JSON.stringify(edit)).join('\n')) : null,
      (payload.files || []).map(file => el('div', {class: 'ev-file'},
        row('path', file.display_path), el('pre', {class: 'ev-pre'}, file.diff?.text || ''))));
  }
  if (event.type === 'verification' && payload.kind === 'check') {
    return el('div', {class: 'ev-grid'}, row('level', payload.level), row('obligation', payload.obligation_id),
      el('div', {class: 'ev-row'}, el('span', {}, 'status'), badge(payload.status, payload.status === 'not_run' ? 'warn' : 'neutral')),
      payload.reason_code ? row('reason_code', payload.reason_code) : null);
  }
  if (event.type === 'verification' && payload.kind === 'evaluation') {
    const verdict = payload.verdict;
    return el('div', {},
      el('div', {class: 'ev-grid'}, row('evaluation_id', payload.evaluation_id),
        el('div', {class: 'ev-row'}, el('span', {}, 'verdict'),
          badge(verdict ? verdict.outcome : '未最终确定', verdict ? 'neutral' : 'warn'))),
      verdict?.criteria ? el('div', {class: 'ev-checks'}, verdict.criteria.map(item =>
        el('div', {class: 'ev-row'}, el('span', {}, item.id || item.obligation_id || 'criterion'),
          badge(item.status || 'not_run', item.status === 'not_run' ? 'warn' : 'neutral')))) : null,
      verdict?.coverage ? row('coverage', verdict.coverage) : null,
      verdict?.limitations ? row('limitations', verdict.limitations) : null,
      el('p', {class: 'ev-muted'},
        '六个允许词：verified_against_stated_criteria / rejected / unverified / unsupported / error / not_run；' +
        'verdict 为 null 时绝不显示成功。'));
  }
  if (event.type === 'audit_runs') {
    return el('div', {}, row('report_sha256', payload.report_sha256),
      payload.runs?.length ? el('div', {class: 'ev-runs'}, payload.runs.map(run =>
        el('div', {class: 'ev-grid'}, row('run', run.run_index),
          row('schema_valid', run.schema_valid), row('score', run.score ?? 'null'),
          row('critical_errors', run.critical_errors ?? []), row('usable', run.usable),
          row('notes', run.notes ?? '')))) : el('p', {class: 'ev-muted'}, '尚无真实审计运行（preview 不伪造）。'));
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

async function loadAnalysis(taskId, analysis, artifacts) {
  try {
    const response = await fetch('/api/tasks/' + encodeURIComponent(taskId) + '/analysis',
      {credentials: 'same-origin', cache: 'no-store'});
    if (!response.ok) return;
    const payload = await response.json();
    if (payload.available && payload.view && payload.finding) {
      const view = payload.view;
      const finding = payload.finding;
      analysis.hidden = false;
      analysis.replaceChildren(
        el('h3', {}, '分析产物 · DisassemblyViewV1 / FindingV1'),
        el('div', {class: 'ev-grid'},
          row('entry', view.elf?.entry ?? '—'),
          row('function', finding.function ?? '—'),
          row('site', finding.address ?? '—'),
          row('instruction', finding.instruction ?? '—'),
          row('finding.status', finding.status ?? '—'),
          row('evidence', (finding.evidence || []).length)),
        el('details', {class: 'ev-raw'}, el('summary', {}, '查看 FindingV1'),
          el('pre', {}, JSON.stringify(finding, null, 2))));
    }
  } catch { /* Analysis is optional until the runner writes it. */ }
  try {
    const response = await fetch('/api/tasks/' + encodeURIComponent(taskId) + '/artifacts',
      {credentials: 'same-origin', cache: 'no-store'});
    if (!response.ok) return;
    const payload = await response.json();
    if (!payload.artifacts?.length) return;
    artifacts.hidden = false;
    artifacts.replaceChildren(
      el('h3', {}, '工件与下载'),
      el('div', {class: 'ev-artifacts'}, payload.artifacts.map(item =>
        el('a', {class: 'ev-artifact', href: item.download_url, download: item.display_path},
          icon('download', 14), item.display_path,
          el('code', {}, item.sha256.slice(0, 12) + '…'))))); 
  } catch { /* No artifacts yet. */ }
}

export async function openEventConsole({taskId = null} = {}) {
  const dialog = el('dialog', {class: 'ev-dialog', 'aria-label': 'S3 事件流'},
    el('header', {class: 'ev-head'},
      el('div', {}, el('h2', {}, 'S3 · 事件流'),
        el('p', {}, '只渲染事件日志；不推断成功或结论。')),
      el('button', {type: 'button', class: 'button icon-only subtle', 'aria-label': '关闭'}, icon('x', 17))));
  const close = dialog.querySelector('header button');
  const body = el('div', {class: 'ev-body'});
  const status = el('p', {class: 'ev-status'}, '正在创建合成预览任务…');
  const analysis = el('section', {class: 'ev-analysis', hidden: true});
  const artifacts = el('section', {class: 'ev-analysis', hidden: true});
  body.append(status, analysis, artifacts);
  dialog.append(body);
  document.body.append(dialog);
  close.addEventListener('click', () => dialog.close());
  let source = null;
  dialog.addEventListener('close', () => { source?.close(); dialog.remove(); });
  dialog.showModal();
  try {
    let id = taskId;
    if (!id) {
      const task = await createPreviewTask();
      id = task.id;
      status.textContent = '合成预览任务 ' + id + ' · 等待事件…';
    } else {
      status.textContent = '任务 ' + id + ' · 等待真实事件…';
    }
    loadAnalysis(id, analysis, artifacts);
    source = new EventSource('/api/tasks/' + encodeURIComponent(id) + '/events');
    source.addEventListener('run_state', event => { body.append(eventRow(JSON.parse(event.data)));});
    const handle = event => {
      const record = JSON.parse(event.data);
      body.append(eventRow(record));
      status.textContent = '收到 #' + record.seq + ' · ' + record.type;
      if (record.type === 'run_end') {
        source.close();
        status.textContent = '事件流结束 · ' + (record.payload?.execution || 'unknown');
        // The runner may have written artifacts after the first fetch; refresh
        // once at the terminal event without inventing any missing artifact.
        loadAnalysis(id, analysis, artifacts);
      }
    };
    for (const type of ['corpus_update', 'plan_update', 'command', 'file_change', 'verification',
      'audit_runs', 'error', 'run_end', 'user_message', 'message_dispatched', 'assistant_delta',
      'assistant_end', 'thinking', 'tool_call', 'tool_result', 'awaiting_user', 'user_response']) {
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
