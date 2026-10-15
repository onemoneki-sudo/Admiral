"""PRs and checks, read with the GitHub CLI (`gh`) in the configured repository.

Four `gh` calls a refresh: open PRs with their checks, the state of recent PRs (asking checks for every state in one
call is heavy enough that GitHub answers 502), and the person's own open PRs and those merged today. The recent-PR
list pages in hundreds, so a refresh makes up to about six API requests. A list that comes back full may have left
out a branch's PR: in a repository with more PRs than the lists hold, the branches left out are asked for by name, one
more call. While every session is quiet, GitHub is asked only every
`quiet_github_minutes` and the last answer is reused in between (<state_dir>/pr-cache.json). A merge is final, so the
cache also keeps the merged PRs it has seen, for branches still in use: a deliverable merged days ago still counts after
it falls out of the recent list.
"""

import json
import subprocess
import time

from .registry import read_json, write_json

OPEN_LIMIT = 100  # open PRs asked with their checks
RECENT_LIMIT = 300  # PRs of every state asked, newest first
MERGED_KEPT = 500  # merged PRs remembered past the recent list, the newest
LOOKUP_CHUNK = 50  # branches asked for by name in one call


def gh_prs(cfg, state, limit, fields):
    r = subprocess.run(["gh", "pr", "list", "--state", state, "--limit", str(limit), "--json", fields],
                       capture_output=True, text=True, cwd=cfg.repo_dir)
    return json.loads(r.stdout) if r.returncode == 0 else None


def prs_by_branch(cfg, branches):
    """branch -> its PR (an open one wins, else the newest); None when gh failed."""
    if not branches or not cfg.repo_dir:
        return {}
    open_prs = gh_prs(cfg, "open", OPEN_LIMIT, "number,headRefName,state,isDraft,reviewDecision,statusCheckRollup")
    all_prs = gh_prs(cfg, "all", RECENT_LIMIT, "number,headRefName,state,isDraft")
    if open_prs is None or all_prs is None:
        return None
    out = {pr["headRefName"]: pr for pr in open_prs if pr["headRefName"] in branches}
    full = len(open_prs) >= OPEN_LIMIT

    def past(pr):
        # an open PR found past the open list, when it was full, never had its checks asked for (with room left, it
        # opened between the calls, and the next refresh has them)
        return dict(pr, checksUnknown=True) if pr["state"] == "OPEN" and full else pr

    for pr in all_prs:  # newest first
        if pr["headRefName"] in branches and pr["headRefName"] not in out:
            out[pr["headRefName"]] = past(pr)
    left = sorted(set(branches) - set(out))
    if left and len(all_prs) >= RECENT_LIMIT:  # the list of every state is full: it may have left a branch's PR out
        found = by_name(cfg, left)
        if found is None:
            return None  # "no PR" cannot be told from "not listed"
        out.update({b: past(pr) for b, pr in found.items()})
    return out


def by_name(cfg, branches):
    """branch -> its PR, asked for by branch name (an open one wins, else the newest), one call per LOOKUP_CHUNK
    branches; a branch with no PR is left out. None when gh failed."""
    out = {}
    for i in range(0, len(branches), LOOKUP_CHUNK):
        chunk = branches[i:i + LOOKUP_CHUNK]
        heads = "".join(f", $b{k}: String!" for k in range(len(chunk)))
        asks = " ".join(f"b{k}: pullRequests(headRefName: $b{k}, first: 5, orderBy: {{field: CREATED_AT, "
                        "direction: DESC}) { nodes { number headRefName state isDraft } }" for k in range(len(chunk)))
        query = f"query($owner: String!, $name: String!{heads}) {{ repository(owner: $owner, name: $name) {{ {asks} }} }}"
        args = ["gh", "api", "graphql", "-F", "owner={owner}", "-F", "name={repo}", "-f", f"query={query}"]
        r = subprocess.run(args + [a for k, b in enumerate(chunk) for a in ("-f", f"b{k}={b}")],
                           capture_output=True, text=True, cwd=cfg.repo_dir)
        try:
            repo = json.loads(r.stdout)["data"]["repository"] if r.returncode == 0 else None
        except (ValueError, KeyError, TypeError):
            repo = None
        if not isinstance(repo, dict):
            return None
        for k, b in enumerate(chunk):
            nodes = [n for n in ((repo.get(f"b{k}") or {}).get("nodes") or []) if n]
            if nodes:
                out[b] = next((n for n in nodes if n.get("state") == "OPEN"), nodes[0])
    return out


def my_prs(cfg, now):
    """The PRs the person running `gh` authored, as GitHub has them: open ones (number, branch) and those merged
    today. None when gh failed or no repository is configured."""
    if not cfg.repo_dir:
        return None
    # GitHub reads a bare date as a UTC day: asked instead from the moment the person's day began, in UTC, which holds
    # on a day the clocks change too
    t = time.localtime(now)
    for hour in range(24):  # a day whose clocks jumped past midnight began at the first hour it had
        try:
            began = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, hour, 0, 0, 0, 0, -1))
            break
        except (OverflowError, ValueError):
            continue
    else:
        began = now
    since = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(began))
    calls = [["--state", "open"], ["--state", "merged", "--search", f"merged:>={since}"]]
    out = []
    for extra in calls:
        r = subprocess.run(["gh", "pr", "list", "--author", "@me", "--limit", "100", *extra,
                            "--json", "number,headRefName"], capture_output=True, text=True, cwd=cfg.repo_dir)
        if r.returncode:
            return None
        out.append(json.loads(r.stdout))
    return {"open": out[0], "mergedToday": out[1]}


def prs_paced(cfg, branches, quiet, now, fetch=prs_by_branch, fetch_mine=my_prs):
    """(prs or None when gh failed, the person's own PRs or None, whether the answer is a reused one)."""
    path = cfg.sub("pr-cache.json")
    cache = read_json(path) or {}
    if quiet and now - cache.get("at", 0) < cfg.quiet_github_s and set(branches) <= set(cache.get("branches", [])) \
            and cache.get("mine") is not None:
        return {b: p for b, p in cache["prs"].items() if b in branches}, cache["mine"], True
    prs = fetch(cfg, branches)
    mine = fetch_mine(cfg, now) if prs is not None else None
    if prs is not None:  # what GitHub answers now wins; a merge seen before fills in what it no longer lists
        # a cache written before the memory existed has none yet: its last answer's merges start it, once
        seen = cache["merged"] if "merged" in cache else \
            {b: p for b, p in (cache.get("prs") or {}).items() if p.get("state") == "MERGED"}
        prs = {**{b: p for b, p in seen.items() if b in branches}, **prs}
        kept = sorted(((b, p) for b, p in prs.items() if p["state"] == "MERGED"), key=lambda bp: -bp[1]["number"])
        write_json(path, {"at": now, "branches": sorted(branches), "prs": prs, "mine": mine,
                          "merged": dict(kept[:MERGED_KEPT])})
    return prs, mine, False


def pick(branches, prs):
    """The PR that speaks for a set of branches: an open one first (the newest), else merged, else closed."""
    found = [prs[b] for b in branches if b in prs]
    for state in ("OPEN", "MERGED", "CLOSED"):
        hit = [p for p in found if p["state"] == state]
        if hit:
            return max(hit, key=lambda p: p["number"])
    return None


def ci(pr, summary=()):
    """(failing job names or state, level: ok, run, fail or none). Summary jobs (config `[github] summary_checks`, jobs
    that only fail because another did) are named only
    when nothing else failed."""
    checks = (pr or {}).get("statusCheckRollup") or []
    if not pr or pr["state"] != "OPEN" or not checks:
        return "", "none"

    def named(conclusions):
        hit = [c.get("name", "?") for c in checks if c.get("conclusion") in conclusions]
        return [n for n in hit if n not in summary] or hit

    bad = named(("FAILURE", "TIMED_OUT"))
    if bad:
        return ", ".join(bad[:2]), "fail"
    if any(c.get("status") not in (None, "COMPLETED") for c in checks):
        return "", "run"
    if named(("CANCELLED",)):
        return "", "none"
    return "", "ok"


LABELS = {
    "en": {"OPEN": "open", "MERGED": "merged", "CLOSED": "closed", "draft": "draft", "APPROVED": "approved",
           "CHANGES_REQUESTED": "changes requested", "review": "in review"},
    "zh": {"OPEN": "开", "MERGED": "已合并", "CLOSED": "已关", "draft": "草稿", "APPROVED": "已批",
           "CHANGES_REQUESTED": "要改", "review": "待审"},
}


def pr_label(pr, language):
    if pr is None:
        return None
    L = LABELS.get(language, LABELS["en"])
    state = L.get(pr["state"], pr["state"])
    if pr["state"] == "OPEN":
        state = L["draft"] if pr.get("isDraft") else L.get(pr.get("reviewDecision") or "", L["review"])
    return {"number": pr["number"], "state": pr["state"], "label": f"#{pr['number']} {state}"}
