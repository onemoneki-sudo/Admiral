---
name: roles
description: Roles when one person runs several AI sessions on one repository - independent session, commander, executor, acceptance executor - and how a commander plans, dispatches and tracks work. Read when the person names this session a commander, when given work large enough to split across sessions, when dispatching work to other sessions, when asked how many sessions a batch needs, or when receiving work from a commander.
---

# Roles

Where the project's own rules differ from this playbook, the project's rules win.

## Who does what

- **Independent session**: carries its own task from start to finish, takes its own locks, makes its own calls, and asks the person directly when a decision is theirs. When the work it is given spans several areas that could go ahead in parallel, each worth its own PR, it says so before starting: it proposes the split and that the person name it a commander, and leaves the choice to the person. Small or tightly coupled work it simply does.
- **Commander** (only when the person names it so: its name starts with the project's commander prefix, `Commander-` unless configured otherwise, given at start with `claude -n` or later with `/rename`): splits the work, writes the task briefs, dispatches and answers by cross-session messages, makes technical and product decisions within the person's authorisation and writes each into the batch's decision log, gathers the decisions only the person can make and brings them together, each with options and a recommendation, rather than one at a time, sets re-test lists, judges acceptance results, writes the pre-ready report and leads the person's acceptance. **It does not write product code** nor do execution work (merging, running tests, browser re-tests), so its context stays free for decisions. Centralised pushing is the exception, where the project has it.
- **Executor**: works from its task brief; sends decisions it cannot make to its commander (question, options, recommendation, impact) and follows the answer; writes its progress and the facts the pre-ready report needs into its status note in the batch folder (see pipeline).
- **Acceptance executor**: works from the acceptance brief its commander gives; builds and maintains the merged version and the acceptance environment, merges each PR's fixes, resolves conflicts, runs tests, re-tests in the browser by the list; writes results into its status note and messages its commander; does not write product code. Problems go back to the session that owns the PR.

## Dispatching

- Dispatch by cross-session message. Every dispatch tells the executor to register with `admiral register ... --lead "<commander name>"`, so the board files it under this commander for good. Without `--lead`, the board guesses from the last commander message the session received, which a single cross-batch message can mislead.
- Once the PR split is settled, record each deliverable (branch, title, owning session) with `admiral plan add --lead "<commander name>"`; keep it in step when the split changes (`admiral plan rm` drops one); `admiral plan close` when the batch is over. The board's batch progress counts this plan, so a merged deliverable keeps counting after its session closes.
- Learn progress from the board (`admiral board`, the snapshot the background job refreshes every minute), not by asking each session; take care of the wrap-up and loose ends it lists for your batch.

## Sizing a batch

When the person asks how many sessions are needed, or gives this commander a requirement, propose the batch before dispatching:
- One development session per non-overlapping area of change, each owning one or two related PRs. Add one acceptance executor when two or more PRs are accepted together or a standing acceptance environment is needed.
- For each session give a name by role, its duty, model, reasoning effort and a start command to paste. Once the person has opened them, the commander finds them and sends the start instructions; the person types nothing in the executors.
- Configure for quality without rework: the commander at a high effort, as the project sets it; executors judged one by one by difficulty and cost of error. Concurrency, state, data consistency, security gates and the product's core logic get the project's main model at a high effort. Downgrade only for simple, fully verifiable work (pure mechanical steps), and say why.
- Only the person sets a session's model and effort: write down how each should be set, and when it must change, tell the person which session and to what.
