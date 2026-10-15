"""The status line, from a fixture board snapshot."""

import json
import os
import re
import shutil
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


class Parts(unittest.TestCase):
    def test_the_bar_fills_by_tenths_and_says_how_many_prs_merged(self):
        lines = statusline.Lines(board())
        self.assertEqual(plain(lines.bar(57, 1, 11)), "██████░░░░  57%  PRs merged 1/11")
        self.assertEqual(plain(lines.bar(57)), "██████░░░░  57%")
        self.assertEqual(plain(lines.bar(None)), "no progress yet")
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
