"""Codex sessions, as the plugin's Codex hooks record them.

Codex keeps no file that says whether a session works, waits for the person or sits idle, so the hooks the plugin
gives Codex (plugin/codex/hooks.json) run `admiral codex-hook` at each turn, tool call and permission request, and it
writes one file per Codex process under <state_dir>/codex, in the shape of Claude Code's session files: the board
reads both alike, and a conversation open in two processes is two files, as with Claude Code. Waiting is Codex's own
PermissionRequest, not a guess: a session waits while any call it asked about has not run. The session's name, when
it has one, is read from Codex's thread list, an internal file like Claude Code's: missing or changed, the session is
shown by its registration, or its id.
"""

import fcntl
import glob
import json
import os
import sqlite3
import subprocess
import time

from .registry import read_json, write_json

STATUS = {"SessionStart": "idle", "UserPromptSubmit": "busy", "PreToolUse": "busy", "PostToolUse": "busy",
          "PermissionRequest": "waiting", "Stop": "idle", "Interrupt": "idle"}
CLEARS = {"SessionStart", "UserPromptSubmit", "Stop", "Interrupt"}  # no call is left waiting after these
ASKS = {"request_user_input"}  # tools that put a question to the person: the session waits while one runs
CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")


def sessions_dir(cfg):
    return cfg.sub("codex")


def record_path(cfg, sid, pid):
    return os.path.join(sessions_dir(cfg), f"{sid}.{pid}.json")


def records_of(cfg, sid):
    """The record files of one session, one per process it runs in."""
    return glob.glob(os.path.join(glob.escape(sessions_dir(cfg)), glob.escape(sid) + ".*.json"))


def codex_pid(start=None):
    """The Codex process this hook runs under: the nearest ancestor whose command is codex; None when there is none."""
    pid = start or os.getppid()
    for _ in range(8):  # a hook runs a shell or two below Codex, never deeper
        r = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True)
        parts = r.stdout.split(None, 1)
        if len(parts) != 2:
            return None
        if os.path.basename(parts[1].strip()) == "codex":
            return pid
        pid = int(parts[0])
        if pid <= 1:
            return None
    return None


def threads(query, args):
    """One row from Codex's newest thread database, read-only; None when there is none or it cannot be read (it is
    Codex's internal file, and may change shape)."""
    dbs = sorted(glob.glob(os.path.join(CODEX_HOME, "state_*.sqlite")))
    if not dbs:
        return None
    try:
        db = sqlite3.connect(f"file:{dbs[-1]}?mode=ro", uri=True, timeout=1)
        try:
            return db.execute(query, args).fetchone()
        finally:
            db.close()
    except sqlite3.Error:
        return None


def thread_name(sid):
    """The name Codex keeps for a session; "" when it has none."""
    row = threads("SELECT name FROM threads WHERE id = ?", (sid,))
    return (row[0] or "") if row else ""


def thread_exists(sid):
    return threads("SELECT 1 FROM threads WHERE id = ?", (sid,)) is not None


def thread_named(name):
    """The Codex session last active under `name`, open or closed; "" when Codex has none."""
    row = threads("SELECT id FROM threads WHERE name = ? AND archived = 0 ORDER BY updated_at DESC LIMIT 1", (name,))
    return row[0] if row else ""


def last_thread(directory):
    """The Codex session last active in `directory`, open or closed; "" when Codex has none there."""
    row = threads("SELECT id FROM threads WHERE cwd = ? AND archived = 0 ORDER BY updated_at DESC LIMIT 1",
                  (os.path.realpath(directory),))
    return row[0] if row else ""


def command_of(event):
    """What a call runs, as both its PreToolUse and its PermissionRequest give it: the command where there is one,
    else the whole input but for the reason a request adds."""
    given = event.get("tool_input")
    if isinstance(given, dict) and "command" in given:
        given = given["command"]
    elif isinstance(given, dict):
        given = {k: v for k, v in given.items() if k != "description"}
    return json.dumps(given, sort_keys=True, ensure_ascii=False)


def locked(cfg):
    """An exclusive lock over the records, so hooks of parallel tool calls apply one after another, not over each
    other."""
    os.makedirs(sessions_dir(cfg), exist_ok=True)
    fh = open(os.path.join(sessions_dir(cfg), ".lock"), "w")
    fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


def hook(cfg, event, starts, find_pid=codex_pid, name_of=thread_name, now=None):
    """Record what one Codex hook event says of its session, in the record of the Codex process the hook runs under;
    SessionEnd removes that record."""
    sid, kind = str(event.get("session_id") or ""), event.get("hook_event_name") or ""
    if not sid or "/" in sid or sid.startswith(".") or (kind not in STATUS and kind != "SessionEnd"):
        return
    pid = find_pid()
    if pid is None:
        return
    proc_start = (starts([pid]).get(pid) or (None,))[0]
    if not proc_start:  # without it a reused pid could pass for this session, and the record could never be pruned
        return
    path = record_path(cfg, sid, pid)
    with locked(cfg):
        if kind == "SessionEnd":
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            return
        old = read_json(path) or {}
        if old.get("procStart") != proc_start:
            old = {}  # a record left by another process that had this pid
        pending = list(old.get("pending") or [])
        running = dict(old.get("running") or {})  # tool_use_id -> command, for the calls begun and not yet ended
        call = str(event.get("tool_use_id") or "")
        if kind == "SessionStart" and event.get("source") == "compact" and old:
            status = old.get("status", "busy")  # compaction mid-turn: the turn goes on
        else:
            if kind in CLEARS:
                pending, running = [], {}
            elif kind == "PermissionRequest":
                # Codex gives a request no tool_use_id: it is a call begun with the same command and not asked about
                # yet, the earliest such; two alike running at once can still be told apart only by when they began
                same = [c for c, cmd in running.items() if cmd == command_of(event) and c not in pending]
                pending.append(same[0] if same else "")
            elif kind == "PreToolUse":
                running[call] = command_of(event)
                if event.get("tool_name") in ASKS:
                    pending.append(call)
            elif kind == "PostToolUse":
                running.pop(call, None)
                # its own request ends with it; one no call could be found for ends with any call that ends: a call
                # running beside it may end it early, but left there it would hold the session waiting until the turn
                # ends, which is worse
                pending = [p for p in pending if call and p and p != call]
            status = "waiting" if pending else STATUS[kind]
        ms = int((time.time() if now is None else now) * 1000)
        write_json(path, {"pid": pid, "procStart": proc_start, "sessionId": sid,
                          "cwd": event.get("cwd") or old.get("cwd", ""), "status": status, "statusUpdatedAt": ms,
                          "startedAt": old.get("startedAt", ms), "name": name_of(sid) or old.get("name", ""),
                          "pending": pending, "running": running, "agent": "codex"})
        if kind == "SessionStart":
            prune(cfg, starts)


def prune(cfg, starts):
    """Remove the records of Codex processes that are gone (or whose pid another process now has), so the directory
    does not grow. A record is one process's, so pruning it never touches a live one."""
    records = [(f, read_json(f) or {}) for f in glob.glob(os.path.join(sessions_dir(cfg), "*.json"))]
    alive = starts([d["pid"] for _, d in records if isinstance(d.get("pid"), int)])
    for f, d in records:
        if not d.get("procStart") or (alive.get(d.get("pid")) or (None,))[0] != d["procStart"]:
            try:
                os.remove(f)
            except FileNotFoundError:
                pass
