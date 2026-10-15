"""Bring a session's terminal tab to the front, by the tty it runs on (the board records each session's tty).

macOS only: Terminal.app or iTerm2, whichever runs a tab on that tty; a running app is asked, none is launched.
"""

import re
import subprocess

SCRIPT = '''
on run argv
  set target to item 1 of argv
  if application "Terminal" is running then
    tell application "Terminal"
      repeat with w in windows
        repeat with t in tabs of w
          if tty of t is target then
            set selected of t to true
            set index of w to 1
            activate
            return "Terminal"
          end if
        end repeat
      end repeat
    end tell
  end if
  if application "iTerm2" is running then
    tell application "iTerm2"
      repeat with w in windows
        repeat with t in tabs of w
          repeat with s in sessions of t
            if tty of s is target then
              select t
              select w
              activate
              return "iTerm2"
            end if
          end repeat
        end repeat
      end repeat
    end tell
  end if
  error "no tab on " & target number 1
end run
'''


def focus(tty):
    """0 brought to front, 1 no tab on that tty, 2 not a terminal device."""
    tty = tty if tty.startswith("/dev/") else "/dev/" + tty
    if not re.fullmatch(r"/dev/tty[a-z]*[0-9]+", tty):
        return 2
    r = subprocess.run(["osascript", "-", tty], input=SCRIPT, capture_output=True, text=True)
    return 0 if r.returncode == 0 else 1
