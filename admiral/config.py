"""Admiral's configuration.

Read from ~/.config/admiral/config.toml, or the file $ADMIRAL_CONFIG names. Every key is optional; with no file at
all Admiral shows every Claude Code session on the machine and reads no GitHub.

    state_dir = "~/.local/state/admiral"   # registrations, plans, the board snapshot, caches
    language = "en"                         # "en" or "zh": the words the board, status line and sidebar use

    [sessions]
    project_dirs = ["~/code/myapp"]         # show only sessions whose working directory starts with one of these
    commander_prefix = "Commander"          # a session whose name starts with this is a commander

    [github]
    repo_dir = "~/code/myapp"               # where `gh` runs to read PRs and checks; empty: no PR or CI
    summary_checks = []                     # CI jobs that only sum up others: named only when nothing else failed

    [locks]
    dir = ""                                # the lock tool's directory; empty: <state_dir>/locks
    commanders = ""                         # who may reorder a waiting line, one session name per line;
                                            # empty: <state_dir>/lock-commanders.txt

    [statusline]
    base = ""                               # the status line command to run first (claude-hud, for example)

    [playbook]
    remind = true                           # a short reminder in every session's system prompt of which playbook
                                            # skill to read when; false where the project's own rules do that job

    [progress]                              # what each milestone is worth, in percent
    develop = 25
    review = 50
    accept = 70
    ci = 80
    merged = 100
"""

import copy
import hashlib
import os
import re
import tomllib

DEFAULTS = {
    "state_dir": "~/.local/state/admiral",
    "language": "en",
    "sessions": {
        "dir": "~/.claude/sessions",  # Claude Code's registry of running sessions
        "projects_dir": "~/.claude/projects",  # Claude Code's transcripts
        "project_dirs": [],
        "commander_prefix": "Commander",
    },
    "github": {"repo_dir": "", "summary_checks": []},
    "locks": {"dir": "", "commanders": ""},
    "statusline": {"base": ""},
    "playbook": {"remind": True},
    "progress": {"develop": 25, "review": 50, "accept": 70, "ci": 80, "merged": 100},
    "pacing": {"quiet_minutes": 30, "quiet_github_minutes": 15},
    "closing": {"idle_confirm_hours": 24, "idle_flag_days": 3, "stale_phase_hours": 24},
    "waiting": {"ask_fresh_hours": 12},  # an idle session's last ask older than this is no longer offered as waiting
}


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def path(p):
    return os.path.abspath(os.path.expanduser(p)) if p else ""


class Config:
    def __init__(self, data):
        self.data = data
        self.state_dir = path(data["state_dir"])
        self.language = data["language"] if data["language"] in ("en", "zh") else "en"
        s = data["sessions"]
        self.sessions_dir = path(s["dir"])
        self.projects_dir = path(s["projects_dir"])
        self.project_dirs = [path(p) for p in s["project_dirs"]]
        self.commander_prefix = s["commander_prefix"]
        self.repo_dir = path(data["github"]["repo_dir"])
        self.summary_checks = tuple(data["github"]["summary_checks"])
        self.locks_dir = path(data["locks"]["dir"]) or os.path.join(self.state_dir, "locks")
        self.lock_commanders = path(data["locks"]["commanders"]) or os.path.join(self.state_dir, "lock-commanders.txt")
        self.statusline_base = data["statusline"]["base"]
        self.playbook_remind = data["playbook"]["remind"] is not False
        p = data["progress"]
        self.weights = [0, p["develop"], p["review"], p["accept"], p["ci"], p["merged"]]
        self.quiet_s = data["pacing"]["quiet_minutes"] * 60
        self.quiet_github_s = data["pacing"]["quiet_github_minutes"] * 60
        c = data["closing"]
        self.idle_confirm_s = c["idle_confirm_hours"] * 3600
        self.idle_flag_s = c["idle_flag_days"] * 86400
        self.stale_phase_s = c["stale_phase_hours"] * 3600
        self.ask_fresh_s = data["waiting"]["ask_fresh_hours"] * 3600
        # Several projects on one board, each with its directories and repository; none: the one project that
        # [sessions] project_dirs and [github] repo_dir describe, as always.
        self.projects = [{"name": str(p.get("name") or f"project {i + 1}"),
                          "dirs": [path(d) for d in p.get("dirs") or []],
                          "repo_dir": path(p.get("repo_dir") or ""),
                          "summary_checks": tuple(p.get("summary_checks") or self.summary_checks)}
                         for i, p in enumerate(data.get("projects") or []) if isinstance(p, dict)]
        self.project = ""  # the one this view of the config is for, when there are several
        self.cache_dir = ""

    def sub(self, *parts):
        """A path under the state directory."""
        return os.path.join(self.state_dir, *parts)

    def cache(self, name):
        """A file of the board's own memory: one set per project when there are several, else where it always was."""
        return os.path.join(self.cache_dir, name) if self.cache_dir else self.sub(name)

    def for_project(self, p):
        """This config as one of its projects sees it: its directories, its repository, its own caches."""
        c = copy.copy(self)
        c.project, c.projects = p["name"], []
        c.project_dirs, c.repo_dir, c.summary_checks = p["dirs"], p["repo_dir"], p["summary_checks"]
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", p["name"]) + "_" + hashlib.sha1(p["name"].encode()).hexdigest()[:10]
        c.cache_dir = self.sub("projects", safe)
        return c

    def in_project(self, cwd):
        """Whether a session working in `cwd` is this config's: with no directories set, every session, unless this
        is one of several projects, which then has none."""
        if not self.project_dirs:
            return not self.project
        return any(str(cwd).startswith(p) for p in self.project_dirs)


def config_path():
    return path(os.environ.get("ADMIRAL_CONFIG") or "~/.config/admiral/config.toml")


def load(file=None):
    file = file or config_path()
    try:
        with open(file, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        data = {}
    return Config(merge(DEFAULTS, data))
