"""`admiral lock stats`: how often each lock was waited for, and how long it was waited for and held.

    admiral lock stats [--days 30]

It reads the history the lock tool keeps of each take and release (admiral/lock.sh: `<locks dir>/.history/
<year>-<month>.log`, tab-separated time, take|release, lock (coded %25, %09, %0A), seconds, who), so that how many
slots a resource gets, and how its line is ordered, follow from how often its takers waited rather than a guess.

A take counts as waited when its taker was in line WAITED seconds or more: a free lock is taken at once, and a loop
that polls a busy one every few seconds should not count a single poll's delay. Port locks are one line (`port-*`).
Locks taken at most twice and never waited for (a run per service, each under a name of its own) are counted
together in one line.
"""

import argparse
import glob
import math
import os
import re
import time

WAITED = 10  # seconds in line from which a take counts as having waited
FEW = 2  # locks taken this often or less, never waited for, are counted together
BUSY = 10  # percent of the time: a lock held this much is shown however seldom it was taken
PORT = re.compile(r"^port-\d+$")
CODED = {"25": "%", "09": "\t", "0A": "\n"}  # how the lock tool writes a lock name into one field


def decoded(name):
    return re.sub(r"%(25|09|0A)", lambda m: CODED[m.group(1)], name)


def read(locks_dir):
    """(time, event, lock, seconds) of every record kept, in the order they were written."""
    out = []
    for path in sorted(glob.glob(os.path.join(locks_dir, ".history", "[0-9]*-[0-9]*.log"))):
        if not os.path.isfile(path):
            continue  # a pipe there would hold the reading up, perhaps for good
        try:  # lines end at a newline only: a carriage return in a who or a name is part of it
            with open(path, encoding="utf-8", errors="replace", newline="\n") as fh:
                for line in fh:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 4 or not parts[0].isdigit() or not parts[3].isdigit():
                        continue  # a line cut short, or written by something else: not a record
                    if parts[1] in ("take", "release"):
                        name = decoded(parts[2])
                        out.append((int(parts[0]), parts[1], "port-*" if PORT.fullmatch(name) else name,
                                    int(parts[3])))
        except OSError:
            continue
    return out


def held_now(locks_dir):
    """{lock: when its holder took it} for every lock held now, by the name its directory has: a hold still going is
    part of how busy a lock was, though its take be older than the history kept, or never written."""
    out = {}
    for owner in glob.glob(os.path.join(glob.escape(locks_dir), "*", "owner")):
        lock = os.path.basename(os.path.dirname(owner))
        try:
            with open(owner) as fh:
                since = dict(line.rstrip("\n").split("=", 1) for line in fh if "=" in line).get("since", "")
        except (OSError, ValueError):
            continue
        if since.isdigit() and not PORT.fullmatch(lock):
            out[lock] = int(since)
    return out


def shown(name):
    """A name as one cell, told apart from every other: one with a control character or a backslash, escaped."""
    return name if name.isprintable() and "\\" not in name else repr(name)[1:-1]


def rank(values, share):
    """The nearest-rank percentile: the smallest value with at least `share` of them at or below it."""
    values = sorted(values)
    return values[max(0, math.ceil(share * len(values)) - 1)]


def span(seconds):
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{round(seconds / 60)}m"
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"


def table(records, start, now, locks_dir):
    """(rows, the number of the few, the number of takes) over the records from `start` to `now`.

    Waits and holds count by when they were recorded; how busy a lock was counts the part of each hold that falls
    between `start` and `now`, the one going on now included, so a hold begun before `start` or not yet released
    is neither counted whole nor left out."""
    takes, holds, busy = {}, {}, {}
    within = lambda a, b: max(0, min(b, now) - max(a, start))  # of [a, b], the seconds between start and now
    for t, event, lock, seconds in records:
        if t < start:
            continue
        takes.setdefault(lock, [])
        if event == "take":
            takes[lock].append(seconds)
        else:
            holds.setdefault(lock, []).append(seconds)
            busy[lock] = busy.get(lock, 0) + within(t - seconds, t)
    holding = held_now(locks_dir)
    for lock, since in holding.items():  # taken before start, perhaps, and held all along
        takes.setdefault(lock, [])
        busy[lock] = busy.get(lock, 0) + within(since, now)
    covered = max(1, now - start)
    rows, few = [], 0
    for lock in takes:
        waits = [w for w in takes[lock] if w >= WAITED]
        share = 100 * min(busy.get(lock, 0), covered) / covered
        if (lock != "port-*" and lock not in holding and not waits and len(takes[lock]) <= FEW
                and share < BUSY):
            few += 1
            continue
        held = holds.get(lock, [])
        rows.append((-sum(waits), -len(takes[lock]), lock, [
            shown(lock),
            str(len(takes[lock])),
            f"{round(100 * len(waits) / len(takes[lock]))}%" if takes[lock] else "-",
            span(rank(waits, 0.5)) if waits else "-",
            span(rank(waits, 0.9)) if waits else "-",
            span(max(waits)) if waits else "-",
            span(rank(held, 0.5)) if held else "-",
            span(rank(held, 0.9)) if held else "-",
            # ports held at once are many locks: their holds added up would say nothing
            f"{round(share)}%" if lock in busy and lock != "port-*" else "-",
        ]))
    rows.sort()
    return [r[3] for r in rows], few, sum(len(v) for v in takes.values())


def main(cfg, argv):
    ap = argparse.ArgumentParser(prog="admiral lock stats", description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=float, default=30, help="how far back to look (default 30)")
    a = ap.parse_args(argv)
    if not math.isfinite(a.days) or a.days <= 0:
        ap.error("--days is a number of days above 0")
    now = int(time.time())
    days = f"{a.days:g}"
    records = read(cfg.locks_dir)
    # from the days asked for, or from the first record where the history begins later
    start = min(now, max(now - int(min(a.days, 36600) * 86400), min((t for t, *_ in records), default=now)))
    rows, few, n = table(records, start, now, cfg.locks_dir)
    if not records or not (rows or few):  # locks held now, with nothing recorded, say nothing yet
        print(f"no lock taken in the last {days} days (each take and release is recorded from Admiral 0.2.22 on)")
        return 0
    begun = time.strftime("%Y-%m-%d %H:%M", time.localtime(start))
    print(f"each lock over the last {days} days (recorded from {begun} on): {n} takes")
    head = ["lock", "taken", "waited", "wait p50", "p90", "max", "held p50", "p90", "busy"]
    widths = [max(len(r[i]) for r in rows + [head]) for i in range(len(head))]
    for r in [head] + rows:
        print("  ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths))).rstrip())
    if few:
        print(f"and {few} more locks, each taken at most {FEW} times and never waited for")
    print(f"waited: the takes that were in line {WAITED} seconds or more; wait: how long those were in line")
    print("held: from take to release; busy: the share of the time recorded that it was held")
    return 0
