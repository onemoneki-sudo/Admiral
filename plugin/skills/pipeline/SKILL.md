---
name: pipeline
description: The delivery path for AI sessions working in parallel - task brief, development with the affected tests, review by a different model, the person's acceptance, pushing and the PR, and how to word completion. Read before starting a feature or fix, when development of a branch is done, before running the whole test suite, before pushing or opening a PR, after a PR is ready, and before reporting work as done.
---

# Delivery pipeline

A default path from task to merge. Shorten it for small changes, and where the project has its own, follow that.

```
brief → develop (affected tests) → review by a different model → the person's acceptance → push, PR → merge
```

## 1. Brief first

An independent session, once it has worked out what is asked and before it writes a design, a brief or code, says in
the chat what it will do, roughly how big that is and how it splits into PRs (below), recommends doing it itself or
being named a commander (see roles), and waits for the person to decide. A small fix asked for plainly, or work the
person said at the start to do directly, it does.

Before a feature or fix, write down its goal, how it will be accepted and what is out of scope; a small fix takes
three lines, and an issue that already says it is cited. Decisions made along the way go into the brief. A batch of
parallel sessions keeps one folder outside the repository for its briefs, a status note per session and the decision
log.

Settle how the work splits into PRs at the start: one PR for each result the person can accept at once, and one for each
independent small fix, since each PR adds review and delivery overhead, including any acceptance and CI the project
requires. Split further only where the parts can each start from the default branch and go ahead at the same time, where
one part is risky (permissions, migrations, money) and is better reviewed alone, or where the whole is too much to
review clearly in one go, judged by how well it can be reviewed, not by its line count. Steps or layers of one result (a
frame and then its content, a backend and its screen) are not split for that alone; a PR that has to wait for another to
merge says why.

## 2. Develop, verifying what is affected

- After each change run the linters and the tests it affects, not the whole suite; tests that need a shared resource
  take its lock first (see resources).
- Verify locally under the conditions CI and production have (versions, services, permissions): what can be caught
  locally is caught there, and a pass under looser conditions does not count.
- Run the whole suite when you cannot tell what is affected, or the change is global (configuration, startup,
  dependencies, CI); otherwise CI covers the rest.

## 3. Review by a different model

- When the change alters behaviour, ask a model other than the one that wrote it (for code Claude wrote, Codex, say)
  to refute it, once the work is complete and its tests pass. Docs, copy and mechanical changes need only your own
  read of the final diff.
- Ask the model, besides for defects, whether the change serves the goal, stays within the brief and holds for every
  case of its kind. Where the repository has its own review prompt, use it, adding only those of these questions it
  does not ask. Give the model the goal and the diff, not your conclusions, which would anchor it.
- Judge each finding by whether it blocks the goal (see principles): fix what blocks it with the simplest reliable
  fix, disprove what is not a defect, defer the rest. The model's opinion is input to your judgment, not a to-do list.
- Have significant fixes reviewed again. Stop when nothing blocking remains, at most three rounds.

## 4. The person's acceptance

How and when is the person's call. A change in behaviour they will see or rely on is best shown at its real entry, on
their data or a faithful copy, rather than described; they may accept it before the PR goes up, or merge it and accept
it by using it, reporting what goes wrong. A commander brings its batch's PRs to the person together, not one by one.
Docs, copy and mechanical changes need none. What changes during acceptance goes through steps 2 and 3 again.

## 5. Push and PR

- Before pushing, tell the person briefly: what changed, how it was verified, the review's findings and what became of
  them, where it stands on goal, scope and kind (see principles), and what is unverified. For a change in behaviour,
  ask whether they want to accept it first or by using it once merged. Report `needs_you` while you wait.
- Pushing is the person's decision. Push once the work is final and open the PR ready, not draft, so CI runs on the
  final version. In a batch, executors commit locally and the commander pushes, so the person decides in one place.
- Once the PR is ready, push only what it needs: a fix, a conflict, a change of base. Every push runs CI again and
  voids approvals, so notes ride along with a fix, and a default branch that merely moved on is not merged in unless
  the repository requires it.
- Merging is the person's or the maintainer's; never go around required checks or approvals. Agreement to mark a PR
  ready covers enabling auto-merge.
- A PR built on another unmerged branch says so on its first line and is not auto-merged; once the lower PR lands,
  retarget it to the default branch.
- PRs of one batch can each pass alone and fail together. Before they go ready, check them merged together on the
  latest default branch. When one adds what every change must satisfy (a check across the repository, a registry, a
  numbered sequence), it merges last: it takes in the default branch and fills in what the others brought, so they
  need no second push or approval, and it is not auto-merged until then. When it guards against harm happening now,
  it merges first instead, and the others take it in before they merge.

## 6. Word completion precisely

Keep "implemented", "ready", "merged" and "released" apart, and "not run", "failed" and "passed".
