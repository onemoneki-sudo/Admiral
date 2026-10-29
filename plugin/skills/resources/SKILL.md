---
name: resources
description: How parallel AI sessions share scarce machine resources - locks and queues for heavy test runs, databases, browsers, model quota and ports - and how to tell an infrastructure failure from a real one. Read before running the whole test suite, database or browser tests, real model calls, a service that needs a port, or a job in the background meant to finish, and before deciding whether a failure is caused by the code.
---

# Shared resources

Where the project's own rules differ from this playbook, the project's rules win.

## Take a lock first

- Every scarce resource is behind a lock (`admiral lock`). A lock records its holder and pid; one whose holder exited
  or timed out may be taken over. Give it the pid of what uses the resource for as long as it is needed (the job, or
  the service holding a port), at once or with `admiral lock attach` once it starts: without one the lock times out
  even while in use, and with the pid of a step that ends sooner it is taken over when that step ends.
- If the lock is busy, queue (`admiral lock acquire --wait`); never go around it.
- Name the locks after what the project actually shares, for example: one heavy slot for whole-suite and browser runs,
  a few slots for a test database, a few for model quota, and ports handed out by the tool rather than picked by hand.

## Queueing

- Short jobs go first; nobody raises the priority of their own long job.
- Nothing waits forever: a commander raises a long job that has waited well past its turn (`admiral lock prio`).
- A job started in the background that is meant to finish gets a time limit from how long it should take: you hear
  when a job exits, not when it hangs, and a hung job keeps its lock. While you are still working, one making less
  progress than its expected time and output allow is looked into rather than waited on. Empty output, or no summary
  line, does not mean a job finished: check that it has exited, and how, before reading a result from it.

## When it was the machine, not the code

When contention crashes a worker, times out a browser or slows everything, the run says nothing about the code: rerun
it once the resource is free before investigating.

## Real model calls

- Where the product calls models, test and evaluate with the model and settings production uses now.
- When the provider starts rate limiting, stop; never push through it.
- Decide the question first and run the fewest calls that answer it, together at the end of a stage rather than after
  each small step; report how many calls and which model.
