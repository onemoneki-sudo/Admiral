"""bin/admiral and scripts/refresh.sh: which Python runs Admiral, and where a failure to start is reported."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Launch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        # a clone of our own: bin/admiral beside the package, so .python-path can be written next to it
        self.clone = os.path.join(self.dir, "clone")
        os.makedirs(os.path.join(self.clone, "bin"))
        shutil.copy(os.path.join(ROOT, "bin", "admiral"), os.path.join(self.clone, "bin"))
        os.symlink(os.path.join(ROOT, "admiral"), os.path.join(self.clone, "admiral"))
        self.home = os.path.join(self.dir, "home")
        os.makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_admiral(self, *argv, path="/usr/bin:/bin", **env):
        e = {"HOME": self.home, "PATH": path, **env}
        return subprocess.run([os.path.join(self.clone, "bin", "admiral"), *argv], capture_output=True, text=True, env=e)

    def record(self, python):
        with open(os.path.join(self.clone, ".python-path"), "w") as fh:
            fh.write(python + "\n")

    def test_the_recorded_python_runs_it_whatever_the_path(self):
        self.record(sys.executable)
        tools = os.path.join(self.dir, "tools")  # what the launcher needs from the PATH, and no python3 at all
        os.makedirs(tools)
        for name in ("dirname", "readlink"):
            os.symlink(shutil.which(name), os.path.join(tools, name))
        r = self.run_admiral("--version", path=tools)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("admiral "))

    def test_a_removed_recorded_python_falls_back_to_python3(self):
        self.record(os.path.join(self.dir, "gone", "python3"))
        r = self.run_admiral("--version", path=os.path.dirname(sys.executable) + ":/usr/bin:/bin")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_job_that_cannot_start_reports_where_the_status_line_looks(self):
        fake = os.path.join(self.dir, "python3")
        with open(fake, "w") as fh:
            fh.write("#!/bin/sh\necho 'this python is broken' >&2\nexit 1\n")
        os.chmod(fake, 0o755)
        env = {"HOME": self.home, "PATH": "/usr/bin:/bin", "ADMIRAL_PYTHON": fake}
        r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "refresh.sh")], capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        with open(os.path.join(self.home, ".local", "state", "admiral", "last-error.txt")) as fh:
            self.assertIn("this python is broken", fh.read())

    @unittest.skipUnless(os.path.exists("/usr/bin/python3") and subprocess.run(
        ["/usr/bin/python3", "-c", "import sys; sys.exit(sys.version_info >= (3, 11))"]).returncode == 0,
        "no Python older than 3.11 at /usr/bin/python3")
    def test_an_old_python_says_so_in_the_status_line(self):
        r = self.run_admiral("statusline", ADMIRAL_PYTHON="/usr/bin/python3")
        self.assertIn("Admiral needs Python 3.11 or newer", r.stdout)  # stdout: drawn where the status line goes
        self.assertEqual(r.returncode, 0)  # Claude Code draws a status line's output only when it exits 0


if __name__ == "__main__":
    unittest.main()
