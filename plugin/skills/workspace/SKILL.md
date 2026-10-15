---
name: workspace
description: Isolation rules that keep parallel AI sessions on one repository from breaking each other - one worktree per task, registration, what never to touch, which git and process commands are forbidden. Read before starting work in a repository other sessions also work in, before creating a worktree or branch, before stopping a process, and before any git command that changes shared state.
---

# Workspace

Where the project's own rules differ from this playbook, the project's rules win.

## Before starting: look, then register

- Start from the fetched default branch; check the repository root, remote, branch and working-tree state. A handover, an old plan or a "current state" is checked against the remote, PRs and issues and production before you act on it.
- Read-only checks first: `admiral list` (who works on what, which files), `admiral lock status` (who holds shared resources), `git worktree list`, ports and containers. When a registered area overlaps yours, agree the merge order with that session's commander or the person first.
- Register when work starts: `admiral register --who "<this session's name>" --task "<task>" --branch <branch> --worktree <path> --files "<main files/areas>" [--lead "<commander>"]`. `--who` is exactly the session's name in the tool (re-register after a rename): the board joins sessions to registrations by it.
- Report each new phase with `admiral state --who "<name>" --phase <phase> [--note "<one line>"]`: `working` (developing), `waiting` (the note says on whom or what), `needs_you` (the person must act or decide: the note says what; the board lists it under waiting for them), `review` (development done, independent review and its fixes), `accepting` (the person's acceptance or the full gate), `paused`, `done`.
- Whenever you need the person to act or decide (approve a command, release data, choose), report `needs_you` as well as asking in the conversation: the person may not be looking at this window.
- When the task ends (PR merged, closed or handed over): `admiral done --who "<name>"`.

## Each to its own

- One task, one worktree, one branch, one environment. Install the environment from the lock file, exactly as CI does; never link another worktree's environment (an editable install points it at the other source). Do not switch the branch of a worktree something is running from.
- Never enter, switch, delete or rewrite another session's directory or branch. The main checkout belongs to the person and long-running sessions.
- Processes: record the pid of everything you start, in your own directory, and stop only by pid. **Never kill by name** (`pkill -f`, `killall`). Remove a container only when it is certainly yours and its caller is gone.
- Never run git commands that change state other sessions share: `git gc`, `git worktree prune`, `git stash`.
- A branch that has been pushed is brought up to date with merge, never rebase, so it is never force-pushed. An unpushed local branch may be rebased.
- Push only your own branches, never the default branch; act only on your own PRs and issues. Another's PR is read-only for you except for review: no pushes, labels or reviewers, and never speak for the person there; coordination goes to the person.
- Inventories, clean-ups and suggestions cover only what the person owns. Read teammates' branches, PRs and code freely to check ownership or whether a change is already on the default branch, but never list their work as a to-do, suggest deleting it or act on it; a teammate's change in their own area is their call, reported objectively, not flagged as a dispute. When ownership is unclear, ask.
- Never edit the tool's own settings files to get past a permission; do not route around a push confirmation.
- When passing text to a shell, quote heredocs (`<<'EOF'`): unquoted, backticked paths or commands inside run on the spot. Write files by absolute path: a `cd` out of the session's starting directory (into a worktree, say) may hold for that one command only, so a relative path can land in the main checkout.

## Data

- Before exposing data to someone new (adding a member, granting a permission, importing one customer's data into an environment others use), say in one sentence who will immediately see what, and wait for the person's explicit yes.
- Real customer data, databases, credentials and personal data never go into issues, PRs, commits or unapproved external services. Tests committed to the repository use fixtures, temporary databases and synthetic data; judging real effect (evaluation, acceptance) may use real data copied locally with the person's authorisation.
- Real models, paid services and outward writes follow the authorisation the person has given; beyond it, ask first.
