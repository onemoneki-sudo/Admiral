"""Registrations (who works on what, under which commander, at which phase) and commanders' plans.

One JSON file per session under <state_dir>/registry/ and per commander under <state_dir>/batches/, each written
whole and atomically, so two sessions never write the same file. A file name carries a hash of the name, so names
that differ only in non-ASCII characters never share a file.
"""

import hashlib
import json
import os
import re
import time

from .words import phase_key


def key(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) + "_" + hashlib.sha1(name.encode()).hexdigest()[:10]


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"  # one per process: the background job and a session may write the same file
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def running_names(cfg):
    """Names of the sessions Claude Code lists as running (for warnings only)."""
    names = set()
    try:
        for f in os.listdir(cfg.sessions_dir):
            if f.endswith(".json"):
                d = read_json(os.path.join(cfg.sessions_dir, f)) or {}
                if d.get("name"):
                    names.add(d["name"])
    except OSError:
        pass
    return names


# ---- registrations ----
#
# A registration its session made is kept under that session, one per session whatever it is called (and whatever
# it registers under), so a rename moves nothing and two sessions of one name never share a file. One made without a
# session (by hand, or for another session) is kept under its name, as it always was.

def reg_path(cfg, who):
    """The file of a registration made without a session, under its name."""
    return cfg.sub("registry", key(who) + ".json")


def session_path(cfg, sid):
    """The file of a registration its session made."""
    return cfg.sub("registry", "session-" + key(sid) + ".json")


def path_of(cfg, reg):
    return session_path(cfg, reg["sessionId"]) if reg.get("sessionId") else reg_path(cfg, reg["who"])


def caller(cfg):
    """(session ID, names) of the Claude Code session running this command, as Claude Code hands its commands
    (CLAUDE_CODE_SESSION_ID, CLAUDE_PID): its name now first, then its former ones. ("", []) outside a session."""
    sid, pid = os.environ.get("CLAUDE_CODE_SESSION_ID", ""), os.environ.get("CLAUDE_PID", "")
    d = read_json(os.path.join(cfg.sessions_dir, pid + ".json")) if pid.isdigit() else None
    if not sid or not d or d.get("sessionId") != sid:
        return "", []
    return sid, [n for n in [d.get("name")] + [f.get("name") for f in d.get("formerNames") or []] if n]


def names_of(reg):
    """The names a registration answers to: the one it is under now and those it was under before."""
    return [reg["who"]] + [n for n in reg.get("aka") or [] if n != reg["who"]]


def itself(cfg, who, sid, names):
    """Whether a session registering a name it does not have (its task's, say) registers itself, not another: it is
    no commander (commanders register their members, open or not), the name is no other running session's, and the
    session is not registered as itself already."""
    if names and names[0].startswith(cfg.commander_prefix):
        return False
    if who in running_names(cfg) - set(names):
        return False
    return read_json(session_path(cfg, sid)) is None


def resolve(cfg, who):
    """The registration a command naming `who` means: from inside a session, its own when `who` is a name of the
    session or of its registration; else the one made under that name without a session; else that of the one other
    session registered under that name. None when there is none, or more than one."""
    sid, names = caller(cfg)
    own = read_json(session_path(cfg, sid)) if sid else None
    if own and (who in names or who in names_of(own)):
        return own
    reg = read_json(reg_path(cfg, who))
    if reg:
        return reg
    others = [r for r in registrations(cfg) if r.get("sessionId") and r["who"] == who]
    return others[0] if len(others) == 1 else None


def renamed(reg, who):
    """The registration under `who`, keeping the names it was under before."""
    if reg["who"] == who:
        return reg
    return dict(reg, who=who, aka=list(dict.fromkeys(names_of(reg))))


def register(cfg, who, task="", branch="", worktree="", files="", lead=""):
    """Create or replace a registration; a phase already reported is kept. Made by the session it names (or by a
    session registering itself under another name), it is kept under that session and follows it through renames;
    one made for another session is kept under its name."""
    sid, names = caller(cfg)
    fields = {"task": task, "branch": branch, "worktree": worktree, "files": files, "lead": lead, "since": time.time()}
    if sid and (who in names or itself(cfg, who, sid, names)):
        own = read_json(session_path(cfg, sid))
        by_name = read_json(reg_path(cfg, who))  # made for it under this name before it registered itself
        old = own or (by_name if by_name and not by_name.get("sessionId") else None) or {}
        reg = dict(renamed(old, who) if old.get("who") else {"who": who}, **fields, sessionId=sid,
                   phase=old.get("phase"), note=old.get("note", ""), phaseAt=old.get("phaseAt"))
        write_json(session_path(cfg, sid), reg)
        if by_name and not own:
            os.remove(reg_path(cfg, who))  # after the write, so nothing is lost if it fails
        return reg
    old = read_json(reg_path(cfg, who)) or {}
    reg = dict({"who": who}, **fields, phase=old.get("phase"), note=old.get("note", ""), phaseAt=old.get("phaseAt"))
    write_json(reg_path(cfg, who), reg)
    return reg


def set_phase(cfg, who, phase, note=""):
    """(ok, message). A phase in either language; waiting needs a note saying on whom or what."""
    k = phase_key(phase)
    if k is None:
        return False, f"unknown phase {phase!r}"
    if k == "waiting" and not note:
        return False, "the waiting phase needs a note saying on whom or what it waits"
    if k == "needs_you" and not note:
        return False, "the needs_you phase needs a note saying what the person must do"
    reg = resolve(cfg, who)
    if reg is None:
        return False, f"{who} is not registered; register first"
    sid, names = caller(cfg)
    if reg.get("sessionId") == sid and names and who == names[0]:
        reg = renamed(reg, who)  # its session reports under the name it has now
    reg.update(phase=k, note=note.replace("\n", " "), phaseAt=time.time())
    write_json(path_of(cfg, reg), reg)
    return True, k


def done(cfg, who):
    reg = resolve(cfg, who)
    try:
        os.remove(path_of(cfg, reg)) if reg else None
        return reg is not None
    except FileNotFoundError:
        return False


def registrations(cfg):
    d = cfg.sub("registry")
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                reg = read_json(os.path.join(d, f))
                if reg and reg.get("who"):
                    out.append(reg)
    return out


# ---- commanders' plans ----

def batch_path(cfg, lead):
    return cfg.sub("batches", key(lead) + ".json")


def plan(cfg, lead):
    return read_json(batch_path(cfg, lead)) or {"lead": lead, "created": time.time(), "items": []}


def plan_add(cfg, lead, branch, title="", owner=""):
    """Add a deliverable, or update its title and owner when the branch is already planned."""
    p = plan(cfg, lead)
    item = next((it for it in p["items"] if it["branch"] == branch), None)
    if item:
        item.update(title=title or item["title"], owner=owner or item.get("owner", ""))
    else:
        p["items"].append({"branch": branch, "title": title, "owner": owner, "added": time.time()})
    write_json(batch_path(cfg, lead), p)
    return p


def plan_remove(cfg, lead, branch):
    p = plan(cfg, lead)
    kept = [it for it in p["items"] if it["branch"] != branch]
    if len(kept) == len(p["items"]):
        return False
    p["items"] = kept
    write_json(batch_path(cfg, lead), p)
    return True


def plan_close(cfg, lead):
    """Archive the plan; a closed plan no longer shows on the board."""
    src = batch_path(cfg, lead)
    if not os.path.exists(src):
        return False
    dst = cfg.sub("batches", "closed", time.strftime("%Y%m%d-%H%M%S-") + os.path.basename(src))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)
    return True


def plans(cfg):
    d = cfg.sub("batches")
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                p = read_json(os.path.join(d, f))
                if p and p.get("lead") and isinstance(p.get("items"), list):
                    out.append(p)
    return out
