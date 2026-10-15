// Admiral's film. render(t) draws the frame at t seconds; nothing moves on its own, so render.py can step through
// it frame by frame. All data comes from assets.js (Admiral's real output on its demo fleet).
"use strict";

const LANG = new URLSearchParams(location.search).get("lang") === "zh" ? "zh" : "en";
document.documentElement.lang = LANG === "zh" ? "zh-CN" : "en";
document.documentElement.dataset.lang = LANG;
const A = window.ASSETS[LANG];
const B = A.board;
const N = name => A.names[name] || name;  // a demo session's name in the film's language
const zh = LANG === "zh";
const TX = {
  en: {
    toasts: ["<b>{0}</b> needs your permission", "<b>{0}</b> is waiting for you", "CI failed: <b>{0}</b>",
      "<b>{0}</b> asked you a question", "CI failed: <b>{0}</b>", "<b>{0}</b> needs you on a real phone"],
    lines: ["{n} Claude Code sessions.", "One of you.", "Who needs you <span style=\"color:var(--amber)\">right now?</span>"],
    tagline: "Command a fleet of Claude Code sessions.",
    legend: ["working", "waiting for you", "idle", "commanders"],
    chatter: ["The two failures are the tax rounding", "  case; fixing the rounding mode.", "Writing the comparison for the",
      "  20 sample queries…", "Running the affected tests first,", "  then asking for a review."],
    ask: "Where does Search stand?",
    reply: "Search is at 61%. Search-Synonyms has its PR open and CI is green. Search-Index is red on\n" +
      "  tests (2) and has changes requested; I sent it the failing test. Search-Ranking is asking\n" +
      "  whether to switch to the new scorer: that call is yours.",
    index: ["The facet counts double-count variants; the test is right.", "  Fixing the grouping in src/search/facets.ts."],
    hud: "← claude-hud, by Jarrod Watts (MIT). Admiral runs it first, then adds its own lines.",
    kinds: ["Blocked on your permission", "Says what it needs from you", "Its last turn asked you"],
    marks: ["Fleet progress", "Your PRs, as GitHub has them", "Who needs you", "CI failing", "Safe to close",
      "One line per commander, those that need you first", "The batch this session leads"],
    caps: [["The status line", "Every session shows the whole fleet, right under the status line you already use."],
      ["The sidebar", "One click opens the details: who needs you and why, every batch, every deliverable."],
      ["One click", "Click a name and that session comes to the front, out of fifty-four."],
      ["Progress", "Progress follows real delivery, one milestone at a time."],
      ["Pull requests", "Nobody registered that branch? The push says whose PR it is."],
      ["Wrap-up", "Know which sessions you can close, and why."],
      ["The playbook", "Six skills every session follows, so fifty-four of them stay out of each other's way."]],
    desc: ["registered, building", "reviewed by a different model", "your acceptance", "PR open, CI running", "merged on GitHub"],
    msNote: "A batch takes the mean of its deliverables. One planned but not started counts as zero.",
    pushNote: "No push to go by? The session that did the work in that worktree. Pushed by a commander? It counts for that batch.",
    closeNote: "Closing is always yours. Admiral tells you which ones are safe.",
    skills: ["Judge every finding by the goal. A quality floor, and evidence for every claim.",
      "Commanders plan, decide and accept. Executors build. A session can own several PRs; each PR has one owner.",
      "One worktree per task. Never touch another session's branch or process.",
      "Locks and queues for heavy tests, databases, ports and model quota.",
      "A brief, affected tests, review by a different model, one push to ready.",
      "After the merge: clean up, then the board says what can close."],
    held: "held by {0} · full gate", inOrder: "waiting, in order", queue: ["{0} · full gate", "{0} · screenshots, 5 min"],
    prio: "priority", qnote: "Short jobs go first; a full gate waiting an hour is raised.",
    limit: ["The limit is no longer you.", "It's your tokens.", "Admiral itself spends none: no model calls, everything runs on your machine."],
    facts: ["No model tokens", "Reads only your machine", "Works under claude-hud", "MIT licensed"],
    demoNote: "# a fleet of 54, before you run your own",
    dec: {
      cap: ["Decisions", "Most calls never reach you: the commander makes the low-risk ones and records them. Yours arrive together."],
      cmd: "decides within your authorisation", log: "decision log", you: "for you", rec: "recommend",
      q: ["Round tax per line or per order?", "Reuse the receipt template?", "Retry a failed payment webhook?",
        "Block or flag a high fraud score?", "Approve the provider's sandbox key?", "Turn the new checkout on for everyone?"],
      a: ["Per line, as the tax tests expect", "Reuse it: one template to keep", "Retry twice, then alert",
        "Flag for review, never block silently", "approve: the new form needs it to be tested", "after your acceptance, behind a flag"],
    },
  },
  zh: {
    toasts: ["<b>{0}</b> 需要你批准", "<b>{0}</b> 在等你", "CI 失败：<b>{0}</b>", "<b>{0}</b> 在问你问题",
      "CI 失败：<b>{0}</b>", "<b>{0}</b> 需要你用真机试一下"],
    lines: ["{n} 个 Claude Code 对话。", "只有你一个人。", "此刻，<span style=\"color:var(--amber)\">谁在等你？</span>"],
    tagline: "指挥一整支 Claude Code 舰队。",
    legend: ["工作", "等你处理", "空闲", "个总指挥"],
    chatter: ["两个失败都是税费四舍五入的情况，", "  正在改舍入方式。", "正在整理 20 个样例查询的对比……", "",
      "先跑受影响的测试，", "  再请另一个模型复查。"],
    ask: "搜索批次现在进展如何？",
    reply: "搜索批次进度 61%。搜索-同义词的 PR 已开，CI 通过；搜索-索引的 tests (2) 失败，审查要求\n" +
      "  修改，我已经把失败的测试发给它。搜索-排序在问要不要换成新的排序算法：这个需要你来定。",
    index: ["筛选计数把同一商品的不同规格重复算了，测试是对的。", "  正在修 src/search/facets.ts 里的分组。"],
    hud: "← claude-hud，作者 Jarrod Watts（MIT 开源）。Admiral 先运行它，再接上自己的几行。",
    kinds: ["被权限拦住，等你批准", "主动说明需要你做什么", "最后一句在问你"],
    marks: ["舰队总进度", "你的 PR，以 GitHub 为准", "谁在等你", "CI 失败", "可以关闭",
      "每个总指挥一行，等你的排在前面", "本对话负责的批次"],
    caps: [["状态栏", "每个对话都能看到整支舰队，就在你原来的状态栏下面。"],
      ["侧边栏", "点一下打开全部细节：谁在等你、为什么，每个批次、每个交付物。"],
      ["一键直达", "点一下名字，那个对话就跳到最前面，54 个里一步找到。"],
      ["进度", "进度跟着真实交付走，一个里程碑一个里程碑地算。"],
      ["PR 认领", "分支没登记？推送记录会说明这是谁的 PR。"],
      ["收尾", "哪些对话可以关、为什么，一目了然。"],
      ["协作规则", "6 套规则，让 54 个对话互不干扰。"]],
    desc: ["已登记，开发中", "换一个模型复查", "你来验收", "PR 已开，CI 运行中", "已在 GitHub 合并"],
    msNote: "一个批次取各交付物的平均；计划了但没开工的按 0 算。",
    pushNote: "没有推送记录？看谁在那个工作区里干的活。总指挥替成员推送的？算进他的批次。",
    closeNote: "关不关永远由你决定，Admiral 告诉你哪些是安全的。",
    skills: ["每个发现都按目标来判断；质量底线；每个说法都要有证据。", "总指挥拆任务、做决定、带验收；执行对话写代码。一个对话可以负责多个 PR，但每个 PR 只归一个对话。",
      "一个任务一个工作区；绝不碰别的对话的分支和进程。", "重测试、数据库、端口、模型额度，一律先拿锁、按顺序排队。",
      "先写任务书，只跑受影响的测试，换一个模型复查，一次推送直接 Ready。", "合并之后安全收尾，面板告诉你哪些可以关。"],
    held: "持有者：{0} · 完整门禁", inOrder: "排队顺序", queue: ["{0} · 完整门禁", "{0} · 截图，约 5 分钟"],
    prio: "优先级", qnote: "短任务优先；完整门禁排满一小时自动提级。",
    limit: ["瓶颈不再是你，", "而是你的 token。", "Admiral 自己一个 token 都不花：不调用模型，全在本机运行。"],
    facts: ["不花模型额度", "只读本机", "搭配 claude-hud", "MIT 开源"],
    demoNote: "# 先用 54 个对话的演示舰队看看效果",
    dec: {
      cap: ["决策", "大多数决定到不了你这：低风险的由总指挥做出并记录，必须你定的集中送到。"],
      cmd: "在你的授权范围内决策", log: "决策记录", you: "待你决定", rec: "建议",
      q: ["税费按行还是按单四舍五入？", "收据模板能不能复用？", "支付回调失败要不要重试？",
        "风控高分是拦截还是标记？", "要不要批准支付商的沙箱密钥？", "新结账页要不要对所有人开放？"],
      a: ["按行，与税费测试一致", "复用：只维护一份模板", "重试两次，再告警",
        "标记待查，不悄悄拦截", "批准：新表单要靠它测试", "你验收后，用开关逐步开放"],
    },
  },
}[LANG];
const f0 = (tpl, v) => tpl.replace("{0}", v);
const W = 1920, H = 1080;
const P = 1.2;           // the film opens on its poster for this long: chat apps show the first frame as the cover
const POSTER_AT = 12.8;  // the poster is this frame of the story: the title over the fleet
const IN = 41.6, D = 6.4;  // story time the decisions scene comes in, and its length: every later scene starts D later
const DURATION = 92 + P + D;

// ---------- helpers ----------
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const seg = (t, a, b) => clamp((t - a) / (b - a));
const lerp = (a, b, x) => a + (b - a) * x;
const inOut = x => (x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const out3 = x => 1 - Math.pow(1 - x, 3);
const outExpo = x => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x));
const fade = (t, a, b, c, d) => Math.min(out3(seg(t, a, b)), 1 - inOut(seg(t, c, d)));  // in over a..b, out over c..d

function el(tag, cls, parent, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  if (parent) parent.appendChild(e);
  return e;
}
function show(e, opacity, transform) {
  e.style.opacity = opacity;
  e.style.visibility = opacity <= 0.002 ? "hidden" : "visible";
  if (transform !== undefined) e.style.transform = transform;
}
function rng(seed) {  // mulberry32: the same "random" layout every render
  return () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const G0 = B.green.faint, G1 = B.green.full;
const shade = x => `rgb(${G0.map((v, i) => Math.round(v + (G1[i] - v) * x)).join(",")})`;

// every session, commanders first within their group, as the board orders them
const groups = B.groups;
const rows = [...groups.flatMap(g => (g.leadRow ? [g.leadRow] : []).concat(g.members)), ...B.unassigned];
const byName = Object.fromEntries(rows.map(r => [r.name, r]));
const counts = {
  total: rows.length,
  waiting: rows.filter(r => r.status === "waiting").length,
  working: rows.filter(r => r.status === "busy" || r.status === "shell").length,
};
counts.idle = counts.total - counts.waiting - counts.working;
const short = name => name.startsWith(B.commanderPrefix) ? name.slice(B.commanderPrefix.length).replace(/^[-_ ]+/, "") : name;

// ---------- the chart (background) ----------
const chart = document.getElementById("chart").getContext("2d");
const contours = (() => {  // depth lines: a few smooth closed curves, fixed
  const r = rng(7), out = [];
  for (let k = 0; k < 9; k++) {
    const cx = r() * W, cy = r() * H, base = 120 + r() * 380, ph = r() * 6.28, f = 2 + Math.floor(r() * 3);
    out.push({ cx, cy, base, ph, f, amp: 18 + r() * 40 });
  }
  return out;
})();
function drawChart(t, sweep) {
  const c = chart;
  c.clearRect(0, 0, W, H);
  const bg = c.createRadialGradient(W * .55, H * .45, 100, W * .5, H * .5, 1250);
  bg.addColorStop(0, "#0f2133"); bg.addColorStop(1, "#071019");
  c.fillStyle = bg; c.fillRect(0, 0, W, H);
  c.strokeStyle = "rgba(120,160,200,.055)"; c.lineWidth = 1;
  for (let x = 0; x <= W; x += 80) { c.beginPath(); c.moveTo(x + .5, 0); c.lineTo(x + .5, H); c.stroke(); }
  for (let y = 0; y <= H; y += 80) { c.beginPath(); c.moveTo(0, y + .5); c.lineTo(W, y + .5); c.stroke(); }
  c.strokeStyle = "rgba(140,180,215,.06)";
  for (const k of contours) {
    for (let ring = 0; ring < 3; ring++) {
      c.beginPath();
      for (let a = 0; a <= 6.30; a += .05) {
        const rad = k.base + ring * 34 + k.amp * Math.sin(a * k.f + k.ph + t * .03);
        const x = k.cx + Math.cos(a) * rad * 1.4, y = k.cy + Math.sin(a) * rad;
        a === 0 ? c.moveTo(x, y) : c.lineTo(x, y);
      }
      c.stroke();
    }
  }
  if (sweep) sweep(c);
}

// ---------- scene 1: too many windows ----------
const chaos = document.getElementById("chaos");
const CHAOS_N = 22;
const C = TX.chatter;
const chatter = [
  ["● Read(src/checkout/api.ts)", "  ⎿  Read 412 lines", "● Bash(npm test -- checkout)", "  ⎿  38 passed, 2 failed",
   "● Update(src/checkout/api.ts)", "  ⎿  +14 −6", "● " + C[0], C[1]],
  ["● Grep(\"rankScore\", src/search)", "  ⎿  Found 9 files", "● Read(src/search/score.ts)", "● Bash(npm run bench:search)",
   "  ⎿  p95 41 ms → 38 ms", "● " + C[2], C[3]],
  ["● Bash(git diff --stat main)", "  ⎿  7 files changed, +211 −48", "● " + C[4], C[5],
   "● Bash(pytest tests/mobile -q)", "  ⎿  ........................ 24 passed"],
  ["● Read(infra/rate_limits.tf)", "● Edit(infra/rate_limits.tf)", "  ⎿  +6 −2", "● Bash(terraform plan -target=…)",
   "  ⎿  Waiting for permission…", "", "  Allow this command?  1 Yes  2 No"],
];
const chaosWins = [];
{
  const r = rng(42);
  for (let i = 0; i < CHAOS_N; i++) {
    const row = rows[(i * 7 + 3) % rows.length];
    const w = el("div", "win", chaos);
    const x = 40 + r() * (W - 520), y = 30 + r() * (H - 330);
    w.style.left = x + "px"; w.style.top = y + "px"; w.style.width = "460px"; w.style.height = "290px";
    el("div", "bar", w, `<i></i><i></i><i></i><span>${esc(row.name)} — claude</span>`);
    const lines = chatter[i % chatter.length];
    const clip = el("div", "abs", w);  // the text scrolls under the title bar, never over it
    Object.assign(clip.style, { left: 0, right: 0, top: "34px", bottom: 0, overflow: "hidden" });
    const body = el("div", "body", clip, lines.map(esc).join("\n"));
    chaosWins.push({ w, body, x, y, row, born: .15 + i * .16 });
  }
}
const toasts = [
  [2.4, 1180, 120, "", f0(TX.toasts[0], N("Rate-Limits"))],
  [3.0, 250, 300, "", f0(TX.toasts[1], N("Checkout-UI"))],
  [3.5, 1100, 640, "red", f0(TX.toasts[2], N("Search-Index"))],
  [3.9, 380, 780, "", f0(TX.toasts[3], N("Coupons"))],
  [4.3, 1260, 880, "red", f0(TX.toasts[4], N("AB-Testing"))],
  [4.6, 640, 140, "", f0(TX.toasts[5], N("Mobile-Cart"))],
].map(([at, x, y, cls, html]) => {
  const e = el("div", "toast " + cls, chaos, html);
  e.style.left = x + "px"; e.style.top = y + "px";
  return { e, at };
});
const shade1 = el("div", "abs", chaos);
Object.assign(shade1.style, { inset: 0, background: "radial-gradient(ellipse at center, rgba(5,12,20,.86) 20%, rgba(5,12,20,.35) 70%)" });
const lines1 = [
  el("div", "abs headline", chaos, TX.lines[0].replace("{n}", counts.total)),
  el("div", "abs headline", chaos, TX.lines[1]),
  el("div", "abs headline", chaos, TX.lines[2]),
];
lines1.forEach((e, i) => {
  Object.assign(e.style, { left: "0", width: W + "px", textAlign: "center", fontSize: i < 2 ? "120px" : "150px" });
});

// ---------- scene 2: the fleet ----------
const fleet = document.getElementById("fleet");
const CX = 960, CY = 520;
const squads = groups.filter(g => g.leadRow);
const dotOf = {};
{
  squads.forEach((g, k) => {
    const ang = -Math.PI / 2 + (k / squads.length) * Math.PI * 2;
    const R = 330;
    const hx = CX + Math.cos(ang) * R * 1.35, hy = CY + Math.sin(ang) * R;
    const ux = Math.cos(ang), uy = Math.sin(ang), px = -uy, py = ux;  // outward, and across
    dotOf[g.leadRow.name] = { x: hx, y: hy, lead: true };
    g.members.forEach((m, j) => {  // a V behind the commander, opening outward
      const rank = Math.floor(j / 2) + 1, side = j % 2 ? 1 : -1;
      dotOf[m.name] = { x: hx + ux * rank * 34 + px * side * rank * 26, y: hy + uy * rank * 34 + py * side * rank * 26 };
    });
    g.label = { x: hx, y: hy + (uy < 0 ? 44 : -44) };  // the side away from its members
  });
  B.unassigned.forEach((m, j) => {
    const a = j / B.unassigned.length * Math.PI * 2 + .4;
    dotOf[m.name] = { x: CX + Math.cos(a) * 120 * 1.3, y: CY + Math.sin(a) * 90 };
  });
}
const STATUS_COLOR = { waiting: "var(--amber)", busy: "var(--green)", shell: "var(--green)", idle: "#56677b" };
const dots = rows.map(r => {
  const d = el("div", "abs", fleet);
  const p = dotOf[r.name];
  const size = p.lead ? 22 : 13;
  Object.assign(d.style, { left: p.x - size / 2 + "px", top: p.y - size / 2 + "px", width: size + "px", height: size + "px",
    borderRadius: r.status === "waiting" ? "3px" : "50%", background: STATUS_COLOR[r.status] || "#56677b",
    boxShadow: p.lead ? "0 0 0 3px var(--ink), 0 0 0 5px var(--brass)" : "none" });
  if (r.status === "waiting") d.style.transform = "rotate(45deg)";
  return { d, r, p, size };
});
const squadLabels = squads.map(g => {
  const e = el("div", "abs mono", fleet, short(g.lead).toUpperCase());
  Object.assign(e.style, { left: g.label.x - 100 + "px", top: g.label.y - 12 + "px", width: "200px", textAlign: "center",
    fontSize: "17px", letterSpacing: ".22em", color: "var(--brass)" });
  return e;
});
const title = el("div", "abs headline", fleet, "Admiral");
Object.assign(title.style, { left: 0, width: W + "px", top: "330px", textAlign: "center", fontSize: "300px", fontWeight: 900,
  letterSpacing: ".06em", color: "var(--fg)", textShadow: "0 10px 60px rgba(0,0,0,.6)" });
title.style.fontFamily = '"Big Shoulders Display", sans-serif';  // the name keeps its face in every language
const tagline = el("div", "abs caption", fleet, TX.tagline);
Object.assign(tagline.style, { left: 0, width: W + "px", top: "650px", textAlign: "center", fontSize: "54px" });
const legend = el("div", "abs mono", fleet,
  `<span style="color:var(--green)">●</span> ${counts.working} ${TX.legend[0]}   ` +
  `<span style="color:var(--amber)">◆</span> ${counts.waiting} ${TX.legend[1]}   ` +
  `<span style="color:#56677b">●</span> ${counts.idle} ${TX.legend[2]}   ` +
  `<span style="color:var(--brass)">◎</span> ${squads.length} ${TX.legend[3]}`);
Object.assign(legend.style, { left: 0, width: W + "px", top: "990px", textAlign: "center", fontSize: "24px", color: "var(--muted)" });

function sonar(t) {
  return c => {
    const a = seg(t, 7.2, 14.4);
    if (a <= 0 || a >= 1) return;
    const alpha = fade(t, 7.2, 8.2, 13.6, 14.4);
    c.save();
    c.translate(CX, CY); c.scale(1.35, 1);
    c.strokeStyle = `rgba(207,167,90,${.16 * alpha})`; c.lineWidth = 1;
    for (const R of [140, 280, 420]) { c.beginPath(); c.arc(0, 0, R, 0, Math.PI * 2); c.stroke(); }
    for (let k = 0; k < 72; k++) {
      const ang = k / 72 * Math.PI * 2, r0 = k % 6 ? 412 : 400;
      c.beginPath(); c.moveTo(Math.cos(ang) * r0, Math.sin(ang) * r0); c.lineTo(Math.cos(ang) * 420, Math.sin(ang) * 420); c.stroke();
    }
    const ang = (t - 7.2) * 1.25;
    const g = c.createConicGradient(ang - .9, 0, 0);
    g.addColorStop(0, "rgba(63,185,80,0)"); g.addColorStop(.14, `rgba(63,185,80,${.18 * alpha})`); g.addColorStop(.15, "rgba(63,185,80,0)");
    c.fillStyle = g; c.beginPath(); c.arc(0, 0, 430, 0, Math.PI * 2); c.fill();
    c.restore();
  };
}

function sceneChaos(t) {
  const on = t < 8;
  chaos.style.display = on ? "block" : "none";
  if (!on) return;
  const gather = inOut(seg(t, 6.2, 7.6));
  chaosWins.forEach(({ w, body, x, y, row, born }, i) => {
    const a = out3(seg(t, born, born + .35));
    const target = dotOf[row.name];
    const tx = lerp(x, target.x - 230, gather), ty = lerp(y, target.y - 145, gather);
    const s = lerp(.94 + .06 * a, .03, gather);
    w.style.left = tx + "px"; w.style.top = ty + "px";
    show(w, a * (1 - seg(t, 7.2, 7.6)), `scale(${s})`);
    body.style.transform = `translateY(${-((t * 22 + i * 9) % 60)}px)`;
  });
  toasts.forEach(({ e, at }) => show(e, fade(t, at, at + .25, 5.4, 5.9), `translateY(${(1 - out3(seg(t, at, at + .3))) * 16}px)`));
  show(shade1, clamp(seg(t, 1.0, 1.6) * .9 + seg(t, 4.8, 5.4) * .1) * (1 - seg(t, 6.0, 6.6)));
  const [l1, l2, l3] = lines1;
  show(l1, fade(t, 1.1, 1.5, 4.7, 5.1), `translateY(${(1 - out3(seg(t, 1.1, 1.6))) * 30}px)`); l1.style.top = "370px";
  show(l2, fade(t, 2.2, 2.6, 4.7, 5.1), `translateY(${(1 - out3(seg(t, 2.2, 2.7))) * 30}px)`); l2.style.top = "510px";
  l2.style.color = "var(--brass)";
  show(l3, fade(t, 5.0, 5.4, 6.1, 6.6), `scale(${lerp(.96, 1, out3(seg(t, 5.0, 5.8)))})`); l3.style.top = "440px";
}

function sceneFleet(t) {
  const on = t > 6.2 && t < 15;
  fleet.style.display = on ? "block" : "none";
  if (!on) return;
  const all = fade(t, 7.0, 7.8, 14.0, 14.8);
  dots.forEach(({ d, r, p }, i) => {
    const appear = out3(seg(t, 7.0 + (i % 9) * .03, 7.6 + (i % 9) * .03));
    let s = 1, o = appear * all;
    if (r.status === "busy" || r.status === "shell") s = 1 + .18 * Math.sin(t * 4 + i);
    if (r.status === "waiting") o *= .55 + .45 * (Math.sin(t * 6 + i) > 0 ? 1 : .2);
    show(d, o, `${r.status === "waiting" ? "rotate(45deg) " : ""}scale(${s})`);
  });
  const dim = seg(t, 9.6, 10.4) * (1 - seg(t, 13.4, 14.0));
  squadLabels.forEach((e, i) => show(e, fade(t, 8.2 + i * .08, 8.7 + i * .08, 14.0, 14.6) * .9 * (1 - .85 * dim)));
  fleet.style.filter = "";
  dots.forEach(({ d }) => { d.style.filter = `brightness(${1 - .7 * dim})`; });
  show(title, fade(t, 9.8, 10.6, 13.6, 14.3), `translateY(${(1 - outExpo(seg(t, 9.8, 10.9))) * 40}px)`);
  title.style.letterSpacing = lerp(.2, .06, outExpo(seg(t, 9.8, 11.2))) + "em";
  show(tagline, fade(t, 10.7, 11.3, 13.6, 14.3), `translateY(${(1 - out3(seg(t, 10.7, 11.4))) * 20}px)`);
  show(legend, fade(t, 11.6, 12.2, 13.8, 14.4));
}

// ---------- the sidebar, as Admiral's plugin draws it (plugin/hooks/register.tsx), from the same board ----------
const Wd = B.words;
const fmt = (key, vars = {}) => String(Wd[key] ?? key)
  .replace(/\{(\w+):([^|{}]*)\|([^{}]*)\}/g, (_, k, one, many) => (String(vars[k]) === "1" ? one : many))
  .replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
const NOW = B.generated;
const RUN = { waiting: ["◆", "c-warn"], busy: ["●", "c-ok"], shell: ["◉", "c-ok"], idle: ["○", "c-in"] };
const pad = (s, n) => String(s).padStart(n);
function agoS(t) {
  const s = Math.max(0, NOW - t);
  if (s < 60) return fmt("just_now");
  if (s < 3600) return fmt("min_ago", { n: Math.floor(s / 60) });
  if (s < 172800) return fmt("h_ago", { n: Math.floor(s / 3600) });
  return fmt("d_ago", { n: Math.floor(s / 86400) });
}
const lastActive = x => (x.status === "busy" || x.status === "shell" ? fmt("now") : x.statusSince ? agoS(x.statusSince) : "");
function barH(p, merged, n, fill = 1) {
  if (p === null || p === undefined) return `<span class="dim">${fmt("no_progress")}</span>`;
  const filled = Math.round(10 * p * fill / 100);
  let h = "";
  for (let i = 0; i < filled; i++) h += `<span style="color:${shade((i + 1) / 10)}">█</span>`;
  h += `<span class="dim">${"░".repeat(10 - filled)}</span> ${pad(Math.round(p * fill), 3)}%`;
  if (n > 0) h += `<span class="dim">  ${fmt("prs_merged", { done: merged, n })}</span>`;
  return h;
}
function pipsH(n, lit = 5) {
  let h = " ";
  for (let i = 0; i < 5; i++) h += i < Math.min(n, lit) ? `<span style="color:${shade((i + 1) / 5)}">▰</span>` : `<span class="dim">▱</span>`;
  return h;
}
const ciH = l => `<span class="c-err" style="display:inline-block;width:2ch;text-align:right">${l === "fail" ? "✗" : " "}</span>`;
const nameH = (x, dim) => `<span class="name${dim ? " dim" : ""}" data-name="${esc(x.name)}">${esc(x.name)}</span>`;
function rowH(x, indent = 0) {
  const [mark, cls] = RUN[x.status] || RUN.idle;
  const pr = x.pr && x.pr.state === "OPEN" ? `<div class="sub">${esc(x.pr.label)}</div>` : "";
  return `<div style="padding-left:${indent}ch"><div class="row"><span class="${cls}">${mark} </span>` +
    `<span class="grow">${nameH(x, x.status === "idle")}</span>${x.stage ? `<span class="pips" data-stage="${x.stage}">${pipsH(x.stage)}</span>` : ""}` +
    `${ciH(x.ciLevel)}<span class="dim" style="display:inline-block;width:12ch;text-align:right">${lastActive(x)}</span></div>${pr}</div>`;
}
function itemH(it, owner) {
  const [mark, cls] = owner ? RUN[owner.status] || RUN.idle : RUN.idle;
  const detail = [it.owner || fmt("no_owner"), it.pr ? it.pr.label : ""].filter(Boolean).join(" · ");
  return `<div style="padding-left:1ch"><div class="row"><span class="${cls}">${mark} </span>` +
    `<span class="grow${it.stage === 4 ? " dim" : ""}">${esc(it.title || it.branch)}</span><span class="pips" data-stage="${it.stage}">${pipsH(it.stage)}</span>` +
    `${ciH(it.ciLevel)}<span class="dim" style="display:inline-block;width:12ch;text-align:right">${owner ? lastActive(owner) : ""}</span></div>` +
    `<div class="sub">${esc(detail)}</div></div>`;
}
function teamH(g) {
  const s = g.summary;
  const [mark, cls] = g.leadRow ? RUN[g.leadRow.status] || RUN.idle : ["✗", "c-err"];
  const loose = g.batch ? g.members.filter(m => !g.batch.items.some(it => it.owner === m.name)) : g.members;
  let h = `<div class="team" data-team="${esc(g.lead)}"><div class="row"><span class="${cls}">${mark} </span><span class="grow">${nameH(g.leadRow || { name: g.lead })}</span>` +
    `<span class="dim">${g.leadRow ? lastActive(g.leadRow) : ""}</span></div>` +
    `<div style="padding-left:2ch" class="row"><span class="pbar" data-p="${s.pct}" data-m="${s.prsMerged || 0}" data-n="${s.prs || 0}">${barH(s.pct, s.prsMerged || 0, s.prs || 0)}</span>` +
    `${g.batch ? "" : `<span class="dim">  ${fmt("no_plan")}</span>`}</div>`;
  if (g.batch) {
    h += `<div class="sub">${fmt("deliverables")}</div>`;
    h += g.batch.items.map(it => itemH(it, g.members.find(m => m.name === it.owner))).join("");
    if (loose.length) h += `<div class="sub">${fmt("other_sessions")}</div>`;
  }
  h += loose.map(x => rowH(x, g.batch ? 1 : 0)).join("");
  return h + "</div>";
}
function sidebarH() {
  const clock = new Date(NOW * 1000).toTimeString().slice(0, 8);
  const rule = `<div class="rule">${"─".repeat(80)}</div>`;
  let h = `<div class="row"><span class="c-claude" style="font-weight:700">Admiral</span><span class="dim">  ${fmt("updated", { t: clock })}</span></div>`;
  h += `<div class="row"><span class="dim">${fmt("overall")} </span><span class="pbar" data-p="${B.pct}" data-m="0" data-n="0">${barH(B.pct, 0, 0)}</span></div>`;
  const ci = rows.filter(r => r.ciLevel === "fail").length;
  h += `<div class="row"><span class="dim">${fmt("total", { n: counts.total })} </span><span class="c-warn">◆ ${counts.waiting} ${fmt("waiting")}  </span>` +
    `<span class="c-ok">● ${counts.working} ${fmt("working")}  </span><span class="c-in">○ ${counts.idle} ${fmt("idle")}  </span>` +
    `<span class="c-err">✗</span><span class="c-in"> ${ci} ${fmt("ci")}</span></div>` + rule;
  h += `<div class="wbox" id="wbox"><div class="c-warn" style="font-weight:700">${fmt("waiting")}</div>` + B.waiting.map(x => {
    const lead = x.waitKind === "maybe" ? fmt("maybe_waiting") : x.waitKind === "reported" ? fmt("reported_waiting") : "";
    return `<div data-wait="${esc(x.name)}"><div class="row"><span class="c-warn">◆ </span><span class="grow">${nameH(x)}</span>` +
      `<span class="dim">${agoS(x.statusSince)}</span></div><div class="sub">${esc(lead + x.waitingFor)}</div></div>`;
  }).join("") + "</div>";
  h += B.groups.filter(g => g.summary.total > 0 || g.batch).map(teamH).join("");
  const idle = B.groups.filter(g => g.summary.total === 0 && !g.batch && g.leadRow);
  if (idle.length) h += `<div class="row team"><span class="grow dim">${fmt("idle_commanders", { n: idle.length })}</span><span class="btn">[ ${fmt("show")} ]</span></div>`;
  h += `<div class="row team"><span style="font-weight:700">${fmt("independent")}</span><span class="dim">  ${B.unassigned.length}</span></div>`;
  h += B.unassigned.map(x => rowH(x)).join("");
  h += rule + `<div style="font-weight:700">${fmt("close_head")}</div>`;
  for (const [key, cls, xs] of [["can_close", "c-ok", B.closable.close], ["wrap_up", "dim", B.closable.wrapup], ["confirm", "c-warn", B.closable.confirm]]) {
    if (!xs.length) continue;
    h += `<div class="${cls}">${fmt(key)} ${xs.length}</div>` + xs.map(x => `<div style="padding-left:1ch">${nameH(x)}<div class="sub">${esc(x.why)}</div></div>`).join("");
  }
  return h;
}

// ---------- scenes 3 to 5: the status line, the sidebar, a click ----------
const ui = document.getElementById("ui");
const cam = el("div", "abs", ui);
Object.assign(cam.style, { left: 0, top: 0, width: W + "px", height: H + "px", transformOrigin: "0 0" });
const MAIN = { x: 90, y: 210, w: 1740, h: 800 };
const main = el("div", "win cc", cam);
Object.assign(main.style, { left: MAIN.x + "px", top: MAIN.y + "px", width: MAIN.w + "px", height: MAIN.h + "px", zIndex: 10 });
el("div", "bar", main, `<i></i><i></i><i></i><span>acme-shop — ${esc(N("Commander-Search"))} — claude</span>`);
const area = el("div", "main-area", main);
const conv = el("div", "conv", area,
  `<span class="you">&gt; ${esc(TX.ask)}</span>\n\n<span class="c-ok">●</span> ${esc(TX.reply)}`);
el("div", "inputbox", area, `<span class="dim">&gt; </span><span id="caret" style="background:#d6dde6">&nbsp;</span>`);
const slWide = el("div", "", area, A.statusCommander.map(l => `<div class="sl">${l || " "}</div>`).join(""));
const slDock = el("div", "", area, A.statusDocked.map(l => `<div class="sl">${l || " "}</div>`).join(""));
slDock.style.display = "none";
const pane = el("div", "pane", main);
const paneInner = el("div", "", pane, sidebarH());  // scrolls, as the real pane does when its content is taller
const caret = document.getElementById("caret");
const hudN = A.hudLines;

// the other sessions' windows, behind (scene 5)
const PROMPT = (() => {  // Claude Code's permission prompt, every line padded to the box
  const Wb = 52, edge = s => `<span class="c-warn">${s}</span>`;
  const line = (text, html) => ` ${edge("│")} ${html ?? esc(text)}${" ".repeat(Wb - 1 - text.length)}${edge("│")}`;
  return [`<span class="c-ok">●</span> Bash(terraform plan -target=module.rate_limits)`, "",
    ` ${edge("╭" + "─".repeat(Wb + 1) + "╮")}`,
    line("Bash command", "<b>Bash command</b>"), line("  terraform plan -target=module.rate_limits"), line(""),
    line("Do you want to proceed?"), line("❯ 1. Yes", `<span class="c-warn">❯ 1. Yes</span>`),
    line("  2. Yes, and don't ask again for terraform plan"), line("  3. No, and tell Claude what to do differently"),
    ` ${edge("╰" + "─".repeat(Wb + 1) + "╯")}`].join("\n");
})();
const INDEX = `<span class="c-ok">●</span> Bash(gh pr checks 234)\n  ⎿  <span class="c-err">✗ tests (2)</span>  ✓ lint  ✓ tests (1)  ✓ browser\n\n` +
  `<span class="c-ok">●</span> Read(tests/search/test_facets.py)\n  ⎿  Read 188 lines\n\n` +
  `<span class="c-ok">●</span> ${esc(TX.index[0])}\n${esc(TX.index[1])}`;
const back = [
  [N("Rate-Limits"), PROMPT, 60, 250], [N("Search-Index"), INDEX, 230, 380], [N("Checkout-UI"), INDEX, 120, 520],
  [N("Coupons"), INDEX, 330, 640], [N("Mobile-Cart"), INDEX, 40, 740],
].map(([name, body, x, y], i) => {
  const w = el("div", "win", cam);
  Object.assign(w.style, { left: x + "px", top: y + "px", width: "820px", height: "470px", zIndex: 5 - i });
  el("div", "bar", w, `<i></i><i></i><i></i><span>acme-shop — ${esc(name)} — claude</span>`);
  el("div", "body", w, body).style.fontSize = "17px";
  return { name, w, x, y };
});

const capBand = el("div", "abs", ui);
Object.assign(capBand.style, { left: 0, top: 0, width: W + "px", height: "215px", zIndex: 30,
  background: "linear-gradient(180deg, rgba(8,17,27,.97) 0%, rgba(8,17,27,.93) 72%, rgba(8,17,27,0) 100%)" });
const capUI = el("div", "abs", ui);
capUI.style.zIndex = 31;
Object.assign(capUI.style, { left: "90px", top: "60px", width: "1740px" });
const eyebrow = el("div", "eyebrow", capUI);
const caption = el("div", "caption", capUI);
caption.style.marginTop = "10px";
const cursor = el("div", "", ui, `<svg viewBox="0 0 24 24" width="34" height="34"><path d="M4 2l15 11-6.5 1.2L16 21l-3 1.4-3.4-6.9L4 20z" fill="#fff" stroke="#111" stroke-width="1.2" stroke-linejoin="round"/></svg>`);
cursor.id = "cursor";
const ripple = el("div", "ripple", ui);
const SLOTS = 5;
const rings = [...Array(SLOTS)].map(() => el("div", "ring", ui));
const tags = [...Array(SLOTS)].map(() => el("div", "tag", ui));
const leads = [...Array(SLOTS)].map(() => { const e = el("div", "abs", ui); e.style.width = "2px"; return e; });

const hudNote = el("div", "abs mono", ui, TX.hud);
Object.assign(hudNote.style, { fontSize: "17px", color: "var(--brass)", opacity: 0 });
const KINDS = [[N("Rate-Limits"), TX.kinds[0], "amber"], [N("Checkout-UI"), TX.kinds[1], ""], [N("Search-Ranking"), TX.kinds[2], ""]];
const kindTags = KINDS.map(() => el("div", "tag", ui));
const kindLeads = KINDS.map(() => el("div", "abs", ui));
[...kindTags, ...kindLeads].forEach(e => { e.style.zIndex = 25; });

function setCaption(t, a, b, eb, text) {
  if (t < a || t > b) return false;
  eyebrow.textContent = eb;
  caption.innerHTML = text;
  show(capUI, fade(t, a, a + .5, b - .5, b), `translateY(${(1 - out3(seg(t, a, a + .6))) * 18}px)`);
  return true;
}
// the rectangle (stage coordinates) of a piece of text inside an element
function textRect(root, needle) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let acc = "", nodes = [];
  while (walker.nextNode()) { nodes.push([walker.currentNode, acc.length]); acc += walker.currentNode.data; }
  const i = acc.indexOf(needle);
  if (i < 0) return null;
  const range = document.createRange();
  const at = pos => { for (let k = nodes.length - 1; k >= 0; k--) if (nodes[k][1] <= pos) return [nodes[k][0], pos - nodes[k][1]]; };
  range.setStart(...at(i)); range.setEnd(...at(i + needle.length));
  const r = range.getBoundingClientRect(), s = document.getElementById("stage").getBoundingClientRect();
  return { x: r.left - s.left, y: r.top - s.top, w: r.width, h: r.height };
}
function rectOf(e) {
  const r = e.getBoundingClientRect(), s = document.getElementById("stage").getBoundingClientRect();
  return { x: r.left - s.left, y: r.top - s.top, w: r.width, h: r.height };
}
function callout(k, rect, label, cls, o, side = "above", tagY) {
  const ring = rings[k], tag = tags[k], lead = leads[k];
  if (!rect || o <= 0) { show(ring, 0); show(tag, 0); show(lead, 0); return; }
  const P = 8;
  Object.assign(ring.style, { left: rect.x - P + "px", top: rect.y - P + "px", width: rect.w + 2 * P + "px", height: rect.h + 2 * P + "px",
    borderColor: cls === "amber" ? "var(--amber)" : cls === "coral" ? "var(--coral)" : cls === "green" ? "#58c46d" : "var(--brass)" });
  tag.className = "tag " + (cls || "");
  tag.textContent = label;
  const tw = tag.offsetWidth || 300;
  const x = clamp(rect.x + rect.w / 2 - tw / 2, 20, W - tw - 20);
  tag.style.left = x + "px";
  const ty = tagY ?? (side === "above" ? rect.y - P - 62 : rect.y + rect.h + P + 14);
  tag.style.top = ty + "px";
  const color = cls === "amber" ? "var(--amber)" : cls === "coral" ? "var(--coral)" : cls === "green" ? "#58c46d" : "var(--brass)";
  const y0 = side === "above" ? ty + 48 : rect.y + rect.h + P, y1 = side === "above" ? rect.y - P : ty;
  Object.assign(lead.style, { left: rect.x + rect.w / 2 - 1 + "px", top: Math.min(y0, y1) + "px", height: Math.abs(y1 - y0) + "px", background: color });
  show(lead, Math.abs(y1 - y0) > 4 ? o * .8 : 0);
  show(ring, o, `scale(${lerp(1.06, 1, out3(Math.min(1, o * 1.5)))})`);
  show(tag, o, `translateY(${(1 - out3(o)) * 10}px)`);
}
function revealLines(box, t, a, step) {  // a terminal draws line by line
  [...box.children].forEach((line, i) => {
    const p = seg(t, a + i * step, a + i * step + step * 1.4);
    line.style.clipPath = `inset(0 ${100 - p * 100}% 0 0)`;
  });
}
function animateBars(root, x) {  // bars and pips fill to their value as x goes 0..1
  root.querySelectorAll(".pbar").forEach(b => { b.innerHTML = barH(+b.dataset.p, +b.dataset.m, +b.dataset.n, x); });
  root.querySelectorAll(".pips").forEach(p => { p.innerHTML = pipsH(+p.dataset.stage, Math.round(5 * x)); });
}

function sceneUI(t) {
  const on = t > 14.2 && t < 52;
  ui.style.display = on ? "block" : "none";
  if (!on) return;
  show(ui, fade(t, 14.2, 15.0, 51.2, 52));
  caret.style.opacity = Math.floor(t * 2) % 2 ? 0 : 1;
  // the window rises
  const rise = out3(seg(t, 14.2, 15.4));
  main.style.transform = `translateY(${(1 - rise) * 120}px)`;
  // scene 3: status line (14.6 .. 27)
  const docked = seg(t, 27.0, 28.4);
  const dk = inOut(docked);
  pane.style.transform = `translateX(${(1 - dk) * 100}%)`;
  area.style.width = lerp(MAIN.w, MAIN.w - 660, dk) + "px";
  slWide.style.display = docked < .5 ? "block" : "none";
  slDock.style.display = docked >= .5 ? "block" : "none";
  conv.style.opacity = out3(seg(t, 15.0, 15.8));
  revealLines(slWide, t, 15.6, .14);
  // callouts on the status line
  const L = slWide.children;
  // five marks on the first line build up one by one, then leave together; then the commanders' lines, one at a time
  const cs = [
    [17.6, 23.3, () => textRect(L[hudN], `${B.pct}%`), TX.marks[0], "", "above", 660],
    [18.6, 23.3, () => textRect(L[hudN], fmt("github_prs", { open: B.mine.open, merged: B.mine.mergedToday })), TX.marks[1], "", "above", 590],
    [19.6, 23.3, () => textRect(L[hudN], `◆ ${counts.waiting} ${fmt("waiting")}`), TX.marks[2], "amber", "above", 520],
    [20.6, 23.3, () => textRect(L[hudN], `✗ ${rows.filter(r => r.ciLevel === "fail").length} CI`), TX.marks[3], "coral", "above", 590],
    [21.6, 23.3, () => textRect(L[hudN], fmt("closable", { n: B.closable.close.length })), TX.marks[4], "green", "above", 520],
    [23.9, 25.2, () => { const a = rectOf(L[hudN + 1]), b = rectOf(L[hudN + 5]); return { x: a.x, y: a.y, w: 1130, h: b.y + b.h - a.y }; },
      TX.marks[5], "", "below"],
    [25.3, 26.6, () => textRect([...L].find(l => l.textContent.includes("▸ ")), "▸ " + short(N("Commander-Search"))), TX.marks[6], "", "below"],
  ];
  cs.forEach(([at, until, rect, label, cls, side, tagY], i) => {
    const k = i < 5 ? i : i - 5;
    if (i >= 5 && t < at - .01) return;  // the later two reuse slots the first five have left
    if (i < 5 && t > until + .55) return;
    const o = t >= at - .01 && t < until + .55 ? fade(t, at, at + .35, until, until + .5) : 0;
    callout(k, o > 0 ? rect() : null, label, cls, o, side, tagY);
  });
  if (t < 17.6 || t > 26.6 + .55) for (let k = 0; k < SLOTS; k++) callout(k, null);
  const capsShown =
    setCaption(t, 14.8, 26.8, ...TX.caps[0]) || setCaption(t, 26.8, 41.6, ...TX.caps[1]) || setCaption(t, 41.6, 51.6, ...TX.caps[2]);
  if (!capsShown) show(capUI, 0);
  show(capBand, t > 28.6 && t < 42.6 ? fade(t, 28.8, 29.6, 41.0, 41.8) : 0);
  // claude-hud's credit, beside its lines while they are on screen
  if (hudN) {
    const r = rectOf(L[0]);
    hudNote.style.left = r.x + 760 + "px"; hudNote.style.top = r.y + 6 + "px";
    show(hudNote, fade(t, 15.9, 16.3, 17.2, 17.6));
  }
  animateBars(pane, t < 35.6 ? 1 : out3(seg(t, 35.8, 37.8)));
  // scene 4: the sidebar (27 .. 41.6): zoom on who is waiting, then on a batch
  const wbox = document.getElementById("wbox");
  let z = { s: 1, x: 0, y: 0 };
  if (t >= 28.6 && t < 42.5) {
    const zoomIn = inOut(seg(t, 28.8, 30.0)), toTeam = inOut(seg(t, 34.6, 35.8)), zoomOut = inOut(seg(t, 40.4, 41.6));
    const target = r => ({ s: 1.6, x: 1090 - (r.x + r.w / 2) * 1.6, y: 650 - (r.y + Math.min(r.h, 520) / 2) * 1.6 });
    cam.style.transform = "none";
    paneInner.style.transform = "none";
    const wr = rectOf(wbox), tr = rectOf(pane.querySelector(`[data-team="${N("Commander-Checkout")}"]`));
    const scroll = (tr.y - rectOf(pane).y - 20) * inOut(seg(t, 34.6, 35.8)) * (1 - inOut(seg(t, 40.4, 41.6)));
    paneInner.style.transform = `translateY(${-scroll}px)`;
    tr.y -= scroll;
    const z1 = target(wr), z2 = target({ x: tr.x, y: tr.y, w: tr.w, h: 420 });
    const zz = { s: lerp(z1.s, z2.s, toTeam), x: lerp(z1.x, z2.x, toTeam), y: lerp(z1.y, z2.y, toTeam) };
    const amt = zoomIn * (1 - zoomOut);
    z = { s: lerp(1, zz.s, amt), x: lerp(0, zz.x, amt), y: lerp(0, zz.y, amt) };
  }
  // scene 5: a click (41.6 .. 51.6): step back, the other sessions behind, a click brings one forward
  const back5 = inOut(seg(t, 41.6, 43.0));
  const front = out3(seg(t, 45.0, 45.9));
  const mainS = lerp(1, .64, back5);
  main.style.left = lerp(MAIN.x, 1920 - MAIN.w * .64 - 60, back5) + "px";
  main.style.top = lerp(MAIN.y, 250, back5) + "px";
  main.style.transformOrigin = "0 0";
  main.style.transform = `translateY(${(1 - rise) * 120}px) scale(${mainS})`;
  back.forEach(({ name, w, x, y }, i) => {
    const o = back5;
    const isRL = name === N("Rate-Limits");
    const f = isRL ? front : 0;
    w.style.zIndex = isRL && front > .3 ? 20 : 5 - i;
    w.style.left = lerp(x, 120, f) + "px";
    w.style.top = lerp(y, 260, f) + "px";
    w.style.boxShadow = isRL && front > 0 ? `0 30px 80px rgba(0,0,0,.6), 0 0 0 ${3 * f}px var(--amber), 0 0 ${60 * f}px rgba(233,185,73,${.35 * f})` : "";
    show(w, o * (t < 51 ? 1 : 0), `scale(${lerp(.92, 1, o) * lerp(1, 1.06, f)})`);
  });
  cam.style.transform = `translate(${z.x}px, ${z.y}px) scale(${z.s})`;
  conv.style.opacity = out3(seg(t, 15.0, 15.8)) * (1 - .75 * clamp((z.s - 1) / .6));
  slDock.style.opacity = 1 - .75 * clamp((z.s - 1) / .6);
  // the three ways a session waits for you, while the camera is on the waiting box
  KINDS.forEach(([name, label, cls], i) => {
    const e = pane.querySelector(`[data-wait="${name}"] .row`);
    const o = t > 29.6 && t < 35.4 ? fade(t, 30.4 + i * .5, 30.9 + i * .5, 34.4, 35.0) : 0;
    if (!e || o <= 0) { show(kindTags[i], 0); show(kindLeads[i], 0); return; }
    const r = rectOf(e), box = rectOf(document.getElementById("wbox"));
    const tg = kindTags[i];
    tg.className = "tag " + cls; tg.textContent = label;
    const tw = tg.offsetWidth;
    tg.style.left = box.x - tw - 70 + "px"; tg.style.top = r.y + r.h / 2 - 24 + "px";
    Object.assign(kindLeads[i].style, { left: box.x - 70 + "px", top: r.y + r.h / 2 - 1 + "px", width: "70px", height: "2px",
      background: cls === "amber" ? "var(--amber)" : cls === "coral" ? "var(--coral)" : "var(--brass)" });
    show(tg, o, `translateX(${(1 - out3(o)) * -16}px)`); show(kindLeads[i], o * .8);
  });

  // the cursor: in at 43, to Rate-Limits in the waiting box, click at 44.8
  const nameEl = pane.querySelector(`#wbox [data-name="${N("Rate-Limits")}"]`);
  if (t > 42.6 && t < 50.6 && nameEl) {
    const r = rectOf(nameEl);
    const p = inOut(seg(t, 42.8, 44.6));
    const cx = lerp(1700, r.x + r.w * .4, p), cy = lerp(1050, r.y + r.h * .6, p) + Math.sin(p * Math.PI) * -60;
    const press = t > 44.8 && t < 45.0 ? .85 : 1;
    show(cursor, fade(t, 42.6, 43.0, 49.8, 50.4), `scale(${press})`);
    cursor.style.left = cx + "px"; cursor.style.top = cy + "px";
    nameEl.style.background = t > 44.5 && t < 46.5 ? "rgba(233,185,73,.25)" : "transparent";
    const rp = seg(t, 44.8, 45.6);
    Object.assign(ripple.style, { left: cx - 40 + "px", top: cy - 40 + "px" });
    show(ripple, rp > 0 && rp < 1 ? 1 - rp : 0, `scale(${.3 + rp * 1.4})`);
  } else { show(cursor, 0); show(ripple, 0); }
}

// ---------- shared: a caption at the top of a scene ----------
function makeCaption(layer) {
  const box = el("div", "abs", layer);
  Object.assign(box.style, { left: "90px", top: "60px", width: "1740px", zIndex: 30 });
  const eb = el("div", "eyebrow", box), cap = el("div", "caption", box);
  cap.style.marginTop = "10px";
  return (t, a, b, eyebrowText, text) => {
    eb.textContent = eyebrowText; cap.innerHTML = text;
    show(box, fade(t, a, a + .5, b - .5, b), `translateY(${(1 - out3(seg(t, a, a + .6))) * 18}px)`);
  };
}
const card = (layer, css) => { const e = el("div", "abs", layer); Object.assign(e.style, { background: "rgba(16,30,45,.92)",
  border: "1px solid rgba(207,167,90,.28)", borderRadius: "14px", boxShadow: "0 20px 60px rgba(0,0,0,.45)", ...css }); return e; };

// ---------- scene 6: milestones ----------
const msL = document.getElementById("milestones");
const capMS = makeCaption(msL);
const WEIGHTS = B.weights;  // [0, develop, review, accept, ci, merged]
const STATIONS = [1, 2, 3, 4, 5].map(i => ({ name: B.words.stages[i], w: WEIGHTS[i] }));
const DESC = TX.desc;
const X0 = 300, X1 = 1620, TY = 520;
const track = el("div", "abs", msL);
Object.assign(track.style, { left: X0 + "px", top: TY - 2 + "px", width: X1 - X0 + "px", height: "4px", background: "#22384c", borderRadius: "2px" });
const trackFill = el("div", "abs", msL);
Object.assign(trackFill.style, { left: X0 + "px", top: TY - 2 + "px", height: "4px", borderRadius: "2px" });
const stations = STATIONS.map((st, i) => {
  const x = X0 + (X1 - X0) * i / 4;
  const dot = el("div", "abs", msL);
  Object.assign(dot.style, { left: x - 15 + "px", top: TY - 15 + "px", width: "30px", height: "30px", borderRadius: "50%",
    border: "3px solid #2b4359", background: "var(--ink)" });
  const name = el("div", "abs headline", msL, st.name);
  Object.assign(name.style, { left: x - 160 + "px", width: "320px", top: TY - 112 + "px", textAlign: "center", fontSize: "56px" });
  const pct = el("div", "abs mono", msL, `${st.w}%`);
  Object.assign(pct.style, { left: x - 100 + "px", width: "200px", top: TY + 34 + "px", textAlign: "center", fontSize: "30px", color: "var(--brass)" });
  const desc = el("div", "abs", msL, DESC[i]);
  Object.assign(desc.style, { left: x - 150 + "px", width: "300px", top: TY + 82 + "px", textAlign: "center", fontSize: "24px", color: "var(--muted)" });
  return { x, dot, name, pct, desc };
});
const token = el("div", "abs mono", msL, esc(N("Checkout-API")));
Object.assign(token.style, { top: TY - 186 + "px", fontSize: "22px", padding: "6px 14px", borderRadius: "8px", background: "#21354a",
  border: "1px solid #3e5b78", color: "var(--fg)" });
const bigBar = el("div", "abs mono", msL);
Object.assign(bigBar.style, { left: "0", width: W + "px", top: "760px", textAlign: "center", fontSize: "64px", letterSpacing: "-.02em" });
const msNote = el("div", "abs caption", msL, TX.msNote);
Object.assign(msNote.style, { left: 0, width: W + "px", top: "905px", textAlign: "center", fontSize: "32px", color: "var(--muted)" });

function sceneMilestones(t) {
  const on = t > 51.2 && t < 59.6;
  msL.style.display = on ? "block" : "none";
  if (!on) return;
  const o = fade(t, 51.4, 52.0, 58.8, 59.4);
  msL.style.opacity = o;
  capMS(t, 51.6, 59.2, ...TX.caps[3]);
  const stepAt = i => 52.4 + i * 1.05;
  let reached = 0;
  for (let i = 0; i < 5; i++) if (t >= stepAt(i)) reached = i + 1;
  // the token sits on the first station, then glides to each next one, arriving as that station lights
  let pos = 0;
  for (let i = 1; i < 5; i++) pos += out3(seg(t, stepAt(i) - .45, stepAt(i)));
  const tx = X0 + (X1 - X0) * pos / 4;
  token.style.left = tx - token.offsetWidth / 2 + "px";
  show(token, out3(seg(t, 51.8, 52.4)));
  trackFill.style.width = (X1 - X0) * pos / 4 + "px";
  trackFill.style.background = `linear-gradient(90deg, ${shade(.1)}, ${shade(Math.max(.15, pos / 4))})`;
  stations.forEach((s, i) => {
    const lit = reached > i;
    const g = out3(seg(t, stepAt(i), stepAt(i) + .4));
    s.dot.style.background = lit ? shade((i + 1) / 5) : "var(--ink)";
    s.dot.style.borderColor = lit ? shade((i + 1) / 5) : "#2b4359";
    s.dot.style.boxShadow = lit ? `0 0 ${24 * g}px ${shade((i + 1) / 5)}` : "none";
    s.name.style.color = lit ? "var(--fg)" : "#4c6276";
    show(s.name, out3(seg(t, 51.8 + i * .08, 52.3 + i * .08)));
    show(s.pct, out3(seg(t, 51.9 + i * .08, 52.4 + i * .08)));
    show(s.desc, out3(seg(t, 52.0 + i * .08, 52.5 + i * .08)) * (lit ? 1 : .55));
  });
  const p = reached ? WEIGHTS[reached] * out3(seg(t, stepAt(reached - 1), stepAt(reached - 1) + .5)) +
    (reached > 1 ? WEIGHTS[reached - 1] * (1 - out3(seg(t, stepAt(reached - 1), stepAt(reached - 1) + .5))) : 0) : 0;
  const filled = Math.round(p / 10);
  let h = "";
  for (let i = 0; i < filled; i++) h += `<span style="color:${shade((i + 1) / 10)}">█</span>`;
  bigBar.innerHTML = h + `<span style="color:#2a3c4f">${"░".repeat(10 - filled)}</span>  <span style="color:var(--fg)">${pad(Math.round(p), 3)}%</span>`;
  show(bigBar, out3(seg(t, 52.2, 52.8)));
  show(msNote, fade(t, 56.8, 57.4, 59.6, 60));
}

// ---------- scene 7: a PR nobody registered ----------
const pushL = document.getElementById("push");
const capPush = makeCaption(pushL);
const sIdx = byName[N("Search-Index")];
const sGroup = groups.find(g => g.lead === N("Commander-Search"));
const pushWin = el("div", "win", pushL);
Object.assign(pushWin.style, { left: "110px", top: "330px", width: "820px", height: "330px" });
el("div", "bar", pushWin, `<i></i><i></i><i></i><span>acme-shop — ${esc(N("Search-Index"))} — claude</span>`);
const pushLines = [
  `<span class="c-ok">●</span> Bash(git push -u origin feat/search-index)`,
  `  ⎿  To github.com:acme/shop.git`,
  `      * [new branch]      <span style="color:var(--amber)">feat/search-index -&gt; feat/search-index</span>`,
  `     branch 'feat/search-index' set up to track 'origin/feat/search-index'.`,
];
const pushBody = el("div", "body", pushWin, pushLines.map(l => `<div class="sl">${l}</div>`).join(""));
pushBody.style.fontSize = "17px"; pushBody.style.lineHeight = "1.7"; pushBody.style.padding = "22px 24px";
const batchCard = card(pushL, { left: "1080px", top: "300px", width: "730px", height: "420px", padding: "26px 30px", fontFamily: "var(--mono)", fontSize: "19px", lineHeight: "1.6" });
const prCard = el("div", "abs mono", pushL, `${esc(sIdx.pr.label)}  <span class="c-err">✗ tests (2)</span>`);
Object.assign(prCard.style, { fontSize: "22px", padding: "10px 18px", borderRadius: "10px", background: "#2a2416",
  border: "1px solid var(--amber)", color: "var(--fg)", zIndex: 5 });
const pushNote = el("div", "abs", pushL, TX.pushNote);
Object.assign(pushNote.style, { left: "110px", width: "1700px", top: "800px", fontSize: "30px", color: "var(--muted)", lineHeight: "1.4" });
function batchHTML(withPR) {
  const s = sGroup.summary, prs = withPR ? s.prs : s.prs - 1;
  const lines = sGroup.members.map(m => {
    const [mark, cls] = RUN[m.status] || RUN.idle;
    const pr = m.name === N("Search-Index") ? (withPR ? `  <span class="dim">${esc(m.pr.label)}</span>` : "  <span class=\"dim\">—</span>")
      : m.pr && m.pr.state === "OPEN" ? `  <span class="dim">${esc(m.pr.label)}</span>` : "";
    const hl = m.name === N("Search-Index") ? ` id="sidx" style="border-radius:6px"` : "";
    return `<div${hl}><span class="${cls}">${mark}</span> ${esc(m.name)}${pr}</div>`;
  }).join("");
  return `<div style="font-weight:700">${esc(sGroup.lead)}</div><div style="padding-left:2ch">${barH(s.pct, s.prsMerged, prs)}</div>` +
    `<div style="height:10px"></div>${lines}`;
}
function scenePush(t) {
  const on = t > 59 && t < 67;
  pushL.style.display = on ? "block" : "none";
  if (!on) return;
  pushL.style.opacity = fade(t, 59.2, 59.8, 66.2, 66.8);
  capPush(t, 59.4, 66.6, ...TX.caps[4]);
  [...pushBody.children].forEach((line, i) => { line.style.clipPath = `inset(0 ${100 - 100 * seg(t, 60.2 + i * .35, 60.6 + i * .35)}% 0 0)`; });
  show(pushWin, out3(seg(t, 59.6, 60.2)), `translateY(${(1 - out3(seg(t, 59.6, 60.3))) * 30}px)`);
  show(batchCard, out3(seg(t, 59.9, 60.5)), `translateY(${(1 - out3(seg(t, 59.9, 60.6))) * 30}px)`);
  const landed = t > 63.0;
  batchCard.innerHTML = batchHTML(landed);
  const fly = inOut(seg(t, 61.9, 63.0));
  const from = { x: 330, y: 450 }, to = (() => { const r = document.getElementById("sidx"); return r ? rectOf(r) : { x: 1300, y: 600, w: 300, h: 30 }; })();
  prCard.style.left = lerp(from.x, to.x + 260, fly) + "px";
  prCard.style.top = lerp(from.y, to.y - 6, fly) - Math.sin(fly * Math.PI) * 120 + "px";
  show(prCard, t > 61.6 && t < 63.1 ? out3(seg(t, 61.6, 61.9)) : 0, `scale(${lerp(1, .8, fly)})`);
  const sidx = document.getElementById("sidx");
  if (sidx) sidx.style.background = landed ? `rgba(233,185,73,${.25 * (1 - seg(t, 63.4, 65))})` : "transparent";
  show(pushNote, fade(t, 63.6, 64.2, 66.2, 66.8));
}

// ---------- scene 8: what you can close ----------
const closeL = document.getElementById("close");
const capClose = makeCaption(closeL);
const COLS = [["can_close", "#58c46d", B.closable.close], ["wrap_up", "#c9d3de", B.closable.wrapup], ["confirm", "var(--amber)", B.closable.confirm]];
const closeCards = COLS.map(([key, color, xs], i) => {
  const c = card(closeL, { left: 90 + i * 590 + "px", top: "290px", width: "560px", padding: "30px 32px 26px", borderTop: `3px solid ${color}` });
  c.innerHTML = `<div class="headline" style="font-size:52px;color:${color}">${esc(fmt(key))} <span style="color:var(--muted);font-size:40px">${xs.length}</span></div>` +
    xs.map(x => `<div style="margin-top:20px"><div class="mono" style="font-size:24px;color:var(--fg)">${esc(x.name)}</div>` +
      `<div style="font-size:21px;color:var(--muted);line-height:1.35;margin-top:4px">${esc(x.why)}</div></div>`).join("");
  return c;
});
const closeNote = el("div", "abs caption", closeL, TX.closeNote);
Object.assign(closeNote.style, { left: "90px", width: "1740px", top: "960px", fontSize: "32px", color: "var(--muted)" });
function sceneClose(t) {
  const on = t > 66.4 && t < 73.6;
  closeL.style.display = on ? "block" : "none";
  if (!on) return;
  closeL.style.opacity = fade(t, 66.6, 67.2, 72.8, 73.4);
  capClose(t, 66.8, 73.2, ...TX.caps[5]);
  closeCards.forEach((c, i) => show(c, out3(seg(t, 67.4 + i * .35, 68.0 + i * .35)), `translateY(${(1 - out3(seg(t, 67.4 + i * .35, 68.1 + i * .35))) * 40}px)`));
  show(closeNote, out3(seg(t, 69.6, 70.2)));
}

// ---------- scene 9: the playbook, and locks ----------
const pbL = document.getElementById("playbook");
const capPB = makeCaption(pbL);
const SKILLS = ["principles", "roles", "workspace", "resources", "pipeline", "wrapup"].map((name, i) => [name, TX.skills[i]]);
const skillCards = SKILLS.map(([name, text], i) => {
  const c = card(pbL, { left: 90 + (i % 2) * 520 + "px", top: 290 + Math.floor(i / 2) * 200 + "px", width: "490px", height: "176px", padding: "24px 28px" });
  c.innerHTML = `<div class="mono" style="font-size:26px;color:var(--brass)">${name}</div><div style="font-size:23px;line-height:1.35;margin-top:10px;color:#cdd7e2">${esc(text)}</div>`;
  return c;
});
const lockCard = card(pbL, { left: "1170px", top: "290px", width: "660px", height: "576px", padding: "28px 32px" });
lockCard.innerHTML = `<div class="mono" style="font-size:22px;color:var(--muted)">admiral lock status</div>
  <div class="mono" style="font-size:30px;margin-top:22px;color:var(--fg)">heavy-gate</div>
  <div id="holder" class="mono" style="font-size:22px;margin-top:10px;padding:12px 16px;border-radius:10px;background:#1c3a29;color:#bfe8c8">${esc(f0(TX.held, N("Checkout-Acceptance")))}</div>
  <div class="mono" style="font-size:20px;margin-top:26px;color:var(--muted)">${TX.inOrder}</div>
  <div id="queue" style="position:relative;height:200px;margin-top:10px"></div>
  <div id="qnote" style="font-size:22px;color:var(--brass);margin-top:6px">${TX.qnote}</div>`;
const queue = lockCard.querySelector("#queue");
const qItems = [[f0(TX.queue[0], N("Search-Acceptance")), "0"], [f0(TX.queue[1], N("Mobile-Release")), "1"]].map(([text, prio]) => {
  const e = el("div", "abs mono", queue, `${esc(text)}  <span style="color:var(--brass)">${TX.prio} ${prio}</span>`);
  Object.assign(e.style, { left: 0, width: "590px", fontSize: "20px", padding: "11px 16px", borderRadius: "10px", background: "#1d2c3c", color: "#cdd7e2" });
  return e;
});
function scenePlaybook(t) {
  const on = t > 73 && t < 80.6;
  pbL.style.display = on ? "block" : "none";
  if (!on) return;
  pbL.style.opacity = fade(t, 73.2, 73.8, 79.8, 80.4);
  capPB(t, 73.4, 80.2, ...TX.caps[6]);
  skillCards.forEach((c, i) => show(c, out3(seg(t, 74.0 + i * .15, 74.6 + i * .15)), `translateY(${(1 - out3(seg(t, 74.0 + i * .15, 74.7 + i * .15))) * 30}px)`));
  show(lockCard, out3(seg(t, 74.6, 75.2)), `translateY(${(1 - out3(seg(t, 74.6, 75.3))) * 30}px)`);
  const join = out3(seg(t, 76.2, 76.7)), jump = inOut(seg(t, 77.2, 78.0));
  qItems[0].style.top = lerp(0, 66, jump) + "px";
  show(qItems[0], out3(seg(t, 75.4, 75.8)));
  qItems[1].style.top = lerp(132, 0, jump) + "px";
  show(qItems[1], join, `translateX(${(1 - join) * 40}px)`);
  qItems[1].style.boxShadow = jump > 0 && jump < 1 ? "0 0 0 2px var(--brass)" : "none";
  show(lockCard.querySelector("#qnote"), out3(seg(t, 77.8, 78.4)));
}

// ---------- scene 10: what changes ----------
const limitL = el("div", "layer", document.getElementById("stage"));
limitL.style.zIndex = 5;
const limit1 = el("div", "abs headline", limitL, TX.limit[0]);
const limit2 = el("div", "abs headline", limitL, TX.limit[1]);
const limit3 = el("div", "abs caption", limitL, TX.limit[2]);  // what Admiral itself costs: nothing
Object.assign(limit3.style, { left: 0, width: W + "px", top: "760px", textAlign: "center", fontSize: "40px", color: "var(--muted)" });
[[limit1, 380, "var(--fg)"], [limit2, 540, "var(--green)"]].forEach(([e, top, color]) =>
  Object.assign(e.style, { left: 0, width: W + "px", top: top + "px", textAlign: "center", fontSize: "150px", color }));
function sceneLimit(t) {
  const on = t > 79.8 && t < 84.4;
  limitL.style.display = on ? "block" : "none";
  if (!on) return;
  show(limit1, fade(t, 80.2, 80.8, 83.4, 84.0), `translateY(${(1 - outExpo(seg(t, 80.2, 81.2))) * 40}px)`);
  show(limit2, fade(t, 81.2, 81.8, 83.4, 84.0), `translateY(${(1 - outExpo(seg(t, 81.2, 82.2))) * 40}px)`);
  limit2.style.letterSpacing = lerp(.12, .01, outExpo(seg(t, 81.2, 82.6))) + "em";
  show(limit3, fade(t, 82.3, 82.8, 83.6, 84.1), `translateY(${(1 - out3(seg(t, 82.3, 82.9))) * 16}px)`);
}

// ---------- scene 11: the end ----------
const outL = document.getElementById("outro");
const endTitle = el("div", "abs headline", outL, "Admiral");
Object.assign(endTitle.style, { left: 0, width: W + "px", top: "150px", textAlign: "center", fontSize: "230px", fontWeight: 900, letterSpacing: ".06em" });
endTitle.style.fontFamily = '"Big Shoulders Display", sans-serif';
const endTag = el("div", "abs caption", outL, TX.tagline);
Object.assign(endTag.style, { left: 0, width: W + "px", top: "395px", textAlign: "center", fontSize: "50px" });
const facts = el("div", "abs", outL, TX.facts
  .map(f => `<span style="padding:0 28px">${f}</span>`).join(`<span style="color:var(--brass)">·</span>`));
Object.assign(facts.style, { left: 0, width: W + "px", top: "500px", textAlign: "center", fontSize: "30px", color: "var(--muted)" });
const install = card(outL, { left: "360px", top: "600px", width: "1200px", padding: "28px 36px", fontFamily: "var(--mono)", fontSize: "26px", lineHeight: "1.7" });
install.innerHTML = `<div><span style="color:var(--muted)">$</span> git clone https://github.com/onemoneki-sudo/Admiral.git ~/admiral</div>` +
  `<div><span style="color:var(--muted)">$</span> ~/admiral/scripts/install.sh</div>` +
  `<div><span style="color:var(--muted)">$</span> admiral demo${zh ? " --lang zh" : ""} <span style="color:var(--muted)">  ${TX.demoNote}</span></div>`;
const url = el("div", "abs mono", outL, "github.com/onemoneki-sudo/Admiral");
Object.assign(url.style, { left: 0, width: W + "px", top: "880px", textAlign: "center", fontSize: "34px", color: "var(--brass)", letterSpacing: ".04em" });
function sceneOutro(t) {
  const on = t > 84;
  outL.style.display = on ? "block" : "none";
  if (!on) return;
  outL.style.opacity = fade(t, 84.2, 84.8, DURATION - .9, DURATION - .1);
  show(endTitle, out3(seg(t, 84.4, 85.4)), `translateY(${(1 - outExpo(seg(t, 84.4, 85.6))) * 40}px)`);
  endTitle.style.letterSpacing = lerp(.18, .06, outExpo(seg(t, 84.4, 85.8))) + "em";
  show(endTag, out3(seg(t, 85.2, 85.8)));
  show(facts, out3(seg(t, 85.8, 86.4)));
  show(install, out3(seg(t, 86.6, 87.2)), `translateY(${(1 - out3(seg(t, 86.6, 87.3))) * 24}px)`);
  show(url, out3(seg(t, 87.4, 88.0)));
}

// ---------- the decisions scene: calls gather at the commander; the low-risk ones are decided and logged, the person's
// ones arrive together (story IN .. IN + D) ----------
const decL = el("div", "layer", document.getElementById("stage"));
decL.style.zIndex = 60;
const capDec = makeCaption(decL);
const EXEC = ["Tax-Rules", "Order-Emails", "Checkout-API", "Fraud-Signals", "Checkout-UI", "Payments-Gateway"];
const ROUTE = [0, 4, 1, 2, 5, 3];  // the order the calls come in; 0-3 are low-risk, 4-5 the person's
const execCards = EXEC.map((name, i) => {
  const c = card(decL, { left: "110px", top: 300 + i * 104 + "px", width: "380px", height: "76px", padding: "14px 20px",
    fontFamily: "var(--mono)", fontSize: "21px", color: "var(--fg)" });
  c.innerHTML = `<span style="color:var(--green)">●</span> ${esc(N(name))}`;
  return c;
});
const cmdCard = card(decL, { left: "730px", top: "500px", width: "430px", padding: "22px 26px", borderColor: "var(--brass)" });
cmdCard.innerHTML = `<div class="mono" style="font-size:23px;color:var(--fg)">${esc(N("Commander-Checkout"))}</div>` +
  `<div style="font-size:20px;color:var(--muted);margin-top:8px">${esc(TX.dec.cmd)}</div>`;
const logCard = card(decL, { left: "1290px", top: "250px", width: "540px", height: "380px", padding: "22px 26px" });
logCard.innerHTML = `<div class="mono" style="font-size:22px;color:var(--brass)">${esc(TX.dec.log)}</div>` +
  [0, 1, 2, 3].map(k => `<div class="mono dl" style="font-size:19px;color:#cdd7e2;margin-top:16px;white-space:normal;line-height:1.35">` +
    `<span style="color:var(--green)">✓</span> ${esc(TX.dec.a[k])}</div>`).join("");
const youCard = card(decL, { left: "1290px", top: "668px", width: "540px", height: "300px", padding: "22px 26px", borderColor: "var(--amber)" });
youCard.innerHTML = `<div class="mono" style="font-size:22px;color:var(--amber)">${esc(TX.dec.you)} · <span id="youN">0</span></div>` +
  [4, 5].map(k => `<div class="yl" style="margin-top:16px"><div style="font-size:21px;color:var(--fg)">◆ ${esc(TX.dec.q[k])}</div>` +
    `<div class="mono" style="font-size:17px;color:var(--muted);margin-top:4px;white-space:normal">${esc(TX.dec.rec)}: ${esc(TX.dec.a[k])}</div></div>`).join("");
const chips = EXEC.map((_, i) => {
  const c = el("div", "abs", decL, `? ${esc(TX.dec.q[i])}`);
  Object.assign(c.style, { fontFamily: "var(--body)", fontSize: "18px", padding: "8px 14px", borderRadius: "999px", whiteSpace: "nowrap",
    background: "#1d2c3c", border: `1px solid ${i >= 4 ? "var(--amber)" : "rgba(207,167,90,.6)"}`, color: "var(--fg)", zIndex: 5 });
  return c;
});
const bez = (a, b, c, x) => (1 - x) * (1 - x) * a + 2 * (1 - x) * x * b + x * x * c;
function sceneDecisions(u) {
  const on = u > 0 && u < D;
  decL.style.display = on ? "block" : "none";
  if (!on) return 0;
  const k = fade(u, 0, .5, D - .5, D);
  decL.style.opacity = k;
  capDec(u, .2, D - .2, ...TX.dec.cap);
  execCards.forEach((c, i) => show(c, out3(seg(u, .4 + i * .08, .8 + i * .08)), `translateX(${(1 - out3(seg(u, .4 + i * .08, .9 + i * .08))) * -30}px)`));
  show(cmdCard, out3(seg(u, .6, 1.0)), `scale(${lerp(.94, 1, out3(seg(u, .6, 1.1)))})`);
  show(logCard, out3(seg(u, .8, 1.2)));
  show(youCard, out3(seg(u, .9, 1.3)));
  const cmdIn = { x: 740, y: 560 }, cmdOut = { x: 1150, y: 560 };
  let logged = 0, yours = 0, busy = 0;
  ROUTE.forEach((i, n) => {
    const c = chips[i], w = c.offsetWidth, h = c.offsetHeight;
    const go = 1.1 + n * .32, mid = go + .55, back = 1.9 + n * .32, land = back + .5;
    const from = { x: 490, y: 338 + i * 104 };
    const to = i < 4 ? { x: 1290, y: 300 + i * 60 } : { x: 1290, y: 730 + (i - 4) * 80 };
    let x, y, o = 1;
    // x is the chip's left edge: it leaves the member's card, stops with its right edge at the commander's card, and
    // later leaves from the commander's right edge into the log or the person's card
    if (u < go) o = 0;
    else if (u < mid) { const p = inOut(seg(u, go, mid)); x = bez(from.x + 10, 610 - w / 2, cmdIn.x - 12 - w, p); y = bez(from.y, (from.y + cmdIn.y) / 2 - 60, cmdIn.y, p);
      o = 1 - seg(u, mid - .12, mid); }
    else if (u < back) { o = 0; busy = Math.max(busy, 1 - seg(u, mid, back)); }
    else if (u < land) { const p = inOut(seg(u, back, land)); x = bez(cmdOut.x + 12, 1210, to.x + 16, p); y = bez(cmdOut.y, (cmdOut.y + to.y) / 2 - 40, to.y, p);
      o = Math.min(1, seg(u, back, back + .1)) * (1 - seg(u, land - .12, land)); }
    else o = 0;
    if (u >= land) { if (i < 4) logged++; else yours++; }
    if (o > 0) { c.style.left = x + "px"; c.style.top = y - h / 2 + "px"; }
    show(c, o, `scale(${u < mid ? 1 : .9})`);
  });
  cmdCard.style.boxShadow = `0 20px 60px rgba(0,0,0,.45), 0 0 ${30 * busy}px rgba(207,167,90,${.45 * busy})`;
  logCard.querySelectorAll(".dl").forEach((d, j) => show(d, j < logged ? 1 : 0, `translateY(${j < logged ? 0 : 8}px)`));
  youCard.querySelectorAll(".yl").forEach((d, j) => show(d, j < yours ? 1 : 0));
  youCard.querySelector("#youN").textContent = yours;
  const glow = yours === 2 ? Math.sin(Math.PI * seg(u, 4.4, 6.0)) : 0;
  youCard.style.boxShadow = `0 20px 60px rgba(0,0,0,.45), 0 0 0 ${2 * glow}px var(--amber), 0 0 ${50 * glow}px rgba(233,185,73,${.35 * glow})`;
  return k;
}

// ---------- frame ----------
const scenes = [sceneChaos, sceneFleet, sceneUI, sceneMilestones, scenePush, sceneClose, scenePlaybook, sceneLimit, sceneOutro];
const curtain = el("div", "layer", document.getElementById("stage"));  // the poster fades to the dark water the story starts on
Object.assign(curtain.style, { background: "var(--ink)", zIndex: 100 });
function render(t) {
  const s = t < P ? POSTER_AT : t - P;
  const old = s < IN ? s : s < IN + D ? IN : s - D;  // the other scenes' own time: they hold still while the decisions play
  drawChart(old, sonar(old));
  for (const sc of scenes) sc(old);
  const k = sceneDecisions(s - IN);
  if (k > 0) { const ui = document.getElementById("ui"); ui.style.opacity = (parseFloat(ui.style.opacity) || 0) * (1 - k); }
  show(curtain, t < P ? inOut(seg(t, P - .5, P)) : 1 - seg(t, P, P + .4));
}
window.render = render;
window.DURATION = DURATION;
render(0);
