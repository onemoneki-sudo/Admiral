"""The `admiral` command end to end, on a temporary state directory."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        cfg = os.path.join(self.dir, "config.toml")
        with open(cfg, "w") as fh:
            fh.write(f'state_dir = "{self.dir}/state"\n[sessions]\ndir = "{self.dir}/sessions"\n')
        os.makedirs(os.path.join(self.dir, "sessions"))
        # not run from a session unless a test says so, wherever the tests themselves run
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        self.env.update(ADMIRAL_CONFIG=cfg, PYTHONPATH=ROOT)

    def in_session(self, pid, sid, name, former=()):
        """Run what follows from inside a Claude Code session, as Claude Code hands its commands who they run for."""
        with open(os.path.join(self.dir, "sessions", f"{pid}.json"), "w") as fh:
            json.dump({"pid": pid, "sessionId": sid, "name": name, "formerNames": [{"name": f} for f in former]}, fh)
        self.env.update(CLAUDE_CODE_SESSION_ID=sid, CLAUDE_PID=str(pid))

    def regs(self):
        d = os.path.join(self.dir, "state", "registry")
        return [json.load(open(os.path.join(d, f))) for f in sorted(os.listdir(d))] if os.path.isdir(d) else []

    def reg(self, who):
        found = [r for r in self.regs() if r["who"] == who]
        self.assertLessEqual(len(found), 1, found)
        return found[0] if found else None

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_cli(self, *argv):
        return subprocess.run([sys.executable, "-m", "admiral", *argv], capture_output=True, text=True, env=self.env)

    def test_register_phase_list_done(self):
        self.assertEqual(self.run_cli("register", "--who", "worker", "--branch", "feat/a", "--lead", "Commander-A").returncode, 0)
        self.assertEqual(self.run_cli("state", "--who", "worker", "--phase", "review").returncode, 0)
        listed = self.run_cli("list").stdout
        self.assertIn("| worker | - | feat/a | - | - | Commander-A | in review | - |", listed)
        self.assertEqual(self.run_cli("done", "--who", "worker").returncode, 0)
        self.assertNotIn("worker", self.run_cli("list").stdout)

    def test_a_session_registering_itself_is_known_by_its_session(self):
        self.in_session(41, "sid-41", "worker")
        self.assertEqual(self.run_cli("register", "--who", "worker", "--branch", "feat/a").returncode, 0)
        self.assertEqual(self.reg("worker")["sessionId"], "sid-41")

    def test_registering_another_session_records_no_session(self):
        self.in_session(40, "sid-40", "Commander-A")  # a commander registering its member
        self.run_cli("register", "--who", "worker", "--lead", "Commander-A")
        self.assertNotIn("sessionId", self.reg("worker"))

    def test_a_renamed_session_reports_under_its_new_name_and_keeps_its_registration(self):
        self.in_session(41, "sid-41", "worker")
        self.run_cli("register", "--who", "worker", "--branch", "feat/a", "--task", "the task")
        self.in_session(41, "sid-41", "worker-renamed", former=("worker",))
        r = self.run_cli("state", "--who", "worker-renamed", "--phase", "review")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNone(self.reg("worker"))  # one registration per session, under the name it has now
        moved = self.reg("worker-renamed")
        self.assertEqual((moved["branch"], moved["task"], moved["phase"]), ("feat/a", "the task", "review"))
        self.assertEqual(self.run_cli("done", "--who", "worker-renamed").returncode, 0)
        self.assertEqual(os.listdir(os.path.join(self.dir, "state", "registry")), [])

    def test_registering_again_after_a_rename_replaces_the_old_registration(self):
        self.in_session(41, "sid-41", "worker")
        self.run_cli("register", "--who", "worker", "--branch", "feat/a")
        self.run_cli("state", "--who", "worker", "--phase", "review")
        self.in_session(41, "sid-41", "worker-renamed", former=("worker",))
        self.run_cli("register", "--who", "worker-renamed", "--branch", "feat/a")
        self.assertIsNone(self.reg("worker"))
        self.assertEqual(self.reg("worker-renamed")["phase"], "review")  # what it reported is kept

    def test_a_session_registering_itself_under_another_name_is_still_known_by_its_session(self):
        self.in_session(45, "sid-45", "dev-45")  # a name it was given, registering under its task's
        r = self.run_cli("register", "--who", "the task", "--branch", "feat/a")
        self.assertEqual(self.reg("the task")["sessionId"], "sid-45")
        self.assertEqual((r.stdout.strip(), r.stderr), ("registered the task, for this session (dev-45)", ""))

    def test_registering_a_running_session_records_no_session(self):
        self.in_session(42, "sid-42", "worker")  # running, under its own name
        self.in_session(41, "sid-41", "helper")
        self.run_cli("register", "--who", "worker")
        self.assertNotIn("sessionId", self.reg("worker"))

    def test_a_commander_registering_a_member_not_yet_open_records_no_session(self):
        self.in_session(40, "sid-40", "Commander-A")
        self.run_cli("register", "--who", "worker-to-come", "--lead", "Commander-A")
        self.assertNotIn("sessionId", self.reg("worker-to-come"))

    def test_a_session_registered_as_itself_registering_another_records_no_session(self):
        self.in_session(41, "sid-41", "helper")
        self.run_cli("register", "--who", "helper")
        self.run_cli("register", "--who", "worker-to-come")  # for a session not open yet
        self.assertNotIn("sessionId", self.reg("worker-to-come"))
        self.assertEqual(self.reg("helper")["sessionId"], "sid-41")

    def test_a_renamed_session_taking_another_ones_name_touches_only_its_own(self):
        self.in_session(42, "sid-b", "new")
        self.run_cli("register", "--who", "new", "--branch", "feat/b")
        self.in_session(41, "sid-a", "old")
        self.run_cli("register", "--who", "old", "--branch", "feat/a")
        self.in_session(41, "sid-a", "new", former=("old",))  # renamed to the other one's name
        self.assertEqual(self.run_cli("state", "--who", "new", "--phase", "review").returncode, 0)
        self.run_cli("register", "--who", "new", "--branch", "feat/a2")
        by_sid = {r["sessionId"]: r for r in self.regs()}
        self.assertEqual((by_sid["sid-a"]["branch"], by_sid["sid-a"]["phase"]), ("feat/a2", "review"))
        self.assertEqual((by_sid["sid-b"]["branch"], by_sid["sid-b"]["phase"]), ("feat/b", None))
        self.run_cli("done", "--who", "new")
        self.assertEqual([r["sessionId"] for r in self.regs()], ["sid-b"])

    def test_a_new_session_registering_an_ended_ones_name_inherits_nothing(self):
        self.in_session(41, "sid-old", "worker")
        self.run_cli("register", "--who", "worker", "--branch", "feat/old")
        self.run_cli("state", "--who", "worker", "--phase", "done")
        self.in_session(43, "sid-new", "worker")
        self.run_cli("register", "--who", "worker", "--branch", "feat/new")
        new = next(r for r in self.regs() if r["sessionId"] == "sid-new")
        self.assertEqual((new["branch"], new["phase"]), ("feat/new", None))

    def test_two_processes_of_one_session_keep_one_registration(self):
        self.in_session(41, "sid-a", "old")
        self.run_cli("register", "--who", "old")
        self.in_session(44, "sid-a", "new", former=("old",))  # the same conversation, another process, renamed
        self.run_cli("register", "--who", "new")
        self.assertEqual([(r["who"], r["sessionId"]) for r in self.regs()], [("new", "sid-a")])

    def test_a_registration_made_for_it_by_name_becomes_its_own(self):
        self.run_cli("register", "--who", "worker", "--lead", "Commander-A")  # by its commander, before it opened
        self.run_cli("state", "--who", "worker", "--phase", "working")
        self.in_session(41, "sid-41", "worker")
        self.run_cli("register", "--who", "worker", "--branch", "feat/a", "--lead", "Commander-A")
        self.assertEqual([(r["who"], r.get("sessionId"), r["phase"]) for r in self.regs()], [("worker", "sid-41", "working")])

    def test_a_session_with_no_name_registering_says_whose_it_is(self):
        self.in_session(46, "sid-46abcdef", "")
        r = self.run_cli("register", "--who", "the task")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "registered the task, for this session (sid-46ab)"))

    def test_registering_again_under_its_task_name_updates_its_one_registration(self):
        self.in_session(45, "sid-45", "dev-45")
        self.run_cli("register", "--who", "task-a", "--branch", "feat/a")
        self.run_cli("state", "--who", "task-a", "--phase", "review")
        self.run_cli("register", "--who", "task-a", "--branch", "feat/b")
        self.assertEqual([(r["who"], r.get("sessionId"), r["branch"], r["phase"]) for r in self.regs()],
                         [("task-a", "sid-45", "feat/b", "review")])
        self.run_cli("done", "--who", "task-a")
        self.assertEqual(self.regs(), [])

    def test_a_new_session_reporting_under_an_ended_ones_name_touches_nothing(self):
        self.in_session(41, "sid-old", "worker")
        self.run_cli("register", "--who", "worker", "--branch", "feat/old")
        self.in_session(43, "sid-new", "worker")  # not registered yet
        r = self.run_cli("state", "--who", "worker", "--phase", "review")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not registered", r.stderr)
        self.assertEqual(self.run_cli("done", "--who", "worker").stdout.strip(), "no registration for worker")
        self.assertEqual([(r["sessionId"], r["phase"]) for r in self.regs()], [("sid-old", None)])

    def test_another_sessions_registration_under_a_former_name_is_left_alone(self):
        self.in_session(41, "sid-a", "alpha")
        self.run_cli("register", "--who", "alpha", "--branch", "feat/a")
        self.in_session(41, "sid-a", "beta", former=("alpha",))  # renamed; its old name passes to another
        self.env.pop("CLAUDE_CODE_SESSION_ID")
        self.run_cli("register", "--who", "alpha", "--branch", "feat/b")  # made by hand for the one now called alpha
        self.in_session(41, "sid-a", "beta", former=("alpha",))
        self.run_cli("register", "--who", "beta", "--branch", "feat/a")
        self.assertEqual(sorted((r["who"], r.get("sessionId"), r["branch"]) for r in self.regs()),
                         [("alpha", None, "feat/b"), ("beta", "sid-a", "feat/a")])

    def test_a_take_over_left_half_done_is_finished_by_the_next_registration(self):
        from admiral import registry
        self.run_cli("register", "--who", "worker", "--branch", "feat/a")  # made for it by name
        self.in_session(41, "sid-41", "worker")
        self.run_cli("register", "--who", "worker", "--branch", "feat/a")
        cfg = os.path.join(self.dir, "state", "registry")
        name_file = os.path.join(cfg, registry.key("worker") + ".json")
        with open(name_file, "w") as fh:  # as if removing it had failed
            json.dump({"who": "worker", "branch": "feat/a"}, fh)
        self.run_cli("register", "--who", "worker", "--branch", "feat/a")
        self.assertEqual([(r["who"], r.get("sessionId")) for r in self.regs()], [("worker", "sid-41")])

    def test_phases_are_checked(self):
        self.run_cli("register", "--who", "worker")
        self.assertNotEqual(self.run_cli("state", "--who", "worker", "--phase", "pending").returncode, 0)
        self.assertNotEqual(self.run_cli("state", "--who", "worker", "--phase", "waiting").returncode, 0)
        self.assertEqual(self.run_cli("state", "--who", "worker", "--phase", "waiting", "--note", "on #1").returncode, 0)
        self.assertEqual(self.run_cli("state", "--who", "worker", "--phase", "验收中").returncode, 0)
        self.assertNotEqual(self.run_cli("state", "--who", "worker", "--phase", "needs_you").returncode, 0)
        self.assertEqual(self.run_cli("state", "--who", "worker", "--phase", "等你", "--note", "approve").returncode, 0)
        self.assertNotEqual(self.run_cli("state", "--who", "nobody", "--phase", "working").returncode, 0)

    def test_a_re_registration_keeps_the_reported_phase(self):
        self.run_cli("register", "--who", "worker")
        self.run_cli("state", "--who", "worker", "--phase", "accepting")
        self.run_cli("register", "--who", "worker", "--branch", "feat/b")
        self.assertIn("| accepting |", self.run_cli("list").stdout)

    def test_plan_add_update_remove_close(self):
        self.run_cli("plan", "add", "--lead", "Commander-A", "--branch", "feat/a", "--title", "first")
        self.run_cli("plan", "add", "--lead", "Commander-A", "--branch", "feat/a", "--title", "renamed", "--owner", "worker")
        self.run_cli("plan", "add", "--lead", "Commander-A", "--branch", "feat/b", "--title", "second")
        listed = self.run_cli("plan", "list").stdout
        self.assertIn("feat/a  renamed  · worker", listed)
        self.assertIn("(2 deliverables)", listed)
        self.assertNotEqual(self.run_cli("plan", "rm", "--lead", "Commander-A", "--branch", "nope").returncode, 0)
        self.assertEqual(self.run_cli("plan", "close", "--lead", "Commander-A").returncode, 0)
        self.assertEqual(self.run_cli("plan", "list").stdout, "no plans\n")

    def test_the_board_prints_the_latest_snapshot_without_building(self):
        os.makedirs(os.path.join(self.dir, "state"))
        with open(os.path.join(self.dir, "state", "board.md"), "w") as fh:
            fh.write("the snapshot\n")
        self.assertEqual(self.run_cli("board").stdout, "the snapshot\n")
        self.assertIn("Admiral board", self.run_cli("board", "--now", "--no-github").stdout)
        os.utime(os.path.join(self.dir, "state", "board.md"), (0, 0))  # stale: built afresh
        self.assertNotEqual(self.run_cli("board").stdout, "the snapshot\n")

    def test_admiral_runs_through_a_symlink_and_lock_reads_the_configured_commanders(self):
        link = os.path.join(self.dir, "admiral")
        os.symlink(os.path.join(ROOT, "bin", "admiral"), link)
        commanders = os.path.join(self.dir, "commanders.txt")
        with open(commanders, "w") as fh:
            fh.write("Commander-A\n")
        with open(self.env["ADMIRAL_CONFIG"], "a") as fh:
            fh.write(f'[locks]\ndir = "{self.dir}/locks"\ncommanders = "{commanders}"\n')
        run = lambda *a: subprocess.run([link, *a], capture_output=True, text=True, env=self.env)
        self.assertEqual(run("where").stdout.strip(), os.path.join(self.dir, "state"))
        self.assertEqual(run("lock", "queue", "heavy", "--who", "w1").returncode, 0)
        self.assertNotEqual(run("lock", "prio", "heavy", "--who", "w1", "--priority", "5", "--by", "Other").returncode, 0)
        self.assertEqual(run("lock", "prio", "heavy", "--who", "w1", "--priority", "5", "--by", "Commander-A").returncode, 0)
        for n in range(30):
            run("lock", "acquire", f"lock-{n}", "--who", "w1")
        cut = subprocess.run(f"'{link}' lock status | head -1", shell=True, capture_output=True, text=True, env=self.env)
        self.assertEqual(cut.stderr, "")  # a reader that stops early ends the tool quietly

    def test_a_lock_without_a_pid_warns_it_can_be_taken_over(self):
        held = self.run_cli("lock", "acquire", "db", "--who", "w1")
        self.assertEqual(held.returncode, 0)
        self.assertIn("may be taken over", held.stderr)
        self.assertIn("admiral lock attach db", held.stderr)
        port = self.run_cli("lock", "port", "--who", "w1", "--from", "18950", "--to", "18999")
        self.assertIn("may be taken over", port.stderr)
        with_pid = self.run_cli("lock", "acquire", "heavy", "--who", "w1", "--pid", str(os.getpid()))
        self.assertEqual((with_pid.returncode, with_pid.stderr), (0, ""))

    def test_one_version_everywhere(self):
        import json
        from admiral import __version__
        self.assertEqual(self.run_cli("--version").stdout.strip(), f"admiral {__version__}")
        for agent in (".claude-plugin", ".codex-plugin"):
            with open(os.path.join(ROOT, "plugin", agent, "plugin.json")) as fh:
                self.assertEqual(json.load(fh)["version"], __version__)  # the plugin updates only when its version moves
        with open(os.path.join(ROOT, "CHANGELOG.md")) as fh:
            self.assertIn(f"## {__version__} ", fh.read())  # every version says what changed

    def test_codex_reads_its_own_hooks(self):
        import json
        # Codex reads a Claude marketplace too and parses hooks/hooks.json in its own shape, which the sidebar's
        # module list is not; its manifest comes first and names a file of its own
        with open(os.path.join(ROOT, "plugin", ".codex-plugin", "plugin.json")) as fh:
            hooks = json.load(fh)["hooks"]
        self.assertNotEqual(os.path.normpath(hooks), os.path.join("hooks", "hooks.json"))
        with open(os.path.join(ROOT, "plugin", hooks)) as fh:
            self.assertLessEqual(set(json.load(fh)), {"description", "hooks"})

    @unittest.skipUnless(os.path.exists("/usr/bin/python3") and subprocess.run(
        ["/usr/bin/python3", "-c", "import sys; sys.exit(sys.version_info >= (3, 11))"]).returncode == 0,
        "no Python older than 3.11 at /usr/bin/python3")
    def test_an_old_python_is_named_plainly(self):
        env = dict(self.env, ADMIRAL_PYTHON="/usr/bin/python3")
        r = subprocess.run([os.path.join(ROOT, "bin", "admiral"), "where"], capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Admiral needs Python 3.11 or newer", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_the_demo_fleet_shows_every_part_of_the_board(self):
        import json
        for _ in range(2):  # a second run starts afresh
            r = self.run_cli("demo", "--once")
            self.assertEqual(r.returncode, 0, r.stderr)
        demo = os.path.join(self.dir, "state", "demo")
        self.assertIn(os.path.join(demo, "config.toml"), r.stdout)
        with open(os.path.join(demo, "state", "board.json")) as fh:
            b = json.load(fh)
        self.assertEqual(b["count"], 54)
        self.assertEqual(len(b["groups"]), 7)
        self.assertEqual(sorted(x["waitKind"] for x in b["waiting"]), ["blocked"] * 2 + ["maybe"] * 2 + ["reported"] * 2)
        self.assertEqual({k: len(v) for k, v in b["closable"].items()}, {"close": 4, "wrapup": 2, "confirm": 2})
        self.assertEqual(sum(x["ciLevel"] == "fail" for g in b["groups"] for x in g["members"])
                         + sum(x["ciLevel"] == "fail" for x in b["unassigned"]), 4)
        self.assertFalse(b["health"])
        self.assertFalse([h for h in b["hints"] if "worktree" in h])  # every worktree that should be there is
        env = dict(self.env, ADMIRAL_CONFIG=os.path.join(demo, "config.toml"), COLUMNS="170")
        line = subprocess.run([sys.executable, "-m", "admiral", "statusline"], input="{}", capture_output=True,
                              text=True, env=env).stdout
        self.assertIn("54 sessions", line)
        self.assertIn("1 more commander: /admiral shows all", line)

    def test_the_demo_shows_its_status_line_and_how_to_try_it_without_installing(self):
        import json
        import shlex
        r = self.run_cli("demo", "--once")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("54 sessions", r.stdout)  # the status line, right there
        words = shlex.split(next(ln for ln in r.stdout.splitlines() if " claude " in ln))
        demo_cfg = os.path.join(self.dir, "state", "demo", "config.toml")
        self.assertEqual(words[:2], ["ADMIRAL_CONFIG=" + demo_cfg, "claude"])
        self.assertEqual(words[words.index("--plugin-dir") + 1], os.path.join(ROOT, "plugin"))
        command = json.loads(words[words.index("--settings") + 1])["statusLine"]["command"]
        self.assertEqual(shlex.split(command), [os.path.join(ROOT, "bin", "admiral"), "statusline"])
        env = dict(self.env, ADMIRAL_CONFIG=demo_cfg, COLUMNS="170")  # that status line, as Claude Code runs it
        line = subprocess.run(["/bin/sh", "-c", command], input="{}", capture_output=True, text=True, env=env).stdout
        self.assertIn("54 sessions", line)

    def test_the_demo_config_reads_back_whatever_the_path(self):
        from admiral import config, demo
        root = os.path.join(self.dir, "home-🚢 \"q\" \\ \x7f é")
        os.makedirs(root)
        cfg = config.load(demo.write_config(root, "en", "base \t🚢"))
        self.assertEqual((cfg.state_dir, cfg.statusline_base), (os.path.join(root, "state"), "base \t🚢"))

    def test_without_a_clone_the_demo_says_what_the_session_needs(self):
        from admiral import demo
        self.assertEqual(demo.try_command("/x/config.toml", root=self.dir), ("ADMIRAL_CONFIG=/x/config.toml claude", False))
        self.assertTrue(demo.try_command("/x/config.toml")[1])  # this clone has its plugin and bin/admiral

    def test_the_demo_fleet_speaks_chinese(self):
        import json
        r = self.run_cli("demo", "--once", "--lang", "zh")
        self.assertEqual(r.returncode, 0, r.stderr)
        demo = os.path.join(self.dir, "state", "demo")
        with open(os.path.join(demo, "state", "board.json"), encoding="utf-8") as fh:
            b = json.load(fh)
        self.assertEqual((b["count"], len(b["groups"]), b["language"]), (54, 7, "zh"))
        self.assertIn("总指挥-结账", [g["lead"] for g in b["groups"]])
        self.assertEqual(sorted(x["waitKind"] for x in b["waiting"]), ["blocked"] * 2 + ["maybe"] * 2 + ["reported"] * 2)
        env = dict(self.env, ADMIRAL_CONFIG=os.path.join(demo, "config.toml"), COLUMNS="170")
        line = subprocess.run([sys.executable, "-m", "admiral", "statusline"], input="{}", capture_output=True,
                              text=True, env=env).stdout
        self.assertIn("共 54 对话", line)
        self.assertIn("  结账  ", line)  # the commander prefix is left off its line

    def test_a_board_without_github_is_never_published(self):
        self.assertNotEqual(self.run_cli("board", "--write", "--no-github").returncode, 0)

    def test_the_board_prints_with_no_session_and_no_config_file(self):
        env = dict(self.env, ADMIRAL_CONFIG=os.path.join(self.dir, "missing.toml"), HOME=self.dir)
        r = subprocess.run([sys.executable, "-m", "admiral", "board", "--no-github"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Admiral board (0 running)", r.stdout)
        self.assertIn("Built just now", r.stdout)  # built for this command, not the background job's snapshot


if __name__ == "__main__":
    unittest.main()
