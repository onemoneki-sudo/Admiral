---
name: roles
description: Roles when one person runs several AI sessions on one repository - independent session, commander, executor - and how a commander plans, dispatches and tracks work. Read when the person names this session a commander, when given work large enough to split across sessions, when dispatching work to other sessions, when asked how many sessions a batch needs, or when receiving work from a commander.
---

# Roles

Where the project's own rules differ from this playbook, the project's rules win.

## Who does what

- **Independent session**: carries its own task from start to finish and asks the person directly when a decision is
  theirs. Before it starts, it says what it will do and waits for the person (see pipeline); when its work spans
  several areas that could go ahead in parallel, each worth its own PR, it proposes there that the person name it a
  commander, and small or tightly coupled work it does itself.
- **Commander** (only when the person names it so: its name starts with the commander prefix, `Commander-` unless
  configured otherwise, set with `claude -n` or `/rename`): splits the work, writes the briefs, dispatches by
  cross-session message, makes the decisions within the person's authorisation and logs each, brings the ones only the
  person can make together, each with options and a recommendation, and writes the batch summary at the end (see
  wrapup). By default it writes no product code, so its context stays free for decisions; in a batch it is the one
  that pushes (see pipeline).
- A new, unrelated batch gets a new commander session: one that led the last batch takes that batch's state and rules
  for the present. Given unrelated work, a commander suggests a new one with a command to start it; work continued
  stays with it.
- **Executor**: works from its brief; sends what it cannot decide to its commander with options and a recommendation;
  keeps a status note in the batch folder, its current state at the top, rewritten when it changes; commits locally,
  then opens and tends its own PR once it is pushed.
- A commander may give one executor the acceptance environment, when several PRs are accepted together.

## Dispatching

- Every dispatch tells the executor to register with `--lead "<commander name>"`, so the board files it under this
  commander for good; without it the board guesses from the last commander message the session received.
- Once the split is settled, record each deliverable (branch, title, owner) with
  `admiral plan add --lead "<commander name>"`, keep it in step with `admiral plan rm`, and `admiral plan close` when
  the batch is over. The board counts the batch's progress from this plan.
- Numbers the batch's work must not repeat (a migration's, a version's) are handed out with the dispatch.
- Learn progress from the board (`admiral board`), not by asking each session.
- An executor may be a Codex session, alone or beside Claude Code ones in one batch. Register it yourself before it
  starts, its worktree included (`admiral register --who <name> --worktree <path> --lead "<commander name>"`): the
  board knows a Codex session without a name by its directory. Give the person the command that opens it there with
  its brief (`codex -C <worktree> "Read <brief> and start"`); send it decisions with `admiral send <name>
  "<message>"`, as Claude Code's own messages reach only Claude Code sessions. Its board row shows when it waits for
  the person's approval once the person has trusted the plugin's hooks in Codex.
- A Codex window takes a message only when its turn ends, one at a time, starts no turn by itself once one ends, and
  after Esc leaves its queue unread: it suits work the person watches or approves as it goes. For long work, run the
  executor in the background a segment at a time instead, `codex exec` and then `codex exec resume <session> "<next
  step>" -o <result file> </dev/null` under a time limit, a new session for each task and small segments, since
  resuming sends the whole session again; you hear when each segment's command exits. Nobody can approve a call
  there, so what it needs is allowed beforehand. Codex's sandbox does not let it write the main repository's `.git`,
  where a linked worktree's commits go, so either the commander commits its work or, with the person's agreement, it
  runs with full access, guarded by the project's PreToolUse hooks. Hooks run there as in a window, once trusted; a
  background run cannot ask, so after an Admiral update trust them in a window first.
- Executors report with `admiral state`. Rather than check on them, leave `admiral wait --lead "<commander name>"`
  running in the background: it returns when a member reports, starts waiting for the person, ends a turn or ends,
  and you hear of it then. With nothing to report it returns at its time limit (`--timeout`, an hour by default);
  start it again each time, so you wake to move the batch along even through a night when nobody reports.

## Sizing a batch

When asked how many sessions are needed, propose the batch before dispatching: one session per area of change that
does not overlap another, plus an acceptance executor when it pays. For each, give a name by role, its duty, the
agent (Claude Code or Codex), the model and effort you suggest (harder or riskier work getting the stronger setting)
and a command to start it, for the person to paste. Once they are open, the commander finds them and sends each
its brief; the person types nothing in them. Only the person sets a session's model and effort.
