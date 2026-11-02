"""`admiral run`: a command run under locks, held for exactly as long as it runs and stopped whole.

    admiral run --lock <name>[|<name>]... [--lock ...]... [--port] --who "<session> <task>" [--limit <minutes>]
                [--priority <n>] [--ready "<check>" [--ready-timeout <seconds>]] [--log <file>] -- <command>...
    admiral run stop --lock <the lock it holds>

Each --lock is taken (all of them); `--lock 'pg-1|pg-2'` (quoted: | is the shell's) takes whichever of those comes
free first, and is then the run's only --lock (waiting on a choice while holding another lock could deadlock two
runs). The command, and the --ready check, get the locks taken as $ADMIRAL_LOCK (the first) and $ADMIRAL_LOCKS (all,
space-separated). --priority places it in each lock's line as `admiral lock acquire --priority` does. `admiral run
stop` names a lock the run actually holds (pg-1, not pg-1|pg-2), as `admiral lock status` and the ready line show it.

It waits its turn for each lock (`admiral lock acquire --wait`), with --port also claims a free port (given to the
command as $PORT), starts the command in a process group of its own, records the command's pid on every lock, and
when the command ends, its time limit is up (`--limit`, 180 minutes by default) or it is told to stop, stops the whole
group (TERM, then KILL after a grace period), then releases the locks. Without --ready it stays in the foreground and
exits with the command's code (124 at the time limit). With --ready it runs the command as a service: it returns once
the check succeeds and leaves a supervisor holding the service and its locks in the background, until `admiral run
stop` or the limit.

A process that leaves the group (a daemon, as `pg_ctl start` starts one) is still stopped when it was seen as a
descendant of the command; the group cannot hold it, so one that left before it was seen is not, and a port still
listened on afterwards is reported. Run services in the foreground (`postgres -D`, not `pg_ctl start`).

Every process is known by its pid and its start time, so a pid used again by another process is never signalled.
The command is not collected until everything is stopped: until then its pid, and its group's, stay its own, and
its locks do not look abandoned. Each run holds its locks under its own name (`<who> [run <id>]`), so two runs given
the same --who never release each other's.
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

from . import sessions

GRACE = 10  # seconds between asking a group to stop and killing it
LIMIT = 180  # minutes, by default: the locks' own default ttl
LOOK = 0.5  # seconds between looks at the command and its descendants
EARLY, EARLY_LOOK = 5, 0.05  # its first seconds, looked at more often: a daemon leaves its group as it starts
PORT_TRIES = 20


# ---- the lock tool -------------------------------------------------------------------------------------------------

def lock_tool(cfg, *args, stopped=lambda: False):
    """`admiral lock <args>`, its output captured; ended (and failed) once `stopped()` says so, as a wait in a lock's
    line may be long."""
    env = dict(os.environ, ADMIRAL_LOCKS_DIR=cfg.locks_dir, ADMIRAL_LOCK_COMMANDERS=cfg.lock_commanders)
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lock.sh")
    p = subprocess.Popen(["/bin/bash", script, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         env=env, stdin=subprocess.DEVNULL)
    cut = False
    while True:
        try:
            out, err = p.communicate(timeout=0.05)  # read all the while: a long wait says a lot, and a full pipe
            break                                   # would stop it
        except subprocess.TimeoutExpired:
            if stopped() and not cut:
                p.terminate()  # its own trap leaves the line
                cut = True
    return subprocess.CompletedProcess(p.args, 1 if cut else p.returncode, out, err)


def owner(cfg, name):
    try:
        with open(os.path.join(cfg.locks_dir, name, "owner")) as fh:
            return dict(line.rstrip("\n").split("=", 1) for line in fh if "=" in line)
    except OSError:
        return {}


def groups(locks):
    """Each --lock as the names it may be (`pg-1|pg-2`: either), in the order they are taken: by their names, so two
    runs needing the same locks never hold one each while waiting for the other."""
    out = []
    for given in locks:
        names = list(dict.fromkeys(n.strip() for n in given.split("|") if n.strip()))
        if names and names not in out:
            out.append(names)
    return sorted(out, key=sorted)


def take_any(cfg, names, who, ttl, prio, stopped):
    """Whichever of `names` comes free first, as the lock tool's own loop over several locks under one --who takes
    it: in line at each, polling, and out of the other lines once one is held. (the name, error or "")."""
    me, shown = str(os.getpid()), ""

    def leave():
        """Out of every line; the lock it may have taken just now, for the caller to let go."""
        for name in names:
            lock_tool(cfg, "leave", name, "--who", who)
        held = [n for n in names if owner(cfg, n).get("who") == who and owner(cfg, n).get("pid") == me]
        return held[0] if held else None
    while True:
        for name in names:
            r = lock_tool(cfg, "acquire", name, "--who", who, "--pid", me, "--ttl", str(ttl), *prio)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if not line.startswith("acquired"):
                        say(line)
                return name, ""
            if r.returncode != 1:  # cut short or failed: out of every line, keeping only what it holds
                return leave(), f"could not take {name}: {(r.stderr or r.stdout).strip()[-300:]}"
        line = "waiting for any of " + ", ".join(names)
        if line != shown:
            say(line)
            shown = line
        end = time.monotonic() + 3
        while time.monotonic() < end:
            if stopped():
                return leave(), "stopped while waiting for the locks"
            time.sleep(0.1)


def take_locks(cfg, locks, who, port, ttl, stopped, priority=None):
    """(locks held, the port or None, error or "")."""
    held, me = [], str(os.getpid())
    prio = ["--priority", str(priority)] if priority is not None else []
    for names in groups(locks):
        if len(names) > 1:
            name, err = take_any(cfg, names, who, ttl, prio, stopped)
            held += [name] if name else []
            if err:
                return held, None, err
            continue
        name = names[0]
        r = lock_tool(cfg, "acquire", name, "--who", who, "--wait", "--pid", me, "--ttl", str(ttl), *prio,
                      stopped=stopped)
        for line in r.stdout.splitlines():
            if not line.startswith("acquired"):
                say(line)
        mine = owner(cfg, name)
        if r.returncode != 0:
            if mine.get("who") == who and mine.get("pid") == me:  # taken just as the wait was cut
                held.append(name)
            return held, None, ("stopped while waiting for the locks" if stopped()
                                else f"could not take {name}: {(r.stderr or r.stdout).strip()[-300:]}")
        held.append(name)
    got, start = None, 8100
    for _ in range(PORT_TRIES if port else 0):
        r = lock_tool(cfg, "port", "--who", who, "--pid", me, "--ttl", str(ttl), "--from", str(start))
        if r.returncode != 0 or not r.stdout.strip().isdigit():
            return held, None, f"no port: {(r.stderr or r.stdout).strip()[-300:]}"
        candidate = int(r.stdout.strip())
        held.append(f"port-{candidate}")
        if bindable(candidate):  # the lock tool asks lsof, which may be missing
            got = candidate
            break
        release(cfg, [held.pop()], who, {me})
        start = candidate + 1
    if port and got is None:
        return held, None, "no free port"
    return held, got, ""


def release(cfg, held, who, pids):
    """Release the locks this run still holds: under its own name and with one of its pids, so a lock taken over
    meanwhile is left to its new holder."""
    for name in held:
        mine = owner(cfg, name)
        if mine.get("who") != who or mine.get("pid") not in pids:
            continue
        r = lock_tool(cfg, "release", name, "--who", who)
        if r.returncode != 0:
            say(f"could not release {name}: {(r.stderr or r.stdout).strip()}")


def bindable(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def listener(port):
    """What listens on the port after the stop, or '': 'pid command' where lsof can tell, else a plain yes."""
    if shutil.which("lsof"):
        r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True)
        pids = [int(p) for p in r.stdout.split() if p.isdigit()]
        return "; ".join(describe(pids)) if pids else ""
    try:
        socket.create_connection(("127.0.0.1", port), 1).close()
        return "a process lsof is not here to name"
    except OSError:
        return ""


# ---- records -------------------------------------------------------------------------------------------------------

def runs_dir(cfg):
    return cfg.sub("runs")


def key(name):
    """A file name for a lock name: readable, and distinct for distinct names."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:60] + "-" + hashlib.sha1(name.encode()).hexdigest()[:10]


def put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def get(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def status_path(cfg, run_id):
    return os.path.join(runs_dir(cfg), f"run-{run_id}.json")


def holder_path(cfg, name):
    return os.path.join(runs_dir(cfg), f"lock-{key(name)}.json")


def remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def drop(cfg, rec):
    for name in rec.get("locks") or []:
        if (get(holder_path(cfg, name)) or {}).get("id") == rec["id"]:
            remove(holder_path(cfg, name))
    remove(status_path(cfg, rec["id"]))


# ---- processes -----------------------------------------------------------------------------------------------------

def start_of(pid):
    return (sessions.proc_starts([pid]).get(pid) or (None,))[0]


def table():
    """pid -> (ppid, pgid, state) of every process."""
    r = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid=,stat="], capture_output=True, text=True)
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 4 and all(p.isdigit() for p in parts[:3]):
            out[int(parts[0])] = (int(parts[1]), int(parts[2]), parts[3])
    return out


def running(procs, pid):
    """Whether `pid` runs, in a process table: a zombie (exited, waiting to be collected) does not."""
    return pid in procs and not procs[pid][2].startswith("Z")


def alive(pid, start):
    """Whether `pid` runs and is the process that started at `start`."""
    return bool(pid) and start is not None and running(table(), pid) and start_of(pid) == start


def describe(pids):
    if not pids:
        return []
    r = subprocess.run(["ps", "-o", "pid=,command=", "-p", ",".join(map(str, pids))], capture_output=True, text=True)
    return [line.strip()[:160] for line in r.stdout.splitlines() if line.strip()]


class Seen:
    """The command's descendants seen so far, each with its start time: a pid used again since by another process is
    neither stopped nor followed to its children."""

    def __init__(self, root, root_start, known=()):
        self.known = {root: root_start, **{int(p): s for p, s in known}}
        self.same = set()

    def look(self):
        """Look for new descendants; returns the process table it read."""
        procs = table()
        now = sessions.proc_starts([p for p in self.known if p in procs])
        same = {p for p, s in self.known.items() if (now.get(p) or (None,))[0] == s}
        mine, new, grew = set(same), [], True
        while grew:  # a child seen now may have children of its own already
            grew = False
            for pid, (ppid, _, _) in procs.items():
                if ppid in mine and pid not in mine and pid not in self.known:
                    mine.add(pid)
                    new.append(pid)
                    grew = True
        found = sessions.proc_starts(new) if new else {}
        for pid, (start, _) in found.items():
            self.known[pid] = start
        self.same = same | set(found)
        return procs

    def outside(self, pgid, procs):
        """(pid, start) of the descendants that run outside the group and are still the processes seen."""
        return [(p, self.known[p]) for p in self.same if running(procs, p) and procs[p][1] != pgid]


def members(pgid, procs):
    return [p for p, (_, g, _) in procs.items() if g == pgid and running(procs, p)]


def signal_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):  # macOS: a group of zombies only refuses with EPERM
        pass


def signal_one(pid, sig):
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def stop_all(pgid, seen, grace=GRACE, after_kill=5):
    """Stop the group (None: no group, only the processes seen) and the descendants seen outside it, looking again
    all the while, as one may leave the group as it is told to stop: TERM, then KILL whatever is left after `grace`
    seconds. The group's leader must not have been collected yet, so its id is still this group's.
    Returns (the descendants stopped outside the group, the pids still running after KILL)."""
    procs = seen.look()
    told, out, killed = set(), {}, None

    def left(procs):
        return (members(pgid, procs) if pgid else []) + [p for p, _ in seen.outside(pgid, procs)]
    if pgid:
        signal_group(pgid, signal.SIGTERM)
    end = time.monotonic() + grace
    while left(procs):
        sig = signal.SIGTERM if killed is None else signal.SIGKILL
        for pid, _ in seen.outside(pgid, procs):
            if (pid, sig) not in told:
                if pgid:
                    out.setdefault(pid, (describe([pid]) or [str(pid)])[0])
                signal_one(pid, sig)
                told.add((pid, sig))
        if killed is None and time.monotonic() >= end:
            killed = time.monotonic()
            if pgid:
                signal_group(pgid, signal.SIGKILL)
            continue
        if killed is not None and time.monotonic() - killed >= after_kill:
            break
        time.sleep(0.1)
        procs = seen.look()
    return list(out.values()), left(procs)


def say(msg):
    print(f"admiral run: {msg}", file=sys.stderr, flush=True)


# ---- a run ---------------------------------------------------------------------------------------------------------

def supervise(cfg, a, run_id):
    """Take the locks, run the command, stop it whole, release them. Returns the exit code."""
    ttl = int(a.limit + GRACE / 60 + 5)  # a holder that outlives its limit by this much is gone
    who, me = f"{a.who} [run {run_id}]", os.getpid()
    stop = {"why": ""}

    def on_signal(sig, _):
        stop["why"] = stop["why"] or f"stopped ({signal.Signals(sig).name})"
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, on_signal)
    rec = {"id": run_id, "supervisor": me, "supervisorStart": start_of(me), "who": who, "locks": [],
           "command": a.command, "limit": a.limit, "phase": "waiting"}
    writing = threading.Lock()

    def save(**fields):
        with writing:
            rec.update(fields)
            put(status_path(cfg, run_id), rec)
    save()
    held, child, pids = [], None, {str(me)}
    try:
        held, port, err = take_locks(cfg, a.lock, who, a.port, ttl, stopped=lambda: bool(stop["why"]),
                                     priority=a.priority)
        save(locks=held)
        if err or stop["why"]:
            say(err or stop["why"])
            return 1
        chosen = [n for n in held if not (port and n == f"port-{port}")]
        env = dict(os.environ, ADMIRAL_LOCK=chosen[0], ADMIRAL_LOCKS=" ".join(chosen),
                   **({"PORT": str(port)} if port else {}))
        try:
            child = subprocess.Popen(a.command, start_new_session=True, env=env, stdin=subprocess.DEVNULL)
        except OSError as e:
            say(f"could not start {a.command[0]}: {e}")
            return 127
        pgid, began = child.pid, time.monotonic()
        seen = Seen(child.pid, start_of(child.pid))
        seen.look()  # before anything slower: a daemon leaves within a tenth of a second
        pids.add(str(child.pid))

        def record():  # beside the looks, which must not wait on it
            for name in held:
                lock_tool(cfg, "attach", name, "--who", who, "--pid", str(child.pid))
            save(phase="running", pid=child.pid, pidStart=seen.known[child.pid], pgid=pgid, port=port, chosen=chosen)
            for name in held:
                put(holder_path(cfg, name), {"id": run_id})
        recording = threading.Thread(target=record)
        recording.start()
        deadline, code, why, escaped = began + a.limit * 60, None, "", []
        while True:
            procs = seen.look()
            now_out = sorted(seen.outside(pgid, procs))
            if now_out != escaped:  # kept, so a stop without this supervisor can still find them
                escaped = now_out
                save(escaped=escaped)
            if not running(procs, child.pid):  # exited, and left uncollected: its pid and group stay its own
                break
            if stop["why"]:
                why = stop["why"]
                break
            if time.monotonic() >= deadline:
                why = f"time limit of {a.limit:g} minutes reached"
                break
            time.sleep(EARLY_LOOK if time.monotonic() - began < EARLY else LOOK)
        recording.join()
        if why:
            say(f"{why}: stopping {' '.join(a.command)[:120]} and everything it started")
        outside, survivors = stop_all(pgid, seen)
        if outside:
            say("stopped what had left its process group: " + "; ".join(outside))
        for name in held:  # held by this process while the command is collected and its pid set free
            lock_tool(cfg, "attach", name, "--who", who, "--pid", str(me))
        if survivors:  # what will not die still uses the resource: the locks stay held until all of it has ended
            say(f"could not stop {'; '.join(describe(survivors))}; holding {', '.join(held)} until they end (stop "
                "this again to leave the locks to them)")
            stop["why"] = ""  # a stop from now on means: wait no longer
            while survivors and not stop["why"]:
                time.sleep(1)
                procs = seen.look()
                survivors = [p for p in survivors if p in seen.same and running(procs, p)]
            if survivors:
                for name in held:
                    lock_tool(cfg, "attach", name, "--who", who, "--pid", str(survivors[0]))
                say(f"left {', '.join(held)} to pid {survivors[0]}, which still runs: they are free once it ends")
                held = []
        try:
            code = child.wait(timeout=None if child.pid not in survivors else 1)
        except subprocess.TimeoutExpired:  # the command itself would not die
            say("ended without the command, which still runs")
            return 1
        if why.startswith("time limit"):
            code = 124
        elif code < 0:
            code = 128 - code
        if port:
            still = listener(port)
            if still:
                say(f"port {port} is still listened on after the stop, by {still}: a process it started left "
                    "before it was seen; run services in the foreground (postgres -D, not pg_ctl start)")
        if a.ready:
            say(f"ended with exit {code}")
        return code
    finally:
        if child is not None and child.returncode is None:  # an error on the way: stop it before letting go
            stop_all(child.pid, Seen(child.pid, start_of(child.pid)))
            child.wait()
        drop(cfg, rec)  # while the locks are still this run's, so a next holder's records are never removed
        release(cfg, held, who, pids)


def check(command, env, timeout, cut):
    """Run the readiness check in a group of its own; whether it succeeded within `timeout` seconds and before
    `cut()`. Whatever it started is stopped with it, its leader collected only after, so the group is still its."""
    p = subprocess.Popen(command, shell=True, env=env, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end, done = time.monotonic() + max(timeout, 0.1), False
    while time.monotonic() < end and not cut():
        if not running(table(), p.pid):
            done = True
            break
        time.sleep(0.1)
    signal_group(p.pid, signal.SIGKILL)
    code = p.wait()
    return done and code == 0 and not cut()


def serve(cfg, a, argv):
    """Start a detached supervisor, wait for the check to pass, and return, leaving the service running. Cut short
    (Ctrl-C, a signal, not ready in time, an error), it stops that supervisor and everything it holds."""
    run_id = uuid.uuid4().hex[:8]
    log = a.log or os.path.join(runs_dir(cfg), f"{key(a.lock[0])}.log")
    os.makedirs(os.path.dirname(os.path.abspath(log)), exist_ok=True)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([here] + [p for p in [os.environ.get("PYTHONPATH")] if p]))
    cut = {"why": ""}

    def on_signal(sig, _):
        cut["why"] = cut["why"] or f"stopped ({signal.Signals(sig).name})"
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, on_signal)
    with open(log, "ab") as fh:
        sup = subprocess.Popen([sys.executable, "-m", "admiral", "run", "--supervise", run_id, *argv],
                               start_new_session=True, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                               env=env)
    ready, began, said, asked = False, None, False, time.monotonic()
    try:
        while not cut["why"]:
            time.sleep(LOOK)
            if sup.poll() is not None:
                say(f"the service ended before it was ready; its output, {log}, ends:\n" + tail(log))
                return 1
            rec = get(status_path(cfg, run_id)) or {}
            if rec.get("phase") != "running":
                if rec.get("phase") == "waiting" and not said and time.monotonic() - asked > 2:
                    say(f"waiting for {', '.join(a.lock)}")
                    said = True
                continue
            began = began or time.monotonic()
            left = a.ready_timeout - (time.monotonic() - began)
            if left <= 0:
                say(f"not ready after {a.ready_timeout:g} seconds; stopping it. Its output: {log}")
                return 1
            chosen = rec.get("chosen") or []
            env = dict(os.environ, ADMIRAL_LOCK=chosen[0] if chosen else "", ADMIRAL_LOCKS=" ".join(chosen),
                       **({"PORT": str(rec["port"])} if rec.get("port") else {}))
            ok = check(a.ready, env, left, lambda: bool(cut["why"]))
            now = get(status_path(cfg, run_id)) or {}
            ok = ok and sup.poll() is None and now.get("phase") == "running" and now.get("pid") == rec.get("pid") \
                and alive(rec.get("pid"), rec.get("pidStart"))
            if ok and not cut["why"]:
                port = f" on port {rec['port']}" if rec.get("port") else ""
                stop_with = f"admiral run stop --lock {shlex.quote(rec['locks'][0])}"
                print(f"ready{port}: pid {rec['pid']}, holding {', '.join(rec['locks'])}; output in {log}; stop it "
                      f"with `{stop_with}` (it stops by itself after {a.limit:g} minutes)")
                ready = True
                return 0
        say(f"{cut['why']} before it was ready; stopping it")
        return 130
    finally:
        if not ready and sup.poll() is None:
            sup.terminate()
            try:
                sup.wait(timeout=GRACE + 20)
            except subprocess.TimeoutExpired:
                held = ((get(status_path(cfg, run_id)) or {}).get("locks") or [])[:1]
                say(f"its supervisor (pid {sup.pid}) did not stop; "
                    + (f"`admiral run stop --lock {shlex.quote(held[0])}`" if held else f"stop it: kill {sup.pid}"))


def tail(path, lines=15):
    try:
        with open(path, errors="replace") as fh:
            return "".join(fh.readlines()[-lines:])
    except OSError:
        return ""


def stop_run(cfg, name):
    """Stop the run holding `name`: its supervisor stops the command and releases the locks. With the supervisor
    gone, this does it, as far as it can tell the processes are still the run's own."""
    if "|" in name:  # each may be held by a run of its own
        held = [f"{n} ({(get(status_path(cfg, (get(holder_path(cfg, n)) or {}).get('id', '-'))) or {}).get('who')})"
                for n in name.split("|") if get(holder_path(cfg, n))]
        return False, ("name the lock the run holds, one of: " + "; ".join(held) if held
                       else f"no run holds any of {name}")
    rec = get(status_path(cfg, (get(holder_path(cfg, name)) or {}).get("id", "-")))
    if not rec:
        return False, f"no run holds {name}"
    locks = ", ".join(rec["locks"])
    if alive(rec["supervisor"], rec.get("supervisorStart")):
        os.kill(rec["supervisor"], signal.SIGTERM)
        end = time.monotonic() + GRACE + 20
        while time.monotonic() < end and alive(rec["supervisor"], rec.get("supervisorStart")):
            time.sleep(0.2)
        if alive(rec["supervisor"], rec.get("supervisorStart")):
            return False, f"the run holding {locks} did not stop (supervisor pid {rec['supervisor']})"
        if get(status_path(cfg, rec["id"])) is None:  # it finished its cleanup, which removes the record last
            kept = [(n, owner(cfg, n).get("pid")) for n in rec["locks"] if owner(cfg, n).get("who") == rec["who"]]
            if kept:
                return False, ("stopped, but " + ", ".join(f"{n} (pid {p})" for n, p in kept) + " stay held by "
                               "processes that would not die")
            return True, f"stopped the run holding {locks}"
        rec = get(status_path(cfg, rec["id"])) or rec  # it died mid-way: clean up after it below
    # its supervisor was killed outright: the command, collected by the system since, may still run
    pids, me = {str(rec["supervisor"])} | ({str(rec["pid"])} if rec.get("pid") else set()), str(os.getpid())
    command_runs = bool(rec.get("pid")) and alive(rec["pid"], rec.get("pidStart"))
    if not command_runs and rec.get("pgid") and members(rec["pgid"], table()):
        return False, (f"its supervisor and command are gone, but process group {rec['pgid']} still runs; it may "
                       f"since be another's, so it is left alone, and so are {locks}. Look with `ps -g {rec['pgid']}`,"
                       " stop what is the run's, then `admiral lock release`")
    mine = [n for n in rec["locks"] if owner(cfg, n).get("who") == rec["who"] and owner(cfg, n).get("pid") in pids]
    for name in mine:  # held by this process while it stops them, so they never look abandoned meanwhile
        lock_tool(cfg, "attach", name, "--who", rec["who"], "--pid", me)
    escaped = rec.get("escaped") or []
    if command_runs:
        seen = Seen(rec["pid"], rec["pidStart"], escaped)
        group = rec["pgid"]
    else:  # only what had left the group, known by pid and start time
        seen = Seen(escaped[0][0], escaped[0][1], escaped[1:]) if escaped else None
        group = None
    survivors = stop_all(group, seen)[1] if seen else []
    drop(cfg, rec)
    if survivors:
        for name in mine:
            lock_tool(cfg, "attach", name, "--who", rec["who"], "--pid", str(survivors[0]))
        return False, (f"could not stop {'; '.join(describe(survivors))}; {', '.join(mine)} stay held by pid "
                       f"{survivors[0]} until it ends")
    release(cfg, mine, rec["who"], {me})
    return True, f"stopped the run holding {locks} (its supervisor was gone)"


def main(cfg, argv):
    if argv[:1] == ["stop"]:
        ap = argparse.ArgumentParser(prog="admiral run stop")
        ap.add_argument("--lock", required=True)
        a = ap.parse_args(argv[1:])
        ok, msg = stop_run(cfg, a.lock)
        print(msg, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    run_id = argv[1] if argv[:1] == ["--supervise"] and len(argv) > 1 else ""
    args = argv[2:] if run_id else argv
    ap = argparse.ArgumentParser(prog="admiral run", description=__doc__.split("\n\n")[0])
    ap.add_argument("--lock", action="append", default=[],
                    help="a lock to hold while it runs (repeatable: all of them); 'a|b', quoted: whichever comes "
                         "free first")
    ap.add_argument("--priority", type=int, default=None,
                    help="its place in each lock's line, as for admiral lock acquire (higher first; default 0)")
    ap.add_argument("--port", action="store_true", help="also claim a free port, given to the command as $PORT")
    ap.add_argument("--who", required=True, help='"<session> <task>", as for admiral lock')
    ap.add_argument("--limit", type=float, default=LIMIT, help=f"minutes before it is stopped (default {LIMIT})")
    ap.add_argument("--ready", default="", help="a check run until it succeeds; then return, leaving it running")
    ap.add_argument("--ready-timeout", type=float, default=120, help="seconds to wait for --ready (default 120)")
    ap.add_argument("--log", default="", help="with --ready, where its output goes")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args(args)
    if a.command[:1] == ["--"]:
        a.command = a.command[1:]
    if not a.command:
        ap.error("the command to run goes after --")
    if not a.lock:
        ap.error("--lock is required: the name the run is held and stopped by")
    if a.limit <= 0:
        ap.error("--limit is a number of minutes above 0")
    if a.priority is not None and not -99 <= a.priority <= 99:
        ap.error("--priority is an integer from -99 to 99")
    if not all(n.strip() for given in a.lock for n in given.split("|")):
        ap.error("--lock names a lock, or several as a|b")
    if len(groups(a.lock)) > 1 and any(len(g) > 1 for g in groups(a.lock)):
        # waiting on a choice while holding another lock, two runs could each hold what the other waits for
        ap.error("a choice of locks (a|b) is taken on its own: give it no other --lock")
    if a.ready and not run_id:
        return serve(cfg, a, args)
    return supervise(cfg, a, run_id or uuid.uuid4().hex[:8])
