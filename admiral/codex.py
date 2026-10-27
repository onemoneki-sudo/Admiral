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
from datetime import datetime

from .registry import read_json, write_json

STATUS = {"SessionStart": "idle", "UserPromptSubmit": "busy", "PreToolUse": "busy", "PostToolUse": "busy",
          "PermissionRequest": "waiting", "Stop": "idle", "Interrupt": "idle"}
CLEARS = {"SessionStart", "UserPromptSubmit", "Stop", "Interrupt"}  # no call is left waiting after these
ASKS = {"request_user_input"}  # tools that put a question to the person: the session waits while one runs
CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
# what Codex writes to a session's transcript once it goes on: a call's output, a message, the turn's end
MOVED_ON = {"function_call_output", "custom_tool_call_output", "agent_message", "task_complete", "turn_aborted"}
TAIL = 256 * 1024  # bytes of the transcript read from its end: far more than one call's worth


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


def transcript_of(sid):
    """The file Codex writes the session's transcript to; "" when its thread list does not say."""
    row = threads("SELECT rollout_path FROM threads WHERE id = ?", (sid,))
    return (row[0] or "") if row else ""


def transcript_events(path, since):
    """(events, reached): the transcript's events (at, type, call_id, text), oldest first, read from its end far
    enough back to hold everything since `since` and the calls made just before it; `reached` is False when even the
    longer read holds nothing from before `since`, the file being longer. ([], True) when it cannot be read."""
    for size in (TAIL, 16 * TAIL):  # one output can be larger than the usual read: then once more, further back
        try:
            with open(path, "rb") as fh:
                fh.seek(0, 2)
                start = max(0, fh.tell() - size)
                fh.seek(start)
                lines = fh.read().decode("utf-8", "replace").splitlines()
        except OSError:
            return [], True
        events = []
        for line in lines[1 if start else 0:]:  # read from mid-file, the first line is cut
            try:
                d = json.loads(line)
                at = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).timestamp()
            except (AttributeError, KeyError, TypeError, ValueError):  # a line cut short, or not an event
                continue
            p = d.get("payload") or {}
            events.append((at, str(p.get("type") or ""), p.get("call_id") or "",
                           str(p.get("input") or p.get("arguments") or "")))
        if not start or (events and events[0][0] < since - 60):
            return events, True
    return events, False


def moved_on(rec, transcript=None):
    """When a session its hooks left waiting went on, in milliseconds; None while it has not. Codex tells no hook
    when the person approves a call or answers, but writes to the session's transcript: the output of each call that
    asked (found by the command it asked about, among the calls made just before), else any call's output or message;
    or the turn's end."""
    since = (rec.get("statusUpdatedAt") or 0) / 1000
    path = (transcript or transcript_of)(rec.get("sessionId", ""))
    events, reached = transcript_events(path, since)
    if not reached:  # more written since the request than the longest read: the call it asked about runs
        return int(os.path.getmtime(path) * 1000)
    after = [e for e in events if e[0] > since]
    ended = min((e[0] for e in after if e[1] in ("task_complete", "turn_aborted")), default=None)
    anything = min((e[0] for e in after if e[1] in MOVED_ON), default=None)
    went = []  # when each call asked about went on; None for one that has not
    for asked in [a for a in rec.get("asked") or [] if a]:
        quoted = json.dumps(asked, ensure_ascii=False)[1:-1]  # as a call's JSON arguments hold it
        calls = [e for e in events if e[1].endswith("_call") and since - 60 <= e[0] <= since + 5
                 and (asked in e[3] or quoted in e[3])]
        mine = [e[0] for e in after if calls and e[2] == calls[-1][2] and e[1].endswith("_output")]
        went.append(min(mine) if mine else None if calls else anything)  # a call not found: any output will do
    answered = (max(went) if None not in went else None) if went else anything
    # the turn's end answers everything; whichever came first
    at = min((x for x in (answered, ended) if x is not None), default=None)
    return int(at * 1000) if at is not None else None


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


def command_text(event):
    """The command a request asks about, as the session's transcript would hold it inside the call; "" for none."""
    given = event.get("tool_input")
    given = given.get("command") if isinstance(given, dict) else None
    if isinstance(given, list):
        given = " ".join(map(str, given))
    return given if isinstance(given, str) else ""


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
        asked = list(old.get("asked") or [])  # the commands asked about, for finding their calls in the transcript
        call = str(event.get("tool_use_id") or "")
        if kind == "SessionStart" and event.get("source") == "compact" and old:
            status = old.get("status", "busy")  # compaction mid-turn: the turn goes on
        else:
            if kind in CLEARS:
                pending, running, asked = [], {}, []
            elif kind == "PermissionRequest":
                asked = (asked + [command_text(event)])[-8:]  # a few at most: requests answered leave it at the turn
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
        if status == "waiting" and old.get("status") == "waiting":
            ms = old.get("statusUpdatedAt", ms)  # still waiting: since the wait began, which the transcript is read from
        write_json(path, {"pid": pid, "procStart": proc_start, "sessionId": sid,
                          "cwd": event.get("cwd") or old.get("cwd", ""), "status": status, "statusUpdatedAt": ms,
                          "startedAt": old.get("startedAt", ms), "name": name_of(sid) or old.get("name", ""),
                          "pending": pending, "running": running, "asked": asked, "agent": "codex"})
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
