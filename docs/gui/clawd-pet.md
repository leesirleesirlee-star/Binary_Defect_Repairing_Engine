# Clawd 小螃蟹：插件宠物移植说明

本目录的对话页、欢迎页与档案库共用一只像素小螃蟹作为交互宠物。它不是重新画的仿制品，
而是把本机 DSH 插件 `dsh-claude-style` v0.19.6 的吉祥物 **Clawd（crab）** 原样搬到本 GUI：

- 精灵图 38 张（19 组动画，每组 body + ink 蒙版）逐字节取自插件构建产物；
- 帧表（每个动画的帧数、裁剪框、reduced-motion 定格帧、80ms 帧间隔）、播放器、优先级状态机、
  空闲小动作、睡觉/唤醒、poke/tickle/drag 交互逻辑均按插件源码一比一移植；
- 本 GUI 没有 DSH 的 session 事件，因此只替换「触发条件」：动画集合、时序、优先级与观感不变。

来源与许可：帧图来自 dsh-claude-style（MIT），由 calmly-eating-bugs 绘制；螃蟹形象是 Anthropic 的
Clawd（见插件 THIRD_PARTY_NOTICES）。迁移时仅改写了宿主定位与信号接入，动画数据未改动。

## 文件

| 文件 | 作用 |
| --- | --- |
| `app/static/ui/shared/pet.mjs` | 宠物模块：帧表、播放器、状态机、交互、锚点、`window.BinaryRepairPet` API |
| `app/static/ui/shared/pet.css` | 螃蟹绘制机制（条带 + ink 蒙版）、chat 跑道/分隔线、欢迎页卡片锚点、档案库固定位 |
| `app/static/ui/assets/mascot/crab/*.png` | 19 组动画的 body/ink 精灵图（插件原件） |
| `app/static/ui/chat/chat-task.mjs` | 对话引擎事件 → 宠物信号（run_state / assistant_delta / thinking / error / awaiting_user / g4_*） |
| `app/static/ui/chat/route-activity.mjs` | 修复运行 journal → 宠物信号（run_state 阶段、plan_update、tool_call、verification、run_end） |
| `app/static/ui/workbench/workbench.mjs` | 档案库任务列表 → `globalThis.__binaryRepairArchiveJobs`（档案页 working 层级） |

## 位置（与参考图一致）

- 对话页：`.composer-wrap` 内、输入卡片正上方新增 `.pet-runway`（高 84px，顶部 1px 分隔线）。
  螃蟹站在输入卡片上沿、靠右端，左侧显示当前活动文字；跑道是真实布局空间，生成文本永远不会被宠物遮挡。
- 欢迎页：螃蟹站在首屏输入卡片（`form.composer-card`）上沿右端。
- 档案库：固定在视口右下角，脚踩视口底边。
- 窄屏（≤720px）：跑道 78px；`.chat-main:has(> .composer-wrap > .pet-runway)` 固定栅格列宽，避免旧布局的横向溢出把螃蟹挤出屏幕。
- 螃蟹不随指针移动；拖动只播放 `drag` 动画，松手回到锚点（与插件一致）。

## 触发条件映射（本 GUI → 插件动画）

插件优先级：交互 10 > error 时刻 8 > notification 7 > compacting 6 > attention(happy) 5 >
conducting 4 > working 3（typing/music/building 按并发数） > thinking 2 > idle 1；
循环动画至少停留 1000ms，更高优先级可立即打断；一次性动画播完即让位。

| 本 GUI 信号 | 宠物表现 |
| --- | --- |
| `awaiting_user` / 契约等待审批 | `notification`（举手等你） |
| 失败：`run_state failed/cancelled`、journal `error`、`verification error/unsupported`、档案任务失败 | `error` 时刻（X 眼 + 感叹号，4.8s） |
| 成功：`run_state completed`、`run_end` 成功、`verification` 通过、档案任务完成 | `happy` 时刻（庆祝，5.2s） |
| 证据收集：journal `plan_update` 的 `collect`/`freeze` 在跑（或 run_state `screening`） | `compacting`（扫证据） |
| 两条修复路线同时 in_progress（`.route-lane[data-status="in_progress"]` ≥ 2，或 journal 并发步骤 ≥ 2） | `conducting`（指挥两条路线） |
| `activity: working`（流式回答/工具运行）`busy` 1 / 2 / ≥3 | `typing` / `music` / `building` |
| `activity: thinking`（模型思考、排队等待执行、验证阶段） | `thinking`（气泡里想事情） |
| 空闲 20–40s 随机 | `idle-look` / `idle-wave` / `idle-laptop` |
| 空闲 60s | `sleeping`（Zzz） |
| 睡着后指针/键盘活动 | `waking` → 回到当前层级 |
| 点击左半/右半、450ms 内连点 4 次、按住拖动 >4px | `poke-left` / `poke-right` / `tickle` / `drag` |

## API

```js
window.BinaryRepairPet = {
  mount(),                       // 幂等
  signal({activity, busy, awaiting, sweeping, routes, runs, moment}),
  setState('idle'|'waiting'|'thinking'|'running'|'happy'|'error'|'sleeping'), // 兼容旧调用
  speak(text),                   // 兼容旧调用（跑道文字短暂提示）
  __debug: {snapshot, setSignal, setState, moment, react, freeze, sleepNow, wake, forceExtra},
};
```

旧版 `binaryrepair:pet-state` 事件仍然有效。`__debug` 仅供测试/联调（`freeze(true)` 可阻止
GUI 信号覆盖注入状态）。

## 验证

- 38 张精灵图与插件 v0.19.6 构建产物的字节一致；
- 19 组动画在 devicePixelRatio=2 下逐像素比对：18/19 与插件帧表 0 差异（`waking` 需等 1s
  minimum-show 结算后出现）；
- 点击/连点/拖动、睡觉/唤醒、优先级与时刻队列、reduced-motion 定格、深浅色、窄屏布局均通过
  Playwright 实测；
- `pytest` 全量 100% 通过，页面无新增 JS 错误（仅既有的 `/api/assistant/key` 401，表示未配置模型 Key）。
