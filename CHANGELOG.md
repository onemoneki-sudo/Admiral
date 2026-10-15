# Changelog

Each version says what changed for someone using Admiral. The version lives in `admiral/__init__.py`, and
`plugin/.claude-plugin/plugin.json` carries the same one (the tests check): Claude Code keeps an installed plugin in
its cache, one copy per version, so a change to the sidebar or the playbook reaches people only when the version moves.

## Unreleased

**Board**
- Merged means merged on GitHub. A session's own `done` no longer counts as a merge: with its PR still open it stays
  in CI; with its PR closed unmerged it is not finished, and closing it is yours to confirm; with no PR at all it reads
  *reported done*, its own progress complete, and closing it is yours to confirm too. PR counts, the plan's "merged
  n/m" and "plan all merged" count only PRs GitHub merged.
- A draft PR no longer moves its session to CI: the session stays at the phase it reported until the PR is ready.
- While GitHub does not answer, a session's `done` is not taken for a task with no PR: a session with any branch,
  registered or taken from its push, stays at accept and is kept until GitHub says what became of its PR.
- A commander whose own PR is still open is kept, like any session.
- A planned PR whose owner reported done and then deregistered keeps its place rather than going back to not started;
  the owner's last registration speaks only for the branches it named, under its old name or its session's new one.
- A session that finished and deregistered reads as finished in `admiral board` and its own status line, not as
  unregistered.
- "Merged today" is the day where you are: GitHub read the bare date as a UTC day, so east of UTC it missed the
  morning's merges, and west of UTC it counted the evening before.
- A deliverable merged days ago keeps counting after it falls out of the 300 most recent PRs: the board remembers
  merged PRs of branches still in use.
- Past the newest 100 open PRs, a draft is still a draft, and the board says their CI is not shown, rather than
  showing none.
- The background job and a session building the board at once no longer trip over one temporary file, which could
  fail a refresh or leave a cache broken.

**Sidebar**
- A session or planned PR only reported done says so, and its last milestone is drawn dim: it no longer looks merged.

**Playbook**
- The wrap-up skill's verdicts follow the board: a session that reported done with no merged PR is for you to confirm.

## 0.2.4 (2026-10-15)

**Sidebar**
- A commander's planned PRs are led by the session that owns each, like every other row, and a click on it brings
  that session forward; the PR's title and number sit under it. The list is headed "planned PRs".
- A long title no longer pushes a row's milestone onto a second line.
- The sidebar and the playbook reminder have tests that run against Claude Code itself (`claude plugin test plugin`).

**Docs**
- The README opens with six things rather than four: records rather than memory, and a fleet that costs nothing to
  watch; each session is a real one, not a subagent.

## 0.2.3 (2026-10-15)

**Playbook**
- Every session reads it: the plugin ends each session's system prompt with a short reminder of which skill to read at
  which moment, about 1 KB; `[playbook] remind = false` turns it off where a project's own rules do that job.
- In a batch, the commander pushes: executors commit locally and hand it the push, so the person's go-ahead and any
  push confirmations happen in one session rather than across the fleet.

**Install**
- While Claude Code's automatic memory is on, the install script recommends turning it off, and says why; it never
  changes the setting itself.

**Docs**
- The README explains the reminder and the memory recommendation, with a `CLAUDE.md` line for a Claude Code without
  plugin function hooks.

## 0.2.2 (2026-10-15)

**Playbook**
- A session given work that spans several areas proposes splitting it and being named a commander, rather than doing
  it all alone; a commander given a requirement proposes the batch without being asked.

**Docs**
- The README plays the film, and walks through your first batch, from a new project to a running fleet.
- The README says why the board spends no model tokens, and what in your sessions does.

## 0.2.1 (2026-10-15)

**Playbook**
- Commanders gather the decisions only the person can make and bring them together, each with options and a
  recommendation; the low-risk ones they make go into the batch's decision log.
- Where knowledge lives: rules, product principles, the task brief, the decision log and environment notes, each in
  its file, not in one conversation or an automatic memory.

**Docs**
- The README says why decisions go through commanders and why the work runs on briefs and records rather than memory.
- The film shows decisions gathered at the commander; the README's film links follow the latest release.

## 0.2.0 (2026-10-15)

The first versioned release.

**Board**
- One background job builds the board every minute; the status line and the sidebar only read it. GitHub is asked
  four times a refresh while any session works, every 15 minutes once all have been idle for 30 minutes, and not
  at all with no session running.
- Sessions are grouped under the commander that directs them: the commander their registration names, else the
  last commander whose message they received (matched by process, so renames hold).
- Progress follows real milestones (develop, review, accept, CI, merged), each worth a configured share; a batch's
  progress is the mean, over the commander's plan when it has one, else over its running members.
- PR counts follow GitHub: the person's own open PRs and those merged today, and each batch's open and merged PRs.
- A PR whose branch nobody registered still finds its owner: the session whose `git push` output updated it, else
  the session that clearly did the work in its worktree, else the batch of the commander that pushed it. It is
  taken only while open and kept once taken; the board asks the owner to register it.
- Three ways a session waits for the person: Claude Code blocks it, it reported `needs_you` with what to do, or
  (maybe) its last turn ended asking the person something.
- Every session gets a close verdict: can close, wrap up first, for the person to confirm, or keep. Commanders are
  judged after their members; a session that finished and deregistered is still known as finished.
- Problems with the sources themselves (session files, transcripts, GitHub) are shown apart, never hidden in the
  numbers.

**Status line and sidebar**
- A status line under the one already in use (claude-hud, say): overall progress, sessions waiting, working and
  idle, CI failures, sessions that can close; one line per commander; the reading session's own milestone. A line
  too wide drops the waiting sessions' names before anything else.
- A sidebar, one click or `/admiral` away, with every session, what waiting sessions ask, the close verdicts and a
  click that brings a session's terminal tab to the front (macOS).
- English and Chinese (`language`); in Chinese a phase can be given in Chinese, such as `审查` for review.

**Commands**
- `admiral register | state | done | list`, `admiral plan add | rm | list | close`, `admiral board` (the latest
  snapshot, without a GitHub call; `--now` builds it afresh), `admiral lock`, `admiral focus`, `admiral where`,
  `admiral --version`.
- `admiral lock`: shared-resource locks with waiting lines and priorities; `[locks] commanders` names who may
  reorder a line.
- `[github] summary_checks` names CI jobs that only sum up the others; they are named only when nothing else failed.
- `admiral demo [--lang zh]`: a made-up fleet of 54 sessions under 7 commanders, built by the real board code, to see
  Admiral before running a fleet of your own.

**Docs**
- The README in English and Chinese, a short film in each (attached to the release), CONTRIBUTING and SECURITY.

**Playbook**
- Six skills for sessions working in parallel: principles, roles, workspace, resources, pipeline, wrapup.

**Install**
- `scripts/install.sh` writes a config template, installs the background job (macOS) and links `admiral` into
  `~/.local/bin`; it never edits Claude Code's settings. `--dry-run` shows what it would do; `--uninstall` undoes it.
- Everything Admiral runs uses the Python the install script checked, recorded by full path (`ADMIRAL_PYTHON`
  overrides it), falling back to `python3` if it is removed. An older Python is named plainly, in the status line
  too. The status line says why the board is missing or old: the background job's last error (a job that cannot
  even start reports it in the default state directory), or how to start the job.
