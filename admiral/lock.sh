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
#
# A lock is STALE (and acquire takes it over, saying so) when its recorded pid no longer runs,
# or when it has no pid and is older than its ttl (default 180 minutes), which acquire and port warn of.
# The pid is of what uses the resource for as long as it is needed, not of a step that ends sooner.
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
is_stale() { # $1 = lock dir
  local p t l; p="$(field "$1" pid)"; t="$(field "$1" since)"; l="$(field "$1" ttl)"
  if [ -n "$p" ]; then kill -0 "$p" 2>/dev/null && return 1 || return 0; fi
  [ -n "$t" ] && [ $(( $(now) - t )) -gt $(( ${l:-180} * 60 )) ] && return 0
  return 1
}
describe() { # $1 = lock dir
  local t; t="$(field "$1" since)"
  printf '%-22s held by: %s | pid: %s | %s min ago%s\n' "$(basename "$1")" "$(field "$1" who)" \
    "$(field "$1" pid)" "$(( ($(now) - ${t:-$(now)}) / 60 ))" "$(is_stale "$1" && echo ' | STALE')"
}
write_owner() {
  printf 'who=%s\npid=%s\nsince=%s\nttl=%s\n' "$who" "$pid" "$(now)" "$ttl" > "$DIR/$1/owner"
  [ -n "$pid" ] || echo "warning: $1 has no pid, so after $ttl minutes it counts as stale and may be taken over" \
    "even while in use; record the process that uses it: admiral lock attach $1 --who \"$who\" --pid <pid>" >&2
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
  if { [ -d "$DIR/$1" ] && is_stale "$DIR/$1"; } || mkdir "$DIR/$1" 2>/dev/null; then
    write_owner "$1"; rmdir "$m"; return 0
  fi
  rmdir "$m"; return 1
}

# --- The waiting line: $DIR/.q.<name>/<md5 of who>, one file per waiter, replaced whole (mv), so
# --- readers never see half an entry. A commander's priority lives beside it in .prio.<key>, which
# --- waiters never write, so their own refreshes cannot undo it.
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
write_entry() { # $1 = entry file, from e_*
  local t="${1%/*}/.tmp.$$"
  printf 'who=%s\npid=%s\nprio=%s\narrival=%s\nseen=%s\nttl=%s\nkind=%s\n' \
    "$e_who" "$e_pid" "$e_base" "$e_arrival" "$e_seen" "$e_ttl" "$e_kind" > "$t" && mv -f "$t" "$1"
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
  e_seen=$NOW; write_entry "$f"; joined=1
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

case "$cmd" in
  acquire)
    need_who; need_name; me="$(key "$who")"
    if [ $wait -eq 1 ]; then
      trap 'rm -f "$Q/$me" "$Q/.prio.$me" "$Q/.tmp.$$"' EXIT; trap 'exit 130' INT TERM HUP
      join_line wait
    else
      join_line poll
    fi
    shown=""; seen_at=$(now)
    while :; do
      first="$(first_waiter)"
      if [ -z "$first" ] || [ "${first##*/}" = "$me" ]; then
        if mkdir "$DIR/$name" 2>/dev/null; then
          write_owner "$name"; drop_entry "$Q/$me"; leave_other_lines; echo "acquired $name"; exit 0
        fi
        if is_stale "$DIR/$name"; then
          was="$(describe "$DIR/$name")"
          if takeover "$name"; then
            drop_entry "$Q/$me"; leave_other_lines
            echo "taking over stale lock: $was"; echo "acquired $name"; exit 0
          fi
        fi
      fi
      if [ $wait -eq 0 ]; then
        if [ -d "$DIR/$name" ] || ! read_entry "$first"; then echo "busy: $(describe "$DIR/$name")"
        else echo "busy: $name is free; first in line: $e_who"; fi
        exit 1
      fi
      now_line="$(position) | holder: $(field "$DIR/$name" who)"
      [ "$now_line" != "$shown" ] && { echo "waiting for $name: $now_line"; shown="$now_line"; }
      sleep 3
      [ $(( $(now) - seen_at )) -ge 30 ] && { join_line wait; seen_at=$(now); }
    done;;
  queue)
    need_who; need_name; me="$(key "$who")"; join_line queue; echo "in line for $name: $(position)";;
  leave)
    need_who; need_name; me="$(key "$who")"
    if [ -f "$Q/$me" ]; then drop_entry "$Q/$me"; echo "left the line for $name"; else echo "not in line for $name"; fi;;
  prio)
    need_who; need_name; [ -n "$prio" ] || { echo "--priority is required" >&2; exit 2; }
    if [ -z "$by" ] || ! grep -Fxq -- "$by" "$COMMANDERS" 2>/dev/null; then
      echo "only a commander listed in $COMMANDERS changes priorities (--by)" >&2; exit 1
    fi
    me="$(key "$who")"; read_entry "$Q/$me" || { echo "$who is not in line for $name" >&2; exit 1; }
    t="$Q/.tmp.prio.$$"; printf 'prio=%s\nby=%s\n' "$prio" "$by" > "$t" && mv -f "$t" "$Q/.prio.$me"
    echo "priority of $who for $name is now $prio (set by $by)"; show_line "$Q";;
  attach)
    need_who; [ "$(field "$DIR/$name" who)" = "$who" ] || { echo "not the holder of $name" >&2; exit 1; }
    t="$DIR/$name/owner.tmp.$$"; sed "s/^pid=.*/pid=$pid/" "$DIR/$name/owner" > "$t" && mv -f "$t" "$DIR/$name/owner"
    echo "attached pid $pid to $name";;
  release)
    need_who; [ -d "$DIR/$name" ] || { echo "$name is not held"; exit 0; }
    [ "$(field "$DIR/$name" who)" = "$who" ] || { echo "not the holder of $name: $(describe "$DIR/$name")" >&2; exit 1; }
    rm -f "$DIR/$name/owner"; rmdir "$DIR/$name"; echo "released $name";;
  status)
    found=0; for d in "$DIR"/*/; do [ -d "$d" ] || continue; found=1; describe "${d%/}"; show_line "$DIR/.q.$(basename "$d")"; done
    [ $found -eq 1 ] || echo "no locks held"
    for q in "$DIR"/.q.*/; do
      [ -d "$q" ] || continue; n="${q%/}"; n="${n##*/.q.}"
      [ -d "$DIR/$n" ] && continue; [ -n "$(in_order "${q%/}")" ] || continue
      printf '%-22s free | waiters:\n' "$n"; show_line "${q%/}"
    done;;
  port)
    need_who
    for p in $(seq "$from" "$to"); do
      lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 && continue
      if mkdir "$DIR/port-$p" 2>/dev/null; then write_owner "port-$p"; echo "$p"; exit 0; fi
      if is_stale "$DIR/port-$p" && takeover "port-$p"; then echo "$p"; exit 0; fi
    done
    echo "no free port in $from-$to" >&2; exit 1;;
  *) echo "unknown command: $cmd" >&2; exit 2;;
esac
