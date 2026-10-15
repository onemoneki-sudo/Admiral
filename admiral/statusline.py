"""The Claude Code status line: the one set before (config `[statusline] base`, for example claude-hud), then
Admiral's lines in the same style. Reads only the board snapshot; calls no GitHub and no model.

    "statusLine": {"type": "command", "command": "admiral statusline", "refreshInterval": 20}

- Line 1, every session: overall progress, the sessions broken down into waiting / working / idle, CI failures,
  sessions that can close, source problems.
- One line per commander with a team or a plan (those needing attention first, at most TEAMS): its progress bar,
  its members, CI; the commander reading it sees its own marked ▸.
- In a registered session that is not a commander (found by its session_id): its own milestone, PR and CI.
"""

import json
import os
import re
import subprocess
import sys
import time
import unicodedata

from .words import phrases

STALE_S = 180
DEFAULT_STATE = "~/.local/state/admiral"  # where scripts/refresh.sh reports a job that could not start (config.py's default)
BAR = 10
TEAMS = 5
RESET, DIM = "\x1b[0m", "\x1b[2m"
RED, GREEN, YELLOW, ORANGE = "\x1b[31m", "\x1b[32m", "\x1b[33m", "\x1b[38;5;208m"
SEP = f" {DIM}│{RESET} "
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def c(color, text):
    return f"{color}{text}{RESET}"


def width(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in ANSI.sub("", s))


def fit(line, cols):
    """Cut a colored line to `cols` cells, keeping its escape codes whole."""
    if width(line) <= cols:
        return line
    out, used = "", 0
    for part in re.split(r"(\x1b\[[0-9;]*m)", line):
        if ANSI.fullmatch(part or "x"):
            out += part
            continue
        for ch in part:
            w = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
            if used + w > cols - 1:
                return out + "…" + RESET
            out, used = out + ch, used + w
    return out + RESET


def pad(text, cells):
    return text + " " * max(0, cells - width(text))


def columns():
    v = os.environ.get("COLUMNS", "")
    if not v.isdigit():
        try:
            with open("/dev/tty") as tty:
                v = subprocess.run(["stty", "size"], stdin=tty, capture_output=True, text=True).stdout.split()[1]
        except (OSError, IndexError):
            v = "120"
    return max(20, int(v) - 4)


class Lines:
    def __init__(self, b):
        self.b, self.W = b, phrases(b["words"])  # the snapshot's words, with their singular/plural forms
        g = b.get("green") or {}
        self.faint, self.full = tuple(g.get("faint", (52, 84, 64))), tuple(g.get("full", (63, 185, 80)))

    def shade(self, t):
        r, g, b = (round(a + (z - a) * t) for a, z in zip(self.faint, self.full))
        return f"\x1b[38;2;{r};{g};{b}m"

    def bar(self, p, merged=None, n=None):
        """Cells deepen from faint to full green left to right; then the percentage, and how many PRs merged."""
        if p is None:
            return c(DIM, self.W["no_progress"])
        filled = round(BAR * p / 100)
        cells = "".join(f"{self.shade((i + 1) / BAR)}█" for i in range(filled))
        prs = c(DIM, "  " + self.W["prs_merged"].format(done=merged, n=n)) if n else ""  # no PR yet: nothing to count
        return f"{cells}{RESET}{DIM}{'░' * (BAR - filled)}{RESET} {p:>3}%" + prs

    def pips(self, stage, reported=False):
        """Filled to the milestone; reported done fills the last one dim, as the session's word, not a merge."""
        lit = stage - 1 if reported else stage
        return ("".join(f"{self.shade((i + 1) / 5)}▰" for i in range(lit)) + (f"{RESET}{DIM}▰" if reported else "")
                + f"{RESET}{DIM}{'▱' * (5 - stage)}{RESET}")

    def count(self, n, mark, word, color):
        return c(color if n else DIM, f"{mark} {n} {word}")

    def breakdown(self, lead, waiting, busy, total, who=""):
        """`who`: the names of the sessions waiting, shown right after their count."""
        idle = max(0, total - waiting - busy)
        parts = [self.count(waiting, "◆", self.W["waiting"], YELLOW) + who,
                 self.count(busy, "●", self.W["working"], GREEN), c(DIM, f"○ {idle} {self.W['idle']}")]
        return c(DIM, lead + (": " if self.b.get("language") != "zh" else "：")) + c(DIM, " · ").join(parts)

    def ci_count(self, n):
        return f"{RED}✗{RESET}{DIM} {n} {self.W['ci']}{RESET}" if n else c(DIM, f"✗ 0 {self.W['ci']}")

    def render(self, session_id, cols=None):
        """The lines; with `cols`, a first line too wide drops the waiting sessions' names before anything else."""
        b, W = self.b, self.W
        label = c(ORANGE, "Admiral")
        rows = [x for g in b["groups"] for x in ([g["leadRow"]] if g["leadRow"] else []) + g["members"]] + b["unassigned"]
        waiting = [x for x in rows if x["status"] == "waiting"]
        busy = sum(x["status"] in ("busy", "shell") for x in rows)
        zh = b.get("language") == "zh"
        names = ("、" if zh else ", ").join(x["name"] for x in waiting[:3]) + ("…" if len(waiting) > 3 else "")
        who = c(YELLOW, ("（" if zh else " (") + names + ("）" if zh else ")")) if waiting else ""
        d = b["dist"]
        if b.get("mine") is not None:  # the person's own PRs as GitHub has them, whatever the registrations say
            head = ([self.bar(b["pct"])] if sum(d) else []) + [
                c(DIM, W["github_prs"].format(open=b["mine"]["open"], merged=b["mine"]["mergedToday"]))]
        else:
            head = [self.bar(b["pct"], b.get("prsMerged", 0), b.get("prs", 0))] if sum(d) else []
        tail = [self.ci_count(sum(x["ciLevel"] == "fail" for x in rows))]
        if b["closable"]["close"]:
            tail.append(c(GREEN, W["closable"].format(n=len(b["closable"]["close"]))))
        if b["health"]:
            tail.append(c(RED, "⚠ " + W["health"].format(n=len(b["health"]))))
        first = [label + "  " + SEP.join(head + [self.breakdown(W["total"].format(n=len(rows)), len(waiting), busy, len(rows), w)]
                                         + tail) for w in (who, "")]
        lines = [first[0] if cols is None or width(first[0]) <= cols else first[1]]

        me = next((x for x in rows if x.get("sessionId") and x["sessionId"] == session_id), None)
        teams = [g for g in b["groups"] if g["summary"]["total"] or g.get("batch")]
        teams.sort(key=lambda g: (-g["summary"]["waiting"], -g["summary"]["ciFail"], g["lead"]))
        prefix = b.get("commanderPrefix", "")
        names = {g["lead"]: (g["lead"][len(prefix):].lstrip("-_ ") if prefix and g["lead"].startswith(prefix) else g["lead"]) or g["lead"]
                 for g in teams}
        cells = min(14, max((width(n) for n in names.values()), default=0))
        for g in teams[:TEAMS]:
            s = g["summary"]
            mine = me is not None and me["isCommander"] and me["name"] == g["lead"]
            name = names[g["lead"]] if width(names[g["lead"]]) <= cells else fit(names[g["lead"]], cells)
            head = (c(ORANGE, "▸ ") if mine else "  ") + (c(ORANGE, pad(name, cells)) if mine else pad(name, cells))
            parts = [self.bar(s["pct"], s.get("prsMerged", 0), s.get("prs", 0))]
            if s["total"]:
                parts.append(self.breakdown(W["members"].format(n=s["total"]), s["waiting"], s["busy"], s["total"]))
            if s["ciFail"]:
                parts.append(self.ci_count(s["ciFail"]))
            if not g.get("leadRow"):
                parts.append(c(RED, W["commander_gone"]))
            lines.append(head + "  " + SEP.join(parts))
        if len(teams) > TEAMS:
            lines.append(c(DIM, "  " + W["more_commanders"].format(n=len(teams) - TEAMS)))

        if me and not me["isCommander"] and (me["registered"] or me.get("finished")):
            st = me.get("stage") or 0
            word = W["reported_done"] if me.get("reportedDone") else W["stages"][st]
            parts = [self.pips(st, me.get("reportedDone")) + " " + word + (f" {me['note']}" if me.get("note") else "")]
            if me.get("pr"):
                parts.append(me["pr"]["label"])
            if me["ciLevel"] == "fail":
                parts.append(f"{DIM}{W['ci']} {RESET}{RED}✗{RESET}")
            tail = c(DIM, "  · " + W["lead_of"].format(lead=me["lead"])) if me.get("lead") else ""
            lines.append(c(DIM, W["this_session"]) + "  " + SEP.join(parts) + tail)
        elif me and not me["isCommander"]:
            lines.append(c(DIM, f"{W['this_session']}  {W['unregistered']}"))
        return lines


def job_error(state_dir):
    """The last line the background job wrote to last-error.txt, in the state directory or, when it could not even
    start, in the default one (scripts/refresh.sh); "" when it went well."""
    for d in dict.fromkeys([state_dir, os.path.expanduser(DEFAULT_STATE)]):
        try:
            with open(os.path.join(d, "last-error.txt"), encoding="utf-8") as fh:
                err = [ln.strip() for ln in fh if ln.strip()]
        except OSError:
            continue
        if err:
            return err[-1][:160]
    return ""


def no_board(state_dir):
    """Why there is no board: the background job's last error when it has one, else how to start it."""
    err = job_error(state_dir)
    if err:
        return f"the background job fails: {err}"
    return "no board yet: run scripts/install.sh (it starts the background job), or `admiral board --write` every minute"


def admiral_lines(board_file, session_id, now=None, cols=None):
    try:
        with open(board_file, encoding="utf-8") as fh:
            b = json.load(fh)
    except (OSError, ValueError):
        return [f"{c(ORANGE, 'Admiral')}  {c(RED, no_board(os.path.dirname(board_file)))}"]
    age = (now or time.time()) - b["generated"]
    if age > STALE_S:
        mins = int(age // 60)
        err = job_error(os.path.dirname(board_file))
        why = f" ({err})" if err else ""
        return [f"{c(ORANGE, 'Admiral')}  {c(RED, b['words']['stale'].format(age=b['words']['min_ago'].format(n=mins)) + why)}"]
    return Lines(b).render(session_id, cols)


def main(cfg):
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
    out = []
    if cfg.statusline_base:
        try:
            r = subprocess.run(["/bin/sh", "-c", cfg.statusline_base], input=raw, capture_output=True, text=True, timeout=5)
            if r.stdout.strip():
                out.append(r.stdout.rstrip("\n"))
        except subprocess.TimeoutExpired:
            pass
    cols = columns()
    out += [fit(line, cols) for line in admiral_lines(cfg.sub("board.json"), data.get("session_id"), cols=cols)]
    sys.stdout.write("\n".join(out) + "\n")
