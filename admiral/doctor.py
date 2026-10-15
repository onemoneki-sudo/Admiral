"""`admiral doctor`: whether each piece Admiral needs is in place, and how to fix the ones that are not.

It only reads: it changes neither Claude Code's settings nor Admiral's config, and asks GitHub once at most. Each
check is ok, a note, a warning or a failure, the last two with what to do: in words, and as a command to paste when
there is one. Any failure makes the exit status 1. Everything it asks the machine goes through Machine, so a test
can answer instead; a check that itself goes wrong is reported as failed, and the others still run.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

from . import __version__, config
from .words import phrases

OK, NOTE, WARN, FAIL = "ok", "note", "warn", "fail"
MARK = {OK: "✓", NOTE: "·", WARN: "!", FAIL: "✗"}
JOB = "com.admiral.board"  # scripts/install.sh's background job
STALE_S = 180  # a board older than this: the background job is not running (the status line says so too)

TEXT = phrases({
    "en": {
        "title": "Admiral doctor {version}", "fix": "fix",
        "summary": "{fail} to fix, {warn} to look at", "all_set": "all set",
        "check_failed": "the {name} check could not run: {error}", "fix_report": "please report it, with this output",
        "py_ok": "Python {v} ({py})", "py_unrecorded": "no Python recorded in {here}/.python-path",
        "py_gone": "the recorded Python {py} does not run", "py_old": "the recorded Python {py} is {v}: 3.11 or newer needed",
        "fix_install": "run the install script again",
        "link_ok": "admiral on the PATH ({link})", "link_missing": "no {link}: sessions cannot run admiral by name",
        "link_other": "{link} is not this clone's: it points to {to}", "fix_link": "remove {link}, then run the install script",
        "path_missing": "~/.local/bin is not on the PATH", "fix_path": "add ~/.local/bin to the PATH in your shell's profile",
        "config_ok": "config {path}", "config_none": "no config at {path}: every session on this machine shows, and no PR or CI",
        "fix_config_new": "the install script writes a commented one",
        "config_broken": "config {path} does not load: {error}", "fix_config": "correct it in {path}",
        "config_type": "config {key} must be {kind}", "kind_table": "a table", "kind_bool": "true or false",
        "kind_number": "a number", "kind_list": "a list of strings, like [\"~/code/app\"]", "kind_string": "a string",
        "language_bad": "config language is {v}: \"en\" or \"zh\"; English is used",
        "dirs_all": "project_dirs is empty: every Claude Code session on this machine shows",
        "dir_missing": "project_dirs names {d}, and no directory starts with it",
        "repo_none": "[github] repo_dir is empty: no PR or CI on the board",
        "fix_repo": "set [github] repo_dir in {path} to your repository",
        "project_no_dirs": "the project has no dirs: none of its sessions shows",
        "project_no_repo": "the project has no repo_dir: no PR or CI for it on the board",
        "fix_project": "set dirs and repo_dir of the project \"{name}\" in {path}",
        "project_twice": "two projects are named \"{given}\": the second reads as \"{name}\"",
        "fix_project_name": "give each project in {path} a name of its own",
        "repo_missing": "[github] repo_dir {d} does not exist", "repo_not_git": "[github] repo_dir {d} is not a git repository",
        "gh_skipped": "gh not checked: no repository set", "gh_missing": "gh (the GitHub CLI) is not installed",
        "fix_gh": "install it from https://cli.github.com, then sign in",
        "gh_cannot": "gh cannot read the repository in {d}: {error}", "fix_gh_login": "sign gh in again",
        "fix_gh_network": "check the network or the proxy gh goes through, then run admiral doctor again",
        "fix_gh_access": "check that your gh account can read this repository",
        "gh_ok": "gh reads {repo}",
        "job_ok": "background job {job} loaded", "job_missing": "background job {job} not loaded",
        "board_ok": "board refreshed {age} ago", "board_none": "no board yet at {path}",
        "board_stale": "board last refreshed {age} ago: the background job is not running",
        "board_error": "the last refresh wrote an error: {error}",
        "fix_board_error": "read {errors}, the last refresh's own words, and check that {state} is writable",
        "fix_cron": "run it every minute from cron or a systemd timer; for cron, this adds the line",
        "unreadable": "{path} is there but cannot be read: {error}",
        "fix_unreadable": "the background job writes it each minute: remove it, and it is written afresh",
        "fix_job_error": "it failed: read {errors}; then",
        "status_ok": "status line runs Admiral ({exe})", "status_none": "no status line set in {path}",
        "status_other": "the status line does not run admiral statusline: {cmd}",
        "status_gone": "the status line command does not draw Admiral's line ({exe}): {error}",
        "status_shape": "statusLine in {path} is not an object with a command",
        "fix_status": "in {path} set {line}",
        "fix_status_keep": "keep the command it runs now as [statusline] base in Admiral's config (it then runs first), and in {path} set {line}",
        "settings_broken": "{path} does not load: {error}", "settings_shape": "{path} is not a JSON object",
        "plugin_ok": "plugin admiral@admiral {v}, enabled", "claude_missing": "Claude Code (claude) is not on the PATH",
        "fix_claude": "install Claude Code, and put claude on the PATH",
        "plugin_unread": "claude plugin list failed: {error}", "fix_claude_update": "update Claude Code",
        "plugin_missing": "plugin admiral@admiral not installed", "fix_plugin": "add Admiral's marketplace and install the plugin",
        "plugin_off": "plugin admiral@admiral is disabled", "fix_plugin_on": "enable it",
        "plugin_old": "plugin admiral@admiral is {v}, this clone is {code}",
        "fix_plugin_update": "update the plugin; sessions load the new one when they restart",
        "plugin_new": "plugin admiral@admiral is {v}, newer than this clone's {code}", "fix_pull": "update the clone",
        "claude_version_failed": "claude --version failed: {error}",
        "claude_note": "Claude Code {v}: the sidebar needs plugin function hooks (early access); type /admiral in a session to see whether it opens",
        "health": "the board reports: {h}",
        "fix_health": "admiral board --now shows it as it is now; if it stays after a Claude Code update, update Admiral",
        "memory_on": "automatic memory is on: recommended off, so what a session knows comes from files you can read (\"autoMemoryEnabled\": false in {path})",
    },
    "zh": {
        "title": "Admiral 自检 {version}", "fix": "修法",
        "summary": "{fail} 项需要修，{warn} 项需要看一下", "all_set": "全部就绪",
        "check_failed": "「{name}」这一项检查没能运行：{error}", "fix_report": "请连同这份输出一起反馈",
        "py_ok": "Python {v}（{py}）", "py_unrecorded": "{here}/.python-path 里没有记录 Python",
        "py_gone": "记录的 Python {py} 无法运行", "py_old": "记录的 Python {py} 是 {v}，需要 3.11 或更新",
        "fix_install": "重新运行安装脚本",
        "link_ok": "admiral 已在 PATH 上（{link}）", "link_missing": "没有 {link}：会话无法直接运行 admiral",
        "link_other": "{link} 不是这份 clone 的：它指向 {to}", "fix_link": "删掉 {link}，再运行安装脚本",
        "path_missing": "~/.local/bin 不在 PATH 上", "fix_path": "在 shell 的配置文件里把 ~/.local/bin 加进 PATH",
        "config_ok": "配置 {path}", "config_none": "没有配置文件 {path}：显示本机所有会话，没有 PR 和 CI",
        "fix_config_new": "安装脚本会写一份带注释的配置",
        "config_broken": "配置 {path} 读取失败：{error}", "fix_config": "在 {path} 里改正",
        "config_type": "配置 {key} 应该是{kind}", "kind_table": "一个表", "kind_bool": " true 或 false",
        "kind_number": "数字", "kind_list": "字符串列表，例如 [\"~/code/app\"]", "kind_string": "字符串",
        "language_bad": "配置 language 是 {v}：只能是 \"en\" 或 \"zh\"，现在按英文显示",
        "dirs_all": "project_dirs 为空：显示本机所有 Claude Code 会话",
        "dir_missing": "project_dirs 里的 {d}，没有任何目录以它开头",
        "repo_none": "[github] repo_dir 为空：看板上没有 PR 和 CI",
        "fix_repo": "在 {path} 里把 [github] repo_dir 设为你的仓库",
        "project_no_dirs": "这个项目没写 dirs：它的对话都不会显示",
        "project_no_repo": "这个项目没写 repo_dir：看板上没有它的 PR 和 CI",
        "fix_project": "在 {path} 里给项目「{name}」写上 dirs 和 repo_dir",
        "project_twice": "有两个项目都叫「{given}」：第二个显示为「{name}」",
        "fix_project_name": "在 {path} 里给每个项目起不同的名字",
        "repo_missing": "[github] repo_dir {d} 不存在", "repo_not_git": "[github] repo_dir {d} 不是 git 仓库",
        "gh_skipped": "没有设置仓库，跳过 gh 检查", "gh_missing": "没有安装 gh（GitHub CLI）",
        "fix_gh": "从 https://cli.github.com 安装，再登录",
        "gh_cannot": "gh 读不到 {d} 的仓库：{error}", "fix_gh_login": "重新登录 gh",
        "fix_gh_network": "检查网络或 gh 使用的代理，再运行一次 admiral doctor",
        "fix_gh_access": "确认你的 gh 账号能读这个仓库",
        "gh_ok": "gh 能读到 {repo}",
        "job_ok": "后台任务 {job} 已加载", "job_missing": "后台任务 {job} 没有加载",
        "board_ok": "看板 {age}前刷新过", "board_none": "{path} 还没有看板",
        "board_stale": "看板上次刷新在 {age}前：后台任务没在运行",
        "board_error": "上次刷新留下了错误：{error}",
        "fix_board_error": "查看 {errors}（上次刷新自己的输出），并确认 {state} 可写",
        "fix_cron": "用 cron 或 systemd 定时器每分钟运行一次；用 cron 的话，下面这条命令会加上那一行",
        "unreadable": "{path} 存在但读不了：{error}",
        "fix_unreadable": "它由后台任务每分钟写一次：删掉它，下次会重新写",
        "fix_job_error": "它失败了：先看 {errors}；然后",
        "status_ok": "状态栏运行的是 Admiral（{exe}）", "status_none": "{path} 里没有设置状态栏",
        "status_other": "状态栏运行的不是 admiral statusline：{cmd}",
        "status_gone": "状态栏命令画不出 Admiral 那一行（{exe}）：{error}",
        "status_shape": "{path} 里的 statusLine 不是带 command 的对象",
        "fix_status": "在 {path} 里设置 {line}",
        "fix_status_keep": "把它现在运行的命令写进 Admiral 配置的 [statusline] base（之后会先运行它），再在 {path} 里设置 {line}",
        "settings_broken": "{path} 读取失败：{error}", "settings_shape": "{path} 不是一个 JSON 对象",
        "plugin_ok": "插件 admiral@admiral {v}，已启用", "claude_missing": "PATH 上没有 Claude Code（claude）",
        "fix_claude": "安装 Claude Code，并把 claude 加进 PATH",
        "plugin_unread": "claude plugin list 失败：{error}", "fix_claude_update": "更新 Claude Code",
        "plugin_missing": "没有安装插件 admiral@admiral", "fix_plugin": "添加 Admiral 的 marketplace 并安装插件",
        "plugin_off": "插件 admiral@admiral 已停用", "fix_plugin_on": "启用它",
        "plugin_old": "插件 admiral@admiral 是 {v}，这份 clone 是 {code}",
        "fix_plugin_update": "更新插件；会话重启后才会载入新版本",
        "plugin_new": "插件 admiral@admiral 是 {v}，比这份 clone 的 {code} 新", "fix_pull": "更新这份 clone",
        "claude_version_failed": "claude --version 失败：{error}",
        "claude_note": "Claude Code {v}：侧边栏需要 plugin function hooks（抢先体验功能），在会话里输入 /admiral，看它能否打开",
        "health": "看板报告：{h}",
        "fix_health": "用 admiral board --now 看它现在的样子；如果 Claude Code 更新后还在，就更新 Admiral",
        "memory_on": "自动记忆是开着的：建议关掉，让会话知道的东西都来自你能读的文件（在 {path} 里设 \"autoMemoryEnabled\": false）",
    },
})


class Machine:
    """What doctor looks at: this clone, the home directory, the platform, the PATH, and the commands it runs."""

    def __init__(self, here, home=None, platform=None, path=None, now=None):
        self.here = here
        self.home = home or os.path.expanduser("~")
        self.platform = platform or sys.platform
        self.path = os.environ.get("PATH", "") if path is None else path
        self.now = time.time() if now is None else now

    def run(self, argv, cwd=None, input=None, env=None):
        """(exit status, stdout, stderr); None when the command is not found. It runs with this machine's home and
        PATH, and `env` added."""
        exe = shutil.which(argv[0], path=self.path)
        if not exe:
            return None
        env = dict(os.environ, HOME=self.home, PATH=self.path, **(env or {}))
        try:
            r = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, cwd=cwd, timeout=30, input=input,
                               env=env)
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, "", str(e)
        return r.returncode, r.stdout, r.stderr


def result(level, text, fix="", cmd=""):
    """One check's outcome: its level, what it found, what to do in words, and the command to paste."""
    return (level, text, fix, cmd)


def first_line(text):
    return next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")


def ago(seconds, language):
    s = int(max(0, seconds))
    zh = language == "zh"
    if s < 60:
        return f"{s}{'秒' if zh else ' s'}"
    if s < 3600:
        return f"{s // 60}{'分钟' if zh else ' min'}"
    return f"{s // 3600}{'小时' if zh else ' h'}"


def version(text):
    try:
        return tuple(int(x) for x in text.split("."))
    except ValueError:
        return ()


def with_config(m, path, cmd):
    """cmd, given the config in use when it is not the default one: launchd and cron start a job without the shell's
    environment, so ADMIRAL_CONFIG has to go in the command."""
    default = os.path.join(m.home, ".config", "admiral", "config.toml")
    if path and os.path.abspath(path) != os.path.abspath(default):  # from anywhere: cron and launchd start in $HOME
        return f"ADMIRAL_CONFIG={shlex.quote(os.path.abspath(path))} {cmd}"
    return cmd


def install_cmd(m, ctx):
    return with_config(m, ctx.get("path"), shlex.quote(os.path.join(m.here, "scripts", "install.sh")))


def read_settings(m):
    """(Claude Code's user settings, {} when there are none; the error when they do not load)."""
    path = os.path.join(m.home, ".claude", "settings.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}, ""
    except (OSError, ValueError) as e:
        return None, str(e)
    return (data, "") if isinstance(data, dict) else (None, "shape")


def read_toml(path):
    """(the config file's own keys, {} when there is none; the error when it does not parse)."""
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh), ""
    except FileNotFoundError:
        return {}, ""
    except (OSError, ValueError) as e:  # TOMLDecodeError and UnicodeDecodeError are ValueErrors
        return None, first_line(str(e)) or type(e).__name__


def wrong_types(data, defaults=config.DEFAULTS, prefix=""):
    """(key, kind) for every key of the config whose value is not of the kind Admiral expects."""
    out = []
    for k, v in data.items():
        if k not in defaults:
            continue
        d, key = defaults[k], prefix + k
        if isinstance(d, dict):
            out += wrong_types(v, d, key + ".") if isinstance(v, dict) else [(key, "kind_table")]
        elif isinstance(d, bool):
            out += [] if isinstance(v, bool) else [(key, "kind_bool")]
        elif isinstance(d, (int, float)):
            out += [] if isinstance(v, (int, float)) and not isinstance(v, bool) else [(key, "kind_number")]
        elif isinstance(d, list):
            out += [] if isinstance(v, list) and all(isinstance(x, str) for x in v) else [(key, "kind_list")]
        elif isinstance(d, str):
            out += [] if isinstance(v, str) else [(key, "kind_string")]
    return out


def matches_a_directory(prefix):
    """Whether any directory's path starts with `prefix`, as project_dirs matches a session's working directory:
    ~/code/app covers ~/code/app-worktrees too."""
    parent, base = os.path.split(prefix.rstrip(os.sep))
    try:
        return os.path.isdir(prefix) or any(n.startswith(base) and os.path.isdir(os.path.join(parent, n))
                                            for n in os.listdir(parent))
    except OSError:
        return False


ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
SEPARATORS = ";&|()\n"


def simple_commands(cmd):
    """A status line command split as the shell splits it: simple commands, each a list of (word, whether the word
    began quoted). Quotes, backslashes, comments and newlines count as the shell counts them; None when a quote does
    not close. Expansions ($, backquotes) are left as written."""
    commands, words, word, quoted, inside, i = [], [], "", False, False, 0
    while i < len(cmd):
        ch = cmd[i]
        if ch in "'\"":
            j = i + 1
            while j < len(cmd) and cmd[j] != ch:
                j += 2 if ch == '"' and cmd[j] == "\\" else 1
            if j >= len(cmd):
                return None
            text = cmd[i + 1:j] if ch == "'" else re.sub(r'\\(["\\$`])', r"\1", cmd[i + 1:j])
            if not inside:
                quoted, inside = True, True
            word, i = word + text, j + 1
        elif ch == "\\" and i + 1 < len(cmd):
            if cmd[i + 1] != "\n":  # a backslash before a newline joins the lines
                if not inside:
                    quoted, inside = True, True
                word += cmd[i + 1]
            i += 2
        elif ch.isspace() or ch in SEPARATORS:
            if inside:
                words.append((word, quoted))
                word, inside = "", False
            if ch in SEPARATORS and words:
                commands.append(words)
                words = []
            i += 1
        elif ch == "#" and not inside:  # a comment, to the end of the line
            i = cmd.find("\n", i) if "\n" in cmd[i:] else len(cmd)
        else:
            if not inside:
                quoted, inside = False, True
            word, i = word + ch, i + 1
    if inside:
        words.append((word, quoted))
    return commands + [words] if words else commands


def admiral_in(cmd):
    """The program a status line command runs as `admiral statusline`, as written, or None: the first word of one
    of its simple commands, past any assignment, named admiral and followed by statusline. Whether it runs, the
    shell itself says (check_statusline)."""
    for words in simple_commands(cmd) or []:
        while words and not words[0][1] and ASSIGNMENT.match(words[0][0]):
            words = words[1:]
        if len(words) >= 2 and os.path.basename(words[0][0]) == "admiral" and words[1][0] == "statusline":
            return words[0][0]
    return None


def check_python(m, T, ctx):
    try:
        with open(os.path.join(m.here, ".python-path"), encoding="utf-8") as fh:
            py = fh.read().strip()
    except OSError:
        py = ""
    if not py:
        return [result(WARN, T["py_unrecorded"].format(here=m.here), T["fix_install"], install_cmd(m, ctx))]
    r = m.run([py, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"])
    if r is None or r[0]:
        return [result(FAIL, T["py_gone"].format(py=py), T["fix_install"], install_cmd(m, ctx))]
    v = r[1].strip()
    if version(v)[:2] < (3, 11):
        return [result(FAIL, T["py_old"].format(py=py, v=v), T["fix_install"], install_cmd(m, ctx))]
    return [result(OK, T["py_ok"].format(v=v, py=py))]


def check_link(m, T, ctx):
    bindir = os.path.join(m.home, ".local", "bin")
    link = os.path.join(bindir, "admiral")
    out = []
    if not os.path.lexists(link):
        out.append(result(FAIL, T["link_missing"].format(link=link), T["fix_install"], install_cmd(m, ctx)))
    elif os.path.realpath(link) != os.path.realpath(os.path.join(m.here, "bin", "admiral")):
        out.append(result(WARN, T["link_other"].format(link=link, to=os.path.realpath(link)),
                          T["fix_link"].format(link=link), install_cmd(m, ctx)))
    else:
        out.append(result(OK, T["link_ok"].format(link=link)))
    if bindir not in m.path.split(os.pathsep):
        out.append(result(WARN, T["path_missing"], T["fix_path"]))
    return out


def check_config(m, T, ctx):
    path, data, error = ctx["path"], ctx["toml"], ctx["toml_error"]
    if data is None:
        return [result(FAIL, T["config_broken"].format(path=path, error=error), T["fix_config"].format(path=path))]
    if not os.path.exists(path):
        out = [result(WARN, T["config_none"].format(path=path), T["fix_config_new"], install_cmd(m, ctx))]
    else:
        out = [result(OK, T["config_ok"].format(path=path))]
    wrong = wrong_types(data)
    out += [result(FAIL, T["config_type"].format(key=k, kind=T[kind]), T["fix_config"].format(path=path))
            for k, kind in wrong]
    if "language" in data and data["language"] not in ("en", "zh") and isinstance(data["language"], str):
        out.append(result(WARN, T["language_bad"].format(v=json.dumps(data["language"])), T["fix_config"].format(path=path)))
    if wrong:
        return out  # the rest reads the config as Admiral would, which a wrong kind would only mislead
    try:
        cfg = config.load(path)
    except Exception as e:  # a value of the right kind Admiral still cannot use
        return out + [result(FAIL, T["config_broken"].format(path=path, error=first_line(str(e)) or type(e).__name__),
                             T["fix_config"].format(path=path))]
    ctx["cfg"] = cfg
    if not cfg.projects:
        return out + where(m, T, cfg, path)
    out += [result(WARN, T["project_twice"].format(given=given, name=name), T["fix_project_name"].format(path=path))
            for given, name in cfg.renamed]
    for p in cfg.projects:  # each project its directories and its repository, its name before what is said of it
        view = cfg.for_project(p)
        found = where(m, T, view, path, T["fix_project"].format(name=p["name"], path=path))
        out += [(level, f"{p['name']}: {text}", fix, cmd) for level, text, fix, cmd in found]
    return out


def where(m, T, cfg, path, fix=None):
    """What is wrong with the directories and repository one project is read from."""
    out = []
    if not cfg.project_dirs:
        out.append(result(WARN, T["project_no_dirs"], fix) if cfg.project else result(NOTE, T["dirs_all"]))
    out += [result(WARN, T["dir_missing"].format(d=d), fix or T["fix_config"].format(path=path))
            for d in cfg.project_dirs if not matches_a_directory(d)]
    fix = fix or T["fix_repo"].format(path=path)
    if not cfg.repo_dir:
        out.append(result(WARN, T["project_no_repo"] if cfg.project else T["repo_none"], fix))
    elif not os.path.isdir(cfg.repo_dir):
        out.append(result(FAIL, T["repo_missing"].format(d=cfg.repo_dir), fix))
    else:
        r = m.run(["git", "-C", cfg.repo_dir, "rev-parse", "--git-dir"])
        if r is not None and r[0]:
            out.append(result(FAIL, T["repo_not_git"].format(d=cfg.repo_dir), fix))
    return out


GH_ACCESS = re.compile(r"not accessible|http 403|forbidden|could not resolve to a repository|http 404", re.I)
GH_AUTH = re.compile(r"auth login|bad credentials|http 401|authentication (required|failed)|not logged in|"
                     r"token (is )?(invalid|expired)", re.I)
GH_NETWORK = re.compile(r"error connecting|could not resolve host|no such host|dial tcp|timed? ?out|unreachable|"
                        r"proxy|tls handshake|connection (refused|reset)", re.I)


def check_gh(m, T, ctx):
    cfg = ctx.get("cfg")
    if cfg is not None and cfg.projects:  # one request for each project's repository
        return [(level, f"{p['name']}: {text}", fix, cmd) for p in cfg.projects
                for level, text, fix, cmd in check_gh(m, T, dict(ctx, cfg=cfg.for_project(p)))]
    if cfg is None or not cfg.repo_dir or not os.path.isdir(cfg.repo_dir):
        return [result(NOTE, T["gh_skipped"])]
    r = m.run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=cfg.repo_dir)
    if r is None:
        return [result(FAIL, T["gh_missing"], T["fix_gh"], "gh auth login")]
    if r[0]:
        said = r[2] + "\n" + r[1]
        error = first_line(r[2]) or first_line(r[1])
        if GH_ACCESS.search(said):
            fix, cmd = T["fix_gh_access"], f"cd {shlex.quote(cfg.repo_dir)} && gh repo view"
        elif GH_AUTH.search(said):
            fix, cmd = T["fix_gh_login"], "gh auth login"
        elif GH_NETWORK.search(said):
            fix, cmd = T["fix_gh_network"], ""
        else:
            fix, cmd = T["fix_gh_access"], f"cd {shlex.quote(cfg.repo_dir)} && gh repo view"
        return [result(FAIL, T["gh_cannot"].format(d=cfg.repo_dir, error=error), fix, cmd)]
    return [result(OK, T["gh_ok"].format(repo=r[1].strip()))]


def check_job(m, T, ctx):
    out = []
    macos = m.platform == "darwin"
    cron = "* * * * * " + with_config(m, ctx.get("path"), shlex.quote(os.path.join(m.here, "scripts", "refresh.sh")))
    cron = cron.replace("%", "\\%")  # cron reads % as a newline
    fix, cmd = (T["fix_install"], install_cmd(m, ctx)) if macos else \
        (T["fix_cron"], f"(crontab -l 2>/dev/null; printf '%s\\n' {shlex.quote(cron)}) | crontab -")
    if macos:
        r = m.run(["launchctl", "print", f"gui/{os.getuid()}/{JOB}"])
        out.append(result(OK, T["job_ok"].format(job=JOB)) if r is not None and not r[0]
                   else result(FAIL, T["job_missing"].format(job=JOB), fix, cmd))
    cfg = ctx.get("cfg")
    if cfg is None:
        return out
    board, errors = cfg.sub("board.json"), cfg.sub("last-error.txt")
    try:
        with open(errors, encoding="utf-8") as fh:
            error = [ln.strip() for ln in fh if ln.strip()]
    except FileNotFoundError:
        error = []
    except (OSError, ValueError) as e:
        out.append(result(FAIL, T["unreadable"].format(path=errors, error=first_line(str(e)) or type(e).__name__),
                          T["fix_unreadable"]))
        error = []
    if not os.path.exists(board):
        out.append(result(FAIL, T["board_none"].format(path=board), fix, cmd))
        return out
    try:
        with open(board, encoding="utf-8") as fh:
            if not isinstance(json.load(fh), dict):
                raise ValueError("not a JSON object")
    except (OSError, ValueError) as e:
        out.append(result(FAIL, T["unreadable"].format(path=board, error=first_line(str(e)) or type(e).__name__),
                          T["fix_unreadable"]))
        return out
    age = m.now - os.path.getmtime(board)
    if age > STALE_S:
        why = T["fix_job_error"].format(errors=errors) + " " if error else ""
        out.append(result(FAIL, T["board_stale"].format(age=ago(age, cfg.language)), why + fix, cmd))
        return out
    out.append(result(OK, T["board_ok"].format(age=ago(age, cfg.language))))
    if error:
        out.append(result(WARN, T["board_error"].format(error=error[-1][:160]),
                          T["fix_board_error"].format(errors=errors, state=cfg.state_dir)))
    return out


def check_statusline(m, T, ctx):
    path = os.path.join(m.home, ".claude", "settings.json")
    settings, broken = ctx["settings"], ctx["settings_error"]
    if broken == "shape":
        return [result(FAIL, T["settings_shape"].format(path=path), T["fix_config"].format(path=path))]
    if broken:
        return [result(FAIL, T["settings_broken"].format(path=path, error=broken), T["fix_config"].format(path=path))]
    command = json.dumps(f"{shlex.quote(os.path.join(m.here, 'bin', 'admiral'))} statusline", ensure_ascii=False)
    line = f'"statusLine": {{"type": "command", "command": {command}, "refreshInterval": 20}}'
    status = settings.get("statusLine")
    if status is None:
        return [result(FAIL, T["status_none"].format(path=path), T["fix_status"].format(path=path, line=line))]
    if not isinstance(status, dict) or not isinstance(status.get("command", ""), str):
        return [result(FAIL, T["status_shape"].format(path=path), T["fix_status"].format(path=path, line=line))]
    cmd = status.get("command", "")
    if not cmd:
        return [result(FAIL, T["status_none"].format(path=path), T["fix_status"].format(path=path, line=line))]
    if "admiral" not in cmd.lower():  # another status line: Admiral can run it first
        return [result(FAIL, T["status_other"].format(cmd=cmd), T["fix_status_keep"].format(path=path, line=line))]
    # Whether it runs Admiral, Admiral itself says: run as Claude Code runs it, through the shell with the session's
    # JSON on stdin, its status line leaves a mark in $ADMIRAL_PROBE, however the command reaches it (a status line
    # only reads). One from before the mark passes as it did: run as written, drawing Admiral's line. Never kept to
    # run first: it names Admiral.
    exe = admiral_in(cmd)
    with tempfile.TemporaryDirectory() as d:
        probe = os.path.join(d, "ran")
        r = m.run(["/bin/sh", "-c", cmd], input=json.dumps({"session_id": ""}), env={"ADMIRAL_PROBE": probe})
        ran = os.path.exists(probe) or (exe is not None and r is not None and "Admiral" in r[1])
    exe = exe or cmd
    if r is None or r[0] or not ran:
        said = first_line(r[2]) or first_line(r[1]) if r else "/bin/sh"
        return [result(FAIL, T["status_gone"].format(exe=exe, error=said), T["fix_status"].format(path=path, line=line))]
    return [result(OK, T["status_ok"].format(exe=exe))]


def check_plugin(m, T, ctx):
    r = m.run(["claude", "plugin", "list", "--json"])
    if r is None:
        return [result(FAIL, T["claude_missing"], T["fix_claude"])]
    try:
        plugins = json.loads(r[1]) if not r[0] else None
    except ValueError:
        plugins = None
    if not isinstance(plugins, list):
        return [result(FAIL, T["plugin_unread"].format(error=first_line(r[2]) or first_line(r[1])),
                       T["fix_claude_update"], "claude update")]
    p = next((p for p in plugins if isinstance(p, dict) and p.get("id") == "admiral@admiral"), None)
    if p is None:
        return [result(FAIL, T["plugin_missing"], T["fix_plugin"],
                       f"claude plugin marketplace add {shlex.quote(m.here)} && claude plugin install admiral@admiral")]
    if p.get("enabled") is False:
        return [result(FAIL, T["plugin_off"], T["fix_plugin_on"], "claude plugin enable admiral@admiral")]
    v = str(p.get("version", ""))
    if version(v) < version(__version__):
        return [result(WARN, T["plugin_old"].format(v=v, code=__version__), T["fix_plugin_update"],
                       "claude plugin marketplace update admiral && claude plugin update admiral@admiral")]
    if version(v) > version(__version__):
        return [result(WARN, T["plugin_new"].format(v=v, code=__version__), T["fix_pull"],
                       f"git -C {shlex.quote(m.here)} pull")]
    return [result(OK, T["plugin_ok"].format(v=v))]


def check_claude(m, T, ctx):
    r = m.run(["claude", "--version"])
    if r is None:
        return []  # check_plugin has said Claude Code is missing
    if r[0]:
        return [result(FAIL, T["claude_version_failed"].format(error=first_line(r[2]) or first_line(r[1])),
                       T["fix_claude_update"], "claude update"),
                result(NOTE, T["claude_note"].format(v="?"))]
    return [result(NOTE, T["claude_note"].format(v=r[1].split()[0] if r[1].split() else "?"))]


def check_health(m, T, ctx):
    cfg = ctx.get("cfg")
    if cfg is None:
        return []
    try:
        with open(cfg.sub("board.json"), encoding="utf-8") as fh:
            b = json.load(fh)
    except (OSError, ValueError):
        return []  # check_job reports a board it cannot read
    health = b.get("health") if isinstance(b, dict) else None
    if not isinstance(health, list):
        return []
    return [result(WARN, T["health"].format(h=h), T["fix_health"], f"git -C {shlex.quote(m.here)} pull")
            for h in health]


def check_memory(m, T, ctx):
    settings = ctx["settings"]
    if settings is not None and settings.get("autoMemoryEnabled") is not False:
        return [result(NOTE, T["memory_on"].format(path=os.path.join(m.home, ".claude", "settings.json")))]
    return []


CHECKS = [("python", check_python), ("link", check_link), ("config", check_config), ("gh", check_gh),
          ("job", check_job), ("statusline", check_statusline), ("plugin", check_plugin), ("claude", check_claude),
          ("board", check_health), ("memory", check_memory)]


def checks(m, path):
    """(every check's results, the language they are in)."""
    data, error = read_toml(path)
    language = data.get("language") if isinstance(data, dict) and data.get("language") in ("en", "zh") else "en"
    T = TEXT[language]
    settings, settings_error = read_settings(m)
    ctx = {"path": path, "toml": data, "toml_error": error, "settings": settings, "settings_error": settings_error}
    results = []
    for name, check in CHECKS:  # in order: the config check leaves the loaded config for those after it
        try:
            results += check(m, T, ctx)
        except Exception as e:
            results.append(result(FAIL, T["check_failed"].format(name=name, error=f"{type(e).__name__}: {e}"),
                                  T["fix_report"]))
    return results, language


def main(machine=None, path=None, out=None):
    """Prints every check; the exit status: 1 when any failed, else 0."""
    m = machine or Machine(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out = out or sys.stdout
    results, language = checks(m, path or config.config_path())
    T = TEXT[language]
    out.write(T["title"].format(version=__version__) + "\n\n")
    for level, text, fix, cmd in results:
        out.write(f"{MARK[level]} {text}\n")
        if fix:
            out.write(f"    {T['fix']}{'：' if language == 'zh' else ': '}{fix}\n")
        if cmd:
            out.write(f"    $ {cmd}\n")
    fail, warn = (sum(r[0] == k for r in results) for k in (FAIL, WARN))
    out.write("\n" + (T["summary"].format(fail=fail, warn=warn) if fail or warn else T["all_set"]) + "\n")
    return 1 if fail else 0
