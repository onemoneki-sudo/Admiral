---
name: workspace
description: Isolation rules that keep parallel AI sessions on one repository from breaking each other - one worktree per task, registration, what never to touch. Read before starting work in a repository other sessions also work in, before creating a worktree or branch, before stopping a process, and before any git command that changes shared state.
---

# Workspace

Where the project's own rules differ from this playbook, the project's rules win.

## Before starting: look, then register

- Start from the fetched default branch. Check a handover, an old plan or a "current state" against the remote and the
  open PRs before acting on it.
- Look first: `admiral list` (who works on what), `admiral lock status`, `git worktree list`. When someone's registered
  area overlaps yours, agree the order with them or the person first.
- Register when work starts: `admiral register --who "<this session's name>" --task "<task>" --branch <branch>
  --worktree <path> --files "<main files or areas>" [--lead "<commander>"]`. `--who` is exactly the session's name (register again after a rename):
  the board joins sessions to registrations by it.
- Report each new phase with `admiral state --who "<name>" --phase <phase> [--note "<one line>"]`: `working`,
  `waiting` (the note says on what), `needs_you` (the person must act or decide: the note says what), `review`,
  `accepting`, `paused`, `done`. Whenever you ask the person something, report `needs_you` too: they may not be
  looking at this window.
- When the task ends: `admiral done --who "<name>"`.

## Each to its own

- One task, one worktree, one branch. Never enter, switch, delete or rewrite another session's directory or branch;
  the main checkout belongs to the person.
- Stop only processes you started, by their pid; **never kill by name** (`pkill -f`, `killall`).
- Never run git commands that change state other sessions share, such as `git gc`, `git worktree prune` or
  `git stash`.
- A pushed branch is updated by merge, never rebase, so it is never force-pushed.
- Push only your own branches, never the default branch; act only on your own PRs and issues. Others' work is
  read-only to you, except for review.
- Never edit the tool's settings to get past a permission, nor route around a confirmation or a repository's checks.

## Data

- Before exposing data to someone new, say in one sentence who will see what, and wait for the person's yes.
- Real customer data, credentials and personal data never go into commits, PRs, issues or unapproved services; tests
  use synthetic data.
- Paid services, real model calls and outward writes stay within what the person authorised; beyond it, ask.
