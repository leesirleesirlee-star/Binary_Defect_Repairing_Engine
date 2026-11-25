// G1–G4 archive detail: one repair run with its verdict and downloadable evidence.
import {el} from '../shared/dom.mjs?v=20261125n';
import {icon} from '../shared/icons.mjs?v=20261125n';

const text = (locale, en, zh) => locale === 'zh-Hans' ? zh : en;

export function g4TaskView(ctx) {
  const {t, language, job, data = {}, api} = ctx;
  const g4 = job.g4 || {};
  const finding = g4.finding || {};
  const counts = g4.cases?.counts || {};
  const options = g4.options || [];
  const selected = options.find(option => option.id === g4.selected_option) || null;
  const evaluation = data.evaluation || null;
  const outcome = evaluation?.verdict?.outcome ?? null;
  const artifacts = data.artifacts || [];
  const taskId = job.id;
  const conversation = '/ui/chat/';
  const sha = value => value ? String(value) : '—';
  const row = (name, value) => el('div', {class: 'stat'},
    el('span', {class: 'muted'}, name), el('span', {class: 'mono'}, value));

  const header = el('div', {class: 'section-head'},
    el('div', {class: 'heading'},
      el('div', {class: 'inline'}, el('span', {class: 'stat mono'}, taskId),
        el('span', {class: 'badge'}, t(job.phase)),
        outcome ? el('span', {class: 'badge'}, outcome) : null),
      el('h1', {}, job.defect || taskId)),
    el('div', {class: 'inline'},
      api?.writable ? el('button', {class: 'button subtle danger', type: 'button',
        onclick: async () => {
          if (!window.confirm(t('deleteConfirm'))) return;
          try {
            await api.remove(job.id);
            try {
              const key = 'binaryrepair.chat.sessions.v1';
              const saved = JSON.parse(localStorage.getItem(key) || 'null');
              if (saved?.chats) {
                saved.chats = saved.chats.filter(chat => chat.jobId !== job.id);
                localStorage.setItem(key, JSON.stringify(saved));
              }
            } catch { /* browser history is best-effort */ }
            location.assign('/ui/');
          }
          catch (error) { window.alert(error?.code || error?.message || t('readError')); }
        }}, icon('x', 16), t('delete')) : null,
      el('a', {class: 'button subtle', href: conversation}, icon('chat', 16),
        text(language, 'New repair', '新建修复'))));

  const verdictSection = el('section', {class: 'card'}, el('h2', {}, t('verdict')),
    outcome ? el('div', {class: 'verdict'}, el('span', {class: 'verdict-label'}, outcome),
      el('span', {class: 'stat'}, text(language, 'Persisted VerdictV1', '持久化 VerdictV1'))) :
      el('p', {class: 'muted'}, text(language, 'No persisted verdict yet.', '尚无持久化结论。')),
    row(text(language, 'Run', '运行'), sha(job.execution?.run_id)),
    row(text(language, 'Contract SHA-256', '契约 SHA-256'), sha(evaluation?.contract_sha256)),
    row(text(language, 'Original SHA-256', '原始程序 SHA-256'), sha(evaluation?.original_sha256)),
    row(text(language, 'Candidate SHA-256', '候选程序 SHA-256'), sha(evaluation?.candidate_sha256)),
    el('div', {class: 'actions'},
      el('a', {class: 'button', href: '/api/tasks/' + encodeURIComponent(taskId) + '/journal', download: ''},
        icon('terminal', 16), text(language, 'Run journal', '运行日志')),
      el('a', {class: 'button', href: '/ui/chat/'}, icon('chat', 16),
        text(language, 'New repair', '新建修复'))));

  const contractSection = el('section', {class: 'card'}, el('h2', {}, t('contract')),
    row(text(language, 'Binary', '二进制'), g4.binary_name || '—'),
    row(text(language, 'Analysis status', '分析状态'), g4.analysis_status || '—'),
    row(text(language, 'Finding', '漏洞定位'),
      finding.function ? `${finding.function} @ ${finding.address} · ${finding.instruction || ''}` : '—'),
    row(text(language, 'CWE', 'CWE'), finding.cwe || '—'),
    row(text(language, 'Cases (valid / PoC)', '用例（正确 / 错误）'),
      `${counts.valid ?? 0} / ${counts.poc ?? 0}`),
    selected ? el('div', {class: 'inline'}, icon('check', 15),
      el('strong', {}, text(language, selected.title_en, selected.title_zh)),
      el('span', {class: 'stat'}, text(language, selected.scope_en, selected.scope_zh) || '')) :
      el('p', {class: 'muted'}, text(language, 'No contract selected.', '未选择修复契约。')));

  const artifactSection = el('section', {class: 'card'}, el('h2', {}, t('artifacts')),
    artifacts.length ? artifacts.map(artifact => el('div', {class: 'inline'},
      icon('file', 15),
      el('a', {class: 'button subtle',
        href: '/api/artifacts/' + encodeURIComponent(artifact.id) + '/download', download: ''},
        icon('download', 14), artifact.name),
      el('code', {class: 'mono'}, artifact.sha256 || ''))) :
      el('p', {class: 'muted'}, t('noArtifacts')));

  return el('div', {class: 'page'}, header,
    verdictSection, contractSection, artifactSection);
}
