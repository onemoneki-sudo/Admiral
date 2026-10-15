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
# fields as GitHub does, and `gh api graphql` asking PRs by branch name (b0, b1, ...: its open PR as oK, its newest as
# nK) from <dir>/by-name.json, newest first, failing when <dir>/graphql.fail exists; logs every call's arguments to
# <dir>/calls.log.
FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
d, args = os.environ["FAKE_GH"], sys.argv[1:]
with open(os.path.join(d, "calls.log"), "a") as fh:
    fh.write(json.dumps(args) + "\\n")
if args[:2] == ["api", "graphql"]:
    if os.path.exists(os.path.join(d, "graphql.fail")):
        sys.exit(1)
    path = os.path.join(d, "by-name.json")
    data = json.load(open(path)) if os.path.exists(path) else []
    asked = dict(kv.split("=", 1) for kv in args[3::2])
    keep = ("number", "headRefName", "state", "isDraft")
    repo = {}
    for k, b in asked.items():
        if k[:1] == "b" and k[1:].isdigit():
            prs = [{f: p[f] for f in keep} for p in data if p["headRefName"] == b]
            repo["o" + k[1:]] = {"nodes": [p for p in prs if p["state"] == "OPEN"][:1]}
            repo["n" + k[1:]] = {"nodes": prs[:1]}
    print(json.dumps({"data": {"repository": repo}}))
    sys.exit(0)
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

    def test_a_day_whose_midnight_never_came_begins_at_its_first_hour(self):
        # Casey, 2016-10-22: 23:59:59 at +08:00, then 03:00 at +11:00, both 16:00 UTC. macOS refuses the midnight
        # that never came; elsewhere the C library places it on its own, so there it only must not fail.
        since = self.in_zone("Antarctica/Casey", "2016-10-22 12:00")
        if sys.platform == "darwin":
            self.assertEqual(since, "merged:>=2016-10-21T16:00:00+00:00")

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

    def full_lists(self):
        """100 open PRs and 300 PRs in all, every one newer than any asked for below."""
        self.answer("open", [{"number": 1000 - i, "headRefName": f"o{i}", "state": "OPEN", "isDraft": False,
                              "reviewDecision": "", "statusCheckRollup": []} for i in range(100)])
        self.answer("all", [{"number": 1000 - i, "headRefName": f"a{i}", "state": "MERGED", "isDraft": False}
                            for i in range(300)])

    def test_a_pr_past_both_lists_is_asked_for_by_its_branch(self):
        self.full_lists()
        self.answer("by-name", [{"number": 7, "headRefName": "old", "state": "OPEN", "isDraft": True},
                                {"number": 5, "headRefName": "gone", "state": "CLOSED", "isDraft": False}])
        prs = github.prs_by_branch(self.cfg, {"old", "gone", "never"})
        self.assertEqual((prs["old"]["state"], prs["old"]["isDraft"], prs["old"]["checksUnknown"]), ("OPEN", True, True))
        self.assertEqual(prs["gone"]["state"], "CLOSED")
        self.assertNotIn("never", prs)  # asked, and GitHub has no PR for it
        asked = [c for c in self.calls() if c[:2] == ["api", "graphql"]]
        self.assertEqual(len(asked), 1)
        self.assertEqual(sorted(kv.split("=", 1)[1] for kv in asked[0][3::2] if kv[:1] == "b"), ["gone", "never", "old"])

    def test_asked_by_name_an_open_pr_wins_however_many_newer_ones_its_branch_has(self):
        self.full_lists()
        self.answer("by-name", [{"number": 20 - i, "headRefName": "old", "state": "MERGED", "isDraft": False}
                                for i in range(5)] + [{"number": 4, "headRefName": "old", "state": "OPEN", "isDraft": True}])
        self.assertEqual(github.prs_by_branch(self.cfg, {"old"})["old"]["number"], 4)

    def test_an_open_pr_past_the_open_list_wins_over_a_merged_one_the_recent_list_has(self):
        self.full_lists()
        self.answer("all", [{"number": 900, "headRefName": "x", "state": "MERGED", "isDraft": False}]
                    + [{"number": 899 - i, "headRefName": f"a{i}", "state": "MERGED", "isDraft": False} for i in range(299)])
        self.answer("by-name", [{"number": 900, "headRefName": "x", "state": "MERGED", "isDraft": False},
                                {"number": 4, "headRefName": "x", "state": "OPEN", "isDraft": True}])
        pr = github.prs_by_branch(self.cfg, {"x"})["x"]
        self.assertEqual((pr["number"], pr["checksUnknown"]), (4, True))

    def test_with_every_pr_listed_an_open_one_still_wins_over_a_newer_merged_one(self):
        self.answer("open", [{"number": 1000 - i, "headRefName": f"o{i}", "state": "OPEN", "isDraft": False,
                              "reviewDecision": "", "statusCheckRollup": []} for i in range(100)])
        self.answer("all", [{"number": 900, "headRefName": "x", "state": "MERGED", "isDraft": False},
                            {"number": 4, "headRefName": "x", "state": "OPEN", "isDraft": True}])
        self.assertEqual(github.prs_by_branch(self.cfg, {"x"})["x"]["number"], 4)
        self.assertFalse([c for c in self.calls() if c[:1] == ["api"]])  # the list of every state is all there is

    def test_when_the_lookup_fails_no_pr_is_unknown_not_none(self):
        self.full_lists()
        open(os.path.join(self.dir, "graphql.fail"), "w").close()
        self.assertIsNone(github.prs_by_branch(self.cfg, {"old"}))  # as when GitHub does not answer at all

    def test_lists_with_room_left_hold_every_pr_so_nothing_more_is_asked(self):
        self.answer("open", [{"number": 3, "headRefName": "feat/a", "state": "OPEN", "isDraft": False,
                              "reviewDecision": "", "statusCheckRollup": []}])
        self.answer("all", [{"number": 3, "headRefName": "feat/a", "state": "OPEN", "isDraft": False}])
        prs = github.prs_by_branch(self.cfg, {"feat/a", "feat/b"})
        self.assertEqual(sorted(prs), ["feat/a"])
        self.assertFalse([c for c in self.calls() if c[:1] == ["api"]])

    def test_many_branches_left_out_are_asked_for_in_bounded_calls(self):
        self.full_lists()
        missing = {f"m{i}" for i in range(github.LOOKUP_CHUNK + 1)}  # one call for every LOOKUP_CHUNK of them
        self.assertEqual(github.prs_by_branch(self.cfg, missing), {})
        self.assertEqual(len([c for c in self.calls() if c[:2] == ["api", "graphql"]]), 2)

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

    def test_the_cap_holds_over_refreshes(self):
        def merged(numbers):
            return {f"b{n}": {"number": n, "headRefName": f"b{n}", "state": "MERGED", "isDraft": False} for n in numbers}
        branches = set(merged(range(1, 502)))
        self.paced(branches, 0, merged(range(1, 301)))
        self.paced(branches, 60, merged(range(301, 502)))
        for now in (120, 180):  # all of them fell out of the recent list
            prs = self.paced(branches, now, {})
        self.assertEqual((len(prs), "b1" in prs), (github.MERGED_KEPT, False))  # the oldest stays forgotten

    def test_a_cache_written_before_the_memory_keeps_its_merges(self):
        registry.write_json(self.cfg.sub("pr-cache.json"), {"at": 0, "branches": ["feat/a"], "mine": {},
                            "prs": {"feat/a": {"number": 1, "headRefName": "feat/a", "state": "MERGED"}}})
        self.assertEqual(self.paced({"feat/a"}, 60, {})["feat/a"]["number"], 1)

    def test_an_answer_reused_while_quiet_holds_only_the_branches_in_use(self):
        past = {"number": 100, "headRefName": "b100", "state": "OPEN", "isDraft": False, "checksUnknown": True}
        github.prs_paced(self.cfg, {"b100", "b200"}, False, 0, fetch=lambda cfg, b: {"b100": past},
                         fetch_mine=lambda cfg, now: {})
        prs, _, reused = github.prs_paced(self.cfg, {"b200"}, True, 60, fetch=lambda cfg, b: self.fail("asked"),
                                          fetch_mine=lambda cfg, now: {})
        self.assertEqual((reused, prs), (True, {}))  # b100 is no longer in use: neither it nor its warning comes back

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
