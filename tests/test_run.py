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

    def test_it_needs_a_lock_and_a_command(self):
        self.assertNotEqual(self.admiral("run", "--who", "s t", "--", "true").returncode, 0)
        self.assertNotEqual(self.admiral("run", "--lock", "x", "--who", "s t").returncode, 0)


if __name__ == "__main__":
    unittest.main()
