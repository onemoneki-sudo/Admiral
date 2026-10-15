"""The status line, from a fixture board snapshot."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from admiral import statusline  # noqa: E402
from admiral.words import words  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(s):
    return ANSI.sub("", s)


def row(name, sid, status="idle", commander=False, stage=0, ci="none", pr=None, lead="", registered=True):
    return {"name": name, "sessionId": sid, "status": status, "isCommander": commander, "stage": stage,
            "ciLevel": ci, "ci": "tests (1)" if ci == "fail" else "", "pr": pr, "lead": lead,
            "registered": registered, "phase": None, "note": ""}


def board(language="en", **over):
    cmd = row("Commander-A", "s1", commander=True)
    workers = [row("one", "s3", status="busy", stage=4, ci="fail", pr={"label": "#7 in review"}, lead="Commander-A"),
               row("two", "s4", status="waiting", stage=1, lead="Commander-A")]
    s = {"total": 2, "done": 0, "dist": [0, 1, 0, 0, 1, 0], "pct": 53, "items": 0, "itemsDone": 0,
         "prsMerged": 0, "prs": 1, "busy": 1, "waiting": 1, "ciFail": 1}
    b = {"generated": time.time(), "count": 3, "language": language, "words": words(language),
         "commanderPrefix": "Commander", "dist": [0, 1, 0, 0, 1, 0], "pct": 53, "prsMerged": 0, "prs": 1, "mine": None,
         "groups": [{"lead": "Commander-A", "leadRow": cmd, "members": workers, "summary": s}],
         "unassigned": [], "waiting": [workers[1]], "closable": {"close": [], "wrapup": [], "confirm": []}, "health": []}
    b.update(over)
    return b


class Main(unittest.TestCase):
    """`admiral statusline` as Claude Code runs it: a process reading the session's JSON."""

    def run_line(self, base="", **env):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config.toml")
            with open(cfg, "w", encoding="utf-8") as fh:
                fh.write(f'state_dir = "{d}"\n[statusline]\nbase = {json.dumps(base)}\n')
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            r = subprocess.run([sys.executable, "-m", "admiral", "statusline"], input='{"session_id": ""}',
                               capture_output=True, text=True, timeout=20,
                               env=dict(os.environ, PYTHONPATH=root, ADMIRAL_CONFIG=cfg, **env))
            return r.returncode, r.stdout

    def test_it_leaves_the_mark_doctor_asks_for(self):
        with tempfile.TemporaryDirectory() as d:
            probe = os.path.join(d, "ran")
            self.run_line(ADMIRAL_PROBE=probe)
            self.assertTrue(os.path.exists(probe))

    def test_a_base_that_runs_admiral_again_never_draws_admiral_inside_admiral(self):
        code, out = self.run_line(base="printenv ADMIRAL_IN_BASE")  # the base runs knowing it is one
        self.assertEqual((code, out.splitlines()[0]), (0, "1"))
        with tempfile.TemporaryDirectory() as d:  # Admiral run by such a base draws nothing, nor says it did
            probe = os.path.join(d, "ran")
            code, out = self.run_line(base="echo hud", ADMIRAL_IN_BASE="1", ADMIRAL_PROBE=probe)
            self.assertEqual((code, out, os.path.exists(probe)), (0, "", False))

    def test_a_base_running_admiral_through_a_script_still_draws_admiral_once(self):
        # what doctor offers for a script whose command does not name Admiral: keep it to run first
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "my-line")
            with open(script, "w") as fh:
                fh.write(f'#!/bin/sh\necho hud\nPYTHONPATH={root} exec {sys.executable} -m admiral statusline\n')
            os.chmod(script, 0o755)
            code, out = self.run_line(base=script)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "hud")
        self.assertEqual(out.count("Admiral"), 1, out)


class Parts(unittest.TestCase):
    def test_the_bar_fills_by_tenths_and_says_how_many_prs_merged(self):
        lines = statusline.Lines(board())
        self.assertEqual(plain(lines.bar(57, 1, 11)), "██████░░░░  57%  PRs merged 1/11")
        self.assertEqual(plain(lines.bar(57)), "██████░░░░  57%")
        # no plan and no member registered: nothing to count, said with why rather than read as nothing done
        self.assertEqual(plain(lines.bar(None)), "progress unknown: no member registered")
        self.assertEqual(plain(lines.bar(25, 0, 0)), "██░░░░░░░░  25%")  # no PR yet: no "merged 0/0"

    def test_the_bar_deepens_from_faint_to_full_green(self):
        lines = statusline.Lines(board())
        cells = re.findall(r"\x1b\[38;2;(\d+);(\d+);(\d+)m█", lines.bar(100))
        greens = [int(g) for _, g, _ in cells]
        self.assertEqual(greens, sorted(greens))
        self.assertEqual(tuple(map(int, cells[-1])), lines.full)

    def test_one_is_singular_in_english(self):
        lines = statusline.Lines(board())
        self.assertEqual(lines.W["total"].format(n=1), "1 session")
        self.assertEqual(lines.W["total"].format(n=2), "2 sessions")
        self.assertEqual(lines.W["more_commanders"].format(n=1), "1 more commander: /admiral shows all")

    def test_a_long_line_is_cut_to_the_width_in_cells(self):
        cut = statusline.fit("舰队指挥" * 10, 9)
        self.assertLessEqual(statusline.width(plain(cut)), 9)
        self.assertTrue(plain(cut).endswith("…"))


class Lines(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.default_state, statusline.DEFAULT_STATE = statusline.DEFAULT_STATE, os.path.join(self.dir, "default-state")
        self.file = os.path.join(self.dir, "board.json")

    def tearDown(self):
        statusline.DEFAULT_STATE = self.default_state
        shutil.rmtree(self.dir)

    def lines(self, b, session_id):
        with open(self.file, "w", encoding="utf-8") as fh:
            json.dump(b, fh, ensure_ascii=False)
        return [plain(x) for x in statusline.admiral_lines(self.file, session_id)]

    def test_a_line_too_wide_drops_the_waiting_names_before_the_ci_count(self):
        full = plain(statusline.Lines(board()).render("nobody")[0])
        narrow = plain(statusline.Lines(board()).render("nobody", cols=statusline.width(full) - 1)[0])
        self.assertNotIn("(two)", narrow)
        self.assertTrue(narrow.endswith("✗ 1 CI"))

    def test_no_board_says_why(self):
        missing = os.path.join(self.dir, "board.json")
        self.assertIn("no board yet: run scripts/install.sh", plain(statusline.admiral_lines(missing, "x")[0]))
        with open(os.path.join(self.dir, "last-error.txt"), "w") as fh:
            fh.write("Traceback (most recent call last):\nModuleNotFoundError: No module named 'tomllib'\n")
        self.assertIn("the background job fails: ModuleNotFoundError", plain(statusline.admiral_lines(missing, "x")[0]))

    def test_a_job_that_could_not_start_is_found_in_the_default_state_directory(self):
        os.makedirs(statusline.DEFAULT_STATE)
        with open(os.path.join(statusline.DEFAULT_STATE, "last-error.txt"), "w") as fh:
            fh.write("Admiral needs Python 3.11 or newer\n")
        line = plain(statusline.admiral_lines(os.path.join(self.dir, "elsewhere", "board.json"), "x")[0])
        self.assertIn("the background job fails: Admiral needs Python 3.11", line)

    def test_a_stale_board_says_why_when_the_job_left_an_error(self):
        b = board(generated=time.time() - 600)
        with open(os.path.join(self.dir, "last-error.txt"), "w") as fh:
            fh.write("RuntimeError: gh is not signed in\n")
        line = self.lines(b, "x")[0]
        self.assertIn("10 min ago", line)
        self.assertIn("(RuntimeError: gh is not signed in)", line)

    def test_names_leave_their_project_out_unless_another_project_has_the_name(self):
        def two_projects(lead, worker):
            b = board(projects=["Shop", "Tools"])
            g = b["groups"][0]
            g["project"], g["lead"] = "Shop", "Commander-A [Shop]"
            for x in [g["leadRow"]] + g["members"]:
                x["project"], x["name"], x["lead"] = "Shop", x["name"] + " [Shop]", x["lead"] and x["lead"] + " [Shop]"
            cmd = dict(row(f"{lead} [Tools]", "s5", commander=True), project="Tools")
            w = dict(row(f"{worker} [Tools]", "s6", status="waiting", lead=f"{lead} [Tools]"), project="Tools")
            s = dict(g["summary"], total=1, busy=0, waiting=1, ciFail=0)
            b["groups"].append({"project": "Tools", "lead": f"{lead} [Tools]", "leadRow": cmd, "members": [w],
                                "summary": s})
            return b

        lines = self.lines(two_projects("Commander-B", "three"), "s3")
        self.assertIn("(two, three)", lines[0])
        self.assertEqual(sorted(x.split()[0] for x in lines[1:3]), ["A", "B"])
        self.assertIn("under Commander-A", lines[-1])
        self.assertNotIn("[", "".join(lines))
        lines = self.lines(two_projects("Commander-A", "two"), "s3")
        self.assertIn("(two [Shop], two [Tools])", lines[0])
        self.assertEqual(sorted(x.split()[1] for x in lines[1:3]), ["[Shop]", "[Tools]"])
        self.assertIn("under Commander-A [Shop]", lines[-1])

    def test_a_name_left_without_its_project_is_never_shown_like_another(self):
        def team(lead, project, members):
            cmd = dict(row(f"{lead} [{project}]", lead + project, commander=True), project=project)
            ws = [dict(row(f"{m} [{project}]", m + project, status="waiting", lead=f"{lead} [{project}]"),
                       project=project) for m in members]
            s = dict(board()["groups"][0]["summary"], total=len(ws), busy=0, waiting=len(ws), ciFail=0)
            return {"project": project, "lead": f"{lead} [{project}]", "leadRow": cmd, "members": ws, "summary": s}

        b = board(projects=["A", "B"],
                  groups=[team("Commander-x", "A", ["x"]), team("Commander_x", "B", ["x", "x [A]"])])
        lines = self.lines(b, "x [A]B")
        self.assertIn("(x [A], x [B], x [A] [B])", lines[0])
        self.assertEqual(sorted(x.split("  ")[1] for x in lines[1:3]), ["x [A]", "x [B]"])
        self.assertIn("under Commander_x", lines[-1])
        b = board(projects=["A", "B"], groups=[team("Commander-x", "A", ["one"]), team("Commander-x", "B", [])])
        self.assertIn("x [A]", self.lines(b, "nobody")[1])  # a batch not on the line still has the name
        b = board(projects=["A", "B"], groups=[team("Commander-x", "A", ["one"]), team("Commander-x ", "B", ["two"])])
        self.assertEqual(sorted(x.split()[1] for x in self.lines(b, "nobody")[1:3]), ["[A]", "[B]"])  # padded alike

    def test_a_name_with_brackets_of_its_own_is_left_as_it_is(self):
        b = board()
        b["groups"][0]["members"][1]["name"] = "two [Shop]"
        self.assertIn("(two [Shop])", self.lines(b, "nobody")[0])

    def test_the_first_line_breaks_every_session_down(self):
        first = self.lines(board(), "nobody")[0]
        self.assertIn("3 sessions: ◆ 1 waiting for you (two) · ● 1 working · ○ 1 idle", first)
        self.assertIn("（two）", self.lines(board("zh"), "nobody")[0])
        self.assertIn("✗ 1 CI", first)

    def test_the_first_line_counts_the_persons_prs_as_github_has_them(self):
        first = self.lines(board(mine={"open": 5, "mergedToday": 2}), "nobody")[0]
        self.assertIn("GitHub PRs: 5 open · 2 merged today", first)
        self.assertNotIn("PRs merged", first)

    def test_a_commander_sees_its_own_team_marked(self):
        self.assertTrue(any(x.startswith("▸ A") for x in self.lines(board(), "s1")))

    def test_a_worker_sees_its_own_milestone_pr_and_ci(self):
        mine = self.lines(board(), "s3")[-1]
        self.assertTrue(mine.startswith("this session  ▰▰▰▰▱ CI"))
        self.assertIn("#7 in review", mine)
        self.assertIn("under Commander-A", mine)

    def test_a_stale_board_says_so(self):
        self.assertIn("background job may have stopped", self.lines(board(generated=time.time() - 600), "s1")[0])

    def test_a_source_problem_is_flagged(self):
        self.assertIn("⚠ source problem 1", self.lines(board(health=["x"]), "s1")[0])

    def test_chinese(self):
        first = self.lines(board("zh", mine={"open": 5, "mergedToday": 1}), "nobody")[0]
        self.assertIn("GitHub PR：开着 5 · 今天合并 1", first)
        self.assertIn("共 3 对话：◆ 1 待处理（two） · ● 1 工作 · ○ 1 空闲", first)


if __name__ == "__main__":
    unittest.main()
