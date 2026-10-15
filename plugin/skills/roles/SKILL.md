---
name: roles
description: Roles when one person runs several AI sessions on one repository - independent session, commander, executor - and how a commander plans, dispatches and tracks work. Read when the person names this session a commander, when given work large enough to split across sessions, when dispatching work to other sessions, when asked how many sessions a batch needs, or when receiving work from a commander.
---

# Roles

Where the project's own rules differ from this playbook, the project's rules win.

## Who does what

- **Independent session**: carries its own task from start to finish and asks the person directly when a decision is
  theirs. When its work spans several areas that could go ahead in parallel, each worth its own PR, it says so first
  and proposes that the person name it a commander; small or tightly coupled work it simply does.
- **Commander** (only when the person names it so: its name starts with the commander prefix, `Commander-` unless
  configured otherwise, set with `claude -n` or `/rename`): splits the work, writes the briefs, dispatches by
  cross-session message, makes the decisions within the person's authorisation and logs each, brings the ones only the
  person can make together, each with options and a recommendation, and writes the batch summary at the end (see
  wrapup). By default it writes no product code, so its context stays free for decisions; in a batch it is the one
  that pushes (see pipeline).
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
- Learn progress from the board (`admiral board`), not by asking each session.

## Sizing a batch

When asked how many sessions are needed, propose the batch before dispatching: one session per area of change that
does not overlap another, plus an acceptance executor when it pays. For each, give a name by role, its duty, the model
and effort you suggest (harder or riskier work getting the stronger setting) and a command to start it, for the person
to paste. Once they are open, the commander finds them and sends each its brief; the person types nothing in them.
Only the person sets a session's model and effort.
