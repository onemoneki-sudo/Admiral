"""The `admiral` command. `admiral --help` lists the commands, and each command's --help says what it does, what its
arguments mean, with an example; `admiral lock` and `admiral run` have their own (admiral/lock.sh, admiral/run.py).

`--who` is the session's name in Claude Code, exactly: the board joins sessions to registrations by it. A Codex
session is joined by its name, or, when it has none, by the registration's --worktree being its directory.
"""

import argparse
import json
import os
import shutil
import signal
import sys
import textwrap
import time

from . import __version__, board, codex, config, registry, relay, sessions
from .words import words


def wrapped(text):
    """A description as argparse would wrap it, so the examples after it can keep their own lines."""
    return textwrap.fill(text, min(shutil.get_terminal_size().columns - 2, 118))


def named(text):
    """A value naming something (a commander, a branch): given, it may not be empty or only spaces."""
    if not text.strip():
        raise argparse.ArgumentTypeError("must not be empty")
    return text


def parser(prog, description, example=""):
    return argparse.ArgumentParser(prog=prog, description=wrapped(description), epilog=example,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)


def warn_not_running(cfg, *names):
    running = registry.running_names(cfg)
    for n in names:
        if n and n not in running:
            print(f'warning: no running session is named "{n}"; --who and --lead must be session names (a Codex '
                  f'session without one is found by its directory, the --worktree registered)',
                  file=sys.stderr)


def build_parser():
    """The parser of every command but lock and run, which have their own; each says what it does in its --help."""
    ap = parser("admiral", "Command a fleet of AI coding sessions: who works on what, under which commander and at "
                "which phase, the board built from it, and the locks that share what the machine has too little of. "
                "Each command's --help says what it does and what its arguments mean.",
                "example, a session's day:\n"
                '  admiral register --who "fix-login" --task "login times out" --branch fix/login --worktree ~/wt/login\n'
                '  admiral state    --who "fix-login" --phase accepting\n'
                '  admiral run      --lock heavy --who "fix-login suite" --limit 30 -- make test\n'
                '  admiral done     --who "fix-login"')
    ap.add_argument("--version", action="version", version=f"admiral {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def command(name, summary, description="", example="", **kw):
        text = f"{summary[0].upper()}{summary[1:]}. {description}".strip()
        return sub.add_parser(name, help=summary, description=wrapped(text), epilog=example,
                              formatter_class=argparse.RawDescriptionHelpFormatter, **kw)

    who = ("the session's name in Claude Code, exactly (claude -n or /rename): the board joins sessions to "
           "registrations by it. A Codex session goes by its name, or, with none, by the registered --worktree")
    r = command("register", "say what this session works on, where, and for which commander",
                "Creates the registration, or replaces it (a phase already reported is kept). Made from inside the "
                "session it names, it is kept under that session and follows it through renames; made for another "
                "session, it is kept under the name given.",
                'example:\n  admiral register --who "Checkout-API" --task "the checkout API" --branch feat/checkout-api'
                ' \\\n    --worktree ~/wt/checkout-api --files "api/checkout" --lead "Commander-Checkout"')
    r.add_argument("--who", required=True, help=who)
    r.add_argument("--task", default="", help="what it works on, in a line")
    r.add_argument("--branch", type=named,
                   help="the branch it works on, several comma-separated: their PRs count for it (so does the branch "
                        "its worktree has checked out)")
    r.add_argument("--worktree", default="", help="the path of its worktree: what wrap-up checks is gone")
    r.add_argument("--files", default="", help="the areas it changes, shown in admiral list so others see an overlap")
    r.add_argument("--lead", type=named,
                   help="the commander it works for: the board files it under that commander for good (without "
                        "one, under the commander whose message it received last)")
    r.add_argument("--agent", choices=["claude", "codex"], default="",
                   help="codex: a Codex session, registered for it from outside Codex (as a commander does), never "
                        "as this session")
    s = command("state", "report the phase this session is in",
                "The board shows it and counts the milestone from it until a PR speaks: review, accept and check "
                "for review, accepting and checking, develop for the others; then CI once its PR is open and ready "
                "(not a draft), and merged once GitHub says so. It goes by the phase reported now, so report the "
                "one you are really in again once a wait is over.",
                "phases (the Chinese names work too):\n"
                "  working     developing, or anything else not listed\n"
                "  waiting     on someone or something else; --note says on whom or what\n"
                "  needs_you   the person must act (also whenever you ask them anything); --note says what\n"
                "  review      a review of the finished development before acceptance, where a project's rules\n"
                "              order it so\n"
                "  accepting   the person's acceptance, of the change at its real entry\n"
                "  checking    the delivery check: review by a different model beside the pre-push run, after\n"
                "              acceptance, or in its place for a change that skips it\n"
                "  paused      put aside for now; --note may say until when\n"
                "  done        finished: with no PR to show it, the board says reported done, never merged\n\n"
                'example:\n  admiral state --who "Checkout-API" --phase needs_you --note "approve the sandbox key"')
    s.add_argument("--who", required=True, help=who)
    s.add_argument("--phase", required=True, help="one of the phases below")
    s.add_argument("--note", default="", help="a line beside the phase; required for waiting and needs_you")
    d = command("done", "remove this session's registration",
                "Run it once the task is over and wrapped up. The board remembers what the session last registered, "
                "so one whose PR merged still shows as finished, with any worktree it left.",
                'example:\n  admiral done --who "Checkout-API"')
    d.add_argument("--who", required=True, help=who)
    command("list", "print every registration: session, task, branch, worktree, files, lead, phase, note, when",
            example="example:\n  admiral list")
    p = command("plan", "a commander's record of the PRs its batch will deliver",
                "The board counts the batch's progress from it, one deliverable per branch; a deliverable not "
                "started counts as zero. The options may come before or after the action.",
                "actions:\n"
                "  add   --lead COMMANDER --branch B [--title T] [--owner NAME]\n"
                "        add a deliverable, or change its title and owner when the branch is planned already\n"
                "  rm    --lead COMMANDER --branch B     drop a deliverable\n"
                "  list  [--lead COMMANDER]              print the plans (or this one) and their deliverables\n"
                "  close --lead COMMANDER                archive the plan, which then no longer shows on the board;\n"
                "        it checks neither that the members wrapped up nor that the deliverables merged: the board\n"
                "        shows both, so look there first\n\n"
                "examples:\n"
                '  admiral plan add --lead "Commander-Checkout" --branch feat/tax-rules --title "Tax rules" '
                '--owner "Tax-Rules"\n'
                '  admiral plan rm --lead "Commander-Checkout" --branch feat/tax-rules\n'
                '  admiral plan list --lead "Commander-Checkout"\n'
                '  admiral plan close --lead "Commander-Checkout"')
    p.add_argument("action", choices=["add", "rm", "list", "close"], help="what to do (below)")
    p.add_argument("--lead", type=named, help="the commander whose plan it is, its session name exactly (list: optional)")
    p.add_argument("--branch", type=named, help="the deliverable's branch, whose PR is the deliverable's (add, rm)")
    p.add_argument("--title", default="", help="what it delivers, in a few words (add)")
    p.add_argument("--owner", default="", help="the session that builds it, its name exactly (add)")
    b = command("board", "print the board: every session, by commander, with its milestone, PR and CI",
                "Without options it prints what the background job wrote, when that is under 3 minutes old, and "
                "builds it afresh otherwise.", "examples:\n  admiral board\n  admiral board --now")
    b.add_argument("--now", action="store_true", help="build it afresh, reading GitHub")
    b.add_argument("--write", action="store_true",
                   help="build it and publish it to <state dir>/board.json and board.md, which the status line, "
                        "the sidebar and sessions read (what the background job runs)")
    b.add_argument("--no-github", action="store_true", help="build it without reading PRs and CI (not with --write)")
    command("statusline", "the Claude Code status line",
            "Claude Code runs it with the session's JSON on stdin; set it as the statusLine command ([statusline] "
            "base runs first).",
            'example, in ~/.claude/settings.json:\n  "statusLine": {"type": "command", "command": "admiral statusline"}')
    command("codex-hook", "what the plugin's Codex hooks run",
            "It records the Codex session from the event on stdin, and hands it the messages admiral send left. Not "
            "for running by hand.", "example, as the plugin's Codex hooks run it:\n  admiral codex-hook < event.json")
    sd = command("send", "put a message into a Codex session",
                 "One at work takes it at its next call; any other gets it through codex queue, at its next turn. "
                 "Claude Code sessions: use Claude Code's own SendMessage.",
                 'example:\n  admiral send "Exec-Search" "decision: keep both scorers behind a flag"')
    sd.add_argument("who", metavar="NAME", help="the Codex session's name, or the name it is registered under")
    sd.add_argument("message", metavar="MESSAGE", help="the text, quoted")
    wt = command("wait", "return once a watched session reports, waits for the person, ends a turn or ends",
                 "Also when one registers under the --lead, or closes its registration. Run it in the background: "
                 "it prints what happened, or that nothing did. It hears only what changes while it runs, so read "
                 "admiral list and start it again each time.",
                 'example:\n  admiral wait --lead "Commander-Checkout" --timeout 3600 --quiet 1200')
    wt.add_argument("--who", action="append", default=[], metavar="NAME", help="a session to watch (repeatable)")
    wt.add_argument("--lead", type=named, metavar="COMMANDER",
                    help="watch every session registered under this commander, and those that register while it waits")
    wt.add_argument("--timeout", type=float, default=3600, metavar="SECONDS",
                    help="return after this long even if nothing happened (default 3600)")
    wt.add_argument("--quiet", type=float, default=0, metavar="SECONDS",
                    help="also return once this wait has heard nothing this long while a member is at work "
                         "(a long job, or one going in circles: look before letting it go on); below --timeout")
    # listed here only: main hands both to their own tools before this parser runs
    command("lock", "shared-resource locks and their waiting lines (admiral lock --help)",
            example="example:\n  admiral lock status")
    command("run", "run a command under locks, held exactly while it runs (admiral run --help)",
            example='example:\n  admiral run --lock heavy --who "Checkout-API suite" -- make test')
    f = command("focus", "bring the terminal tab of a session to the front (macOS: Terminal and iTerm2)",
                "The sidebar runs it when a name is clicked. Exit 1: no tab on that tty; 2: not a terminal device.",
                "example:\n  admiral focus ttys003")
    f.add_argument("tty", metavar="TTY", help="the tab's terminal device, as the board records it (ttys003 or /dev/ttys003)")
    command("where", "print the state directory, where registrations, plans and the board files live",
            "The locks are under it too, in locks/, unless the config's [locks] dir says otherwise.",
            'example:\n  cat "$(admiral where)/board.md"')
    command("doctor", "check that each piece Admiral needs is in place, and say how to fix the rest",
            "Exit 1 when a check failed.", "example:\n  admiral doctor")
    dm = command("demo", "a made-up fleet of 54 sessions, to see Admiral without running one",
                 "It writes the fleet under <state dir>/demo, prints its status line and the command that opens it in "
                 "Claude Code, and rebuilds it every 20 seconds until Ctrl-C.",
                 "example:\n  admiral demo --lang zh --once")
    dm.add_argument("--lang", choices=["en", "zh"], default="en", help="the language of its names and words")
    dm.add_argument("--tty", action="append", default=[], metavar="NAME=TTY",
                    help="tie a demo session to a real terminal tab, so a click focuses it (repeatable)")
    dm.add_argument("--once", action="store_true", help="build the demo board once and exit")
    return ap


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:2] == ["lock", "stats"]:  # read from the history the lock tool keeps
        from . import lockstats
        sys.exit(lockstats.main(config.load, argv[2:]))  # the config read once its arguments parse: --help needs none
    if argv[:1] == ["lock"]:  # handed to the lock tool whole, so its own options pass through untouched
        asks_help = argv[1:2] == ["help"] or any(x in ("-h", "--help") for x in argv[1:])  # as the tool tells it
        cfg = None if asks_help else config.load()  # its help is there for a config that does not read, too
        env = dict(os.environ, **({} if cfg is None else {"ADMIRAL_LOCKS_DIR": cfg.locks_dir,
                                                         "ADMIRAL_LOCK_COMMANDERS": cfg.lock_commanders}))
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lock.sh")
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # Python ignores it, and bash would inherit that: a reader
        os.execve("/bin/bash", ["bash", script, *argv[1:]], env)  # that stops early must end the tool quietly
    if argv[:1] == ["run"]:  # its own parser: everything after -- is the command's
        from . import run
        sys.exit(run.main(config.load, argv[1:]))
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.cmd == "doctor":  # before the config loads: a config that does not is one of the things it reports
        from . import doctor
        sys.exit(doctor.main())
    if a.cmd == "codex-hook":
        try:  # a hook must never stand in Codex's way: whatever goes wrong, it says nothing and lets Codex go on
            blocked = codex.hook(config.load(), json.load(sys.stdin), sessions.proc_starts)
        except Exception:
            blocked = None
        if blocked:  # messages left for the session: Codex hands the model this instead of running the call
            print(blocked, file=sys.stderr)
            sys.exit(2)
        return
    cfg = config.load()

    if a.cmd == "register":
        reg = registry.register(cfg, a.who, a.task, a.branch or "", a.worktree, a.files, a.lead or "", a.agent)
        sid, names = registry.caller(cfg)
        if reg.get("sessionId") and a.who not in names:  # itself, under another name: the board knows it anyway
            print(f"registered {a.who}, for this session ({names[0] if names else sid[:8]})")
            warn_not_running(cfg, a.lead)
        elif a.agent == "codex":
            warn_not_running(cfg, a.lead)  # the Codex session itself may well not be open yet
            print(f"registered {a.who}")
        else:
            warn_not_running(cfg, a.who, a.lead)
            print(f"registered {a.who}")
    elif a.cmd == "state":
        ok, msg = registry.set_phase(cfg, a.who, a.phase, a.note)
        if not ok:
            sys.exit(msg)
        print(f"{a.who}: {msg}")
    elif a.cmd == "done":
        print(f"removed {a.who}" if registry.done(cfg, a.who) else f"no registration for {a.who}")
    elif a.cmd == "list":
        W = words(cfg.language)
        print("| session | task | branch | worktree | files | lead | phase | note | updated |")
        print("|---|---|---|---|---|---|---|---|---|")
        for reg in registry.registrations(cfg):
            at = reg.get("phaseAt")
            age = f"{int((time.time() - at) // 60)} min ago" if at else "-"
            print("| " + " | ".join(str(v or "-") for v in [
                reg["who"], reg.get("task"), reg.get("branch"), reg.get("worktree"), reg.get("files"), reg.get("lead"),
                W["phases"].get(reg.get("phase"), reg.get("phase")), reg.get("note"), age]) + " |")
    elif a.cmd == "plan":
        if a.action == "list":
            shown = [pl for pl in registry.plans(cfg) if not a.lead or pl["lead"] == a.lead]
            if not shown:
                print("no plans" + (f" for {a.lead}" if a.lead else ""))
            for pl in shown:
                n = len(pl["items"])
                print(f"== {pl['lead']} ({n} deliverable{'' if n == 1 else 's'})")
                for it in pl["items"]:
                    print(f"  {it['branch']}  {it['title']}" + (f"  · {it['owner']}" if it.get("owner") else ""))
            return
        if not a.lead:
            ap.error("--lead is required")
        if a.action == "close":
            if not registry.plan_close(cfg, a.lead):
                sys.exit(f"no plan for {a.lead}")
            print(f"closed the plan of {a.lead}")
            return
        if not a.branch:
            ap.error("--branch is required")
        if a.action == "add":
            pl = registry.plan_add(cfg, a.lead, a.branch, a.title, a.owner)
            warn_not_running(cfg, a.lead, a.owner)
            n = len(pl["items"])
            print(f"{a.lead}: {n} deliverable{'' if n == 1 else 's'}")
        elif not registry.plan_remove(cfg, a.lead, a.branch):
            sys.exit(f"{a.branch} is not in the plan of {a.lead}")
        else:
            print(f"removed {a.branch} from the plan of {a.lead}")
    elif a.cmd == "send":
        ok, msg = relay.send(cfg, a.who, a.message, sessions.proc_starts)
        print(msg, file=sys.stdout if ok else sys.stderr)
        if not ok:
            sys.exit(1)
    elif a.cmd == "wait":
        if not a.who and not a.lead:
            sys.exit("admiral wait needs --who NAME (one or more) or --lead COMMANDER")
        found = relay.wait(cfg, a.who, a.lead or "", timeout=a.timeout, quiet=a.quiet)
        print("\n".join(found) if found else f"nothing changed in {a.timeout / 60:g} minutes")
    elif a.cmd == "statusline":
        from . import statusline
        statusline.main(cfg)
    elif a.cmd == "focus":
        from .focus import focus
        sys.exit(focus(a.tty))
    elif a.cmd == "where":
        print(cfg.state_dir)
    elif a.cmd == "demo":
        from . import demo
        ttys = dict(t.split("=", 1) for t in a.tty if "=" in t)
        demo.run(cfg, a.lang, ttys, once=a.once)
    elif a.cmd == "board":
        if a.write and a.no_github:
            sys.exit("--write with --no-github would publish a board without PRs and CI to every session")
        latest = cfg.sub("board.md")
        if not (a.write or a.now or a.no_github) and os.path.exists(latest) \
                and time.time() - os.path.getmtime(latest) < 180:  # what the background job wrote: no GitHub call
            with open(latest, encoding="utf-8") as fh:
                sys.stdout.write(fh.read())
            return
        snap = board.build(cfg, use_gh=not a.no_github)
        if a.write:
            board.write(cfg, snap)
        else:
            sys.stdout.write(board.markdown(snap, live=True))


if __name__ == "__main__":
    main()
