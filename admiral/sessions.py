"""Claude Code's running sessions and the commanders their transcripts show them taking orders from.

Both sources are Claude Code's internal files, not an API: a session file that does not parse, or lacks a field the
board needs, is counted so the board can say its sources may have changed shape, never silently dropped.
"""

import glob
import json
import os
import re
import subprocess
import time

from .registry import read_json, write_json

FIELDS = ("pid", "sessionId", "status", "cwd")  # what the board needs from a session file
# A cross-session message as a transcript stores it: the sender's socket (its pid) and its name.
PEER_MSG = re.compile(rb'cc-socks/(\d+)\.sock\\"[^>]{0,400}?from-name=\\"([^\\]{1,128})\\"')
OVERLAP = 4096  # bytes re-read before where the last scan stopped, so a message cut there is still matched


def norm(s):
    return " ".join(s.split())


def proc_starts(pids):
    """pid -> (start time as `ps` prints it in C locale and UTC, the form of procStart; its terminal, like ttys012)."""
    if not pids:
        return {}
    env = dict(os.environ, LC_ALL="C", TZ="UTC")
    r = subprocess.run(["ps", "-o", "pid=,tty=,lstart=", "-p", ",".join(map(str, pids))],
                       capture_output=True, text=True, env=env)
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3:
            out[int(parts[0])] = (norm(parts[2]), parts[1] if parts[1].startswith("tty") else "")
    return out


def load(cfg, starts=proc_starts):
    """(running sessions of the configured projects, files that did not parse, files missing a needed field, running
    sessions outside the projects). A pid that is gone, or now belongs to another process, is not a session."""
    raw, broken, shapeless = [], 0, 0
    for f in glob.glob(os.path.join(cfg.sessions_dir, "*.json")):
        d = None
        for _ in range(2):  # a file read mid-write does not parse; one retry
            d = read_json(f)
            if d is not None:
                break
            time.sleep(0.2)
        if d is None:
            broken += 1
            continue
        if any(k not in d for k in FIELDS):
            shapeless += 1
            if "pid" not in d:
                continue
        raw.append(d)
    procs = starts([d["pid"] for d in raw])
    live, elsewhere = [], []
    for d in raw:
        start, tty = procs.get(d["pid"], (None, ""))
        if start is None or (d.get("procStart") and norm(d["procStart"]) != start):
            continue
        (live if cfg.in_project(d.get("cwd", "")) else elsewhere).append(dict(d, _tty=tty))
    return live, broken, shapeless, elsewhere


def transcript(cfg, cwd, session_id):
    return os.path.join(cfg.projects_dir, re.sub(r"[^A-Za-z0-9]", "-", cwd), session_id + ".jsonl")


def infer_leads(cfg, convs):
    """(sessionId -> the commander, by current name, whose message the session received last, for non-commanders;
    stats: transcripts missing, transcripts read, whether any commander message was ever found, and "heard":
    sessionId -> the name that last commander message came from, whether that commander still runs or not).
    Only the bytes added since the last run are read; <state_dir>/lead-cache.json keeps where each live session's
    scan stopped and the last commander it found, and only live sessions are kept, so it stays bounded."""
    path = cfg.cache("lead-cache.json")
    cache = read_json(path) or {}
    commanders = [c for c in convs if c["isCommander"]]
    by_pid = {pid: c["name"] for c in commanders for pid in c.get("pids") or [c["pid"]]}  # every process of one
    by_name = {n: c["name"] for c in commanders for n in [c["name"]] + c["former"]}
    fresh, out = {}, {}
    stats = {"missing": 0, "read": 0, "found": False, "heard": {}}
    for c in convs:
        if c["isCommander"] or not c["sessionId"]:
            continue
        entry = dict(cache.get(c["sessionId"]) or {"offset": 0, "pid": None, "name": ""})
        t = transcript(cfg, c["cwd"], c["sessionId"])
        if not os.path.exists(t):
            stats["missing"] += 1
        try:
            size = os.path.getsize(t)
            start = 0 if size < entry["offset"] else max(0, entry["offset"] - OVERLAP)
            with open(t, "rb") as fh:
                fh.seek(start)
                chunk = fh.read()
            for pid, name in PEER_MSG.findall(chunk):
                pid, name = int(pid), name.decode("utf-8", "replace")
                if pid in by_pid or name.startswith(cfg.commander_prefix):
                    entry.update(pid=pid, name=name)
            entry["offset"] = size
            stats["read"] += 1
        except OSError:
            pass
        stats["found"] = stats["found"] or bool(entry["name"])
        if entry["name"]:
            stats["heard"][c["sessionId"]] = entry["name"]
        fresh[c["sessionId"]] = entry
        lead = by_pid.get(entry["pid"]) or by_name.get(entry["name"])
        if lead:
            out[c["sessionId"]] = lead
    write_json(path, fresh)
    return out, stats


# `git push` output, as the tool result stores it: a "To <remote>" line, then one line per branch it updated.
PUSH_TO = re.compile(r"^To \S+$")
PUSH_REF = re.compile(r"^\s*[+*]?\s*(?:\[new branch\]|[0-9a-f]{7,}\.{2,3}[0-9a-f]{7,})\s+\S+\s+->\s+(?:refs/heads/)?(\S+)")
PUSHED_KEPT = 100  # branches remembered per session
WORK_CACHE_VERSION = 2  # what a cache entry holds; an entry of another version is read again from the start


def pushed(text):
    """The branches a `git push` output says it updated."""
    out, inside = [], False
    for line in text.splitlines():
        if PUSH_TO.match(line):
            inside = True
        elif inside and (m := PUSH_REF.match(line)):
            out.append(m.group(1))
        else:
            inside = False
    return out


def result_text(block):
    c = block.get("content")
    return c if isinstance(c, str) else "".join(x.get("text", "") for x in c or [] if isinstance(x, dict))


WORK_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path",
              "Bash": "command"}


def work_in(cfg, convs, roots):
    """sessionId -> {"counts": {worktree: how many of the session's edits and commands touched it}, "pushed": the
    branches its `git push` outputs updated, oldest first}; a commander's edits and commands are not counted (it
    reads its members' worktrees), only its pushes. A session that moved to another
    branch without re-registering is still known by what it pushed and where it works. Only the bytes added since
    the last run are read, up to the last whole line; <state_dir>/work-cache.json keeps where each live session's
    scan stopped and what it found, and only live sessions are kept, so it stays bounded."""
    path = cfg.cache("work-cache.json")
    cache = read_json(path) or {}
    roots = sorted({r for r in roots if r}, key=len, reverse=True)  # the longest first: a/b-c before a/b
    pattern = re.compile("|".join(re.escape(r) + r"(?![-\w])" for r in roots)) if roots else None
    fresh, out = {}, {}
    for c in convs:
        if not c["sessionId"]:
            continue
        entry = cache.get(c["sessionId"]) or {}
        if entry.get("v") != WORK_CACHE_VERSION:
            entry = {"v": WORK_CACHE_VERSION, "offset": 0, "counts": {}, "pushed": []}
        entry = dict(entry, counts=dict(entry["counts"]))
        t = transcript(cfg, c["cwd"], c["sessionId"])
        try:
            size = os.path.getsize(t)
            if size < entry["offset"]:
                entry = {"v": WORK_CACHE_VERSION, "offset": 0, "counts": {}, "pushed": []}
            with open(t, "rb") as fh:
                fh.seek(entry["offset"])
                chunk = fh.read()
            chunk = chunk[:chunk.rfind(b"\n") + 1]  # a line still being written is read next time, whole
            for line in chunk.splitlines():
                use = pattern is not None and b'"tool_use"' in line
                push = b'"tool_result"' in line and b" -> " in line and b"To " in line
                if not (use or push):
                    continue
                try:
                    blocks = (json.loads(line).get("message") or {}).get("content")
                except ValueError:
                    continue
                for b in blocks if isinstance(blocks, list) else []:
                    if push and isinstance(b, dict) and b.get("type") == "tool_result":
                        for br in pushed(result_text(b)):
                            entry["pushed"] = [x for x in entry["pushed"] if x != br][-PUSHED_KEPT + 1:] + [br]
                    if use and not c["isCommander"] and isinstance(b, dict) and b.get("type") == "tool_use" \
                            and b.get("name") in WORK_TOOLS:
                        arg = str((b.get("input") or {}).get(WORK_TOOLS[b["name"]], ""))
                        for root in {m.group(0) for m in pattern.finditer(arg)}:
                            entry["counts"][root] = entry["counts"].get(root, 0) + 1
            entry["offset"] += len(chunk)
        except OSError:
            pass
        fresh[c["sessionId"]] = entry
        out[c["sessionId"]] = {"counts": entry["counts"], "pushed": entry["pushed"]}
    write_json(path, fresh)
    return out


def pushed_by(work, branch):
    """The sessionId whose `git push` last updated the branch, among sessions that pushed it; None when none did or
    several did (an acceptance session merging work, say)."""
    hits = [sid for sid, w in work.items() if branch in w["pushed"]]
    return hits[0] if len(hits) == 1 else None


def owner_by_work(counts, root, least=3, margin=3):
    """The sessionId that clearly did the work in a worktree: at least `least` actions there, and `margin` times
    as many as any other session; None when nobody did, or it is not clear."""
    ranked = sorted(((n["counts"].get(root, 0), sid) for sid, n in counts.items()), reverse=True)
    if not ranked or ranked[0][0] < least:
        return None
    if len(ranked) > 1 and ranked[0][0] < margin * ranked[1][0]:
        return None
    return ranked[0][1]


def lock_holders(cfg):
    """lock name -> who holds it (the lock tool writes `who=<session> <task>` into <locks>/<name>/owner)."""
    out = {}
    for f in glob.glob(os.path.join(cfg.locks_dir, "*", "owner")):
        try:
            with open(f, encoding="utf-8") as fh:
                who = next((ln[4:].strip() for ln in fh if ln.startswith("who=")), "")
        except OSError:
            continue
        if who:
            out[os.path.basename(os.path.dirname(f))] = who
    return out


def last_commit(worktree):
    """Epoch of the worktree's last commit, "gone" when the directory is missing, None when unknown."""
    if not worktree:
        return None
    if not os.path.isdir(worktree):
        return "gone"
    r = subprocess.run(["git", "-C", worktree, "log", "-1", "--format=%ct"], capture_output=True, text=True)
    return float(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def worktree_branch(worktree):
    """The branch a worktree has checked out now, so a session that moved on without re-registering still counts."""
    if not worktree or not os.path.isdir(worktree):
        return ""
    r = subprocess.run(["git", "-C", worktree, "branch", "--show-current"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def worktrees(cfg):
    """branch -> the worktree that has it checked out, from the repository's worktree list."""
    if not cfg.repo_dir:
        return {}
    r = subprocess.run(["git", "-C", cfg.repo_dir, "worktree", "list", "--porcelain"], capture_output=True, text=True)
    out, path = {}, ""
    for line in r.stdout.splitlines():
        if line.startswith("worktree "):
            path = line[9:]
        elif line.startswith("branch refs/heads/"):
            out[line[18:]] = path
    return out


ASKS = re.compile(r"(需要你|请你|你来|你确认|你决定|你批准|你同意|你放行|请确认|请批准|请放行|是否|要不要|可以吗|好吗|行吗"
                  r"|[?？]\s*$|please (confirm|approve|decide)|do you want|would you like|need you to|shall I)", re.I)
TAIL = 256 * 1024  # bytes read from a transcript's end to find how its last turn ended


def last_turn(path):
    """The text the session's last turn ended on, when the assistant spoke last (no tool call pending, the person
    has not answered); None otherwise."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            start = max(0, fh.tell() - TAIL)
            fh.seek(start)
            lines = fh.read().decode("utf-8", "replace").splitlines()
            if start:
                lines = lines[1:]  # read from mid-file: the first line is cut
    except OSError:
        return None
    for line in reversed(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") not in ("user", "assistant"):
            continue
        if d["type"] == "user":
            return None  # the person, or a tool result, came last
        content = (d.get("message") or {}).get("content")
        if isinstance(content, list):
            if any(b.get("type") == "tool_use" for b in content):
                return None
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
        else:
            text = str(content or "").strip()
        return text or None
    return None


def tail(text, limit=100):
    """A turn's closing words, at most `limit` characters, starting at a word (not mid-word) and marked as cut."""
    t = " ".join(text.split())
    if len(t) <= limit:
        return t
    cut = t[-limit:]
    space = cut.find(" ")
    if 0 <= space < limit // 4:  # a space early on: start at the word after it (text without spaces is cut as is)
        cut = cut[space + 1:]
    return "…" + cut


def asks(text):
    """Whether a turn's closing words ask the person to act or answer."""
    return bool(ASKS.search(text.strip()[-300:]))


def json_dump(data):
    return json.dumps(data, ensure_ascii=False)
