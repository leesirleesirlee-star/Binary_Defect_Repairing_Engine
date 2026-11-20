/**
 * S6 archive bridge: read the S3 task list/export API without touching the
 * legacy workbench controller. Read-only; verdict is shown only when persisted.
 */
import {el} from '../shared/dom.mjs?v=20261120au';
import {icon} from '../shared/icons.mjs?v=20261120au';

const statusLabel = value => ({
  draft: '草稿', preview: '合成预览', queued: '排队', running: '运行中',
  failed: '失败', cancelled: '已取消', completed: '已完成', blocked: '阻塞',
}[value] || value || '未知');

function badge(text, tone = 'neutral') {
  return el('span', {class: 'archive-badge', 'data-tone': tone}, text);
}

async function fetchTasks() {
  const session = await fetch('/api/session', {credentials: 'same-origin', cache: 'no-store'});
  if (!session.ok) throw new Error('session unavailable');
  const response = await fetch('/api/tasks?limit=20', {credentials: 'same-origin', cache: 'no-store'});
  if (!response.ok) throw new Error('task list unavailable');
  return response.json();
}

function taskCard(task) {
  const verdict = task.verdict?.outcome ?? null;
  return el('article', {class: 'archive-task'},
    el('header', {},
      el('strong', {}, task.id),
      badge(statusLabel(task.phase), task.phase === 'failed' || task.phase === 'blocked' ? 'bad' : 'neutral'),
      task.demo ? badge('合成预览', 'warn') : null),
    el('div', {class: 'archive-facts'},
      el('span', {}, 'fixture：' + (task.fixture_id || '—')),
      el('span', {}, '创建：' + (task.created_at || '—')),
      el('span', {}, 'verdict：' + (verdict || '未最终确定'))),
    el('div', {class: 'archive-actions'},
      el('a', {class: 'button subtle', href: '/api/tasks/' + encodeURIComponent(task.id) + '/export'},
        icon('download', 14), '导出 JSON'),
      el('button', {type: 'button', class: 'button subtle', onclick: async () => {
        const module = await import('../chat/event-console.mjs?v=20261120au');
        await module.openEventConsole({taskId: task.id});
      }}, icon('terminal', 14), '查看事件流')));
}

function panel() {
  const root = el('section', {class: 'archive-bridge glass', 'aria-label': 'S3 任务与证据'},
    el('header', {},
      el('div', {}, el('h2', {}, '任务与证据'), el('p', {}, '只读任务列表；verdict 只从持久化结果读取。')),
      el('button', {type: 'button', class: 'button subtle', onclick: () => refresh()}, '刷新')),
    el('div', {class: 'archive-list'}, el('p', {class: 'archive-muted'}, '正在读取任务…')));
  const list = root.querySelector('.archive-list');
  async function refresh() {
    list.replaceChildren(el('p', {class: 'archive-muted'}, '正在读取任务…'));
    try {
      const data = await fetchTasks();
      const tasks = Array.isArray(data.tasks) ? data.tasks : [];
      list.replaceChildren(...(tasks.length
        ? tasks.map(taskCard)
        : [el('p', {class: 'archive-muted'}, '还没有任务。先在对话页审阅冻结样例并启动一次真实运行。')]));
    } catch (error) {
      list.replaceChildren(el('p', {class: 'archive-error'}, '任务列表不可用：' + error.message));
    }
  }
  root._refresh = refresh;
  refresh();
  return root;
}

let mounted = null;
function attach() {
  if (mounted?.isConnected) return;
  const app = document.getElementById('app');
  if (!app) return;
  if (document.querySelector('.archive-bridge')) return;
  const element = panel();
  app.parentNode.insertBefore(element, app);
  mounted = element;
}

const observer = new MutationObserver(() => attach());
observer.observe(document.body, {childList: true, subtree: true});
attach();
