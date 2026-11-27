---
name: workspace
description: Isolation that keeps parallel AI sessions on one repository from breaking each other - one worktree per task, registration, what never to touch. Read before working in a repository other sessions also work in, before creating a worktree or branch, before stopping a process, and before any git command that changes shared state.
---

# Workspace

Each session works in its own place, says where it is, and touches nothing it does not own.

## Before starting

- Start from the fetched default branch and check any handover or plan against the remote, the open PRs and recent
  merges; the same work under way, or an overlap, goes to the person instead of being done again.
- Look at `admiral list`, `admiral lock status` and `git worktree list`, and agree the order with anyone registered on
  your area.
- Register at the start: `admiral register --who "<session name>" --task "<task>" --branch <branch> --worktree <path>
  --files "<areas>" [--lead "<commander>"]`, `--who` exactly the session's name; where Codex's sandbox blocks it, ask
  the person to approve the command.
- Report each phase with `admiral state --who "<name>" --phase <phase> [--note "<line>"]`: `working`, `waiting` (on
  what), `needs_you` (for what; also whenever you ask the person anything), `review` (the delivery check without
  acceptance), `accepting` (acceptance and the delivery check after it), `paused`, `done`. Only forward, or the board's
  progress goes back. End with `admiral done --who "<name>"`.

## Each to its own

- One task: one worktree, one branch and its own environment, installed as CI installs it; never link another
  worktree's, which would run its source.
- Never enter, switch, delete or rewrite another session's directory or branch; the main checkout is the person's.
- Stop only what you started, processes by pid, **never by name** (`pkill -f`, `killall`), which hits other sessions'.
- Never run git commands that change what all worktrees share (`git gc`, `git worktree prune`, `git stash`).
- Write by absolute path, since a `cd` may not last, and hand a shell literal text (a file or `<<'EOF'`), since an
  unquoted heredoc runs its backticks.
- A branch that is pushed or built on is merged into, never rebased or force-pushed.
- Push only your own branches, never the default branch, and act only on your own PRs and issues; others' you only
  review.
- Before retrying a write that is not safe to repeat (a comment, a PR, a release, a message), check whether the last
  one went through.
- Never edit the tool's settings past a permission, route around a confirmation or a check, or ask another session to
  do what was refused: hand it to the person.

## Data

- Before exposing data to anyone new, say who will see what, and wait for the person's yes.
- Real customer data, credentials and personal data stay out of commits, PRs, issues and unapproved services; tests use
  synthetic data.
- Paid services, real model calls and outward writes stay within what the person authorised.
