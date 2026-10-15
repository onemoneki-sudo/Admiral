"""`admiral doctor`: whether each piece Admiral needs is in place, and how to fix the ones that are not.

It only reads: it changes neither Claude Code's settings nor Admiral's config, and asks GitHub once at most. Each
check is ok, a note, a warning or a failure, the last two with their fix; any failure makes the exit status 1.
Everything it asks the machine goes through Machine, so a test can answer instead.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import time

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
        "fix_install": "run {here}/scripts/install.sh",
        "py_ok": "Python {v} ({py})", "py_unrecorded": "no Python recorded in {here}/.python-path",
        "py_gone": "the recorded Python {py} does not run", "py_old": "the recorded Python {py} is {v}: 3.11 or newer needed",
        "link_ok": "admiral on the PATH ({link})", "link_missing": "no {link}: sessions cannot run admiral by name",
        "link_other": "{link} is not this clone's: it points to {to}", "fix_link": "remove it, then run {here}/scripts/install.sh",
        "path_missing": "~/.local/bin is not on the PATH", "fix_path": "add ~/.local/bin to the PATH in your shell's profile",
        "config_ok": "config {path}", "config_none": "no config at {path}: every session on this machine shows, and no PR or CI",
        "config_broken": "config {path} does not load: {error}", "fix_config": "correct it in {path}",
        "dirs_all": "project_dirs is empty: every Claude Code session on this machine shows",
        "dir_missing": "project_dirs names {d}, and no directory starts with it",
        "repo_none": "[github] repo_dir is empty: no PR or CI on the board",
        "fix_repo": "set [github] repo_dir in {path} to your repository",
        "repo_missing": "[github] repo_dir {d} does not exist", "repo_not_git": "[github] repo_dir {d} is not a git repository",
        "gh_skipped": "gh not checked: no repository set", "gh_missing": "gh (the GitHub CLI) is not installed",
        "fix_gh": "install it from https://cli.github.com, then gh auth login",
        "gh_cannot": "gh cannot read the repository in {d}: {error}", "fix_gh_login": "gh auth login",
        "fix_gh_access": "check that your gh account can read this repository (gh repo view, in {d})",
        "gh_ok": "gh reads {repo}",
        "job_ok": "background job {job} loaded", "job_missing": "background job {job} not loaded",
        "board_ok": "board refreshed {age} ago", "board_none": "no board yet at {path}",
        "board_stale": "board last refreshed {age} ago: the background job is not running",
        "board_error": "the last refresh failed: {error}",
        "fix_cron": "run {here}/scripts/refresh.sh every minute (cron: * * * * * {here}/scripts/refresh.sh)",
        "fix_job": "run {here}/scripts/install.sh, or see {error}",
        "status_ok": "status line runs Admiral", "status_none": "no status line set in {path}",
        "status_other": "the status line runs something else: {cmd}",
        "status_gone": "the status line runs {exe}, which does not exist",
        "fix_status": "in {path} set {line}",
        "fix_status_keep": "keep it as [statusline] base in the config (it then runs first), and in {path} set {line}",
        "settings_broken": "{path} does not load: {error}",
        "plugin_ok": "plugin admiral@admiral {v}, enabled", "claude_missing": "Claude Code (claude) is not on the PATH",
        "fix_claude": "install Claude Code, or add it to the PATH",
        "plugin_unread": "claude plugin list failed: {error}", "plugin_missing": "plugin admiral@admiral not installed",
        "fix_plugin": "claude plugin marketplace add '{here}' && claude plugin install admiral@admiral",
        "plugin_off": "plugin admiral@admiral is disabled", "fix_plugin_on": "claude plugin enable admiral@admiral",
        "plugin_old": "plugin admiral@admiral is {v}, this clone is {code}",
        "fix_plugin_update": "claude plugin marketplace update admiral && claude plugin update admiral@admiral; sessions pick it up when they restart",
        "plugin_new": "plugin admiral@admiral is {v}, newer than this clone's {code}", "fix_pull": "git -C '{here}' pull",
        "claude_note": "Claude Code {v}: the sidebar needs plugin function hooks (early access); type /admiral in a session to see whether it opens",
        "health": "the board reports: {h}",
        "memory_on": "automatic memory is on: recommended off, so what a session knows comes from files you can read (\"autoMemoryEnabled\": false in {path})",
    },
    "zh": {
        "title": "Admiral 自检 {version}", "fix": "修法",
        "summary": "{fail} 项需要修，{warn} 项需要看一下", "all_set": "全部就绪",
        "fix_install": "运行 {here}/scripts/install.sh",
        "py_ok": "Python {v}（{py}）", "py_unrecorded": "{here}/.python-path 里没有记录 Python",
        "py_gone": "记录的 Python {py} 无法运行", "py_old": "记录的 Python {py} 是 {v}，需要 3.11 或更新",
        "link_ok": "admiral 已在 PATH 上（{link}）", "link_missing": "没有 {link}：会话无法直接运行 admiral",
        "link_other": "{link} 不是这份 clone 的：它指向 {to}", "fix_link": "删掉它，再运行 {here}/scripts/install.sh",
        "path_missing": "~/.local/bin 不在 PATH 上", "fix_path": "在 shell 的配置文件里把 ~/.local/bin 加进 PATH",
        "config_ok": "配置 {path}", "config_none": "没有配置文件 {path}：显示本机所有会话，没有 PR 和 CI",
        "config_broken": "配置 {path} 读取失败：{error}", "fix_config": "在 {path} 里改正",
        "dirs_all": "project_dirs 为空：显示本机所有 Claude Code 会话",
        "dir_missing": "project_dirs 里的 {d}，没有任何目录以它开头",
        "repo_none": "[github] repo_dir 为空：看板上没有 PR 和 CI",
        "fix_repo": "在 {path} 里把 [github] repo_dir 设为你的仓库",
        "repo_missing": "[github] repo_dir {d} 不存在", "repo_not_git": "[github] repo_dir {d} 不是 git 仓库",
        "gh_skipped": "没有设置仓库，跳过 gh 检查", "gh_missing": "没有安装 gh（GitHub CLI）",
        "fix_gh": "从 https://cli.github.com 安装，再 gh auth login",
        "gh_cannot": "gh 读不到 {d} 的仓库：{error}", "fix_gh_login": "gh auth login",
        "fix_gh_access": "确认你的 gh 账号能读这个仓库（在 {d} 里运行 gh repo view）",
        "gh_ok": "gh 能读到 {repo}",
        "job_ok": "后台任务 {job} 已加载", "job_missing": "后台任务 {job} 没有加载",
        "board_ok": "看板 {age}前刷新过", "board_none": "{path} 还没有看板",
        "board_stale": "看板上次刷新在 {age}前：后台任务没在运行",
        "board_error": "上次刷新失败：{error}",
        "fix_cron": "每分钟运行一次 {here}/scripts/refresh.sh（cron：* * * * * {here}/scripts/refresh.sh）",
        "fix_job": "运行 {here}/scripts/install.sh，或查看 {error}",
        "status_ok": "状态栏运行的是 Admiral", "status_none": "{path} 里没有设置状态栏",
        "status_other": "状态栏运行的是别的命令：{cmd}",
        "status_gone": "状态栏运行的 {exe} 不存在",
        "fix_status": "在 {path} 里设置 {line}",
        "fix_status_keep": "把它写进配置的 [statusline] base（之后会先运行它），再在 {path} 里设置 {line}",
        "settings_broken": "{path} 读取失败：{error}",
        "plugin_ok": "插件 admiral@admiral {v}，已启用", "claude_missing": "PATH 上没有 Claude Code（claude）",
        "fix_claude": "安装 Claude Code，或把它加进 PATH",
        "plugin_unread": "claude plugin list 失败：{error}", "plugin_missing": "没有安装插件 admiral@admiral",
        "fix_plugin": "claude plugin marketplace add '{here}' && claude plugin install admiral@admiral",
        "plugin_off": "插件 admiral@admiral 已停用", "fix_plugin_on": "claude plugin enable admiral@admiral",
        "plugin_old": "插件 admiral@admiral 是 {v}，这份 clone 是 {code}",
        "fix_plugin_update": "claude plugin marketplace update admiral && claude plugin update admiral@admiral；会话重启后生效",
        "plugin_new": "插件 admiral@admiral 是 {v}，比这份 clone 的 {code} 新", "fix_pull": "git -C '{here}' pull",
        "claude_note": "Claude Code {v}：侧边栏需要 plugin function hooks（抢先体验功能），在会话里输入 /admiral，看它能否打开",
        "health": "看板报告：{h}",
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

    def run(self, argv, cwd=None):
        """(exit status, stdout, stderr); None when the command is not found."""
        exe = shutil.which(argv[0], path=self.path)
        if not exe:
            return None
        try:
            r = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, cwd=cwd, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, "", str(e)
        return r.returncode, r.stdout, r.stderr


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


def read_settings(m):
    """(Claude Code's user settings or None when there are none, the error when they do not load)."""
    path = os.path.join(m.home, ".claude", "settings.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), ""
    except FileNotFoundError:
        return None, ""
    except (OSError, ValueError) as e:
        return None, str(e)


def check_python(m, T):
    try:
        with open(os.path.join(m.here, ".python-path"), encoding="utf-8") as fh:
            py = fh.read().strip()
    except OSError:
        py = ""
    if not py:
        return [(WARN, T["py_unrecorded"].format(here=m.here), T["fix_install"].format(here=m.here))]
    r = m.run([py, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"])
    if r is None or r[0]:
        return [(FAIL, T["py_gone"].format(py=py), T["fix_install"].format(here=m.here))]
    v = r[1].strip()
    if version(v)[:2] < (3, 11):
        return [(FAIL, T["py_old"].format(py=py, v=v), T["fix_install"].format(here=m.here))]
    return [(OK, T["py_ok"].format(v=v, py=py), "")]


def check_link(m, T):
    bindir = os.path.join(m.home, ".local", "bin")
    link = os.path.join(bindir, "admiral")
    out = []
    if not os.path.lexists(link):
        out.append((FAIL, T["link_missing"].format(link=link), T["fix_install"].format(here=m.here)))
    elif os.path.realpath(link) != os.path.realpath(os.path.join(m.here, "bin", "admiral")):
        out.append((WARN, T["link_other"].format(link=link, to=os.path.realpath(link)), T["fix_link"].format(here=m.here)))
    else:
        out.append((OK, T["link_ok"].format(link=link), ""))
    if bindir not in m.path.split(os.pathsep):
        out.append((WARN, T["path_missing"], T["fix_path"]))
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


def check_config(m, T, path):
    """(results, the config as loaded, or None when it does not load)."""
    if not os.path.exists(path):
        return [(WARN, T["config_none"].format(path=path), T["fix_install"].format(here=m.here))], config.load(path)
    try:
        cfg = config.load(path)
    except Exception as e:  # a config that does not parse, or a key of the wrong type: say which, check the rest
        return [(FAIL, T["config_broken"].format(path=path, error=first_line(str(e)) or type(e).__name__),
                 T["fix_config"].format(path=path))], None
    out = [(OK, T["config_ok"].format(path=path), "")]
    if not cfg.project_dirs:
        out.append((NOTE, T["dirs_all"], ""))
    out += [(WARN, T["dir_missing"].format(d=d), T["fix_config"].format(path=path))
            for d in cfg.project_dirs if not matches_a_directory(d)]
    if not cfg.repo_dir:
        out.append((WARN, T["repo_none"], T["fix_repo"].format(path=path)))
    elif not os.path.isdir(cfg.repo_dir):
        out.append((FAIL, T["repo_missing"].format(d=cfg.repo_dir), T["fix_repo"].format(path=path)))
    else:
        r = m.run(["git", "-C", cfg.repo_dir, "rev-parse", "--git-dir"])
        if r is not None and r[0]:
            out.append((FAIL, T["repo_not_git"].format(d=cfg.repo_dir), T["fix_repo"].format(path=path)))
    return out, cfg


def check_gh(m, T, cfg):
    if cfg is None or not cfg.repo_dir or not os.path.isdir(cfg.repo_dir):
        return [(NOTE, T["gh_skipped"], "")]
    r = m.run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=cfg.repo_dir)
    if r is None:
        return [(FAIL, T["gh_missing"], T["fix_gh"])]
    if r[0]:
        error = first_line(r[2]) or first_line(r[1])
        fix = T["fix_gh_login"] if "auth login" in r[2] + r[1] else T["fix_gh_access"].format(d=cfg.repo_dir)
        return [(FAIL, T["gh_cannot"].format(d=cfg.repo_dir, error=error), fix)]
    return [(OK, T["gh_ok"].format(repo=r[1].strip()), "")]


def check_job(m, T, cfg):
    out = []
    macos = m.platform == "darwin"
    fix = T["fix_install"].format(here=m.here) if macos else T["fix_cron"].format(here=m.here)
    if macos:
        r = m.run(["launchctl", "print", f"gui/{os.getuid()}/{JOB}"])
        if r is None or r[0]:
            out.append((FAIL, T["job_missing"].format(job=JOB), fix))
        else:
            out.append((OK, T["job_ok"].format(job=JOB), ""))
    if cfg is None:
        return out
    board, errors = cfg.sub("board.json"), cfg.sub("last-error.txt")
    try:
        with open(errors, encoding="utf-8") as fh:
            error = [ln.strip() for ln in fh if ln.strip()]
    except OSError:
        error = []
    if not os.path.exists(board):
        out.append((FAIL, T["board_none"].format(path=board), fix))
    else:
        age = m.now - os.path.getmtime(board)
        if age > STALE_S:
            out.append((FAIL, T["board_stale"].format(age=ago(age, cfg.language)),
                        T["fix_job"].format(here=m.here, error=errors) if error else fix))
        else:
            out.append((OK, T["board_ok"].format(age=ago(age, cfg.language)), ""))
    if error:
        out.append((WARN, T["board_error"].format(error=error[-1][:160]), ""))
    return out


def check_statusline(m, T, settings, broken):
    path = os.path.join(m.home, ".claude", "settings.json")
    if broken:
        return [(FAIL, T["settings_broken"].format(path=path, error=broken), T["fix_config"].format(path=path))]
    line = f'"statusLine": {{"type": "command", "command": "\'{m.here}/bin/admiral\' statusline", "refreshInterval": 20}}'
    cmd = ((settings or {}).get("statusLine") or {}).get("command", "")
    if not cmd:
        return [(FAIL, T["status_none"].format(path=path), T["fix_status"].format(path=path, line=line))]
    if "admiral" not in cmd or "statusline" not in cmd:
        return [(FAIL, T["status_other"].format(cmd=cmd), T["fix_status_keep"].format(path=path, line=line))]
    try:
        exe = shlex.split(cmd)[0]
    except (ValueError, IndexError):
        exe = ""
    if not (os.path.exists(os.path.expanduser(exe)) or shutil.which(exe, path=m.path)):
        return [(FAIL, T["status_gone"].format(exe=exe), T["fix_status"].format(path=path, line=line))]
    return [(OK, T["status_ok"], "")]


def check_plugin(m, T):
    r = m.run(["claude", "plugin", "list", "--json"])
    if r is None:
        return [(FAIL, T["claude_missing"], T["fix_claude"])]
    try:
        plugins = json.loads(r[1]) if not r[0] else None
    except ValueError:
        plugins = None
    if not isinstance(plugins, list):
        return [(WARN, T["plugin_unread"].format(error=first_line(r[2]) or first_line(r[1])), "")]
    p = next((p for p in plugins if isinstance(p, dict) and p.get("id") == "admiral@admiral"), None)
    if p is None:
        return [(FAIL, T["plugin_missing"], T["fix_plugin"].format(here=m.here))]
    if p.get("enabled") is False:
        return [(FAIL, T["plugin_off"], T["fix_plugin_on"])]
    v = str(p.get("version", ""))
    if version(v) < version(__version__):
        return [(WARN, T["plugin_old"].format(v=v, code=__version__), T["fix_plugin_update"])]
    if version(v) > version(__version__):
        return [(WARN, T["plugin_new"].format(v=v, code=__version__), T["fix_pull"].format(here=m.here))]
    return [(OK, T["plugin_ok"].format(v=v), "")]


def check_claude(m, T):
    r = m.run(["claude", "--version"])
    if r is None or r[0]:
        return []  # check_plugin has said Claude Code is missing
    return [(NOTE, T["claude_note"].format(v=r[1].split()[0] if r[1].split() else "?"), "")]


def check_health(m, T, cfg):
    try:
        with open(cfg.sub("board.json"), encoding="utf-8") as fh:
            health = json.load(fh).get("health") or []
    except (OSError, ValueError, AttributeError):
        return []
    return [(WARN, T["health"].format(h=h), "") for h in health]


def check_memory(m, T, settings):
    if settings is None or settings.get("autoMemoryEnabled") is not False:
        return [(NOTE, T["memory_on"].format(path=os.path.join(m.home, ".claude", "settings.json")), "")]
    return []


def checks(m, path):
    """(every check's (level, text, fix), the language they are in)."""
    try:
        language = config.load(path).language
    except Exception:
        language = "en"
    T = TEXT[language]
    found, cfg = check_config(m, T, path)
    settings, broken = read_settings(m)
    results = (check_python(m, T) + check_link(m, T) + found + check_gh(m, T, cfg) + check_job(m, T, cfg)
               + check_statusline(m, T, settings, broken) + check_plugin(m, T) + check_claude(m, T)
               + (check_health(m, T, cfg) if cfg else []) + check_memory(m, T, settings))
    return results, language


def main(machine=None, path=None, out=None):
    """Prints every check; the exit status: 1 when any failed, else 0."""
    m = machine or Machine(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out = out or sys.stdout
    results, language = checks(m, path or config.config_path())
    T = TEXT[language]
    out.write(T["title"].format(version=__version__) + "\n\n")
    for level, text, fix in results:
        out.write(f"{MARK[level]} {text}\n")
        if fix:
            out.write(f"    {T['fix']}{'：' if language == 'zh' else ': '}{fix}\n")
    fail, warn = (sum(r[0] == k for r in results) for k in (FAIL, WARN))
    out.write("\n" + (T["summary"].format(fail=fail, warn=warn) if fail or warn else T["all_set"]) + "\n")
    return 1 if fail else 0
