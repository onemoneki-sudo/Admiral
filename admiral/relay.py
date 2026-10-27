"""A commander and its executors across agents: `admiral send` puts a message into a Codex session, `admiral wait`
returns as soon as a member reports.

Claude Code sessions message each other with Claude Code's own tool, and nothing outside Claude Code can put a
message into one, so `send` serves Codex sessions, through `codex queue`: a session open in a terminal takes the
message up within seconds, one that is closed when it is resumed. An executor reports with `admiral state`, whatever
its agent; its commander, run in the background, `admiral wait` ends when one does, or starts waiting for the person,
or ends a turn, and Claude Code tells a session when a command it left in the background exits. Which session a name
means is decided as the board decides it (board.attach), so a message never goes where the board would not show it.
"""

import os
import subprocess
import time

from . import board, codex, registry, sessions

ORDER = {"waiting": 0, "busy": 1, "shell": 2, "idle": 3}


def registration(cfg, who):
    """The registration under `who`, made by its session or for it."""
    return next((r for r in registry.registrations(cfg) if who in registry.names_of(r)), None)


def attached(cfg, starts):
    """(session, its registration or None) for each running session, read once for any number of names."""
    live, _, _, elsewhere = sessions.load(cfg, starts)
    current = {s.get("name") for s in live + elsewhere if s.get("name")}
    return list(zip(live, board.attach(live, registry.registrations(cfg), current, elsewhere)))


def sessions_of(cfg, who, starts, pairs=None):
    """The running sessions (one per process) `who` names: those its registration is attached to, else those of
    that name with no registration of their own."""
    pairs = attached(cfg, starts) if pairs is None else pairs
    # a Claude Code session goes by its own name on the board, whatever name it registered under
    return [s for s, reg in pairs if (reg and who in registry.names_of(reg))
            or (s.get("name") == who and (reg is None or s.get("agent") != "codex"))]


def codex_thread(cfg, who, starts):
    """(the Codex thread `who` means, or "", why not)."""
    found = sessions_of(cfg, who, starts)
    if any(s.get("agent") != "codex" for s in found):
        return "", f"{who} is a Claude Code session: message it with Claude Code's own SendMessage"
    threads = {s["sessionId"] for s in found}
    if len(threads) > 1:
        return "", f"{who} names {len(threads)} Codex sessions; register each under a name of its own"
    if threads:
        return threads.pop(), ""
    # not running: the thread it registered from, the closed one Codex keeps under that name, or the last one in its
    # worktree, unless Codex sessions run there that the board could not tell apart
    reg = registration(cfg, who)
    if reg and reg.get("sessionId") and codex.thread_exists(reg["sessionId"]):
        return reg["sessionId"], ""
    named = codex.thread_named(who)
    if named:
        return named, ""
    wt = board.first((reg or {}).get("worktree"))
    if wt:
        live = sessions.load(cfg, starts)[0]
        here = {s["sessionId"] for s in live if s.get("agent") == "codex"
                and os.path.realpath(s.get("cwd") or "/nonexistent") == os.path.realpath(wt)}
        if here:
            return "", (f"{len(here)} Codex sessions run in {wt} and none is {who} for certain; register each under "
                        "a name of its own")
        thread = codex.last_thread(wt)
        if thread:
            return thread, ""
    return "", (f"no Codex session is {who}: none running has that name or registration, and Codex has none in its "
                "registered worktree")


def send(cfg, who, message, starts, run=subprocess.run):
    """(ok, what happened)."""
    thread, why = codex_thread(cfg, who, starts)
    if not thread:
        return False, why
    r = run(["codex", "queue", "--thread", thread, "--message", message], capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=60)
    if r.returncode != 0:
        return False, f"codex queue failed: {(r.stderr or r.stdout).strip()[:300]}"
    return True, f"queued for {who} (Codex session {thread[:8]})"


def watched(cfg, who=(), lead=""):
    """The names to watch: those given, and every registration under the commander."""
    names = list(who)
    if lead:
        names += [r["who"] for r in registry.registrations(cfg) if r.get("lead") == lead and r["who"] not in names]
    return names


def snapshot(cfg, names, starts):
    """name -> (what it last reported, or None with no registration; its sessions' most pressing status, "" with no
    session; when that status last changed)."""
    out, pairs = {}, attached(cfg, starts)  # one look for every name: the sessions are read once
    for who in names:
        reg = registration(cfg, who)
        found = sorted(sessions_of(cfg, who, starts, pairs), key=lambda s: (ORDER.get(s.get("status"), 9),
                                                                     -(s.get("statusUpdatedAt") or 0)))
        # the most pressing process speaks, with its own time: another process's work moves nothing here
        out[who] = ((reg.get("phase"), reg.get("note", ""), reg.get("phaseAt")) if reg else None,
                    found[0].get("status", "") if found else "", (found[0].get("statusUpdatedAt") or 0) if found else 0)
    return out


def changes(before, after):
    """What happened between two snapshots, one line per event."""
    out = []
    for who, (rep, status, at) in after.items():
        if who not in before:
            out.append(f"{who}: registered")
            continue
        orep, ostatus, oat = before[who]
        if rep != orep:
            out.append(f"{who}: registration closed" if rep is None else
                       f"{who}: reported {rep[0] or '-'}" + (f": {rep[1]}" if rep[1] else ""))
        moved = status != ostatus or at != oat  # a turn begun and ended between two looks moves the time only
        if moved and status == "waiting":
            out.append(f"{who}: waiting for the person (an approval or a question)")
        elif moved and status == "idle" and ostatus in ("busy", "shell", "idle", "waiting"):
            out.append(f"{who}: finished a turn")
        elif ostatus and not status:
            out.append(f"{who}: its session ended")
    return out


def wait(cfg, who=(), lead="", timeout=3600, interval=5, starts=None, sleep=time.sleep, clock=time.monotonic):
    """The changes once any watched member reports, starts waiting for the person, ends a turn, ends or closes its
    registration, or a new one registers under the commander; [] when nothing did within `timeout` seconds. A member
    watched at the start stays watched after it leaves the commander's registrations, so its last word is heard."""
    starts = starts or sessions.proc_starts
    first_names = watched(cfg, who, lead)
    before = snapshot(cfg, first_names, starts)
    end = clock() + timeout
    while clock() < end:
        sleep(interval)
        names = first_names + [n for n in watched(cfg, who, lead) if n not in first_names]
        found = changes(before, snapshot(cfg, names, starts))
        if found:
            return found
    return []
