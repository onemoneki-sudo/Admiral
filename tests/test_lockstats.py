"""What the lock tool records of each take and release, and `admiral lock stats`, against a state directory of its own."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Recorded(unittest.TestCase):
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

    def admiral(self, *args):
        return subprocess.run([sys.executable, "-m", "admiral", *args], capture_output=True, text=True, env=self.env,
                              timeout=60)

    def history(self):
        d = os.path.join(self.locks, ".history")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def records(self):
        out = []
        for f in self.history():
            with open(os.path.join(self.locks, ".history", f)) as fh:
                out += [line.rstrip("\n").split("\t") for line in fh]
        return out

    def write_history(self, month, rows):
        d = os.path.join(self.locks, ".history")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{month}.log"), "a") as fh:
            for row in rows:
                fh.write("\t".join(str(x) for x in row) + "\n")

    # ---- what is recorded ----------------------------------------------------------------------------------------

    def test_each_take_and_release_is_recorded_with_its_wait_and_its_hold(self):
        self.assertEqual(self.admiral("lock", "acquire", "db", "--who", "w1").returncode, 0)
        p = subprocess.Popen([sys.executable, "-m", "admiral", "lock", "acquire", "db", "--who", "w2", "--wait",
                              "--pid", str(os.getpid())], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=self.env)
        self.started.append(p)
        line = os.path.join(self.locks, ".q.db")
        end = time.monotonic() + 20
        while not (os.path.isdir(line) and [f for f in os.listdir(line) if not f.startswith(".")]):
            self.assertLess(time.monotonic(), end, "the waiter never joined the line")
            time.sleep(0.1)
        time.sleep(2.5)
        self.assertEqual(self.admiral("lock", "release", "db", "--who", "w1").returncode, 0)
        self.assertEqual(p.wait(timeout=30), 0)
        self.assertEqual(self.admiral("lock", "release", "db", "--who", "w2").returncode, 0)
        port = self.admiral("lock", "port", "--who", "w1", "--from", "18950", "--to", "18999").stdout.strip()
        got = self.records()
        self.assertTrue(all(len(r) == 5 and r[0].isdigit() for r in got), got)
        self.assertEqual([(r[1], r[2], r[4]) for r in got], [
            ("take", "db", "w1"), ("release", "db", "w1"), ("take", "db", "w2"), ("release", "db", "w2"),
            ("take", f"port-{port}", "w1")])
        self.assertLess(int(got[0][3]), 10)  # it took a free lock at once: the tool's own second, at most, not a wait
        # seconds, not anything a hundred times larger: a loaded machine may take a while to start the waiter
        self.assertTrue(2 <= int(got[1][3]) <= 120, got[1])  # held while the other waited
        self.assertTrue(2 <= int(got[2][3]) <= 120, got[2])  # waited from joining the line until it was free
        self.assertEqual(got[4][3], "0")  # a port is claimed, never waited for

    def test_a_run_s_wait_and_hold_are_recorded_under_its_own_name(self):
        self.assertEqual(self.admiral("run", "--lock", "heavy", "--who", "s t", "--", "sleep", "1").returncode, 0)
        got = self.records()
        self.assertEqual([(r[1], r[2]) for r in got], [("take", "heavy"), ("release", "heavy")])
        self.assertRegex(got[0][4], r"^s t \[run [0-9a-f]{8}\]$")
        self.assertGreaterEqual(int(got[1][3]), 1)

    def test_a_who_with_a_tab_or_a_newline_stays_one_record(self):
        self.assertEqual(self.admiral("lock", "acquire", "x", "--who", "a\tb\nc").returncode, 0)
        got = self.records()
        self.assertEqual([(len(r), r[1], r[2], r[4]) for r in got], [(5, "take", "x", "a b c")])

    def test_only_the_three_latest_months_are_kept(self):
        for month in ("2020-01", "2020-02", "2020-03", "2020-04"):
            self.write_history(month, [(1, "take", "old", 0, "w")])
        self.assertEqual(self.admiral("lock", "acquire", "x", "--who", "w1").returncode, 0)
        self.assertEqual(self.history(), ["2020-03.log", "2020-04.log", time.strftime("%Y-%m") + ".log"])
        self.assertEqual(self.admiral("lock", "release", "x", "--who", "w1").returncode, 0)  # an old month stays
        self.assertEqual(len(self.history()), 3)

    def test_a_history_that_cannot_be_written_never_fails_the_lock(self):
        os.makedirs(self.locks)
        open(os.path.join(self.locks, ".history"), "w").close()  # where the history would go: never a directory
        r = self.admiral("lock", "acquire", "x", "--who", "w1", "--pid", str(os.getpid()))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.admiral("lock", "release", "x", "--who", "w1").returncode, 0)

    # ---- admiral lock stats --------------------------------------------------------------------------------------

    def test_stats_show_each_lock_s_waits_and_holds(self):
        now = int(time.time())
        start = now - 20000
        rows = [(start, "take", "svc-a", 0, "w"), (start + 1, "take", "svc-b", 0, "w")]
        # heavy: ten takes, five waited 10 seconds or more; ten holds of ten minutes over 20000 seconds: 30% held
        for i, waited in enumerate((0, 0, 0, 0, 0, 30, 60, 120, 600, 1200)):
            rows += [(start + 100 + i * 1000, "take", "heavy", waited, "w"),
                     (start + 700 + i * 1000, "release", "heavy", 600, "w")]
        # db-1: four takes, none waited for 10 seconds (5 is a poll's own delay)
        for i, (waited, held) in enumerate(((0, 60), (0, 120), (0, 180), (5, 240))):
            rows += [(start + 50 + i * 100, "take", "db-1", waited, "w"),
                     (start + 60 + i * 100, "release", "db-1", held, "w")]
        rows += [(start + 5 + i, "take", f"port-{8100 + i}", 0, "w") for i in range(3)]  # ports, one line
        self.write_history(time.strftime("%Y-%m"), sorted(rows))
        out = self.admiral("lock", "stats").stdout.splitlines()
        self.assertIn("over the last 30 days", out[0])
        self.assertIn("19 takes", out[0])
        table = [line.split() for line in out if line.split()[:1] in (["heavy"], ["db-1"], ["port-*"])]
        self.assertEqual(table, [
            ["heavy", "10", "50%", "2m", "20m", "20m", "10m", "10m", "30%"],
            ["db-1", "4", "0%", "-", "-", "-", "2m", "4m", "3%"],
            ["port-*", "3", "0%", "-", "-", "-", "-", "-", "-"],
        ])
        self.assertTrue(any("2 more locks" in line for line in out), out)  # svc-a and svc-b, taken once each

    def test_stats_look_only_as_far_back_as_the_days_asked_for(self):
        now = int(time.time())
        self.write_history(time.strftime("%Y-%m"), [(now - 40 * 86400, "take", "heavy", 99999, "w")] +
                           [(now - 100 + i, "take", "heavy", 0, "w") for i in range(3)])
        self.assertNotIn("27h46m", self.admiral("lock", "stats").stdout)
        self.assertIn("27h46m", self.admiral("lock", "stats", "--days", "60").stdout)  # the wait of 99999 seconds

    def test_busy_counts_a_hold_still_going_and_only_the_time_recorded(self):
        now = int(time.time())
        # two holds of 100 seconds done, and one taken 600 seconds ago and still held: 800 of the 1000 recorded
        self.write_history(time.strftime("%Y-%m"), [
            (now - 1000, "take", "db", 0, "w"), (now - 900, "release", "db", 100, "w"),
            (now - 800, "take", "db", 0, "w"), (now - 700, "release", "db", 100, "w"),
            (now - 600, "take", "db", 0, "w")])
        os.makedirs(os.path.join(self.locks, "db"))
        with open(os.path.join(self.locks, "db", "owner"), "w") as fh:
            fh.write(f"who=w\npid=\nsince={now - 600}\nttl=180\n")
        row = [line.split() for line in self.admiral("lock", "stats").stdout.splitlines() if line.startswith("db ")]
        self.assertEqual(row[0][-1], "80%", row)

    def test_busy_counts_of_a_hold_begun_before_the_days_only_what_falls_within_them(self):
        now = int(time.time())
        start = now - 86400
        rows = [(now - 2 * 86400, "take", "other", 0, "w"),  # the history goes back before the day asked for
                (start + 3600, "release", "db", 7200, "w")]  # taken an hour before the day began
        for i in range(3):
            rows += [(start + 4000 + i * 1000, "take", "db", 0, "w"),
                     (start + 4100 + i * 1000, "release", "db", 100, "w")]
        self.write_history(time.strftime("%Y-%m"), rows)
        out = self.admiral("lock", "stats", "--days", "1").stdout
        row = [line.split() for line in out.splitlines() if line.startswith("db ")]
        self.assertEqual(row[0][-1], "5%", out)  # 3600 + 300 of 86400 seconds

    def test_ports_are_shown_however_few(self):
        self.write_history(time.strftime("%Y-%m"), [(int(time.time()) - 10, "take", "port-8100", 0, "w")])
        self.assertIn("port-*", self.admiral("lock", "stats").stdout)

    def test_a_lock_name_with_a_tab_stays_one_record(self):
        self.assertEqual(self.admiral("lock", "acquire", "heavy\t120", "--who", "w1").returncode, 0)
        got = self.records()
        self.assertEqual([(len(r), r[1], r[2]) for r in got], [(5, "take", "heavy%09120")])  # the name, coded
        self.assertLess(int(got[0][3]), 10)  # not the 120 a tab in the name would have made of it

    def test_a_history_that_cannot_be_written_says_nothing(self):
        os.makedirs(os.path.join(self.locks, ".history"))
        os.chmod(os.path.join(self.locks, ".history"), 0o500)
        try:
            r = self.admiral("lock", "acquire", "x", "--who", "w1", "--pid", str(os.getpid()))
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            r = self.admiral("lock", "release", "x", "--who", "w1")
            self.assertEqual((r.returncode, r.stderr), (0, ""))
        finally:
            os.chmod(os.path.join(self.locks, ".history"), 0o700)

    def test_stats_refuse_days_that_are_not_a_number_of_days(self):
        for days in ("nan", "inf", "1e309", "-1"):
            r = self.admiral("lock", "stats", "--days", days)
            self.assertEqual(r.returncode, 2, days)
            self.assertNotIn("Traceback", r.stderr, days)

    def own(self, lock, since):
        os.makedirs(os.path.join(self.locks, lock.lstrip("/")))
        with open(os.path.join(self.locks, lock.lstrip("/"), "owner"), "w") as fh:
            fh.write(f"who=w\npid=\nsince={since}\nttl=180\n")

    def row(self, name, *args):
        out = self.admiral("lock", "stats", *args).stdout
        found = [line.split() for line in out.splitlines() if line.split()[:1] == [name]]
        self.assertEqual(len(found), 1, out)
        return found[0]

    def test_a_lock_held_since_before_the_days_asked_for_shows_it_busy_all_along(self):
        now = int(time.time())
        self.write_history(time.strftime("%Y-%m"), [(now - 3 * 86400, "take", "other", 0, "w"),
                                                    (now - 2 * 86400, "take", "db", 0, "w")])
        self.own("db", now - 2 * 86400)
        self.assertEqual(self.row("db", "--days", "1")[1:3] + self.row("db", "--days", "1")[-1:], ["0", "-", "100%"])

    def test_a_lock_released_within_the_days_after_a_long_hold_is_shown(self):
        now = int(time.time())
        self.write_history(time.strftime("%Y-%m"), [(now - 3 * 86400, "take", "other", 0, "w"),
                                                    (now - 3600, "release", "db", 2 * 86400, "w")])
        self.assertEqual(self.row("db", "--days", "1")[-1], "96%")  # 23 of the 24 hours

    def test_records_written_after_now_make_no_negative_and_no_future_share(self):
        now = int(time.time())
        self.write_history(time.strftime("%Y-%m"), [(now + 100, "take", "db", 20, "w")])  # a clock put back
        self.own("db", now - 1)
        self.assertEqual(self.row("db")[-1], "0%")
        self.write_history(time.strftime("%Y-%m"), [(now - 1000, "take", "q", 0, "w"),
                                                    (now + 1000, "release", "q", 1500, "w")])  # ends after now
        self.assertEqual(self.row("q")[-1], "50%")  # 500 of the 1000 seconds to now, not 1500

    def test_a_lock_never_held_for_long_is_busy_zero_not_unknown(self):
        now = int(time.time())
        self.write_history(time.strftime("%Y-%m"), [(now - 100 + i, e, "db", 0, "w") for i in range(3)
                                                    for e in ("take", "release")])
        self.assertEqual(self.row("db")[-1], "0%")

    def test_locks_named_alike_stay_apart_and_a_name_like_a_path_finds_its_owner(self):
        for name in ("db\tA", "db A", "/db"):
            self.assertEqual(self.admiral("lock", "acquire", name, "--who", "w1").returncode, 0)
        self.assertEqual(sorted(r[2] for r in self.records()), ["/db", "db A", "db%09A"])
        out = self.admiral("lock", "stats").stdout.splitlines()
        self.assertEqual(len([line for line in out if line.startswith("db A ")]), 2, out)  # both held now, apart
        self.assertTrue([line for line in out if line.startswith("/db ")], out)

    def test_a_history_that_is_not_a_file_never_holds_up_a_lock(self):
        os.makedirs(os.path.join(self.locks, ".history"))
        os.mkfifo(os.path.join(self.locks, ".history", time.strftime("%Y-%m") + ".log"))  # nobody reads it
        start = time.monotonic()
        r = self.admiral("lock", "acquire", "x", "--who", "w1", "--pid", str(os.getpid()))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.admiral("lock", "release", "x", "--who", "w1").returncode, 0)
        self.assertLess(time.monotonic() - start, 30)

    def test_stats_without_a_history_say_so(self):
        r = self.admiral("lock", "stats")
        self.assertEqual(r.returncode, 0)
        self.assertIn("no lock taken in the last 30 days", r.stdout)
        self.assertNotEqual(self.admiral("lock", "stats", "--days", "0").returncode, 0)


if __name__ == "__main__":
    unittest.main()
