# Changelog

Each version says what changed for someone using Admiral. The version lives in `admiral/__init__.py`, and
`plugin/.claude-plugin/plugin.json` carries the same one (the tests check): Claude Code keeps an installed plugin in
its cache, one copy per version, so a change to the sidebar or the playbook reaches people only when the version moves.

## Unreleased

**Playbook**
- A brief's acceptance says the cases it must hold in and those it leaves alone, so that a review does not take every
  edge case for a failure.
- The tests a change affects are found by more than one route, as deep as the change warrants: its callers, with an
  impact tool or by hand, and a search for the names and paths it touches. Files read at run time rather than imported
  are found by their paths, and a test that scans the whole tree or a registry runs on any change to what it scans.
- A background job meant to finish gets a time limit from how long it should take, since a hang sends no notice and
  keeps its lock; one making less progress than expected is looked into, not waited on. The resources skill is now
  read before starting such a job.
- Before new work, the remote is checked for the same work under way or done (open PRs, issues, recent merges, wherever
  the project keeps them), as closely as the work's size warrants: a session that has ended may have left a PR open.
  What is found goes to the person rather than being started again.
- PRs of one batch can each pass alone and fail together: before they go ready they are checked merged together on the
  latest default branch, and one that adds what every change must satisfy (a check across the repository, a registry,
  a numbered sequence) merges after the PRs it must cover, catching up with them itself; two that need each other are
  ordered or combined. One that guards against harm going on merges first, without waiting for the batch.
  Numbers a batch must not repeat are handed out with the dispatch.
- An independent session stops once it has worked out what is asked, before it writes a design, a brief or code: it
  says what it will do, roughly how big that is and how it splits into PRs, recommends doing it itself or being named a
  commander, and waits for the person to decide. A small fix asked for plainly, or work the person said to do directly,
  it does.
- How work splits into PRs: one for each result the person can accept at once, and one for each independent small fix.
  Split further only for parts that can go ahead at the same time, a risky part better reviewed alone, or a whole too
  much to review clearly, judged by how well it can be reviewed rather than by line count; not by steps or layers of
  one result.

## 0.2.7 (2026-10-16)

**Playbook**
- A session that hands a piece of work over (done, sent for review, ready to push), or is in doubt, says unasked, a
  sentence each with its evidence, whether the work still serves the goal, stays within the task's scope and holds for
  every case of its kind rather than one; a small change needs a few words. The review by a different model asks the
  same, adding to a repository's own review prompt only what it does not ask, and the report before a push carries it.

**Try it**
- `admiral demo` prints the demo's status line, and the command that opens Claude Code on the demo with Admiral's status
  line and sidebar read from the clone for that session only: the demo can be tried right after cloning, before
  anything is installed or set. "Try it in a minute" in the README now starts from the clone. Run from a copy without
  the plugin, the demo says the session needs it installed; a path with an emoji in it no longer stops the demo.

**Status line**
- On a board of several projects, the status line leaves a name's project out wherever the name then reads like no
  other on the line (a session waiting, a batch, the commander a session works under): with it, batch names were cut
  short. Names that would read alike keep their project; the board and the sidebar still give every name its project.

## 0.2.6 (2026-10-15)

**Board**
- A registration a session makes for itself records that session, and follows it: renamed, it stays registered with
  its task, branch and phase, with no hint to register again, and reports under its new name move the registration
  along; a new session taking an ended one's name no longer inherits its registration. A session registering itself
  under another name (its task's, say) is known all the same, and told so. One made by hand, or for another session
  (by a commander, under a running session's name, or by a session registered as itself already), is found by name
  as before. The commands are unchanged.
- "Running but not registered" is said only of a session at work that ought to register: not of a commander, listed
  as one by its name, nor of one just opened that has had no message yet. Executors just opened no longer make the
  board say transcripts may have moved.
- A registration whose session ended with its work over and wrapped up (every branch merged on GitHub, its worktree
  gone, no lock held) is no longer listed to tidy; it stays, so a session that comes back still reads as finished.
  Any of them missing, or a session file that did not read, it is listed as before.
- Several projects on one board: `[[projects]]`, each with its `dirs` and `repo_dir`, is read project by project (its
  sessions, PRs, CI and caches) and put together, every batch and session saying its project; a registration or plan
  belongs to where its session or commander works. With none, `[sessions] project_dirs` and `[github] repo_dir` work
  as always. `admiral doctor` checks each project.
- A name a session has now is that session's: another session that once had it no longer takes its registration,
  nor a commander that once had it the other's members.
- Not seen among the projects' sessions is no proof a session has ended. A registered session running outside
  `project_dirs` is not shown, as before, but no longer reads as ended, and a batch with anyone of it working there
  (an owner, its commander, a member) is not taken for one that is over.
- A PR list that comes back full may leave a branch's PR out: those branches are asked for by name, one more call
  for every 50, which gives each its open PR, else its newest. So an old PR past both lists is found rather than
  taken for none, a session that reported done with its draft still open stays at accept, and an open PR wins over
  a newer one of its branch closed or merged. If that call fails too, the PRs read as unknown, as when GitHub does
  not answer.

**Status line and sidebar**
- In Chinese, a commander's planned PRs are headed 交付清单, as the board names the plan everywhere else, rather than
  计划中的 PR, which read as PRs not started yet.
- A batch with no plan and no member registered reads "progress unknown: no member registered" rather than "no
  progress yet", which read as nothing done.

**Install**
- `admiral doctor` asks Admiral whether the status line reaches it, rather than reading the command: one that runs it
  through `exec`, `env`, `sh -c` or a script named in the command passes, and one that names Admiral but does not run
  it is never offered to run first, inside Admiral's own status line. A status line run that way draws nothing, so no
  setting can make Admiral run itself.
- A config of your own (`ADMIRAL_CONFIG`) goes with the background job, as the full path Admiral reads it as: the
  install script writes it into the macOS job and its note for Linux, and doctor's fixes (the install command, the
  cron line) carry it, since launchd and cron start the job without your shell's environment or directory.

## 0.2.5 (2026-10-15)

**Board**
- One conversation resumed in several terminals is one session: counted once, shown as its most pressing process
  (waiting before working before idle), and the to-tidy list names where it is open, since each process writes the
  same conversation. A commander open twice no longer shows two batches; a message from any of its processes, or
  under a name any of them remembers, still finds it.
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
- A batch whose commander was closed before its plan leaves the status line and the sidebar once every
  deliverable has merged and no session of it runs, rather than showing "commander not running"; its plan stays
  until `admiral plan close`, which the board's to-tidy list suggests. A batch with anything unmerged, or unknown,
  still shows, marked as before.

**Sidebar**
- A session or planned PR only reported done says so, and its last milestone is drawn dim: it no longer looks merged.

**Playbook**
- Only what any project can use, as defaults rather than a checklist, at about half the length. Thresholds, tools and
  one team's procedures (minutes in a lock queue, when a fix is reviewed again, the fields of a pre-ready report,
  fixes after approval) are left to each project's own rules, which win wherever they differ.
- Acceptance is the person's call, asked before pushing: before the PR, or by using the change once merged; either
  way shown at its real entry rather than described.
- A fix settles the kind its defect belongs to, never a condition for the one case that broke.
- When a batch ends, the commander writes a short summary, the one thing the next batch reads; what was deferred along
  the way is gone through once, and issues are opened only for what is risky or hurts real use.
- Once a PR is ready, push only what it needs, since every push runs CI again and voids approvals; local checks run
  under the conditions CI and production have.
- The review by a different model names an example: for code Claude wrote, Codex.
- The wrap-up skill's verdicts follow the board: a session that reported done with no merged PR is for you to confirm.

**Install**
- `admiral doctor` checks each piece Admiral needs: Python, `admiral` on the PATH, the config, `gh` and the
  repository, the background job and the board's freshness, the status line, the plugin and its version. It says
  what is not in place and how to fix it, changes nothing, and asks GitHub once at most. The install script ends by
  pointing to it.

**Docs**
- The README's to-tidy list, first batch and records follow the board and the playbook as they now are.

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
