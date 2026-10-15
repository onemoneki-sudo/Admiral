"""`admiral doctor` on a made-up machine: a temporary home, clone, config and board, and a Machine whose commands are
answered here. Nothing on the real machine is read or run, but for the one end-to-end run of the command.

    python3 -m unittest discover -s tests
"""

import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from admiral import __version__, doctor  # noqa: E402


class FakeMachine(doctor.Machine):
    def __init__(self, answers, **kw):
        super().__init__(**kw)
        self.answers, self.ran = answers, []

    def run(self, argv, cwd=None, input=None):
        self.ran.append(list(argv))
        if argv[0] == "/bin/sh":  # the status line runs for real, in the made-up home and PATH
            return super().run(argv, cwd, input)
        for prefix, answer in self.answers.items():
            if tuple(argv[:len(prefix)]) == prefix:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        return None  # not installed


class Doctor(unittest.TestCase):
    language = "en"
    clone = "admiral"

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.here, self.home = self.dir(self.clone), self.dir("home")
        self.repo, self.state = self.dir("code/shop"), self.dir("state")
        exe = self.write(f"{self.clone}/bin/admiral", '#!/bin/sh\n[ "$1" = statusline ] && echo "Admiral  20 working"\n')
        os.chmod(exe, 0o755)
        self.write(f"{self.clone}/.python-path", "/py/python3\n")
        os.makedirs(os.path.join(self.home, ".local", "bin"))
        os.symlink(exe, os.path.join(self.home, ".local", "bin", "admiral"))
        self.settings({"statusLine": {"type": "command", "command": f"{shlex.quote(exe)} statusline"},
                       "autoMemoryEnabled": False})
        self.config(f'language = "{self.language}"\nstate_dir = "{self.state}"\n'
                    f'[sessions]\nproject_dirs = ["{self.repo}"]\n[github]\nrepo_dir = "{self.repo}"\n')
        self.board(age=30)
        self.answers = {
            ("/py/python3",): (0, "3.12.1\n", ""),
            ("git",): (0, ".git\n", ""),
            ("gh", "repo", "view"): (0, "acme/shop\n", ""),
            ("launchctl",): (0, "", ""),
            ("claude", "plugin", "list"): (0, json.dumps([{"id": "admiral@admiral", "version": __version__,
                                                           "enabled": True}]), ""),
            ("claude", "--version"): (0, "2.1.300 (Claude Code)\n", ""),
        }
        self.platform = "darwin"

    def dir(self, rel):
        path = os.path.join(self.root, rel)
        os.makedirs(path, exist_ok=True)
        return path

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def settings(self, data):
        self.write("home/.claude/settings.json", data if isinstance(data, str) else json.dumps(data))

    def statusline(self, command):
        self.settings({"statusLine": {"type": "command", "command": command}, "autoMemoryEnabled": False})

    def config(self, text):
        self.config_path = self.write("config.toml", text)

    def board(self, age, health=(), error=""):
        path = self.write("state/board.json", json.dumps({"health": list(health)}))
        os.utime(path, (time.time() - age, time.time() - age))
        self.write("state/last-error.txt", error)

    def doctor(self):
        """(exit status, what it printed)."""
        self.machine = FakeMachine(self.answers, here=self.here, home=self.home, platform=self.platform,
                                   path=os.pathsep.join([os.path.join(self.home, ".local", "bin"), "/usr/bin"]))
        out = io.StringIO()
        return doctor.main(self.machine, self.config_path, out), out.getvalue()

    def fails(self, line, fix=None, cmd=None):
        code, out = self.doctor()
        self.assertEqual(code, 1, out)
        self.assertIn("✗ " + line, out)
        if fix:
            self.assertIn("    fix: " + fix, out)
        if cmd:
            self.assertIn("    $ " + cmd, out)
        return out

    def cron_given(self):
        """What crontab is given when the cron fix doctor prints on Linux is pasted into a shell."""
        self.platform = "linux"
        os.remove(os.path.join(self.state, "board.json"))
        cmd = next(ln[6:] for ln in self.doctor()[1].splitlines() if "crontab -" in ln)
        fake = self.dir("fakecron")  # a crontab that keeps what it is given
        self.write("fakecron/crontab", f'#!/bin/sh\n[ "$1" = - ] && cat > {shlex.quote(fake)}/given || exit 1\n')
        os.chmod(os.path.join(fake, "crontab"), 0o755)
        subprocess.run(["/bin/sh", "-c", cmd], env=dict(os.environ, PATH=fake + os.pathsep + "/usr/bin:/bin"), check=True)
        with open(os.path.join(fake, "given"), encoding="utf-8") as fh:
            return fh.read()

    def install(self):
        return shlex.quote(os.path.join(self.here, "scripts", "install.sh"))


class Checks(Doctor):
    def test_a_complete_setup_is_all_set_and_asks_github_once(self):
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        marks = [ln[0] for ln in out.splitlines()[2:-2] if ln and not ln.startswith(" ")]
        self.assertEqual(set(marks), {"✓", "·"}, out)  # the one note: what the sidebar needs, not checkable here
        self.assertTrue(out.rstrip().endswith("all set"))
        self.assertIn("✓ gh reads acme/shop", out)
        self.assertEqual([c for c in self.machine.ran if c[0] == "gh"],
                         [["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]])

    def test_gh_missing_signed_out_offline_or_without_access(self):
        for said, fix, cmd in (("To get started with GitHub CLI, please run:  gh auth login", "sign gh in again",
                                "gh auth login"),
                               ("HTTP 401: Bad credentials (https://api.github.com/graphql)", "sign gh in again",
                                "gh auth login"),
                               ("error connecting to api.github.com", "check the network or the proxy", None),
                               ("GraphQL: Resource not accessible by personal access token (repository)",
                                "check that your gh account can read this repository",
                                f"cd {shlex.quote(self.repo)} && gh repo view"),
                               ("GraphQL: Could not resolve to a Repository with the name 'acme/shop'.",
                                "check that your gh account can read this repository",
                                f"cd {shlex.quote(self.repo)} && gh repo view")):
            with self.subTest(said=said):
                self.answers[("gh", "repo", "view")] = (1, "", said + "\n")
                self.fails(f"gh cannot read the repository in {self.repo}: {said}", fix, cmd)
        del self.answers[("gh", "repo", "view")]
        self.fails("gh (the GitHub CLI) is not installed", "install it from https://cli.github.com", "gh auth login")

    def test_a_background_job_not_loaded_or_a_stale_board(self):
        self.answers[("launchctl",)] = (113, "", "Could not find service")
        self.fails("background job com.admiral.board not loaded", "run the install script again", self.install())
        self.board(age=600, error="Traceback\nRuntimeError: gh is not signed in\n")
        out = self.fails("board last refreshed 10 min ago: the background job is not running",
                         f"it failed: read {self.state}/last-error.txt; then run the install script again")

    def test_a_board_or_an_error_file_that_cannot_be_read_is_a_failed_check(self):
        self.write("state/board.json", "{invalid")
        self.fails(f"{self.state}/board.json is there but cannot be read", "the background job writes it each minute")
        self.write("state/board.json", "[]")
        self.fails(f"{self.state}/board.json is there but cannot be read: not a JSON object")
        self.board(age=30)
        os.remove(os.path.join(self.state, "last-error.txt"))
        os.mkdir(os.path.join(self.state, "last-error.txt"))
        self.fails(f"{self.state}/last-error.txt is there but cannot be read")

    def test_a_config_that_is_not_utf8_is_reported_and_the_rest_still_checked(self):
        with open(self.config_path, "wb") as fh:
            fh.write(b'language = "zh"\n#\xff\n')
        out = self.fails(f"config {self.config_path} does not load")
        self.assertIn("✓ plugin admiral@admiral", out)

    def test_an_error_the_last_refresh_left_says_what_to_do(self):
        self.board(age=30, error="PermissionError: cannot write board\n")
        code, out = self.doctor()
        self.assertIn("! the last refresh wrote an error: PermissionError: cannot write board", out)
        self.assertIn(f"    fix: read {self.state}/last-error.txt", out)

    def test_elsewhere_than_macos_the_job_is_one_to_schedule(self):
        self.platform = "linux"
        refresh = shlex.quote(os.path.join(self.here, "scripts", "refresh.sh"))
        os.remove(os.path.join(self.state, "board.json"))
        out = self.fails(f"no board yet at {self.state}/board.json", "run it every minute from cron or a systemd timer")
        self.assertIn(f"    $ (crontab -l 2>/dev/null; printf '%s\\n' {shlex.quote('* * * * * ' + refresh)}) | crontab -", out)
        self.assertFalse([c for c in self.machine.ran if c[0] == "launchctl"])
        self.board(age=600, error="RuntimeError: gh is not signed in\n")
        out = self.fails("board last refreshed 10 min ago")
        self.assertIn(f"it failed: read {self.state}/last-error.txt; then run it every minute from cron", out)

    def test_a_status_line_not_set_or_set_to_another_command(self):
        exe = os.path.join(self.here, "bin", "admiral")
        line = '"statusLine": {"type": "command", "command": ' + json.dumps(f"{shlex.quote(exe)} statusline")
        self.settings({})
        self.assertIn(line, self.fails(f"no status line set in {self.home}/.claude/settings.json"))
        self.statusline("npx claude-hud")
        self.fails("the status line does not run admiral statusline: npx claude-hud", "keep the command it runs now")

    def test_the_status_line_is_read_as_the_shell_reads_it(self):
        exe = os.path.join(self.here, "bin", "admiral")
        for cmd, ok in ((f"'{exe}' statusline", True),
                        (f"ADMIRAL_CONFIG=/x/config.toml '{exe}' statusline", True),
                        (f"/bin/echo hud; '{exe}' statusline", True),
                        ("admiral statusline", True),  # on the PATH, through ~/.local/bin
                        ("/bin/echo claude-hud; /missing/admiral statusline", False),
                        ("'~/.local/bin/admiral' statusline", False),  # quoted: the shell does not expand ~
                        ("PATH=~/.local/bin admiral statusline", True),  # this ~ the shell expands
                        ("PATH='$PATH' admiral statusline", False),  # a PATH of the four letters $PATH
                        ('"$HOME/.local/bin/admiral" statusline', True),
                        ("/bin/echo admiral statusline", False),
                        (f"'{exe}' board", False),
                        (f"/bin/echo claude-hud\n'{exe}' statusline", True),  # a newline ends a command
                        (f"/bin/echo ';' '{exe}' statusline", False),  # a quoted ; is an argument
                        ("PATH=/nonexistent admiral statusline", False),  # the PATH it runs with has no admiral
                        ("/bin/echo '~'; ~/.local/bin/admiral statusline", True),  # this ~ is not quoted
                        (f"'{exe}' statusline \\\n  # the line goes on\n", True)):
            with self.subTest(cmd=cmd):
                self.statusline(cmd)
                code, out = self.doctor()
                self.assertEqual("✓ status line runs Admiral" in out, ok, out)
                self.assertEqual(code, 0 if ok else 1)

    def test_settings_of_the_wrong_shape_are_reported_and_the_rest_still_checked(self):
        for data in ('{"statusLine": "admiral statusline"}', '{"statusLine": {"command": 1}}', "[1, 2]", "{"):
            with self.subTest(data=data):
                self.settings(data)
                code, out = self.doctor()
                self.assertEqual(code, 1, out)
                self.assertIn(f"{self.home}/.claude/settings.json", out)
                self.assertIn("✓ plugin admiral@admiral", out)
                self.assertNotIn("could not run", out)

    def test_the_plugin_missing_disabled_or_behind(self):
        self.answers[("claude", "plugin", "list")] = (0, "[]", "")
        self.fails("plugin admiral@admiral not installed", "add Admiral's marketplace and install the plugin",
                   f"claude plugin marketplace add {shlex.quote(self.here)} && claude plugin install admiral@admiral")
        self.answers[("claude", "plugin", "list")] = (0, json.dumps([{"id": "admiral@admiral", "version": __version__,
                                                                      "enabled": False}]), "")
        self.fails("plugin admiral@admiral is disabled", "enable it", "claude plugin enable admiral@admiral")
        self.answers[("claude", "plugin", "list")] = (0, json.dumps([{"id": "admiral@admiral", "version": "0.1.0",
                                                                      "enabled": True}]), "")
        code, out = self.doctor()
        self.assertEqual(code, 0)  # an old plugin still works: a warning, with the update
        self.assertIn(f"! plugin admiral@admiral is 0.1.0, this clone is {__version__}", out)
        self.assertIn("    $ claude plugin marketplace update admiral && claude plugin update admiral@admiral\n", out)

    def test_a_plugin_list_that_fails_or_does_not_parse_is_a_failed_check(self):
        for answer, said in (((1, "", "error: unknown option '--json'"), "error: unknown option '--json'"),
                             ((0, "{invalid", ""), "{invalid")):
            with self.subTest(answer=answer):
                self.answers[("claude", "plugin", "list")] = answer
                out = self.fails(f"claude plugin list failed: {said}", "update Claude Code", "claude update")

    def test_claude_code_missing_or_its_version_unread(self):
        self.answers[("claude", "--version")] = (1, "", "segfault")
        out = self.fails("claude --version failed: segfault", "update Claude Code", "claude update")
        self.assertIn("· Claude Code ?: the sidebar needs plugin function hooks", out)
        del self.answers[("claude", "plugin", "list")], self.answers[("claude", "--version")]
        self.fails("Claude Code (claude) is not on the PATH")

    def test_a_config_that_does_not_load_is_reported_and_the_rest_still_checked(self):
        self.config("language = \n")
        out = self.fails(f"config {self.config_path} does not load")
        self.assertIn("✓ status line runs Admiral", out)
        self.assertIn("✓ plugin admiral@admiral", out)

    def test_a_config_value_of_the_wrong_kind_is_reported(self):
        self.config(f'state_dir = "{self.state}"\n[sessions]\nproject_dirs = "/"\n[github]\nrepo_dir = 42\n')
        out = self.fails("config sessions.project_dirs must be a list of strings, like [\"~/code/app\"]")
        self.assertIn("✗ config github.repo_dir must be a string", out)

    def test_no_repository_means_no_github_and_no_gh_check(self):
        self.config(f'state_dir = "{self.state}"\n')
        code, out = self.doctor()
        self.assertEqual(code, 0)
        self.assertIn("! [github] repo_dir is empty: no PR or CI on the board", out)
        self.assertIn("· gh not checked: no repository set", out)
        self.assertFalse([c for c in self.machine.ran if c[0] == "gh"])

    def test_project_dirs_match_as_prefixes(self):
        self.dir("code/shop-worktrees")
        self.config(f'state_dir = "{self.state}"\n[sessions]\nproject_dirs = ["{self.root}/code/shop-wo", '
                    f'"{self.root}/code/nothing"]\n[github]\nrepo_dir = "{self.repo}"\n')
        code, out = self.doctor()
        self.assertNotIn("shop-wo, and no directory", out)
        self.assertIn(f"! project_dirs names {self.root}/code/nothing, and no directory starts with it", out)

    def test_the_boards_own_source_problems_are_passed_on(self):
        self.board(age=30, health=["gh failed: no PR or CI this time"])
        out = self.doctor()[1]
        self.assertIn("! the board reports: gh failed: no PR or CI this time", out)
        self.assertIn(f"    $ git -C {shlex.quote(self.here)} pull", out)

    def test_automatic_memory_on_is_a_note(self):
        self.settings({"statusLine": {"command": f"{shlex.quote(os.path.join(self.here, 'bin', 'admiral'))} statusline"}})
        code, out = self.doctor()
        self.assertEqual(code, 0)
        self.assertIn("· automatic memory is on", out)

    def test_a_check_that_goes_wrong_is_a_failure_and_the_others_still_run(self):
        self.answers[("launchctl",)] = RuntimeError("launchd is gone")
        out = self.fails("the job check could not run: RuntimeError: launchd is gone")
        self.assertIn("✓ status line runs Admiral", out)

    def test_it_changes_nothing(self):
        before = {os.path.join(d, f): os.path.getmtime(os.path.join(d, f))
                  for d, _, fs in os.walk(self.root) for f in fs}
        self.doctor()
        after = {os.path.join(d, f): os.path.getmtime(os.path.join(d, f))
                 for d, _, fs in os.walk(self.root) for f in fs}
        self.assertEqual(before, after)


class SpacedClone(Doctor):
    clone = "my tools 100%/admiral"

    def test_commands_quote_a_path_with_a_space(self):
        self.answers[("launchctl",)] = (113, "", "")
        self.answers[("claude", "plugin", "list")] = (0, "[]", "")
        out = self.doctor()[1]
        self.assertIn(f"    $ '{self.here}/scripts/install.sh'\n", out)
        self.assertIn(f"    $ claude plugin marketplace add '{self.here}' && claude plugin install admiral@admiral\n", out)

    def test_the_cron_command_adds_one_line_cron_reads_as_the_path(self):
        refresh = os.path.join(self.here, "scripts", "refresh.sh")
        self.assertEqual(self.cron_given(), "* * * * * '" + refresh.replace("%", "\\%") + "'\n")  # % as cron needs


class BackslashedClone(Doctor):
    clone = "tools\\new/admiral"  # echo would read \n as a newline

    def test_a_backslash_in_the_path_survives_the_cron_command(self):
        self.assertEqual(self.cron_given(), f"* * * * * '{self.here}/scripts/refresh.sh'\n")


class Chinese(Doctor):
    language = "zh"

    def test_it_speaks_the_configured_language(self):
        self.answers[("claude", "plugin", "list")] = (0, "[]", "")
        code, out = self.doctor()
        self.assertTrue(out.startswith("Admiral 自检"))
        self.assertIn("✗ 没有安装插件 admiral@admiral", out)
        self.assertIn("    修法：添加 Admiral 的 marketplace 并安装插件\n    $ claude plugin marketplace add", out)
        self.assertIn("1 项需要修，0 项需要看一下", out)

    def test_another_key_of_the_wrong_kind_keeps_the_language(self):
        self.config(f'language = "zh"\nstate_dir = "{self.state}"\n[github]\nrepo_dir = 42\n')
        code, out = self.doctor()
        self.assertTrue(out.startswith("Admiral 自检"), out)
        self.assertIn("✗ 配置 github.repo_dir 应该是字符串", out)


class Command(unittest.TestCase):
    def test_a_broken_config_does_not_stop_the_command(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        with open(os.path.join(d, "config.toml"), "w") as fh:
            fh.write("language = \n")
        os.mkdir(os.path.join(d, "bin"))  # an empty PATH: no gh, claude or launchctl of the real machine runs
        r = subprocess.run([sys.executable, "-m", "admiral", "doctor"], capture_output=True, text=True,
                           env=dict(os.environ, ADMIRAL_CONFIG=os.path.join(d, "config.toml"), PYTHONPATH=ROOT,
                                    HOME=d, PATH=os.path.join(d, "bin")))
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("does not load", r.stdout)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
