https://github.com/user-attachments/assets/45d323e5-d813-40b3-8f96-10a7cf6d5188

<p align="center">
  <b>Command a fleet of Claude Code sessions.</b><br>
  See who needs you, keep them out of each other's way, and drive every PR to merge.
</p>

<h3 align="center">The limit is no longer you. It's your tokens.</h3>

<p align="center">
  <a href="https://github.com/onemoneki-sudo/Admiral/actions/workflows/test.yml"><img src="https://github.com/onemoneki-sudo/Admiral/actions/workflows/test.yml/badge.svg" alt="tests"></a>
  <img src="https://img.shields.io/badge/license-MIT-c9a35b" alt="MIT license">
  <img src="https://img.shields.io/badge/python-3.11%2B-3fb950" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/model%20tokens-0-3fb950" alt="no model tokens">
</p>

<p align="center">⬇ Download the film in 1080p: <a href="https://github.com/onemoneki-sudo/Admiral/releases/download/film/admiral.mp4">English</a> · <a href="https://github.com/onemoneki-sudo/Admiral/releases/download/film/admiral.zh.mp4">中文</a></p>

<p align="center">🌐 Read this in: English · <a href="README.zh-CN.md">简体中文</a></p>

---

**One person is becoming a whole team.** Admiral grew out of daily work, not a design exercise: one person running
**close to fifty Claude Code sessions at once** on one product, in parallel, with commanders that split each batch of
work and direct the sessions under them. Each is a real Claude Code session you can talk to at any moment, not a
subagent hidden inside another. That is where building software is going, and at that scale six things decide whether
it works:

- **Big work in parallel.** Many large, hard tasks at the same time, each in a session of its own, grouped under
  commanders, batch by batch. This is what Admiral is for; small jobs do not need a fleet.
- **No chaos.** Past a dozen sessions you lose the thread: which one waits for your approval, which batch is stuck,
  which PR is red, which are done. Admiral answers those at a glance in every session, and its playbook keeps each
  session to its own worktree, branch and locks.
- **No drop in quality.** The playbook has every change in behaviour reviewed by a different model and tested where it matters,
  and Admiral counts progress by real delivery only: reviewed, accepted, CI, merged.
- **Decisions in one place.** Executors send the calls they cannot make to their commander. It makes the low-risk
  ones itself, the best way it sees, and writes each into the batch's decision log for you to read whenever you like;
  the ones only you can make, it gathers and brings to you together, each with options and a recommendation. You
  decide in a handful of commanders, not across fifty sessions, and the pushes you approve go out from there.
- **Records, not memory.** Every task has a brief, and every batch keeps its progress and its decisions in files. A
  session compacted, closed or replaced loses nothing: the next one picks the work up from the files
  ([more](#briefs-and-records-not-memory)).
- **Free to watch.** Admiral reads the records Claude Code already writes rather than asking sessions how they are
  doing, so it spends no model tokens and interrupts no one: watching fifty sessions costs what watching five does,
  nothing ([why](#why-it-spends-no-tokens)).

All of it shows inside Claude Code: in every session's status line, and in a sidebar one click away.

## Who it's for

- **Heavy Claude Code users.** You build with Claude Code all day and keep many sessions going at once, from half a
  dozen to fifty, on work big enough to split: an indie developer shipping a product alone, a tech lead driving a
  project through a fleet of sessions. This is who Admiral is built for: you see who waits for you and why, where every
  batch stands against real delivery, which CI is red and what you can close, from any session, for no model tokens.
- **Your team works that way too.** Each person runs Admiral for their own fleet, and the playbook gives everyone's
  sessions the same rules: one worktree per task, locks on what they share, review by a different model, one push
  straight to ready. PRs then arrive the same way, whoever's sessions made them. Each board shows one machine's
  sessions; it is not a shared team dashboard.
- **Not for you** if you run one or two sessions at a time: Claude Code on its own is enough.

## What you get

### A status line for the whole fleet

<img src="docs/media/statusline.png" alt="Admiral's lines under claude-hud's in a Claude Code session" width="100%">

Every session shows the fleet under the status line you already have (above: [claude-hud](https://github.com/jarrodwatts/claude-hud),
which Admiral runs first and leaves as it is).

- **Fleet progress**: one bar, by delivery milestone, its cells deepening from faint to full green as it fills.
- **Your PRs, as GitHub has them**: open, and merged today.
- **Sessions**: waiting for you, working, idle, and the names of those waiting.
- **CI failing** and **safe to close**, counted.
- **One line per commander**, those that need you first: its batch's progress, PRs merged, members, CI. The session
  reading it sees its own batch marked `▸`; a session that is not a commander gets a line of its own: its milestone,
  its PR, its commander.
- Too narrow a terminal drops the waiting names before anything else, so the counts stay.

### A sidebar with every detail

<img src="docs/media/sidebar.png" alt="The sidebar's waiting box, with the three ways a session waits for you" width="100%">

`/admiral` (or the button above the prompt) opens it on the right. It refreshes every ten seconds from the same
snapshot.

- **Waiting for you**, with what each one wants. A session waits for you in three ways, and Admiral catches all three:
  - **blocked**: Claude Code is asking your permission (the command is shown);
  - **reported**: the session said what it needs from you (`admiral state --phase needs_you --note "…"`);
  - **asked**: its last turn ended on a question, and you have not answered.
- **Every batch**, under its commander: progress, PRs merged, and each PR in its plan, led by the session that owns
  it (a click brings it forward), with its five-step milestone, title, failing CI and last activity. A planned PR
  nobody has started shows as such.

  <img src="docs/media/batch.png" alt="A commander's batch: its plan, each deliverable's milestone, owner and PR" width="100%">

- **Independent sessions**, the ones no commander runs.
- **Wrap-up**: which sessions can close, which must wrap up first, which are yours to decide.
- **To tidy**: sessions not registered, renamed, idle for days, open in more than one terminal, or still registered
  after their PR merged; the plan of a batch that is over, to close.

### One click to the session that needs you

<img src="docs/media/click.gif" alt="A click on a name in the sidebar brings that session's terminal tab to the front" width="100%">

With fifty-four sessions open, finding the one that waits is the hard part. Click any name in the sidebar and its
terminal tab comes to the front (macOS: Terminal and iTerm2).

### Progress you can trust

<img src="docs/media/milestones.png" alt="Five milestones: develop 25%, review 50%, accept 70%, CI 80%, merged 100%" width="100%">

Progress follows real delivery, never a guess: a session or deliverable is at **develop**, **review** (by a different
model), **accept** (yours), **CI** (its PR is open and ready, not a draft) or **merged** (as GitHub has it: nothing else
counts as a merge), each worth a set share. A batch takes the mean of its deliverables; one planned but not started
counts as zero, and a merged one keeps counting after its session closes. A session that says it is done with no PR to
show it reads **reported done**: its own progress is complete, but it is never counted as a merged PR, and whether to
close it is yours to confirm.

### PRs find their owner

<img src="docs/media/push.png" alt="A git push output, and the PR counted for the session that pushed it" width="100%">

A session's PRs are those of the branches it registered and the one its worktree has checked out. When a session moved
on without registering the new branch, Admiral still finds whose PR it is: the session whose `git push` output updated
it, else the one that clearly did the work in its worktree, else the batch of the commander that pushed it. The PR then
counts, and the board asks the owner to register it.

### Know what you can close

<img src="docs/media/close.png" alt="Can close, wrap up first, and for you to confirm, each with its reason" width="100%">

Every session gets a verdict with its reason: **can close** (its PR merged and it wrapped up), **wrap up first**
(merged, but its worktree or a lock is left), **for you to confirm** (a commander with nothing running, a session idle
for a day with no PR, a session that only reported done, with no merged PR), or keep. Closing is always yours.

### A playbook, and locks

<img src="docs/media/playbook.png" alt="Six skills, and a lock queue where a short job goes ahead of a full gate" width="100%">

Six skills Claude Code loads when they apply, so dozens of sessions stay out of each other's way:

| Skill | What it settles |
|---|---|
| principles | judge every finding by the goal; a quality floor; evidence for every claim; when to stop |
| roles | commanders plan, decide and accept; executors build; how to size a batch |
| workspace | one worktree per task; registration; what never to touch (others' branches, shared git state, processes by name) |
| resources | locks and queues for heavy tests, databases, browsers, ports and model quota |
| pipeline | from task brief to merge: affected tests, review by a different model, your acceptance, one push to ready |
| wrapup | after the merge: clean up safely, then close; a short summary when a batch ends |

`admiral lock` guards what the sessions share: one full test run at a time, a few database slots, model quota, ports.
Short jobs go first; a commander raises a long job left waiting; a session that crashed never holds a lock for good,
the next in line takes it over.

The skills are defaults that hold for any project, not a checklist: where your project's own rules differ, they win, so
the details that are yours (thresholds, tools, CI, reviewers) live in your project's rules.

## Try it in a minute

Nothing to install first; Python 3.11 or newer.

```sh
git clone https://github.com/onemoneki-sudo/Admiral.git ~/admiral
~/admiral/bin/admiral demo
```

Builds a made-up fleet of 54 sessions under 7 commanders with Admiral's real board code, prints its status line, and
keeps the fleet fresh until Ctrl-C. Leave it running, and in another terminal run the command it prints: a Claude Code
session with Admiral's status line and sidebar (`/admiral`, on a Claude Code with plugin function hooks), read from the
clone for that session only. Nothing of yours is touched or installed; [Install](#install) sets it up for your own
sessions.

## How it works

```
Claude Code's session registry ─┐
Session transcripts ────────────┤                                   ┌─ status line (every session)
Registrations and plans ────────┼─▶ admiral board --write ─▶ board ─┼─ sidebar (one click away)
GitHub (gh: PRs, checks) ───────┤      every minute                 └─ board.md (commanders read it)
Locks ──────────────────────────┘
```

One background job builds the board once a minute; every session reads the same snapshot. Each refresh asks GitHub
four times (up to about six API requests, and in a repository with more PRs than the lists hold, one more for every
50 branches they left out) while any session works; once all have been idle for 30 minutes, every 15 minutes; with no
session running, not at all. That stays under a tenth of GitHub's hourly allowance.

Transcripts are read from where the last refresh stopped, and every cache is bounded, so fifty sessions running for
days stay fast. When Claude Code's internal files stop looking as expected, the board says so in red, rather than
showing wrong numbers quietly.

## Install

Requirements: macOS for the background job and the click-to-focus (elsewhere, run `scripts/refresh.sh` every minute
from cron or a systemd timer; everything else works the same); Python 3.11 or newer; the GitHub CLI `gh`, signed in;
for the sidebar, a Claude Code with plugin function hooks (early access, developed against 2.1.299 and tested on 2.1.300).

```sh
git clone https://github.com/onemoneki-sudo/Admiral.git ~/admiral   # cloned already to try the demo: skip this
~/admiral/scripts/install.sh       # config template, background job, `admiral` on your PATH; --dry-run shows what it would do
```

Then two steps that are yours, since Admiral never edits Claude Code's settings itself:

1. **Status line**: in `~/.claude/settings.json` set the line the install script prints:
   ```json
   "statusLine": {"type": "command", "command": "'/Users/you/admiral/bin/admiral' statusline", "refreshInterval": 20}
   ```
   The status line you had before (claude-hud, say) is kept in Admiral's config and still runs first.
2. **Sidebar and playbook**:
   ```sh
   claude plugin marketplace add ~/admiral
   claude plugin install admiral@admiral
   ```
   Codex takes the same marketplace for the playbook's skills (`codex plugin marketplace add ~/admiral`, then
   `codex plugin add admiral@admiral`); the sidebar and the reminder are Claude Code's alone.

Last, set `project_dirs` and `[github] repo_dir` in `~/.config/admiral/config.toml`, and run `admiral doctor`: it checks
each piece (Python, the background job, the status line, the plugin, `gh` and the config), says what is not in
place and how to fix it, and changes nothing itself. `scripts/install.sh --uninstall` removes the background job and
the link.

**The playbook in every session.** A skill is read when a session thinks of it, and a busy one may not. So the plugin
ends every session's system prompt with a short reminder, about 1 KB, of which skill to read at which moment: before a
task, before a push, when named a commander, after a merge. Where your project's own rules already do that job, turn
it off with `[playbook] remind = false`. On a Claude Code without plugin function hooks, put the same line in your
project's `CLAUDE.md`: *Follow the Admiral playbook: read admiral:principles and admiral:workspace before starting any
task, and its other skills at the moments their descriptions name.*

**Recommended: turn off automatic memory** (`"autoMemoryEnabled": false` in `~/.claude/settings.json`; the install
script reminds you while it is on). Fifty sessions should not share notes nobody can see: with it off, what a session
knows comes from files you can read and correct, the task brief, the decision log and your rules. It applies to all
your projects, so it is your call, and the playbook works either way; see
[Briefs and records, not memory](#briefs-and-records-not-memory).

**Update**:

```sh
git -C ~/admiral pull                                                        # the board and the status line
claude plugin marketplace update admiral && claude plugin update admiral@admiral   # the sidebar and the playbook
```

The board and the status line run from the clone and pick the update up on their next run. Claude Code keeps the
plugin in its own cache, one copy per version, so the sidebar and the playbook move only with a new version: a session
started after the update loads it, while sessions already running keep the copy they loaded until they restart. What
changed is in [CHANGELOG.md](CHANGELOG.md).

## Config

`~/.config/admiral/config.toml` (or `$ADMIRAL_CONFIG`, which the install script carries into the background job).
Every key is optional.

```toml
language = "en"                        # or "zh"

[sessions]
project_dirs = ["~/code/myapp"]        # show only sessions working here; empty shows every session
commander_prefix = "Commander"         # a session named Commander-... is a commander

[github]
repo_dir = "~/code/myapp"              # where gh reads PRs and checks
summary_checks = []                    # CI jobs that only sum up the others: named only when nothing else failed

[statusline]
base = ""                              # a status line command to run first

[playbook]
remind = true                          # remind every session which playbook skill to read when; false where your rules do

[progress]                             # what each milestone is worth
develop = 25
review = 50
accept = 70
ci = 80
merged = 100
```

**Several projects on one board.** Working on more than one repository at once, list each as a project instead of
`[sessions] project_dirs` and `[github] repo_dir`. Each is read on its own (its sessions, its PRs and CI, its
caches), and the board puts them together, every batch and session saying its project:

```toml
[[projects]]
name = "Shop"
dirs = ["~/code/shop", "~/code/shop-worktrees"]
repo_dir = "~/code/shop"

[[projects]]
name = "Tools"
dirs = ["~/code/tools"]
repo_dir = "~/code/tools"
```

Locks, the commander prefix and everything else stay one for the machine. `admiral doctor` checks each project.

## Your first batch

From a new project to a running fleet, once Admiral is installed:

1. **Name a commander.** Open a session in the repository and give it a name with the commander prefix: start it with
   `claude -n Commander-Checkout`, or type `/rename Commander-Checkout` in one already open. The name is what makes
   it a commander; a session named otherwise works alone. Describe a big requirement to an ordinary session and the
   playbook has it suggest this step first.
2. **Describe the work.** Tell the commander what you want built. It writes the task brief, splits the work into PRs
   by areas that do not overlap, and proposes the batch: one session per area, plus an acceptance session when PRs
   are accepted together, each with a name, its duty, model, reasoning effort and a start command to paste.
3. **Open the sessions.** Paste each start command into a new terminal tab. Admiral never starts a session; you do,
   and after that you type nothing in them: the commander finds them, sends each its brief and has it register under
   the commander.
4. **Watch the board.** The status line and the sidebar show the batch: who works, who waits for you and why, every
   deliverable's stage, and CI. Decisions the commander can make, it makes and logs; the ones only you can make, it
   brings to you together.
5. **Accept and close.** You accept what you want to see, before its PR goes up or by using it once merged; as PRs
   merge, the board tells you which sessions you can close.

## Working with it

**Commanders and members.** A session whose name starts with the commander prefix is a commander. Another session
belongs to the commander its registration names; without one, to the commander whose message it received last.

**Registration.** A session says what it works on and where it stands; the playbook has every session do this:

```sh
admiral register --who "<session name>" --task "<task>" --branch <branch> --worktree <path> --lead "<commander>"
admiral state    --who "<session name>" --phase review        # working, waiting, needs_you, review, accepting, paused, done
admiral done     --who "<session name>"
```

**Plans.** A commander records the PRs its batch will deliver, so progress counts every one of them:

```sh
admiral plan add   --lead "<commander>" --branch <branch> --title "<deliverable>" --owner "<session>"
admiral plan close --lead "<commander>"
```

A commander closes its plan when the batch is over. If it was closed first, the batch leaves the board once every
deliverable has merged and no session of it runs, and the to-tidy list suggests `admiral plan close`; until then the
batch shows, marked commander not running. The board never closes a plan itself.

**Commands.**

```
admiral register | state | done | list          registrations
admiral plan add | rm | list | close            commanders' plans
admiral board [--now | --write] [--no-github]   the latest board as Markdown (--now builds it afresh)
admiral statusline                              the status line (reads Claude Code's JSON on stdin)
admiral lock acquire | release | status | port  shared-resource locks
admiral focus <tty>                             bring a session's tab to the front (macOS: Terminal, iTerm2)
admiral demo                                    a made-up fleet, to see Admiral without one
admiral where                                   the state directory
admiral doctor                                  whether each piece is in place, and how to fix the rest
```

## What it reads, and where data goes

- **Reads**, on your machine only: Claude Code's session registry and transcripts (`~/.claude`); `ps`, for each
  session's start time and terminal; `git`, read-only, in your repository and the registered worktrees; the lock
  owners; `~/.claude/settings.json` once, at install, to keep your status line and see whether automatic memory is on.
- **Writes**: its state directory (`~/.local/state/admiral`) and the locks you take; at install, its config, the
  background job, the `~/.local/bin/admiral` link and `.python-path` in the clone.
- **Adds**: one thing to what your sessions read, the playbook's reminder at the end of the system prompt, about 1 KB;
  `[playbook] remind = false` turns it off.
- **Sends**: only the `gh` calls to GitHub, as you, listing PRs and checks. No model is called and nothing is uploaded.

## Why it spends no tokens

A model charges tokens for the text it reads and writes. Admiral sends no text to any model, so building and showing
the board costs none:

- **There is no model in it.** Admiral is Python's standard library and the `gh` CLI: no API key, no model client, no
  `claude -p`. The background job reads files and counts; no step of it asks a model anything. It calls out only to
  `gh`, `git` and `ps`, and reaches the network only through `gh` (`admiral/github.py`).
- **It reads the record instead of asking.** To learn how a session is doing, you could send it a message: "Where are
  you?" The model would then read the whole conversation again to answer, and every word it reads and writes is
  tokens: in a long conversation one such question costs tens of thousands, and asking fifty sessions every minute
  would cost far more, and interrupt their work besides. But Claude Code already writes every message and every
  command of each session to a file under `~/.claude` as it works. Admiral reads those files and works out what each
  session did last, who waits for you and which PR each is on. Reading a file is your machine computing, with no model
  involved: it costs nothing, and the session never notices. A manager reading the work log everyone already keeps,
  rather than going from desk to desk.
- **What it shows stays on your screen.** Claude Code runs the status line command and draws its output under the
  prompt; the plugin draws the sidebar from the board file. Neither is put into any conversation, so no model reads
  them.

What does take tokens is your sessions' own work with Admiral, and it is small:

- **The playbook.** It is instructions for your sessions, so it sits in their context like any rules: the reminder of
  when to read which skill, about 1 KB, and the six skill descriptions, about 2 KB, in every session; a skill's full
  text, 2 to 5 KB, once a session opens it. `[playbook] remind = false` drops the reminder.
- **A few commands.** Registering (`admiral register`), taking a lock or a commander reading `board.md` is an ordinary
  command, and the session reads its few lines of output.
- **`/admiral`** leaves one line in the conversation, saying the sidebar opened or closed.

## Why sessions, not subagents

Subagents are good at a bounded job inside one session: search the code, review a diff, report back. A deliverable
that takes hours or days wants a session of its own:

- **Its whole task in one context, for as long as it lasts.** A subagent works for its parent and hands back a
  summary; a session keeps its own task, decisions and history, and carries them for days.
- **You can talk to it.** Every session is a terminal you can switch to, answer, redirect or stop, and Admiral tells
  you which one needs you. A subagent is reached through the session that started it.
- **One owner per PR.** Each session works in its own worktree and branch and carries its PRs from the first commit to
  the merge, so ownership, review and progress stay clear.
- **No single context to fill.** Every subagent's report lands in its parent's context, so one parent can only take in
  so many. Fifty sessions report to you through Admiral's board instead, and none of them has to hold the others.

Sessions still use subagents for small jobs inside them. Admiral is for keeping the sessions themselves in hand.

## Briefs and records, not memory

Fifty sessions cannot share one memory, and should not lean on one. The playbook keeps what the work needs in files
that you and every session can read:

- **A task brief per task**: its goal, how it will be accepted and what is out of scope. Whichever session takes the
  task, and after any restart or compaction, works from the same page.
- **A folder per batch**: its briefs, a status note per session and the decision log: what was decided, by whom and
  why. The low-risk calls a commander made for you are all there to read. When the batch ends, a short summary is the
  one thing the next batch reads.
- **Every kind of knowledge in its place**: what holds for every task in the project's rule files, one task's in its
  brief, one batch's in its folder.

Automatic memory is the opposite: you cannot see what it holds, notes from one task drift into unrelated ones, and
stale facts stay. The fleet Admiral grew out of runs with Claude Code's automatic memory turned off
(`"autoMemoryEnabled": false`) and lets the files carry everything; the playbook works either way.

## How it differs from an orchestration platform

Platforms such as Google's [Scion](https://github.com/GoogleCloudPlatform/scion) run agents for you: each in its own
container, scaling out to a cluster, coordinating among themselves. Admiral runs nothing. It sits on top of the
Claude Code sessions you already run in your terminals, where you can talk to any of them at any moment, and it adds
what one person needs to keep dozens of them in hand: who needs you, where each batch stands against real delivery,
what you can close, and a playbook that keeps them out of each other's way. No containers, no cluster, no tokens.

## Limits

- Claude Code's session registry and transcripts are internal files, not an API. Admiral says so when they stop
  looking as expected, rather than showing wrong numbers quietly; a Claude Code update can still need an Admiral one.
- The sidebar uses Claude Code's early-access plugin API, which moves between releases.
- It sees the sessions on this machine only, and Claude Code ones only.
- It shows the sessions of `project_dirs` only. One running elsewhere is never taken for one that ended, but a
  commander working outside them (in its batch folder, say) reads as not running: add that directory to
  `project_dirs`.
- Progress is milestone-based: it cannot see how far along development itself is.

Status: early, maintained on a best-effort basis.

## FAQ

**Does it cost anything?** No. Admiral is free (MIT) and calls no model, so the board spends none of your tokens
([why](#why-it-spends-no-tokens)). Its only traffic is `gh` asking GitHub for your PRs and checks, under a tenth of
GitHub's hourly allowance.

**Does my code or data leave my machine?** No. It reads Claude Code's files, `ps` and `git` locally, and sends nothing
but those `gh` calls, as you. See [What it reads](#what-it-reads-and-where-data-goes).

**Does it slow Claude Code down?** No. The status line reads a snapshot the background job already built, in about
70 ms on top of the status line you had; the job runs once a minute. No session is asked anything or interrupted.

**Does it start, stop or steer sessions?** No. It runs nothing and types into nothing: you and your commanders steer.
A click in the sidebar only brings a session's terminal tab to the front.

**Do I have to change how I work?** A little. Commanders are named with a prefix, and sessions register what they work
on; the playbook has them do that themselves. Without it Admiral still shows every session and who waits for you, and
finds a PR's owner from its push; registrations and plans are what make progress exact rather than estimated.

**Is it worth it with two or three sessions?** No: Claude Code on its own is enough. Admiral pays off from about half
a dozen sessions, on work big enough to split.

**No sidebar?** The sidebar, `/admiral` and the playbook reminder need a Claude Code with plugin function hooks, an
early-access feature: it depends on your Claude Code's version, and may depend on your account too. Update Claude Code,
open a new session and type `/admiral`: if the sidebar opens, or a "◂ Admiral board" button appears above the prompt,
you have it. `admiral doctor` checks the rest: that the plugin is installed, enabled and as new as your clone. Without
it Admiral still works: the status line and the playbook do not need it, and a line in your project's `CLAUDE.md` does
the reminder's job (see [Install](#install)).

**Linux? Windows?** Everything runs on macOS. On Linux all but click-to-focus works, and for now you schedule the
once-a-minute job yourself (cron or a systemd timer). Windows is untested.

**Can my team share one board?** Not yet. Each person runs Admiral for their own fleet, and the playbook gives everyone
the same rules; a team view is on the roadmap below.

**Why sessions and not subagents?** See [Why sessions, not subagents](#why-sessions-not-subagents).

## Where it is going

Admiral is used every day and developed in the open. These are plans, not promises; ideas and help are welcome in the
issues.

Next:
- **Registration without discipline**: sessions registered as they push a branch or create a worktree, so the board
  never depends on a session remembering to.
- **A notification when a session starts waiting for you**, optional, for when you are not looking at the status line.
- **Linux in full**: the background job set up by the install script, and click-to-focus for common terminals (tmux
  among them).
- **More than Claude Code**: sessions of other coding agents, such as Codex, on the same board.

Later:
- **A team view**: boards from several machines brought together, by choice.
- **History**: how long each batch spends at each milestone, and where work stalls.
- **A published interface**: moving off Claude Code's internal files as soon as Claude Code offers one.

## Develop

```sh
python3 -m unittest discover -s tests      # also run by GitHub Actions on every push and PR (Linux and macOS)
claude plugin validate plugin
claude --plugin-dir plugin                 # a session with the sidebar loaded from the working tree
```

How to contribute, and what to leave out of an issue: [CONTRIBUTING.md](CONTRIBUTING.md). Security reports:
[SECURITY.md](SECURITY.md).

The film and the pictures above are drawn from Admiral's real output on its demo fleet: `docs/film/build_assets.py`,
then `docs/film/render.py` (needs Playwright and ffmpeg).

To release: raise `__version__` in `admiral/__init__.py` and the version in `plugin/.claude-plugin/plugin.json` and
`plugin/.codex-plugin/plugin.json` together, move the `Unreleased` notes in `CHANGELOG.md` under the new version, and
tag the commit `v<version>`.

## Acknowledgements

Admiral's status line is made to sit under [claude-hud](https://github.com/jarrodwatts/claude-hud) by Jarrod Watts
(MIT): it runs your claude-hud first, unchanged, and adds its own lines below, with progress bars drawn in claude-hud's
style. Admiral includes none of claude-hud's code. Thank you to its author for an open source status line worth
building on.

## License

MIT
