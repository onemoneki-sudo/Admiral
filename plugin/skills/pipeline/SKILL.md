---
name: pipeline
description: The delivery path for parallel AI sessions - task brief, development with light checks, the person's acceptance, one delivery check (review by a different model beside the pre-push run), push and PR. Read before starting a feature or fix, when development of a branch is done, before running the whole test suite, before pushing or opening a PR, and after a PR is ready.
---

# Delivery pipeline

Light checks while developing, one full check on the final version, one push. This is the default order; a project may
set another in its rules.

```
brief → develop (light checks) → acceptance → delivery check (review ∥ pre-push run) → push, PR → merge
```

Small changes shorten every step.

## 1. Brief

- An independent session first says what it will do, how big it is, how it splits into PRs and whether to name it a
  commander (roles), then waits for the person, unless the fix is small and plainly asked or the person said to go.
- The brief states the goal, the cases acceptance covers and those it leaves alone (so a review does not take every
  edge for a failure), and what is out of scope; work that picks things out is accepted on what it leaves out too, or
  picking everything passes.
- A behaviour change adds its invariants, the point every path passes and the paths that reach it, with the search
  that found them; a different model reviews that plan before the code, while moving it is cheap.
- One PR per result the person can accept at once and per independent fix; split further only for parts that can go
  ahead in parallel, a risky part (permissions, migrations, money) or a whole too large to review clearly, never into
  the layers of one result.

## 2. Develop

- After each change run the linters and the tests you touched; when you change a contract others rely on (a
  signature, a schema), update its callers and run their tests then.
- Adapt an existing test before adding one, and put each on the lowest layer that exposes the error: logic in plain
  tests, database, permissions and concurrency on a real database set up as CI's, a browser only for key user paths.
- See a behaviour change early through its real entry on real data or a faithful copy, since data that suits the
  change hides what real data breaks, and list at the start what relies on the old behaviour.
- Rerun a test only when what it covers changed; heavy runs wait for the delivery check.

## 3. Acceptance

Phase `accepting`. Docs, copy and mechanical changes skip it. For a change people will see or rely on, ask the person
whether they accept it before the PR or by using it once merged, so they never judge from a description. Show it at
its real entry on their data or a faithful copy: a signed-in tab per case with a line on what to expect, each
environment or account on a host name of its own, as a browser shares a host's cookies across ports. A commander
brings its batch's PRs together. Changes made during acceptance get the light checks; the delivery check covers them.

## 4. Delivery check

Phase `checking`, once, on one candidate: a commit and the base it was merged with, both recorded, so every result
proves the same version. Both checks run at the same time:

- **Pre-push run**: the affected tests on the candidate (your branch merged with the latest of its PR's base, in a
  temporary tree), under CI's and production's conditions, since a branch can pass alone and fail beside what landed
  meanwhile. Find them by callers and by searching the names and paths touched (files read at run time have only
  paths; a test that scans the tree is affected by what it scans). Trust an impact tool only once it has been checked
  on this project against changes whose affected tests are known, and add every later miss to that set. Run the whole
  suite only when you cannot tell what is affected or the change is global (configuration, startup, dependencies, CI).
- **Review by a different model** when behaviour changed (Codex for Claude's code, read-only `claude -p` for Codex's);
  otherwise your own read of the final diff. Run it non-interactively, time-limited, with finite input (`codex exec ...
  </dev/null`, or it waits for input). Give it the goal, the brief's decisions, the diff and the repository's review
  prompt, and ask about goal, scope and kind too; never your conclusions, which anchor it. A change too large for one
  review goes in complete parts, with a seam where two parts call each other or share data inside one of them, so no
  interface goes unreviewed.
- Word a security review as checking that each protection holds, since a provider may refuse what reads as an attack.
  A part still refused is recorded as unreviewed, and a PR whose required security review is unfinished does not go
  ready: finish it by an independent review the person approves, never by retrying the refused call in another
  session.
- Group findings by the invariant they break before the first fix, and fix what blocks at the shared point. Review a
  fix again, narrowed to it, unless it stays in one module, avoids rendering, state, storage and permissions, and has a
  real-path test red before and green after; at most three rounds, then whoever decides. A fix that changes what the
  person saw goes back to them.
- When the candidate's commit or its base changes (a fix, a new base, a retarget), rerun the checks that change
  invalidates (the tests it affects, a narrowed review) and keep the rest, so the evidence is for what you push.

## 5. Push and PR

- Before pushing, tell the person what changed, how it was verified and on which candidate, the findings and their
  handling, goal, scope and kind, and what is unverified, and report `needs_you`; they may authorise the push in
  advance on conditions they state, and when one fails you wait.
- Push once, final, and open the PR ready so CI runs on that version; in a batch the commander pushes what executors
  committed.
- After that push only a fix, a conflict or a base change, as each push reruns CI and voids approvals; a default branch
  that merely moved on is not merged in.
- When CI fails, collect every failure, fix their shared cause, rerun those tests and the fix's locally, push once.
- Merging is the person's or the maintainer's, never around required checks or approvals; agreeing to mark a PR ready
  covers auto-merge, except where a rule below holds it back.
- A PR on another unmerged branch says so on its first line and never merges while that branch is its base. Once the
  lower lands, keep your branch if you can: if the lower was squashed, first restore the tie (on a scratch branch from
  the default branch, `git merge -s ours` the lower's final head, then merge that branch into yours), then retarget the
  PR to the default branch. If the lower's history was rewritten under yours, redo your changes on a new branch from
  the default branch and open a replacement PR, since a retarget never changes a PR's head. Never pick a merge base by
  hand; either way, check that the diff shows your changes and nothing else.
- A batch's PRs can pass alone and fail together: check them merged together on the latest default branch before they
  go ready. A PR adding what every change must satisfy (a repository-wide check, a registry, a numbered sequence)
  merges after the PRs it covers, takes them in and fills in what they brought, with no auto-merge until then; two such
  PRs that need each other are ordered or combined before they go ready. When waiting would let harm go on, it merges
  first and the others take it in before they merge.
