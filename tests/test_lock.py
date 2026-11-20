"""The lock tool (admiral/lock.sh) on names alike but for case, on locks taken without a pid whose session still runs,
on takeovers told to the holder they were taken from, and on what a wait says while it waits."""

import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Lock(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.locks = os.path.join(self.root, "state", "locks")
        cfg = os.path.join(self.root, "config.toml")
        with open(cfg, "w") as fh:
            fh.write(f'state_dir = "{os.path.join(self.root, "state")}"\n')
        self.env = dict(os.environ, ADMIRAL_CONFIG=cfg, PYTHONPATH=ROOT, ADMIRAL_LOCK_SESSION="none")
        self.started = []

    def tearDown(self):
        for p in self.started:
            if p.poll() is None:
                p.kill()
            p.communicate()
        shutil.rmtree(self.root, ignore_errors=True)

    def admiral(self, *args, session=None, **extra):
        env = dict(self.env, **({"ADMIRAL_LOCK_SESSION": str(session)} if session is not None else {}), **extra)
        return subprocess.run([sys.executable, "-m", "admiral", *args], capture_output=True, text=True, env=env,
                              timeout=60)

    def background(self, *args):
        p = subprocess.Popen([sys.executable, "-m", "admiral", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=self.env)
        self.started.append(p)
        return p

    def owner(self, name):
        with open(os.path.join(self.locks, name, "owner")) as fh:
            return dict(line.rstrip("\n").split("=", 1) for line in fh if "=" in line)

    def age(self, name, minutes):
        """The lock taken `minutes` ago."""
        path = os.path.join(self.locks, name, "owner")
        with open(path) as fh:
            text = fh.read()
        with open(path, "w") as fh:
            fh.write(re.sub(r"^since=\d+", f"since={int(time.time()) - minutes * 60}", text, flags=re.M))

    def dead_pid(self):
        p = subprocess.Popen(["true"])
        p.wait()
        return p.pid

    def first_line(self, stream, starting, seconds=20):
        """The first line of the stream that says `starting`, read on a thread so that a silent stream fails the test
        once the time is up rather than hang it."""
        lines = queue.Queue()
        threading.Thread(target=lambda: [lines.put(line) for line in stream], daemon=True).start()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                line = lines.get(timeout=max(0.01, end - time.monotonic()))
            except queue.Empty:
                break
            if line.startswith(starting) or f": {starting}" in line:
                return line
        self.fail(f"no line {starting!r}")

    # ---- names alike but for case ---------------------------------------------------------------------------------

    def test_a_name_differing_only_in_case_from_a_held_lock_is_refused_naming_its_holder(self):
        self.assertEqual(self.admiral("lock", "acquire", "proxy-A1", "--who", "w1", "--pid", str(os.getpid()))
                         .returncode, 0)
        for command in ("acquire", "queue"):
            r = self.admiral("lock", command, "proxy-a1", "--who", "w2")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("proxy-A1 is held by w1", r.stderr)
            self.assertIn("differ only in case", r.stderr)
        self.assertEqual(self.admiral("lock", "acquire", "proxy-A1", "--who", "w2").returncode, 1)  # same: busy
        self.assertEqual(self.admiral("lock", "acquire", "proxy-a2", "--who", "w2").returncode, 0)  # another

    def test_a_name_differing_only_in_case_from_a_line_with_waiters_is_refused(self):
        self.assertEqual(self.admiral("lock", "queue", "Line-A", "--who", "w1", "--pid", str(os.getpid())).returncode,
                         0)
        r = self.admiral("lock", "acquire", "line-a", "--who", "w2")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Line-A has a line of waiters", r.stderr)

    def test_a_line_whose_only_waiter_has_gone_does_not_refuse(self):
        self.assertEqual(self.admiral("lock", "queue", "Line-B", "--who", "w1", "--pid", str(self.dead_pid()))
                         .returncode, 0)
        r = self.admiral("lock", "acquire", "line-b", "--who", "w2")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_two_spellings_taken_at_once_never_both_hold(self):
        procs = [subprocess.Popen([sys.executable, "-m", "admiral", "lock", "acquire", name, "--who", f"w-{name}",
                                   "--pid", str(os.getpid())], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env=self.env) for name in ("Race-X", "race-x") * 3]
        codes = [p.wait(timeout=60) for p in procs]
        for p in procs:
            p.communicate()
        held = [n for n in os.listdir(self.locks) if n.lower() == "race-x"]
        self.assertEqual(len(held), 1)  # one directory, one spelling, on any disk
        self.assertEqual(codes.count(0), 1)
        self.assertTrue(all(c in (0, 1, 2) for c in codes))

    def test_a_spelling_mark_left_by_a_dead_caller_is_passed_after_a_minute(self):
        mark = os.path.join(self.locks, ".spelling.svc")
        os.makedirs(mark)
        os.utime(mark, (time.time() - 120, time.time() - 120))
        r = self.admiral("lock", "acquire", "SVC", "--who", "w1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(mark))  # and its own goes once it is done

    def test_another_spelling_held_while_one_waits_ends_the_wait_saying_so(self):
        self.admiral("lock", "acquire", "Wait-A", "--who", "w1", "--pid", str(os.getpid()))
        p = self.background("lock", "acquire", "Wait-A", "--who", "w2", "--wait")
        self.first_line(p.stdout, "waiting for Wait-A")
        self.admiral("lock", "release", "Wait-A", "--who", "w1")
        try:  # another spelling, taken past the line (a stale place, say)
            os.makedirs(os.path.join(self.locks, "wait-a"))
        except FileExistsError:
            self.skipTest("the waiter took Wait-A first, and on this disk wait-a is the same directory")
        with open(os.path.join(self.locks, "wait-a", "owner"), "w") as fh:
            fh.write(f"who=w3\npid={os.getpid()}\nsince={int(time.time())}\nttl=180\n")
        _, err = p.communicate(timeout=60)
        if os.path.exists(os.path.join(self.locks, "Wait-A")) and not os.path.exists(os.path.join(self.locks, "wait-a")):
            self.skipTest("one directory on this disk: the waiter simply waits for w3, named in its line")
        self.assertEqual(p.returncode, 2, err)
        self.assertIn("held by w3", err)

    def test_an_empty_line_left_by_an_old_spelling_does_not_refuse(self):
        os.makedirs(os.path.join(self.locks, ".q.Old-Name"))
        r = self.admiral("lock", "acquire", "old-name", "--who", "w1")
        self.assertEqual(r.returncode, 0, r.stderr)

    # ---- a lock without a pid, and the session it was taken in --------------------------------------------------

    def test_past_its_ttl_a_lock_without_a_pid_is_kept_while_its_session_runs(self):
        r = self.admiral("lock", "acquire", "svc", "--who", "w1", "--ttl", "1", session=os.getpid())
        self.assertIn("kept only while this session", r.stderr)
        self.assertEqual(self.owner("svc")["session"], str(os.getpid()))
        self.age("svc", 5)
        busy = self.admiral("lock", "acquire", "svc", "--who", "w2")
        self.assertEqual(busy.returncode, 1, busy.stdout)
        self.assertIn("kept: its session", self.admiral("lock", "status").stdout)

    def test_once_its_session_has_ended_it_is_stale_and_taken_over(self):
        self.admiral("lock", "acquire", "svc", "--who", "w1", "--ttl", "1", session=self.dead_pid())
        self.age("svc", 5)
        r = self.admiral("lock", "acquire", "svc", "--who", "w2")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("taking over stale lock", r.stdout)

    def test_a_session_whose_pid_is_used_again_is_not_the_session(self):
        self.admiral("lock", "acquire", "svc", "--who", "w1", "--ttl", "1", session=os.getpid())
        path = os.path.join(self.locks, "svc", "owner")
        with open(path) as fh:
            text = fh.read()
        with open(path, "w") as fh:
            fh.write(re.sub(r"^session_start=.*$", "session_start=Thu Jan  1 00:00:00 1970", text, flags=re.M))
        self.age("svc", 5)
        self.assertEqual(self.admiral("lock", "acquire", "svc", "--who", "w2").returncode, 0)

    def test_without_a_session_it_is_stale_past_its_ttl_as_before(self):
        r = self.admiral("lock", "acquire", "svc", "--who", "w1", "--ttl", "1")
        self.assertIn("counts as stale", r.stderr)
        self.assertNotIn("session", self.owner("svc"))
        self.age("svc", 5)
        self.assertEqual(self.admiral("lock", "acquire", "svc", "--who", "w2").returncode, 0)

    def test_a_lock_with_a_pid_goes_by_its_pid_alone(self):
        self.admiral("lock", "acquire", "svc", "--who", "w1", "--pid", str(os.getpid()), "--ttl", "1",
                     session=os.getpid())
        self.assertNotIn("session", self.owner("svc"))
        self.age("svc", 5)
        self.assertEqual(self.admiral("lock", "acquire", "svc", "--who", "w2").returncode, 1)  # its pid still runs

    # ---- a takeover told to the holder it was taken from --------------------------------------------------------

    def test_the_holder_a_lock_was_taken_from_is_told_and_status_lists_it(self):
        self.admiral("lock", "acquire", "port-8150", "--who", "w1", "--ttl", "1")
        self.age("port-8150", 5)
        self.assertEqual(self.admiral("lock", "acquire", "port-8150", "--who", "w2").returncode, 0)
        for command in ("release", "attach"):
            r = self.admiral("lock", command, "port-8150", "--who", "w1", "--pid", "1")
            self.assertEqual(r.returncode, 1)
            self.assertIn("was taken over from you", r.stderr)
            self.assertIn("by w2", r.stderr)
            self.assertIn("no pid and was past its 1-minute ttl", r.stderr)
        status = self.admiral("lock", "status").stdout
        self.assertIn("taken over in the last day:", status)
        self.assertIn("port-8150 at", status)
        self.assertIn("from w1 by w2", status)
        busy = self.admiral("lock", "acquire", "port-8150", "--who", "w1")
        self.assertEqual(busy.returncode, 1)
        self.assertIn("was taken over from you", busy.stderr)
        self.assertNotIn("taken over from you", self.admiral("lock", "acquire", "port-8150", "--who", "w3").stderr)
        self.assertEqual(self.admiral("lock", "release", "port-8150", "--who", "w2").returncode, 0)
        again = self.admiral("lock", "acquire", "port-8150", "--who", "w1")
        self.assertEqual(again.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.locks, ".taken", "port-8150")))  # its own again
        self.assertNotIn("taken over", self.admiral("lock", "status").stdout)

    def test_each_holder_displaced_in_turn_is_told(self):
        self.admiral("lock", "acquire", "svc", "--who", "w1", "--ttl", "1")
        self.age("svc", 5)
        self.admiral("lock", "acquire", "svc", "--who", "w2", "--ttl", "1")
        self.age("svc", 5)
        self.admiral("lock", "acquire", "svc", "--who", "w3")
        self.assertIn("by w2", self.admiral("lock", "release", "svc", "--who", "w1").stderr)
        self.assertIn("by w3", self.admiral("lock", "release", "svc", "--who", "w2").stderr)
        status = self.admiral("lock", "status").stdout
        self.assertIn("from w1 by w2", status)
        self.assertIn("from w2 by w3", status)

    def test_the_session_is_told_apart_whatever_zone_the_reader_is_in(self):
        self.admiral("lock", "acquire", "svc", "--who", "w1", "--ttl", "1", session=os.getpid(), TZ="UTC")
        self.age("svc", 5)
        busy = self.admiral("lock", "acquire", "svc", "--who", "w2", TZ="Asia/Tokyo", LC_ALL="C")
        self.assertEqual(busy.returncode, 1, busy.stdout)

    def test_a_takeover_of_a_dead_pid_says_so(self):
        self.admiral("lock", "acquire", "db", "--who", "w1", "--pid", str(self.dead_pid()))
        self.assertEqual(self.admiral("lock", "acquire", "db", "--who", "w2").returncode, 0)
        self.assertIn("no longer ran", self.admiral("lock", "release", "db", "--who", "w1").stderr)

    # ---- what a wait says while it waits ------------------------------------------------------------------------

    def test_a_wait_names_the_holder_and_since_when(self):
        self.admiral("lock", "acquire", "heavy", "--who", "w1", "--pid", str(os.getpid()))
        since = time.strftime("%H:%M", time.localtime(int(self.owner("heavy")["since"])))
        p = self.background("lock", "acquire", "heavy", "--who", "w2", "--wait")
        line = self.first_line(p.stdout, "waiting for heavy")
        self.assertIn(f"holder: w1, since {since}", line)

    def test_admiral_run_says_whom_it_waits_for_while_it_waits(self):
        self.admiral("lock", "acquire", "heavy", "--who", "w1", "--pid", str(os.getpid()))
        p = self.background("run", "--lock", "heavy", "--who", "w2", "--", "true")
        line = self.first_line(p.stderr, "waiting for heavy")
        self.assertIn("holder: w1", line)
        self.assertIsNone(p.poll())  # said while still waiting, not once it was over
        self.assertEqual(self.admiral("lock", "release", "heavy", "--who", "w1").returncode, 0)
        _, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, err)
        self.assertNotIn("waiting for heavy", err)  # said once, not again at the end

    def test_admiral_run_waiting_for_any_of_several_names_their_holders(self):
        for name, who in (("slot-1", "w1"), ("slot-2", "w2")):
            self.admiral("lock", "acquire", name, "--who", who, "--pid", str(os.getpid()))
        p = self.background("run", "--lock", "slot-1|slot-2", "--who", "w3", "--", "true")
        line = self.first_line(p.stderr, "waiting for any of")
        self.assertIn("slot-1 held by w1 since", line)
        self.assertIn("slot-2 held by w2 since", line)
        self.admiral("lock", "release", "slot-2", "--who", "w2")
        p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
