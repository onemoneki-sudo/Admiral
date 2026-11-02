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
- Once the split is settled, record each deliverable (branch, title, owner) with `admiral plan add --lead "<commander
  name>"`, keep it in step with `admiral plan rm`, and `admiral plan close` when the batch is over. The board counts
  the batch's progress from this plan.
- Numbers the batch's work must not repeat (a migration's, a version's) are handed out with the dispatch.
- Learn progress from the board (`admiral board`), not by asking each session.
- An executor may be a Codex session, alone or beside Claude Code ones in one batch. Register it yourself before it
  starts, its worktree included (`admiral register --who <name> --agent codex --worktree <path> --lead "<commander
  name>"`; without `--agent codex` a session that is not named as a commander registers itself): the board knows a
  Codex session without a name by its directory. Give the person the command that opens it there with its brief
  (`codex -C <worktree> "Read <brief> and start"`); send it decisions with `admiral send <name> "<message>"`, as
  Claude Code's own messages reach only Claude Code sessions. One at work reads the message at its next call, which
  the plugin's hook stops to hand it over, or before its turn ends; one between turns, when its next turn starts. Its
  brief says that its commander's messages may come that way and override the brief where they differ: told nothing
  of it, Codex stops at such a message rather than act on it. Its board row shows when it waits for the person's
  approval once the person has trusted the plugin's hooks in Codex.
- A Codex window starts no turn by itself once one ends: it suits work the person watches or approves as it goes. For
  long work, run the executor in the background a segment at a time instead, `codex exec` and then `codex exec resume
  <session> "<next step>" -o <result file> </dev/null` under a time limit, a new session for each task; you hear
  when each segment's command exits. A segment runs to where a Claude Code executor would stop too: a design
  checkpoint, a decision to make, work done and waiting to be pushed, a review round's result. A longer session costs
  more with either agent, but cutting the work finer only has the commander resume it more often, and `admiral send`
  corrects it on the way. Nobody can approve a call there, so what it needs is allowed beforehand. Codex's sandbox
  does not let it write the main repository's `.git`, where a linked worktree's commits go, so either the commander
  commits its work or, with the person's agreement, it runs with full access, guarded by the project's PreToolUse
  hooks, which must block a call outright, as nobody is there to answer one that asks. Hooks run there as in a window,
  once trusted; a background run cannot ask, so after an Admiral update trust them in a window first.
- Claude Code's auto mode refuses a full-access `codex exec` written out by hand. Start it through one launcher script
  that fixes everything but the task: it takes only a worktree under the project's worktree folder and a time limit
  within bounds, and itself sets the access, the time limit and the empty input; the person allows that one script.
  Type the rule in `/permissions` without quotes around it: it is saved as typed, and quoted it never matches.
- Its brief names the few reasons it must stop: a hook or a rule refused what it was doing, or going on would leave
  the brief's scope; a message handed over at a call is no refusal. Anything else that fails on the way (a query, a
  tool it may not use) it judges within the rules and says how in its report: told to stop at any failure, a Codex
  executor stops at the first one, however minor.
- Stuck is reported, not a reason to stop: when three different attempts at one problem have brought it no closer to
  passing, the executor reports `stuck: <what it tried>; next: <what it will try>` as the note of its `admiral state`
  and may go on, keeping that note until it is past the problem or its commander answers. The commander, woken by the
  report or finding it on its next look, decides whether it goes on, gets a correction or is stopped.
- A segment stopped by its pid leaves what it started running (a server, a test run) and its locks held. The next
  segment's first step is to find its own locks and processes and clean them up before going on.
- Executors report with `admiral state`. Rather than check on them, leave `admiral wait --lead "<commander name>"`
  running in the background: it returns when a member reports, starts waiting for the person, ends a turn or ends, and
  you hear of it then. With nothing to report it returns at its time limit (`--timeout`, an hour by default); start it
  again each time, so you wake to move the batch along even through a night when nobody reports. Each time it
  returns, read every member's state (`admiral list`), not only the lines it printed: it hears what changes while it
  runs, so a report made before you started it again wakes nothing.

## Sizing a batch

When asked how many sessions are needed, propose the batch before dispatching: one session per area of change that
does not overlap another, plus an acceptance executor when it pays. For each, give a name by role, its duty, the
agent (Claude Code or Codex), the model and effort you suggest (harder or riskier work getting the stronger setting)
and a command to start it, for the person to paste. Once they are open, the commander finds them and sends each
its brief; the person types nothing in them. Only the person sets a session's model and effort.
