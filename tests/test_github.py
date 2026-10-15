"""What Admiral asks GitHub and how it reads the answers, against a stand-in `gh` on the PATH: the real subprocess
calls run, nothing reaches GitHub.

    python3 -m unittest discover -s tests
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from admiral import config, github, registry  # noqa: E402

# Answers `gh pr list` from <dir>/<state>.json (or mine-<state>.json with --author), cut to --limit and to the --json
# fields as GitHub does, and logs every call's arguments to <dir>/calls.log.
FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
d, args = os.environ["FAKE_GH"], sys.argv[1:]
with open(os.path.join(d, "calls.log"), "a") as fh:
    fh.write(json.dumps(args) + "\\n")
key = ("mine-" if "--author" in args else "") + args[args.index("--state") + 1]
path = os.path.join(d, key + ".json")
data = json.load(open(path)) if os.path.exists(path) else []
fields = args[args.index("--json") + 1].split(",")
print(json.dumps([{k: p[k] for k in fields if k in p} for p in data[:int(args[args.index("--limit") + 1])]]))
"""


class FakeGitHub(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        gh = os.path.join(self.dir, "gh")
        with open(gh, "w") as fh:
            fh.write(FAKE_GH)
        os.chmod(gh, 0o755)
        env = mock.patch.dict(os.environ, {"FAKE_GH": self.dir, "PATH": self.dir + os.pathsep + os.environ["PATH"]})
        env.start()
        self.addCleanup(env.stop)
        self.cfg = config.Config(config.merge(config.DEFAULTS, {"state_dir": os.path.join(self.dir, "state"),
                                                                "github": {"repo_dir": self.dir}}))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def answer(self, key, prs):
        with open(os.path.join(self.dir, key + ".json"), "w") as fh:
            json.dump(prs, fh)

    def calls(self):
        with open(os.path.join(self.dir, "calls.log")) as fh:
            return [json.loads(line) for line in fh]


class MergedToday(FakeGitHub):
    def in_zone(self, tz, local):
        """The search `my_prs` sends for merged PRs when the clock reads `local` (Y-m-d H:M) in time zone `tz`."""
        old = os.environ.get("TZ")
        os.environ["TZ"] = tz
        time.tzset()
        try:
            github.my_prs(self.cfg, time.mktime(time.strptime(local, "%Y-%m-%d %H:%M")))
        finally:
            if old is None:
                del os.environ["TZ"]
            else:
                os.environ["TZ"] = old
            time.tzset()
        merged = [c for c in self.calls() if "merged" in c]
        return merged[-1][merged[-1].index("--search") + 1]

    def test_today_is_the_local_day_not_the_utc_one(self):
        # GitHub reads a bare date as a UTC day: at 03:00 in UTC+8 that day has not begun, and at 20:00 in UTC-7 it
        # began the evening before. Asked from the moment the person's day began, it is their own.
        self.assertEqual(self.in_zone("Asia/Shanghai", "2026-10-15 03:00"), "merged:>=2026-10-14T16:00:00+00:00")
        self.assertEqual(self.in_zone("America/Los_Angeles", "2026-10-15 20:00"), "merged:>=2026-10-15T07:00:00+00:00")
        self.assertEqual(self.in_zone("Asia/Kolkata", "2026-10-15 01:00"), "merged:>=2026-10-14T18:30:00+00:00")
        self.assertEqual(self.in_zone("UTC", "2026-10-15 12:00"), "merged:>=2026-10-15T00:00:00+00:00")

    def test_a_day_the_clocks_change_begins_at_its_own_midnight(self):
        # the day began before the change, in the offset it had then
        self.assertEqual(self.in_zone("America/Los_Angeles", "2026-03-08 12:00"), "merged:>=2026-03-08T08:00:00+00:00")
        self.assertEqual(self.in_zone("America/Los_Angeles", "2026-11-01 12:00"), "merged:>=2026-11-01T07:00:00+00:00")


class Limits(FakeGitHub):
    def test_an_open_pr_past_the_open_list_keeps_its_draft_flag_and_its_ci_is_unknown(self):
        open_prs = [{"number": 200 - i, "headRefName": f"b{200 - i}", "state": "OPEN", "isDraft": i % 2 == 0,
                     "reviewDecision": "", "statusCheckRollup": []} for i in range(101)]  # newest first
        self.answer("open", open_prs)
        self.answer("all", [{k: p[k] for k in ("number", "headRefName", "state", "isDraft")} for p in open_prs])
        prs = github.prs_by_branch(self.cfg, {"b200", "b100"})
        self.assertEqual((prs["b200"]["isDraft"], prs["b200"].get("checksUnknown")), (True, None))
        self.assertEqual((prs["b100"]["isDraft"], prs["b100"]["checksUnknown"]), (True, True))  # the 101st open PR

    def test_a_pr_opened_between_the_two_calls_is_not_taken_for_one_past_the_limit(self):
        self.answer("open", [])  # asked first: not open yet
        self.answer("all", [{"number": 7, "headRefName": "feat/a", "state": "OPEN", "isDraft": False}])
        self.assertIsNone(github.prs_by_branch(self.cfg, {"feat/a"})["feat/a"].get("checksUnknown"))

    def test_a_merged_pr_that_left_the_recent_list_is_remembered_while_its_branch_is_in_use(self):
        merged = {"number": 1, "headRefName": "feat/a", "state": "MERGED", "isDraft": False}
        first = github.prs_paced(self.cfg, {"feat/a", "feat/b"}, False, 0,
                                 fetch=lambda cfg, b: {"feat/a": merged}, fetch_mine=lambda cfg, now: {})
        self.assertEqual(first[0]["feat/a"]["state"], "MERGED")
        later = github.prs_paced(self.cfg, {"feat/a", "feat/b"}, False, 60,
                                 fetch=lambda cfg, b: {}, fetch_mine=lambda cfg, now: {})  # it fell out of the 300
        self.assertEqual(later[0]["feat/a"]["state"], "MERGED")
        github.prs_paced(self.cfg, {"feat/b"}, False, 120, fetch=lambda cfg, b: {}, fetch_mine=lambda cfg, now: {})
        gone = github.prs_paced(self.cfg, {"feat/a"}, False, 180,
                                fetch=lambda cfg, b: {}, fetch_mine=lambda cfg, now: {})
        self.assertNotIn("feat/a", gone[0])  # no longer in use: forgotten, so the memory stays bounded

    def paced(self, branches, now, prs, mine=None):
        return github.prs_paced(self.cfg, branches, False, now, fetch=lambda cfg, b: prs,
                                fetch_mine=lambda cfg, n: {} if mine is None else mine)[0]

    def test_the_remembered_merges_are_capped_keeping_the_newest(self):
        many = {f"b{n}": {"number": n, "headRefName": f"b{n}", "state": "MERGED", "isDraft": False} for n in range(600)}
        self.paced(set(many), 0, many)
        kept = registry.read_json(self.cfg.sub("pr-cache.json"))["merged"]
        self.assertEqual((len(kept), min(p["number"] for p in kept.values())), (github.MERGED_KEPT, 100))

    def test_a_newer_answer_replaces_a_remembered_merge_even_when_the_persons_prs_fail(self):
        merged = {"number": 1, "headRefName": "feat/a", "state": "MERGED", "isDraft": False}
        closed = {"number": 9, "headRefName": "feat/a", "state": "CLOSED", "isDraft": False}
        github.prs_paced(self.cfg, {"feat/a"}, False, 0, fetch=lambda cfg, b: {"feat/a": merged},
                         fetch_mine=lambda cfg, now: {})
        github.prs_paced(self.cfg, {"feat/a"}, False, 60, fetch=lambda cfg, b: {"feat/a": closed},
                         fetch_mine=lambda cfg, now: None)  # the person's own PRs failed this time
        later = self.paced({"feat/a"}, 120, {})  # #9 fell out of the recent list too
        self.assertNotIn("feat/a", later)  # the merge #9 replaced does not come back

    def test_a_newer_pr_on_the_same_branch_wins_over_a_remembered_merge(self):
        merged = {"number": 1, "headRefName": "feat/a", "state": "MERGED", "isDraft": False}
        reopened = {"number": 9, "headRefName": "feat/a", "state": "OPEN", "isDraft": False}
        github.prs_paced(self.cfg, {"feat/a"}, False, 0, fetch=lambda cfg, b: {"feat/a": merged},
                         fetch_mine=lambda cfg, now: {})
        prs = github.prs_paced(self.cfg, {"feat/a"}, False, 60, fetch=lambda cfg, b: {"feat/a": reopened},
                               fetch_mine=lambda cfg, now: {})[0]
        self.assertEqual(prs["feat/a"]["number"], 9)


WRITER = """
import sys
sys.path.insert(0, sys.argv[1])
from admiral import registry
for i in range(int(sys.argv[3])):
    registry.write_json(sys.argv[2], {"writer": sys.argv[4], "pad": "x" * (i % 7 * 300)})
"""


class Writes(unittest.TestCase):
    def test_two_processes_writing_one_file_never_fail_or_leave_it_broken(self):
        # the background job and a session's `admiral board --now` write the same caches
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        path = os.path.join(d, "cache.json")
        procs = [subprocess.Popen([sys.executable, "-c", WRITER, ROOT, path, "400", w], stderr=subprocess.PIPE, text=True)
                 for w in ("a", "b")]
        errors = [p.communicate()[1] for p in procs]
        self.assertEqual([p.returncode for p in procs], [0, 0], errors)
        self.assertIn(registry.read_json(path)["writer"], ("a", "b"))
        self.assertEqual(sorted(os.listdir(d)), ["cache.json"])  # no temporary file left behind


if __name__ == "__main__":
    unittest.main()
