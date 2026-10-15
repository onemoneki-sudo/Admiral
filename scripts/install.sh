#!/bin/bash
# Set Admiral up on macOS:
#   scripts/install.sh [--dry-run]      config template, the every-minute background job, `admiral` on the PATH
#                                       (~/.local/bin), then what to paste
#   scripts/install.sh --uninstall      stop and remove the background job and the link (config and state are kept)
# It never edits Claude Code's own settings: the status line and plugin steps are printed for you to run.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
label="com.admiral.board"
plist="$HOME/Library/LaunchAgents/$label.plist"
config="${ADMIRAL_CONFIG:-$HOME/.config/admiral/config.toml}"
# a config of its own, as the background job will find it: from anywhere, with none of this shell's environment
own_config=""
if [ -n "${ADMIRAL_CONFIG:-}" ]; then
  case "$ADMIRAL_CONFIG" in /*|"~"*) own_config="$ADMIRAL_CONFIG";; *) own_config="$PWD/$ADMIRAL_CONFIG";; esac
fi
dry=0; [ "${1:-}" = "--dry-run" ] && dry=1
run() { if [ $dry -eq 1 ]; then echo "would run: $*"; else "$@"; fi; }

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  rm -f "$plist"; echo "removed the background job $label"
  [ "$(readlink "$HOME/.local/bin/admiral" 2>/dev/null)" = "$here/bin/admiral" ] && rm -f "$HOME/.local/bin/admiral" && echo "removed ~/.local/bin/admiral"
  exit 0
fi

# The background job and Claude Code do not see your shell's PATH (pyenv, conda, mise, uv...): the Python checked here
# is recorded by full path in .python-path, which bin/admiral reads.
py="${ADMIRAL_PYTHON:-$(command -v python3 || true)}"
[ -n "$py" ] && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' ||
  { echo "Admiral needs Python 3.11 or newer as python3 (or set ADMIRAL_PYTHON to one)" >&2; exit 1; }
py="$("$py" -c 'import sys; print(sys.executable)')"
command -v gh >/dev/null || echo "note: gh (GitHub CLI) not found: the board will show no PRs or CI until it is installed and signed in"
job_env=""; [ -n "$own_config" ] && job_env="ADMIRAL_CONFIG='$own_config' "
[ "$(uname)" = Darwin ] || { echo "the background job is set up for macOS only; elsewhere run ${job_env}'$here/scripts/refresh.sh' every minute (cron, a systemd timer)"; }

if [ $dry -eq 1 ]; then echo "would record the Python $py in $here/.python-path"
else printf '%s\n' "$py" > "$here/.python-path"; echo "using Python $py"; fi

# 1. Config: a commented template, only when there is none.
if [ ! -f "$config" ]; then
  base=""
  settings="$HOME/.claude/settings.json"
  if [ -f "$settings" ]; then  # an existing status line (claude-hud, say) runs first, above Admiral's lines
    base="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("statusLine",{}).get("command",""))' "$settings" 2>/dev/null || true)"
    case "$base" in *"admiral statusline"*) base="";; esac
  fi
  base_toml="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$base")"
  template="# Admiral's configuration. Every key is optional; see admiral/config.py for all of them.
language = \"en\"                      # \"en\" or \"zh\"

[sessions]
project_dirs = []                    # e.g. [\"~/code/myapp\"]: show only sessions working there; empty shows all
commander_prefix = \"Commander\"       # a session whose name starts with this is a commander

[github]
repo_dir = \"\"                        # e.g. \"~/code/myapp\": where gh reads PRs and checks; empty: none

[statusline]
base = $base_toml"
  if [ $dry -eq 1 ]; then echo "would write $config:"; echo "$template" | sed 's/^/    /'
  else mkdir -p "$(dirname "$config")"; printf '%s\n' "$template" > "$config"; echo "wrote $config: edit project_dirs and repo_dir"; fi
else
  echo "keeping $config"
fi

# 2. The background job: `admiral board --write` every minute. launchd starts it without the shell's environment, so
# a config of its own (ADMIRAL_CONFIG) goes in the job, or the job would build another board than the sessions read.
if [ "$(uname)" = Darwin ]; then
  env_keys=""
  if [ -n "$own_config" ]; then
    xml="$(printf '%s' "$own_config" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g')"
    env_keys="
  <key>EnvironmentVariables</key><dict><key>ADMIRAL_CONFIG</key><string>$xml</string></dict>"
  fi
  job="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$here/scripts/refresh.sh</string></array>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>$env_keys
</dict></plist>"
  if [ $dry -eq 1 ]; then echo "would write $plist and load it:"; echo "$job" | sed 's/^/    /'
  else
    mkdir -p "$(dirname "$plist")"
    printf '%s\n' "$job" > "$plist"
    launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$plist"; echo "loaded the background job $label (every minute)"
  fi
fi

# 3. `admiral` on the PATH, so sessions run it by name: a link in ~/.local/bin.
link="$HOME/.local/bin/admiral"
if [ "$(readlink "$link" 2>/dev/null)" = "$here/bin/admiral" ]; then
  echo "keeping $link"
elif [ -e "$link" ] || [ -L "$link" ]; then
  echo "note: $link exists and is not Admiral's; left as it is"
else
  run mkdir -p "$HOME/.local/bin"; run ln -s "$here/bin/admiral" "$link"
  [ $dry -eq 1 ] || echo "linked $link"
fi
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "note: add ~/.local/bin to your PATH, so sessions find admiral";; esac

# 4. What only you should change: Claude Code's settings.
cat <<NEXT

Next, by hand:

  1. Status line: in ~/.claude/settings.json set
       "statusLine": {"type": "command", "command": "'$here/bin/admiral' statusline", "refreshInterval": 20}
     (your previous status line, if any, is kept in the config's [statusline] base and still runs first)

  2. Sidebar and playbook skills:
       claude plugin marketplace add '$here'
       claude plugin install admiral@admiral

  3. Check: '$here/bin/admiral' doctor   (what is in place, and how to fix the rest)
NEXT

# Automatic memory, read and never changed: recommended off, so what a session knows comes from files you can read.
settings="$HOME/.claude/settings.json"
memory="$(python3 -c 'import json,sys; print("off" if json.load(open(sys.argv[1])).get("autoMemoryEnabled") is False else "on")' "$settings" 2>/dev/null || echo on)"
if [ "$memory" = on ]; then cat <<MEMORY

Recommended: Claude Code's automatic memory is on. Many sessions should not share notes nobody can see; with it off,
what a session knows comes from the task brief, the decision log and your rules, files you can read and correct.
It applies to all your projects, so it is your call. To turn it off, add to ~/.claude/settings.json:
       "autoMemoryEnabled": false
MEMORY
fi
