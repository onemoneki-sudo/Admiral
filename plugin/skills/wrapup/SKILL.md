---
name: wrapup
description: What to do after a PR merges or closes and when a batch ends, and which AI sessions can be closed - processes, locks, when a worktree and branch may be deleted, the batch summary, the board's close verdicts. Read when a PR of yours has merged or closed, when a batch ends or is paused for days, or when deciding which sessions to close.
---

# Wrap-up

Free what you hold, delete only what loses nothing, list the rest for the person, and leave the next batch one page.

## After a PR merges or closes

The session that owns the PR does it at once; if that session has been closed, its commander does.

1. Stop your processes by pid and release your locks, keeping what others still use.
2. Take stock from the machine and GitHub, not memory: worktrees, branches, locks, processes, registrations, plans,
   temporary data.
3. Delete a worktree and its local branch **only when all hold**: GitHub has the PR merged, the branch head is its
   final commit, the tree is clean, no session works there. Keep evidence in the batch folder first. Only steps this
   safe run without the person.
4. List everything else with its evidence for the person.
5. `admiral done --who "<name>"`.

## When a batch ends

- The commander writes the one page the next batch reads: what merged, what was left and why, decisions in force,
  pitfalls, where baselines are kept. A single task adds a few lines to its brief.
- A line per executor (agent, model, effort, kind of task, rounds of rework, findings that held, where it stuck) shows
  over batches which work suits which.
- Count what each check (tests, review, acceptance, CI, a PR reviewer) caught that would have blocked the goal, with an
  example. Propose trimming one that caught nothing for three batches unless it guards something rare and costly
  (security, permissions, data loss, money), and trace what CI or a reviewer caught to the local check that missed it.
- With the person's agreement, open issues from the deferred list for what is risky or hurts real use; the rest gets a
  line in the summary.
- Check each note on where work stuck against its evidence; propose what holds for any task as a rule or a tool.
- Work paused for days gets a few lines atop its brief instead (what merged, where branches and worktrees stand, what is
  left) and phase `paused`; on resuming, the code and the PRs outrank older notes.

## Which sessions can be closed

Closing discards a session's context, so it is the person's act. The board (`admiral board`, the sidebar) gives each a
verdict and its reason: can close (its PR merged and it has wrapped up: no worktree, no lock), wrap up first, for the
person to confirm, or keep. A commander closes once no member runs and its plan has merged: `admiral plan close`,
then `admiral state --who "<name>" --phase done`.
