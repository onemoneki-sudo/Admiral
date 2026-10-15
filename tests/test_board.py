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

    def tearDown(self):
        shutil.rmtree(self.root)

    def build(self, use_gh=True, now=NOW):
        def fetch(cfg, branches):
            self.gh_calls.append(set(branches))
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
        self.assertEqual(board.stage_of("review", pr(1, "MERGED")), 5)
        self.assertEqual(board.stage_of("done", None), 5)
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


if __name__ == "__main__":
    unittest.main()
