---
name: resources
description: How parallel AI sessions share scarce machine resources - heavy test runs, databases, browsers, model quota, ports - through locks, and tell a machine failure from a real one. Read before running the whole test suite, database or browser tests, real model calls, a service that needs a port or a background job meant to finish, and before deciding whether a failure is caused by the code.
---

# Shared resources

What the machine has too little of is used under a lock for exactly as long as it is used, and a failure under
contention is not blamed on the code.

## Locks

- Use a scarce resource only under its lock, queueing when it is busy, never around it.
- Run what uses it with `admiral run --lock <name> --who "<session> <task>" --limit <minutes> -- <command>` (`admiral
  run --help`): it waits its turn, holds the lock exactly while the command runs, and at the end or the limit stops the
  command and all it started, then releases the lock.
- A service adds `--ready "<check>"`: the run returns once the check succeeds and leaves the service holding its locks
  until `admiral run stop --lock <name>` or the limit. `--port` gives it a free port as `$PORT`. Start it in the
  foreground (`postgres -D`, not `pg_ctl start`), since a daemon escapes what the run can stop, and under a lock named
  for it even when it holds nothing scarce, so it can be stopped and seen.
- `--lock 'db-1|db-2'` takes whichever slot frees first and must then be the run's only `--lock`, since waiting on a
  choice while holding another lock can deadlock two runs; the command reads the slot it got from `$ADMIRAL_LOCK`.
- `admiral run stop` stops whatever run holds that lock now: first check in `admiral lock status` that the holder is
  still your run (your `--who`, and the pid its ready line printed), as after a limit the slot may be another
  session's.
- A lock taken by hand (`admiral lock acquire|attach|release`) carries the pid of what uses the resource, or it can be
  taken over while still in use; told it was taken from you, stop using the resource.
- Spell a lock's name one way: names that differ only in case are one lock on a disk that ignores case.
- Release locks, ports and services as soon as you are done, not when the PR merges.
- Name locks after what the project shares (a heavy slot, database slots, model quota, ports from `admiral lock port`)
  and size them from `admiral lock stats`, not a guess.

## Queues and background jobs

- Short jobs first (`--priority`); nobody raises their own long job, and a commander raises one left waiting (`admiral
  lock prio`).
- A background job gets a time limit from how long it should take, since you hear when a job exits, not when it hangs;
  a shell's limit stops only the shell, `admiral run` stops everything.
- Look into a job slower than expected, and check that it exited, and how, before reading a result from it.

## The machine, not the code

A crash, a timeout or slowness under contention says nothing about the code: rerun once the resource is free before
investigating, and add no check of the machine before a run unless measurements show it catching something.

## Real model calls

- Use the model and settings production uses now, read from where they are set.
- Stop when the provider rate-limits; never push through it.
- Run the fewest calls that answer a settled question, together at the end of a stage, and report how many and which
  model.
