---
name: roles
description: Independent session, commander and executor when one person runs several AI sessions on one repository, and how a commander plans, dispatches and tracks work. Read when the person names this session a commander, when given work large enough to split across sessions, when dispatching or receiving work, and when asked how many sessions a batch needs.
---

# Roles

An independent session carries its task alone; a commander, only when the person names one, splits, decides and
tracks; executors build.

## Who does what

- **Independent session**: carries its task end to end, asks the person directly, and suggests being named a commander
  when the work spans parallel areas each worth a PR (pipeline).
- **Commander**: only when the person names it so, with the commander prefix (`Commander-` by default, set with
  `claude -n` or `/rename`). It splits the work, writes the briefs, dispatches, decides within the person's
  authorisation and logs why, brings the person's decisions together with options and a recommendation, pushes for the
  batch and writes its summary (wrapup); it writes no product code, keeping its context for decisions.
- An unrelated batch gets a new commander, so the last batch's state and rules do not carry into it.
- **Executor**: works from its brief, sends what it cannot decide to its commander with options and a recommendation,
  keeps a status note in the batch folder (current state on top), commits locally, and tends its PR once pushed.
- An acceptance executor may hold the environment when several PRs are accepted together.

## Dispatching

- Tell each executor to register with `--lead "<commander>"`, so the board files it under you for good.
- Record each deliverable with `admiral plan add --lead "<commander>" --branch <branch> --title "<title>" --owner
  <session>` and drop one with `admiral plan rm --lead "<commander>" --branch <branch>`: the board counts the batch's
  progress from the plan, and closing it is in wrapup.
- Hand out the numbers that must not repeat (a migration's, a version's) and which branch builds on which.
- Follow progress on `admiral board`, with `admiral wait --lead "<commander>"` in the background: it returns when a
  member reports, waits for the person, ends a turn or ends, or at `--timeout` (3600 seconds by default). Each time,
  read `admiral list` and start it again, as it hears only what changes while it runs.
- While executors work unwatched, add `--quiet <seconds>`, below `--timeout`: it also returns once this wait has
  heard nothing that long while a member is at work. It measures the wait, not any one member's silence, and silence
  can be a long job or one going in circles, so read the member's board row and log before you let it go on, correct
  it with `admiral send` or stop it by its pid.
- An executor that three different attempts have brought no closer on one problem reports `stuck: <what it tried>;
  next: <what it will try>` as its state note, keeps it until it is past the problem or answered, and may go on; its
  commander decides whether it continues, is corrected or is stopped.

## Codex executors

- Register it yourself (`admiral register --who <name> --agent codex --worktree <path> --lead "<commander>"`), give
  the person its start command (`codex -C <worktree> "Read <brief> and start"`), and send it decisions with `admiral
  send`, which its brief says override the brief, or it stops at them.
- Its brief names the only reasons to stop, a refusal by a hook or rule (a message handed over at a call is none) and
  leaving the brief's scope, or it stops at the first trivial failure.
- For long work run it in the background a segment at a time (`codex exec`, then `codex exec resume <session> "<next
  step>" -o <file> </dev/null` under a time limit, a new session per task), each ending where a Claude Code executor
  would stop.
- Nobody answers its prompts there, so allow what it needs beforehand. Its sandbox cannot write the main repository's
  `.git`: the commander commits for it, or, with the person's agreement, it runs with full access behind hooks that
  block outright. Trust the plugin's hooks in a window after each update.
- Claude Code's auto mode refuses a full-access `codex exec` written by hand: start it through one launcher script
  that sets the access, the time limit and the empty input itself, takes a time limit only within bounds, and refuses
  any path that does not resolve to the worktree registered for this task (`admiral list`), so the allowed script
  cannot hand full access to the main checkout or another session's worktree.
  The person allows that script in `/permissions`, unquoted, or the rule never matches.
- After a segment stopped by pid, the next first cleans up the servers, runs and locks it left.

## Sizing a batch

Propose the batch before dispatching: one session per area that overlaps no other, plus an acceptance executor when it
pays, each with a role name, duty, agent, suggested model and effort (stronger for harder or riskier work) and a start
command to paste; the commander then sends each its brief. Only the person sets a session's model and effort.
