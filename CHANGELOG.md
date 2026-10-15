# Changelog

Each version says what changed for someone using Admiral. The version lives in `admiral/__init__.py`, and
`plugin/.claude-plugin/plugin.json` carries the same one (the tests check): a plugin installed from the clone's
folder is read from it, but one installed from a repository is updated by Claude Code only when its version moves.

## Unreleased

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
