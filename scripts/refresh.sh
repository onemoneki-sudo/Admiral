#!/bin/bash
# Run every minute by the background job: one `admiral board --write` for every session to read.
# launchd starts with a bare PATH, so the usual places of gh, python3 and git are put on it. Each run
# overwrites <state_dir>/last-error.txt with its own stderr (empty when it went well), so nothing grows; emptied as
# the run begins, it also tells a late board whose refresh is under way (slow) from one nobody refreshes (stopped).
# When Admiral cannot even say where its state is (no usable Python, a broken config), the reason goes to the
# default state directory, where the status line looks for it.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
here="$(cd "$(dirname "$0")/.." && pwd)"
fallback="$HOME/.local/state/admiral"  # config.py's default state_dir
if ! state="$("$here/bin/admiral" where 2> "${TMPDIR:-/tmp}/admiral-where.$$")" || [ -z "$state" ]; then
  mkdir -p "$fallback"
  mv -f "${TMPDIR:-/tmp}/admiral-where.$$" "$fallback/last-error.txt"
  exit 1
fi
rm -f "${TMPDIR:-/tmp}/admiral-where.$$"
mkdir -p "$state"
"$here/bin/admiral" board --write 2> "$state/last-error.txt"
code=$?
# Ended badly without a word (killed, say): left empty, the file would read as a refresh still under way.
if [ $code -ne 0 ] && [ ! -s "$state/last-error.txt" ]; then
  echo "admiral board --write ended with status $code" > "$state/last-error.txt"
fi
exit $code
