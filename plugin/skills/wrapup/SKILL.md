---
name: wrapup
description: What to do after a PR merges or closes and when a batch ends, and how to tell which AI sessions can be closed - stopping processes, releasing locks, when a worktree and branch may be deleted, the batch summary, and the board's close verdicts. Read when a PR of yours has merged or closed, when a batch ends or is paused for days, or when deciding which sessions to close.
---

# Wrap-up

Where the project's own rules differ from this playbook, the project's rules win.

## Right after the PR merges

The session that owns the PR wraps up at once; if it has already been closed, its commander does.

1. Stop your own processes by pid and release your locks; keep anything another session still uses.
2. Delete the worktree and the local branch **only when all hold**: GitHub has the PR merged; the local branch head is
   the PR's final commit; the working tree has no changes; no session works in it. Move evidence worth keeping to the
   batch folder first.
3. Anything else (a PR closed unmerged, a condition not met, unclear ownership): list it and leave it to the person.
4. `admiral done --who "<name>"`.

## When a batch ends

- The commander writes a short summary into the batch folder, the one thing the next batch reads: what merged, what
  was left and why, the decisions still in force, the pitfalls, and where any baseline the next batch needs is kept.
  A single task adds the same in a few lines at the end of its brief.
- Work paused for days gets no summary: a few lines at the top of its brief say what merged, where unpushed branches
  and worktrees stand, and what is left, and it reports `paused`. On resuming, those lines, the code and the PRs are
  what count; older notes are background.
- The deferred list is gone through once: with the person's agreement, issues are opened for what is risky (security,
  permissions, data lost or leaked, wrong numbers) or hurts real use; the rest gets a line in the summary.
- The notes on where work stuck are gone through once: each cause checked against its evidence, what would hold for
  any task is proposed to the person as a change to the rules, and a step that was written down yet missed again as a
  tool or a check. The rest stays with the batch.
- The process notes are kept but not read by default; where they disagree with the code or the PRs, those are right.

## Which sessions can be closed

The board (`admiral board`, and the sidebar's wrap-up section) sorts every session; closing is always the person's
act, since it discards the session's context.

| Verdict | When |
|---|---|
| can close | its PR merged, as GitHub has it, and it has wrapped up: worktree gone, no lock held |
| wrap up first | its PR merged but its worktree remains or it still holds locks |
| for the person to confirm | it reported `done` with no PR at all (shown as reported done); its PR closed unmerged; it is unregistered, with no PR, idle over a day; or it is a commander with no running members and no plan |
| keep | working, waiting for the person, PR still open, or still developing |

A commander can close once no member is still running and its batch is wrapped up: with its plan all merged, it runs
`admiral plan close` and reports `done` (`admiral state --who "<its name>" --phase done`). If it was closed first, the
batch leaves the board once every deliverable has merged and nobody of it runs; its plan stays, listed to tidy, until
someone runs `admiral plan close`.
