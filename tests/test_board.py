"""The board against fixture files: no real sessions, transcripts, GitHub or git are read.

    python3 -m unittest discover -s tests
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from admiral import board, config  # noqa: E402

NOW = 1_800_000_000.0
START = "Mon Oct 12 02:23:18 2026"


def pr(number, state, review="", checks=()):
    return {"number": number, "headRefName": "", "state": state, "isDraft": False, "reviewDecision": review,
            "statusCheckRollup": [{"name": n, "status": "COMPLETED", "conclusion": c} for n, c in checks]}


class World(unittest.TestCase):
    """A temporary machine: sessions, transcripts, registrations, plans and locks, with a config pointing at it."""

    language = "en"

    def setUp(self):
        self.root = tempfile.mkdtemp()
        for d in ("sessions", "projects", "locks"):
            os.makedirs(os.path.join(self.root, d))
        self.cfg = config.Config(config.merge(config.DEFAULTS, {
            "state_dir": os.path.join(self.root, "state"), "language": self.language,
            "sessions": {"dir": os.path.join(self.root, "sessions"), "projects_dir": os.path.join(self.root, "projects"),
                         "project_dirs": ["/w/app"], "commander_prefix": "Commander"},
            "github": {"repo_dir": "/w/app"}, "locks": {"dir": os.path.join(self.root, "locks")}}))
        self.prs, self.gh_calls, self.commits = {}, [], {}
        self.mine, self.checked_out = {"open": [], "mergedToday": []}, {}
        self.gh_down = False  # gh fails, as when it is signed out or GitHub does not answer

    def tearDown(self):
        shutil.rmtree(self.root)

    def build(self, use_gh=True, now=NOW):
        def fetch(cfg, branches):
            self.gh_calls.append(set(branches))
            if self.gh_down:
                return None
            return {b: p for b, p in self.prs.items() if b in branches}
        return board.build(self.cfg, use_gh=use_gh, now=now,
                           starts=lambda pids: {p: (START, f"ttys{p:03d}") for p in pids},
                           fetch=fetch, commits=lambda wt: self.commits.get(wt) if wt else None,
                           fetch_mine=lambda cfg, now: self.mine,
                           checked_out=lambda wt: self.checked_out.get(wt, ""),
                           worktrees=lambda cfg: {b: wt for wt, b in self.checked_out.items()})

    def session(self, pid, name, status="idle", former=(), cwd="/w/app", since=NOW - 600, **extra):
        d = {"pid": pid, "sessionId": f"s{pid}", "name": name, "status": status, "cwd": cwd, "procStart": START,
             "statusUpdatedAt": since * 1000, "formerNames": [{"name": f} for f in former], **extra}
        with open(os.path.join(self.root, "sessions", f"{pid}.json"), "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
        self.transcript(pid)

    def transcript(self, pid, *messages, cwd="/w/app"):
        """messages: (sender pid, sender name), stored as Claude Code stores a cross-session message."""
        from admiral import sessions
        path = sessions.transcript(self.cfg, cwd, f"s{pid}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for sender, name in messages:
                text = (f'<cross-session-message from="uds:/tmp/cc-socks/{sender}.sock" from-name="{name}" '
                        f'from-mode="prompting">\nwork</cross-session-message>')
                fh.write(json.dumps({"type": "user", "message": {"content": text}}, ensure_ascii=False) + "\n")

    def register(self, who, branch="", worktree="", lead="", phase=None, note=""):
        from admiral import registry
        registry.register(self.cfg, who, branch=branch, worktree=worktree, lead=lead)
        if phase:
            note = note or ("on someone" if phase in ("waiting", "needs_you") else "")
            ok, msg = registry.set_phase(self.cfg, who, phase, note)
            assert ok, msg

    def plan(self, lead, *items):
        from admiral import registry
        for branch, title, owner in items:
            registry.plan_add(self.cfg, lead, branch, title, owner)

    def lock(self, name, who):
        os.makedirs(os.path.join(self.root, "locks", name))
        with open(os.path.join(self.root, "locks", name, "owner"), "w", encoding="utf-8") as fh:
            fh.write(f"who={who}\npid=1\n")

    def group(self, b, lead):
        return next(g for g in b["groups"] if g["lead"] == lead)


class Milestones(unittest.TestCase):
    def test_stage_follows_the_phase_until_the_pr_opens(self):
        self.assertEqual(board.stage_of(None, None), 1)
        self.assertEqual(board.stage_of("working", None), 1)
        self.assertEqual(board.stage_of("review", None), 2)
        self.assertEqual(board.stage_of("accepting", None), 3)
        self.assertEqual(board.stage_of("working", pr(1, "OPEN")), 4)  # one push straight to ready
        self.assertEqual(board.stage_of("review", dict(pr(1, "OPEN"), isDraft=True)), 2)  # a draft is not ready
        self.assertEqual(board.stage_of("review", pr(1, "MERGED")), 5)
        self.assertEqual(board.stage_of("done", None), 5)  # no PR to speak for it: the session's word
        self.assertEqual(board.stage_of("done", pr(1, "OPEN")), 4)  # done is not merged while the PR is open
        self.assertEqual(board.stage_of("done", pr(1, "CLOSED")), 3)
        self.assertEqual(board.stage_of(None, pr(1, "CLOSED")), 1)

    def test_unregistered_and_not_started(self):
        self.assertEqual(board.stage(None, pr(1, "OPEN")), 0)
        self.assertEqual(board.item_stage(None, None), 0)
        self.assertEqual(board.item_stage({"phase": None}, None), 1)
        self.assertEqual(board.item_stage(None, pr(1, "MERGED")), 5)

    def test_percentage_is_the_mean_worth(self):
        w = [0, 25, 50, 70, 80, 100]
        self.assertIsNone(board.pct([0] * 6, w))
        self.assertEqual(board.pct([0, 1, 0, 0, 0, 0], w), 25)
        self.assertEqual(board.pct([1, 0, 0, 0, 1, 1], w), 60)


class Grouping(World):
    def test_a_registered_lead_wins_over_the_last_message(self):
        self.session(1, "Commander-A")
        self.session(2, "Commander-B")
        self.session(3, "worker")
        self.transcript(3, (1, "Commander-A"))
        self.register("worker", lead="Commander-B")
        b = self.build(use_gh=False)
        self.assertEqual([x["name"] for x in self.group(b, "Commander-B")["members"]], ["worker"])

    def test_without_a_lead_the_last_commander_message_decides(self):
        self.session(1, "Commander-A")
        self.session(2, "Commander-B")
        self.session(3, "worker")
        self.transcript(3, (1, "Commander-A"), (2, "Commander-B"))
        member = self.group(self.build(use_gh=False), "Commander-B")["members"][0]
        self.assertEqual((member["name"], member["leadFrom"]), ("worker", "message"))

    def test_a_message_from_a_non_commander_is_ignored(self):
        self.session(1, "Commander-A")
        self.session(3, "worker")
        self.session(4, "peer")
        self.transcript(3, (1, "Commander-A"), (4, "peer"))
        self.assertEqual([x["name"] for x in self.group(self.build(use_gh=False), "Commander-A")["members"]], ["worker"])

    def test_a_renamed_commander_keeps_its_team(self):
        self.session(1, "Commander-New", former=["Commander-Old"])
        self.session(3, "worker")
        self.transcript(3, (1, "Commander-Old"))
        self.assertEqual([x["name"] for x in self.group(self.build(use_gh=False), "Commander-New")["members"]], ["worker"])

    def test_a_commander_is_known_by_pid_when_its_old_name_was_not_kept(self):
        self.session(1, "Commander-New")
        self.session(3, "worker")
        self.transcript(3, (1, "Commander-Old"))
        self.assertEqual([x["name"] for x in self.group(self.build(use_gh=False), "Commander-New")["members"]], ["worker"])

    def test_the_transcript_scan_resumes_where_it_stopped(self):
        self.session(1, "Commander-A")
        self.session(2, "Commander-B")
        self.session(3, "worker")
        self.transcript(3, (1, "Commander-A"))
        self.build(use_gh=False)
        self.transcript(3, (2, "Commander-B"))
        self.assertEqual([x["name"] for x in self.group(self.build(use_gh=False), "Commander-B")["members"]], ["worker"])

    def test_only_sessions_of_the_configured_projects_show(self):
        self.session(1, "Commander-A")
        self.session(9, "elsewhere", cwd="/w/other")
        self.assertEqual(self.build(use_gh=False)["count"], 1)


class PastTheLists(World):
    def test_a_draft_found_by_its_branch_past_the_lists_keeps_a_done_session_at_accept(self):
        self.session(3, "worker")
        self.register("worker", branch="old", phase="done")
        # what the query answers for a draft PR past both lists, asked for by its branch
        self.prs = {"old": {"number": 7, "headRefName": "old", "state": "OPEN", "isDraft": True, "checksUnknown": True}}
        row = next(x for x in self.build()["unassigned"] if x["name"] == "worker")
        self.assertEqual((row["stage"], row["reportedDone"]), (3, False))


class OutsideTheProjects(World):
    """Sessions outside the configured projects are not shown, but a name running there is never taken for one that
    ended, nor its batch for one with nobody running."""

    def test_a_registered_session_outside_the_projects_is_not_taken_for_ended(self):
        self.session(3, "worker")
        self.session(9, "helper", cwd="/w/other")  # registrations are shared: it may belong to another project
        self.register("helper")
        b = self.build(use_gh=False)
        self.assertEqual([x["name"] for x in b["unassigned"]], ["worker"])
        self.assertFalse([h for h in b["hints"] if "has ended" in h], b["hints"])

    def test_a_planned_owner_running_outside_the_projects_keeps_its_batch_on_the_board(self):
        self.session(3, "worker")  # keeps the board refreshing
        self.session(9, "owner", cwd="/w/other")
        self.plan("Commander-A", ("feat/a", "merged one", "owner"))
        self.prs = {"feat/a": pr(1, "MERGED")}
        b = self.build()
        self.assertEqual([g["lead"] for g in b["groups"]], ["Commander-A"])  # its owner still runs: not over
        self.assertFalse([h for h in b["hints"] if "all merged" in h], b["hints"])

    def test_sessions_outside_the_projects_stay_out(self):
        self.session(1, "Commander-A")
        self.session(9, "elsewhere", cwd="/w/other")
        self.session(8, "Commander-Other", cwd="/w/other")  # another project's commander, named only there
        self.session(6, None, cwd="/w/other")  # no name: tied by none
        self.session(7, "other-worker", cwd="/w/other")
        self.register("other-worker", lead="Commander-Other")
        self.assertEqual(self.build(use_gh=False)["count"], 1)


class Progress(World):
    def test_a_plan_counts_every_deliverable_including_closed_sessions(self):
        self.session(1, "Commander-A")
        self.session(3, "worker")
        self.register("worker", branch="feat/b", lead="Commander-A")
        self.plan("Commander-A", ("feat/a", "merged one", "a closed session"), ("feat/b", "in CI", "worker"),
                  ("feat/c", "not started", ""))
        self.prs = {"feat/a": pr(1, "MERGED"), "feat/b": pr(2, "OPEN")}
        s = self.group(self.build(), "Commander-A")["summary"]
        self.assertEqual(s["dist"], [1, 0, 0, 0, 1, 1])
        self.assertEqual((s["pct"], s["items"], s["itemsDone"]), (60, 3, 1))

    def test_without_a_plan_registered_members_are_averaged(self):
        self.session(1, "Commander-A")
        for pid, name in ((3, "one"), (4, "two"), (5, "three")):
            self.session(pid, name)
            self.transcript(pid, (1, "Commander-A"))
        self.register("one", phase="review")
        self.register("two", branch="feat/x")
        self.prs = {"feat/x": pr(7, "OPEN")}
        s = self.group(self.build(), "Commander-A")["summary"]
        self.assertEqual((s["total"], s["pct"]), (3, 65))

    def test_the_playbook_reminder_follows_the_config(self):
        self.assertIs(self.build(use_gh=False)["playbookReminder"], True)  # on unless turned off
        self.cfg.playbook_remind = False
        self.assertIs(self.build(use_gh=False)["playbookReminder"], False)

    def test_weights_come_from_the_config(self):
        self.cfg.weights = [0, 10, 20, 30, 40, 100]
        self.session(3, "worker")
        self.register("worker", phase="review")
        self.assertEqual(self.build(use_gh=False)["pct"], 20)

    def test_a_failing_check_is_named_without_the_summary_job(self):
        from admiral import github
        checks = [("summary", "FAILURE"), ("tests (1)", "FAILURE")]
        self.assertEqual(github.ci(pr(1, "OPEN", checks=checks), ("summary",)), ("tests (1)", "fail"))
        self.assertEqual(github.ci(pr(1, "OPEN", checks=checks)), ("summary, tests (1)", "fail"))  # none configured
        self.assertEqual(github.ci(pr(1, "OPEN", checks=checks[:1]), ("summary",)), ("summary", "fail"))  # alone: named


class Linking(World):
    def test_every_registered_branch_and_the_worktree_branch_count(self):
        self.session(3, "worker")
        self.register("worker", branch="feat/a, feat/b", worktree="/w/wt/a")
        self.checked_out = {"/w/wt/a": "feat/c"}  # moved on without re-registering
        self.prs = {"feat/a": pr(1, "MERGED"), "feat/b": pr(2, "OPEN"), "feat/c": pr(3, "OPEN")}
        x = self.build()["unassigned"][0]
        self.assertEqual(sorted(x["prStates"]), [1, 2, 3])
        self.assertEqual(x["pr"]["number"], 3)

    def test_pr_counts_follow_github_not_sessions(self):
        self.session(1, "Commander-A")
        for pid, name in ((3, "one"), (4, "two"), (5, "three")):
            self.session(pid, name)
            self.transcript(pid, (1, "Commander-A"))
        self.register("one", branch="feat/a")
        self.register("two", branch="feat/b")
        self.register("three")
        self.prs = {"feat/a": pr(1, "OPEN"), "feat/b": pr(2, "MERGED")}
        b = self.build()
        s = self.group(b, "Commander-A")["summary"]
        self.assertEqual((s["prsMerged"], s["prs"], b["prsMerged"], b["prs"]), (1, 2, 1, 2))

    def test_my_open_prs_no_session_owns_are_listed(self):
        self.session(3, "worker")
        self.register("worker", branch="feat/a")
        self.prs = {"feat/a": pr(1, "OPEN")}
        self.mine = {"open": [{"number": 1, "headRefName": "feat/a"}, {"number": 9, "headRefName": "feat/z"}],
                     "mergedToday": [{"number": 5, "headRefName": "feat/y"}]}
        self.checked_out = {"/w/wt/z": "feat/z"}
        b = self.build()
        self.assertEqual(b["mine"], {"open": 2, "mergedToday": 1})
        self.assertTrue(any("PR #9 (feat/z) belongs to no session, checked out in /w/wt/z" in h for h in b["hints"]))
        self.assertFalse(any("PR #1 " in h for h in b["hints"]))

    def work(self, pid, *calls, cut=""):
        """calls: (tool, argument): edits and commands, stored as Claude Code stores a tool call; `cut` is a line
        still being written."""
        from admiral import sessions
        with open(sessions.transcript(self.cfg, "/w/app", f"s{pid}"), "a", encoding="utf-8") as fh:
            for tool, arg in calls:
                key = sessions.WORK_TOOLS[tool]
                fh.write(json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "t", "name": tool, "input": {key: arg}}]}}) + "\n")
            fh.write(cut)

    def moved(self):
        """worker registered feat/a in /w/wt/a, then went on to feat/b in /w/wt/b without re-registering."""
        self.session(3, "worker")
        self.register("worker", branch="feat/a", worktree="/w/wt/a")
        self.checked_out = {"/w/wt/a": "feat/a", "/w/wt/b": "feat/b", "/w/wt/b-old": "feat/old"}
        self.prs = {"feat/b": pr(9, "OPEN")}
        self.mine = {"open": [{"number": 9, "headRefName": "feat/b"}], "mergedToday": []}

    def test_a_session_that_moved_worktrees_is_found_by_its_work(self):
        self.moved()
        self.work(3, ("Edit", "/w/wt/b/app.py"), ("Bash", "cd /w/wt/b && git push"), ("Write", "/w/wt/b/x.py"),
                  ("Bash", "ls /w/wt/b-old"))
        self.session(4, "other")
        self.work(4, ("Bash", "git -C /w/wt/b log"))
        b = self.build()
        x = next(x for x in b["unassigned"] if x["name"] == "worker")
        self.assertEqual((x["pr"]["number"], x["guessedBranches"], x["stage"]), (9, ["feat/b"], 4))
        self.assertTrue(any("PR #9 (feat/b) is counted for worker" in h for h in b["hints"]))
        self.assertFalse(any("belongs to no session" in h for h in b["hints"]))

    def test_a_branch_taken_by_work_still_counts_for_the_batch_after_its_pr_merges(self):
        self.moved()
        self.session(1, "Commander-A")
        self.transcript(3, (1, "Commander-A"))
        self.work(3, *[("Edit", "/w/wt/b/app.py")] * 3)
        self.build()
        self.prs = {"feat/b": pr(9, "MERGED")}
        self.mine = {"open": [], "mergedToday": [{"number": 9, "headRefName": "feat/b"}]}
        b = self.build()
        x, s = self.group(b, "Commander-A")["members"][0], self.group(b, "Commander-A")["summary"]
        self.assertEqual((s["prsMerged"], s["prs"]), (1, 1))
        # but it does not make the session look finished: it may have gone on to other work
        self.assertEqual((x["pr"], x["stage"], x["done"]), (None, 1, False))
        self.assertFalse(any("PR #9" in h for h in b["hints"]))

    def push(self, pid, *branches, remote="git@example.com:o/app.git"):
        """A Bash call whose result is `git push` output updating these branches."""
        from admiral import sessions
        refs = "".join(f" * [new branch]      {b} -> {b}\n" if i % 2 == 0 else f"   1a2b3c4d..5e6f7a8b  {b} -> {b}\n"
                       for i, b in enumerate(branches))
        with open(sessions.transcript(self.cfg, "/w/app", f"s{pid}"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t", "content": f"Enumerating objects: 5\nTo {remote}\n{refs}"
                 f"branch '{branches[0]}' set up to track 'origin/{branches[0]}'.\n"}]}}) + "\n")

    def test_a_pushed_branch_belongs_to_the_session_that_pushed_it(self):
        self.session(3, "worker")
        self.register("worker", branch="feat/a")
        self.push(3, "feat/b", "feat/c")
        self.prs = {"feat/b": pr(9, "OPEN"), "feat/c": pr(10, "MERGED")}  # feat/c merged long ago: not taken
        self.mine = {"open": [{"number": 9, "headRefName": "feat/b"}], "mergedToday": []}
        b = self.build()
        x = b["unassigned"][0]
        self.assertEqual((x["guessedBranches"], x["pr"]["number"]), (["feat/b"], 9))
        self.assertFalse(any("belongs to no session" in h for h in b["hints"]))

    def test_a_cache_from_an_older_version_is_read_again(self):
        from admiral import registry, sessions
        self.session(3, "worker")
        self.register("worker", branch="feat/a")
        self.push(3, "feat/b")
        size = os.path.getsize(sessions.transcript(self.cfg, "/w/app", "s3"))
        registry.write_json(self.cfg.sub("work-cache.json"), {"s3": {"offset": size, "counts": {}}})  # read, by v1
        self.prs = {"feat/b": pr(9, "OPEN")}
        self.assertEqual(self.build()["unassigned"][0]["guessedBranches"], ["feat/b"])

    def test_a_branch_two_sessions_pushed_falls_back_to_the_work(self):
        self.moved()
        self.push(3, "feat/b")
        self.session(4, "acceptance")
        self.push(4, "feat/b")
        self.work(3, *[("Edit", "/w/wt/b/app.py")] * 3)
        b = self.build()
        self.assertEqual({x["name"]: x["guessedBranches"] for x in b["unassigned"]},
                         {"worker": ["feat/b"], "acceptance": []})

    def test_a_branch_a_commander_pushed_counts_for_its_batch(self):
        self.session(1, "Commander-A")
        self.session(3, "worker")
        self.transcript(3, (1, "Commander-A"))
        self.register("worker", branch="feat/a")
        self.push(1, "feat/a", "feat/b", "feat/c")
        self.prs = {"feat/a": pr(1, "OPEN"), "feat/b": pr(2, "OPEN"), "feat/c": pr(3, "MERGED")}
        self.mine = {"open": [{"number": 1, "headRefName": "feat/a"}, {"number": 2, "headRefName": "feat/b"}],
                     "mergedToday": []}
        b = self.build()
        g = self.group(b, "Commander-A")
        # feat/a stays the worker's; feat/b counts for the batch; feat/c merged before it was ever seen open
        self.assertEqual((g["summary"]["prs"], g["leadRow"]["guessedBranches"], g["leadRow"]["pr"]), (2, ["feat/b"], None))
        self.assertTrue(any("PR #2 (feat/b) was pushed by Commander-A" in h for h in b["hints"]))
        self.assertFalse(any("belongs to no session" in h for h in b["hints"]))
        self.prs["feat/b"] = pr(2, "MERGED")
        s = self.group(self.build(), "Commander-A")["summary"]
        self.assertEqual((s["prsMerged"], s["prs"]), (1, 2))

    def test_a_commanders_push_does_not_outrank_its_members_work(self):
        self.moved()
        self.session(1, "Commander-A")
        self.push(1, "feat/b")
        self.work(3, *[("Edit", "/w/wt/b/app.py")] * 3)
        b = self.build()
        self.assertEqual(b["unassigned"][0]["guessedBranches"], ["feat/b"])

    def test_text_that_only_looks_like_a_push_is_ignored(self):
        from admiral import sessions
        two = {"s3": {"pushed": ["feat/b"], "counts": {}}, "s4": {"pushed": ["feat/a", "feat/b"], "counts": {}}}
        self.assertEqual((sessions.pushed_by(two, "feat/b"), sessions.pushed_by(two, "feat/a")), (None, "s4"))
        self.assertEqual(sessions.pushed("To run it:\n * [new branch] feat/x -> feat/x\n"), [])
        self.assertEqual(sessions.pushed("From github.com:o/app\n * [new branch]  feat/x -> origin/feat/x\n"), [])
        self.assertEqual(sessions.pushed("To github-alias:o/app.git\n ! [rejected]  feat/x -> feat/x (fetch first)\n"), [])
        self.assertEqual(sessions.pushed("To github-alias:o/app.git\n + 1a2b3c4...5e6f7a8 feat/x -> feat/x (forced update)\n"
                                         "   1a2b3c4..5e6f7a8  HEAD -> refs/heads/feat/y\n"), ["feat/x", "feat/y"])

    def test_unclear_work_attaches_nothing(self):
        self.moved()
        self.work(3, *[("Bash", "cd /w/wt/b")] * 3)
        self.session(4, "other")
        self.work(4, *[("Bash", "cd /w/wt/b")] * 2)
        b = self.build()
        self.assertEqual([x["guessedBranches"] for x in b["unassigned"]], [[], []])
        self.assertTrue(any("PR #9 (feat/b) belongs to no session" in h for h in b["hints"]))

    def test_a_merged_branch_is_never_attached(self):
        self.moved()
        self.prs = {"feat/b": pr(9, "MERGED")}
        self.work(3, *[("Edit", "/w/wt/b/app.py")] * 5)
        x = self.build()["unassigned"][0]
        self.assertEqual((x["pr"], x["guessedBranches"], x["stage"], x["done"]), (None, [], 1, False))

    def test_a_commanders_work_does_not_count(self):
        self.moved()
        self.session(1, "Commander-A")
        self.work(1, *[("Bash", "git -C /w/wt/b push")] * 5)
        b = self.build()
        self.assertEqual([x["guessedBranches"] for g in b["groups"] for x in [g["leadRow"]] + g["members"]]
                         + [x["guessedBranches"] for x in b["unassigned"]], [[], []])
        self.assertTrue(any("PR #9 (feat/b) belongs to no session" in h for h in b["hints"]))

    def test_a_worktree_inside_another_is_told_apart(self):
        self.moved()
        self.checked_out = {"/w/app": "main", "/w/app/.claude/worktrees/b": "feat/b"}
        self.work(3, *[("Edit", "/w/app/.claude/worktrees/b/app.py")] * 3)
        self.assertEqual(self.build()["unassigned"][0]["guessedBranches"], ["feat/b"])

    def test_the_work_scan_reads_only_new_whole_lines(self):
        self.moved()
        self.work(3, ("Edit", "/w/wt/b/a.py"), ("Edit", "/w/wt/b/b.py"), cut='{"type": "assistant", "mess')
        self.assertEqual(self.build()["unassigned"][0]["guessedBranches"], [])  # two whole actions: not yet
        from admiral import sessions
        with open(sessions.transcript(self.cfg, "/w/app", "s3"), "a", encoding="utf-8") as fh:
            fh.write('age": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/w/wt/b/c.py"}}]}}\n')
        self.assertEqual(self.build()["unassigned"][0]["guessedBranches"], ["feat/b"])


class Waiting(World):
    def say(self, pid, *entries):
        from admiral import sessions
        path = sessions.transcript(self.cfg, "/w/app", f"s{pid}")
        with open(path, "a", encoding="utf-8") as fh:
            for kind, text in entries:
                if kind == "user":
                    d = {"type": "user", "message": {"role": "user", "content": text}}
                else:
                    blocks = [{"type": "text", "text": text}]
                    if kind == "assistant-tool":
                        blocks.append({"type": "tool_use", "id": "t1", "name": "Bash", "input": {}})
                    d = {"type": "assistant", "message": {"role": "assistant", "content": blocks}}
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
                fh.write(json.dumps({"type": "file-history-snapshot"}) + "\n")

    def waiting(self, b):
        return {x["name"]: x["waitKind"] for x in b["waiting"]}

    def test_a_turn_that_ended_asking_the_person_is_maybe_waiting(self):
        self.session(3, "acceptance")
        self.say(3, ("user", "run it"), ("assistant", "The migration has not run yet. Do you want me to go ahead?"))
        b = self.build(use_gh=False)
        self.assertEqual(self.waiting(b), {"acceptance": "maybe"})
        self.assertIn("go ahead?", b["waiting"][0]["waitingFor"])

    def test_a_long_ask_is_cut_at_a_word(self):
        from admiral import sessions
        long = "The new scorer ranks 3 of the 20 sample queries worse than the old one on the checkout page. " \
               "Do you want me to switch to it anyway, or keep both behind a flag?"
        cut = sessions.tail(long)
        self.assertTrue(cut.startswith("…") and cut.endswith("behind a flag?"))
        self.assertIn(" " + cut[1:].split(" ")[0] + " ", " " + long + " ")  # it starts on a whole word
        self.assertLessEqual(len(cut), 101)
        self.assertEqual(sessions.tail("Short question?"), "Short question?")
        self.assertEqual(sessions.tail("确" * 150)[:2], "…确")

    def test_chinese_asks_are_recognised(self):
        self.session(3, "验收")
        self.say(3, ("assistant", "部署还没开始，需要你在这里同意一下。"))
        self.assertEqual(self.waiting(self.build(use_gh=False)), {"验收": "maybe"})

    def test_a_report_the_person_answered_or_a_running_tool_is_not_waiting(self):
        for pid in (3, 4, 5):
            self.session(pid, f"s-{pid}")
        self.say(3, ("assistant", "Pushed; CI is green."))
        self.say(4, ("assistant", "Shall I continue?"), ("user", "yes"))
        self.say(5, ("assistant-tool", "Do you want tests first?"))
        self.assertEqual(self.waiting(self.build(use_gh=False)), {})

    def test_an_old_ask_or_a_working_session_is_not_offered(self):
        self.session(3, "old", since=NOW - 13 * 3600)
        self.session(4, "busy", status="busy")
        self.say(3, ("assistant", "Shall I continue?"))
        self.say(4, ("assistant", "Shall I continue?"))
        self.assertEqual(self.waiting(self.build(use_gh=False)), {})

    def test_a_reported_wait_shows_its_note_and_a_blocked_one_shows_too(self):
        self.session(3, "one")
        self.session(4, "two", status="waiting", waitingFor="input needed")
        self.register("one", phase="needs_you", note="approve the real-data run")
        b = self.build(use_gh=False)
        self.assertEqual(self.waiting(b), {"one": "reported", "two": "blocked"})
        self.assertEqual(next(x["waitingFor"] for x in b["waiting"] if x["name"] == "one"), "approve the real-data run")


class Closing(World):
    def verdicts(self, b):
        return {x["name"]: k for k, xs in b["closable"].items() for x in xs}

    def test_merged_and_wrapped_up_can_close(self):
        self.session(3, "worker")
        self.register("worker", branch="feat/a", worktree="/w/wt/a")
        self.prs = {"feat/a": pr(1, "MERGED")}
        self.commits = {"/w/wt/a": "gone"}
        self.assertEqual(self.verdicts(self.build()).get("worker"), "close")

    def deregister(self, who):
        from admiral import registry
        registry.done(self.cfg, who)

    def test_a_session_that_wrapped_up_and_deregistered_can_close_and_counts_as_merged(self):
        self.session(1, "Commander-A")
        self.session(3, "worker")
        self.transcript(3, (1, "Commander-A"))
        self.register("worker", branch="feat/a", worktree="/w/wt/a", lead="Commander-A")
        self.prs = {"feat/a": pr(1, "OPEN")}
        self.build()
        self.prs = {"feat/a": pr(1, "MERGED")}
        self.commits = {"/w/wt/a": "gone"}
        self.deregister("worker")
        b = self.build()
        v = self.verdicts(b)
        self.assertEqual((v.get("worker"), v.get("Commander-A")), ("close", "close"))
        self.assertEqual(self.group(b, "Commander-A")["summary"]["pct"], 100)
        self.assertFalse(any("worker" in h for h in b["hints"]))

    def test_a_deregistered_session_whose_worktree_remains_must_wrap_up_and_holds_its_commander(self):
        self.session(1, "Commander-A")
        self.session(3, "worker")
        self.transcript(3, (1, "Commander-A"))
        self.register("worker", branch="feat/a", worktree="/w/wt/a", lead="Commander-A")
        self.prs = {"feat/a": pr(1, "MERGED")}
        self.commits = {"/w/wt/a": NOW - 60}
        self.build()
        self.deregister("worker")
        v = self.verdicts(self.build())
        self.assertEqual(v.get("worker"), "wrapup")
        self.assertNotIn("Commander-A", v)

    def test_a_deregistered_session_that_did_not_finish_is_not_counted_done(self):
        self.session(3, "worker")
        self.register("worker", branch="feat/a")
        self.prs = {"feat/a": pr(1, "OPEN")}
        self.build()
        self.deregister("worker")
        b = self.build()
        self.assertEqual(b["unassigned"][0]["stage"], 0)
        self.assertIsNone(self.verdicts(b).get("worker"))

    def test_merged_with_its_worktree_or_a_lock_left_must_wrap_up(self):
        self.session(3, "worker")
        self.register("worker", branch="feat/a", worktree="/w/wt/a")
        self.prs = {"feat/a": pr(1, "MERGED")}
        self.commits = {"/w/wt/a": NOW - 100}
        self.lock("port-8100", "worker acceptance service")
        b = self.build()
        self.assertEqual(self.verdicts(b).get("worker"), "wrapup")
        why = next(x["why"] for x in b["closable"]["wrapup"] if x["name"] == "worker")
        self.assertIn("worktree not deleted", why)
        self.assertIn("holds 1 lock", why)

    def test_working_waiting_or_an_open_pr_keeps_it(self):
        self.session(3, "one", status="busy")
        self.session(4, "two", status="waiting")
        self.session(5, "three")
        self.register("three", branch="feat/c")
        self.prs = {"feat/c": pr(3, "OPEN")}
        self.assertEqual(self.verdicts(self.build()), {})

    def test_a_commander_without_members_is_for_the_person_to_confirm(self):
        self.session(1, "Commander-A")
        self.session(2, "Commander-B")
        self.register("Commander-B", phase="done")
        v = self.verdicts(self.build(use_gh=False))
        self.assertEqual((v.get("Commander-A"), v.get("Commander-B")), ("confirm", "close"))

    def test_a_commander_closes_by_the_steps_the_wrapup_skill_gives(self):
        from admiral import registry
        self.session(1, "Commander-A")
        self.register("Commander-A")
        self.plan("Commander-A", ("feat/a", "first", "worker"))
        self.prs = {"feat/a": pr(1, "MERGED")}  # its member has closed; the plan is all merged
        b = self.build()
        self.assertEqual(self.verdicts(b)["Commander-A"], "wrapup")
        self.assertIn("close the plan and report done", next(c["why"] for c in b["closable"]["wrapup"]))
        registry.plan_close(self.cfg, "Commander-A")
        self.assertEqual(self.verdicts(self.build())["Commander-A"], "confirm")  # the plan closed, done not reported
        registry.set_phase(self.cfg, "Commander-A", "done")
        self.assertEqual(self.verdicts(self.build())["Commander-A"], "close")

    def test_an_old_unregistered_idle_session_is_for_the_person_to_confirm(self):
        self.session(3, "scratch", since=NOW - 30 * 3600)
        self.session(4, "fresh", since=NOW - 600)
        v = self.verdicts(self.build(use_gh=False))
        self.assertEqual((v.get("scratch"), v.get("fresh")), ("confirm", None))

    def test_a_closed_unmerged_pr_is_for_the_person_to_confirm(self):
        self.session(3, "worker")
        self.register("worker", branch="feat/a")
        self.prs = {"feat/a": pr(1, "CLOSED")}
        self.assertEqual(self.verdicts(self.build()).get("worker"), "confirm")


class Evidence(World):
    """Merged is what GitHub says. A session's own word that it is done shows as reported done: it ends the session's
    progress only where no PR speaks for it, never counts as a merge, and never alone makes a session closable."""

    def verdicts(self, b):
        return {x["name"]: k for k, xs in b["closable"].items() for x in xs}

    def why(self, b, name):
        return next(x["why"] for xs in b["closable"].values() for x in xs if x["name"] == name)

    def batch(self, phase, pr_=None):
        """A commander whose plan has one deliverable, feat/a, owned by a live, registered worker."""
        self.session(1, "Commander-A")
        self.session(3, "worker")
        self.register("worker", branch="feat/a", lead="Commander-A", phase=phase)
        self.plan("Commander-A", ("feat/a", "the deliverable", "worker"))
        if pr_:
            self.prs = {"feat/a": pr_}
        b = self.build()
        g = self.group(b, "Commander-A")
        return b, g, next(x for x in g["members"] if x["name"] == "worker")

    def test_a_draft_pr_leaves_the_session_where_its_phase_says(self):
        draft = dict(pr(1, "OPEN"), isDraft=True)
        b, g, x = self.batch("working", draft)
        self.assertEqual((x["stage"], g["batch"]["items"][0]["stage"], g["summary"]["pct"]), (1, 1, 25))
        self.prs = {"feat/a": dict(draft, isDraft=False)}  # marked ready: now it is in CI
        g = self.group(self.build(), "Commander-A")
        self.assertEqual((g["batch"]["items"][0]["stage"], g["summary"]["pct"]), (4, 80))

    def test_done_with_no_pr_is_reported_done_not_merged(self):
        b, g, x = self.batch("done")
        self.assertEqual((x["stage"], x["reportedDone"], g["summary"]["pct"]), (5, True, 100))
        self.assertEqual((g["summary"]["prsMerged"], g["summary"]["prs"], b["prsMerged"], b["prs"]), (0, 1, 0, 1))
        md = board.markdown(b)
        self.assertIn("progress 100% (reported done 1)", md)
        self.assertIn("plan, merged 0/1", md)
        self.assertIn("| the deliverable | feat/a | worker | reported done | - |", md)
        self.assertIn("| reported done · done |", md)  # the worker's own row
        self.assertNotIn("merged 1/1", md)
        self.assertNotIn("(merged 1", md)
        self.assertEqual(self.verdicts(b)["worker"], "confirm")
        self.assertIn("no merged PR", self.why(b, "worker"))
        self.assertNotIn("Commander-A", self.verdicts(b))  # it waits for its member

    def test_done_with_its_pr_still_open_is_in_ci_not_merged(self):
        b, g, x = self.batch("done", pr(1, "OPEN"))
        self.assertEqual((x["stage"], x["reportedDone"], g["summary"]["prsMerged"], g["summary"]["pct"]),
                         (4, False, 0, 80))
        self.assertNotIn("worker", self.verdicts(b))

    def test_done_with_its_pr_closed_unmerged_is_not_finished(self):
        b, g, x = self.batch("done", pr(1, "CLOSED"))
        self.assertEqual((x["stage"], x["done"], g["summary"]["prsMerged"]), (3, False, 0))
        self.assertEqual(self.verdicts(b)["worker"], "confirm")
        self.assertIn("PR closed without merging", self.why(b, "worker"))

    def test_done_and_merged_is_merged(self):
        b, g, x = self.batch("done", pr(1, "MERGED"))
        self.assertEqual((x["stage"], x["reportedDone"], g["summary"]["prsMerged"], g["summary"]["prs"]),
                         (5, False, 1, 1))
        self.assertEqual(self.verdicts(b)["worker"], "close")
        self.assertIn("progress 100% (merged 1)", board.markdown(b))

    def test_with_github_down_done_is_not_taken_as_done_without_a_pr(self):
        b, g, x = self.batch("done", pr(1, "OPEN"))
        self.assertEqual(g["summary"]["pct"], 80)
        self.gh_down = True  # GitHub does not answer: the open PR is unknown, not gone
        b = self.build()
        g = self.group(b, "Commander-A")
        x = next(x for x in g["members"] if x["name"] == "worker")
        self.assertIn("gh failed", " ".join(b["health"]))
        self.assertEqual((x["stage"], x["reportedDone"], g["batch"]["items"][0]["stage"]), (3, False, 3))
        self.assertEqual((g["summary"]["pct"], g["summary"]["prsMerged"]), (70, 0))
        self.assertNotIn("worker", self.verdicts(b))

    def test_with_github_down_a_task_with_no_branch_still_ends_on_its_report(self):
        self.gh_down = True
        self.session(3, "investigation")
        self.register("investigation", phase="done")  # no branch: no PR could speak for it
        x = self.build()["unassigned"][0]
        self.assertEqual((x["stage"], x["reportedDone"]), (5, True))

    def test_a_commander_with_its_own_pr_open_is_kept(self):
        self.session(1, "Commander-A")
        self.register("Commander-A", branch="chore/a", phase="done")
        self.prs = {"chore/a": pr(5, "OPEN")}
        self.assertNotIn("Commander-A", self.verdicts(self.build()))

    def test_a_deliverable_keeps_its_owners_report_after_the_owner_deregisters(self):
        from admiral import registry
        self.batch("done")
        registry.done(self.cfg, "worker")  # wrapped up; its session still runs
        g = self.group(self.build(), "Commander-A")
        it = g["batch"]["items"][0]
        self.assertEqual((it["stage"], it["reportedDone"], g["summary"]["pct"], g["summary"]["prsMerged"]),
                         (5, True, 100, 0))

    def test_a_plan_finished_only_by_reports_is_for_the_person_to_confirm(self):
        self.session(1, "Commander-A")
        self.register("worker", branch="feat/a", lead="Commander-A", phase="done")  # its session has closed
        self.register("other", branch="feat/b", lead="Commander-A")
        self.plan("Commander-A", ("feat/a", "reported", "worker"), ("feat/b", "merged", "other"))
        self.prs = {"feat/b": pr(2, "MERGED")}
        b = self.build()
        self.assertEqual(self.verdicts(b)["Commander-A"], "confirm")
        self.assertIn("1 deliverable", self.why(b, "Commander-A"))
        self.prs["feat/a"] = pr(1, "MERGED")
        b = self.build()
        self.assertEqual(self.verdicts(b)["Commander-A"], "wrapup")  # all merged: close the plan
        self.assertEqual(self.group(b, "Commander-A")["summary"]["prsMerged"], 2)

    def test_a_deregistered_session_is_judged_by_the_same_evidence(self):
        from admiral import registry
        self.session(3, "closed-pr")
        self.session(4, "no-pr")
        self.register("closed-pr", branch="feat/a", phase="done")
        self.register("no-pr", phase="done")
        self.prs = {"feat/a": pr(1, "CLOSED")}
        self.build()
        registry.done(self.cfg, "closed-pr")
        registry.done(self.cfg, "no-pr")
        b = self.build()
        rows = {x["name"]: x for x in b["unassigned"]}
        self.assertFalse(rows["closed-pr"]["finished"])
        self.assertEqual((rows["no-pr"]["finished"], rows["no-pr"]["reportedDone"]), (True, True))
        v = self.verdicts(b)
        self.assertNotEqual(v.get("closed-pr"), "close")
        self.assertEqual(v.get("no-pr"), "confirm")

    def status_lines(self, b, sid):
        """The status line a session sees, drawn from the board as written: (raw, without colors)."""
        import re
        from admiral import statusline
        board.write(self.cfg, b)
        raw = statusline.admiral_lines(self.cfg.sub("board.json"), sid, now=NOW)
        return raw, [re.sub(r"\x1b\[[0-9;]*m", "", ln) for ln in raw]

    def test_the_status_line_shows_reported_done_and_counts_no_merge(self):
        b, g, x = self.batch("done")
        raw, lines = self.status_lines(b, "s3")
        self.assertTrue(any("100%  PRs merged 0/1" in ln for ln in lines), lines)
        self.assertTrue(lines[-1].startswith("this session  ▰▰▰▰▰ reported done"), lines[-1])
        self.assertIn("\x1b[2m▰", raw[-1])  # the last milestone dim: the session's word, not a merge
        b, g, x = self.batch("done", pr(1, "MERGED"))
        self.assertNotIn("\x1b[2m▰", self.status_lines(b, "s3")[0][-1])

    def test_with_github_down_a_commanders_own_pr_is_unknown_not_absent(self):
        self.session(1, "Commander-A")
        self.register("Commander-A", branch="chore/own", phase="done")
        self.prs = {"chore/own": pr(5, "OPEN")}
        self.build()
        self.gh_down = True
        b = self.build()
        self.assertNotIn("Commander-A", self.verdicts(b))
        self.assertEqual(b["groups"][0]["leadRow"]["stage"], 3)

    def test_with_github_down_a_taken_branch_is_unknown_not_absent(self):
        from tests.test_board import Linking
        self.session(3, "worker")
        self.register("worker", phase="done")  # no branch registered: the board takes the one it pushed
        Linking.push(self, 3, "feat/pushed")
        self.prs = {"feat/pushed": pr(9, "OPEN")}
        self.assertEqual(self.build()["unassigned"][0]["stage"], 4)
        self.gh_down = True
        x = self.build()["unassigned"][0]
        self.assertEqual((x["stage"], x["reportedDone"]), (3, False))

    def test_an_owners_last_registration_speaks_only_for_the_deliverables_it_named(self):
        from admiral import registry
        self.batch("done")  # worker reported feat/a done, with no PR
        registry.done(self.cfg, "worker")
        self.plan("Commander-A", ("feat/new", "next", "worker"))  # planned for it since, not started
        items = {i["branch"]: i["stage"] for i in self.group(self.build(), "Commander-A")["batch"]["items"]}
        self.assertEqual(items, {"feat/a": 5, "feat/new": 0})

    def test_an_owner_renamed_after_deregistering_keeps_its_deliverable(self):
        from admiral import registry
        self.batch("done")
        registry.done(self.cfg, "worker")
        self.build()
        self.session(3, "worker-2", former=("worker",))  # renamed in Claude Code
        self.plan("Commander-A", ("feat/a", "the deliverable", "worker-2"))  # the plan follows the new name
        g = self.group(self.build(), "Commander-A")
        self.assertEqual((g["batch"]["items"][0]["stage"], g["summary"]["pct"]), (5, 100))

    def test_with_github_down_from_the_start_a_pushed_branch_is_unknown_not_absent(self):
        from tests.test_board import Linking
        self.gh_down = True  # never answered: the push alone says there is a branch
        self.session(1, "Commander-A")
        self.register("Commander-A", phase="done")
        Linking.push(self, 1, "feat/for-a-member")
        self.session(3, "worker")
        self.register("worker", phase="done")
        Linking.push(self, 3, "feat/pushed")
        b = self.build()
        x = b["unassigned"][0]
        self.assertEqual((x["stage"], x["reportedDone"]), (3, False))
        self.assertEqual(self.verdicts(b), {})  # neither can close while GitHub cannot say

    def test_a_commanders_own_pr_closed_unmerged_is_for_the_person_to_confirm(self):
        self.session(1, "Commander-A")
        self.register("Commander-A", branch="feat/a", phase="done")
        self.prs = {"feat/a": pr(1, "CLOSED")}
        b = self.build()
        self.assertEqual((self.verdicts(b)["Commander-A"], self.why(b, "Commander-A")),
                         ("confirm", "PR closed without merging"))

    def test_an_owners_memory_is_only_for_the_branches_its_registration_named(self):
        from admiral import registry
        self.session(3, "worker")
        self.register("worker", branch="feat/a", worktree="/w/wt/a", phase="done")
        self.checked_out = {"/w/wt/a": "feat/b"}  # its worktree has another branch checked out
        self.build()
        registry.done(self.cfg, "worker")
        self.plan("Commander-A", ("feat/b", "never registered", "worker"))
        self.assertEqual(self.group(self.build(), "Commander-A")["batch"]["items"][0]["stage"], 0)

    def test_two_owners_that_swapped_names_keep_each_their_deliverable(self):
        from admiral import registry
        self.session(3, "alpha")
        self.session(4, "beta")
        self.register("alpha", branch="feat/a", phase="done")
        self.register("beta", branch="feat/b", phase="done")
        self.build()
        registry.done(self.cfg, "alpha")
        registry.done(self.cfg, "beta")
        self.session(3, "beta", former=("alpha",))
        self.session(4, "alpha", former=("beta",))
        self.plan("Commander-A", ("feat/a", "a", "alpha"), ("feat/b", "b", "beta"))
        items = {i["branch"]: i["stage"] for i in self.group(self.build(), "Commander-A")["batch"]["items"]}
        self.assertEqual(items, {"feat/a": 5, "feat/b": 5})

    def test_a_session_that_finished_and_deregistered_reads_as_finished(self):
        from admiral import registry
        self.session(3, "investigation")
        self.register("investigation", phase="done")
        self.build()
        registry.done(self.cfg, "investigation")  # wrapped up; its session still runs
        b = self.build()
        self.assertIn("| investigation | idle 10 min | reported done |", board.markdown(b))
        self.assertTrue(self.status_lines(b, "s3")[1][-1].startswith("this session  ▰▰▰▰▰ reported done"))


class FinishedBatches(World):
    """A batch whose commander has gone: over once every deliverable merged and nobody of it runs, and then no longer
    shown, its plan left for `admiral plan close`; else still shown, marked commander not running."""

    def setUp(self):
        super().setUp()
        self.session(4, "elsewhere")  # some session runs, so the board is built and GitHub asked

    def gone(self, *prs_by_branch):
        self.plan("Commander-Gone", *[(b, b, "worker") for b, _ in prs_by_branch])
        self.prs = {b: p for b, p in prs_by_branch if p}
        return self.build()

    def lead_of(self, b):
        return next((g for g in b["groups"] if g["lead"] == "Commander-Gone"), None)

    def test_a_batch_all_merged_with_nobody_running_leaves_the_board_and_its_plan_stays(self):
        from admiral import registry, statusline
        import re
        b = self.gone(("feat/a", pr(1, "MERGED")), ("feat/b", pr(2, "MERGED")))
        self.assertIsNone(self.lead_of(b))
        self.assertEqual([p["lead"] for p in registry.plans(self.cfg)], ["Commander-Gone"])  # the board closes no plan
        self.assertIn('the plan of Commander-Gone is all merged and nobody of its batch runs: no longer shown; '
                      'admiral plan close --lead "Commander-Gone" puts it away', b["hints"])
        self.assertEqual((b["prsMerged"], b["prs"]), (0, 0))  # not counted, as a closed plan is not
        board.write(self.cfg, b)
        shown = " ".join(re.sub(r"\x1b\[[0-9;]*m", "", ln)
                         for ln in statusline.admiral_lines(self.cfg.sub("board.json"), "s4", now=NOW))
        self.assertNotIn("Gone", shown)
        self.assertNotIn("commander not running", shown)
        self.assertNotIn("## Commander-Gone", board.markdown(b))

    def test_a_batch_with_anything_unmerged_stays_marked_commander_not_running(self):
        for second in (pr(2, "OPEN"), pr(2, "CLOSED"), None):
            with self.subTest(second=second):
                self.tearDown()
                self.setUp()
                g = self.lead_of(self.gone(("feat/a", pr(1, "MERGED")), ("feat/b", second)))
                self.assertIsNotNone(g)
                self.assertIsNone(g["leadRow"])

    def test_a_deliverable_only_reported_done_keeps_the_batch(self):
        self.register("worker", branch="feat/b", phase="done")  # its session has closed; no PR
        self.assertIsNotNone(self.lead_of(self.gone(("feat/a", pr(1, "MERGED")), ("feat/b", None))))

    def test_with_github_down_the_batch_is_kept(self):
        self.gh_down = True
        self.assertIsNotNone(self.lead_of(self.gone(("feat/a", pr(1, "MERGED")))))

    def test_a_running_commander_closes_its_own_plan(self):
        self.session(1, "Commander-Gone")
        g = self.lead_of(self.gone(("feat/a", pr(1, "MERGED"))))
        self.assertIsNotNone(g)
        self.assertEqual(g["leadRow"]["close"], "wrapup")  # "plan all merged: close the plan and report done"

    def test_a_member_still_running_keeps_the_batch(self):
        self.session(3, "worker")
        self.register("worker", branch="feat/a", lead="Commander-Gone")
        g = self.lead_of(self.gone(("feat/a", pr(1, "MERGED"))))
        self.assertEqual([m["name"] for m in g["members"]], ["worker"])

    def test_an_owner_still_running_keeps_the_batch_though_nothing_groups_it(self):
        for name, former in (("worker", ()), ("worker-2", ("worker",))):  # by its name, or the one it had
            with self.subTest(name=name):
                self.tearDown()
                self.setUp()
                self.session(3, name, former=former)
                self.register(name, branch="feat/a")  # no --lead, no commander message
                b = self.gone(("feat/a", pr(1, "MERGED")))
                self.assertIsNotNone(self.lead_of(b))
                self.assertFalse([h for h in b["hints"] if "nobody of its batch runs" in h])

    def test_a_member_that_only_heard_from_the_commander_keeps_the_batch(self):
        self.session(1, "Commander-Gone")
        self.session(3, "reviewer")  # no --lead, owns no planned PR: its batch is known from the commander's message
        self.transcript(3, (1, "Commander-Gone"))
        self.assertEqual([m["name"] for m in self.lead_of(self.gone(("feat/a", pr(1, "MERGED"))))["members"]],
                         ["reviewer"])
        os.remove(os.path.join(self.root, "sessions", "1.json"))  # the commander exits; the reviewer runs on
        b = self.build()
        self.assertIsNotNone(self.lead_of(b))
        self.assertFalse([h for h in b["hints"] if "nobody of its batch runs" in h])

    def test_an_empty_plan_is_not_taken_for_a_finished_one(self):
        self.plan("Commander-Gone", ("feat/a", "a", "worker"))
        from admiral import registry
        registry.plan_remove(self.cfg, "Commander-Gone", "feat/a")
        self.assertIsNotNone(self.lead_of(self.build()))

    def test_the_board_leaves_the_plan_file_as_it_was(self):
        self.plan("Commander-Gone", ("feat/a", "a", "worker"))
        self.prs = {"feat/a": pr(1, "MERGED")}
        d = self.cfg.sub("batches")
        before = {f: (open(os.path.join(d, f), "rb").read(), os.stat(os.path.join(d, f)).st_mtime_ns) for f in os.listdir(d)}
        self.assertIsNone(self.lead_of(self.build()))
        after = {f: (open(os.path.join(d, f), "rb").read(), os.stat(os.path.join(d, f)).st_mtime_ns) for f in os.listdir(d)}
        self.assertEqual(before, after)

    def test_once_the_plan_is_closed_the_hint_goes_too(self):
        from admiral import registry
        self.gone(("feat/a", pr(1, "MERGED")))
        registry.plan_close(self.cfg, "Commander-Gone")
        self.assertFalse([h for h in self.build()["hints"] if "Commander-Gone" in h])


class OneConversation(World):
    """One conversation resumed in several terminals is one session; two sessions sharing a name stay two."""

    def test_a_conversation_open_in_two_terminals_is_one_session(self):
        self.session(3, "worker", status="busy", since=NOW - 300)
        self.session(4, "worker", status="waiting", since=NOW - 30, sessionId="s3")  # the same one, resumed again
        b = self.build(use_gh=False)
        rows = [x for x in b["unassigned"] if x["name"] == "worker"]
        self.assertEqual((b["count"], len(rows)), (1, 1))
        self.assertEqual((rows[0]["status"], rows[0]["tty"]), ("waiting", "ttys004"))  # the one that needs the person
        self.assertEqual(len(b["waiting"]), 1)
        self.assertTrue(any("worker" in h and "ttys003" in h and "ttys004" in h for h in b["hints"]), b["hints"])

    def test_a_commander_open_twice_leads_one_batch(self):
        self.session(1, "Commander-A", status="busy")
        self.session(2, "Commander-A", status="idle", sessionId="s1")
        self.session(3, "worker")
        self.transcript(3, (1, "Commander-A"))
        groups = [g for g in self.build(use_gh=False)["groups"] if g["lead"] == "Commander-A"]
        self.assertEqual(len(groups), 1)
        self.assertEqual([m["name"] for m in groups[0]["members"]], ["worker"])

    def test_a_message_from_any_process_of_a_commander_finds_it(self):
        self.session(1, "Commander-New", status="waiting")
        self.session(2, "Commander-New", status="idle", sessionId="s1")  # the same commander; it wrote to the member
        self.session(3, "worker")
        self.transcript(3, (2, "Commander-Old"))  # under a name no session keeps: only its process tells who it was
        g = next(g for g in self.build(use_gh=False)["groups"] if g["lead"] == "Commander-New")
        self.assertEqual([m["name"] for m in g["members"]], ["worker"])

    def test_a_name_only_one_process_remembers_still_finds_the_session(self):
        self.session(1, "Commander-New", status="waiting")
        self.session(2, "Commander-New", status="idle", sessionId="s1", former=("Commander-Old",))
        self.session(3, "worker")
        self.register("worker", lead="Commander-Old")
        b = self.build(use_gh=False)
        self.assertEqual([[m["name"] for m in g["members"]] for g in b["groups"]], [["worker"]])
        self.assertFalse([h for h in b["hints"] if "not running" in h])

    def test_processes_of_one_conversation_that_differ_in_name_or_directory_lose_nothing(self):
        self.session(1, "Commander-New", status="waiting")
        self.session(2, "Commander-Old", sessionId="s1")  # renamed in one terminal only
        self.session(3, "worker")
        self.session(5, "helper", cwd="/w/app/wt")
        self.session(6, "helper", cwd="/w/app", sessionId="s5")  # resumed from another directory
        self.transcript(5, (1, "Commander-New"), cwd="/w/app/wt")
        self.register("worker", lead="Commander-Old")
        b = self.build(use_gh=False)
        self.assertFalse([h for h in b["hints"] if "not running" in h], b["hints"])
        self.assertEqual([m["name"] for m in self.group(b, "Commander-Old")["members"]], ["worker"])
        self.assertEqual([m["name"] for m in self.group(b, "Commander-New")["members"]], ["helper", "helper"])
        self.assertEqual(len([h for h in b["hints"] if "open 2 times" in h]), 2)  # still told it is open twice

    def test_a_member_open_twice_is_one_member(self):
        self.session(1, "Commander-A")
        self.session(3, "worker", status="idle")
        self.session(4, "worker", status="busy", sessionId="s3")
        self.register("worker", lead="Commander-A")
        g = self.group(self.build(use_gh=False), "Commander-A")
        self.assertEqual(([m["name"] for m in g["members"]], g["summary"]["busy"]), (["worker"], 1))

    def test_two_processes_in_one_terminal_are_named_once(self):
        self.session(3, "worker", status="busy")
        self.session(4, "worker", status="idle", sessionId="s3")
        b2 = board.build(self.cfg, use_gh=False, now=NOW, starts=lambda pids: {p: (START, "ttys001") for p in pids})
        hint = next(h for h in b2["hints"] if "open 2 times" in h)
        self.assertIn("(ttys001)", hint)

    def test_two_sessions_sharing_a_commanders_name_both_stay_shown(self):
        self.session(1, "Commander-A", status="busy")
        self.session(2, "Commander-A", status="waiting")  # another conversation, given the same name
        b = self.build(use_gh=False)
        self.assertEqual(sorted(g["leadRow"]["sessionId"] for g in b["groups"]), ["s1", "s2"])  # neither is dropped
        self.assertFalse([h for h in b["hints"] if "times (" in h])

    def test_different_conversations_with_different_names_stay_apart(self):
        self.session(3, "one", status="busy")
        self.session(4, "two", status="waiting")
        b = self.build(use_gh=False)
        self.assertEqual(sorted(x["name"] for x in b["unassigned"]), ["one", "two"])
        self.assertFalse([h for h in b["hints"] if "times (" in h])


class Sources(World):
    def test_a_registered_branch_keeps_its_merge_while_its_session_is_away(self):
        self.session(4, "other")  # keeps the board refreshing
        self.register("worker", branch="feat/a")  # its session has exited; the registration stays
        self.prs = {"feat/a": pr(1, "MERGED")}
        self.build()
        self.prs = {}  # the merge fell out of the 300 most recent PRs
        self.build(now=NOW + 60)
        self.build(now=NOW + 120)
        self.session(3, "worker")  # back
        x = next(x for x in self.build(now=NOW + 180)["unassigned"] if x["name"] == "worker")
        self.assertEqual((x["stage"], (x["pr"] or {}).get("state")), (5, "MERGED"))

    def test_open_prs_past_the_open_list_say_their_ci_is_not_shown(self):
        self.session(3, "worker")
        self.register("worker", branch="feat/a")
        self.prs = {"feat/a": dict(pr(1, "OPEN"), checksUnknown=True)}
        self.assertIn("1 open PR is past the newest 100: its CI is not shown", self.build()["health"])

    def test_no_session_means_no_github_call(self):
        self.register("gone", branch="feat/a")
        self.build()
        self.assertEqual(self.gh_calls, [])

    def test_quiet_sessions_ask_github_every_quarter_hour(self):
        self.session(3, "worker", since=NOW - 2 * 3600)
        self.register("worker", branch="feat/a")
        self.prs = {"feat/a": pr(1, "OPEN")}
        self.build()
        self.prs = {"feat/a": pr(1, "MERGED")}
        b = self.build(now=NOW + 5 * 60)
        self.assertEqual((len(self.gh_calls), b["unassigned"][0]["pr"]["state"], b["ghReused"]), (1, "OPEN", True))
        b = self.build(now=NOW + 16 * 60)
        self.assertEqual((len(self.gh_calls), b["unassigned"][0]["pr"]["state"]), (2, "MERGED"))

    def test_a_working_session_keeps_github_asked_every_run(self):
        self.session(3, "worker", status="busy")
        self.register("worker", branch="feat/a")
        self.build()
        self.build(now=NOW + 60)
        self.assertEqual(len(self.gh_calls), 2)

    def test_without_a_repository_github_is_never_asked(self):
        self.cfg.repo_dir = ""
        self.session(3, "worker", status="busy")
        self.register("worker", branch="feat/a")
        self.build()
        self.assertEqual(self.gh_calls, [])

    def test_a_session_file_missing_fields_is_reported(self):
        self.session(1, "Commander-A")
        with open(os.path.join(self.root, "sessions", "2.json"), "w", encoding="utf-8") as fh:
            json.dump({"pid": 2, "sessionId": "s2", "cwd": "/w/app", "procStart": START}, fh)
        self.assertTrue(any("lack" in h for h in self.build(use_gh=False)["health"]))

    def test_no_commander_message_anywhere_is_reported(self):
        self.session(1, "Commander-A")
        self.session(3, "worker")
        self.assertTrue(any("grouping by message may be off" in h for h in self.build(use_gh=False)["health"]))

    def test_missing_transcripts_are_reported(self):
        from admiral import sessions
        self.session(1, "Commander-A")
        self.session(3, "worker")
        os.remove(sessions.transcript(self.cfg, "/w/app", "s3"))
        self.assertTrue(any("no transcript found" in h for h in self.build(use_gh=False)["health"]))


class Chinese(World):
    language = "zh"

    def test_the_board_speaks_the_configured_language(self):
        self.cfg.commander_prefix = "总指挥"
        self.session(1, "总指挥-甲")
        self.session(3, "执行-一")
        self.transcript(3, (1, "总指挥-甲"))
        self.register("执行-一", phase="Codex审查")
        b = self.build(use_gh=False)
        md = board.markdown(b)
        self.assertIn("## 总指挥-甲", md)
        self.assertIn("审查 · 审查中", md)  # "Codex审查" is still accepted as input
        self.assertIn("开发 25%、审查 50%", md)
        self.assertEqual(b["words"]["waiting"], "待处理")

    def test_a_waiting_line_reads_as_chinese(self):
        self.cfg.commander_prefix = "总指挥"
        self.session(1, "总指挥-甲")
        self.session(3, "执行-一", since=NOW - 20)
        self.register("执行-一", lead="总指挥-甲", phase="needs_you", note="批准沙箱密钥")
        md = board.markdown(self.build(use_gh=False))
        self.assertIn("- 执行-一（总指挥-甲）：批准沙箱密钥，刚刚", md)

    def test_reported_done_reads_as_chinese(self):
        self.session(3, "执行-一")
        self.register("执行-一", phase="完成")
        b = self.build(use_gh=False)
        md = board.markdown(b)
        self.assertIn("已报告完成 · 完成", md)
        self.assertIn("已报告完成，但没有已合并的 PR", next(x["why"] for x in b["closable"]["confirm"]))


if __name__ == "__main__":
    unittest.main()
