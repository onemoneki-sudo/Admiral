#!/bin/bash
# Shared-resource locks for parallel AI sessions on one machine. Run it as `admiral lock ...`.
# A lock is a directory (mkdir is atomic); its "owner" file says who holds it and how to tell
# whether the holder is gone. The board reads the owners to tell which sessions still hold resources.
#
# Directory: $ADMIRAL_LOCKS_DIR (admiral sets it from the config's [locks] dir, default <state_dir>/locks).
# Commanders allowed to reorder a line: one session name per line in $ADMIRAL_LOCK_COMMANDERS
# (default <locks dir>/../lock-commanders.txt).
#
#   admiral lock acquire <name> --who "<session> <task>" [--pid <pid>] [--ttl <minutes>]
#        exit 0 = acquired; exit 1 = busy (prints the holder)
#   admiral lock attach  <name> --who "<same who>" --pid <pid>   record the job's pid after starting it
#   admiral lock release <name> --who "<same who>"               only the holder releases
#   admiral lock status                                          every lock, holder, age, stale or not
#   admiral lock port    --who "<session> <task>" [--from 8100 --to 8199]   claim a free port, prints it
#   admiral lock stats   [--days 30]                             how often each lock was waited for, and how
#        long it was waited for and held (admiral/lockstats.py), from the history below
#
# History: each take (with how long its taker waited in line) and each release (with how long it was
# held) is a line of $DIR/.history/<year>-<month>.log, tab-separated: time, take|release, lock (its %, tab
# and newline coded %25, %09, %0A), seconds, who. The three latest months are kept. A history that cannot be
# written never fails the lock.
#
# A lock is STALE (and acquire takes it over, saying so) when its recorded pid no longer runs, or when it has no
# pid, is older than its ttl (default 180 minutes) and the session it was taken in no longer runs: the nearest
# claude or codex process above the command that took it (or $ADMIRAL_LOCK_SESSION, a pid, or `none`), recorded
# with its start time, so a service whose session still runs keeps its port however long it runs. Acquire and port
# warn of a lock taken without a pid. The pid is of what uses the resource for as long as it is needed, not of a
# step that ends sooner.
#
# A takeover is kept in $DIR/.taken/<name>/, one record per holder displaced (the owner it replaced, who took it, when
# and why), written once the lock is the taker's: the holder it was taken
# from is told so when it next acquires, attaches or releases that lock, rather than finding out from a clash, and
# `status` lists the takeovers of the last day.
#
# Names that differ only in case are one lock on a disk that ignores case, as macOS's does: acquire and queue refuse a
# name that differs only in case from a lock held or waited for, and name its holder, rather than wait for it unseen.
#
# Waiting line. Each lock has a line of waiters, ordered by priority (higher first,
# default 0), then by arrival. A free lock goes only to the first waiter in its line; with nobody
# waiting, acquire behaves as above. The line only decides who may try: holding is still the mkdir
# above, so two holders are impossible however old and new callers mix.
#
#   admiral lock acquire <name> --who "..." --wait [--priority N] [--pid <pid>] [--ttl <minutes>]
#        joins the line and blocks until acquired (exit 0); run it in the background.
#        --pid/--ttl describe the holder once acquired, exactly as for a plain acquire
#   admiral lock queue   <name> --who "..." [--priority N] [--pid <pid>] [--ttl <minutes>]
#        joins the line without blocking; then poll acquire with the same --who
#   admiral lock leave   <name> --who "..."                      leaves the line
#   admiral lock prio    <name> --who "<a waiter's who>" --priority N --by "<commander>"
#        reorders the line; --by must be a line of lock-commanders.txt. A waiter's own --priority
#        counts only when it joins; changing it later is this command's job
#
# A plain acquire that does not get the lock keeps its caller's place in the line (by --who), so
# an existing `until admiral lock acquire ...; do sleep 30; done` loop waits its turn. Waiters leave the
# line by the STALE rule: their pid no longer runs, or, without a pid, they are past their ttl.
# Plain-acquire loops and --wait must also keep coming back: one not seen for 2 minutes has left.
# A queue entry not seen for 2 minutes keeps its place but is passed over until it polls again.
set -u
DIR="${ADMIRAL_LOCKS_DIR:-$HOME/.local/state/admiral/locks}"
COMMANDERS="${ADMIRAL_LOCK_COMMANDERS:-$(dirname "$DIR")/lock-commanders.txt}"
mkdir -p "$DIR"
cmd="${1:-status}"; shift || true
name=""; who=""; pid=""; ttl=180; from=8100; to=8199; prio=""; wait=0; by=""
if [ "$cmd" != "status" ] && [ "$cmd" != "port" ]; then name="${1:-}"; shift || true; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --who) who="$2"; shift 2;; --pid) pid="$2"; shift 2;; --ttl) ttl="$2"; shift 2;;
    --from) from="$2"; shift 2;; --to) to="$2"; shift 2;;
    --priority) prio="$2"; shift 2;; --by) by="$2"; shift 2;; --wait) wait=1; shift;;
    *) echo "unknown argument: $1" >&2; exit 2;;
  esac
done
if [ -n "$prio" ] && ! [[ "$prio" =~ ^-?[0-9]{1,2}$ ]]; then echo "--priority is an integer from -99 to 99" >&2; exit 2; fi
now() { date +%s; }
field() { sed -n "s/^$2=//p" "$1/owner" 2>/dev/null | head -1; }
hhmm() { date -r "$1" +%H:%M 2>/dev/null || date -d "@$1" +%H:%M 2>/dev/null; }  # an epoch as a time of day
started() { LC_ALL=C TZ=UTC ps -o lstart= -p "$1" 2>/dev/null | sed 's/^ *//; s/ *$//'; }  # with its pid, tells a
# process apart: in one zone and language whoever asks, so a holder and a taker read the same time alike
session_of() { # the session this command runs under (see the top): its pid, or nothing
  case "${ADMIRAL_LOCK_SESSION:-}" in none) return 0;; *[!0-9]*) ;; ?*) echo "$ADMIRAL_LOCK_SESSION"; return 0;; esac
  ps -A -o pid=,ppid=,comm= 2>/dev/null | awk -v p=$$ '
    { c = $3; for (i = 4; i <= NF; i++) c = c " " $i; n = split(c, part, "/"); up[$1] = $2; name[$1] = part[n] }
    END { for (i = 0; i < 64 && p > 1; i++) { p = up[p]; if (name[p] == "claude" || name[p] == "codex") { print p; exit } } }'
}
session_runs() { # $1 = lock dir: the session it was taken in still runs (the same process, by its start time)
  local s; s="$(field "$1" session)"
  [ -n "$s" ] && kill -0 "$s" 2>/dev/null && [ "$(started "$s")" = "$(field "$1" session_start)" ]
}
past_ttl() { local t l; t="$(field "$1" since)"; l="$(field "$1" ttl)"; [ -n "$t" ] && [ $(( $(now) - t )) -gt $(( ${l:-180} * 60 )) ]; }
is_stale() { # $1 = lock dir
  local p; p="$(field "$1" pid)"
  if [ -n "$p" ]; then kill -0 "$p" 2>/dev/null && return 1 || return 0; fi
  past_ttl "$1" && ! session_runs "$1"
}
describe() { # $1 = lock dir
  local t note=""; t="$(field "$1" since)"
  if is_stale "$1"; then note=' | STALE'
  elif [ -z "$(field "$1" pid)" ] && past_ttl "$1"; then note=" | past its ttl, kept: its session (pid $(field "$1" session)) still runs"
  fi
  printf '%-22s held by: %s | pid: %s | %s min ago%s\n' "$(basename "$1")" "$(field "$1" who)" \
    "$(field "$1" pid)" "$(( ($(now) - ${t:-$(now)}) / 60 ))" "$note"
}
write_owner() {
  local s=""; [ -n "$pid" ] || s="$(session_of)"
  { printf 'who=%s\npid=%s\nsince=%s\nttl=%s\n' "$who" "$pid" "$(now)" "$ttl"
    [ -z "$s" ] || printf 'session=%s\nsession_start=%s\n' "$s" "$(started "$s")"; } > "$DIR/$1/owner"
  [ -z "$pid" ] || return 0
  local again="admiral lock attach $(printf %q "$1") --who $(printf %q "$who") --pid <pid>"
  if [ -n "$s" ]; then
    echo "warning: $1 has no pid, so after $ttl minutes it is kept only while this session (pid $s) runs, and may" \
      "be taken over once it ends even while in use; record the process that uses it: $again" >&2
  else
    echo "warning: $1 has no pid, so after $ttl minutes it counts as stale and may be taken over even while in use;" \
      "record the process that uses it: $again" >&2
  fi
}
taken_why() { # $1 = a stale lock: why it is stale, in words
  local p; p="$(field "$DIR/$1" pid)"
  if [ -n "$p" ]; then echo "its pid $p no longer ran"
  else echo "it had no pid and was past its $(field "$DIR/$1" ttl)-minute ttl$([ -n "$(field "$DIR/$1" session)" ] && echo ", its session ended")"
  fi
}
note_takeover() { # $1 = a lock just taken over, $2 = the owner it had, $3 = why: one record per holder displaced, in
  local d="$DIR/.taken/$1" f  # $DIR/.taken/<name>/<time>.<pid>, written only once the lock is the taker's
  f="$(now).$$"
  { mkdir -p "$d" && { printf '%s\n' "$2"; printf 'taken_by=%s\ntaken_at=%s\nwhy=%s\n' "$who" "$(now)" "$3"; } \
      > "$d/.tmp.$$" && mv -f "$d/.tmp.$$" "$d/$f"; } 2>/dev/null
  rm -f "$d/.tmp.$$" 2>/dev/null
  return 0
}
taken_records() { # $1 = lock name: the records of its takeovers from $who, oldest first
  local f
  for f in "$DIR/.taken/$1"/*; do
    [ -f "$f" ] && [ "$(sed -n 's/^who=//p' "$f" | head -1)" = "$who" ] && echo "$f"
  done
  return 0
}
taken_from_me() { # $1 = lock name: when it was taken over from $who, says so (stderr) and succeeds
  local f by at why
  f="$(taken_records "$1" | tail -1)"; [ -n "$f" ] || return 1
  by="$(sed -n 's/^taken_by=//p' "$f" | head -1)"; at="$(sed -n 's/^taken_at=//p' "$f" | head -1)"
  why="$(sed -n 's/^why=//p' "$f" | head -1)"
  echo "note: $1 was taken over from you at $(hhmm "$at") by $by ($why). Whatever of yours still uses it (a" \
    "service on that port, say) now shares it with them: stop it, or take another" >&2
}
forget_taken() { # $1 = lock name, its own again: the records of its takeovers from $who have been told
  local f
  while IFS= read -r f; do rm -f "$f"; done < <(taken_records "$1")
  rmdir "$DIR/.taken/$1" 2>/dev/null
  return 0
}
case_twin() { # a lock held, or a line someone still waits in, whose name differs from $name only in case: its name
  local e b f live all=()
  NOW=$(now)
  for e in "$DIR"/*/ "$DIR"/.q.*/; do
    [ -d "$e" ] || continue
    b="${e%/}"; b="${b##*/}"
    case "$b" in .q.*)
      b="${b#.q.}"; live=0
      for f in "$e"*; do read_entry "$f" && ! entry_stale && { live=1; break; }; done
      [ $live -eq 1 ] || continue;;
    esac
    shopt -s nocasematch
    case "$b" in "$name") all+=("$b");; esac
    shopt -u nocasematch
  done
  for b in ${all[@]+"${all[@]}"}; do [ "$b" != "$name" ] && { echo "$b"; return 0; }; done
  return 1
}
spelling_lock() { # held while a name is checked against the others' and joins its line, so two spellings of one
  local m="$DIR/.spelling" i  # name taken at once still see each other; never held long, never waited on for long
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
    mkdir "$m" 2>/dev/null && return 0
    [ -n "$(find "$m" -maxdepth 0 -mmin +1 2>/dev/null)" ] && rmdir "$m" 2>/dev/null  # a dead holder's mark
    sleep 0.1
  done
  return 0
}
spelling_unlock() { rmdir "$DIR/.spelling" 2>/dev/null; return 0; }
refuse_twin() { # acquire and queue, under spelling_lock: never wait unseen for a lock spelled otherwise
  local t; t="$(case_twin)" || return 0
  spelling_unlock
  if [ -d "$DIR/$t" ] && [ -n "$(field "$DIR/$t" who)" ]; then
    local since; since="$(field "$DIR/$t" since)"
    echo "$name: the lock $t is held by $(field "$DIR/$t" who) (for $(( ($(now) - ${since:-$(now)}) / 60 )) min)." >&2
  else
    echo "$name: $t has a line of waiters." >&2
  fi
  echo "Names that differ only in case are one lock on a disk that ignores case, as macOS's does, so $name would" \
    "wait for it. To share that resource, name it $t; for another one, use a name that differs in more than case." >&2
  exit 2
}
record() { # $1 = take|release, $2 = lock, $3 = since when it waited or was held (none: not at all)
  local h="$DIR/.history" d t s m w="${who//$'\t'/ }" l="${2//"%"/%25}" all
  w="${w//$'\n'/ }"; l="${l//$'\t'/%09}"; l="${l//$'\n'/%0A}"  # five fields whatever the names hold, the lock's
  # name kept whole (lockstats.py reads it back), so two locks named alike stay two
  { d="$(date '+%s %Y-%m')"; t="${d% *}"; m="$h/${d#* }.log"  # one date for it all: a process each is slow
    case "${3:-}" in ''|*[!0-9]*) s=0;; *) s=$(( t - $3 )); [ $s -lt 0 ] && s=0;; esac
    if [ ! -e "$m" ]; then  # a new month: the history keeps the three latest
      mkdir -p "$h" && : >> "$m" || return 0
      all=( "$h"/[0-9][0-9][0-9][0-9]-[0-9][0-9].log )
      [ ${#all[@]} -gt 3 ] && rm -f "${all[@]:0:$(( ${#all[@]} - 3 ))}"
    fi
    [ -f "$m" ] || return 0  # a pipe or a device there would hold the lock command up, perhaps for good
    printf '%s\t%s\t%s\t%s\t%s\n' "$t" "$1" "$l" "$s" "$w" >> "$m"
  } 2>/dev/null  # nothing of it on the lock command's output, nor in its exit
  return 0
}
took() { # $1 = lock just taken, recorded with the wait of $me's place in its line, read before it goes
  local from=""
  read_entry "$Q/$me" && from=$(( e_arrival / 1000000 ))
  record take "$1" "$from"
}
need_who() { [ -n "$who" ] || { echo "--who is required" >&2; exit 2; }; }
need_name() { [ -n "$name" ] || { echo "lock name required" >&2; exit 2; }; }
# Taking over a stale lock is check-then-write, so two waiters could both find it stale and both
# "acquire" it. One takeover at a time, under its own mkdir mark, re-checked inside.
takeover() { # $1 = lock name; succeeds for one caller only, and only while the lock is still stale
  local m="$DIR/.$1.takeover"
  if ! mkdir "$m" 2>/dev/null; then
    [ -n "$(find "$m" -maxdepth 0 -mmin +1 2>/dev/null)" ] && rmdir "$m" 2>/dev/null  # a dead taker's mark
    return 1
  fi
  if [ -d "$DIR/$1" ] && is_stale "$DIR/$1"; then
    local was why; was="$(cat "$DIR/$1/owner" 2>/dev/null)"; why="$(taken_why "$1")"
    write_owner "$1"; note_takeover "$1" "$was" "$why"; rmdir "$m"; return 0
  fi
  if mkdir "$DIR/$1" 2>/dev/null; then write_owner "$1"; rmdir "$m"; return 0; fi
  rmdir "$m"; return 1
}

# --- The waiting line: $DIR/.q.<name>/<md5 of who>, one file per waiter, replaced whole (mv), so
# --- readers never see half an entry. A commander's priority lives beside it in .prio.<key>, which
# --- waiters never write, so their own refreshes cannot undo it. A line empty and unchanged for a minute
# --- goes when a lock is taken, released or left, or the lines are shown (tidy_lines): kept, one per name
# --- ever used (a run per service, say), they made every acquire and status walk them all. A waiter
# --- coming in as its line goes makes it again (write_entry), and a line so new is left alone.
AWAKE=120                      # seconds: a waiter not seen for this long is not waiting now
Q="$DIR/.q.$name"
key() { if [ -x /sbin/md5 ]; then /sbin/md5 -qs "$1"; else printf '%s' "$1" | md5sum | cut -d' ' -f1; fi; }
usec() { /usr/bin/perl -MTime::HiRes=time -e 'printf "%d\n", time*1e6'; }
read_entry() { # $1 = entry file; sets e_*; returns 1 when it is gone
  e_who=; e_pid=; e_base=0; e_arrival=0; e_seen=0; e_ttl=180; e_kind=poll; e_by=
  local l o="${1%/*}/.prio.${1##*/}"
  [ -f "$1" ] || return 1
  { while IFS= read -r l; do
      case "$l" in
        who=*) e_who="${l#who=}";; pid=*) e_pid="${l#pid=}";; prio=*) e_base="${l#prio=}";;
        arrival=*) e_arrival="${l#arrival=}";; seen=*) e_seen="${l#seen=}";; ttl=*) e_ttl="${l#ttl=}";;
        kind=*) e_kind="${l#kind=}";;
      esac
    done; } 2>/dev/null < "$1" || return 1
  e_prio=$e_base
  [ -f "$o" ] && { while IFS= read -r l; do
      case "$l" in prio=*) e_prio="${l#prio=}";; by=*) e_by="${l#by=}";; esac
    done; } 2>/dev/null < "$o"
  return 0
}
write_entry() { # $1 = entry file, from e_*. Its line, empty for a minute, may go just as it comes: made again
  local d="${1%/*}" t="${1%/*}/.tmp.$$" n
  for n in 1 2 3 4 5 6 7 8 9 10; do  # each miss takes another sweep that saw the line old, just then
    mkdir -p "$d" && { printf 'who=%s\npid=%s\nprio=%s\narrival=%s\nseen=%s\nttl=%s\nkind=%s\n' \
      "$e_who" "$e_pid" "$e_base" "$e_arrival" "$e_seen" "$e_ttl" "$e_kind" > "$t"; } 2>/dev/null \
      && mv -f "$t" "$1" && return 0
  done
  return 1
}
drop_entry() { rm -f "$1" "${1%/*}/.prio.${1##*/}"; } # $1 = entry file
entry_stale() { # the entry just read, at $NOW
  if [ -n "$e_pid" ] && ! kill -0 "$e_pid" 2>/dev/null; then return 0; fi
  [ "$e_kind" != queue ] && [ $(( NOW - e_seen )) -gt $AWAKE ] && return 0
  [ -z "$e_pid" ] && [ $(( NOW - e_seen )) -gt $(( ${e_ttl:-180} * 60 )) ] && return 0
  return 1
}
entry_awake() { [ $(( NOW - e_seen )) -le $AWAKE ]; }
join_line() { # $1 = poll|wait|queue; keeps an existing place and priority, marks it seen now
  mkdir -p "$Q"; NOW=$(now); local f="$Q/$me"
  if read_entry "$f" && ! entry_stale; then
    if [ -z "${joined:-}" ] && [ -n "$prio" ] && [ "$prio" != "$e_prio" ]; then
      echo "already in line for $name at priority $e_prio; only a commander changes it (admiral lock prio)" >&2
    fi
    case "$1" in
      wait) e_kind=wait; e_pid=$$;;
      queue) [ "$e_kind" = wait ] || e_kind=queue; [ -n "$pid" ] && e_pid="$pid"; e_ttl="$ttl";;
      poll) [ "$e_kind" = poll ] && e_pid="$pid";;
    esac
  else
    drop_entry "$f"
    e_who="$who"; e_base="${prio:-0}"; e_arrival="$(usec)"; e_kind="$1"; e_ttl="$ttl"
    if [ "$1" = wait ]; then e_pid=$$; else e_pid="$pid"; fi
  fi
  e_seen=$NOW
  write_entry "$f" || { echo "could not write a place in the line for $name ($f)" >&2; return 1; }
  joined=1
}
in_order() { # $1 = line dir; "prio|arrival|file" of every entry, first waiter first
  local f
  for f in "$1"/*; do read_entry "$f" && printf '%s|%s|%s\n' "$e_prio" "$e_arrival" "$f"; done \
    | sort -t'|' -k1,1nr -k2,2n -k3,3
}
first_waiter() { # the entry file of the first waiter still waiting; drops waiters that have left
  local p a f; NOW=$(now)
  while IFS='|' read -r p a f; do
    read_entry "$f" || continue
    if entry_stale; then drop_entry "$f"; continue; fi
    entry_awake && { echo "$f"; return; }
  done < <(in_order "$Q")
}
position() { # where $me stands among waiters still waiting
  local p a f n=0 mine=0 first=""; NOW=$(now)
  while IFS='|' read -r p a f; do
    read_entry "$f" && ! entry_stale && entry_awake || continue
    n=$((n+1)); [ -n "$first" ] || first="$e_who"; [ "${f##*/}" = "$me" ] && mine=$n
  done < <(in_order "$Q")
  echo "#$mine of $n in line (first: $first)"
}
show_line() { # $1 = line dir; for status
  local p a f n=0 note kind; NOW=$(now)
  while IFS='|' read -r p a f; do
    read_entry "$f" || continue; n=$((n+1)); note=""
    case "$e_kind" in wait) kind="acquire --wait";; queue) kind="queue";; *) kind="acquire loop";; esac
    [ -n "$e_by" ] && note=" | priority set by $e_by"
    if entry_stale; then note="$note | STALE"; elif ! entry_awake; then note="$note | not polling, passed over"; fi
    printf '    waiting #%d: %s | priority %s | %s min | pid: %s | %s%s\n' "$n" "$e_who" "$e_prio" \
      "$(( (NOW - e_arrival / 1000000) / 60 ))" "$e_pid" "$kind" "$note"
  done < <(in_order "$1")
}
leave_other_lines() { # a loop polling several locks under one --who leaves the rest once it holds one
  local q f
  for q in "$DIR"/.q.*/; do
    f="$q$me"; [ "${q%/}" != "$Q" ] && read_entry "$f" && [ "$e_kind" = poll ] && drop_entry "$f"
  done
  return 0
}
tidy_lines() { # the lines nobody is in, unchanged for a minute, go. It takes no waiter out of line and no
  local q f  # commander's priority away: a waiter that has left goes when its own line is next read (first_waiter),
  for q in "$DIR"/.q.*/; do  # as ever. Only what nobody writes any more goes, so no write in flight is undone
    [ -d "$q" ] || continue
    for f in "$q"*; do [ -e "$f" ] && continue 2; done  # someone is in line
    for f in "$q".tmp.*; do  # a place whose writing was cut short: never one being written, which takes no time
      [ -e "$f" ] && { find "$q" -maxdepth 1 -type f -name '.tmp.*' -mmin +1 -delete 2>/dev/null; break; }
    done
  done
  # in one call: a process each took seconds over a backlog of hundreds
  find "$DIR" -mindepth 1 -maxdepth 1 -type d -name '.q.*' -empty -mmin +1 -exec rmdir {} + 2>/dev/null
  [ -d "$DIR/.taken" ] && { find "$DIR/.taken" -type f -mmin +10080 -delete  # takeovers, kept a week
    find "$DIR/.taken" -mindepth 1 -type d -empty -delete; } 2>/dev/null
  return 0
}

case "$cmd" in
  acquire)
    need_who; need_name; me="$(key "$who")"
    taken_from_me "$name"
    spelling_lock; refuse_twin
    if [ $wait -eq 1 ]; then
      trap 'rm -f "$Q/.tmp.$$"; drop_entry "$Q/$me"' EXIT; trap 'exit 130' INT TERM HUP
      join_line wait || { spelling_unlock; exit 2; }
    else
      join_line poll || { spelling_unlock; exit 2; }
    fi
    spelling_unlock
    shown=""; seen_at=$(now)
    while :; do
      first="$(first_waiter)"
      if [ -z "$first" ] || [ "${first##*/}" = "$me" ]; then
        if mkdir "$DIR/$name" 2>/dev/null; then
          write_owner "$name"; took "$name"; drop_entry "$Q/$me"; leave_other_lines; tidy_lines
          forget_taken "$name"  # its own again: what was taken from it has been told
          echo "acquired $name"; exit 0
        fi
        if is_stale "$DIR/$name"; then
          was="$(describe "$DIR/$name")"
          if takeover "$name"; then
            took "$name"; drop_entry "$Q/$me"; leave_other_lines; tidy_lines
            echo "taking over stale lock: $was"; echo "acquired $name"; exit 0
          fi
        fi
      fi
      if [ $wait -eq 0 ]; then
        if [ -d "$DIR/$name" ] || ! read_entry "$first"; then echo "busy: $(describe "$DIR/$name")"
        else echo "busy: $name is free; first in line: $e_who"; fi
        exit 1
      fi
      since="$(field "$DIR/$name" since)"
      now_line="$(position) | holder: $(field "$DIR/$name" who)${since:+, since $(hhmm "$since")}"
      [ "$now_line" != "$shown" ] && { echo "waiting for $name: $now_line"; shown="$now_line"; }
      sleep 3
      [ $(( $(now) - seen_at )) -ge 30 ] && { join_line wait; seen_at=$(now); }  # failing, it tries again
    done;;
  queue)
    need_who; need_name; me="$(key "$who")"; spelling_lock; refuse_twin
    join_line queue || { spelling_unlock; exit 2; }; spelling_unlock; echo "in line for $name: $(position)";;
  leave)
    need_who; need_name; me="$(key "$who")"
    if [ -f "$Q/$me" ]; then drop_entry "$Q/$me"; echo "left the line for $name"; else echo "not in line for $name"; fi
    tidy_lines;;
  prio)
    need_who; need_name; [ -n "$prio" ] || { echo "--priority is required" >&2; exit 2; }
    if [ -z "$by" ] || ! grep -Fxq -- "$by" "$COMMANDERS" 2>/dev/null; then
      echo "only a commander listed in $COMMANDERS changes priorities (--by)" >&2; exit 1
    fi
    me="$(key "$who")"; read_entry "$Q/$me" || { echo "$who is not in line for $name" >&2; exit 1; }
    t="$Q/.tmp.prio.$$"
    if ! { printf 'prio=%s\nby=%s\n' "$prio" "$by" > "$t" && mv -f "$t" "$Q/.prio.$me"; } 2>/dev/null; then
      rm -f "$t"  # the priority it had stays
      if read_entry "$Q/$me"; then echo "could not write the priority of $who for $name" >&2
      else echo "$who is not in line for $name" >&2; fi
      exit 1
    fi
    if ! read_entry "$Q/$me"; then  # it left the line just as it was set: nobody's priority now
      rm -f "$Q/.prio.$me"; echo "$who is not in line for $name" >&2; exit 1
    fi
    echo "priority of $who for $name is now $prio (set by $by)"; show_line "$Q";;
  attach)
    need_who; [ "$(field "$DIR/$name" who)" = "$who" ] || { taken_from_me "$name"; echo "not the holder of $name" >&2; exit 1; }
    t="$DIR/$name/owner.tmp.$$"; sed "s/^pid=.*/pid=$pid/" "$DIR/$name/owner" > "$t" && mv -f "$t" "$DIR/$name/owner"
    echo "attached pid $pid to $name";;
  release)
    need_who; [ -d "$DIR/$name" ] || { taken_from_me "$name"; echo "$name is not held"; exit 0; }
    [ "$(field "$DIR/$name" who)" = "$who" ] || {
      taken_from_me "$name"; echo "not the holder of $name: $(describe "$DIR/$name")" >&2; exit 1; }
    record release "$name" "$(field "$DIR/$name" since)"
    rm -f "$DIR/$name/owner"; rmdir "$DIR/$name"; echo "released $name"; tidy_lines;;
  status)
    tidy_lines  # nothing in them to show, and the walk below took seconds over hundreds of them
    found=0; for d in "$DIR"/*/; do [ -d "$d" ] || continue; found=1; describe "${d%/}"; show_line "$DIR/.q.$(basename "$d")"; done
    [ $found -eq 1 ] || echo "no locks held"
    for q in "$DIR"/.q.*/; do
      [ -d "$q" ] || continue; n="${q%/}"; n="${n##*/.q.}"
      [ -d "$DIR/$n" ] && continue; [ -n "$(in_order "${q%/}")" ] || continue
      printf '%-22s free | waiters:\n' "$n"; show_line "${q%/}"
    done
    first=1
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      [ $first -eq 1 ] && { echo "taken over in the last day:"; first=0; }
      t="$(sed -n 's/^taken_at=//p' "$f" | head -1)"; n="${f%/*}"; n="${n##*/}"
      printf '  %s at %s from %s by %s: %s\n' "$n" "$(hhmm "$t")" "$(sed -n 's/^who=//p' "$f" | head -1)" \
        "$(sed -n 's/^taken_by=//p' "$f" | head -1)" "$(sed -n 's/^why=//p' "$f" | head -1)"
    done < <(find "$DIR/.taken" -type f -mmin -1440 ! -name '.tmp.*' 2>/dev/null | sort);;
  port)
    need_who
    for p in $(seq "$from" "$to"); do
      lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 && continue
      if mkdir "$DIR/port-$p" 2>/dev/null; then write_owner "port-$p"; record take "port-$p"; echo "$p"; exit 0; fi
      if is_stale "$DIR/port-$p" && takeover "port-$p"; then record take "port-$p"; echo "$p"; exit 0; fi
    done
    echo "no free port in $from-$to" >&2; exit 1;;
  *) echo "unknown command: $cmd" >&2; exit 2;;
esac
