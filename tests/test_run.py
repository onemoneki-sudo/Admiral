"""`admiral run`, with real processes and the real lock tool, against a state directory of its own."""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # a zombie (exited, its parent not yet told) counts as gone
    r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(r.stdout.strip()) and not r.stdout.strip().startswith("Z")


def gone_soon(pid, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not alive(pid):
            return True
        time.sleep(0.1)
    return False


class Run(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.locks = os.path.join(self.root, "state", "locks")
        cfg = os.path.join(self.root, "config.toml")
        with open(cfg, "w") as fh:
            fh.write(f'state_dir = "{os.path.join(self.root, "state")}"\n')
        self.env = dict(os.environ, ADMIRAL_CONFIG=cfg, PYTHONPATH=ROOT)
        self.started = []

    def tearDown(self):
        for p in self.started:
            if p.poll() is None:
                p.kill()
            p.communicate()
        shutil.rmtree(self.root, ignore_errors=True)

    def admiral(self, *args, timeout=60):
        return subprocess.run([sys.executable, "-m", "admiral", *args], capture_output=True, text=True,
                              env=self.env, timeout=timeout)

    def background(self, *args):
        p = subprocess.Popen([sys.executable, "-m", "admiral", *args], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=self.env)
        self.started.append(p)
        return p

    def held(self):
        return sorted(os.listdir(self.locks)) if os.path.isdir(self.locks) else []

    def owner(self, name):
        try:
            with open(os.path.join(self.locks, name, "owner")) as fh:
                return dict(line.rstrip("\n").split("=", 1) for line in fh if "=" in line)
        except OSError:
            return {}

    def wait_for(self, check, seconds=10):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            got = check()
            if got:
                return got
            time.sleep(0.1)
        self.fail("timed out")

    def visible(self):
        return [n for n in self.held() if not n.startswith(".")]

    def test_the_command_runs_under_its_lock_with_its_own_pid_and_its_exit_code_passes(self):
        out = os.path.join(self.root, "seen")
        r = self.admiral("run", "--lock", "heavy", "--who", "s t", "--",
                         "sh", "-c", f'echo $$ > {out}.pid; sleep 1; cp {self.locks}/heavy/owner {out}; exit 3')
        self.assertEqual(r.returncode, 3, r.stderr)
        with open(out + ".pid") as fh:
            pid = fh.read().strip()
        with open(out) as fh:
            owner = dict(line.rstrip("\n").split("=", 1) for line in fh if "=" in line)
        self.assertEqual(owner["pid"], pid)  # the command's own pid, not the runner's
        self.assertRegex(owner["who"], r"^s t \[run [0-9a-f]{8}\]$")  # its own name: two runs never share one
        self.assertEqual(self.visible(), [])  # released once it ended

    def test_the_limit_stops_the_whole_group_and_releases(self):
        out = os.path.join(self.root, "child")
        start = time.monotonic()
        r = self.admiral("run", "--lock", "heavy", "--who", "s t", "--limit", "0.03", "--",
                         "sh", "-c", f"sleep 300 & echo $! > {out}; sleep 300")
        self.assertEqual(r.returncode, 124, r.stderr)
        self.assertIn("time limit", r.stderr)
        self.assertLess(time.monotonic() - start, 30)
        with open(out) as fh:
            grandchild = int(fh.read())
        self.assertTrue(gone_soon(grandchild), "the command's child was left running")
        self.assertEqual(self.visible(), [])

    def test_a_process_that_leaves_the_group_is_stopped_too(self):
        out = os.path.join(self.root, "daemon")
        # a daemon as `pg_ctl start` makes one: a child in a session of its own, its parent gone at once
        daemon = (f"import os, time\nif os.fork() == 0:\n    os.setsid()\n"
                  f"    open({out!r}, 'w').write(str(os.getpid()))\n"
                  "    time.sleep(300)\nelse:\n    time.sleep(0.2)\n")
        r = self.admiral("run", "--lock", "db", "--who", "s t", "--", sys.executable, "-c", daemon)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out) as fh:
            pid = int(fh.read())
        self.assertTrue(gone_soon(pid), "the daemon was left running")
        self.assertIn("left its process group", r.stderr)
        self.assertEqual(self.visible(), [])

    def test_a_service_returns_once_ready_and_stops_with_its_locks(self):
        server = "import http.server, os; http.server.HTTPServer(('127.0.0.1', int(os.environ['PORT'])), " \
                 "http.server.SimpleHTTPRequestHandler).serve_forever()"
        check = f"{sys.executable} -c \"import os, socket; socket.create_connection(('127.0.0.1', " \
                "int(os.environ['PORT'])), 1)\""
        r = self.admiral("run", "--lock", "web", "--port", "--who", "s t", "--limit", "5", "--ready", check,
                         "--", sys.executable, "-c", server)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ready on port", r.stdout)
        port = int(r.stdout.split("ready on port ")[1].split(":")[0])
        self.assertEqual(self.visible(), ["port-%d" % port, "web"])
        pid = int(self.owner("web")["pid"])
        self.assertEqual(self.owner(f"port-{port}")["pid"], str(pid))
        socket.create_connection(("127.0.0.1", port), 1).close()  # it serves after the run returned
        r = self.admiral("run", "stop", "--lock", "web")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(gone_soon(pid))
        self.assertEqual(self.visible(), [])
        self.assertNotEqual(self.admiral("run", "stop", "--lock", "web").returncode, 0)  # nothing to stop now

    def test_a_service_whose_supervisor_was_killed_is_still_stopped(self):
        import glob
        r = self.admiral("run", "--lock", "web", "--who", "s t", "--ready", "true", "--", "sleep", "600")
        self.assertEqual(r.returncode, 0, r.stderr)
        pid = int(self.owner("web")["pid"])
        (status,) = glob.glob(os.path.join(self.root, "state", "runs", "run-*.json"))
        with open(status) as fh:
            supervisor = json.load(fh)["supervisor"]
        os.kill(supervisor, 9)
        self.assertTrue(gone_soon(supervisor))
        self.assertTrue(alive(pid))  # the service runs on, its lock with it
        r = self.admiral("run", "stop", "--lock", "web")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("supervisor was gone", r.stdout)
        self.assertTrue(gone_soon(pid))
        self.assertEqual(self.visible(), [])

    def test_a_service_that_dies_before_ready_says_why_and_holds_nothing(self):
        r = self.admiral("run", "--lock", "web", "--who", "s t", "--ready", "false", "--",
                         "sh", "-c", "echo cannot start >&2; exit 1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot start", r.stderr)
        self.assertEqual(self.visible(), [])

    def test_a_run_stopped_while_waiting_leaves_the_line_and_the_holder_alone(self):
        self.assertEqual(self.admiral("lock", "acquire", "heavy", "--who", "s t").returncode, 0)  # the same --who
        p = self.background("run", "--lock", "heavy", "--who", "s t", "--", "true")
        line = os.path.join(self.locks, ".q.heavy")
        self.wait_for(lambda: os.path.isdir(line) and [f for f in os.listdir(line) if not f.startswith(".")])
        self.assertIsNone(p.poll())  # still in line
        self.assertNotEqual(self.admiral("run", "stop", "--lock", "heavy").returncode, 0)  # a waiter holds nothing
        p.terminate()
        p.wait(timeout=20)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.owner("heavy")["who"], "s t")  # the holder untouched, though it has the same --who
        line = os.path.join(self.locks, ".q.heavy")
        self.assertEqual([f for f in os.listdir(line) if not f.startswith(".")] if os.path.isdir(line) else [], [])

    def test_two_runs_of_one_lock_take_turns(self):
        out = os.path.join(self.root, "order")
        first = self.background("run", "--lock", "heavy", "--who", "s one", "--",
                                "sh", "-c", f"echo one-start >> {out}; sleep 2; echo one-end >> {out}")
        self.wait_for(lambda: os.path.exists(out))
        r = self.admiral("run", "--lock", "heavy", "--who", "s two", "--", "sh", "-c", f"echo two >> {out}")
        first.wait(timeout=20)
        self.assertEqual((first.returncode, r.returncode), (0, 0), r.stderr)
        with open(out) as fh:
            self.assertEqual(fh.read().split(), ["one-start", "one-end", "two"])

    def test_a_command_that_cannot_start_holds_nothing(self):
        r = self.admiral("run", "--lock", "heavy", "--who", "s t", "--", "/nonexistent/command")
        self.assertEqual(r.returncode, 127)
        self.assertIn("could not start", r.stderr)
        self.assertEqual(self.visible(), [])
        self.assertEqual(os.listdir(os.path.join(self.root, "state", "runs")), [])

    def test_a_check_that_hangs_is_held_to_the_ready_timeout(self):
        start = time.monotonic()
        r = self.admiral("run", "--lock", "web", "--who", "s t", "--ready", "sleep 600", "--ready-timeout", "2",
                         "--", "sleep", "600")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not ready after 2 seconds", r.stderr)
        self.assertLess(time.monotonic() - start, 30)
        self.wait_for(lambda: self.visible() == [] or None)

    def test_lock_names_alike_but_different_keep_their_own_records(self):
        from admiral import run
        self.assertNotEqual(run.key("db:a"), run.key("db?a"))

    def test_a_process_that_leaves_the_group_when_told_to_stop_is_stopped_too(self):
        out = os.path.join(self.root, "late")
        # a child that, told to stop, slips into a session of its own and goes on
        late = ("import os, signal, time\n"
                "def leave(*_):\n    os.setsid()\n"
                "signal.signal(signal.SIGTERM, leave)\n"
                f"open({out!r}, 'w').write(str(os.getpid()))\n"
                "while True:\n    time.sleep(0.1)\n")
        r = self.admiral("run", "--lock", "heavy", "--who", "s t", "--limit", "0.03", "--",
                         "sh", "-c", f"{sys.executable} -c \"{late}\" & wait")
        self.assertEqual(r.returncode, 124, r.stderr)
        with open(out) as fh:
            pid = int(fh.read())
        self.assertTrue(gone_soon(pid), "a process that left the group on TERM was left running")

    def line(self, name):
        q = os.path.join(self.locks, f".q.{name}")
        return [f for f in os.listdir(q) if not f.startswith(".")] if os.path.isdir(q) else []

    def test_any_of_takes_the_free_one_and_tells_the_command(self):
        self.assertEqual(self.admiral("lock", "acquire", "pg-1", "--who", "other job").returncode, 0)
        r = self.admiral("run", "--lock", "pg-1|pg-2", "--who", "s t", "--",
                         "sh", "-c", 'echo "$ADMIRAL_LOCK/$ADMIRAL_LOCKS"')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "pg-2/pg-2")
        self.assertEqual(self.visible(), ["pg-1"])  # the other job's, untouched
        # waiting on a choice while holding another lock could deadlock two runs: refused
        r = self.admiral("run", "--lock", "pg-1|pg-2", "--lock", "heavy", "--who", "s t", "--", "true")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("taken on its own", r.stderr)

    def test_a_lock_named_like_a_port_is_still_the_command_s(self):
        r = self.admiral("run", "--lock", "port-worker", "--who", "s t", "--", "sh", "-c", 'echo "$ADMIRAL_LOCK"')
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "port-worker"), r.stderr)

    def test_any_of_waits_for_whichever_comes_free_and_leaves_the_other_line(self):
        for n in ("pg-1", "pg-2"):
            self.assertEqual(self.admiral("lock", "acquire", n, "--who", f"holder {n}").returncode, 0)
        out = os.path.join(self.root, "got")
        p = self.background("run", "--lock", "pg-1|pg-2", "--who", "s t", "--",
                            "sh", "-c", f'echo "$ADMIRAL_LOCK" > {out}')
        self.wait_for(lambda: self.line("pg-1") and self.line("pg-2"))  # in line at both
        self.assertEqual(self.admiral("lock", "release", "pg-2", "--who", "holder pg-2").returncode, 0)
        p.wait(timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr.read())
        with open(out) as fh:
            self.assertEqual(fh.read().strip(), "pg-2")
        self.assertEqual((self.line("pg-1"), self.line("pg-2")), ([], []))  # out of the other line too
        self.assertEqual(self.owner("pg-1")["who"], "holder pg-1")

    def test_a_choice_stopped_while_waiting_leaves_every_line(self):
        for n in ("pg-1", "pg-2"):
            self.assertEqual(self.admiral("lock", "acquire", n, "--who", f"holder {n}").returncode, 0)
        p = self.background("run", "--lock", "pg-1|pg-2", "--who", "s t", "--", "true")
        self.wait_for(lambda: self.line("pg-1") and self.line("pg-2"))
        p.terminate()
        p.wait(timeout=30)
        self.assertEqual((self.line("pg-1"), self.line("pg-2")), ([], []))
        self.assertEqual([self.owner(n)["who"] for n in ("pg-1", "pg-2")], ["holder pg-1", "holder pg-2"])

    def test_a_short_job_given_priority_goes_first(self):
        self.assertEqual(self.admiral("lock", "acquire", "heavy", "--who", "holder").returncode, 0)
        out = os.path.join(self.root, "order")
        long = self.background("run", "--lock", "heavy", "--who", "s long", "--", "sh", "-c", f"echo long >> {out}")
        self.wait_for(lambda: len(self.line("heavy")) == 1)
        short = self.background("run", "--lock", "heavy", "--who", "s short", "--priority", "1", "--",
                                "sh", "-c", f"echo short >> {out}")
        self.wait_for(lambda: len(self.line("heavy")) == 2)
        self.assertEqual(self.admiral("lock", "release", "heavy", "--who", "holder").returncode, 0)
        long.wait(timeout=30)
        short.wait(timeout=30)
        with open(out) as fh:
            self.assertEqual(fh.read().split(), ["short", "long"])

    def test_stop_names_the_lock_held_not_the_choice(self):
        r = self.admiral("run", "--lock", "pg-1|pg-2", "--who", "s t", "--ready", '[ "$ADMIRAL_LOCK" = pg-1 ]',
                         "--ready-timeout", "5", "--", "sleep", "600")  # the check sees the lock taken too
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("admiral run stop --lock pg-1`", r.stdout)
        r = self.admiral("run", "stop", "--lock", "pg-1|pg-2")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("pg-1 (s t [run ", r.stderr)
        self.assertEqual(self.admiral("run", "stop", "--lock", "pg-1").returncode, 0)
        self.assertEqual(self.visible(), [])

    def test_it_needs_a_lock_and_a_command(self):
        self.assertNotEqual(self.admiral("run", "--who", "s t", "--", "true").returncode, 0)
        self.assertNotEqual(self.admiral("run", "--lock", "x", "--who", "s t").returncode, 0)

    def lines(self):
        return sorted(n for n in self.held() if n.startswith(".q."))

    def age(self, *paths, seconds=120):
        for path in paths:
            os.utime(os.path.join(self.locks, path), (time.time() - seconds,) * 2)

    def test_a_line_is_left_empty_by_every_way_out_and_goes_a_minute_later(self):
        # every way into a line and out of it: a plain acquire, a run, a queue left, a wait that got its turn, a
        # wait stopped, a choice that took one lock and left the other line. A run under a name of its own (one
        # per service, say) left a line behind each time, and every acquire and status went through them all
        self.assertEqual(self.admiral("lock", "acquire", "plain", "--who", "w1").returncode, 0)
        self.assertEqual(self.admiral("lock", "release", "plain", "--who", "w1").returncode, 0)
        self.assertEqual(self.admiral("run", "--lock", "service-a1", "--who", "s t", "--", "true").returncode, 0)
        self.assertEqual(self.admiral("lock", "queue", "later", "--who", "w1").returncode, 0)
        self.assertEqual(self.admiral("lock", "leave", "later", "--who", "w1").returncode, 0)
        self.assertEqual(self.admiral("lock", "acquire", "heavy", "--who", "holder").returncode, 0)
        waiting = self.background("run", "--lock", "heavy", "--who", "s wait", "--", "true")
        stopped = self.background("run", "--lock", "heavy", "--who", "s stop", "--", "true")
        self.wait_for(lambda: len(self.line("heavy")) == 2)
        stopped.terminate()
        stopped.wait(timeout=20)
        self.assertEqual(self.admiral("lock", "release", "heavy", "--who", "holder").returncode, 0)
        waiting.wait(timeout=30)
        self.assertEqual(waiting.returncode, 0, waiting.stderr.read())
        self.assertEqual(self.admiral("lock", "acquire", "pg-1", "--who", "holder").returncode, 0)
        self.assertEqual(self.admiral("run", "--lock", "pg-1|pg-2", "--who", "s t", "--", "true").returncode, 0)
        left = self.lines()
        self.assertTrue(left)
        self.assertEqual({n: os.listdir(os.path.join(self.locks, n)) for n in left}, {n: [] for n in left})
        self.assertEqual(self.admiral("lock", "status").returncode, 0)
        self.assertEqual(self.lines(), left)  # a line empty only just now stays: one coming in may be making it
        self.age(*left)
        self.assertEqual(self.admiral("lock", "status").returncode, 0)
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.visible(), ["pg-1"])

    def test_lines_nobody_is_in_are_tidied_and_a_waiter_s_line_is_kept(self):
        dead = subprocess.Popen(["true"])
        dead.wait()
        for name in ("left-1", "left-2"):  # left behind by an older version: one per name ever used
            os.makedirs(os.path.join(self.locks, f".q.{name}"))
        self.age(".q.left-1", ".q.left-2")
        os.makedirs(os.path.join(self.locks, ".q.fresh"))  # empty just now: a waiter may be coming in
        self.assertEqual(self.admiral("lock", "queue", "gone", "--who", "w gone", "--pid", str(dead.pid)).returncode, 0)
        self.age(".q.gone")
        os.makedirs(os.path.join(self.locks, ".q.priority"))  # a commander's priority, its waiter just leaving
        with open(os.path.join(self.locks, ".q.priority", ".prio.0123"), "w") as fh:
            fh.write("prio=5\nby=Commander-A\n")
        self.age(".q.priority/.prio.0123", ".q.priority")
        for name, seconds in (("writing", 0), ("cut", 120)):  # a place being written, and one whose writer died
            os.makedirs(os.path.join(self.locks, f".q.{name}"))
            open(os.path.join(self.locks, f".q.{name}", ".tmp.4321"), "w").close()
            self.age(f".q.{name}/.tmp.4321", seconds=seconds)
            self.age(f".q.{name}")
        self.assertEqual(self.admiral("lock", "queue", "live", "--who", "w live", "--pid", str(os.getpid())).returncode,
                         0)
        self.age(".q.live")
        status = self.admiral("lock", "status").stdout
        self.assertIn("w gone", status)
        self.assertIn("STALE", status)
        self.assertEqual(self.lines(), [".q.cut", ".q.fresh", ".q.gone", ".q.live", ".q.priority", ".q.writing"])
        self.assertEqual(os.listdir(os.path.join(self.locks, ".q.cut")), [])
        self.assertEqual(os.listdir(os.path.join(self.locks, ".q.writing")), [".tmp.4321"])
        self.assertEqual(os.listdir(os.path.join(self.locks, ".q.priority")), [".prio.0123"])  # never taken away
        self.assertEqual((len(self.line("live")), len(self.line("gone"))), (1, 1))  # nor a waiter, though stale
        # the stale waiter goes when its own line is next read, as ever, and the line once it has been empty a while
        self.assertEqual(self.admiral("lock", "acquire", "gone", "--who", "w1").returncode, 0)
        self.assertEqual(self.admiral("lock", "release", "gone", "--who", "w1").returncode, 0)
        self.assertEqual(self.line("gone"), [])
        self.age(".q.gone", ".q.cut")
        self.assertEqual(self.admiral("lock", "status").returncode, 0)
        self.assertEqual(self.lines(), [".q.fresh", ".q.live", ".q.priority", ".q.writing"])

    def test_taking_releasing_or_leaving_a_lock_tidies_too(self):
        # not only a status: a machine where nobody looks at the locks still clears them
        self.assertEqual(self.admiral("lock", "acquire", "held", "--who", "holder").returncode, 0)
        for step in (("acquire", "other", "--who", "w1"), ("release", "other", "--who", "w1"),
                     ("leave", "held", "--who", "w2"), ("release", "held", "--who", "holder")):
            os.makedirs(os.path.join(self.locks, ".q.left"))
            self.age(".q.left")
            self.assertEqual(self.admiral("lock", *step).returncode, 0)
            self.assertNotIn(".q.left", self.lines(), step)

    def test_a_place_that_cannot_be_written_fails_rather_than_claims_one(self):
        os.makedirs(self.locks)
        open(os.path.join(self.locks, ".q.blocked"), "w").close()  # where its line would go: never a directory
        r = self.admiral("lock", "queue", "blocked", "--who", "w1")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("could not write a place in the line for blocked", r.stderr)
        r = self.admiral("lock", "acquire", "blocked", "--who", "w1")
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_a_priority_that_cannot_be_written_keeps_the_one_it_had(self):
        commanders = os.path.join(self.root, "state", "lock-commanders.txt")
        os.makedirs(self.locks)
        with open(commanders, "w") as fh:
            fh.write("Commander-A\n")
        self.assertEqual(self.admiral("lock", "queue", "heavy", "--who", "w1", "--pid", str(os.getpid())).returncode, 0)
        set_to = lambda n, env=None: subprocess.run(
            [sys.executable, "-m", "admiral", "lock", "prio", "heavy", "--who", "w1", "--priority", str(n), "--by",
             "Commander-A"], capture_output=True, text=True, env=env or self.env, timeout=60)
        self.assertEqual(set_to(8).returncode, 0)
        broken = os.path.join(self.root, "broken")  # an mv that fails, as on a full disk
        os.makedirs(broken)
        with open(os.path.join(broken, "mv"), "w") as fh:
            fh.write("#!/bin/sh\nexit 1\n")
        os.chmod(os.path.join(broken, "mv"), 0o755)
        r = set_to(9, dict(self.env, PATH=broken + os.pathsep + self.env["PATH"]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("could not write the priority of w1", r.stderr)
        self.assertIn("priority 8", self.admiral("lock", "status").stdout)


if __name__ == "__main__":
    unittest.main()
