"""scripts/install.sh, in --dry-run: it changes nothing, and the config it would write parses."""

import json
import os
import subprocess
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
            self.assertEqual(recorded(), before)  # the dry run records no Python


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
