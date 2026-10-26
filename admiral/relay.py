"""A commander and its executors across agents: `admiral send` puts a message into a Codex session, `admiral wait`
returns as soon as a member reports.

Claude Code sessions message each other with Claude Code's own tool, and nothing outside Claude Code can put a
message into one, so `send` serves Codex sessions, through `codex queue`: a session open in a terminal takes the
message up within seconds, one that is closed when it is resumed. An executor reports with `admiral state`, whatever
its agent; its commander, run in the background, `admiral wait` ends when one does, or starts waiting for the person,
or ends a turn, and Claude Code tells a session when a command it left in the background exits. Which session a name
means is decided as the board decides it (board.attach), so a message never goes where the board would not show it.
"""

import subprocess
import time

from . import board, codex, registry, sessions

ORDER = {"waiting": 0, "busy": 1, "shell": 2, "idle": 3}


def registration(cfg, who):
    """The registration under `who`, made by its session or for it."""
    return next((r for r in registry.registrations(cfg) if who in registry.names_of(r)), None)


def sessions_of(cfg, who, starts):
    """The running sessions (one per process) `who` names: those its registration is attached to, else those of
    that name with no registration of their own."""
    live, _, _, elsewhere = sessions.load(cfg, starts)
    current = {s.get("name") for s in live + elsewhere if s.get("name")}
    pairs = list(zip(live, board.attach(live, registry.registrations(cfg), current)))
    return [s for s, reg in pairs if (reg and who in registry.names_of(reg)) or (reg is None and s.get("name") == who)]


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
    reg = registration(cfg, who)  # not running: the thread it registered from, or the last one in its worktree
    if reg and reg.get("sessionId") and codex.thread_exists(reg["sessionId"]):
        return reg["sessionId"], ""
    wt = board.first((reg or {}).get("worktree"))
    thread = codex.last_thread(wt) if wt else ""
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
    out = {}
    for who in names:
        reg = registration(cfg, who)
        found = sorted(sessions_of(cfg, who, starts), key=lambda s: ORDER.get(s.get("status"), 9))
        out[who] = ((reg.get("phase"), reg.get("note", ""), reg.get("phaseAt")) if reg else None,
                    found[0].get("status", "") if found else "", max((s.get("statusUpdatedAt") or 0 for s in found), default=0))
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
