"""The words Admiral shows, in English and Chinese. The board snapshot carries the chosen table, so the status line
and the sidebar draw the same words without a table of their own."""

import re

# A count's noun in English: "{n} {n:session|sessions}" says "1 session" and "2 sessions". The plugin resolves the same
# form (register.tsx fmt), so a phrase reads right wherever it is drawn.
PLURAL = re.compile(r"\{(\w+):([^|{}]*)\|([^{}]*)\}")


class Phrase(str):
    """A word-table string whose .format also picks singular or plural forms."""

    def format(self, *args, **kwargs):
        text = PLURAL.sub(lambda m: m.group(2) if str(kwargs.get(m.group(1))) == "1" else m.group(3), self)
        return str.format(text, *args, **kwargs)


def phrases(table):
    if isinstance(table, dict):
        return {k: phrases(v) for k, v in table.items()}
    if isinstance(table, list):
        return [phrases(v) for v in table]
    return Phrase(table) if isinstance(table, str) else table


# Milestones, in order: 0 is a planned deliverable not started yet, 5 is merged.
STAGE_KEYS = ["not_started", "develop", "review", "accept", "ci", "merged"]

# Phases a session reports with `admiral state`. The keys are stored; either language's name is accepted.
PHASE_KEYS = ["working", "waiting", "needs_you", "review", "accepting", "paused", "done"]

WORDS = {
    "en": {
        "stages": ["not started", "develop", "review", "accept", "CI", "merged"],
        "phases": {"working": "working", "waiting": "waiting", "needs_you": "needs you", "review": "in review",
                   "accepting": "accepting", "paused": "paused", "done": "done"},
        "maybe_waiting": "may be waiting for you: ", "reported_waiting": "needs you: ",
        "github_prs": "GitHub PRs: {open} open · {merged} merged today", "prs_merged": "PRs merged {done}/{n}",
        "overall": "progress", "no_owner": "no owner", "no_terminal": "no terminal found for {name}",
        "no_tab": "no terminal tab found for {name} ({tty})", "pane_closed": "Admiral board hidden.",
        "pane_opened": "Admiral board shown.", "pane_waits": "Admiral board opened; it docks on the right once the terminal is 110 columns wide.",
        "command_desc": "Show or hide the Admiral board on the right", "loading": "waiting for the background job's first refresh",
        "short_min": "{n}m", "short_h": "{n}h", "short_d": "{n}d",
        "run": {"busy": "working", "shell": "running a command", "waiting": "waiting for you", "idle": "idle"},
        "waiting": "waiting for you", "working": "working", "idle": "idle", "sessions": "sessions",
        "total": "{n} {n:session|sessions}", "members": "{n} {n:member|members}", "merged": "merged {done}/{n}",
        "no_progress": "no progress yet", "no_plan": "estimated from running members", "ci": "CI", "closable": "closable {n}",
        "stale": "data {age} old: the background job may have stopped", "unreadable": "cannot read the board",
        "health": "source problem {n}", "updated": "updated {t}", "independent": "independent sessions",
        "idle_commanders": "{n} more {n:commander|commanders} without members", "to_tidy": "to tidy {n}",
        "show": "show", "hide": "hide", "close_head": "wrap-up", "can_close": "can close",
        "wrap_up": "wrap up first", "confirm": "for you to confirm", "deliverables": "planned PRs",
        "other_sessions": "other sessions", "now": "working", "just_now": "just now",
        "min_ago": "{n} min ago", "h_ago": "{n} h ago", "d_ago": "{n} d ago", "open_board": "Admiral board",
        "your_team": "this batch", "this_session": "this session", "lead_of": "under {lead}",
        "unregistered": "not registered", "no_phase": "no phase reported", "not_running": "not running",
        "commander_gone": "commander not running", "more_commanders": "{n} more {n:commander|commanders}: /admiral shows all",
    },
    "zh": {
        "stages": ["未开始", "开发", "审查", "验收", "CI", "合并"],
        "phases": {"working": "进行中", "waiting": "等待", "needs_you": "等你", "review": "审查中",
                   "accepting": "验收中", "paused": "暂停", "done": "完成"},
        "maybe_waiting": "可能在等你：", "reported_waiting": "等你：",
        "github_prs": "GitHub PR：开着 {open} · 今天合并 {merged}", "prs_merged": "PR 已合并 {done}/{n}",
        "overall": "总进度", "no_owner": "未指定负责对话", "no_terminal": "未找到「{name}」所在的终端",
        "no_tab": "未找到「{name}」所在的终端标签页（{tty}）", "pane_closed": "Admiral 面板已收起。",
        "pane_opened": "Admiral 面板已展开。", "pane_waits": "Admiral 面板已打开，终端宽度达到 110 列后显示在右侧。",
        "command_desc": "展开或收起右侧的 Admiral 面板", "loading": "等待后台任务完成首次刷新",
        "short_min": "{n}分", "short_h": "{n}时", "short_d": "{n}天",
        "run": {"busy": "工作", "shell": "执行命令", "waiting": "待处理", "idle": "空闲"},
        "waiting": "待处理", "working": "工作", "idle": "空闲", "sessions": "对话",
        "total": "共 {n} 对话", "members": "成员 {n}", "merged": "已合并 {done}/{n} 项",
        "no_progress": "暂无进度", "no_plan": "按在线成员估算", "ci": "CI", "closable": "可关闭 {n}",
        "stale": "数据已 {age}未更新，后台任务可能已停止", "unreadable": "无法读取面板数据",
        "health": "数据源异常 {n}", "updated": "更新于 {t}", "independent": "独立对话",
        "idle_commanders": "另有 {n} 个总指挥暂无成员", "to_tidy": "待整理 {n} 项",
        "show": "查看", "hide": "收起", "close_head": "收尾", "can_close": "可以关闭",
        "wrap_up": "待收尾后关闭", "confirm": "需要你确认", "deliverables": "计划中的 PR",
        "other_sessions": "其他对话", "now": "工作中", "just_now": "刚才",
        "min_ago": "{n} 分钟前", "h_ago": "{n} 小时前", "d_ago": "{n} 天前", "open_board": "Admiral 面板",
        "your_team": "本批次", "this_session": "本对话", "lead_of": "所属 {lead}",
        "unregistered": "未登记", "no_phase": "未报告阶段", "not_running": "未运行",
        "commander_gone": "总指挥未运行", "more_commanders": "另有 {n} 个总指挥，可用 /admiral 查看全部",
    },
}

# Names a phase may be given by, in either language, to its stored key.
PHASE_ALIASES = {**{k: k for k in PHASE_KEYS},
                 **{name: k for table in WORDS.values() for k, name in table["phases"].items()},
                 "进行中": "working", "等待": "waiting", "等你": "needs_you", "Codex审查": "review", "审查": "review",
                 "验收中": "accepting", "暂停": "paused", "完成": "done"}


WORDS = phrases(WORDS)


def words(language):
    return WORDS.get(language, WORDS["en"])


def phase_key(name):
    """The stored key for a phase given in either language, or None."""
    return PHASE_ALIASES.get(name)
