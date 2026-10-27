"""The `admiral` command.

    admiral register --who NAME [--task T] [--branch B] [--worktree PATH] [--files F] [--lead COMMANDER]
    admiral state    --who NAME --phase PHASE [--note TEXT]
    admiral done     --who NAME
    admiral list
    admiral plan add   --lead COMMANDER --branch B [--title T] [--owner NAME]
    admiral plan rm    --lead COMMANDER --branch B
    admiral plan list  [--lead COMMANDER]
    admiral plan close --lead COMMANDER
    admiral board    [--now | --write] [--no-github]   the latest board; --now builds it afresh, --write publishes
    admiral statusline           the Claude Code status line (reads the session's JSON on stdin)
    admiral codex-hook           what the plugin's Codex hooks run: records the Codex session (its event on stdin)
    admiral send NAME MESSAGE    put a message into the Codex session NAME (Claude Code sessions: SendMessage)
    admiral wait [--who NAME]... [--lead COMMANDER] [--timeout SECONDS]   return when a member reports, waits for
                                 the person, ends a turn or ends; run it in the background to hear of it
    admiral lock ...             shared-resource locks (`admiral lock status`; see admiral/lock.sh)
    admiral focus TTY            bring the terminal tab on TTY to the front (macOS)
    admiral doctor               whether each piece Admiral needs is in place, and how to fix the rest
    admiral where                print the state directory (the board files live there)
    admiral demo [--lang zh] [--tty NAME=TTY] [--once]   a made-up fleet, to see Admiral without one

`--who` is the session's name in Claude Code, exactly: the board joins sessions to registrations by it. A Codex
session is joined by its name, or, when it has none, by the registration's --worktree being its directory. Phases:
working, waiting (needs --note: on whom or what), review, accepting, paused, done; the Chinese names work too.
"""

import argparse
import json
import os
import signal
import sys
import time

from . import __version__, board, codex, config, registry, relay, sessions
from .words import words


def warn_not_running(cfg, *names):
    running = registry.running_names(cfg)
    for n in names:
        if n and n not in running:
            print(f'warning: no running session is named "{n}"; --who and --lead must be session names (a Codex '
                  f'session without one is found by its directory, the --worktree registered)',
                  file=sys.stderr)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["lock"]:  # handed to the lock tool whole, so its own options pass through untouched
        cfg = config.load()
        env = dict(os.environ, ADMIRAL_LOCKS_DIR=cfg.locks_dir,
                   ADMIRAL_LOCK_COMMANDERS=cfg.lock_commanders)
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lock.sh")
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # Python ignores it, and bash would inherit that: a reader
        os.execve("/bin/bash", ["bash", script, *argv[1:]], env)  # that stops early must end the tool quietly
    ap = argparse.ArgumentParser(prog="admiral", description="Command a fleet of AI coding sessions.")
    ap.add_argument("--version", action="version", version=f"admiral {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register")
    for f in ("--task", "--branch", "--worktree", "--files", "--lead"):
        r.add_argument(f, default="")
    r.add_argument("--who", required=True)
    s = sub.add_parser("state")
    s.add_argument("--who", required=True)
    s.add_argument("--phase", required=True)
    s.add_argument("--note", default="")
    d = sub.add_parser("done")
    d.add_argument("--who", required=True)
    sub.add_parser("list")
    p = sub.add_parser("plan")
    p.add_argument("action", choices=["add", "rm", "list", "close"])
    p.add_argument("--lead")
    p.add_argument("--branch")
    p.add_argument("--title", default="")
    p.add_argument("--owner", default="")
    b = sub.add_parser("board")
    b.add_argument("--write", action="store_true")
    b.add_argument("--now", action="store_true")
    b.add_argument("--no-github", action="store_true")
    sub.add_parser("statusline")
    sub.add_parser("codex-hook")
    sd = sub.add_parser("send")
    sd.add_argument("who")
    sd.add_argument("message")
    wt = sub.add_parser("wait")
    wt.add_argument("--who", action="append", default=[])
    wt.add_argument("--lead", default="")
    wt.add_argument("--timeout", type=float, default=3600)
    f = sub.add_parser("focus")
    f.add_argument("tty")
    sub.add_parser("where")
    sub.add_parser("doctor", help="whether each piece Admiral needs is in place, and how to fix the rest")
    dm = sub.add_parser("demo", help="a made-up fleet to try Admiral without running dozens of sessions")
    dm.add_argument("--lang", choices=["en", "zh"], default="en")
    dm.add_argument("--tty", action="append", default=[], metavar="NAME=TTY",
                    help="tie a demo session to a real terminal tab, so a click focuses it")
    dm.add_argument("--once", action="store_true", help="build the demo board once and exit")
    a = ap.parse_args(argv)
    if a.cmd == "doctor":  # before the config loads: a config that does not is one of the things it reports
        from . import doctor
        sys.exit(doctor.main())
    if a.cmd == "codex-hook":
        try:  # a hook must never stand in Codex's way: whatever goes wrong, it says nothing and lets Codex go on
            codex.hook(config.load(), json.load(sys.stdin), sessions.proc_starts)
        except Exception:
            pass
        return
    cfg = config.load()

    if a.cmd == "register":
        reg = registry.register(cfg, a.who, a.task, a.branch, a.worktree, a.files, a.lead)
        sid, names = registry.caller(cfg)
        if reg.get("sessionId") and a.who not in names:  # itself, under another name: the board knows it anyway
            print(f"registered {a.who}, for this session ({names[0] if names else sid[:8]})")
            warn_not_running(cfg, a.lead)
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
        found = relay.wait(cfg, a.who, a.lead, timeout=a.timeout)
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
