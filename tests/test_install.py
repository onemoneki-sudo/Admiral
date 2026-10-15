"""scripts/install.sh, in --dry-run: it changes nothing, and the config it would write parses."""

import json
import os
import plistlib
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def recorded():
    try:
        with open(os.path.join(ROOT, ".python-path")) as fh:
            return fh.read()
    except OSError:
        return None


class Install(unittest.TestCase):
    def test_the_dry_run_writes_nothing_and_its_config_parses(self):
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "home")
            os.makedirs(os.path.join(home, ".claude"))
            with open(os.path.join(home, ".claude", "settings.json"), "w") as fh:
                fh.write('{"statusLine": {"type": "command", "command": "bash -c \'echo \\"hud\\"\'"}}')
            cfg = os.path.join(d, "config.toml")
            before = recorded()
            r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "install.sh"), "--dry-run"], capture_output=True,
                               text=True, env=dict(os.environ, HOME=home, ADMIRAL_CONFIG=cfg))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(os.path.exists(cfg))
            # the template is the indented block right under "would write <config>:", up to the first unindented line
            lines = r.stdout.split(f"would write {cfg}:", 1)[1].splitlines()[1:]
            block = []
            for line in lines:
                if line and not line.startswith("    "):
                    break
                block.append(line[4:])
            text = "\n".join(block)
            data = tomllib.loads(text)
            self.assertEqual(data["statusline"]["base"], 'bash -c \'echo "hud"\'')
            self.assertEqual(data["sessions"]["commander_prefix"], "Commander")
            self.assertIn("claude plugin install admiral@admiral", r.stdout)
            self.assertIn("would record the Python", r.stdout)
            self.assertIn('"autoMemoryEnabled": false', r.stdout)  # memory left on: recommended off
            self.assertEqual(recorded(), before)  # the dry run records no Python

    @unittest.skipUnless(sys.platform == "darwin", "the background job is set up on macOS only")
    def test_a_config_of_its_own_goes_into_the_background_job(self):
        with tempfile.TemporaryDirectory() as d:
            home, cfg = os.path.join(d, "home"), os.path.join(d, "R&D <a>", "config.toml")
            os.makedirs(home)
            r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "install.sh"), "--dry-run"], capture_output=True,
                               text=True, env=dict(os.environ, HOME=home, ADMIRAL_CONFIG=cfg))
            self.assertEqual(r.returncode, 0, r.stderr)
            plist = r.stdout.split("and load it:", 1)[1].split("</plist>", 1)[0] + "</plist>"
            plist = "\n".join(line[4:] for line in plist.splitlines() if line.strip())
            job = plistlib.loads(plist.encode())
            self.assertEqual(job["EnvironmentVariables"], {"ADMIRAL_CONFIG": cfg})
            self.assertEqual(job["StartInterval"], 60)

    @unittest.skipUnless(sys.platform == "darwin", "the background job is set up on macOS only")
    def test_a_config_path_goes_into_the_job_as_admiral_reads_it(self):
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            home, child = os.path.join(d, "home"), os.path.join(d, "physical", "child")
            os.makedirs(home)
            os.makedirs(child)
            os.symlink(child, os.path.join(d, "link"))
            for given, where, read_as in (("../config.toml", os.path.join(d, "link"), os.path.join(d, "physical", "config.toml")),
                                          ("~/cfg.toml", d, os.path.join(home, "cfg.toml")),
                                          ("~fixture/cfg.toml", d, os.path.join(d, "~fixture", "cfg.toml"))):
                with self.subTest(given=given):
                    r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "install.sh"), "--dry-run"],
                                       capture_output=True, text=True, cwd=where,
                                       env=dict(os.environ, HOME=home, PWD=where, ADMIRAL_CONFIG=given))
                    plist = r.stdout.split("and load it:", 1)[1].split("</plist>", 1)[0] + "</plist>"
                    job = plistlib.loads("\n".join(ln[4:] for ln in plist.splitlines() if ln.strip()).encode())
                    self.assertEqual(job["EnvironmentVariables"]["ADMIRAL_CONFIG"], read_as)

    @unittest.skipUnless(sys.platform == "darwin", "the background job is set up on macOS only")
    def test_a_relative_config_goes_into_the_job_as_a_full_path(self):
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "home")
            os.makedirs(home)
            r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "install.sh"), "--dry-run"], capture_output=True,
                               text=True, cwd=d, env=dict(os.environ, HOME=home, ADMIRAL_CONFIG="rel.toml"))
            plist = r.stdout.split("and load it:", 1)[1].split("</plist>", 1)[0] + "</plist>"
            job = plistlib.loads("\n".join(ln[4:] for ln in plist.splitlines() if ln.strip()).encode())
            self.assertEqual(job["EnvironmentVariables"]["ADMIRAL_CONFIG"], os.path.join(os.path.realpath(d), "rel.toml"))

    def test_elsewhere_than_macos_the_job_to_schedule_carries_a_config_of_its_own(self):
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "bin")
            os.makedirs(fake)
            with open(os.path.join(fake, "uname"), "w") as fh:
                fh.write("#!/bin/sh\necho Linux\n")
            os.chmod(os.path.join(fake, "uname"), 0o755)
            cfg = os.path.join(d, "my config.toml")
            r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "install.sh"), "--dry-run"], capture_output=True,
                               text=True, env=dict(os.environ, HOME=d, ADMIRAL_CONFIG=cfg,
                                                   PATH=fake + os.pathsep + os.environ["PATH"]))
            cmd = r.stdout.split("elsewhere run ", 1)[1].split(" every minute", 1)[0]
            self.assertEqual(cmd, f"ADMIRAL_CONFIG={shlex.quote(cfg)} {shlex.quote(ROOT + '/scripts/refresh.sh')}")

    def test_the_job_to_schedule_elsewhere_pastes_as_it_reads_whatever_the_path(self):
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "bin")
            os.makedirs(fake)
            with open(os.path.join(fake, "uname"), "w") as fh:
                fh.write("#!/bin/sh\necho Linux\n")
            os.chmod(os.path.join(fake, "uname"), 0o755)
            cfg = os.path.join(d, "O'Brien config.toml")
            r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "install.sh"), "--dry-run"], capture_output=True,
                               text=True, env=dict(os.environ, HOME=d, ADMIRAL_CONFIG=cfg,
                                                   PATH=fake + os.pathsep + os.environ["PATH"]))
            cmd = r.stdout.split("elsewhere run ", 1)[1].split(" every minute", 1)[0]
            # the shell reads it as two words: the assignment, the path whole, then the script
            said = subprocess.run(["/bin/sh", "-c", f'set -- {cmd}; printf "%s\\n" "$@"'], capture_output=True, text=True)
            self.assertEqual(said.stdout.splitlines()[0], f"ADMIRAL_CONFIG={cfg}")

    def test_no_memory_advice_once_it_is_off(self):
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "home")
            os.makedirs(os.path.join(home, ".claude"))
            with open(os.path.join(home, ".claude", "settings.json"), "w") as fh:
                fh.write('{"autoMemoryEnabled": false}')
            r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "install.sh"), "--dry-run"], capture_output=True,
                               text=True, env=dict(os.environ, HOME=home, ADMIRAL_CONFIG=os.path.join(d, "c.toml")))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("autoMemoryEnabled", r.stdout)


class SpacedPath(unittest.TestCase):
    def test_the_printed_status_line_command_runs_from_a_path_with_a_space(self):
        with tempfile.TemporaryDirectory() as d:
            spaced = os.path.join(d, "my tools")
            os.makedirs(spaced)
            os.symlink(ROOT, os.path.join(spaced, "admiral"))
            home = os.path.join(d, "home")
            os.makedirs(os.path.join(home, ".claude"))
            env = dict(os.environ, HOME=home, ADMIRAL_CONFIG=os.path.join(d, "config.toml"))
            out = subprocess.run(["bash", os.path.join(spaced, "admiral", "scripts", "install.sh"), "--dry-run"],
                                 capture_output=True, text=True, env=env).stdout
            line = next(ln for ln in out.splitlines() if '"statusLine"' in ln)
            command = json.loads("{" + line.strip() + "}")["statusLine"]["command"]
            r = subprocess.run(["sh", "-c", command], input="{}", capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Admiral", r.stdout)


if __name__ == "__main__":
    unittest.main()
