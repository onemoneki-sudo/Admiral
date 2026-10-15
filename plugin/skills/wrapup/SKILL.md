---
name: wrapup
description: What to do after a PR merges or closes, and how to tell which AI sessions can be closed - stopping processes, releasing locks, the exact conditions for deleting a worktree and branch, and the board's close verdicts. Read when a PR of yours has merged or closed, when a batch ends, or when deciding which sessions to close.
---

# Wrap-up

Where the project's own rules differ from this playbook, the project's rules win.

## Right after the PR merges

The session that owns the PR wraps up at once; if it has already been closed, its commander does.

1. Stop your own processes and private services by pid and release your locks, without asking. Keep anything another PR of the same batch or another session still uses.
2. Delete the worktree, any separate clone and the local branch (after a squash merge, `git branch -D`) **only when all hold**: the PR is MERGED; the local branch head equals the PR's final head commit; the working tree has no tracked or untracked changes; no session uses it as its working directory. Move evidence worth keeping to the batch folder first; baselines and acceptance data later PRs need stay until the batch ends.
3. A PR closed without merging, a remote or backup branch, a condition not met, or unclear ownership: list it and wait for the person. When a deletion is blocked by permissions, hand the command to the person; never ask another session to delete it.
4. `admiral done --who "<name>"`.

## Which sessions can be closed

The board (`admiral board`, and the sidebar's wrap-up section) sorts every session; closing is always the person's act, since it discards the session's context.

| Verdict | When |
|---|---|
| can close | its PR merged, as GitHub has it, and it has wrapped up: worktree gone, no lock held |
| wrap up first | its PR merged but its worktree remains or it still holds locks: it must do the steps above |
| for the person to confirm | it reported `done` and has no PR at all (shown as reported done); its PR closed without merging; or it is unregistered, has no PR and has been idle over a day; or it is a commander with no running members and no plan (it may be planning, or deferred) |
| keep | working, waiting for the person, PR still open, or still developing |

A commander can close once no member is still running and it has wrapped up its batch: with its plan all merged, it
closes the plan (`admiral plan close`) and reports `done` (`admiral state --who "<its name>" --phase done`; a commander registers like any session). Until it reports `done`, a
commander with no running member is for the person to confirm: it may be planning, or deferred.
