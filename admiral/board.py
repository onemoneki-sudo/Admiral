"""The board: every running session, grouped under its commander, with milestone progress, who waits for the person,
and which sessions can be closed. `admiral board --write` leaves it in <state_dir>/board.json (the status line and
the sidebar read it) and <state_dir>/board.md (sessions read it).

Milestones, 0 to 5, for a session or a planned deliverable:
  0 not started  a deliverable with neither PR nor registered owner (an unregistered session is left out)
  1 develop      registered, nothing later yet
  2 review       phase `review`: development done, independent review and its fixes
  3 accept       phase `accepting`: the person's acceptance or the local full gate
  4 CI           its PR is open and ready: everything local is done and it was pushed once (a draft is not)
  5 merged       its PR merged, as GitHub says
A PR, when there is one, speaks for itself: phase `done` with a PR not merged is at most accept. Only where no PR speaks
does phase `done` reach the last milestone, shown as reported done: never counted as a merge, and never enough on its
own for a session to be closed.
Each milestone is worth a share (config `progress`) and a percentage is the mean worth. A commander's progress counts
its plan's deliverables when it has one (a merged deliverable keeps counting after its session closes), else its
live members. Grouping: a registered `--lead` wins; otherwise the commander whose cross-session message the session
received last.
"""

import os
import time

from . import github, registry, sessions
from . import words as words_mod
from .words import STAGE_KEYS, words

ORDER = {"waiting": 0, "busy": 1, "shell": 2, "idle": 3}

TEXT = words_mod.phrases({
    "en": {
        "working": "working", "waiting": "waiting for you", "members": "{n} {n:member|members} not finished",
        "members_wrapup": "waiting for {n} {n:member|members} to wrap up", "members_done": "all {n} {n:member|members} finished and wrapped up",
        "deregistered_done": "finished and deregistered",
        "h_unlinked": "PR #{n} ({branch}) belongs to no session{where}: the session that owns it should add the branch to its registration (several branches: comma-separated)",
        "checked_out": ", checked out in {wt}",
        "h_guessed": "PR #{n} ({branch}) is counted for {name}, who pushed it or did the work in its worktree: "
                     "{name} should add the branch to its registration",
        "h_lead_pushed": "PR #{n} ({branch}) was pushed by {name} and counts for its batch: {name} should add it to its "
                         "plan (admiral plan add) with the session that owns it",
        "plan_open": "plan not all merged", "plan_done": "plan all merged: close the plan and report done",
        "locks": "still holds {n} {n:lock|locks}", "reported_done": "reported done, no member running",
        "no_members": "no member running and no plan: confirm the work is over before closing",
        "pr_open": "PR not merged", "merged_left": "merged, wrap-up left: {what}", "worktree": "worktree not deleted",
        "holds": "holds {n} {n:lock|locks}", "registered": "still registered", "merged_clean": "merged and wrapped up",
        "deregister": " (run `admiral done` before closing)", "pr_closed": "PR closed without merging",
        "pr_unknown": "GitHub did not answer: its PR is unknown",
        "reported_only": "reported done, but no merged PR shows it: confirm the work is over before closing",
        "left": "; wrap-up left: {what}",
        "plan_reported": "plan finished, but {n} {n:deliverable is|deliverables are} only reported done, with no merged PR: "
                         "confirm, then close the plan",
        "idle_unregistered": "unregistered, no PR, idle {age}", "unregistered_locks": "unregistered, holds {n} {n:lock|locks}",
        "developing": "developing",
        "h_unregistered": "running but not registered: {name}",
        "h_renamed": "registered under the old name \"{old}\"; the session is now \"{new}\": register again under the new name and `done` the old one",
        "h_idle": "idle over {days} days: {name}; close it if its work is over",
        "h_lead_gone": "--lead names a commander that is not running: {lead}",
        "h_twice": "{name} is open {n} times ({where}): close all but one, as each writes the same conversation",
        "h_plan_finished": "the plan of {lead} is all merged and nobody of its batch runs: no longer shown; "
                           "admiral plan close --lead \"{lead}\" puts it away",
        "h_gone": "registered but the session has ended: {who} (`admiral done --who \"{who}\"` once confirmed)",
        "h_worktree_gone": "worktree no longer exists: {who} -> {wt}",
        "h_pr_done": "{label}, still registered: {who}; wrap it up",
        "h_stale_phase": "phase not updated for over {hours} hours: {who} ({phase})",
        "x_gh": "gh failed: no PR or CI this time",
        "x_open_limit": "{n} open {n:PR is|PRs are} past the newest {limit}: {n:its|their} CI is not shown",
        "x_broken": "{n} session {n:file does|files do} not parse (Claude Code's internal format may have changed, or a file was being written); skipped",
        "x_shape": "{n} session {n:file lacks|files lack} one of {fields}: Claude Code's internal format may have changed; run states may be wrong",
        "x_no_transcripts": "no transcript found (~/.claude/projects): their location may have changed; grouping by message is off",
        "x_no_messages": "no commander message found in any transcript: the cross-session message format may have changed; grouping by message may be off (--lead is unaffected)",
        "title": "Admiral board ({n} running{total})", "progress": ", progress {pct}% ({spread})",
        "updated": "Updated {t}, every minute; older than 3 minutes means the background job stopped.",
        "built": "Built just now, at {t}, for this command; the background job keeps its own copy, refreshed every minute.",
        "weights": "Progress by milestone: {weights}; a batch takes the mean.", "x_head": "> Source problem: {h}",
        "waiting_head": "## Waiting for you ({n})", "none": "- none", "teams_head": "## Commanders",
        "team_line": "- {lead} ({own}): {pct}{how} · {n} {n:member|members} · {busy} working · {waiting} waiting · {ci} CI failing",
        "live_members": " (live members)", "team_head": "## {lead} ({pct}; {how})",
        "how_plan": "plan, merged {done}/{n}", "how_live": "live members, no plan",
        "no_member_rows": "(no members: executors register with --lead, or receive a message from this commander)",
        "independent": "## Independent sessions ({n}, no commander)", "close_head": "## Wrap-up (after a PR merges, wrap up, then close)",
        "close": "can close", "wrapup": "wrap up first", "confirm": "for you to confirm", "close_none": "- no session to close",
        "tidy": "## To tidy ({n})",
        "cols": "| Session | Run | Milestone · phase | Branch | PR | CI | Last commit |",
        "item_cols": "| Deliverable | Branch | Owner | Milestone | PR | CI |",
        "unreg": "unregistered", "nophase": "no phase reported", "dir_gone": "directory gone", "ago": "{age} ago",
        "just_now": "just now", "waiting_line": "- {name}{lead}: {what}, {when}", "waiting_lead": " ({lead})",
        "not_running": "not running", "waiting_for": "waiting for input",
    },
    "zh": {
        "working": "正在工作", "waiting": "待处理", "members": "还有 {n} 个成员未完成",
        "members_wrapup": "等 {n} 个成员收尾", "members_done": "{n} 个成员都已完成并收尾",
        "deregistered_done": "已完成并注销登记",
        "h_unlinked": "PR #{n}（{branch}）没有对应到任何对话{where}：请负责它的对话把这个分支加进登记（多个分支用逗号分隔）",
        "checked_out": "，检出在 {wt}",
        "h_guessed": "PR #{n}（{branch}）按推送或工作区里的修改记录算给了 {name}：请 {name} 把这个分支补进登记",
        "h_lead_pushed": "PR #{n}（{branch}）由 {name} 推送，已算进本批次：请 {name} 用 admiral plan add 把它连同负责对话登记进交付清单",
        "plan_open": "交付清单未全部合并", "plan_done": "交付清单已全部合并，先关闭交付清单",
        "locks": "仍占用 {n} 把锁", "reported_done": "已报告完成，没有成员在运行",
        "no_members": "没有成员在运行，也没有交付清单；确认任务已结束再关闭",
        "pr_open": "PR 未合并", "merged_left": "已合并，待收尾：{what}", "worktree": "worktree 未删除",
        "holds": "占用 {n} 把锁", "registered": "仍在登记中", "merged_clean": "已合并并收尾",
        "deregister": "（关闭前 admiral done）", "pr_closed": "PR 已关闭但未合并",
        "pr_unknown": "GitHub 没有响应，PR 状态未知",
        "reported_only": "已报告完成，但没有已合并的 PR 可以印证：确认任务已结束再关闭",
        "left": "；待收尾：{what}",
        "plan_reported": "交付清单都已完成，但有 {n} 项只是自报完成、没有已合并的 PR：确认后再关闭交付清单",
        "idle_unregistered": "未登记、无 PR，已空闲 {age}", "unregistered_locks": "未登记，仍占用 {n} 把锁",
        "developing": "开发中",
        "h_unregistered": "运行中但未登记：{name}",
        "h_renamed": "登记名仍为旧名「{old}」，对话已改名为「{new}」：请用新名重新登记，并 done 旧名",
        "h_idle": "空闲超过 {days} 天：{name}，任务已结束的请按收尾规则关闭",
        "h_lead_gone": "--lead 指定的总指挥未运行：{lead}",
        "h_twice": "{name} 同时开了 {n} 份（{where}）：只留一个，它们写的是同一份对话记录",
        "h_plan_finished": "{lead} 的交付清单已全部合并，批次里也没有对话在运行：已不再显示；"
                           "用 admiral plan close --lead \"{lead}\" 收起它",
        "h_gone": "已登记但对话已结束：{who}（确认后 admiral done --who \"{who}\"）",
        "h_worktree_gone": "worktree 已不存在：{who} → {wt}",
        "h_pr_done": "{label}，但仍在登记中：{who}，可以收尾",
        "h_stale_phase": "阶段超过 {hours} 小时未更新：{who}（{phase}）",
        "x_gh": "gh 调用失败，本次未获取 PR/CI",
        "x_open_limit": "{n} 个打开的 PR 不在最新 {limit} 个之内，它们的 CI 状态无法显示",
        "x_broken": "{n} 个会话文件无法解析（可能是 Claude Code 内部格式变化或正在写入），已跳过",
        "x_shape": "{n} 个会话文件缺少 {fields} 中的字段：Claude Code 内部格式可能已变化，运行状态可能不准",
        "x_no_transcripts": "找不到任何对话记录文件（~/.claude/projects）：记录位置可能已变化，归属推断已失效",
        "x_no_messages": "对话记录里没有找到任何总指挥消息：会话间消息的记录格式可能已变化，归属推断可能失效；用 --lead 登记不受影响",
        "title": "Admiral 面板（{n} 个在运行{total}）", "progress": "，进度 {pct}%（{spread}）",
        "updated": "更新于 {t}，每分钟刷新；若距今超过 3 分钟，说明后台任务已停止，内容已过时。",
        "built": "本次命令当场生成于 {t}；后台任务另有一份，每分钟刷新。",
        "weights": "进度按里程碑折算：{weights}，一批取平均。", "x_head": "> ⚠ 数据源异常：{h}",
        "waiting_head": "## 待处理（{n}）", "none": "- 无", "teams_head": "## 各总指挥",
        "team_line": "- {lead}（{own}）：{pct}{how} · 成员 {n} 个 · 工作 {busy} · 待处理 {waiting} · CI 失败 {ci}",
        "live_members": "（在线成员）", "team_head": "## {lead}（{pct}；{how}）",
        "how_plan": "交付清单，合并 {done}/{n}", "how_live": "在线成员，未登记交付清单",
        "no_member_rows": "（暂无成员对话：执行对话登记时加 --lead，或收到过本总指挥的消息）",
        "independent": "## 独立对话（{n}，没有总指挥）", "close_head": "## 收尾（PR 合并后先收尾再关闭）",
        "close": "可以关闭", "wrapup": "待收尾后关闭", "confirm": "需要你确认", "close_none": "- 暂无可关闭的对话",
        "tidy": "## 待整理（{n}）",
        "cols": "| 对话 | 运行 | 里程碑 · 阶段 | 分支 | PR | CI | 最后提交 |",
        "item_cols": "| 交付物 | 分支 | 负责对话 | 里程碑 | PR | CI |",
        "unreg": "未登记", "nophase": "未报告阶段", "dir_gone": "目录不存在", "ago": "{age}前",
        "just_now": "刚刚", "waiting_line": "- {name}{lead}：{what}，{when}", "waiting_lead": "（{lead}）",
        "not_running": "未运行", "waiting_for": "等待输入",
    },
})


def ago(seconds, language):
    s = max(0, seconds)
    zh = language == "zh"
    if s < 3600:
        return f"{int(s // 60)}{'分' if zh else ' min'}"
    if s < 172800:
        return f"{int(s // 3600)}{'时' if zh else ' h'}"
    return f"{int(s // 86400)}{'天' if zh else ' d'}"


def since(seconds, language, T):
    """How long ago, for a line of text: "just now" under a minute."""
    return T["just_now"] if seconds < 60 else T["ago"].format(age=ago(seconds, language))


def first(cell):
    v = (cell or "").split(",")[0].strip()
    return "" if v in ("-", "(detached)") else v


def merged(pr):
    return bool(pr) and pr["state"] == "MERGED"


def stage_of(phase, pr, unknown=False):
    """`unknown`: GitHub did not answer this time, so finding no PR does not mean there is none."""
    # a PR is opened ready only once everything local is done (one push, straight to ready), so it outranks the
    # phases; a draft does not, and a session's `done` is its word against a PR GitHub has not merged
    if merged(pr):
        return 5
    if pr and pr["state"] == "OPEN" and not pr.get("isDraft"):
        return 4
    if phase == "done":
        return 3 if pr or unknown else 5
    if phase == "accepting":
        return 3
    if phase == "review":
        return 2
    return 1


def stage(reg, pr, unknown=False):
    """A registered session's milestone; 0 when it is not registered."""
    return stage_of(reg.get("phase"), pr, unknown) if reg else 0


def item_stage(owner_reg, pr, unknown=False):
    """A deliverable's milestone: 0 (not started) while it has neither a PR nor a registered owner."""
    if pr is None and not owner_reg:
        return 0
    return stage_of((owner_reg or {}).get("phase"), pr, unknown)


def pr_count(group):
    """(PRs merged, PRs counted) as GitHub has them: a plan counts its planned deliverables (one PR each, opened or
    not); without a plan, every PR its sessions' branches have (open or merged)."""
    if group.get("batch"):
        items = group["batch"]["items"]
        return sum((i["pr"] or {}).get("state") == "MERGED" for i in items), len(items)
    rows = group["members"] + ([group["leadRow"]] if group.get("leadRow") else [])  # a commander's pushed branches
    seen = {n: s for x in rows for n, s in x.get("prStates", {}).items() if s in ("OPEN", "MERGED")}
    return sum(s == "MERGED" for s in seen.values()), len(seen)


def counted(group):
    """What a group's progress counts: its plan's deliverables when it has one, else its members past not started."""
    return group["batch"]["items"] if group.get("batch") else [x for x in group["members"] if x["stage"]]


def dist(stages):
    out = [0] * len(STAGE_KEYS)
    for s in stages:
        out[s] += 1
    return out


def pct(d, weights):
    n = sum(d)
    return round(sum(weights[i] * k for i, k in enumerate(d)) / n) if n else None


def closing(x, locks, groups, now, cfg, T):
    """Whether a session can be closed: after its PR merged and it wrapped up. (verdict, reason), the verdict being
    close (wrapped up), wrapup (finished, cleanup left), confirm (the person decides) or keep."""
    if x["status"] in ("busy", "shell"):
        return "keep", T["working"]
    if x["status"] == "waiting":
        return "keep", T["waiting"]
    held = sorted(n for n, who in locks.items() if who == x["name"] or who.startswith(x["name"] + " "))
    pr = x["pr"]
    if pr and pr["state"] == "OPEN":  # a commander's own PR too
        return "keep", T["pr_open"]
    if x["prUnknown"]:
        return "keep", T["pr_unknown"]
    if x["isCommander"] and pr and pr["state"] == "CLOSED":
        return "confirm", T["pr_closed"]
    if x["isCommander"]:
        g = next((g for g in groups if g["lead"] == x["name"]), None)
        members = (g or {}).get("members") or []
        unfinished = [m for m in members if m.get("close") != "close"]  # members are judged before commanders
        if unfinished:
            if all(m.get("close") == "wrapup" for m in unfinished):
                return "keep", T["members_wrapup"].format(n=len(unfinished))
            return "keep", T["members"].format(n=len(unfinished))
        items = (g or {}).get("batch", {}).get("items", []) if g else []
        if any(i["stage"] != 5 for i in items):
            return "keep", T["plan_open"]
        reported = sum(i["reportedDone"] for i in items)
        if reported:
            return "confirm", T["plan_reported"].format(n=reported)
        if items:
            return "wrapup", T["plan_done"]
        if held:
            return "wrapup", T["locks"].format(n=len(held))
        if x["phase"] == "done":
            return "close", T["reported_done"]
        if members:
            return "close", T["members_done"].format(n=len(members))
        # no members is not the same as done: a commander may be planning, or deferred until others finish
        return "confirm", T["no_members"]
    if x["done"]:
        left = ([T["worktree"]] if x["worktree"] and not x["worktreeGone"] else []) + \
               ([T["holds"].format(n=len(held))] if held else []) + ([T["registered"]] if x["registered"] else [])
        if x["reportedDone"]:  # its own word is all there is: the person decides whether the work is over
            return "confirm", T["reported_only"] + (T["left"].format(what=", ".join(left)) if left else "")
        if left and left != [T["registered"]]:
            return "wrapup", T["merged_left"].format(what=", ".join(left))
        if not x["registered"]:
            return "close", T["deregistered_done"]
        return "close", T["merged_clean"] + (T["deregister"] if left else "")
    if pr and pr["state"] == "CLOSED":
        return "confirm", T["pr_closed"]
    if not x["registered"] and not pr and now - (x["statusSince"] or now) > cfg.idle_confirm_s:
        return "confirm", T["idle_unregistered"].format(age=ago(now - x["statusSince"], cfg.language))
    if held and x["status"] == "idle" and not x["registered"]:
        return "confirm", T["unregistered_locks"].format(n=len(held))
    return "keep", T["developing"]


def branches_of(cell):
    """Every branch a registration names (a session may own several, comma-separated)."""
    return [b.strip() for b in (cell or "").split(",") if b.strip() not in ("", "-", "(detached)")]


def remember(cfg, convs):
    """sessionId -> the last registration seen for that live session. A session that wrapped up deregisters;
    remembering what it worked on lets the board still tell it finished. Only live sessions are kept."""
    memory = registry.read_json(cfg.sub("reg-memory.json")) or {}
    fresh = {}
    for c in convs:
        r = c["reg"]
        if r:
            fresh[c["sessionId"]] = {"who": r["who"], "aka": registry.names_of(r)[1:], "branches": c["branches"],
                                     "worktree": first(r.get("worktree")),
                                     "lead": r.get("lead", ""), "phase": r.get("phase"),
                                     "registered": branches_of(r.get("branch"))}
        elif c["sessionId"] in memory:
            fresh[c["sessionId"]] = memory[c["sessionId"]]
    registry.write_json(cfg.sub("reg-memory.json"), fresh)
    return fresh


def build(cfg, use_gh=True, now=None, starts=sessions.proc_starts, fetch=github.prs_by_branch,
          commits=sessions.last_commit, fetch_mine=github.my_prs, checked_out=sessions.worktree_branch,
          worktrees=sessions.worktrees):
    now = time.time() if now is None else now
    T, W = TEXT[cfg.language], words(cfg.language)
    live, broken, shapeless, elsewhere = sessions.load(cfg, starts)
    regs, plans = registry.registrations(cfg), registry.plans(cfg)
    # Sessions outside the configured projects are not shown, but they run: a name running anywhere is never taken
    # for a session that ended, nor its batch for one with nobody of it running.
    running_elsewhere = {n for s in elsewhere for n in [s.get("name")] + [f.get("name") for f in s.get("formerNames") or []]
                         if n}
    # One conversation resumed in another terminal runs as another process, named in a hint. Processes alike in all
    # but their terminal are one session, shown as its most pressing process (waiting before working before idle, then
    # the latest change); those that differ in name or directory are rare and stay apart, so nothing of them is lost.
    by_sid = {}
    for s in live:
        by_sid.setdefault(s.get("sessionId") or f"pid {s['pid']}", []).append(s)
    live, open_twice = [], []
    for procs in by_sid.values():
        procs.sort(key=lambda s: (ORDER.get(s.get("status"), 9), -(s.get("statusUpdatedAt") or 0)))
        if len(procs) > 1:
            where = list(dict.fromkeys(p.get("_tty") or f"pid {p['pid']}" for p in procs))
            open_twice.append((procs[0].get("name") or procs[0].get("sessionId", "?")[:8], len(procs), where))
        alike = {}
        for p in procs:
            alike.setdefault((p.get("name"), p.get("cwd")), []).append(p)
        for same in alike.values():
            one = dict(same[0], _pids=[p["pid"] for p in same])  # a message may come from any of them
            one["formerNames"] = [f for p in same for f in p.get("formerNames") or []]  # as may an old registration
            live.append(one)
    # A registration its session made follows that session, whatever it is called now; one made without a session
    # (by hand, or for another session) is found by name, as before.
    by_session = {r["sessionId"]: r for r in regs if r.get("sessionId")}
    by_name = {}
    for r in regs:
        if not r.get("sessionId"):
            by_name.setdefault(r["who"], r)

    convs, matched = [], set()
    for s in live:
        name = s.get("name") or s.get("sessionId", "?")[:8]
        former = [f.get("name", "") for f in s.get("formerNames") or []]
        reg = by_session.get(s.get("sessionId")) or next((by_name[n] for n in [s.get("name") or ""] + former
                                                          if n in by_name), None)
        if reg:
            matched.add(reg["who"])
        convs.append({"name": name, "sessionId": s.get("sessionId", ""), "pid": s["pid"], "pids": s.get("_pids", [s["pid"]]),
                      "cwd": s.get("cwd", ""),
                      "tty": s.get("_tty", ""), "former": former, "status": s.get("status") or "?",
                      "statusSince": (s.get("statusUpdatedAt") or 0) / 1000, "waitingFor": s.get("waitingFor") or "",
                      "reg": reg, "isCommander": name.startswith(cfg.commander_prefix)})

    for c in convs:  # registered branches, plus whatever the registered worktree has checked out now
        r = c["reg"]
        bs = branches_of(r.get("branch")) if r else []
        now_on = checked_out(first(r.get("worktree"))) if r else ""
        c["branches"] = bs + ([now_on] if now_on and now_on not in bs and now_on not in ("main", "master") else [])
    kept = registry.read_json(cfg.sub("guessed.json")) or {}  # branches attached by work on earlier runs
    for c in convs:
        c["kept"] = [b for b in kept.get(c["sessionId"], []) if b not in c["branches"]]
        c["branches"] = c["branches"] + c["kept"]
    known = registry.read_json(cfg.sub("reg-memory.json")) or {}
    claimed = ({b for c in convs for b in c["branches"]} | {it["branch"] for p in plans for it in p["items"]}
               | {b for m in known.values() for b in m.get("branches", [])}) - {""}
    # A branch no session claims goes to the session that pushed it (its `git push` output says so), else, for a
    # worktree's branch, to the session that clearly did the work there (its edits and commands): a session that
    # moved on without re-registering still counts its PR. A branch is first taken this way only while its PR is
    # open (below), so branches merged long ago are never taken; once taken it stays (<state_dir>/guessed.json),
    # so the PR still counts after it merges.
    # Last, a branch a commander pushed (commanders often push for their members) counts for its batch.
    where = worktrees(cfg) if convs else {}
    work = sessions.work_in(cfg, convs, where.values()) if convs else {}
    leads = {c["sessionId"] for c in convs if c["isCommander"]}
    members = {sid: w for sid, w in work.items() if sid not in leads}
    guessed = {}
    for b in (set(where) | {b for w in work.values() for b in w["pushed"]}) - claimed - {"main", "master"}:
        sid = (sessions.pushed_by(members, b) or (sessions.owner_by_work(members, where[b]) if b in where else None)
               or sessions.pushed_by({s: work[s] for s in leads if s in work}, b))
        if sid:
            guessed.setdefault(sid, []).append(b)
    branches = claimed | {b for bs in guessed.values() for b in bs}
    prs, gh_ok, reused, mine = {}, None, False, None
    quiet = all(c["status"] not in ("busy", "shell", "waiting") and now - c["statusSince"] > cfg.quiet_s for c in convs)
    if use_gh and live and cfg.repo_dir:  # with no session running nothing reads the board, so GitHub is left alone
        # a registration whose session is not running keeps its branches in use, so their merges stay remembered
        in_use = branches | {b for r in regs for b in branches_of(r.get("branch"))}
        prs, mine, reused = github.prs_paced(cfg, in_use, quiet, now, fetch, fetch_mine)
        gh_ok = prs is not None and mine is not None
        prs = prs or {}
    unknown = gh_ok is False  # GitHub failed: a branch with no PR found may still have one
    for c in convs:
        new = [b for b in guessed.get(c["sessionId"], []) if (prs.get(b) or {}).get("state") == "OPEN"]
        c["branches"] = c["branches"] + new
        c["guessed"] = c["kept"] + new
    registry.write_json(cfg.sub("guessed.json"), {c["sessionId"]: c["guessed"] for c in convs if c["guessed"]})
    memory = remember(cfg, convs)

    inferred, read = sessions.infer_leads(cfg, convs) if convs else ({}, {"missing": 0, "read": 0, "found": False,
                                                                           "heard": {}})
    # Who waits for the person: Claude Code blocks the session (a prompt or a question), the session reported
    # needs_you, or (maybe) an idle session's last turn ended asking the person something.
    for c in convs:
        c["waitKind"], c["ask"] = "", ""
        if c["status"] == "waiting":
            c["waitKind"] = "blocked"
        elif c["status"] in ("busy", "shell"):
            continue
        elif c["reg"] and c["reg"].get("phase") == "needs_you":
            c["waitKind"], c["ask"] = "reported", c["reg"].get("note", "")
        elif c["statusSince"] and now - c["statusSince"] < cfg.ask_fresh_s:
            text = sessions.last_turn(sessions.transcript(cfg, c["cwd"], c["sessionId"]))
            if text and sessions.asks(text):
                c["waitKind"], c["ask"] = "maybe", sessions.tail(text)
    rows = []
    for c in convs:
        r = c["reg"]
        bs, wt = c["branches"], first(r.get("worktree")) if r else ""
        # A taken branch speaks for the session's stage only while its PR is open: its merged PR counts for the
        # batch, but must not make a session that went on to other work look finished.
        # A commander's taken branches are its members' work: they count for its batch, never as its own PR.
        own = [b for b in bs if b not in c["guessed"]
               or (not c["isCommander"] and (prs.get(b) or {}).get("state") == "OPEN")]
        pr, lead, finished = github.pick(own, prs), (r or {}).get("lead", ""), False
        mem = memory.get(c["sessionId"]) if not r else None
        # any branch it has, registered, taken, pushed or last registered, may have a PR GitHub did not report
        pr_unknown = unknown and bool(bs or (work.get(c["sessionId"]) or {}).get("pushed") or (mem or {}).get("branches"))
        st = stage(r, pr, pr_unknown)
        if mem:  # deregistered since: finished if what it last worked on reached the last milestone, as above
            mpr = github.pick(mem.get("branches", []), prs)
            if stage_of(mem.get("phase"), mpr, pr_unknown) == 5:
                finished, bs, pr, st, wt, lead = True, mem.get("branches", []), mpr, 5, mem.get("worktree", ""), mem.get("lead", "")
        ci_text, ci_level = github.ci(pr, cfg.summary_checks)
        lc = commits(wt) if wt else None
        status = "waiting" if c["waitKind"] else c["status"]
        rows.append({
            "name": c["name"], "sessionId": c["sessionId"], "tty": c["tty"], "isCommander": c["isCommander"],
            "lead": lead or ("" if c["isCommander"] else inferred.get(c["sessionId"], "")),
            "leadFrom": "registered" if lead else ("message" if inferred.get(c["sessionId"]) else ""),
            "stage": st, "done": st == 5, "reportedDone": st == 5 and not merged(pr), "finished": finished,
            "prUnknown": pr_unknown and not finished,
            "status": status, "claudeStatus": c["status"], "waitKind": c["waitKind"],
            "run": W["run"].get(status, status), "statusSince": c["statusSince"],
            "waitingFor": c["ask"] or c["waitingFor"], "registered": bool(r),
            "phase": (r or {}).get("phase"), "note": (r or {}).get("note", ""), "phaseAt": (r or {}).get("phaseAt"),
            "task": (r or {}).get("task", ""), "branch": (pr or {}).get("headRefName") or (bs[0] if bs else ""),
            "branches": bs, "guessedBranches": c["guessed"] if not finished else [], "prStates": {prs[b]["number"]: prs[b]["state"] for b in bs if b in prs},
            "pr": github.pr_label(pr, cfg.language), "ci": ci_text, "ciLevel": ci_level,
            "lastCommit": None if lc == "gone" else lc, "worktreeGone": lc == "gone", "worktree": wt,
        })
    rows.sort(key=lambda x: (ORDER.get(x["status"], 9), -(x["statusSince"] or 0)))

    commanders = [x for x in rows if x["isCommander"]]
    names = {x["name"] for x in commanders}
    alias = {f: c["name"] for c in convs if c["isCommander"] for f in c["former"]}
    groups = []
    for cmd in sorted(commanders, key=lambda x: x["name"]):
        members = [x for x in rows if not x["isCommander"] and alias.get(x["lead"], x["lead"]) == cmd["name"]]
        groups.append({"lead": cmd["name"], "leadRow": cmd, "members": members})
    orphans = sorted({x["lead"] for x in rows if x["lead"] and not x["isCommander"]
                      and alias.get(x["lead"], x["lead"]) not in names})
    for lead in orphans:
        groups.append({"lead": lead, "leadRow": None,
                       "members": [x for x in rows if not x["isCommander"] and x["lead"] == lead]})
    unassigned = [x for x in rows if not x["isCommander"] and not x["lead"]]

    reg_by_who = {}  # by the name each is under, then the names it was under before
    for r in regs:
        reg_by_who.setdefault(r["who"], r)
    for r in regs:
        for n in registry.names_of(r)[1:]:
            reg_by_who.setdefault(n, r)
    finished = []  # plans of batches over, with nobody of them running: not shown, left to `admiral plan close`
    # a planned PR's owner may run ungrouped, or outside the projects
    running = {n for c in convs for n in [c["name"]] + c["former"]} | running_elsewhere
    heard = set(read["heard"].values())  # commanders a running session last heard from, gone or not
    mem_by_who = {}  # owners that deregistered since, by the name each registered under and its session's name now
    for c in convs:
        m = memory.get(c["sessionId"])
        for n in ({m.get("who"), c["name"], *(m.get("aka") or [])} if m else set()) - {None, ""}:
            mem_by_who.setdefault(n, []).append(m)
    for p in plans:
        lead = alias.get(p["lead"], p["lead"])
        g = next((g for g in groups if g["lead"] == lead), None)  # None: neither the commander nor a member runs
        items = []
        for it in p["items"]:
            pr = prs.get(it["branch"])
            ci_text, ci_level = github.ci(pr, cfg.summary_checks)
            owner = it.get("owner", "")
            # an owner's last registration speaks only for the branches it named
            mem = next((m for m in mem_by_who.get(owner, []) if it["branch"] in m.get("registered", m.get("branches", []))), None)
            st = item_stage(reg_by_who.get(owner) or mem, pr, unknown)
            items.append({"branch": it["branch"], "title": it.get("title", ""), "owner": it.get("owner", ""),
                          "stage": st, "reportedDone": st == 5 and not merged(pr),
                          "pr": github.pr_label(pr, cfg.language), "ci": ci_text, "ciLevel": ci_level})
        # of the batch: its owners, its commander, and the sessions registered under it, wherever they run
        ours = {i["owner"] for i in items} | {p["lead"], lead} | {r["who"] for r in regs if r.get("lead") in (p["lead"], lead)}
        if g is None and items and all((i["pr"] or {}).get("state") == "MERGED" for i in items) \
                and not ours & running and p["lead"] not in heard and lead not in heard:
            # the batch is over: every deliverable merged, and nobody of it runs. It leaves the board rather than show
            # its commander not running; its plan is the commander's or the person's to close, never the board's
            finished.append(p["lead"])
            continue
        if g is None:  # the commander is not running and the batch is not over: its plan still counts
            g = {"lead": lead, "leadRow": None, "members": []}
            groups.append(g)
        g["batch"] = {"items": items}

    for g in groups:
        m, bt, counts = g["members"], g.get("batch"), counted(g)
        d = dist([x["stage"] for x in counts])
        merged_prs, all_prs = pr_count(g)
        g["summary"] = {"total": len(m), "done": sum(x["done"] for x in m), "dist": d, "pct": pct(d, cfg.weights),
                        "reported": sum(x["reportedDone"] for x in counts),
                        "items": len(bt["items"]) if bt else 0, "prsMerged": merged_prs, "prs": all_prs,
                        "itemsDone": sum(i["stage"] == 5 for i in bt["items"]) if bt else 0,
                        "busy": sum(x["status"] in ("busy", "shell") for x in m),
                        "waiting": sum(x["status"] == "waiting" for x in m),
                        "ciFail": sum(x["ciLevel"] == "fail" for x in m)}

    locks = sessions.lock_holders(cfg)
    for x in sorted(rows, key=lambda x: x["isCommander"]):  # members first: a commander is judged by them
        x["close"], x["closeWhy"] = closing(x, locks, groups, now, cfg, T)
    closable = {v: [{"name": x["name"], "lead": x["lead"], "tty": x["tty"], "why": x["closeWhy"]}
                    for x in rows if x["close"] == v] for v in ("close", "wrapup", "confirm")}

    hints = [T["h_unregistered"].format(name=x["name"]) for x in rows if not x["registered"] and not x["finished"]]
    if mine:
        linked = {b for x in rows for b in x["branches"]} | {it["branch"] for p in plans for it in p["items"]}
        for p in mine["open"]:
            if p["headRefName"] not in linked:
                wt = where.get(p["headRefName"])
                hints.append(T["h_unlinked"].format(n=p["number"], branch=p["headRefName"],
                                                    where=T["checked_out"].format(wt=wt) if wt else ""))
    for x in rows:
        for b in x["guessedBranches"]:
            if b in prs and prs[b]["state"] == "OPEN":  # once merged, re-registering no longer matters
                hints.append(T["h_lead_pushed" if x["isCommander"] else "h_guessed"].format(
                    n=prs[b]["number"], branch=b, name=x["name"]))
    for c in convs:
        r = c["reg"]
        if r and r["who"] != c["name"] and not r.get("sessionId"):  # one that follows its session needs nothing
            hints.append(T["h_renamed"].format(old=r["who"], new=c["name"]))
        if c["status"] == "idle" and c["statusSince"] and now - c["statusSince"] > cfg.idle_flag_s:
            hints.append(T["h_idle"].format(days=cfg.idle_flag_s // 86400, name=c["name"]))
    hints += [T["h_lead_gone"].format(lead=lead) for lead in orphans]
    hints += [T["h_twice"].format(name=name, n=n, where=", ".join(where)) for name, n, where in open_twice]
    hints += [T["h_plan_finished"].format(lead=lead) for lead in finished]
    live_ids = {s.get("sessionId") for s in live + elsewhere}
    for r in regs:
        # its session has ended: by its session when it records one, else by its name, wherever sessions run
        ended = r["sessionId"] not in live_ids if r.get("sessionId") else \
            r["who"] not in matched and r["who"] not in running_elsewhere
        if ended:
            hints.append(T["h_gone"].format(who=r["who"]))
            continue
        wt = first(r.get("worktree"))
        if wt and not os.path.isdir(wt):
            hints.append(T["h_worktree_gone"].format(who=r["who"], wt=wt))
        pr = github.pick(branches_of(r.get("branch")), prs)
        if pr and pr["state"] in ("MERGED", "CLOSED"):
            hints.append(T["h_pr_done"].format(label=github.pr_label(pr, cfg.language)["label"], who=r["who"]))
        if r.get("phase") not in (None, "paused", "done") and r.get("phaseAt") and now - r["phaseAt"] > cfg.stale_phase_s:
            hints.append(T["h_stale_phase"].format(hours=cfg.stale_phase_s // 3600, who=r["who"],
                                                   phase=W["phases"].get(r["phase"], r["phase"])))

    # Problems with the sources themselves: every other number depends on them, so they are shown apart.
    health = []
    if gh_ok is False:
        health.append(T["x_gh"])
    unknown = sum(bool(p.get("checksUnknown")) for p in prs.values())
    if unknown:
        health.append(T["x_open_limit"].format(n=unknown, limit=github.OPEN_LIMIT))
    if broken:
        health.append(T["x_broken"].format(n=broken))
    if shapeless:
        health.append(T["x_shape"].format(n=shapeless, fields="/".join(sessions.FIELDS)))
    workers = [c for c in convs if not c["isCommander"]]
    if workers and read["missing"] == len(workers):
        health.append(T["x_no_transcripts"])
    elif commanders and workers and read["read"] and not read["found"] \
            and not any(c["reg"] and c["reg"].get("lead") for c in workers):
        health.append(T["x_no_messages"])

    overall = [x for g in groups for x in counted(g)] + [x for x in unassigned if x["stage"]]
    total = dist([x["stage"] for x in overall])
    solo = pr_count({"members": unassigned})
    return {"generated": now, "gh": gh_ok, "ghReused": reused, "count": len(rows), "language": cfg.language,
            "commanderPrefix": cfg.commander_prefix, "playbookReminder": cfg.playbook_remind,
            "words": W, "weights": cfg.weights, "green": {"faint": [52, 84, 64], "full": [63, 185, 80]},
            "dist": total, "pct": pct(total, cfg.weights), "reported": sum(x["reportedDone"] for x in overall),
            "waiting": [x for x in rows if x["status"] == "waiting"],
            "prsMerged": sum(g["summary"]["prsMerged"] for g in groups) + solo[0],
            "prs": sum(g["summary"]["prs"] for g in groups) + solo[1],
            "mine": {"open": len(mine["open"]), "mergedToday": len(mine["mergedToday"])} if mine else None,
            "groups": groups, "unassigned": unassigned, "closable": closable, "health": health, "hints": hints}


def cell(s):
    return str(s).replace("|", "/").replace("\n", " ")


def spread(d, W, reported=0):
    """How many at each milestone, the furthest first; of the last, those there only by their own report apart."""
    out = []
    for i, n in reversed(list(enumerate(d))):
        if i == len(d) - 1 and reported:
            out += [f"{W['stages'][i]} {n - reported}"] if n > reported else []
            out.append(f"{W['reported_done']} {reported}")
        elif n:
            out.append(f"{W['stages'][i]} {n}")
    return " · ".join(out)


def stage_word(x, W):
    return W["reported_done"] if x.get("reportedDone") else W["stages"][x["stage"]]


def markdown(b, live=False):
    """The board as Markdown; `live` when it was built for this one command rather than read from the snapshot."""
    lang = b["language"]
    T, W, S = TEXT[lang], b["words"], b["words"]["stages"]
    now = b["generated"]

    def table(rows):
        out = [T["cols"], "|---|---|---|---|---|---|---|"]
        for x in rows:
            if x["finished"]:  # deregistered after finishing: its last registration says how
                ph = stage_word(x, W)
            elif not x["registered"]:
                ph = T["unreg"]
            elif x["phase"]:
                ph = f"{stage_word(x, W)} · {W['phases'].get(x['phase'], x['phase'])} {x['note']}".rstrip()
            else:
                ph = f"{stage_word(x, W)} · {T['nophase']}"
            commit = T["dir_gone"] if x["worktreeGone"] else (
                T["ago"].format(age=ago(now - x["lastCommit"], lang)) if x["lastCommit"] else "-")
            out.append("| " + " | ".join(cell(v) for v in [
                x["name"], f"{x['run']} {ago(now - x['statusSince'], lang)}", ph, x["branch"] or "-",
                (x["pr"] or {}).get("label", "-"), x["ci"] or "-", commit]) + " |")
        return out

    total = T["progress"].format(pct=b["pct"], spread=spread(b["dist"], W, b["reported"])) if sum(b["dist"]) else ""
    weights = ("、" if lang == "zh" else ", ").join(f"{s} {w}%" for s, w in zip(S[1:], b["weights"][1:]))
    out = [f"# {T['title'].format(n=b['count'], total=total)}", ""]
    out += [T["x_head"].format(h=h) for h in b["health"]] + ([""] if b["health"] else [])
    out += [T["built" if live else "updated"].format(t=time.strftime("%H:%M:%S", time.localtime(now))) + ("" if lang == "zh" else " ")
            + T["weights"].format(weights=weights),
            "", T["waiting_head"].format(n=len(b["waiting"]))]
    out += [T["waiting_line"].format(name=x["name"], lead=T["waiting_lead"].format(lead=x["lead"]) if x["lead"] else "",
                                     what=x["waitingFor"] or T["waiting_for"], when=since(now - x["statusSince"], lang, T))
            for x in b["waiting"]] or [T["none"]]
    out += ["", T["teams_head"]]
    for g in b["groups"]:
        s = g["summary"]
        own = f"{g['leadRow']['run']} {ago(now - g['leadRow']['statusSince'], lang)}" if g["leadRow"] else T["not_running"]
        p = f"{s['pct']}% ({spread(s['dist'], W, s['reported'])})" if s["pct"] is not None else "-"
        out.append(T["team_line"].format(lead=g["lead"], own=own, pct=p, how="" if g.get("batch") else T["live_members"],
                                         n=s["total"], busy=s["busy"], waiting=s["waiting"], ci=s["ciFail"]))
    if not b["groups"]:
        out.append(T["none"])
    for g in b["groups"]:
        s = g["summary"]
        how = T["how_plan"].format(done=s["prsMerged"], n=s["items"]) if g.get("batch") else T["how_live"]
        out += ["", T["team_head"].format(lead=g["lead"], pct=f"{s['pct']}%" if s["pct"] is not None else "-", how=how)]
        if g.get("batch"):
            out += [T["item_cols"], "|---|---|---|---|---|---|"]
            out += ["| " + " | ".join(cell(v) for v in [it["title"] or "-", it["branch"], it["owner"] or "-",
                                                         stage_word(it, W), (it["pr"] or {}).get("label", "-"),
                                                         it["ci"] or "-"]) + " |" for it in g["batch"]["items"]]
            out.append("")
        out += table(g["members"]) if g["members"] else [T["no_member_rows"]]
    if b["unassigned"]:
        out += ["", T["independent"].format(n=len(b["unassigned"]))] + table(b["unassigned"])
    out += ["", T["close_head"]]
    c = b["closable"]
    for k in ("close", "wrapup", "confirm"):
        out += [f"- {T[k]}: {x['name']}{' (' + x['lead'] + ')' if x['lead'] else ''}, {x['why']}" for x in c[k]]
    if not any(c.values()):
        out.append(T["close_none"])
    out += ["", T["tidy"].format(n=len(b["hints"]))] + [f"- {h}" for h in b["hints"]] + ([T["none"]] if not b["hints"] else [])
    return "\n".join(out) + "\n"


def write(cfg, b):
    os.makedirs(cfg.state_dir, exist_ok=True)
    for name, text in (("board.json", sessions.json_dump(b)), ("board.md", markdown(b))):
        p, tmp = cfg.sub(name), cfg.sub(f"{name}.{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, p)
