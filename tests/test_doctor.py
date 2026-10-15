"""`admiral doctor` on a made-up machine: a temporary home, clone, config and board, and a Machine whose commands are
answered here. Nothing on the real machine is read or run, but for the one end-to-end run of the command.

    python3 -m unittest discover -s tests
"""

import io
import json
import os
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

    def run(self, argv, cwd=None):
        self.ran.append(list(argv))
        for prefix, answer in self.answers.items():
            if tuple(argv[:len(prefix)]) == prefix:
                return answer
        return None  # not installed


class Doctor(unittest.TestCase):
    language = "en"

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.here, self.home = self.dir("admiral"), self.dir("home")
        self.repo, self.state = self.dir("code/shop"), self.dir("state")
        self.write("admiral/bin/admiral", "#!/bin/sh\n")
        self.write("admiral/.python-path", "/py/python3\n")
        os.makedirs(os.path.join(self.home, ".local", "bin"))
        os.symlink(os.path.join(self.here, "bin", "admiral"), os.path.join(self.home, ".local", "bin", "admiral"))
        self.settings({"statusLine": {"type": "command", "command": f"'{self.here}/bin/admiral' statusline"},
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
        self.write("home/.claude/settings.json", json.dumps(data))

    def config(self, text):
        self.config_path = self.write("config.toml", text)

    def board(self, age, health=(), error=""):
        path = self.write("state/board.json", json.dumps({"health": list(health)}))
        os.utime(path, (time.time() - age, time.time() - age))
        self.write("state/last-error.txt", error)

    def doctor(self):
        """(exit status, what it printed)."""
        m = FakeMachine(self.answers, here=self.here, home=self.home, platform=self.platform,
                        path=os.pathsep.join([os.path.join(self.home, ".local", "bin"), "/usr/bin"]))
        out, self.machine = io.StringIO(), m
        return doctor.main(m, self.config_path, out), out.getvalue()


class Checks(Doctor):
    def test_a_complete_setup_is_all_set(self):
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        marks = [ln[0] for ln in out.splitlines()[2:-2] if ln and not ln.startswith(" ")]
        self.assertEqual(set(marks), {"✓", "·"}, out)  # the one note: what the sidebar needs, not checkable here
        self.assertTrue(out.rstrip().endswith("all set"))
        self.assertIn("✓ gh reads acme/shop", out)

    def fails(self, line, fix=None):
        code, out = self.doctor()
        self.assertEqual(code, 1, out)
        self.assertIn("✗ " + line, out)
        if fix:
            self.assertIn("    fix: " + fix, out)
        return out

    def test_gh_missing_or_signed_out(self):
        self.answers[("gh", "repo", "view")] = (1, "", "To get started with GitHub CLI, please run:  gh auth login\n")
        self.fails(f"gh cannot read the repository in {self.repo}: To get started with GitHub CLI", "gh auth login")
        del self.answers[("gh", "repo", "view")]
        self.fails("gh (the GitHub CLI) is not installed", "install it from https://cli.github.com")

    def test_a_background_job_not_loaded_or_a_stale_board(self):
        self.answers[("launchctl",)] = (113, "", "Could not find service")
        self.fails("background job com.admiral.board not loaded", f"run {self.here}/scripts/install.sh")
        self.board(age=600, error="Traceback\nRuntimeError: gh is not signed in\n")
        out = self.fails("board last refreshed 10 min ago: the background job is not running")
        self.assertIn("! the last refresh failed: RuntimeError: gh is not signed in", out)

    def test_elsewhere_than_macos_the_job_is_one_to_schedule(self):
        self.platform = "linux"
        os.remove(os.path.join(self.state, "board.json"))
        out = self.fails(f"no board yet at {self.state}/board.json", f"run {self.here}/scripts/refresh.sh every minute")
        self.assertNotIn("launchctl", json.dumps(out))

    def test_a_status_line_not_set_or_set_to_another_command(self):
        self.settings({})
        line = f"\"statusLine\": {{\"type\": \"command\", \"command\": \"'{self.here}/bin/admiral' statusline\""
        out = self.fails(f"no status line set in {self.home}/.claude/settings.json")
        self.assertIn(line, out)
        self.settings({"statusLine": {"command": "npx claude-hud"}})
        self.fails("the status line runs something else: npx claude-hud", "keep it as [statusline] base")
        self.settings({"statusLine": {"command": "'/gone/bin/admiral' statusline"}})
        self.fails("the status line runs /gone/bin/admiral, which does not exist")

    def test_the_plugin_missing_disabled_or_behind(self):
        self.answers[("claude", "plugin", "list")] = (0, "[]", "")
        self.fails("plugin admiral@admiral not installed", f"claude plugin marketplace add '{self.here}'")
        self.answers[("claude", "plugin", "list")] = (0, json.dumps([{"id": "admiral@admiral", "version": __version__,
                                                                      "enabled": False}]), "")
        self.fails("plugin admiral@admiral is disabled", "claude plugin enable admiral@admiral")
        self.answers[("claude", "plugin", "list")] = (0, json.dumps([{"id": "admiral@admiral", "version": "0.1.0",
                                                                      "enabled": True}]), "")
        code, out = self.doctor()
        self.assertEqual(code, 0)  # an old plugin still works: a warning, with the update
        self.assertIn(f"! plugin admiral@admiral is 0.1.0, this clone is {__version__}", out)
        self.assertIn("claude plugin update admiral@admiral", out)

    def test_claude_code_missing(self):
        del self.answers[("claude", "plugin", "list")], self.answers[("claude", "--version")]
        self.fails("Claude Code (claude) is not on the PATH")

    def test_a_config_that_does_not_load_is_reported_and_the_rest_still_checked(self):
        self.config("language = \n")
        out = self.fails(f"config {self.config_path} does not load")
        self.assertIn("✓ status line runs Admiral", out)
        self.assertIn("✓ plugin admiral@admiral", out)

    def test_no_repository_means_no_github_and_no_gh_check(self):
        self.config(f'state_dir = "{self.state}"\n')
        code, out = self.doctor()
        self.assertEqual(code, 0)
        self.assertIn("! [github] repo_dir is empty: no PR or CI on the board", out)
        self.assertIn("· gh not checked: no repository set", out)
        self.assertFalse([c for c in self.machine.ran if c[:1] == ["gh"]])

    def test_project_dirs_match_as_prefixes(self):
        self.dir("code/shop-worktrees")
        self.config(f'state_dir = "{self.state}"\n[sessions]\nproject_dirs = ["{self.root}/code/shop-wo", '
                    f'"{self.root}/code/nothing"]\n[github]\nrepo_dir = "{self.repo}"\n')
        code, out = self.doctor()
        self.assertNotIn("shop-wo, and no directory", out)
        self.assertIn(f"! project_dirs names {self.root}/code/nothing, and no directory starts with it", out)

    def test_the_boards_own_source_problems_are_passed_on(self):
        self.board(age=30, health=["gh failed: no PR or CI this time"])
        self.assertIn("! the board reports: gh failed: no PR or CI this time", self.doctor()[1])

    def test_automatic_memory_on_is_a_note(self):
        self.settings({"statusLine": {"command": f"'{self.here}/bin/admiral' statusline"}})
        code, out = self.doctor()
        self.assertEqual(code, 0)
        self.assertIn("· automatic memory is on", out)

    def test_it_changes_nothing(self):
        before = {os.path.join(d, f): os.path.getmtime(os.path.join(d, f))
                  for d, _, fs in os.walk(self.root) for f in fs}
        self.doctor()
        after = {os.path.join(d, f): os.path.getmtime(os.path.join(d, f))
                 for d, _, fs in os.walk(self.root) for f in fs}
        self.assertEqual(before, after)


class Chinese(Doctor):
    language = "zh"

    def test_it_speaks_the_configured_language(self):
        self.answers[("claude", "plugin", "list")] = (0, "[]", "")
        code, out = self.doctor()
        self.assertTrue(out.startswith("Admiral 自检"))
        self.assertIn("✗ 没有安装插件 admiral@admiral", out)
        self.assertIn("    修法：claude plugin marketplace add", out)
        self.assertIn("1 项需要修，0 项需要看一下", out)


class Command(unittest.TestCase):
    def test_a_broken_config_does_not_stop_the_command(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        with open(os.path.join(d, "config.toml"), "w") as fh:
            fh.write("language = \n")
        r = subprocess.run([sys.executable, "-m", "admiral", "doctor"], capture_output=True, text=True,
                           env=dict(os.environ, ADMIRAL_CONFIG=os.path.join(d, "config.toml"), PYTHONPATH=ROOT))
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("does not load", r.stdout)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
