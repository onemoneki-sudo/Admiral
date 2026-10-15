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
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


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

def reg_path(cfg, who):
    return cfg.sub("registry", key(who) + ".json")


def register(cfg, who, task="", branch="", worktree="", files="", lead=""):
    """Create or replace a registration; a phase already reported is kept."""
    old = read_json(reg_path(cfg, who)) or {}
    reg = {"who": who, "task": task, "branch": branch, "worktree": worktree, "files": files, "lead": lead,
           "since": time.time(), "phase": old.get("phase"), "note": old.get("note", ""), "phaseAt": old.get("phaseAt")}
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
    reg = read_json(reg_path(cfg, who))
    if reg is None:
        return False, f"{who} is not registered; register first"
    reg.update(phase=k, note=note.replace("\n", " "), phaseAt=time.time())
    write_json(reg_path(cfg, who), reg)
    return True, k


def done(cfg, who):
    try:
        os.remove(reg_path(cfg, who))
        return True
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
