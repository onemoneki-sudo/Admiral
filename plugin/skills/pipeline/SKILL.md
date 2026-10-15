---
name: pipeline
description: The delivery pipeline for AI sessions working in parallel - task brief, development with affected tests, independent refutation by a different model, acceptance, when to run the full gate, the pre-ready report, one push straight to ready, fixes after ready, stacked PRs and how to word completion. Read before starting a feature or fix, when development of a branch is done, before running the full test gate, before pushing or opening a PR, after a PR is ready, and before reporting work as done.
---

# Delivery pipeline

Where the project's own rules differ from this playbook, the project's rules win.

```
brief → develop (lint + affected tests) → independent refutation → (if needed) person's acceptance
→ (if needed) full gate on the final candidate → pre-ready report → person decides → one push, PR ready → merge
```

## 1. Write the task brief first

Before each feature or fix: goal, real user and entry point, triggering data, expected result, what is out of scope, how it will be accepted, which standing product principles apply (where the project keeps any), and decisions specific to this task. A user-facing feature states its entry, who can see it and how to click through acceptance; an entry left to a later PR names that PR. Small fixes take three to five lines (goal, acceptance, out of scope). Where an issue or PR already says enough, the brief cites it. New decisions go into the brief as they are made; work follows the brief plus the rules. Settle the PR split and stacking order at the start; branches never cherry-pick from each other. A batch of parallel sessions keeps one folder outside the repository, the batch folder: the briefs, a status note per session (its progress and the facts the pre-ready report needs) and the decision log (what was decided and why).

## 2. While developing, verify only what is affected

- After each change run the linters and the tests the change directly affects, chosen by the files and callers touched; tests that need a shared resource take its lock first.
- Check logic that is easy to get backwards (dates, directions, units, grouping, caching, fallbacks) with one counterexample that exposes the core error.
- Key fixes have a test that fails before and passes after.
- Record commit, base, result, duration and number of calls for gates and real-model runs; the pre-ready report needs them.

## 3. Independent refutation by a different model

It stands in for a separate self-review: the refutation plus the owner's judgment is the final check, and the
"look for a counterexample" principle is carried by it.

- A review asked by the author from a model other than the one that wrote the code, on a fixed candidate: run it once the branch's work is complete and its affected tests pass; never on half-finished work; before the PR.
- **Run it** when the change alters behaviour (computation, data mapping, caching, concurrency or timing, error handling, permissions, the call chain from entry to output). Skip it for docs, copy, styles and mechanical changes; read the final diff yourself instead.
- Use the repository's review prompt where it has one; otherwise ask for a refutation of the diff against the brief's goal and acceptance. Never let the model read the author's conclusions first (that anchors it to the stated goal).
- For a large branch, review the first round by functional block, each a complete scope with its commits and files; where blocks call each other or share data, put the seam inside one block. The first round is complete only when every block is.
- **Each finding** is judged by whether it blocks the goal: fix what blocks it, choosing the simplest reliable fix yourself; disprove what is not a defect with code paths, tests or a reproduction; defer real but non-blocking problems (an issue when there is a real trigger). The model's opinion is input to your judgment, not a list to execute.
- **Converged** when, with your own verification, nothing blocking remains, whatever the round number or the model's wording.
- **Re-review after fixes** unless all four hold: the fix stays in one file (a fix across files or modules is re-reviewed); it touches no rendering, state transition, storage or permission; its test runs the real path (the page really renders, the endpoint is really called); there is before-fail, after-pass evidence. When unsure, re-review. Gather fixes into one narrowed re-review, at most three rounds.
- Report each round in the conversation: round, the model's verdict and the verdict after your judgment, each finding and its disposition, and what the model did not verify.

## 4. The person's acceptance (when the brief asks for it)

Before marking ready. Changes during acceptance go through steps 2 and 3 again, without triggering the full gate. A large new feature asked for during acceptance goes into a new PR.

- The acceptance executor, where there is one, builds and keeps the acceptance environment; otherwise the PR's owner does. A commander leads the person through acceptance. For a user-facing feature, whoever builds the environment walks the entry and the main flow once as soon as the first version runs.
- Build it first on the latest default branch and record its and each branch's commit; afterwards merge the default branch and new commits in; rebuild only when a branch was rebased, a merge conflicted or the composition is unclear. With several branches, run the affected tests once on the acceptance version.

## 5. The full gate: by default not run

- **Run it only when** the affected tests cannot all be listed (grep the changed functions, classes and files across the repository), or the change alters global behaviour (configuration, middleware, startup, validation, sessions), or it changes CI, runners, dependencies or migrations. Otherwise linters plus affected tests suffice and CI covers the rest.
- When needed, narrow it first; run it once on the final candidate (after acceptance and merging the latest default branch). PRs accepted and readied together run once on their combined version.
- On failure collect all failures, fix the common cause, rerun only what failed or did not run. A test-only fix may go to CI without a local rerun only when the failure was proven to be the test's own, the diff touches only that test, and waiting for the lock would take longer than the rerun.

## 6. Pre-ready report

Before marking ready, give the person a report (a file in the batch folder, a short conclusion in chat), for each PR: PR, title and head commit; refutation rounds, each finding and its disposition (fixed in which commit, disproved with evidence, or kept as is) and whether it converged; your own verdict ("ready" or "not ready, because"); gate scope, version, result and duration, and for anything not run, why and what covered it; CI state; real-model calls and their conclusion; acceptance state; the code-owner paths whose approval is needed; known risks and gaps.

## 7. One push, straight to ready

- Development, acceptance and the gate all happen locally. Once the person decides, push each branch once and open the PR ready (not draft), so CI runs once on the final version. Push earlier only when someone truly needs the remote branch and the person agrees.
- **In a batch, the commander pushes.** Pushing is the person's decision, and in a batch that decision is made at the commander, so the commander carries it out: executors commit locally and send it the branch, worktree and commit; once the person decides, it pushes each (`git -C <worktree> push -u origin <branch>`). Where every push asks for confirmation, the person confirms them in one session rather than across the fleet. The executor that owns the PR then opens it, sets labels and reviewers, writes its body and answers comments. An independent session pushes its own; where a project's rules have executors push their own, they do.
- Marking ready, closing, reopening and merging are the person's or the maintainer's; agents never merge on their own nor bypass required checks or approvals. Agreement to mark ready authorises enabling auto-merge.
- **Stacked PRs** (base is not the default branch): say so on the first line; never auto-merge or merge them (an unprotected base swallows the merge); after the lower PR lands, retarget to the default branch, merge it in (with the lower PR's last head as merge base when it was squashed), push, then enable auto-merge.

## 8. Fixes after ready

New pushes void earlier approvals. Before approval, fix in batches. After approval, a small, scoped fix (tens of lines) with its own test is described in a PR comment (what, why, which commit, how tested) and the reviewer re-approves the increment; a large change, a change to authorisation in a security-gated path, or a change beyond the review's findings goes back through full review.

## 9. Word completion precisely

Keep "implemented", "ready", "mergeable", "merged" and "released" apart; keep "will not run", "not run yet", "failed" and "passed" apart.
