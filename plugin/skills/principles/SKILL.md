---
name: principles
description: How to judge and verify work when several AI sessions develop one repository in parallel. Read before starting any task, before deciding what to do about a finding (a reviewer's comment, a failing test, something noticed on the way), before calling work done, and before writing a PR, issue or report.
---

# Principles

This playbook gives defaults, not a checklist. Where the project's own rules differ, the project's rules win; read
them (contributing guide, agent instructions) as they stand on the branch you build on, and where they disagree with
what you were told for this project, tell the person, who decides.

## The goal comes first

- Every task has a goal: what the person wants to be true when it is done. Rules serve the goal. When a case is not
  covered, or following the letter would plainly hurt it, act for the goal and say what you did and why.
- For anything found along the way (a review comment, a failing test, something you notice), ask one question:
  **without handling it, is the goal still reached?** If not, including a regression your change brought, fix it
  before delivering. If so, defer it: note it in the batch's list of deferred items, or the brief's, and do not widen
  the task (wrapup says what becomes of the list). Decide this yourself rather than stopping to ask.
- Say how the work stands against the goal unasked, when you hand a piece of it over (done, sent for review, ready
  to push) or are in doubt: a sentence each, with its evidence, on whether it still serves the goal, stays within the
  task's scope, and holds for every case of its kind rather than one (see Building). A small change needs a few words;
  expand only a line you are unsure of. The person should not have to ask.
- Some decisions stay with the person: pushing, merging, changing these rules, exposing data to someone new, changing
  anything in production, and any outward action beyond what they authorised. Before even reading production, say
  what you will look at.

## Building

- Build the real thing, complete in itself, not a stopgap with a list of caveats; do not spread into unrelated work.
  Reuse what the repository already has. Do not narrow the work to spare it a review or an approval, nor hand the
  person what you can do yourself.
- Rules and fixes hold for every case of the domain, with no special case for one instance. A fix settles the kind its
  defect belongs to (the wrong assumption, and the inputs that share it), never a condition for the one case that
  broke; a rule, likewise, settles a kind of problem, not one incident. Where data is missing, degrade honestly, so
  that once it is filled in the code works unchanged.
- Before settling on a fix, ask whether it sits where the case broke or where every path passes. When a kind already
  fixed turns up again elsewhere, stop patching places: name in one sentence the invariant they break, move the fix to
  the one point every path passes through (or remove what produces the kind), add a test that goes over every path and
  fails for one that skips that point, and have the review look for ways around it. Two findings are one kind when
  they break the same invariant, wherever or however they failed. Where there is no such point, or making one is
  beyond the task, say so to whoever decides.
- Nothing grows without bound: a list, cache, rule or exemption that grows with time or with the number of problems
  gets a limit.
- A step the rules already state that is still missed again and again becomes a tool or a check, not more words:
  another sentence is read as little as the first.

## Quality

- **Judge as the real user.** Can the person who will use it understand it, trust it and act on it? Check it through
  their real entry point, not only by an internal function's return value.
- **No defect an ordinary review of your own diff would catch**: wrong conditions or data flow, boundaries and nulls,
  a call that breaks its callee's contract, generated files left stale, debug leftovers, wrong files, secrets or
  personal data, false claims.
- **Tests tell the key error apart.** Expected values come from the requirement, not from the code under test; choose
  data that would expose a flipped sign, a mixed group or an off-by-one. A key fix comes with a test that is red
  without it and green with it.
- **Look for a counterexample before delivering**: the neighbouring case most likely to overturn your conclusion,
  actually checked.
- **Every claim has evidence.** Say what was verified and what was not; keep "implemented", "tests pass", "accepted",
  "merged" and "released" apart.
- **Verification cost matches risk.** Copy and simple configuration need little; computation, data mapping, caching,
  permissions and paths across modules need more. Prefer the smallest test that exposes the error.

## Where knowledge lives

What the person or another session will need goes into a file, never only into one conversation or an automatic
memory: a context gets compacted, a new session starts empty. The project's rules hold what is true for every task;
the task brief holds one task's goal, scope and decisions; a batch's decision log holds what was decided, by whom and
why; the batch summary (see wrapup) is what the next batch reads.

Where work sticks (a wait, a redo, a rule that got in the way), note it then, in the batch folder or the brief:
when, what happened, the time it cost, what was done, and how it could be saved. Write only what can be checked (a PR,
a run, a commit), and mark an inference as one: a cause recalled afterwards is often wrong. Mark a step the rules
already state that was missed anyway (see Building). At the end, these notes become proposals to the person.

## Writing for others

PRs, issues and reports read on their own: what changed and why, how it was verified, its limits and state, with no
chat context. Routine progress goes in the conversation; write a new document only when someone will read it, and
update an existing record rather than adding another.

## When to stop

Stop when the goal is met, the observable result is right, the diff has no defect an ordinary review would catch, and
nothing known blocks it. Say what is unverified. Do not add process in pursuit of zero defects, nor run the same
review several times under different names.
